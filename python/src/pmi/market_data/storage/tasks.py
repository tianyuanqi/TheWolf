"""跨线程任务持有统一文件锁；SQLite连接只在所属线程的短事务中使用。"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import threading
from typing import Iterator

from .database import Database, StorageError, location


class _Context(threading.local):
    def __init__(self):
        self.tasks: dict[str, tuple[Task, int]] = {}


_CONTEXT = _Context()


class Task:
    """一个逻辑批次一把锁；显式retain/use允许其worker复用，不传SQLite连接。"""

    def __init__(self, database: Database, descriptor: int, identity: tuple[int, int]):
        self.database, self.descriptor, self.identity = database, descriptor, identity
        self._mutex = threading.Lock()
        self._owners, self._users = 1, 0
        self._closed = False

    @classmethod
    def current(cls, root: Path) -> Task | None:
        current = _CONTEXT.tasks.get(str(root))
        return current[0] if current else None

    @classmethod
    def acquire(cls, root: Path, parent: Task | None = None) -> Task:
        """只复用明确传入或当前线程已获准的批次；无授权者不能借全局对象入写。"""
        current = parent or cls.current(root)
        if current is not None:
            if current.database.root != root:
                raise StorageError('storage_task_scope_mismatch')
            return current.retain()
        database = Database(root)
        database.check()
        path = root / '.writer.lock'
        expected = location(path)
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            actual = os.fstat(descriptor)
            if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                raise StorageError('storage_location_changed')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise StorageError('storage_writer_busy') from error
            return cls(database, descriptor, (actual.st_dev, actual.st_ino))
        except BaseException:
            os.close(descriptor)
            raise

    def retain(self) -> Task:
        with self._mutex:
            if self._closed or self._owners == 0:
                raise StorageError('storage_task_closed')
            self._owners += 1
        return self

    def check(self) -> None:
        self.database.check()
        with self._mutex:
            if self._closed:
                raise StorageError('storage_task_closed')
            actual = os.fstat(self.descriptor)
        path = location(self.database.root / '.writer.lock')
        if (actual.st_dev, actual.st_ino) != self.identity or (path.st_dev, path.st_ino) != self.identity:
            raise StorageError('storage_location_changed')

    @contextmanager
    def use(self) -> Iterator[Task]:
        """本线程仅在明确作用域内获得写权限；退出不污染后续HTTP请求。"""
        self.check()
        key = str(self.database.root)
        current = _CONTEXT.tasks.get(key)
        if current is not None and current[0] is not self:
            raise StorageError('storage_task_conflict')
        with self._mutex:
            if self._closed or self._owners == 0:
                raise StorageError('storage_task_closed')
            self._users += 1
        _CONTEXT.tasks[key] = (self, current[1] + 1 if current else 1)
        try:
            yield self
            self.check()
        finally:
            if current:
                _CONTEXT.tasks[key] = current
            else:
                _CONTEXT.tasks.pop(key, None)
            with self._mutex:
                self._users -= 1
                self._release_if_unused()

    def _release_if_unused(self) -> None:
        if self._owners == 0 and self._users == 0 and not self._closed:
            os.close(self.descriptor)
            self._closed = True

    def close(self) -> None:
        """每个acquire/retain对应一次close；最后使用者退出才释放锁。"""
        with self._mutex:
            if self._owners <= 0:
                raise StorageError('storage_task_already_released')
            self._owners -= 1
            self._release_if_unused()


@contextmanager
def task_writer(root: Path) -> Iterator[Task]:
    task = Task.acquire(root)
    try:
        with task.use():
            yield task
    finally:
        task.close()
