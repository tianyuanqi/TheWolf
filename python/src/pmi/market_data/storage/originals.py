"""内容寻址原件池；只有证据、发布验证和完整性检查读取原字节。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from uuid import uuid4

from .database import Database, StorageError, fsync_directory, identifier, location

MAX_BYTES = 64 * 1024 * 1024


class Originals:
    """先同步不可变原件，再登记SQL引用；读操作不清理、恢复或创建文件。"""

    def __init__(self, database: Database):
        self.database = database

    def _bytes(self, path: Path, limit: int) -> bytes:
        self.database.check()
        before = location(path)
        if before.st_size > limit:
            raise StorageError('storage_original_too_large')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise StorageError('storage_location_changed')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                raw = stream.read(limit + 1)
            after = os.fstat(descriptor)
            if (after.st_size, after.st_mtime_ns, after.st_ino, after.st_nlink) != (
                    before.st_size, before.st_mtime_ns, before.st_ino, 1):
                raise StorageError('storage_original_changed')
        finally:
            os.close(descriptor)
        final = location(path)
        if (final.st_dev, final.st_ino) != (before.st_dev, before.st_ino) or len(raw) > limit:
            raise StorageError('storage_original_changed')
        self.database.check()
        return raw

    def get(self, object_id: str, *, limit: int = MAX_BYTES) -> bytes:
        """调用者先核对固定版本成员；本层验证登记长度、定位和SHA。"""
        identifier(object_id)
        with self.database.read() as connection:
            row = connection.execute('SELECT byte_length FROM original_object WHERE id=?', (object_id,)).fetchone()
            if row is None:
                raise StorageError('storage_original_not_found')
            if row[0] > limit:
                raise StorageError('storage_original_too_large')
        root = self.database.root / 'objects'
        expected = location(root, directory=True)
        try:
            raw = self._bytes(root / object_id, limit)
        except FileNotFoundError as error:
            raise StorageError('storage_original_missing') from error
        if len(raw) != row[0] or hashlib.sha256(raw).hexdigest() != object_id:
            raise StorageError('storage_original_corrupt')
        try:
            current = location(root, directory=True)
        except FileNotFoundError as error:
            raise StorageError('storage_location_changed') from error
        if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
            raise StorageError('storage_location_changed')
        self.database.check()
        return raw

    def put(self, raw: bytes, media_type: str = 'application/octet-stream') -> str:
        """仅后端写租约内；同字节复用，不覆盖已有原件，失败只遗留未发布材料。"""
        if not self.database.is_writer:
            raise StorageError('storage_writer_required')
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise StorageError('storage_original_too_large')
        object_id = hashlib.sha256(raw).hexdigest()
        root, incoming = self.database.root / 'objects', self.database.root / 'incoming'
        location(root, directory=True)
        location(incoming, directory=True)
        target = root / object_id
        if target.exists():
            self._finish_own_link(object_id)
            if self._bytes(target, MAX_BYTES) != raw:
                raise StorageError('storage_original_corrupt')
        else:
            pending = incoming / ('.object-' + object_id + '-' + uuid4().hex)
            descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                remaining = memoryview(raw)
                while remaining:
                    count = os.write(descriptor, remaining)
                    if count <= 0:
                        raise OSError('short_write')
                    remaining = remaining[count:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if hashlib.sha256(self._bytes(pending, MAX_BYTES)).hexdigest() != object_id:
                raise StorageError('storage_original_corrupt')
            # link为排他建名，不会覆盖意外已有的原件；只删除本次临时硬链接。
            os.link(pending, target, follow_symlinks=False)
            fsync_directory(root)
            pending.unlink()
            fsync_directory(incoming)
        with self.database.transaction() as connection:
            connection.execute('INSERT OR IGNORE INTO original_object VALUES(?,?,?)', (object_id, len(raw), media_type))
            if connection.execute('SELECT byte_length FROM original_object WHERE id=?', (object_id,)).fetchone()[0] != len(raw):
                raise StorageError('storage_original_corrupt')
        return object_id

    def _finish_own_link(self, object_id: str) -> None:
        """只在显式写重试完成未登记原件的目录同步；未知硬链接拒绝。"""
        target = self.database.root / 'objects' / object_id
        info = target.lstat()
        with self.database.read() as connection:
            registered = connection.execute('SELECT 1 FROM original_object WHERE id=?', (object_id,)).fetchone()
        if info.st_nlink == 1:
            if not registered:
                # unlink后incoming同步也可能失败；单链接不能证明目录状态已持久化。
                # 未登记原件的显式重试须补齐两个目录同步，失败时仍不得登记SQL。
                fsync_directory(self.database.root / 'objects')
                fsync_directory(self.database.root / 'incoming')
            return
        if registered or not stat.S_ISREG(info.st_mode) or info.st_nlink != 2:
            raise StorageError('storage_unsafe_location')
        matching = []
        incoming = self.database.root / 'incoming'
        for pending in incoming.glob('.object-' + object_id + '-*'):
            other = pending.lstat()
            if stat.S_ISREG(other.st_mode) and (other.st_dev, other.st_ino) == (info.st_dev, info.st_ino):
                matching.append(pending)
        if len(matching) != 1:
            raise StorageError('storage_unsafe_location')
        # 字节先于链接同步；首次链接后的目录同步可能失败，不能据链接存在假定已持久化。
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_nlink) != (info.st_dev, info.st_ino, 2):
                raise StorageError('storage_original_changed')
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != object_id:
                raise StorageError('storage_original_corrupt')
        finally:
            os.close(descriptor)
        fsync_directory(self.database.root / 'objects')
        matching[0].unlink()
        fsync_directory(incoming)
