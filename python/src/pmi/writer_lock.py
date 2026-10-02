"""以数据根文件锁协调 CLI 与服务写入者；崩溃退出自动释放。"""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from pmi.snapshot import SnapshotError


@contextmanager
def writer_lock(root: Path) -> Iterator[None]:
    """非阻塞独占整个采集和发布阶段，防止跨进程观察竞态。

    锁文件不能删除，否则其他进程可锁住另一个 inode。退出仅释放锁。
    """
    if root.is_symlink():
        raise SnapshotError("data root must not be a symbolic link")
    root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(root / ".writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SnapshotError("writer_busy: 此数据根已有写入任务") from error
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
