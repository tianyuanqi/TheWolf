"""显式初始化、纯读连接及跨进程单写者；仅使用Python标准库。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
from typing import Any, Iterator
from uuid import uuid4

APPLICATION_ID = 0x574F4C46
SCHEMA_VERSION = 2
DB_NAME = 'facts.sqlite'
WRITE_CACHE_KIB = 256 * 1024
READ_CACHE_KIB = 16 * 1024
class _ThreadState(threading.local):
    def __init__(self):
        self.leases: dict[str, dict[str, Any]] = {}
        self.reads: dict[str, sqlite3.Connection] = {}


_LOCAL = _ThreadState()
_MUTEXES: dict[str, threading.RLock] = {}
_REGISTRY_LOCK = threading.Lock()


class StorageError(ValueError):
    """稳定错误码，不能将本机路径/SQL参数透传给客户端。"""


class CommitUncertain(StorageError):
    """提交返回失败，不能用随后可读的记录替本次请求证明持久化成功。"""


def _commit(connection: sqlite3.Connection) -> None:
    """唯一事务提交点，便于独立注入提交前后I/O故障。"""
    connection.execute('COMMIT')


def canonical(value: Any) -> bytes:
    """保留字符串精度，拒绝非有限值；调用者不传浮点金融值。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def identifier(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise StorageError('storage_invalid_identifier')
    return value


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def location(path: Path, *, directory: bool = False) -> os.stat_result:
    """规范绝对路径、无链接、当前用户独占写权限；文件不得有硬链接。"""
    if not path.is_absolute() or path.resolve() != path:
        raise StorageError('storage_invalid_location')
    for part in (path, *path.parents):
        if part.is_symlink():
            raise StorageError('storage_invalid_location')
    value = path.stat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(value.st_mode) or value.st_uid != os.getuid()
            or value.st_mode & 0o022 or (not directory and value.st_nlink != 1)):
        raise StorageError('storage_unsafe_location')
    return value


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Database:
    """位置身份在构造时冻结；构造及读取不建库、恢复或创建旁路文件。"""

    def __init__(self, root: Path):
        location(root, directory=True)
        self.root, self.path = root, root / DB_NAME
        self._parents = {p: (p.stat().st_dev, p.stat().st_ino) for p in (root, *root.parents)}
        self._identity: tuple[int, int] | None = None
        if self.path.exists():
            info = location(self.path)
            self._identity = (info.st_dev, info.st_ino)
        with _REGISTRY_LOCK:
            self._mutex = _MUTEXES.setdefault(str(root), threading.RLock())

    def check(self) -> None:
        for path, expected in self._parents.items():
            location(path, directory=True) if path == self.root else None
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or (info.st_dev, info.st_ino) != expected:
                raise StorageError('storage_location_changed')
        if self._identity is not None:
            info = location(self.path)
            if (info.st_dev, info.st_ino) != self._identity:
                raise StorageError('storage_location_changed')
        elif self.path.exists():
            raise StorageError('storage_location_changed')

    @property
    def exists(self) -> bool:
        self.check()
        return self.path.exists()

    def initialize(self) -> None:
        """显式写用例创建空库；旧格式目录拒绝，不在读取中猜测或转换。"""
        from .schema import SCHEMA
        self.check()
        if any(self.root.iterdir()):
            raise StorageError('storage_initialization_requires_empty_root')
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        descriptor = os.open(self.root / '.writer.lock', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        (self.root / 'objects').mkdir(mode=0o700)
        (self.root / 'incoming').mkdir(mode=0o700)
        connection = sqlite3.connect(self.path, isolation_level=None)
        try:
            # DELETE避免只读客户端为WAL隐式创建SHM；完整批次仍单事务提交。
            connection.execute('PRAGMA journal_mode=DELETE')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
            connection.execute('INSERT INTO store_identity VALUES (1,?,?,?)', (uuid4().hex, SCHEMA_VERSION, now()))
            connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
            connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        fsync_directory(self.root)
        info = location(self.path)
        self._identity = (info.st_dev, info.st_ino)

    def _connect(self, write: bool) -> sqlite3.Connection:
        self.check()
        if not self.path.is_file():
            raise StorageError('storage_not_initialized')
        location(self.path)
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = self.path.with_name(self.path.name + suffix)
            if sidecar.exists():
                # DELETE事务的在途journal不是损坏；只读SQLite可读上次提交。
                # 没有活跃写者则拒绝，不能由普通GET触发热journal恢复。
                if suffix != '-journal' or write or not self._writer_active():
                    raise StorageError('storage_recovery_required')
        connection = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'),
                                     uri=True, isolation_level=None, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            # 连接内页缓存有界；单写者256MiB，短只读连接16MiB，不改数据库文件。
            connection.execute(f'PRAGMA cache_size=-{WRITE_CACHE_KIB if write else READ_CACHE_KIB}')
            if not write:
                connection.execute('PRAGMA query_only=ON')
            else:
                connection.execute('PRAGMA synchronous=FULL')
            if (connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                    or connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION
                    or connection.execute('PRAGMA journal_mode').fetchone()[0] != 'delete'):
                raise StorageError('storage_schema_mismatch')
            self.check()
            return connection
        except BaseException:
            connection.close()
            raise

    def _writer_active(self) -> bool:
        path = self.root / '.writer.lock'
        expected = location(path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            actual = os.fstat(descriptor)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise StorageError('storage_location_changed')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            return False
        finally:
            os.close(descriptor)

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """固定一致事务；同线程写用例可检查自己的候选，不向其他读者暴露。"""
        key = str(self.root)
        active = _LOCAL.leases.get(key)
        if active is not None:
            self.check()
            yield active['connection']
            self.check()
            return
        existing = _LOCAL.reads.get(key)
        if existing is not None:
            self.check()
            yield existing
            self.check()
            return
        connection = self._connect(False)
        try:
            connection.execute('BEGIN')
            _LOCAL.reads[key] = connection
            yield connection
            self.check()
        finally:
            _LOCAL.reads.pop(key, None)
            connection.rollback()
            connection.close()

    @contextmanager
    def exclusive_read(self) -> Iterator[sqlite3.Connection]:
        """备份冻结写入但不写源库；锁文件只读打开，归档副本也可恢复。"""
        key = str(self.root)
        if key in _LOCAL.reads or key in _LOCAL.leases:
            raise StorageError('storage_exclusive_read_requires_idle_connection')
        if not self._mutex.acquire(blocking=False):
            raise StorageError('storage_writer_busy')
        descriptor = None
        try:
            self.check()
            path = self.root / '.writer.lock'
            expected = location(path)
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            actual = os.fstat(descriptor)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise StorageError('storage_location_changed')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise StorageError('storage_writer_busy') from error
            with self.read() as connection:
                yield connection
            current = location(path)
            if (current.st_dev, current.st_ino) != (actual.st_dev, actual.st_ino):
                raise StorageError('storage_location_changed')
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self._mutex.release()

    @contextmanager
    def writer(self) -> Iterator[sqlite3.Connection]:
        """后端整项任务租约；跨线程/进程排他，调用者另用transaction定义提交边界。"""
        self.check()
        leases = _LOCAL.leases
        key = str(self.root)
        if key in _LOCAL.reads:
            raise StorageError('storage_read_transaction_cannot_write')
        if key in leases:
            yield leases[key]['connection']
            return
        if not self._mutex.acquire(blocking=False):
            raise StorageError('storage_writer_busy')
        descriptor = None
        connection = None
        try:
            from .tasks import Task
            task = Task.current(self.root)
            lock_path = self.root / '.writer.lock'
            expected = location(lock_path)
            if task is not None:
                task.check()
                lease_descriptor = task.descriptor
            else:
                descriptor = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
                lease_descriptor = descriptor
            actual = os.fstat(lease_descriptor)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise StorageError('storage_location_changed')
            if task is None:
                try:
                    fcntl.flock(lease_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise StorageError('storage_writer_busy') from error
            connection = self._connect(True)
            leases[key] = {'connection': connection, 'descriptor': lease_descriptor}
            yield connection
            self.check()
            if (lock_path.stat().st_dev, lock_path.stat().st_ino) != (actual.st_dev, actual.st_ino):
                raise StorageError('storage_location_changed')
        finally:
            leases.pop(key, None)
            if connection is not None:
                connection.rollback()
                connection.close()
            if descriptor is not None:
                os.close(descriptor)
            self._mutex.release()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """租约内原子变更；嵌套使用保存点，异常不提交半成品。"""
        active = _LOCAL.leases.get(str(self.root))
        if active is None:
            from .tasks import Task
            if Task.current(self.root) is not None:
                with self.writer(), self.transaction() as connection:
                    yield connection
                return
            raise StorageError('storage_writer_required')
        connection = active['connection']
        nested = connection.in_transaction
        name = 's_' + uuid4().hex
        connection.execute('SAVEPOINT ' + name if nested else 'BEGIN IMMEDIATE')
        try:
            yield connection
            self.check()
            if nested:
                connection.execute('RELEASE ' + name)
            else:
                try:
                    _commit(connection)
                except (sqlite3.Error, OSError) as error:
                    raise CommitUncertain('storage_commit_uncertain') from error
        except BaseException:
            if nested:
                connection.execute('ROLLBACK TO ' + name)
                connection.execute('RELEASE ' + name)
            else:
                connection.rollback()
            raise

    @property
    def is_writer(self) -> bool:
        from .tasks import Task
        return str(self.root) in _LOCAL.leases or Task.current(self.root) is not None

    def inherited_lock(self) -> int:
        active = _LOCAL.leases.get(str(self.root))
        if active is None:
            from .tasks import Task
            task = Task.current(self.root)
            if task is not None:
                task.check()
                return task.descriptor
            raise StorageError('storage_writer_required')
        return active['descriptor']
