"""RB-RO-1：正常回滚日志库的只读事务与完整读取用例锁。

仅支持项目生产者的正常旧库；WAL和非空journal明确拒绝。此边界不恢复、
创建或迁移任何文件，不承诺防御能够任意替换本机文件的恶意程序。
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
from typing import Iterator


class ReadUnavailable(ValueError):
    """本地状态不能在已批准的只读模式下安全读取。"""


def checked_path(path: Path) -> Path:
    """拒绝路径各层的符号链接；只查询元数据，不创建缺失目录。"""
    if not path.is_absolute() or ".." in path.parts:
        raise ReadUnavailable("读取需要明确的绝对路径")
    for part in (*reversed(path.parents), path):
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ReadUnavailable("数据路径不能包含符号链接")
    return path


def _identity(path: Path) -> tuple[int, int] | None:
    checked_path(path)
    try:
        value = path.stat()
    except FileNotFoundError:
        return None
    return value.st_dev, value.st_ino


def read_bytes(path: Path, limit: int = -1) -> bytes:
    """读取已有普通文件并核对定位；对象内容身份由调用方继续校验。"""
    expected = _identity(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or expected != (before.st_dev, before.st_ino):
            raise ReadUnavailable("读取对象不是稳定的普通文件")
        content = stream.read(limit)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ReadUnavailable("读取期间对象发生变化")
    if _identity(path) != expected:
        raise ReadUnavailable("读取期间对象定位发生变化")
    return content


def _check_database(path: Path) -> bool:
    for suffix in ("-wal", "-shm", "-journal"):
        auxiliary = path.with_name(path.name + suffix)
        if _identity(auxiliary) is not None:
            value = auxiliary.stat()
            if not stat.S_ISREG(value.st_mode) or suffix != "-journal" or value.st_size != 0:
                raise ReadUnavailable("数据库需要另行处理辅助文件；只读服务不会恢复")
    if _identity(path) is None:
        return False
    header = read_bytes(path, 100)
    if len(header) != 100 or header[:16] != b"SQLite format 3\0" or header[18:20] != b"\x01\x01":
        raise ReadUnavailable("数据库不是受支持的正常回滚日志格式")
    return True


def _authorize(action: int, first: str | None, second: str | None,
               database: str | None, trigger: str | None) -> int:
    # 读路径只需这些纯SQL操作；不允许后续PRAGMA、扩展、ATTACH或事务写入。
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ}
    if action in allowed:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in {"count", "min", "max", "coalesce"}:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_TRANSACTION and first == "ROLLBACK":
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


@contextmanager
def read_scope(parent: Path, database: Path) -> Iterator[sqlite3.Connection | None]:
    """持已有父锁和SQLite读事务至用例完成，异常也释放，不创建缺库。

    Args:
        parent: 冻结的父数据根；股票与指数共享该父锁。
        database: 父根内的固定数据库位置，不接受HTTP任意路径。
    Yields:
        已限制的连接；正常缺库为None，由调用方表达无资料。
    Raises:
        ReadUnavailable: 锁忙、辅助文件不安全或定位变化，不能返回混合结果。
    """
    checked_path(parent)
    checked_path(database)
    if not database.is_relative_to(parent):
        raise ReadUnavailable("数据库越出配置根")
    tracked = {p: _identity(p) for p in (*database.parents, database)}
    lock_path = parent / ".writer.lock"
    lock_identity = _identity(lock_path)
    lock_fd: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        if lock_identity is not None:
            lock_fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            value = os.fstat(lock_fd)
            if not stat.S_ISREG(value.st_mode) or (value.st_dev, value.st_ino) != lock_identity:
                raise ReadUnavailable("父锁定位发生变化")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ReadUnavailable("数据正在写入，请稍后重读") from error
        if _check_database(database):
            connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True,
                                         timeout=0, isolation_level=None)
            connection.row_factory = sqlite3.Row
            for setting, expected in (("query_only", 1), ("temp_store", 2),
                                      ("mmap_size", 0), ("trusted_schema", 0)):
                connection.execute(f"PRAGMA {setting}={expected}")
                row = connection.execute(f"PRAGMA {setting}").fetchone()
                if row is None or row[0] != expected:
                    raise ReadUnavailable("SQLite只读设置未生效")
            connection.execute("BEGIN")
            connection.set_authorizer(_authorize)
        yield connection
        _check_database(database)
        if _identity(lock_path) != lock_identity or any(_identity(p) != value for p, value in tracked.items()):
            raise ReadUnavailable("读取期间数据或父锁定位变化，请重新读取")
    finally:
        if connection is not None:
            connection.close()
        if lock_fd is not None:
            os.close(lock_fd)
