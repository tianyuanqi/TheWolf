"""完整性检查的期限、损坏隔离、显式解封与中断记录，均使用假数据。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.integrity import Integrity
from pmi.market_data.storage.originals import Originals


class Interrupted(BaseException):
    pass


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='wolf-integrity-', dir='/private/tmp')
        self.root = Path(self.temp.name)
        self.db = Database(self.root)
        self.db.initialize()
        self.point = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.check = Integrity(self.db, lambda: self.point)
        self.raw = b'synthetic integrity evidence'
        with self.db.writer():
            self.source = Originals(self.db).put(self.raw)

    def tearDown(self):
        self.temp.cleanup()
        self.assertFalse(self.root.exists())

    @staticmethod
    def synthetic_semantics(connection):
        # 仅本测试的空发布集合，无来源事实可重放；正式检查不能使用此函数。
        if connection.execute('SELECT count(*) FROM publication').fetchone()[0]:
            raise AssertionError('unexpected non-synthetic publication')

    def test_due_windows_and_full_checker_is_required(self):
        with self.assertRaisesRegex(StorageError, 'check_due'):
            self.check.require_available()
        with self.assertRaisesRegex(StorageError, 'request_invalid'):
            self.check.run('full')
        self.check.run('full', semantic_check=self.synthetic_semantics)
        self.check.require_available()
        self.point += timedelta(hours=24)
        self.assertTrue(self.check.status()['structure_due'])
        self.assertFalse(self.check.status()['full_due'])
        self.check.run('structure')
        self.check.require_available()
        self.point += timedelta(days=6)
        self.assertTrue(self.check.status()['full_due'])

    def test_bad_original_quarantines_across_restart_and_only_explicit_full_releases(self):
        self.check.run('full', semantic_check=self.synthetic_semantics)
        (self.root / 'objects' / self.source).write_bytes(b'tampered synthetic bytes')
        with self.assertRaisesRegex(StorageError, 'original_corrupt'):
            self.check.run('full', semantic_check=self.synthetic_semantics)
        restarted = Integrity(Database(self.root), lambda: self.point)
        with self.assertRaisesRegex(StorageError, 'quarantined'):
            restarted.require_available()
        (self.root / 'objects' / self.source).write_bytes(self.raw)
        restarted.run('full', semantic_check=self.synthetic_semantics)
        self.assertTrue(restarted.status()['quarantined'])
        restarted.run('full', semantic_check=self.synthetic_semantics, release_quarantine=True)
        restarted.require_available()
        with self.db.read() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM integrity_check WHERE state='failed'").fetchone()[0], 1)

    def test_interruption_does_not_extend_expired_success(self):
        self.check.run('full', semantic_check=self.synthetic_semantics)
        old = self.check.status()['last_full']
        self.point += timedelta(days=8)

        def stop(_):
            raise Interrupted()

        with self.assertRaises(Interrupted):
            self.check.run('full', semantic_check=stop)
        self.assertEqual(self.check.status()['last_full'], old)
        self.assertFalse(self.check.status()['quarantined'])
        with self.assertRaisesRegex(StorageError, 'check_due'):
            self.check.require_available()
        with self.db.read() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM integrity_check WHERE state='interrupted'").fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
