"""六指数 v2 不可变对象、事务发布及无副作用读取；不迁移 v1。"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import date, datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Callable, Iterator, TypedDict

from pmi.market_data import SnapshotError
from pmi.market_data.index_activity import is_active
from pmi.market_data.index_catalog import IndexDefinition, get_index
from pmi.market_data.index_history_calendar import FrozenWindow
from pmi.market_data.index_series_contract import Original, SeriesManifest, build_manifest, canonical, digest, parse_evidence, rebuild_manifest, utc
from pmi.market_data.read_only import ReadUnavailable, checked_path, read_bytes, read_scope

ACTIVE = frozenset({"preparing", "fetching_csindex", "fetching_cnindex", "fetching_eastmoney", "validating", "publishing"})
TERMINAL = frozenset({"idle", "completed", "failed", "interrupted"})
_SCHEMA_STATEMENTS = (
    "CREATE TABLE IF NOT EXISTS identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), index_id TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, end_date TEXT NOT NULL, anchor_date TEXT NOT NULL, first_observation TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id), observed_at TEXT NOT NULL, receipt TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS current_snapshot (singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot_id TEXT NOT NULL REFERENCES snapshots(id), observation_id TEXT NOT NULL REFERENCES observations(id))",
    "CREATE TABLE IF NOT EXISTS committed_jobs (job_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id), state TEXT NOT NULL)",
)


class UpdateState(TypedDict):
    """落盘任务状态；enabled 仅由公开门面注入。"""

    index_id: str
    job_id: str | None
    trigger: str | None
    stage: str
    result: str | None
    started_at: str | None
    finished_at: str | None
    target_start: str | None
    target_end: str | None
    previous_snapshot_id: str | None
    snapshot_id: str | None
    observation_id: str | None
    last_success_at: str | None
    added_dates: list[str]
    revised_dates: list[str]
    message: str
    differences: list[dict[str, str]]


class SourceReceipt(TypedDict):
    """来源原件的独立观察时间；不代表来源发布时刻。"""

    source: str
    url: str
    started_at: str
    completed_at: str
    object_id: str
    published_at: None


class Retrieval(TypedDict):
    """快照观察与内容分离，首次观察引用保持不变。"""

    index_id: str
    snapshot_id: str
    sources: list[SourceReceipt]
    observed_at: str


class SeriesSnapshot(SeriesManifest):
    """已完整重放的 manifest 加固定观察身份。"""

    snapshot_id: str
    observation_id: str
    retrieval: Retrieval


def index_root(parent: Path, index: IndexDefinition) -> Path:
    """仅由登记身份得到固定目录，不接受调用者拼接的路径。"""
    if get_index(index.index_id) != index:
        raise SnapshotError("unknown_index_definition")
    return checked_path(parent / index.relative_dir)


def _file(path: Path) -> bool:
    checked_path(path)
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ReadUnavailable("指数文件不是独立普通文件")
    return True


def _directory(path: Path) -> None:
    checked_path(path)
    if not path.is_dir():
        raise ReadUnavailable("指数目录类型不安全")


def sync_directory(path: Path) -> None:
    """同步目录项；调用者必须持父写锁并已核验定位。"""
    _directory(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_directories(parent: Path, index: IndexDefinition) -> Path:
    """父独占锁内创建本指数目录，随后由门面登记 inode。"""
    root = index_root(parent, index)
    for path in (parent / "indices", root, root / "objects"):
        checked_path(path)
        path.mkdir(exist_ok=True)
        _directory(path)
        sync_directory(path.parent)
    return root


def validate_id(value: str) -> None:
    """仅准入内容 hash，禁止将外部字符串解释为文件路径。"""
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SnapshotError("invalid_object_id")


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError("duplicate_local_json_member")
        result[key] = value
    return result


def load_json(content: bytes | str) -> dict:
    """只接受对象及唯一成员；本地损坏不宽容解析。"""
    try:
        value = json.loads(content, object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise SnapshotError("invalid_local_json") from error


def atomic_json(path: Path, value: dict) -> None:
    """父锁内原子替换状态；不覆盖链接或特殊文件。"""
    _file(path)
    _directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".index-v2-pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        _file(path)
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_record(path: Path, value: dict) -> None:
    """父独占锁内追加持久证据；不修改旧行。"""
    _file(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        actual = os.fstat(stream.fileno())
        if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1:
            raise ReadUnavailable("指数账本文件类型不安全")
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def write_object(root: Path, content: bytes) -> str:
    """已有对象先核对字节；新对象用硬链接发布，永不覆盖旧对象。"""
    objects = checked_path(root / "objects")
    _directory(objects)
    object_id = digest(content)
    path = objects / object_id
    if _file(path):
        if read_bytes(path) != content:
            raise SnapshotError("object_hash_mismatch")
        return object_id
    descriptor, temporary = tempfile.mkstemp(prefix=".index-v2-pending-", dir=objects)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        sync_directory(objects)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return object_id


def read_object(root: Path, object_id: str) -> bytes:
    """读取已存在的普通对象并核对 SHA；缺失或损坏不回退。"""
    validate_id(object_id)
    path = checked_path(root / "objects" / object_id)
    if not _file(path):
        raise SnapshotError("object_missing")
    content = read_bytes(path)
    if digest(content) != object_id:
        raise SnapshotError("object_hash_mismatch")
    return content


def _database(parent: Path, index: IndexDefinition) -> Path:
    return index_root(parent, index) / "index-v2.sqlite"


def has_database(parent: Path, index: IndexDefinition) -> bool:
    """仅检查库存在及类型；空库或损坏库不能解释为没有 v2。"""
    return _file(_database(parent, index))


def reject_sidecars(parent: Path, index: IndexDefinition) -> None:
    """任何正式 SQLite 辅助文件均保留并拒绝，必须早于目录/状态写入。"""
    _reject_sidecars(_database(parent, index))


def _reject_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        if _file(Path(str(path) + suffix)):
            raise ReadUnavailable("指数数据库辅助文件需要另行处理")


def _check_database(path: Path, *, links: int = 1) -> bool:
    _reject_sidecars(path)
    if links == 1:
        if not _file(path):
            return False
    else:
        _same_file(path, path.lstat(), links=links)
    header = read_bytes(path, 100)
    if len(header) != 100 or header[:16] != b"SQLite format 3\0" or header[18:20] != b"\x01\x01":
        raise ReadUnavailable("指数数据库不是正常回滚日志格式")
    return True


@contextmanager
def connection_locked(parent: Path, index: IndexDefinition) -> Iterator[sqlite3.Connection | None]:
    """父 EX 锁内只读正式库；所有写事务只能进入私有候选库。"""
    path = _database(parent, index)
    if not _check_database(path):
        yield None
        return
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.close()


@contextmanager
def candidate_connection(path: Path) -> Iterator[sqlite3.Connection]:
    """只对调用者自有私有副本打开事务连接，不接受正式库路径。"""
    if path.name != "candidate.sqlite" or re.fullmatch(r"\.index-v2-stage-[a-z0-9_]{8}", path.parent.name) is None:
        raise SnapshotError("invalid_candidate_path")
    if not _file(path):
        raise SnapshotError("candidate_missing")
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        yield connection
    finally:
        connection.close()


def _schema(connection: sqlite3.Connection, index: IndexDefinition) -> None:
    for statement in _SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.execute("INSERT OR IGNORE INTO identity VALUES (1,?)", (index.index_id,))
    _identity(connection, index)


def _identity(connection: sqlite3.Connection, index: IndexDefinition) -> None:
    rows = connection.execute("SELECT index_id FROM identity").fetchall()
    if len(rows) != 1 or rows[0][0] != index.index_id:
        raise SnapshotError("wrong_database_index")


def _same_file(path: Path, expected: os.stat_result, *, links: int) -> None:
    checked_path(path)
    actual = path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink != links
            or (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns)
            != (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns)):
        raise ReadUnavailable("指数恢复文件定位或内容已变化")


def _recovery_identity(path: Path, index: IndexDefinition, *, empty: bool = False) -> None:
    """恢复前只读核对不变的身份/schema；不将未恢复页用作金融读取。"""
    header = read_bytes(path, 100)
    if len(header) != 100 or header[:16] != b"SQLite format 3\0" or header[18:20] != b"\x01\x01":
        raise ReadUnavailable("指数恢复数据库格式不受支持")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0, isolation_level=None)
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        expected = {statement.split(" (")[0].split()[-1]: statement.replace(" IF NOT EXISTS", "")
                    for statement in _SCHEMA_STATEMENTS}
        actual = dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        other_schema = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('trigger','view') OR (type='index' AND sql IS NOT NULL)").fetchall()
        if actual != expected or other_schema:
            raise SnapshotError("recovery_schema_mismatch")
        _identity(connection, index)
        if empty and any(connection.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone() is not None
                         for table in ("snapshots", "observations", "current_snapshot", "committed_jobs")):
            raise SnapshotError("pending_database_not_empty")
    finally:
        connection.close()


def _pending_links(parent: Path, index: IndexDefinition) -> list[tuple[Path, Path, os.stat_result]]:
    """只识别本生产者 link 后未 unlink 的精确二链接，不接纳任意硬链接。"""
    root = index_root(parent, index)
    repairs = []
    for directory, prefix, database in ((root / "objects", ".index-v2-pending-", False),
                                         (root, ".index-v2-db-pending-", True)):
        _directory(directory)
        entries = {entry.name: entry for entry in directory.iterdir()}
        names = ["index-v2.sqlite"] if database else [name for name in entries if re.fullmatch(r"[0-9a-f]{64}", name)]
        for name in names:
            final = directory / name
            checked_path(final)
            if name not in entries:
                continue
            info = final.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ReadUnavailable("指数恢复目标不是普通文件")
            if info.st_nlink == 1:
                continue
            if info.st_nlink != 2:
                raise ReadUnavailable("指数恢复拒绝未知硬链接")
            candidates = []
            for pending_name, pending in entries.items():
                if re.fullmatch(re.escape(prefix) + r"[a-z0-9_]{8}", pending_name):
                    value = pending.lstat()
                    if stat.S_ISREG(value.st_mode) and (value.st_dev, value.st_ino) == (info.st_dev, info.st_ino):
                        candidates.append(pending)
            if database and not candidates:
                candidates = _published_links(parent, index, final, info)
                if len(candidates) != 1:
                    raise ReadUnavailable("指数恢复缺少唯一已发布候选链接")
                repairs.append((candidates[0], final, info))
                continue
            if len(candidates) != 1:
                raise ReadUnavailable("指数恢复缺少唯一自有临时链接")
            pending = candidates[0]
            _same_file(pending, info, links=2)
            if database:
                _recovery_identity(final, index, empty=True)
            elif digest(read_bytes(final)) != name:
                raise SnapshotError("object_hash_mismatch")
            _same_file(final, info, links=2)
            repairs.append((pending, final, info))
    return repairs


def _history_inventory(connection: sqlite3.Connection) -> dict[str, dict[str, tuple]]:
    """核对原库可见的不可变历史行；无法可靠读取时不冒险恢复原库。"""
    return {table: {str(row[0]): tuple(row) for row in connection.execute("SELECT " + columns + " FROM " + table)}
            for table, columns in (("snapshots", "id,end_date,anchor_date,first_observation"),
                                   ("observations", "id,snapshot_id,observed_at,receipt,rowid"),
                                   ("committed_jobs", "job_id,snapshot_id,state"),
                                   ("current_snapshot", "singleton,snapshot_id,observation_id"))}


def _validate_database(parent: Path, index: IndexDefinition, path: Path, *, links: int = 1) -> dict:
    """完整核验候选的 current、全部快照、观察与任务，不只抽查当前指针。"""
    _check_database(path, links=links)
    _recovery_identity(path, index)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        if connection.execute("PRAGMA integrity_check").fetchall()[0][0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
            raise SnapshotError("recovery_database_integrity")
        inventory = _history_inventory(connection)
        manifests, receipts = {}, {}
        for identifier in inventory["snapshots"]:
            snapshot = _read_snapshot(parent, index, identifier, connection)
            manifests[identifier] = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "observation_id", "retrieval"}}
            receipts[snapshot["observation_id"]] = snapshot["retrieval"]
        for identifier, row in inventory["observations"].items():
            if row[1] not in manifests or row[4] < 1:
                raise SnapshotError("recovery_orphan_observation")
            if identifier not in receipts:
                receipts[identifier] = _read_receipt(connection, index_root(parent, index), index, row[1], identifier, manifests[row[1]])
        job_states = [load_json(row[2]) for row in inventory["committed_jobs"].values()]
        for row, state in zip(inventory["committed_jobs"].values(), job_states):
            _validate_state(state, index)
            receipt = receipts.get(state["observation_id"])
            if receipt is None:
                raise SnapshotError("committed_observation_missing")
            _validate_job_state(state, index, row[0], row[1], receipt)
        if ({job["snapshot_id"] for job in job_states} != set(inventory["snapshots"])
                or {job["observation_id"] for job in job_states} != set(inventory["observations"])):
            raise SnapshotError("recovery_history_proof_incomplete")
        # observations 从不删除或改写；rowid保留唯一插入顺序。用原发布规则
        # 重放所有成功观察，防止journal仅回退current而保留全部历史行。
        expected_current = None
        previous_window = previous_time = None
        for row in sorted(inventory["observations"].values(), key=lambda value: value[4]):
            snapshot = inventory["snapshots"][row[1]]
            window, observed = (snapshot[1], snapshot[2]), _instant(row[2])
            if (expected_current is None or (window[0] >= previous_window[0] and window[1] >= previous_window[1]
                                            and observed >= previous_time)):
                expected_current = (1, row[1], row[0])
                previous_window, previous_time = window, observed
        if inventory["current_snapshot"] != ({"1": expected_current} if expected_current else {}):
            raise SnapshotError("recovery_current_history_mismatch")
        return inventory
    finally:
        connection.close()


class PublicationUncertain(SnapshotError):
    """正式建名已发生但同步或最终核验未确认；必须保留副本并报告 unknown。"""


def _location(path: Path) -> dict[str, int]:
    checked_path(path)
    value = path.lstat()
    return {"device": value.st_dev, "inode": value.st_ino}


def _valid_location(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == {"device", "inode"}
            and type(value["device"]) is int and value["device"] >= 0
            and type(value["inode"]) is int and value["inode"] > 0)


def _published_links(parent: Path, index: IndexDefinition, final: Path, info: os.stat_result) -> list[Path]:
    """只解除已发布完整库的唯一候选别名，绝不提升缺少 final 的候选。"""
    root = index_root(parent, index)
    candidates = []
    for stage in root.iterdir():
        if re.fullmatch(r"\.index-v2-stage-[a-z0-9_]{8}", stage.name) is None:
            continue
        _directory(stage)
        candidate = checked_path(stage / "candidate.sqlite")
        if not candidate.exists():
            continue
        value = candidate.lstat()
        if (value.st_dev, value.st_ino) != (info.st_dev, info.st_ino):
            continue
        _same_file(candidate, info, links=2)
        _reject_sidecars(candidate)
        receipt_path = stage / "publication.json"
        if not _file(receipt_path):
            raise ReadUnavailable("指数首存残留缺少发布凭据")
        receipt = load_json(read_bytes(receipt_path))
        fields = {"schema_version", "index_id", "index_location", "stage_location", "candidate_location",
                  "base", "candidate_sha256", "completed_state", "record_sha256"}
        if set(receipt) != fields:
            raise SnapshotError("invalid_publication_receipt")
        unsigned = {key: value for key, value in receipt.items() if key != "record_sha256"}
        if (receipt["schema_version"] != "index-series-publication-v1" or receipt["index_id"] != index.index_id
                or receipt["base"] is not None or digest(canonical(unsigned)) != receipt["record_sha256"]
                or any(not _valid_location(receipt[key]) or receipt[key] != _location(path)
                       for key, path in (("index_location", root), ("stage_location", stage), ("candidate_location", candidate)))
                or receipt["candidate_sha256"] != digest(read_bytes(candidate))):
            raise SnapshotError("publication_receipt_mismatch")
        _validate_state(receipt["completed_state"], index)
        inventory = _validate_database(parent, index, candidate, links=2)
        job = inventory["committed_jobs"].get(receipt["completed_state"]["job_id"])
        if job is None or load_json(job[2]) != receipt["completed_state"]:
            raise SnapshotError("publication_job_mismatch")
        candidates.append(candidate)
    return candidates


def recover_locked(parent: Path, index: IndexDefinition, *, guard: Callable[[], None] | None = None) -> None:
    """父 EX 下仅收尾严格证明的自身两链接；正式 SQLite sidecar 一律不处理。"""
    if guard:
        guard()
    reject_sidecars(parent, index)
    repairs = _pending_links(parent, index)
    locations = {pending: (_location(pending.parent), _location(final.parent)) for pending, final, _ in repairs}
    # 全部证明收齐才清理；没有残留时不打开写连接或写任何文件。
    for pending, final, info in repairs:
        if guard:
            guard()
        reject_sidecars(parent, index)
        if (_location(pending.parent), _location(final.parent)) != locations[pending]:
            raise ReadUnavailable("指数残留目录定位变化")
        _same_file(final, info, links=2)
        _same_file(pending, info, links=2)
        os.unlink(pending)
        _same_file(final, info, links=1)
        sync_directory(pending.parent)
        if final.parent != pending.parent:
            sync_directory(final.parent)


def _sync_file(path: Path) -> None:
    if not _file(path):
        raise SnapshotError("publication_file_missing")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _new_file(path: Path, content: bytes) -> os.stat_result:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    identity = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            return os.fstat(stream.fileno())
    except BaseException:
        try:
            if _file(path) and _location(path) == {"device": identity.st_dev, "inode": identity.st_ino}:
                os.unlink(path)
        except (OSError, ReadUnavailable):
            pass
        raise


def _stage_cleanup(stage: Path, identity: dict, owned: dict[str, os.stat_result]) -> None:
    """仅清理本调用仍拥有的文件；异常成员或换置时保留整份证据。"""
    try:
        _directory(stage)
        if _location(stage) != identity:
            return
        entries = list(stage.iterdir())
        for path in entries:
            if path.name not in owned or not _file(path):
                return
            value, expected = path.lstat(), owned[path.name]
            if (value.st_dev, value.st_ino) != (expected.st_dev, expected.st_ino):
                return
        for path in entries:
            os.unlink(path)
        os.rmdir(stage)
    except (OSError, ReadUnavailable):
        # 清理故障不能触发金融回滚，也不扫描清理他人的残留。
        return


def _validate_publication(before: dict, after: dict, completed: UpdateState, receipt: Retrieval, window: FrozenWindow) -> None:
    """精确比较全部旧行及唯一允许的新增行，current 按既有发布规则推导。"""
    expected = deepcopy(before)
    snapshot_id, observation_id = completed["snapshot_id"], completed["observation_id"]
    expected["snapshots"].setdefault(snapshot_id, (snapshot_id, window.end, window.anchor_date, observation_id))
    inserted = observation_id not in expected["observations"]
    if inserted:
        rowid = max((row[4] for row in expected["observations"].values()), default=0) + 1
        expected["observations"][observation_id] = (observation_id, snapshot_id, receipt["observed_at"], canonical(receipt).decode(), rowid)
        old = expected["current_snapshot"].get("1")
        old_snapshot = expected["snapshots"][old[1]] if old else None
        old_observation = expected["observations"][old[2]] if old else None
        if (old is None or (window.end >= old_snapshot[1] and window.anchor_date >= old_snapshot[2]
                            and _instant(receipt["observed_at"]) >= _instant(old_observation[2]))):
            expected["current_snapshot"] = {"1": (1, snapshot_id, observation_id)}
    expected["committed_jobs"][completed["job_id"]] = (completed["job_id"], snapshot_id, canonical(completed).decode())
    if after != expected:
        raise SnapshotError("publication_history_mismatch")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(utc(value).replace("Z", "+00:00"))


def _receipt(index: IndexDefinition, snapshot_id: str, originals: tuple[Original, ...]) -> Retrieval:
    sources = [{"source": item.source, "url": item.url, "started_at": utc(item.started_at),
                "completed_at": utc(item.completed_at), "object_id": digest(item.content), "published_at": None} for item in originals]
    return {"index_id": index.index_id, "snapshot_id": snapshot_id, "sources": sources,
            "observed_at": max((item["completed_at"] for item in sources), key=_instant)}


def publish(parent: Path, index: IndexDefinition, window: FrozenWindow, manifest: SeriesManifest,
            originals: tuple[Original, ...], state: UpdateState, checkpoint: Callable[[str], None] | None = None) -> UpdateState:
    """私有副本完成事务与全历史核验，fsync 后原子发布；正式库始终只读。"""
    _validate_state(state, index)
    if (build_manifest(index, window, originals) != manifest or state.get("index_id") != index.index_id
            or state["target_start"] != window.start or state["target_end"] != window.end):
        raise SnapshotError("publish_identity_mismatch")
    root, final = index_root(parent, index), _database(parent, index)
    reject_sidecars(parent, index)
    exists = _check_database(final)
    snapshot_id = digest(canonical(manifest))
    with connection_locked(parent, index) as connection:
        previous_job = _committed_job(parent, index, state["job_id"], connection)
    if previous_job:
        if previous_job["snapshot_id"] != snapshot_id:
            raise SnapshotError("job_content_conflict")
        return previous_job
    before = (_validate_database(parent, index, final) if exists else
              {key: {} for key in ("snapshots", "observations", "committed_jobs", "current_snapshot")})
    old_info = final.lstat() if exists else None
    old_bytes = read_bytes(final) if exists else b""
    if exists:
        _same_file(final, old_info, links=1)
    for original in originals:
        write_object(root, original.content)
    write_object(root, canonical(manifest))
    receipt = _receipt(index, snapshot_id, originals)
    observation_id = digest(canonical(receipt))
    if checkpoint:
        checkpoint("objects_written")
    stage = Path(tempfile.mkdtemp(prefix=".index-v2-stage-", dir=root))
    stage_identity, root_identity = _location(stage), _location(root)
    candidate = stage / "candidate.sqlite"
    owned: dict[str, os.stat_result] = {}
    published = confirmed = False
    try:
        if exists:
            owned["before.sqlite"] = _new_file(stage / "before.sqlite", old_bytes)
        owned["candidate.sqlite"] = _new_file(candidate, old_bytes)
        if read_bytes(candidate) != old_bytes:
            raise SnapshotError("candidate_copy_mismatch")
        if checkpoint:
            checkpoint("candidate_copied")
        with candidate_connection(candidate) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if not exists:
                    _schema(connection, index)
                _identity(connection, index)
                if checkpoint:
                    checkpoint("candidate_started")
                current = connection.execute("SELECT s.end_date,s.anchor_date,o.observed_at FROM current_snapshot c JOIN snapshots s ON s.id=c.snapshot_id JOIN observations o ON o.id=c.observation_id").fetchone()
                connection.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?)", (snapshot_id, window.end, window.anchor_date, observation_id))
                inserted = connection.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?)", (observation_id, snapshot_id, receipt["observed_at"], canonical(receipt).decode())).rowcount
                if inserted and (current is None or (window.end >= current["end_date"] and window.anchor_date >= current["anchor_date"]
                                                    and _instant(receipt["observed_at"]) >= _instant(current["observed_at"]))):
                    connection.execute("INSERT OR REPLACE INTO current_snapshot VALUES (1,?,?)", (snapshot_id, observation_id))
                completed = {**state, "stage": "completed", "snapshot_id": snapshot_id, "observation_id": observation_id,
                             "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                             "last_success_at": receipt["observed_at"]}
                connection.execute("INSERT INTO committed_jobs VALUES (?,?,?)", (state["job_id"], snapshot_id, canonical(completed).decode()))
                if checkpoint:
                    checkpoint("before_commit")
                connection.commit()
                if checkpoint:
                    checkpoint("candidate_committed")
            except BaseException:
                connection.rollback()
                raise
        _reject_sidecars(candidate)
        _sync_file(candidate)
        if checkpoint:
            checkpoint("candidate_synced")
        after = _validate_database(parent, index, candidate)
        _validate_publication(before, after, completed, receipt, window)
        candidate_info, candidate_hash = candidate.lstat(), digest(read_bytes(candidate))
        publication = {"schema_version": "index-series-publication-v1", "index_id": index.index_id,
                       "index_location": root_identity, "stage_location": stage_identity,
                       "candidate_location": _location(candidate),
                       "base": ({"device": old_info.st_dev, "inode": old_info.st_ino,
                                 "size": old_info.st_size, "sha256": digest(old_bytes)} if exists else None),
                       "candidate_sha256": candidate_hash, "completed_state": completed}
        publication["record_sha256"] = digest(canonical(publication))
        owned["publication.json"] = _new_file(stage / "publication.json", canonical(publication))
        sync_directory(stage)
        if checkpoint:
            checkpoint("publication_synced")
            checkpoint("before_publish")
        if _location(root) != root_identity or _location(stage) != stage_identity:
            raise ReadUnavailable("指数发布目录定位变化")
        reject_sidecars(parent, index)
        _same_file(stage / "publication.json", owned["publication.json"], links=1)
        if read_bytes(stage / "publication.json") != canonical(publication):
            raise SnapshotError("publication_receipt_changed")
        if exists:
            _same_file(stage / "before.sqlite", owned["before.sqlite"], links=1)
            if read_bytes(stage / "before.sqlite") != old_bytes:
                raise SnapshotError("publication_backup_changed")
        _same_file(candidate, candidate_info, links=1)
        _reject_sidecars(candidate)
        if digest(read_bytes(candidate)) != candidate_hash:
            raise SnapshotError("candidate_changed_before_publish")
        if exists:
            _same_file(final, old_info, links=1)
            if final.lstat().st_ctime_ns != old_info.st_ctime_ns or read_bytes(final) != old_bytes:
                raise ReadUnavailable("指数发布前原库已变化")
            os.replace(candidate, final)
            published = True
            if checkpoint:
                checkpoint("database_replaced")
        else:
            os.link(candidate, final, follow_symlinks=False)
            published = True
            if checkpoint:
                checkpoint("database_linked")
            if _location(root) != root_identity or _location(stage) != stage_identity:
                raise ReadUnavailable("指数发布目录定位变化")
            _same_file(candidate, candidate_info, links=2)
            _same_file(final, candidate_info, links=2)
            os.unlink(candidate)
            if checkpoint:
                checkpoint("database_unlinked")
            sync_directory(stage)
        _same_file(final, candidate_info, links=1)
        if digest(read_bytes(final)) != candidate_hash:
            raise SnapshotError("published_database_hash_mismatch")
        sync_directory(root)
        if checkpoint:
            checkpoint("directory_synced")
        if (_location(root) != root_identity or _location(stage) != stage_identity
                or _validate_database(parent, index, final) != after):
            raise SnapshotError("published_database_proof_mismatch")
        _same_file(final, candidate_info, links=1)
        if digest(read_bytes(final)) != candidate_hash:
            raise SnapshotError("published_database_hash_mismatch")
        confirmed = True
        if checkpoint:
            checkpoint("after_publish")
            checkpoint("after_commit")
        return completed
    except Exception as error:
        if published and not confirmed:
            raise PublicationUncertain("publication_outcome_unknown") from error
        raise
    finally:
        if not published or confirmed:
            _stage_cleanup(stage, stage_identity, owned)


def _read_receipt(connection: sqlite3.Connection, root: Path, index: IndexDefinition,
                  snapshot_id: str, observation_id: str, manifest: dict) -> dict:
    """核对观察 hash、指数归属、原件身份并重放完整金融契约。"""
    validate_id(observation_id)
    row = connection.execute("SELECT snapshot_id,observed_at,receipt FROM observations WHERE id=?", (observation_id,)).fetchone()
    if row is None or row["snapshot_id"] != snapshot_id:
        raise SnapshotError("observation_membership_mismatch")
    receipt = load_json(row["receipt"])
    if digest(canonical(receipt)) != observation_id:
        raise SnapshotError("observation_hash_mismatch")
    try:
        originals = tuple(Original(item["source"], read_object(root, item["object_id"]), item["started_at"], item["completed_at"], item["url"]) for item in receipt["sources"])
        if _receipt(index, snapshot_id, originals) != receipt or receipt["observed_at"] != row["observed_at"]:
            raise SnapshotError("observation_identity_mismatch")
        rebuild_manifest(index, manifest, originals)
    except (KeyError, TypeError) as error:
        raise SnapshotError("invalid_observation") from error
    return receipt


def _read_snapshot(parent: Path, index: IndexDefinition, snapshot_id: str | None, connection: sqlite3.Connection | None) -> SeriesSnapshot | None:
    """连接所属完整用例内读取一次固定内容，当前指针另核对所指观察。"""
    if snapshot_id is not None:
        validate_id(snapshot_id)
    if connection is None:
        return None
    _identity(connection, index)
    root = index_root(parent, index)
    current = None
    if snapshot_id is None:
        current = connection.execute("SELECT snapshot_id,observation_id FROM current_snapshot WHERE singleton=1").fetchone()
        if current is None:
            return None
        snapshot_id = current["snapshot_id"]
    row = connection.execute("SELECT end_date,anchor_date,first_observation FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
    if row is None:
        if current is not None:
            raise SnapshotError("current_snapshot_missing")
        return None
    manifest = load_json(read_object(root, snapshot_id))
    receipt = _read_receipt(connection, root, index, snapshot_id, row["first_observation"], manifest)
    if row["end_date"] != manifest["window"]["end"] or row["anchor_date"] != manifest["window"]["anchor_date"]:
        raise SnapshotError("snapshot_end_mismatch")
    if current is not None and current["observation_id"] != row["first_observation"]:
        _read_receipt(connection, root, index, snapshot_id, current["observation_id"], manifest)
    return {**manifest, "snapshot_id": snapshot_id, "observation_id": row["first_observation"], "retrieval": receipt}


def read_snapshot(parent: Path, index: IndexDefinition, snapshot_id: str | None = None, *, connection: sqlite3.Connection | None = None) -> SeriesSnapshot | None:
    """完整只读事务内重放双源；固定引用绝不跨指数或回退版本。"""
    _check_database(_database(parent, index))
    scope = nullcontext(connection) if connection is not None else read_scope(parent, _database(parent, index))
    with scope as active:
        return _read_snapshot(parent, index, snapshot_id, active)


def read_snapshot_locked(parent: Path, index: IndexDefinition, snapshot_id: str | None = None) -> dict | None:
    """父独占锁内读取；仅更新器调用，不再获取共享锁。"""
    with connection_locked(parent, index) as connection:
        return _read_snapshot(parent, index, snapshot_id, connection)


def latest_success_at_locked(parent: Path, index: IndexDefinition) -> str | None:
    """父 EX 锁内返回当前指针的已核成功观察；不复用固定快照首次观察。"""
    with connection_locked(parent, index) as connection:
        snapshot = _read_snapshot(parent, index, None, connection)
        if snapshot is None:
            return None
        row = connection.execute("SELECT observation_id FROM current_snapshot WHERE singleton=1").fetchone()
        if row[0] == snapshot["observation_id"]:
            return snapshot["retrieval"]["observed_at"]
        manifest = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "observation_id", "retrieval"}}
        return _read_receipt(connection, index_root(parent, index), index, snapshot["snapshot_id"], row[0], manifest)["observed_at"]


def read_evidence(parent: Path, index: IndexDefinition, snapshot_id: str, object_id: str, *, connection: sqlite3.Connection | None = None) -> dict:
    """先验证固定快照全体来源及成员关系，再提供原值及定位。"""
    validate_id(object_id)
    _check_database(_database(parent, index))
    scope = nullcontext(connection) if connection is not None else read_scope(parent, _database(parent, index))
    with scope as active:
        snapshot = _read_snapshot(parent, index, snapshot_id, active)
        if snapshot is None:
            raise SnapshotError("index_evidence_not_found")
        receipt = next((item for item in snapshot["retrieval"]["sources"] if item["object_id"] == object_id), None)
        if receipt is None:
            raise SnapshotError("index_evidence_not_member")
        content = read_object(index_root(parent, index), object_id)
        manifest = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "observation_id", "retrieval"}}
        evidence = parse_evidence(index, manifest, Original(receipt["source"], content, receipt["started_at"], receipt["completed_at"], receipt["url"]))
        return {"snapshot_id": snapshot_id, "observation_id": snapshot["observation_id"], **evidence,
                "retrieval": receipt, "verification": snapshot["verification"],
                "text_preview": content[:4096].decode("utf-8", errors="replace"), "preview_truncated": len(content) > 4096}


def idle_state(index: IndexDefinition) -> UpdateState:
    """返回新字典，避免实例间共享状态。"""
    return {"index_id": index.index_id, "job_id": None, "trigger": None, "stage": "idle", "result": None,
            "started_at": None, "finished_at": None, "target_start": None, "target_end": None,
            "previous_snapshot_id": None, "snapshot_id": None, "observation_id": None, "last_success_at": None,
            "added_dates": [], "revised_dates": [], "message": "尚无指数更新任务", "differences": []}


def raw_status(parent: Path, index: IndexDefinition) -> UpdateState:
    """只读状态字节；不把残留 active 文本当作运行证明。"""
    path = index_root(parent, index) / "update-v2-status.json"
    if not _file(path):
        return idle_state(index)
    state = load_json(read_bytes(path))
    _validate_state(state, index)
    return state


def save_status(parent: Path, index: IndexDefinition, state: dict) -> None:
    """父锁内写入本指数状态；拒绝夹带公共门面权限或其他字段。"""
    _validate_state(state, index)
    atomic_json(index_root(parent, index) / "update-v2-status.json", state)


def _validate_state(state: dict, index: IndexDefinition) -> None:
    """落盘和重读使用同一精确状态边界，损坏数据不能变成业务结果。"""
    try:
        if (set(state) != set(idle_state(index)) or state["index_id"] != index.index_id
                or state["stage"] not in ACTIVE | TERMINAL
                or state["trigger"] not in {None, "manual", "startup"}
                or state["result"] not in {None, "business_changed", "evidence_changed", "unchanged", "source_not_ready", "failed", "interrupted"}
                or not isinstance(state["message"], str)):
            raise ValueError("shape")
        job = state["job_id"]
        if state["stage"] != "idle" and (not isinstance(job, str) or not job.isascii() or not 1 <= len(job) <= 128):
            raise ValueError("job")
        for key in ("previous_snapshot_id", "snapshot_id", "observation_id"):
            if state[key] is not None:
                validate_id(state[key])
        for key in ("started_at", "finished_at", "last_success_at"):
            if state[key] is not None:
                utc(state[key])
        for key in ("target_start", "target_end"):
            if state[key] is not None and date.fromisoformat(state[key]).isoformat() != state[key]:
                raise ValueError("date")
        for key in ("added_dates", "revised_dates"):
            if not isinstance(state[key], list) or any(date.fromisoformat(day).isoformat() != day for day in state[key]):
                raise ValueError("dates")
        if not isinstance(state["differences"], list):
            raise ValueError("differences")
        for difference in state["differences"]:
            if (not isinstance(difference, dict) or set(difference) != {"date", "field", "official_raw", "comparison_value", "eastmoney_raw"}
                    or any(not isinstance(value, str) for value in difference.values())
                    or difference["field"] not in {"open", "high", "low", "close"}
                    or date.fromisoformat(difference["date"]).isoformat() != difference["date"]):
                raise ValueError("difference")
    except (ValueError, TypeError, KeyError) as error:
        raise SnapshotError("invalid_index_status") from error


def _validate_job_state(state: dict, index: IndexDefinition, job_id: str, snapshot_id: str, receipt: dict) -> None:
    """核验已完整重放观察所对应的任务，供全库存与单 job 两条读路径共用。"""
    _validate_state(state, index)
    if (state["job_id"] != job_id or state["snapshot_id"] != snapshot_id or state["stage"] != "completed"
            or receipt["snapshot_id"] != snapshot_id or digest(canonical(receipt)) != state["observation_id"]):
        raise SnapshotError("committed_job_identity_mismatch")
    if (state["last_success_at"] != receipt["observed_at"] or state["finished_at"] is None
            or state["started_at"] is None or _instant(state["finished_at"]) < _instant(state["started_at"])
            or _instant(state["finished_at"]) < _instant(receipt["observed_at"])):
        raise SnapshotError("committed_observation_time_mismatch")


def _committed_job(parent: Path, index: IndexDefinition, job_id: str | None, connection: sqlite3.Connection | None) -> dict | None:
    if not job_id or connection is None:
        return None
    _identity(connection, index)
    row = connection.execute("SELECT snapshot_id,state FROM committed_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        return None
    state = load_json(row["state"])
    _validate_state(state, index)
    if state.get("job_id") != job_id or state.get("index_id") != index.index_id or state.get("snapshot_id") != row["snapshot_id"] or state.get("stage") != "completed":
        raise SnapshotError("committed_job_identity_mismatch")
    snapshot = _read_snapshot(parent, index, row["snapshot_id"], connection)
    if snapshot is None:
        raise SnapshotError("committed_snapshot_missing")
    manifest = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "observation_id", "retrieval"}}
    receipt = (snapshot["retrieval"] if state["observation_id"] == snapshot["observation_id"] else
               _read_receipt(connection, index_root(parent, index), index, row["snapshot_id"], state["observation_id"], manifest))
    _validate_job_state(state, index, job_id, row["snapshot_id"], receipt)
    return state


def committed_job_locked(parent: Path, index: IndexDefinition, job_id: str | None) -> dict | None:
    """父 EX 锁内查询精确 job，包含所引用快照和观察的完整核验。"""
    with connection_locked(parent, index) as connection:
        return _committed_job(parent, index, job_id, connection)


def read_status(parent: Path, index: IndexDefinition) -> dict:
    """GET 不恢复磁盘；仅精确活动锁或已验证 job 提交可证明运行/成功。"""
    try:
        _check_database(_database(parent, index))
        with read_scope(parent, _database(parent, index)) as connection:
            state = raw_status(parent, index)
            committed = _committed_job(parent, index, state.get("job_id"), connection)
            if committed:
                return committed
            if state["stage"] in ACTIVE:
                return {**state, "stage": "interrupted", "result": "interrupted", "message": "任务已中断，旧快照保留"}
            if state["stage"] == "completed" and state["result"] != "source_not_ready":
                raise SnapshotError("completed_job_proof_missing")
            return state
    except ReadUnavailable:
        active = _observe_active(parent, index)
        if active is not None:
            return active
        raise


def _observe_active(parent: Path, index: IndexDefinition) -> UpdateState | None:
    """父写锁仍忙、inode 稳定且精确活动凭据匹配时才返回运行状态。"""
    path = checked_path(parent / ".writer.lock")
    if not _file(path):
        return None
    identity = path.stat().st_dev, path.stat().st_ino
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        value = os.fstat(stream.fileno())
        if not stat.S_ISREG(value.st_mode) or (value.st_dev, value.st_ino) != identity:
            raise ReadUnavailable("父写锁身份不稳定")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            first = raw_status(parent, index)
            active = (first["stage"] in ACTIVE and is_active(index_root(parent, index), index.index_id, first.get("job_id"))
                      and raw_status(parent, index) == first)
            after = path.stat(follow_symlinks=False)
            if not active or (after.st_dev, after.st_ino) != identity:
                return None
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return deepcopy(first)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return None


def read_original(parent: Path, index: IndexDefinition, snapshot_id: str, object_id: str) -> Original:
    """量额配对所需的完整已存原件；先重放固定价格快照并核成员，不返回预览冒充原件。"""
    validate_id(object_id)
    with read_scope(parent, _database(parent, index)) as active:
        snapshot = _read_snapshot(parent, index, snapshot_id, active)
        if snapshot is None:
            raise SnapshotError("index_evidence_not_found")
        receipt = next((x for x in snapshot["retrieval"]["sources"] if x["object_id"] == object_id), None)
        if receipt is None:
            raise SnapshotError("index_evidence_not_member")
        content = read_object(index_root(parent, index), object_id)
        return Original(receipt["source"], content, receipt["started_at"], receipt["completed_at"], receipt["url"])
