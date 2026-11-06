"""保留已验收读取安全断言；仅使用本地合成SQLite。"""
import fcntl
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pmi.market_data.read_only import ReadUnavailable, read_scope
from pmi.market_data import MarketData
from http_test_support import disk

class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wolf-read-only-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def seed(self,root):
        with sqlite3.connect(root/'index-v2.sqlite') as conn:
            conn.execute('CREATE TABLE synthetic(value INTEGER)')
            conn.execute('INSERT INTO synthetic VALUES(1)')

    def test_sqlite_transaction_snapshot_and_close(self):
        database = self.root / "index-v2.sqlite"
        with sqlite3.connect(database) as prepare:
            prepare.execute("CREATE TABLE synthetic(value INTEGER)")
            prepare.execute("INSERT INTO synthetic VALUES(1)")
        writer = sqlite3.connect(database, timeout=0, isolation_level=None)
        try:
            with read_scope(self.root, database) as reader:
                self.assertEqual(reader.execute("SELECT value FROM synthetic").fetchone()[0], 1)
                writer.execute("BEGIN IMMEDIATE"); writer.execute("UPDATE synthetic SET value=2")
                self.assertEqual(reader.execute("SELECT value FROM synthetic").fetchone()[0], 1)
                with self.assertRaises(sqlite3.OperationalError): writer.execute("COMMIT")
                writer.execute("ROLLBACK")
            with self.assertRaises(sqlite3.ProgrammingError): reader.execute("SELECT 1")
            writer.execute("UPDATE synthetic SET value=2")
            with read_scope(self.root, database) as reader:
                self.assertEqual(reader.execute("SELECT value FROM synthetic").fetchone()[0], 2)
        finally: writer.close()


    def test_unsafe_storage_is_rejected_without_recovery(self):
        for suffix, content in (("-wal", b""), ("-shm", b""), ("-journal", b"unsafe journal")):
            root = self.root / suffix; root.mkdir(); self.seed(root)
            (root / ("index-v2.sqlite" + suffix)).write_bytes(content)
            before = disk(root)
            with self.assertRaises(ReadUnavailable):
                with read_scope(root,root/"index-v2.sqlite"): pass
            self.assertEqual(before,disk(root))
        root = self.root / "zero"; root.mkdir(); self.seed(root)
        (root / "index-v2.sqlite-journal").write_bytes(b"")
        before = disk(root)
        with read_scope(root,root/"index-v2.sqlite") as conn:
            self.assertEqual(conn.execute("SELECT value FROM synthetic").fetchone()[0],1)
        self.assertEqual(before, disk(root))
        (root / "index-v2.sqlite").write_bytes(b"corrupt")
        before = disk(root)
        with self.assertRaises(ReadUnavailable):
            with read_scope(root,root/"index-v2.sqlite"): pass
        self.assertEqual(before, disk(root))


    def test_transaction_settings_authorizer_lock_and_exception_release(self):
        self.seed(self.root); lock = self.root / ".writer.lock"; lock.write_bytes(b"synthetic existing lock")
        before = disk(self.root); original_connect = sqlite3.connect; settings = []
        class Observed(sqlite3.Connection):
            def execute(self, sql, *args):
                result = super().execute(sql, *args)
                if sql.startswith("PRAGMA ") and "=" not in sql:
                    settings.append((sql, super().execute(sql).fetchone()[0]))
                return result
        def connect(*args, **kwargs): return original_connect(*args, **kwargs, factory=Observed)
        with patch("pmi.market_data.read_only.sqlite3.connect", side_effect=connect):
            with read_scope(self.root, self.root / "index-v2.sqlite") as conn:
                conn.execute("SELECT name FROM sqlite_master").fetchall()
                for sql in ("CREATE TABLE evil(x)", "PRAGMA query_only=OFF", "ATTACH ':memory:' AS evil", "DELETE FROM synthetic"):
                    with self.assertRaises(sqlite3.DatabaseError): conn.execute(sql)
                with lock.open("rb") as writer:
                    with self.assertRaises(BlockingIOError): fcntl.flock(writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(settings, [("PRAGMA query_only", 1), ("PRAGMA temp_store", 2), ("PRAGMA mmap_size", 0), ("PRAGMA trusted_schema", 0)])
        with self.assertRaises(RuntimeError):
            with read_scope(self.root, self.root / "index-v2.sqlite") as conn: raise RuntimeError("controlled failure")
        with lock.open("rb") as writer:
            fcntl.flock(writer.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ReadUnavailable):
                with read_scope(self.root,self.root/"index-v2.sqlite"): pass
        self.assertEqual(before, disk(self.root))

