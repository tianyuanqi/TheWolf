"""真实后台线程、统一额度租约和只读备份的隔离检查。"""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import threading
import unittest

from pmi.market_data import SnapshotError
from pmi.market_data.index_series_update import Runtime, start_update
from pmi.market_data.index_series_fetch import NetworkBudget
from pmi.market_data.periodic_budget import Budget, PeriodicOptions, initialize, BudgetError
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.database import digest
from pmi.market_data.storage.documents import Documents
from pmi.market_data.storage.publications import Publications
from pmi.market_data.storage.index_store import read_status
from test_index_series_contract import WINDOW, originals
from test_market_activity import INDEX
from test_periodic_budget import Clock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/migrations'))
from backup_sqlite import backup


class WriterRuntimeTests(unittest.TestCase):
    def test_background_handoff_reuses_quota_task_and_rejects_unrelated_writer(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-handoff-', dir='/private/tmp') as directory:
            root = Path(directory)
            database = Database(root)
            database.initialize()
            with database.writer(), database.transaction() as connection:
                Publications(connection).domain('price-v2', digest('synthetic-price'))
            initialize(root, root)
            budget = Budget(root, root, PeriodicOptions(), Clock())
            lease = budget.begin([], target='synthetic', automatic=False)
            runtime, entered, resume = Runtime(), threading.Event(), threading.Event()
            samples = {row.source: row for row in originals(INDEX, WINDOW)}
            def fetch(parent, index, source, window, job, **kwargs):
                entered.set()
                if not resume.wait(5):
                    raise AssertionError('worker did not resume')
                return samples[source]
            try:
                result = start_update(root, INDEX, WINDOW, budget=NetworkBudget(lease=lease), runtime=runtime, fetch=fetch)
                self.assertTrue(entered.wait(5))
                self.assertEqual(read_status(root, INDEX)['job_id'], result['job_id'])
                self.assertIn(read_status(root, INDEX)['stage'], ('fetching_csindex', 'fetching_cnindex'))
                with self.assertRaisesRegex(StorageError, 'writer_busy'):
                    with database.writer():
                        self.fail('unrelated request received permission')
                resume.set()
                self.assertTrue(runtime.wait(10))
                self.assertEqual(read_status(root, INDEX)['stage'], 'completed')
                lease.finish()
                self.assertEqual(budget.read()['attempts'], [])
                with database.writer():
                    pass
            finally:
                resume.set()
                runtime.close(10)
                if not lease.closed:
                    lease.finish('test_cleanup')
        self.assertFalse(root.exists())

    def test_readonly_backup_preserves_source_bytes_and_independent_objects(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-backup-', dir='/private/tmp') as directory:
            root = Path(directory) / 'source'
            root.mkdir(mode=0o700)
            database = Database(root)
            database.initialize()
            with database.writer(), database.transaction() as connection:
                reference = Documents(connection).put({'a': [], 'b': [], 'c': {}, 'd': {}})
            def manifest():
                return {str(path.relative_to(root)): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns, path.stat().st_ino)
                        for path in root.rglob('*') if path.is_file()}
            before = manifest()
            report = backup(root, Path(directory) / 'restored')
            self.assertTrue(report['passed'])
            self.assertEqual(manifest(), before)
            with database.read() as connection:
                result = Documents(connection).get(reference)
            result['a'].append(1); result['c']['test'] = 2
            self.assertEqual(result['b'], [])
            self.assertEqual(result['d'], {})
        self.assertFalse(root.exists())
