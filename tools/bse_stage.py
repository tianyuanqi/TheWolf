"""BSE离线操作暂存：仅保存原件与任务回执，不包含行情发布或页面读取。"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import tempfile
import time
from threading import Event
from typing import Iterator

from pmi.market_data.read_only import ReadUnavailable, checked_path, read_bytes
from pmi.market_data.activity.model import ActivityError, load


class Stage:
    """构造只冻结已有根，读取绝不建目录、锁或恢复。"""
    def __init__(self, root: Path):
        checked_path(root)
        if not root.is_dir() or root.resolve() != root:
            raise ValueError('量额根必须已存在且无链接')
        self.root = root
        self.identities = {p: (p.stat().st_dev, p.stat().st_ino) for p in (root, *root.parents)}

    def check(self) -> None:
        """每层核对冻结身份与链接；一次遍历覆盖祖先，不反复从根扫描。"""
        for path, identity in self.identities.items():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ReadUnavailable('数据路径不能包含符号链接')
            if (info.st_dev, info.st_ino) != identity:
                raise ActivityError('activity_location_changed')

    def path(self, *parts: str) -> Path:
        allowed = {'plan.json', 'receipts.json', 'attempts.json', 'pacing.json', 'published.json', '.activity.lock'}
        if not (len(parts) == 1 and parts[0] in allowed or len(parts) == 2 and parts[0] == 'raw'
                and len(parts[1]) == 64 and all(character in '0123456789abcdef' for character in parts[1])):
            raise ActivityError('history_stage_key_invalid')
        self.check()
        path = checked_path(self.root.joinpath(*parts))
        if not path.is_relative_to(self.root):
            raise ActivityError('activity_path_invalid')
        if path.exists():
            current = path.stat()
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                raise ActivityError('activity_file_invalid')
        return path

    def read(self, *parts: str, limit: int = 4 * 1048576) -> bytes | None:
        path = self.path(*parts)
        if not path.exists():
            return None
        result = read_bytes(path, limit + 1)
        if len(result) > limit:
            raise ActivityError('activity_size_exceeded')
        self.check()
        return result

    def json(self, *parts: str) -> dict | None:
        content = self.read(*parts)
        return load(content) if content is not None else None

    @contextmanager
    def lock(self, *, write: bool, cancel: Event | None = None) -> Iterator[None]:
        """读入口立即返回竞争；周期写入口可取消地等待读锁，最多30秒，不重试出站。"""
        path = self.path('.activity.lock')
        if not write and not path.exists():
            yield
            return
        fd = os.open(path, (os.O_RDWR | os.O_CREAT if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ActivityError('activity_file_invalid')
            deadline = time.monotonic() + 30
            while True:
                try:
                    fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError as error:
                    if not write or cancel is None or time.monotonic() >= deadline:
                        raise ActivityError('activity_busy') from error
                    if cancel.wait(.05):
                        raise ActivityError('activity_cancelled') from error
            self.check()
            yield
            self.check()
        finally:
            os.close(fd)

    def write(self, parts: tuple[str, ...], content: bytes, *, immutable: bool = False) -> None:
        """持写锁后原子写和fsync，immutable对象冲突拒绝；只清本次暂存。"""
        path = self.path(*parts)
        for parent in reversed(path.parent.relative_to(self.root).parents):
            directory = checked_path(self.root / parent)
            created = not directory.exists()
            directory.mkdir(exist_ok=True)
            if created:
                descriptor = os.open(directory.parent, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        created = not path.parent.exists()
        path.parent.mkdir(exist_ok=True)
        if created:
            descriptor = os.open(path.parent.parent, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        checked_path(path.parent)
        if immutable and path.exists():
            if self.read(*parts) != content:
                raise ActivityError('immutable_conflict')
            return
        fd, temporary = tempfile.mkstemp(prefix='.activity-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.path(*parts)
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
