"""以来源中立的不可变快照保存首个单证券切片。

调用方提供已核验的来源元数据和交易日历；本模块不推定开市日、公告时刻或来源权限。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterator, Optional
from zoneinfo import ZoneInfo


_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SnapshotError(ValueError):
    """待发布或已保存的快照不符合切片契约。"""


@dataclass(frozen=True)
class DailyBar:
    """以十进制字符串保存一日未复权价格、股数和人民币成交额。"""

    trade_date: str
    open_cny: str
    high_cny: str
    low_cny: str
    close_cny: str
    volume_shares: str
    amount_cny: str


@dataclass(frozen=True)
class DocumentEvidence:
    """关联公告来源、发布时间精度、物理页码与原文片段。"""

    document_id: str
    title: str
    issuer_name: str
    source_url: str
    published_at: Optional[str]
    publication_precision: str
    physical_page: int
    evidence_text: str


@dataclass(frozen=True)
class MarketContract:
    """记录行情来源、证券映射、原始单位及标准化版本。"""

    source_url: str
    raw_publisher: str
    transport_id: str
    source_symbol: str
    trading_scope: str
    price_resolution: str
    volume_resolution: str
    amount_resolution: str
    verification_source_url: str
    currency: str
    adjustment: str
    raw_price_unit: str
    raw_volume_unit: str
    raw_amount_unit: str
    normalization_version: str


@dataclass(frozen=True)
class SliceInput:
    """描述一次待发布切片；追加公告须提供对应的独立 PDF 原件。"""

    instrument_code: str
    instrument_name: str
    exchange: str
    source_id: str
    source_version: str
    source_policy_version: str
    batch_id: str
    market_contract: MarketContract
    retrieved_at: str
    complete_through_date: str
    completion_basis: str
    calendar_dates: tuple[str, ...]
    bars: tuple[DailyBar, ...]
    document: DocumentEvidence
    raw_response: bytes
    verification_response: bytes
    pdf_bytes: bytes
    additional_documents: tuple[DocumentEvidence, ...] = ()
    additional_pdf_bytes: tuple[bytes, ...] = ()


def _utc_timestamp(value: str) -> str:
    """要求来源时刻携带时区，并统一为 UTC 保存。"""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise SnapshotError("invalid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _calendar_day(value: str) -> date:
    """要求交易日与日期精度公告使用规范的 YYYY-MM-DD。"""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise SnapshotError("invalid calendar or trade date") from error
    if parsed.isoformat() != value:
        raise SnapshotError("dates must use YYYY-MM-DD")
    return parsed


def _number(value: str, label: str) -> Decimal:
    """将非负十进制字符串转为精确数值，拒绝浮点形式与非有限值。"""
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise SnapshotError(f"{label} must be a nonnegative decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise SnapshotError(f"invalid {label}") from error
    if not result.is_finite():
        raise SnapshotError(f"non-finite {label}")
    return result


def _validate(payload: SliceInput) -> None:
    """校验证券、交易日、未复权数值及每份公告的时间和原件契约。"""
    if payload.instrument_code != "002245" or payload.exchange != "SZSE":
        raise SnapshotError("this slice accepts only verified 002245 / SZSE")
    if not all((payload.instrument_name, payload.source_id, payload.source_version,
                payload.source_policy_version, payload.batch_id)):
        raise SnapshotError("instrument and source identity are required")
    contract = payload.market_contract
    if contract.currency != "CNY" or contract.adjustment != "none":
        raise SnapshotError("slice requires CNY unadjusted daily bars")
    if not all((contract.source_url, contract.raw_publisher,
                contract.transport_id, contract.source_symbol, contract.trading_scope,
                contract.price_resolution, contract.volume_resolution,
                contract.amount_resolution, contract.verification_source_url,
                contract.raw_price_unit,
                contract.raw_volume_unit, contract.raw_amount_unit,
                contract.normalization_version)):
        raise SnapshotError("source mapping, scope, units and conversion version are required")
    _utc_timestamp(payload.retrieved_at)
    if not payload.calendar_dates or len(payload.calendar_dates) > 60:
        raise SnapshotError("calendar must contain 1 to 60 open sessions")
    calendar = [_calendar_day(day) for day in payload.calendar_dates]
    if calendar != sorted(set(calendar)):
        raise SnapshotError("calendar must be sorted and unique")
    if not payload.completion_basis or calendar[-1] > _calendar_day(payload.complete_through_date):
        raise SnapshotError("calendar exceeds verified complete-through date")
    observed: set[str] = set()
    for bar in payload.bars:
        if bar.trade_date not in payload.calendar_dates or bar.trade_date in observed:
            raise SnapshotError("bar date is outside calendar or repeated")
        observed.add(bar.trade_date)
        low = _number(bar.low_cny, "low")
        high = _number(bar.high_cny, "high")
        opening = _number(bar.open_cny, "open")
        closing = _number(bar.close_cny, "close")
        if low <= 0 or not low <= opening <= high or not low <= closing <= high:
            raise SnapshotError("invalid OHLC relationship")
        volume = _number(bar.volume_shares, "volume_shares")
        if volume != volume.to_integral_value():
            raise SnapshotError("volume_shares must be a whole share count")
        _number(bar.amount_cny, "amount_cny")
    if len(payload.additional_documents) != len(payload.additional_pdf_bytes):
        raise SnapshotError("document and PDF counts differ")
    documents = (payload.document,) + payload.additional_documents
    if len({item.document_id for item in documents}) != len(documents):
        raise SnapshotError("document IDs must be unique")
    for document in documents:
        if not all((document.document_id, document.title, document.issuer_name,
                    document.source_url, document.evidence_text)):
            raise SnapshotError("document identity and evidence are required")
        if document.physical_page < 1 or document.publication_precision not in {
            "second", "minute", "date", "unknown"
        }:
            raise SnapshotError("invalid document page or publication precision")
        if document.published_at:
            if document.publication_precision == "unknown":
                raise SnapshotError("unknown precision cannot have published_at")
            if document.publication_precision == "date":
                _calendar_day(document.published_at)
            else:
                _utc_timestamp(document.published_at)
        elif document.publication_precision != "unknown":
            raise SnapshotError("unknown publication time requires unknown precision")
    if not payload.raw_response or not payload.verification_response or \
            not all(item.startswith(b"%PDF-") for item in
                    (payload.pdf_bytes,) + payload.additional_pdf_bytes):
        raise SnapshotError("raw market, verification and PDF originals are required")


def _canonical_bytes(value: dict) -> bytes:
    """稳定序列化清单，使相同事实与原件得到相同快照 ID。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _objects_directory(root: Path, create: bool) -> Path:
    """限制对象目录位于数据根内，拒绝符号链接跳出隔离目录。"""
    directory = root / "objects"
    if directory.is_symlink():
        raise SnapshotError("object directory must not be a symlink")
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    if directory.exists() and directory.resolve().parent != root.resolve():
        raise SnapshotError("object directory escapes data root")
    return directory


def _write_object(root: Path, content: bytes) -> str:
    """先持久化哈希命名的原件；已存在对象必须通过哈希校验。"""
    object_id = _digest(content)
    directory = _objects_directory(root, create=True)
    destination = directory / object_id
    if destination.exists():
        _read_object(root, object_id)
        return object_id
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return object_id


def _read_object(root: Path, object_id: str) -> bytes:
    """按哈希读取不可变对象，拒绝缺失、符号链接及内容损坏。"""
    if not _SHA256.fullmatch(object_id):
        raise SnapshotError("invalid object ID")
    path = _objects_directory(root, create=False) / object_id
    if path.is_symlink() or not path.is_file():
        raise SnapshotError("snapshot object is missing or unsafe")
    content = path.read_bytes()
    if _digest(content) != object_id:
        raise SnapshotError("snapshot object hash mismatch")
    return content


def _public_available_at(document: dict, first_seen_at: str) -> str:
    """按公告时间精度计算保守可用时刻；未知时使用首次获取时刻。"""
    if document["publication_precision"] == "date":
        # 只有发布日期时，不假定公告在当天任一盘中时刻已可见。
        next_day = date.fromisoformat(document["published_at"]) + timedelta(days=1)
        available = datetime.combine(next_day, datetime.min.time(),
                                     ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc)
    elif document["published_at"]:
        available = datetime.fromisoformat(document["published_at"]).astimezone(timezone.utc)
    else:
        available = datetime.fromisoformat(first_seen_at)
    return available.isoformat()


@contextmanager
def _connect(root: Path) -> Iterator[sqlite3.Connection]:
    """提供发布事务，失败时回滚数据库指针；已落盘的孤儿对象保持不可变。"""
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "slice.sqlite", timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = FULL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id TEXT PRIMARY KEY,
            manifest_object_id TEXT NOT NULL,
            raw_object_id TEXT NOT NULL,
            pdf_object_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS current_snapshot (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id)
        );
    """)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _ensure_observation_schema(connection: sqlite3.Connection) -> None:
    """仅在发布事务内追加观察索引；读取旧快照不迁移数据库。"""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_observations (
            observation_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
            observed_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            time_basis TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS current_observation (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            observation_id TEXT NOT NULL REFERENCES snapshot_observations(observation_id)
        )
    """)


def publish_snapshot(root: Path, payload: SliceInput,
                     checkpoint: Optional[Callable[[str], None]] = None) -> str:
    """原件全部持久化后，原子发布清单及当前快照指针。

    清单 ID 表示内容；清单 ID 与获取时刻共同标识一次观察。同一观察重试幂等，
    较晚观察可重新指向旧内容，较早观察不回退当前指针。旧库首次发布时以已有
    当前快照的首次获取时刻建立观察锚点，不改写旧快照。数据库提交前失败可能留下
    未引用对象，但不会暴露半成品快照。
    """
    _validate(payload)
    raw_id = _write_object(root, payload.raw_response)
    if checkpoint:
        checkpoint("raw_written")
    verification_id = _write_object(root, payload.verification_response)
    pdf_id = _write_object(root, payload.pdf_bytes)
    additional_pdf_ids = tuple(_write_object(root, content)
                               for content in payload.additional_pdf_bytes)
    documents = (payload.document,) + payload.additional_documents
    pdf_ids = (pdf_id,) + additional_pdf_ids
    manifest = {
        "contract_version": 4,
        "instrument_code": payload.instrument_code,
        "instrument_name": payload.instrument_name,
        "exchange": payload.exchange,
        "source_id": payload.source_id,
        "source_version": payload.source_version,
        "source_policy_version": payload.source_policy_version,
        "batch_id": payload.batch_id,
        "market_contract": payload.market_contract.__dict__,
        "complete_through_date": payload.complete_through_date,
        "completion_basis": payload.completion_basis,
        "pit_grade": "latest_only",
        "calendar_dates": list(payload.calendar_dates),
        "bars": [bar.__dict__ for bar in payload.bars],
        "document": payload.document.__dict__,
        "documents": [{**document.__dict__, "pdf_object_id": object_id}
                      for document, object_id in zip(documents, pdf_ids)],
        "raw_object_id": raw_id,
        "verification_object_id": verification_id,
        "pdf_object_id": pdf_id,
    }
    manifest_id = _write_object(root, _canonical_bytes(manifest))
    if checkpoint:
        checkpoint("objects_ready")
    now = datetime.now(timezone.utc).isoformat()
    observed_at = _utc_timestamp(payload.retrieved_at)
    observation_id = _digest(_canonical_bytes({
        "snapshot_id": manifest_id, "observed_at": observed_at,
    }))
    with _connect(root) as connection:
        connection.execute("BEGIN IMMEDIATE")
        _ensure_observation_schema(connection)
        connection.execute("""
            INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?, ?, ?)
        """, (manifest_id, manifest_id, raw_id, pdf_id,
              observed_at, now))
        current = connection.execute("""
            SELECT c.snapshot_id, s.first_seen_at, o.observation_id, o.observed_at,
                   o.snapshot_id AS observed_snapshot_id
            FROM current_snapshot c JOIN snapshots s ON s.snapshot_id = c.snapshot_id
            LEFT JOIN current_observation co ON co.singleton = c.singleton
            LEFT JOIN snapshot_observations o ON o.observation_id = co.observation_id
            WHERE c.singleton = 1
        """).fetchone()
        if current is not None and current["observation_id"] is None:
            # 旧库只有内容指针；以其原始 first_seen_at 建立一次性顺序锚点。
            legacy_at = current["first_seen_at"]
            legacy_id = _digest(_canonical_bytes({
                "snapshot_id": current["snapshot_id"], "observed_at": legacy_at,
            }))
            connection.execute("""
                INSERT OR IGNORE INTO snapshot_observations VALUES (?, ?, ?, ?, ?)
            """, (legacy_id, current["snapshot_id"], legacy_at, now,
                  "legacy_snapshot_first_seen"))
            connection.execute("INSERT INTO current_observation VALUES (1, ?)",
                               (legacy_id,))
            current_at = legacy_at
        elif current is not None:
            if current["snapshot_id"] != current["observed_snapshot_id"]:
                raise SnapshotError("current snapshot and observation disagree")
            current_at = current["observed_at"]
        else:
            current_at = None
        inserted_observation = connection.execute("""
            INSERT OR IGNORE INTO snapshot_observations VALUES (?, ?, ?, ?, ?)
        """, (observation_id, manifest_id, observed_at, now,
              "payload_retrieved_at")).rowcount == 1
        # 相同时刻的不同新观察按首次入库顺序前进；已有观察的重试不改变指针。
        if current_at is None or (inserted_observation and
                                  datetime.fromisoformat(observed_at) >=
                                  datetime.fromisoformat(current_at)):
            connection.execute("""
                INSERT INTO current_snapshot VALUES (1, ?)
                ON CONFLICT(singleton) DO UPDATE SET snapshot_id = excluded.snapshot_id
            """, (manifest_id,))
            connection.execute("""
                INSERT INTO current_observation VALUES (1, ?)
                ON CONFLICT(singleton) DO UPDATE SET observation_id = excluded.observation_id
            """, (observation_id,))
        if checkpoint:
            checkpoint("manifest_uncommitted")
    if checkpoint:
        checkpoint("committed")
    return manifest_id


def read_snapshot(root: Path, snapshot_id: Optional[str] = None) -> Optional[dict]:
    """读取当前或指定的已提交快照，并校验全部引用原件。

    旧单公告清单按只读兼容形式返回；未知缺口来自日历与已观察日期之差，
    不推断停牌或填零。
    """
    with _connect(root) as connection:
        if snapshot_id is None:
            row = connection.execute("""
                SELECT s.* FROM snapshots s JOIN current_snapshot c
                ON c.snapshot_id = s.snapshot_id WHERE c.singleton = 1
            """).fetchone()
        else:
            if not _SHA256.fullmatch(snapshot_id):
                raise SnapshotError("invalid snapshot ID")
            row = connection.execute("SELECT * FROM snapshots WHERE snapshot_id = ?",
                                     (snapshot_id,)).fetchone()
    if row is None:
        return None
    if (row["snapshot_id"] != row["manifest_object_id"] or
            (snapshot_id is not None and row["snapshot_id"] != snapshot_id)):
        raise SnapshotError("snapshot identity and manifest disagree")
    manifest = json.loads(_read_object(root, row["manifest_object_id"]))
    if (manifest["raw_object_id"] != row["raw_object_id"] or
            manifest["pdf_object_id"] != row["pdf_object_id"]):
        raise SnapshotError("manifest and database disagree")
    _read_object(root, row["raw_object_id"])
    if manifest.get("verification_object_id"):
        _read_object(root, manifest["verification_object_id"])
    _read_object(root, row["pdf_object_id"])
    documents = manifest.get("documents")
    if documents is None:
        documents = [{**manifest["document"], "pdf_object_id": row["pdf_object_id"]}]
    if not isinstance(documents, list) or not documents or \
            documents[0]["pdf_object_id"] != row["pdf_object_id"] or \
            {key: value for key, value in documents[0].items()
             if key != "pdf_object_id"} != manifest["document"]:
        raise SnapshotError("document list and primary original disagree")
    for document in documents:
        _read_object(root, document["pdf_object_id"])
    documents = [{**item, "public_available_at":
                  _public_available_at(item, row["first_seen_at"])}
                 for item in documents]
    return {**manifest, "documents": documents,
            "snapshot_id": row["snapshot_id"],
            "first_seen_at": row["first_seen_at"],
            "recorded_at": row["recorded_at"],
            "document_public_available_at": documents[0]["public_available_at"],
            "observed_count": len(manifest["bars"]),
            "open_session_count": len(manifest["calendar_dates"]),
            "unknown_missing_dates": sorted(set(manifest["calendar_dates"]) -
                                            {bar["trade_date"] for bar in manifest["bars"]})}


def read_pdf(root: Path, snapshot_id: str, object_id: str) -> bytes:
    """仅返回指定固定快照实际引用的 PDF，阻止跨版本原件串用。"""
    snapshot = read_snapshot(root, snapshot_id)
    if snapshot is None or object_id not in {
        document["pdf_object_id"] for document in snapshot["documents"]
    }:
        raise SnapshotError("PDF object is not in the requested snapshot")
    return _read_object(root, object_id)
