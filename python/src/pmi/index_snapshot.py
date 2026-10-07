"""指数独立子根的内容寻址、观察排序、事务发布与只读证据。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from pmi.index_contract import Original, build_manifest, canonical, contract_sources, digest, source_url, utc
from pmi.snapshot import SnapshotError

ID_PATTERN = r"[0-9a-f]{64}"


def safe_path(path: Path) -> Path:
    """检查绝对路径各层，拒绝符号链接，包括父数据根的祖先目录。"""
    path = Path(os.path.abspath(path.expanduser()))
    for layer in (path, *path.parents):
        if layer.is_symlink():
            raise SnapshotError("index_path_invalid: 数据路径含符号链接")
    return path


def index_root(parent: Path) -> Path:
    """解析固定子根，读取时不创建任何目录或锁文件。"""
    return safe_path(parent / "indices" / "csi000300")


def validate_id(value: str) -> None:
    """仅准入SHA-256对象ID，禁止路径输入。"""
    if not re.fullmatch(ID_PATTERN, value):
        raise SnapshotError("index_id_invalid: ID必须是64位小写十六进制")


def atomic_json(path: Path, value: dict) -> None:
    """锁内原子写状态；落盘和目录同步使中断后结果可判定。"""
    safe_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_object(root: Path, content: bytes) -> str:
    """不可变写入哈希对象；已存在对象损坏时拒绝覆盖。"""
    objects = safe_path(root / "objects")
    objects.mkdir(exist_ok=True)
    object_id = digest(content)
    path = safe_path(objects / object_id)
    if path.exists():
        if path.read_bytes() != content:
            raise SnapshotError("指数对象哈希损坏")
        return object_id
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=objects)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # 所有调用者持父根锁；link只创建新名称，绝不覆盖已发布对象。
        os.link(temporary, path)
        _sync_directory(objects)
    finally:
        os.unlink(temporary)
    return object_id


def read_object(root: Path, object_id: str) -> bytes:
    """读取固定哈希对象并检验路径与内容，不回退到当前版本。"""
    validate_id(object_id)
    content = safe_path(root / "objects" / object_id).read_bytes()
    if digest(content) != object_id:
        raise SnapshotError("指数对象哈希损坏")
    return content


@contextmanager
def _connection(root: Path, write: bool = False) -> Iterator[sqlite3.Connection]:
    path = safe_path(root / "index.sqlite")
    for suffix in ("-wal", "-shm", "-journal"):
        safe_path(Path(str(path) + suffix))
    connection = sqlite3.connect(path if write else path.as_uri() + "?mode=ro", uri=not write)
    connection.row_factory = sqlite3.Row
    try:
        if write:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
        yield connection
    finally:
        connection.close()


def _schema(connection: sqlite3.Connection) -> None:
    for statement in (
        "CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, end_date TEXT NOT NULL, first_observation TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id), observed_at TEXT NOT NULL, receipt TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS current_snapshot (singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot_id TEXT NOT NULL REFERENCES snapshots(id), observation_id TEXT NOT NULL REFERENCES observations(id))",
        "CREATE TABLE IF NOT EXISTS committed_jobs (job_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES snapshots(id), state TEXT NOT NULL)",
    ):
        connection.execute(statement)


def _observation(manifest_id: str, originals: tuple[Original, ...], days: tuple[str, ...]) -> dict:
    receipts = []
    for item in originals:
        start, end = utc(item.started_at), utc(item.completed_at)
        if end < start:
            raise SnapshotError("来源观察完成时刻早于开始")
        receipts.append({"source": item.source, "url": source_url(item.source, days), "started_at": start,
                         "completed_at": end, "object_id": digest(item.content), "published_at": None})
    return {"snapshot_id": manifest_id, "sources": receipts, "observed_at": max(item["completed_at"] for item in receipts)}


def publish(parent: Path, manifest: dict, originals: tuple[Original, ...], state: dict,
            checkpoint: Callable[[str], None] | None = None) -> str:
    """在父根锁内先写全对象，再事务提交内容/观察/当前指针/job结果。

    旧截止日或迟到旧观察不推进指针；同一观察重放幂等。提交后状态丢失可由job表恢复。
    """
    days = tuple(manifest["calendar_dates"])
    if build_manifest(days, originals) != manifest:
        raise SnapshotError("清单与双源固定输入不一致")
    root = index_root(parent)
    root.mkdir(parents=True, exist_ok=True)
    for original in originals:
        write_object(root, original.content)
    snapshot_id = write_object(root, canonical(manifest))
    receipt = _observation(snapshot_id, originals, days)
    observation_id = digest(canonical(receipt))
    if checkpoint:
        checkpoint("objects_written")
    with _connection(root, True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _schema(connection)
            existing = connection.execute("SELECT state FROM committed_jobs WHERE job_id=?", (state["job_id"],)).fetchone()
            if existing:
                stored = json.loads(existing["state"])
                if stored["snapshot_id"] != snapshot_id:
                    raise SnapshotError("job_id与已提交内容不一致")
                return snapshot_id
            current = connection.execute("SELECT s.end_date,o.observed_at FROM current_snapshot c JOIN snapshots s ON s.id=c.snapshot_id JOIN observations o ON o.id=c.observation_id").fetchone()
            connection.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?)", (snapshot_id, days[-1], observation_id))
            inserted = connection.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?)", (observation_id, snapshot_id, receipt["observed_at"], canonical(receipt).decode())).rowcount
            if inserted and (current is None or (days[-1] >= current["end_date"] and receipt["observed_at"] >= current["observed_at"])):
                connection.execute("INSERT OR REPLACE INTO current_snapshot VALUES (1,?,?)", (snapshot_id, observation_id))
            completed = {**state, "stage": "completed", "snapshot_id": snapshot_id, "observation_id": observation_id,
                         "finished_at": receipt["observed_at"], "last_success_at": receipt["observed_at"]}
            connection.execute("INSERT INTO committed_jobs VALUES (?,?,?)", (state["job_id"], snapshot_id, canonical(completed).decode()))
            if checkpoint:
                checkpoint("before_commit")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    _sync_directory(root)
    if checkpoint:
        checkpoint("after_commit")
    return snapshot_id


def committed_job(parent: Path, job_id: str | None) -> dict | None:
    """只读查询提交结果；未提交job不因状态文件而推定成功。"""
    root = index_root(parent)
    if not job_id or not safe_path(root / "index.sqlite").exists():
        return None
    with _connection(root) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "committed_jobs" not in tables:
            return None
        row = connection.execute("SELECT snapshot_id,state FROM committed_jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        return None
    state = json.loads(row["state"])
    if state.get("job_id") != job_id or state.get("snapshot_id") != row["snapshot_id"] or state.get("stage") != "completed":
        raise SnapshotError("指数job提交标识不一致")
    return state


def read_snapshot(parent: Path, snapshot_id: str | None = None) -> dict | None:
    """只读完整固定视图，证据观察始终绑定快照首次成功发布。

    每次重建双源契约校验清单与原件；损坏时明确报错，绝不静默换版本。
    """
    if snapshot_id is not None:
        validate_id(snapshot_id)
    root = index_root(parent)
    if not safe_path(root / "index.sqlite").exists():
        return None
    with _connection(root) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "snapshots" not in tables:
            return None
        if snapshot_id is None:
            row = connection.execute("SELECT snapshot_id,observation_id FROM current_snapshot WHERE singleton=1").fetchone()
            if row is None:
                return None
            snapshot_id = row[0]
            current_observation = connection.execute("SELECT snapshot_id,receipt,observed_at FROM observations WHERE id=?", (row["observation_id"],)).fetchone()
            if current_observation is None or current_observation["snapshot_id"] != snapshot_id:
                raise SnapshotError("指数当前观察关联损坏")
            current_receipt = json.loads(current_observation["receipt"])
            if digest(canonical(current_receipt)) != row["observation_id"] or current_receipt.get("snapshot_id") != snapshot_id or current_receipt.get("observed_at") != current_observation["observed_at"]:
                raise SnapshotError("指数当前观察身份损坏")
        row = connection.execute("SELECT * FROM snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if row is None:
            if connection.execute("SELECT 1 FROM current_snapshot WHERE snapshot_id=?", (snapshot_id,)).fetchone():
                raise SnapshotError("指数当前指针未引用完整快照")
            return None
        observation = connection.execute("SELECT snapshot_id,receipt FROM observations WHERE id=?", (row["first_observation"],)).fetchone()
        if observation is None or observation["snapshot_id"] != snapshot_id:
            raise SnapshotError("指数首次观察关联损坏")
    manifest = json.loads(read_object(root, snapshot_id))
    receipt = json.loads(observation["receipt"])
    if digest(canonical(receipt)) != row["first_observation"] or receipt["snapshot_id"] != snapshot_id:
        raise SnapshotError("指数观察身份损坏")
    originals = tuple(Original(item["source"], read_object(root, item["object_id"]), item["started_at"], item["completed_at"]) for item in receipt["sources"])
    version = manifest.get("source_contract", {}).get("version")
    if tuple(item.source for item in originals) != contract_sources(version) or build_manifest(tuple(manifest["calendar_dates"]), originals, contract_version=version) != manifest:
        raise SnapshotError("指数快照清单契约不一致")
    if _observation(snapshot_id, originals, tuple(manifest["calendar_dates"])) != receipt or row["end_date"] != manifest["window"]["end"]:
        raise SnapshotError("指数观察/截止日不一致")
    return {**manifest, "snapshot_id": snapshot_id, "observation_id": row["first_observation"], "retrieval": receipt}


def read_evidence(parent: Path, snapshot_id: str, object_id: str) -> dict:
    """仅提供指定快照成员原件的安全文本和逐日定位，不执行HTML或出站。"""
    validate_id(snapshot_id)
    validate_id(object_id)
    snapshot = read_snapshot(parent, snapshot_id)
    if snapshot is None:
        raise SnapshotError("index_evidence_not_found: 快照不存在")
    evidence = next((item for item in snapshot["evidence"] if item["object_id"] == object_id), None)
    if evidence is None:
        raise SnapshotError("index_evidence_not_found: 对象不属于此快照")
    original = read_object(index_root(parent), object_id)
    receipt = next(item for item in snapshot["retrieval"]["sources"] if item["object_id"] == object_id)
    return {"snapshot_id": snapshot_id, "observation_id": snapshot["observation_id"], **evidence,
            "retrieval": receipt, "verification": "260日×4个OHLC精确一致", "unused_fields": snapshot["source_contract"]["unused_fields"],
            "text_preview": original[:4096].decode("utf-8", errors="replace"), "preview_truncated": len(original) > 4096}
