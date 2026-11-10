"""原件目录同步重试的隔离反例；进程退出与崩溃模型不冒充物理断电。"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.originals import Originals
import pmi.market_data.storage.originals as original_module


class OriginalDirectoryRetryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='wolf-original-sync-', dir='/private/tmp')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = Database(self.root)
        self.database.initialize()

    def assert_unregistered(self, identity):
        with Database(self.root).read() as connection:
            count = connection.execute('SELECT count(*) FROM original_object WHERE id=?', (identity,)).fetchone()[0]
        self.assertEqual(count, 0)
        with self.assertRaisesRegex(StorageError, 'storage_original_not_found'):
            Originals(Database(self.root)).get(identity)

    def fail_directory(self, database, raw, directory):
        """真实抛出目录同步错误，并验证SQL登记尚未开始。"""
        actual_sync = original_module.fsync_directory
        events = []

        def synchronized(path):
            events.append('sync:' + path.name)
            if path == self.root / directory:
                raise OSError('synthetic directory sync failure')
            actual_sync(path)

        def statement(sql):
            if sql.startswith('INSERT OR IGNORE INTO original_object'):
                events.append('sql-registration')

        with database.writer() as connection, patch.object(original_module, 'fsync_directory', synchronized):
            connection.set_trace_callback(statement)
            try:
                with self.assertRaisesRegex(OSError, 'synthetic directory sync failure'):
                    Originals(database).put(raw)
            finally:
                connection.set_trace_callback(None)
        self.assertNotIn('sql-registration', events)
        self.assert_unregistered(hashlib.sha256(raw).hexdigest())

    def test_single_link_retry_syncs_directories_before_registration(self):
        for first_failure in ('objects', 'incoming'):
            with self.subTest(first_failure=first_failure):
                raw = ('synthetic original sync retry ' + first_failure).encode()
                identity = hashlib.sha256(raw).hexdigest()
                target = self.root / 'objects' / identity
                self.fail_directory(self.database, raw, first_failure)
                # 也覆盖双链接恢复过程中，unlink完成后incoming同步再次失败。
                self.fail_directory(self.database, raw, 'incoming')
                self.assertEqual(target.stat().st_nlink, 1)
                for database in (self.database, Database(self.root)):
                    for directory in ('objects', 'incoming'):
                        self.fail_directory(database, raw, directory)
                        self.assertEqual(target.stat().st_nlink, 1)

                events = []
                actual_sync = original_module.fsync_directory

                def synchronized(path):
                    actual_sync(path)
                    events.append(path.name)

                def statement(sql):
                    if sql.startswith('INSERT OR IGNORE INTO original_object'):
                        events.append('sql-registration')

                database = Database(self.root)
                with database.writer() as connection, patch.object(original_module, 'fsync_directory', synchronized):
                    connection.set_trace_callback(statement)
                    try:
                        self.assertEqual(Originals(database).put(raw), identity)
                    finally:
                        connection.set_trace_callback(None)
                self.assertEqual(events, ['objects', 'incoming', 'sql-registration'])
                self.assertEqual(Originals(Database(self.root)).get(identity), raw)
                self.assertEqual(list((self.root / 'incoming').iterdir()), [])
                # 已登记、单链接的正常复用不需要再次同步目录，也不复制原件。
                before = (target.stat().st_ino, target.stat().st_mtime_ns, target.read_bytes())
                with database.writer(), patch.object(original_module, 'fsync_directory', side_effect=AssertionError('registered reuse must not sync')):
                    self.assertEqual(Originals(database).put(raw), identity)
                self.assertEqual((target.stat().st_ino, target.stat().st_mtime_ns, target.read_bytes()), before)

    def test_unsynced_unlink_crash_model_remains_unpublished_until_retry(self):
        raw = b'synthetic original unlink crash model'
        identity = hashlib.sha256(raw).hexdigest()
        target = self.root / 'objects' / identity
        self.fail_directory(self.database, raw, 'incoming')
        # 明确的崩溃一致性模型：恢复尚未确认持久化删除的自有临时链接。
        pending = self.root / 'incoming' / ('.object-' + identity + '-' + uuid4().hex)
        os.link(target, pending, follow_symlinks=False)
        self.assertEqual(target.stat().st_nlink, 2)
        self.assert_unregistered(identity)
        self.fail_directory(Database(self.root), raw, 'incoming')
        self.fail_directory(Database(self.root), raw, 'incoming')
        database = Database(self.root)
        with database.writer():
            self.assertEqual(Originals(database).put(raw), identity)
        self.assertEqual(target.stat().st_nlink, 1)
        self.assertEqual(list((self.root / 'incoming').iterdir()), [])
        self.assertEqual(Originals(Database(self.root)).get(identity), raw)

    def test_actual_process_exit_before_incoming_sync_and_restart(self):
        raw = b'synthetic original process exit before directory sync'
        identity = hashlib.sha256(raw).hexdigest()
        child = '''
import os
from pathlib import Path
import sys
from pmi.market_data.storage import Database
from pmi.market_data.storage.originals import Originals
import pmi.market_data.storage.originals as module
root = Path(sys.argv[1])
actual = module.fsync_directory
def interrupted(path):
    if sys.argv[2] == 'interrupt' and path == root / 'incoming':
        os._exit(86)
    actual(path)
module.fsync_directory = interrupted
database = Database(root)
with database.writer():
    Originals(database).put(b'synthetic original process exit before directory sync')
'''
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONPYCACHEPREFIX')}
        environment.update(PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'), PYTHONDONTWRITEBYTECODE='1')
        # 两个全新进程都必须走到同步点；第二次不能因目标已单链接而直接成功。
        for _ in range(2):
            completed = subprocess.run([sys.executable, '-B', '-c', child, str(self.root), 'interrupt'],
                                       env=environment, capture_output=True, timeout=15)
            self.assertEqual(completed.returncode, 86, completed.stderr.decode())
            self.assert_unregistered(identity)
            self.assertEqual((self.root / 'objects' / identity).stat().st_nlink, 1)
        completed = subprocess.run([sys.executable, '-B', '-c', child, str(self.root), 'complete'],
                                   env=environment, capture_output=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(Originals(Database(self.root)).get(identity), raw)
        self.assertEqual(list((self.root / 'incoming').iterdir()), [])

    def test_failed_directory_sync_cannot_publish_or_replace_old_version(self):
        from pmi.market_data.index_series_contract import build_manifest
        from pmi.market_data.storage import index_store
        from pmi.market_data.storage.database import digest
        from pmi.market_data.storage.publications import Publications
        from test_index_series_contract import originals, WINDOW
        from test_index_series_runtime import state
        from test_market_activity import INDEX

        with self.database.writer(), self.database.transaction() as connection:
            Publications(connection).domain('price-v2', digest('synthetic-directory-retry'))
        first_items = originals(INDEX, WINDOW)
        with self.database.writer():
            first = index_store.publish(self.root, INDEX, WINDOW, build_manifest(INDEX, WINDOW, first_items),
                                        first_items, state(INDEX))
        before = index_store.read_snapshot(self.root, INDEX)
        changed = originals(INDEX, WINDOW, prices=('101.00', '111.00', '91.00', '106.00'))
        manifest = build_manifest(INDEX, WINDOW, changed)
        actual_sync = original_module.fsync_directory

        def interrupted(path):
            if path == self.root / 'incoming':
                raise OSError('synthetic incoming sync failure')
            actual_sync(path)

        for _ in range(len(changed) + 1):
            database = Database(self.root)
            with database.writer(), patch.object(original_module, 'fsync_directory', interrupted):
                with self.assertRaisesRegex(OSError, 'synthetic incoming sync failure'):
                    index_store.publish(self.root, INDEX, WINDOW, manifest, changed, state(INDEX, 'directory-retry'))
            self.assertEqual(index_store.read_snapshot(self.root, INDEX), before)
            self.assertIsNone(index_store.committed_job_locked(self.root, INDEX, 'directory-retry'))
        database = Database(self.root)
        with database.writer():
            second = index_store.publish(self.root, INDEX, WINDOW, manifest, changed, state(INDEX, 'directory-retry'))
            self.assertEqual(index_store.publish(self.root, INDEX, WINDOW, manifest, changed,
                                                state(INDEX, 'directory-retry')), second)
        self.assertNotEqual(first['snapshot_id'], second['snapshot_id'])
        self.assertEqual(index_store.read_snapshot(self.root, INDEX)['snapshot_id'], second['snapshot_id'])
        self.assertEqual(index_store.read_snapshot(self.root, INDEX, first['snapshot_id']), before)
        for original in (*first_items, *changed):
            self.assertEqual(Originals(Database(self.root)).get(hashlib.sha256(original.content).hexdigest()), original.content)
        with database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM publication').fetchone()[0], 2)
