"""一次性旧格式验证的只读边界；产品服务不得导入。"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
from typing import Any, Iterator
from urllib.parse import unquote, urlsplit


class BoundaryError(RuntimeError):
    pass


def contained(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def fingerprint(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify_copies(manifest: dict[str, Any], roots: dict[str, str]) -> dict[str, Any]:
    """只核对已复制输入，不通过清单中的原根路径读取来源。"""
    result = {}
    if set(roots) != set(manifest['roots']):
        raise BoundaryError('copy_root_set_mismatch')
    for key, expected in manifest['roots'].items():
        root = Path(roots[key])
        if not root.is_absolute() or root.resolve() != root or not root.is_dir():
            raise BoundaryError('unsafe_copy_root')
        if any(contained(str(root), item['original_root']) or contained(item['original_root'], str(root))
               for item in manifest['roots'].values()):
            raise BoundaryError('copy_overlaps_original')
        files, links = set(), {}
        for parent, directories, names in os.walk(root, followlinks=False):
            for name in directories + names:
                path = Path(parent) / name
                if path.is_symlink():
                    links[str(path.relative_to(root))] = os.readlink(path)
            directories[:] = [name for name in directories if not (Path(parent) / name).is_symlink()]
            for name in names:
                path = Path(parent) / name
                if path.is_symlink():
                    continue
                relative = str(path.relative_to(root))
                files.add(relative)
                item = expected['files'].get(relative)
                if item is None or path.stat().st_size != item['size'] or fingerprint(path) != item['sha256']:
                    raise BoundaryError('copy_file_mismatch')
        if files != expected['files'].keys() or links != {v['path']: v['target'] for v in expected['symlinks']}:
            raise BoundaryError('copy_inventory_mismatch')
        result[key] = {'files': len(files), 'bytes': sum(v['size'] for v in expected['files'].values()), 'symlinks': len(links)}
    return result


class ReadBoundary:
    """拒绝真实根、写入和出站；只允许恢复副本、固定代码/依赖及报告输出。"""

    def __init__(self, *, copies: list[Path], originals: list[Path], code: list[Path], output: Path):
        self.copies = [str(path) for path in copies]
        self.originals = [str(path) for path in originals]
        self.read_roots = [*self.copies, *(str(path) for path in code)]
        self.output = str(output)
        self.opened: set[str] = set()
        self.denied: list[dict[str, str]] = []
        self._stat, self._lstat = os.stat, os.lstat
        self._descriptors: dict[int, str] = {}
        self._opening = threading.local()

    def _path(self, value: Any) -> str | None:
        if isinstance(value, int) or value is None:
            return None
        value = os.fsdecode(value)
        if value.startswith('file:'):
            value = unquote(urlsplit(value).path)
        return os.path.abspath(value)

    def _original(self, path: str | None) -> bool:
        return path is not None and any(contained(path, root) for root in self.originals)

    def reject(self, event: str, path: str = '') -> None:
        self.denied.append({'event': event, 'path': path})
        raise BoundaryError('legacy_validation_boundary_denied')

    def audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event == 'open':
            path = getattr(self._opening, 'path', None) or self._path(args[0])
            if path is None:
                return
            mode, flags = args[1], args[2]
            write = (isinstance(mode, str) and any(character in mode for character in 'wax+')) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if self._original(path) or (write and path != self.output):
                self.reject(event, path)
            if not write and path != self.output and not any(contained(path, root) for root in self.read_roots):
                self.reject(event, path)
            self.opened.add(path)
        elif event == 'sqlite3.connect':
            value = os.fsdecode(args[0])
            path = self._path(value)
            if (self._original(path) or not any(contained(path, root) for root in self.copies)
                    or not value.startswith('file:') or 'mode=ro' not in urlsplit(value).query.split('&')):
                self.reject(event, path or '')
            self.opened.add(path)
        elif event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.posix_spawn'):
            self.reject(event)
        elif event in ('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.symlink', 'os.link', 'os.chmod', 'os.chown', 'os.utime', 'os.truncate'):
            self.reject(event, self._path(args[0]) or '')
        elif event in ('os.listdir', 'os.scandir'):
            path = self._path(args[0])
            if self._original(path):
                self.reject(event, path or '')

    def authorize(self, action: int, one: str | None, two: str | None, database: str | None, trigger: str | None) -> int:
        allowed = {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION,
                   sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT, sqlite3.SQLITE_RECURSIVE}
        if action in allowed:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and (two is None or (one == 'query_only' and two in ('ON', '1'))):
            return sqlite3.SQLITE_OK
        self.denied.append({'event': 'sqlite_authorizer', 'path': str(action)})
        return sqlite3.SQLITE_DENY

    def install(self) -> None:
        """在独立验证进程安装，不在当前服务进程解除或改变全局文件定位。"""
        def relative_path(path, directory):
            if directory is not None and not os.path.isabs(os.fsdecode(path)):
                if directory not in self._descriptors:
                    self.reject('unknown_directory_descriptor')
                return self._path(os.path.join(self._descriptors[directory], os.fsdecode(path)))
            return self._path(path)

        def checked_stat(path, *args, **kwargs):
            normalized = relative_path(path, kwargs.get('dir_fd'))
            if self._original(normalized):
                self.reject('os.stat', normalized or '')
            return self._stat(path, *args, **kwargs)

        def checked_lstat(path, *args, **kwargs):
            normalized = relative_path(path, kwargs.get('dir_fd'))
            if self._original(normalized):
                self.reject('os.lstat', normalized or '')
            return self._lstat(path, *args, **kwargs)

        original_connect = sqlite3.connect
        original_open, original_close = os.open, os.close

        def checked_open(path, flags, mode=0o777, *, dir_fd=None):
            resolved = relative_path(path, dir_fd)
            self._opening.path = resolved
            try:
                # 文件定位仍使用原dir_fd；摘要映射和审计均不更改读取路径。
                descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
                self._descriptors[descriptor] = resolved
                return descriptor
            finally:
                self._opening.path = None

        def checked_close(descriptor):
            try:
                return original_close(descriptor)
            finally:
                self._descriptors.pop(descriptor, None)

        def readonly_connect(*args, **kwargs):
            # connect/handle 审计事件发生时Python连接尚未初始化，必须返回后设置。
            connection = original_connect(*args, **kwargs)
            connection.set_authorizer(self.authorize)
            connection.execute('PRAGMA query_only=ON')
            return connection

        os.stat, os.lstat = checked_stat, checked_lstat
        os.open, os.close = checked_open, checked_close
        sqlite3.connect = readonly_connect
        sys.addaudithook(self.audit)


@contextmanager
def readonly_database(path: Path) -> Iterator[sqlite3.Connection]:
    """仅静态恢复副本，绝不触发恢复或创建数据库；调用后关闭连接。"""
    for suffix in ('-wal', '-shm', '-journal'):
        if path.with_name(path.name + suffix).exists():
            raise BoundaryError('legacy_sidecar_present')
    connection = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        yield connection
    finally:
        connection.close()
