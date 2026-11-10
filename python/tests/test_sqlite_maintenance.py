"""本地维护的逾期门禁、失败持久性及与发布共用锁；只有合成空库/原件。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import sys
from unittest.mock import patch

from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.maintenance import Maintenance
from pmi.market_data.storage.originals import Originals
from pmi.market_data.storage.tasks import Task

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wolf-sql-maintenance-', dir='/private/tmp')
        self.root = Path(self.tmp.name)
        self.database = Database(self.root)
        self.database.initialize()
        self.point = datetime(2026, 11, 8, tzinfo=timezone.utc)
        self.cleared = []
        self.maintenance = Maintenance(self.database, lambda: self.cleared.append(True))
        self.maintenance.integrity.clock = lambda: self.point
        self.addCleanup(self.tmp.cleanup)

    def test_due_blocks_reads_local_check_never_networks_or_charges(self):
        with self.assertRaisesRegex(StorageError, 'check_due'):
            self.maintenance.require_available()
        with patch('socket.socket.connect', side_effect=AssertionError('maintenance must be local')):
            self.maintenance.check_once()
        self.maintenance.require_available()
        self.point += timedelta(hours=24)
        with self.assertRaisesRegex(StorageError, 'check_due'):
            self.maintenance.require_available()
        with patch('socket.socket.connect', side_effect=AssertionError('maintenance must be local')):
            self.maintenance.check_once()
        self.maintenance.require_available()
        with self.database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM attempt').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM publication').fetchone()[0], 0)
            self.assertEqual([row[0] for row in connection.execute('SELECT kind FROM integrity_check ORDER BY started_at')], ['full','structure'])
        self.assertGreaterEqual(len(self.cleared), 4)

    def test_bad_original_quarantine_and_shared_writer_snapshot(self):
        with self.database.writer():
            identity = Originals(self.database).put(b'synthetic only')
        task = Task.acquire(self.root)
        try:
            with self.assertRaisesRegex(StorageError, 'writer_busy'):
                self.maintenance.check_once()
            with self.database.read() as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM integrity_check').fetchone()[0], 0)
        finally:
            task.close()
        self.maintenance.check_once()
        (self.root/'objects'/identity).write_bytes(b'corrupt')
        self.point += timedelta(days=8)
        with self.assertRaisesRegex(StorageError, 'original_corrupt'):
            self.maintenance.check_once()
        restarted = Maintenance(Database(self.root), lambda: self.cleared.append(True))
        restarted.integrity.clock = lambda: self.point
        restarted.check_once()
        with self.assertRaisesRegex(StorageError, 'quarantined'):
            restarted.require_available()
        self.assertTrue(restarted.close())

    def test_explicit_cli_full_release_and_report_path_boundary(self):
        from pmi.market_data.storage.integrity import Integrity
        tool = Path(__file__).resolve().parents[2] / 'tools/migrations/check_sqlite.py'
        def run(output, *extra):
            return subprocess.run([sys.executable, '-B', str(tool), '--root', str(self.root), '--output', str(output), *extra],
                                  capture_output=True, text=True, timeout=30)
        with tempfile.TemporaryDirectory(prefix='wolf-sql-check-reports-', dir='/private/tmp') as directory:
            report = Path(directory)
            for name in (self.root/'unexpected.json', report/'..'/self.root.name/'unexpected.json'):
                before = self.database.path.read_bytes()
                self.assertNotEqual(run(name).returncode, 0)
                self.assertEqual(self.database.path.read_bytes(), before)
                self.assertFalse((self.root/'unexpected.json').exists())
            self.assertNotEqual(run(report/'invalid.json', '--kind', 'structure', '--release-quarantine').returncode, 0)
            with self.database.writer():
                object_id = Originals(self.database).put(b'original synthetic bytes')
            (self.root/'objects'/object_id).write_bytes(b'corrupted')
            self.assertEqual(run(report/'failure.json').returncode, 1)
            self.assertEqual(json.loads((report/'failure.json').read_text())['state'], 'failed')
            self.assertTrue(Integrity(self.database).status()['quarantined'])
            (self.root/'objects'/object_id).write_bytes(b'original synthetic bytes')
            self.assertEqual(run(report/'pass-still-quarantined.json').returncode, 0)
            self.assertTrue(Integrity(self.database).status()['quarantined'])
            self.assertEqual(run(report/'release.json', '--release-quarantine').returncode, 0)
            Integrity(self.database).require_available()

if __name__ == '__main__':
    unittest.main()
