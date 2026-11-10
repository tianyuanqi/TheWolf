"""ETF独立不可变对象与单指针发布；GET不建库、不修复、不删除原件。"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import threading
from typing import Any, Iterator
from uuid import uuid4

from pmi.market_data.read_only import checked_path, read_bytes
from .model import FlowError, canonical, decode, digest, exact, object_id

MAX_OBJECT_BYTES = 64 * 1024 * 1024


def location(path: Path, *, directory: bool = True) -> Path:
    """仅接受现存规范位置；拒绝链接、非普通文件及非独占写权限。"""
    checked_path(path)
    if path.resolve() != path or not (path.is_dir() if directory else path.is_file()):
        raise FlowError("etf_invalid_location", 422)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022 or (not directory and info.st_nlink != 1):
        raise FlowError("etf_unsafe_location", 422)
    return path


def _fsync(directory: Path) -> None:
    """持久化目录项，避免只同步文件内容却遗漏发布指针的创建或替换。"""
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _create(path: Path, data: bytes) -> None:
    """只创建新普通文件并完整同步；失败文件保留，不覆盖已有原件。"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        pending = memoryview(data)
        while pending:
            count = os.write(fd, pending)
            if count <= 0:
                raise OSError("short_write")
            pending = pending[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync(path.parent)


class Store:
    """根及祖先身份固定；不可变对象验证hash，运行锁覆盖完整写用例。"""

    def __init__(self, root: Path):
        self.root = location(root)
        repo = next((p for p in Path(__file__).resolve().parents if (p / "contracts/openapi.yaml").is_file()), None)
        if repo is not None and (root.is_relative_to(repo) or repo.is_relative_to(root)):
            raise FlowError("etf_root_overlaps_repository", 422)
        self.scope = digest({"format": "etf-flow-root-v1", "root": str(root)})
        self._parents = {p: (p.stat().st_dev, p.stat().st_ino) for p in (root, *root.parents)}
        self._mutex = threading.Lock()
        self._writer: int | None = None
        self._writer_fd: int | None = None

    def check(self) -> None:
        location(self.root)
        for path, expected in self._parents.items():
            checked_path(path)
            if (path.stat().st_dev, path.stat().st_ino) != expected:
                raise FlowError("etf_location_changed")

    @property
    def initialized(self) -> bool:
        """纯读检查完整初始化标记；部分初始化不在读取时修补。"""
        self.check()
        marker = self.root / "initialized.json"
        if not marker.exists():
            if any((self.root / name).exists() for name in ("objects", "journals", "incoming", ".writer.lock", "current.json")):
                raise FlowError("etf_incomplete_initialization")
            return False
        raw = self._read(marker, 4096)
        if decode(raw) != {"format": "etf-flow-store-v1", "scope": self.scope}:
            raise FlowError("etf_invalid_store")
        for name in ("objects", "journals", "incoming"):
            location(self.root / name)
        location(self.root / ".writer.lock", directory=False)
        return True

    def initialize(self) -> None:
        """仅明确初始化用例调用；必须新空根，失败保留以供人工核验。"""
        self.check()
        if any(self.root.iterdir()):
            raise FlowError("etf_initialization_requires_empty_root", 409)
        for name in ("objects", "journals", "incoming"):
            (self.root / name).mkdir(mode=0o700)
        _create(self.root / ".writer.lock", b"")
        _create(self.root / "initialized.json", canonical({"format": "etf-flow-store-v1", "scope": self.scope}))
        self.check()

    def _read(self, path: Path, limit: int = MAX_OBJECT_BYTES) -> bytes:
        """有限读取且复核根身份；正常不存在与损坏/不安全位置分别处理。"""
        self.check()
        checked_path(path)
        path.stat()  # 正常不存在保留FileNotFoundError；不与不安全位置混为一类。
        location(path, directory=False)
        if path.stat().st_size > limit:
            raise FlowError("etf_object_too_large")
        data = read_bytes(path, limit + 1)
        if len(data) > limit:
            raise FlowError("etf_object_too_large")
        self.check()
        return data

    @contextmanager
    def writer(self) -> Iterator[None]:
        """线程和进程均非阻塞独占；关闭页面不能释放服务worker持有的锁。"""
        if not self.initialized:
            raise FlowError("etf_not_initialized")
        if not self._mutex.acquire(blocking=False):
            raise FlowError("etf_busy")
        fd: int | None = None
        try:
            path = location(self.root / ".writer.lock", directory=False)
            before = path.stat()
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
                raise FlowError("etf_location_changed")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise FlowError("etf_busy") from error
            self._writer = threading.get_ident()
            self._writer_fd = fd
            yield
            self.check()
            after = path.stat()
            if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
                raise FlowError("etf_location_changed")
        finally:
            self._writer = None
            self._writer_fd = None
            if fd is not None:
                os.close(fd)
            self._mutex.release()

    def _require_writer(self) -> None:
        """所有存储变更均须由当前线程持有本根排他锁。"""
        self.check()
        if self._writer != threading.get_ident():
            raise FlowError("etf_writer_required", 403)

    def inherited_lock(self) -> int:
        """受控网络子进程继承同一个锁；父进程崩溃后仍不能误判为可恢复。"""
        self._require_writer()
        if self._writer_fd is None:
            raise FlowError("etf_writer_required", 403)
        return self._writer_fd

    def spool(self, attempt: str, suffix: str) -> Path:
        """临时原件也留在本根，不接受路径输入，不删除失败或部分响应。"""
        import re
        if not isinstance(attempt, str) or not re.fullmatch("[a-f0-9]{32}", attempt) or suffix not in {"raw", "receipt"}:
            raise FlowError("etf_invalid_receipt")
        self.check()
        return location(self.root / "incoming") / (attempt + "." + suffix)

    def create_spool(self, attempt: str, suffix: str) -> int:
        self._require_writer()
        path = self.spool(attempt, suffix)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fsync(fd)
            _fsync(path.parent)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def read_spool(self, attempt: str, suffix: str, limit: int) -> bytes | None:
        """缺文件代表未知回执；损坏或超限不能当作空响应。"""
        try:
            return self._read(self.spool(attempt, suffix), limit)
        except FileNotFoundError:
            return None

    def put(self, raw: bytes) -> str:
        """保存原件或规范对象；同hash只核对不覆盖，失败不删除已写文件。"""
        self._require_writer()
        if len(raw) > MAX_OBJECT_BYTES:
            raise FlowError("etf_object_too_large")
        identifier = hashlib.sha256(raw).hexdigest()
        path = self.root / "objects" / identifier
        location(path.parent)
        if path.exists():
            if self._read(path) != raw:
                raise FlowError("etf_object_corrupt")
        else:
            _create(path, raw)
        return identifier

    def put_json(self, value: Any) -> str:
        return self.put(canonical(value))

    def get(self, identifier: str) -> bytes:
        path = self.root / "objects" / object_id(identifier)
        try:
            raw = self._read(path)
        except FileNotFoundError as error:
            raise FlowError("etf_object_not_found", 404) from error
        if hashlib.sha256(raw).hexdigest() != identifier:
            raise FlowError("etf_object_corrupt")
        return raw

    def get_json(self, identifier: str) -> Any:
        return decode(self.get(identifier))

    def _pointer(self, path: Path) -> str | None:
        """只读取已有完整指针；缺失不初始化，破损不解释为空库。"""
        self.check()
        checked_path(path)
        try:
            value = exact(decode(self._read(path, 1024)), {"object_id"})
        except FileNotFoundError:
            return None
        return object_id(value["object_id"])

    def _replace_pointer(self, path: Path, identifier: str) -> None:
        """先同步新指针，再原子替换并同步父目录；旧目标对象始终保留。"""
        self._require_writer()
        checked_path(path)
        if path.exists():
            location(path, directory=False)
        location(path.parent)
        temporary = path.with_name(".pending-" + uuid4().hex)
        _create(temporary, canonical({"object_id": object_id(identifier)}))
        self.check()
        os.replace(temporary, path)
        _fsync(path.parent)

    def current_id(self) -> str | None:
        """正常空库返回None；不在GET创建current或锁。"""
        return self._pointer(self.root / "current.json") if self.initialized else None

    def publish(self, identifier: str, expected: str | None) -> None:
        """单指针CAS是发布点；parent链同时证明历史提交，原对象不删除。"""
        self._require_writer()
        snapshot = self.get_json(identifier)
        if not isinstance(snapshot, dict) or snapshot.get("parent") != expected or snapshot.get("format") != "etf-flow-snapshot-v1":
            raise FlowError("etf_invalid_snapshot")
        if self.current_id() != expected:
            raise FlowError("etf_snapshot_changed")
        self._replace_pointer(self.root / "current.json", identifier)

    def journal(self, key: str) -> tuple[str | None, Any | None]:
        """固定hash命名的状态指针；读取不修复queued/running记录。"""
        identifier = self._pointer(self.root / "journals" / object_id(key)) if self.initialized else None
        if identifier is None:
            return None, None
        record = exact(self.get_json(identifier), {"previous", "value"})
        if record["previous"] is not None:
            object_id(record["previous"])
        return identifier, record["value"]

    def write_journal(self, key: str, value: Any, expected: str | None) -> str:
        """状态每版仍是不可变对象，previous引用保留；指针更新要求原版本。"""
        self._require_writer()
        if self.journal(key)[0] != expected:
            raise FlowError("etf_journal_changed")
        raw = {"previous": expected, "value": value}
        identifier = self.put_json(raw)
        self._replace_pointer(self.root / "journals" / object_id(key), identifier)
        return identifier

    def published_operation(self, operation_key: str) -> tuple[str, dict[str, Any]] | None:
        """只沿已发布parent链查证原请求；孤立的预写快照不算已提交。"""
        identifier = self.current_id()
        visited: set[str] = set()
        while identifier is not None:
            if identifier in visited:
                raise FlowError("etf_snapshot_cycle")
            visited.add(identifier)
            value = self.get_json(identifier)
            if not isinstance(value, dict) or value.get("format") != "etf-flow-snapshot-v1":
                raise FlowError("etf_invalid_snapshot")
            if value.get("operation_key") == operation_key:
                return identifier, value
            identifier = value.get("parent")
            if identifier is not None:
                object_id(identifier)
        return None
