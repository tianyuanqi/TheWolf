"""指数任务的精确活动证明；父写锁之外区分指数及job身份。"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Iterator

from pmi.market_data import SnapshotError
from pmi.market_data.read_only import checked_path


def _identity(index_id: str, job_id: str) -> bytes:
    if (not isinstance(index_id, str) or not isinstance(job_id, str)
            or not index_id.isascii() or not job_id.isascii()
            or not 1 <= len(index_id) <= 64 or not 1 <= len(job_id) <= 128):
        raise SnapshotError("指数活动身份无效")
    return json.dumps([index_id, job_id], separators=(",", ":")).encode("ascii")


def _path(root: Path) -> Path:
    return checked_path(root / ".index-v2-activity.lock")


@contextmanager
def activity(root: Path, index_id: str, job_id: str) -> Iterator[None]:
    """在父独占锁内持有精确指数与job凭据，退出先于父锁释放。

    Args:
        root: 已由数据层登记的指数子目录。
        index_id: canonical指数身份，与状态文件共同核验。
        job_id: 本次任务身份，不复用上次残留文本。
    """
    expected = _identity(index_id, job_id)
    path = _path(root)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(descriptor, "r+b", buffering=0) as stream:
        value = os.fstat(stream.fileno())
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise SnapshotError("指数活动文件类型不安全")
        # 先更换身份再持锁，避免新持有者短暂替旧job的残留状态背书。
        stream.write(expected)
        stream.truncate()
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def is_active(root: Path, index_id: str, job_id: str | None) -> bool:
    """只读验证稳定身份、活动锁和inode；残留文件或其他指数的锁无效。"""
    if not job_id:
        return False
    try:
        expected = _identity(index_id, job_id)
        path = _path(root)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb", buffering=0) as stream:
            actual = os.fstat(stream.fileno())
            if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1:
                return False
            first = stream.read(512)
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                stream.seek(0)
                second = stream.read(512)
                after = path.stat(follow_symlinks=False)
                return (first == second == expected and stat.S_ISREG(after.st_mode)
                        and (actual.st_dev, actual.st_ino) == (after.st_dev, after.st_ino))
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                return False
    except (OSError, ValueError):
        return False
