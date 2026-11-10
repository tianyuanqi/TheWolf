"""读取优化的定位与内容反例；仅使用自有临时文件，不伪造有效来源。"""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmi.market_data.storage import StorageError
from pmi.market_data.storage.originals import Originals
from sqlite_fixture import initialize
from pmi.market_data.storage.activity_store import Store


class ActivityReadIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wolf-activity-integrity-", dir="/private/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "nested" / "activity"
        self.root.mkdir(parents=True)
        initialize(self.root)
        self.store = Store(self.root)

    def test_root_and_ancestor_replacements_are_rejected(self):
        self.root.rename(self.root.with_name("old"))
        self.root.mkdir()
        with self.assertRaisesRegex(StorageError, "storage_location_changed"):
            self.store.check()
        current = Store(self.root)
        parent = self.root.parent
        parent.rename(parent.with_name("old-parent"))
        self.root.mkdir(parents=True)
        with self.assertRaisesRegex(StorageError, "storage_location_changed"):
            current.check()

    def test_symlink_to_same_original_root_does_not_reuse_identity(self):
        moved = self.root.with_name("moved")
        self.root.rename(moved)
        self.root.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(StorageError):
            self.store.check()

    def test_original_change_with_preserved_size_and_mtime_is_rejected(self):
        raw = b"synthetic original"
        key = hashlib.sha256(raw).hexdigest()
        objects = self.root / "objects"
        objects.mkdir(exist_ok=True)
        source = objects / key
        with self.store.database.writer(), self.store.database.transaction():
            Originals(self.store.database).put(raw)
        before = source.stat()
        self.assertEqual(self.store.original(key), raw)
        source.write_bytes(b"X" + raw[1:])
        os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(StorageError, "storage_original_(corrupt|missing|not_found)"):
            self.store.original(key)

    def test_hardlink_and_nested_symlink_are_rejected(self):
        raw = b"synthetic original"
        key = hashlib.sha256(raw).hexdigest()
        target = self.parent / "target"
        target.write_bytes(raw)
        with self.store.database.writer(), self.store.database.transaction() as connection:
            connection.execute("INSERT INTO original_object VALUES(?,?,?)", (key,len(raw),"test"))
        objects = self.root / "objects"
        objects.mkdir(exist_ok=True)
        os.link(target, objects / key)
        with self.assertRaisesRegex(StorageError, "storage_(unsafe|invalid)_location"):
            self.store.original(key)
        (objects / key).unlink()
        objects.rmdir()
        objects.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(StorageError):
            self.store.original(key)

    def originals(self):
        objects = self.root / 'objects'
        objects.mkdir(exist_ok=True)
        expected = {}
        for content in (b'synthetic first', b'synthetic second'):
            key = hashlib.sha256(content).hexdigest()
            with self.store.database.writer(), self.store.database.transaction():
                Originals(self.store.database).put(content)
            expected[key] = content
        return objects, expected

    def test_batch_preserves_bytes_and_rejects_missing_or_corrupt(self):
        objects, expected = self.originals()
        self.assertEqual(self.store.originals(list(expected)), expected)
        self.assertEqual(self.store.originals([*expected, next(iter(expected))]), expected)
        self.assertEqual({key: self.store.original(key) for key in expected}, expected)
        with self.assertRaisesRegex(StorageError, 'storage_original_(corrupt|missing|not_found)'):
            self.store.originals([*expected, '0'*64])
        key = next(iter(expected));path = objects / key;before = path.stat()
        path.write_bytes(b'X' + expected[key][1:]);os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(StorageError, 'storage_original_(corrupt|missing|not_found)'):
            self.store.originals(list(expected))

    def test_batch_rejects_file_symlink_hardlink_and_directory_symlink(self):
        objects, expected = self.originals();key = next(iter(expected));path = objects / key
        external = self.parent / 'original';external.write_bytes(expected[key]);path.unlink()
        path.symlink_to(external)
        with self.assertRaisesRegex(StorageError, 'storage_(unsafe|invalid)_location'):
            self.store.originals(list(expected))
        path.unlink();os.link(external, path)
        with self.assertRaisesRegex(StorageError, 'storage_(unsafe|invalid)_location'):
            self.store.originals(list(expected))
        moved = objects.with_name('old-objects');objects.rename(moved);objects.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(StorageError):
            self.store.originals(list(expected))

    def test_batch_rejects_directory_or_root_replacement_during_read(self):
        objects, expected = self.originals();actual = hashlib.sha256
        for target in (objects, self.root):
            changed = False;moved = target.with_name(target.name + '-saved')
            def digest(raw):
                nonlocal changed
                if not changed:
                    changed = True;target.rename(moved);target.mkdir()
                return actual(raw)
            try:
                with patch('pmi.market_data.storage.originals.hashlib.sha256', side_effect=digest):
                    with self.assertRaisesRegex(StorageError, 'storage_location_changed'):
                        self.store.originals(list(expected))
            finally:
                if changed:
                    target.rmdir();moved.rename(target)
            self.assertEqual(self.store.originals(list(expected)), expected)

    def test_batch_rejects_oversize_original_and_missing_directory(self):
        with self.assertRaisesRegex(StorageError, 'storage_original_(corrupt|missing|not_found)'):
            self.store.originals(['0'*64])
        objects, expected = self.originals();raw = b'x' * (4 * 1048576 + 1);key = hashlib.sha256(raw).hexdigest()
        with self.store.database.writer(), self.store.database.transaction():
            Originals(self.store.database).put(raw)
        with self.assertRaisesRegex(StorageError, 'storage_original_too_large'):
            self.store.originals([key])
        self.assertEqual(self.store.originals(list(expected)), expected)
