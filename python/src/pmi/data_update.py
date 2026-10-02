"""手动更新单证券完整窗口，保留公告依据和全部旧快照。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import requests

from pmi.sina_slice import (FORMAL_PDF_SHA256, PDF_SHA256, SINA_URL, SZSE_PARAMS,
                            SZSE_URL, _daily_bars, _decode_sina,
                            _official_rows, _record_observation)
from pmi.snapshot import (DocumentEvidence, MarketContract, SliceInput, SnapshotError,
                          _write_object, publish_snapshot, read_pdf, read_snapshot)
from pmi.trading_calendar import complete_window, completion_basis
from pmi.writer_lock import writer_lock


_LOGGER = logging.getLogger(__name__)
_ACTIVE = {"preparing", "fetching_sina", "fetching_szse", "validating", "publishing"}
_STATUS_FILE = "update-status.json"
_STATE_MUTEX = threading.Lock()


def _fetch_bounded(url: str, params: Optional[dict[str, str]] = None,
                   receipt_root: Optional[Path] = None) -> bytes:
    """独立子进程获取固定来源，45 秒硬截止后回收；父进程消失即停止。

    子进程不写数据根。成功后父写入者归档逐原件真实完成凭据；无自动重试。
    每源至多 45 秒运行及两次 1 秒退出等待，不依赖慢速 HTTP 响应及时返回。
    """
    if (url, params) not in ((SINA_URL, None), (SZSE_URL, SZSE_PARAMS)):
        raise SnapshotError("unapproved update source")
    with tempfile.TemporaryDirectory(prefix="thewolf-fetch-") as directory:
        process = subprocess.Popen([sys.executable, "-m", "pmi.source_fetch", "--source",
                                    "sina" if url == SINA_URL else "szse", "--output", directory],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            try:
                process.wait(timeout=45)
            except subprocess.TimeoutExpired as error:
                raise SnapshotError("source total deadline exceeded (45 seconds)") from error
            if process.returncode != 0:
                failure_path = Path(directory) / "failure.json"
                message = json.loads(failure_path.read_bytes())["message"] if failure_path.exists() else "source subprocess interrupted"
                raise SnapshotError(message)
            content = (Path(directory) / "original").read_bytes()
            receipt = json.loads((Path(directory) / "receipt.json").read_bytes())
            if receipt_root is not None:
                _record_observation(receipt_root, url, content, receipt["completed_at"])
            return content
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            if process.stdin is not None:
                process.stdin.close()


def _read_status(root: Path) -> dict:
    path = root / _STATUS_FILE
    if path.is_symlink():
        raise SnapshotError("unsafe update status file")
    if not path.exists():
        return {"stage": "idle", "last_success_at": None}
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or value.get("stage") not in _ACTIVE | {"idle", "completed", "failed", "interrupted"}:
        raise SnapshotError("invalid update status")
    return value


def _save_status(root: Path, state: dict) -> None:
    """在数据根锁内原子持久化检查状态；不写旧快照清单。"""
    descriptor, temporary = tempfile.mkstemp(prefix=".update-", dir=root)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / _STATUS_FILE)
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _recover_status(root: Path, state: dict) -> dict:
    """锁已释放的运行状态视为中断；按观察索引核实提交后的客户端失联。"""
    if state["stage"] not in _ACTIVE:
        return state
    committed_id = None
    if state.get("observed_at") and (root / "slice.sqlite").exists():
        with sqlite3.connect(root / "slice.sqlite") as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "snapshot_observations" in tables:
                row = connection.execute("SELECT snapshot_id FROM snapshot_observations WHERE observed_at=?",
                                         (state["observed_at"],)).fetchone()
                committed_id = row[0] if row else None
    if committed_id:
        read_snapshot(root, committed_id)
        state.update(stage="completed", snapshot_id=committed_id,
                     last_success_at=state["observed_at"], message="已从本地观察记录核实提交成功")
    else:
        state.update(stage="interrupted", result="interrupted", message="上次更新中断，旧数据仍可读取；可手动重试")
    _save_status(root, state)
    return state


def update_status(root: Path) -> dict:
    """只查询本地任务；释放锁的残留任务进行恢复核对，不抓取上游。"""
    state = _read_status(root)
    if state["stage"] not in _ACTIVE:
        return state
    with _STATE_MUTEX:
        try:
            with writer_lock(root):
                return _recover_status(root, _read_status(root))
        except SnapshotError as error:
            if str(error).startswith("writer_busy:"):
                return _read_status(root)
            raise


def _inherit_document(document: dict) -> DocumentEvidence:
    """沿用旧证据的保守可用时刻；无逐原件获取凭据则明确保持未知。"""
    return DocumentEvidence(
        **{name: document[name] for name in ("document_id", "title", "issuer_name", "source_url",
                                           "published_at", "publication_precision", "physical_page", "evidence_text")},
        inherited_public_available_at=document["public_available_at"],
        original_retrieved_at=document.get("original_retrieved_at"),
        original_retrieval_basis=document.get("original_retrieval_basis") or "unknown; inherited local evidence, no per-original receipt established")


def _validate_update_source(previous: dict) -> None:
    """只更新已验证新浪口径的 002245 切片，拒绝把其他来源单位继承给新浪事实。"""
    contract = previous["market_contract"]
    if (previous["instrument_code"] != "002245" or previous["exchange"] != "SZSE" or
            previous["source_id"] != "sina-finance-a-share-daily" or
            any(contract.get(key) != value for key, value in {
                "source_url": SINA_URL, "verification_source_url": SZSE_URL,
                "source_symbol": "sz002245", "currency": "CNY", "adjustment": "none",
                "raw_price_unit": "CNY/share", "raw_volume_unit": "share", "raw_amount_unit": "CNY"}.items())):
        raise SnapshotError("当前快照不符合已核验的新浪 002245 单位与来源契约")


def prepare_update(root: Path, previous: dict, sina_raw: bytes, official_raw: bytes,
                   observed_at: str, calendar_dates: tuple[str, ...]) -> SliceInput:
    """核验完整双源窗口并复用本地两份公告，拒绝缺日、冲突和陈旧窗口。

    旧公告获取时间未知时不使用行情新观察时间补造；固定视图保持可读。
    """
    _validate_update_source(previous)
    if len(calendar_dates) != 60 or list(calendar_dates) != sorted(set(calendar_dates)):
        raise SnapshotError("更新窗口必须是 60 个唯一且递增的已核验开市日")
    if calendar_dates[-1] < previous["complete_through_date"]:
        raise SnapshotError("stale_window: 更新不能回退当前行情截止日")
    documents = previous["documents"]
    if len(documents) != 2 or [item["pdf_object_id"] for item in documents] != [PDF_SHA256, FORMAL_PDF_SHA256]:
        raise SnapshotError("更新需要两份已验证本地公告，请先准备完整切片")
    pdfs = [read_pdf(root, previous["snapshot_id"], item["pdf_object_id"]) for item in documents]
    name, official_rows = _official_rows(official_raw, calendar_dates)
    bars = _daily_bars(_decode_sina(sina_raw, calendar_dates), official_rows, calendar_dates)
    # 复用已验证清单的来源口径，不在更新模块另维护一套金融单位定义。
    with_metadata = replace(_legacy_template(previous, pdfs, observed_at),
                            instrument_name=name, bars=bars, calendar_dates=calendar_dates,
                            complete_through_date=calendar_dates[-1], completion_basis=completion_basis(),
                            raw_response=sina_raw, verification_response=official_raw,
                            source_version=f"observed-sha256:{hashlib.sha256(sina_raw).hexdigest()}",
                            batch_id=f"sina-002245-{calendar_dates[0]}-{calendar_dates[-1]}-{hashlib.sha256(sina_raw).hexdigest()[:16]}",
                            document=_inherit_document(documents[0]),
                            additional_documents=(_inherit_document(documents[1]),))
    return with_metadata


def _legacy_template(previous: dict, pdfs: list[bytes], observed_at: str) -> SliceInput:
    """从已验证清单复用来源契约，避免再次解码旧窗口或重新下载公告。"""
    return SliceInput(
        instrument_code="002245", instrument_name=previous["instrument_name"], exchange="SZSE",
        source_id=previous["source_id"], source_version=previous["source_version"],
        source_policy_version=previous["source_policy_version"], batch_id=previous["batch_id"],
        market_contract=MarketContract(**previous["market_contract"]), retrieved_at=observed_at,
        complete_through_date=previous["complete_through_date"], completion_basis=previous["completion_basis"],
        calendar_dates=tuple(previous["calendar_dates"]), bars=(),
        document=_inherit_document(previous["documents"][0]), raw_response=b"", verification_response=b"",
        pdf_bytes=pdfs[0], additional_documents=(_inherit_document(previous["documents"][1]),),
        additional_pdf_bytes=(pdfs[1],))


def classify_change(previous: dict, payload: SliceInput) -> str:
    """区分业务变化、仅原件/元数据证据变化及完全无变化，不伪报新增日。"""
    if list(payload.calendar_dates) != previous["calendar_dates"] or [bar.__dict__ for bar in payload.bars] != previous["bars"]:
        return "business_changed"
    if (hashlib.sha256(payload.raw_response).hexdigest() != previous["raw_object_id"] or
            hashlib.sha256(payload.verification_response).hexdigest() != previous["verification_object_id"] or
            previous["completion_basis"] != payload.completion_basis or
            previous["documents"][0].get("original_retrieval_basis") is None):
        return "evidence_changed"
    return "unchanged"


def _perform_update(root: Path, state: dict, fetch: Callable = _fetch_bounded,
                    now: Optional[datetime] = None,
                    checkpoint: Optional[Callable[[str], None]] = None) -> dict:
    """在调用者独占锁内执行一次有限采集，失败保持旧指针并留下诊断状态。

    每源仅一次请求，无自动重试；5/15 秒连接/读取超时、30 秒读取总预算和
    1 MB 上限沿用来源适配器，子进程每源另有 45 秒硬截止。
    轮询与恢复核对不增加来源请求。
    """
    try:
        previous = read_snapshot(root)
        if previous is None:
            raise SnapshotError("slice_empty: 请先准备两份公告的完整切片")
        _validate_update_source(previous)
        days = complete_window(now or datetime.now(timezone.utc))
        if days[-1] < previous["complete_through_date"]:
            raise SnapshotError("stale_window: 更新不能回退当前行情截止日")
        # 在联网前核实两份公告，空库或损坏的本地依据不浪费来源请求。
        if [item["pdf_object_id"] for item in previous["documents"]] != [PDF_SHA256, FORMAL_PDF_SHA256]:
            raise SnapshotError("更新需要两份已验证本地公告")
        state.update(stage="fetching_sina", target_start=days[0], target_end=days[-1], previous_snapshot_id=previous["snapshot_id"])
        _save_status(root, state)
        sina_raw = fetch(SINA_URL, receipt_root=root)
        _write_object(root, sina_raw)
        state["stage"] = "fetching_szse"
        _save_status(root, state)
        official_raw = fetch(SZSE_URL, SZSE_PARAMS, root)
        _write_object(root, official_raw)
        state["stage"] = "validating"
        _save_status(root, state)
        # 本次观察在两份行情读完后产生，不复用旧快照首次获取时刻。
        observed_at = datetime.now(timezone.utc).isoformat()
        payload = prepare_update(root, previous, sina_raw, official_raw, observed_at, days)
        result = classify_change(previous, payload)
        state.update(stage="publishing", result=result, observed_at=observed_at,
                     added_dates=sorted(set(days) - set(previous["calendar_dates"])),
                     removed_dates=sorted(set(previous["calendar_dates"]) - set(days)),
                     revised_dates=[bar.trade_date for bar in payload.bars
                                    if bar.trade_date in {row["trade_date"] for row in previous["bars"]}
                                    and bar.__dict__ != next(row for row in previous["bars"] if row["trade_date"] == bar.trade_date)])
        _save_status(root, state)
        snapshot_id = publish_snapshot(root, payload, checkpoint)
        state.update(stage="completed", snapshot_id=snapshot_id, last_success_at=observed_at,
                     message={"business_changed": "日线窗口或数值已更新", "evidence_changed": "日线无业务变化，仅来源证据更新", "unchanged": "检查成功，日线与来源证据无变化"}[result])
        _save_status(root, state)
    except (SnapshotError, requests.RequestException, OSError, sqlite3.Error, ValueError) as error:
        _LOGGER.error("002245 update failed; job=%s stage=%s error_type=%s", state["job_id"], state["stage"], type(error).__name__)
        # 提交后发生状态写入故障时保留 publishing，下一次本地查询可核对观察索引。
        if state.get("observed_at"):
            recovered = _recover_status(root, {**state, "stage": "publishing"})
            if recovered["stage"] == "completed":
                return recovered
        message = str(error) if isinstance(error, SnapshotError) else f"更新失败（{type(error).__name__}），旧数据保留"
        result = "source_not_ready" if "cover every expected" in message else "failed"
        state.update(stage="failed", result=result, message=message)
        _save_status(root, state)
    return state


def start_update(root: Path) -> dict:
    """启动后台有限更新；重复调用返回运行任务，CLI 竞争时明确忙碌。"""
    with _STATE_MUTEX:
        lock = writer_lock(root)
        try:
            lock.__enter__()
        except SnapshotError as error:
            if str(error).startswith("writer_busy:"):
                state = _read_status(root)
                if state["stage"] in _ACTIVE:
                    return state
            raise
        try:
            previous = _recover_status(root, _read_status(root))
            state = {"job_id": uuid.uuid4().hex, "stage": "preparing", "result": None,
                     "started_at": datetime.now(timezone.utc).isoformat(),
                     "last_success_at": previous.get("last_success_at"), "message": "正在准备更新"}
            _save_status(root, state)
            def worker() -> None:
                try:
                    _perform_update(root, state)
                finally:
                    lock.__exit__(None, None, None)
            threading.Thread(target=worker, daemon=True).start()
        except BaseException:
            lock.__exit__(None, None, None)
            raise
        return dict(state)
