"""沪深300手动更新编排、有限网络、账本和提交恢复；GET不写磁盘。"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pmi.index_calendar import complete_window
from pmi.index_contract import Original, SOURCES, Source, SourceNotReady, build_manifest, canonical, source_url
from pmi.index_snapshot import (atomic_json, committed_job, index_root, publish, read_snapshot,
                                safe_path, write_object)
from pmi.snapshot import SnapshotError
from pmi.writer_lock import writer_lock

# 旧东财阶段仅用于重启/状态恢复，新编排只遍历当前SOURCES。
ACTIVE = {"preparing", "fetching_eastmoney", "fetching_tencent", "fetching_csindex", "validating", "publishing"}
_LOGGER = logging.getLogger(__name__)
_MUTEX = threading.Lock()
_FETCH_DEADLINE_SECONDS = 45


def _read_state(parent: Path) -> dict:
    path = safe_path(index_root(parent) / "update-status.json")
    if not path.exists():
        return {"stage": "idle", "last_success_at": None}
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or value.get("stage") not in ACTIVE | {"idle", "completed", "failed", "interrupted"}:
        raise SnapshotError("index_update_status_invalid: 非法本地任务状态")
    return value


def _save_state(parent: Path, state: dict) -> None:
    atomic_json(index_root(parent) / "update-status.json", state)


def _writer_active(parent: Path) -> bool:
    path = safe_path(parent / ".writer.lock")
    if not path.exists():
        return False
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return False


def update_status(parent: Path) -> dict:
    """只读状态/提交标识推导恢复，启动和GET不持久化、不联网。"""
    state = _read_state(parent)
    if state["stage"] not in ACTIVE or _writer_active(safe_path(parent)):
        return state
    committed = committed_job(parent, state.get("job_id"))
    if committed:
        read_snapshot(parent, committed["snapshot_id"])
        return {**committed, "message": "已从本地job提交标识核实成功"}
    return {**state, "stage": "interrupted", "result": "interrupted", "message": "上次更新中断，旧数据仍可读取，可手动重试"}


def classify_change(previous: dict | None, manifest: dict) -> tuple[str, list[str], list[str]]:
    """比较业务四值及原件，窗口前滚只记录新增/修订，不删除历史。"""
    old = {bar["trade_date"]: {field: bar[field] for field in ("open", "high", "low", "close")} for bar in previous["bars"]} if previous else {}
    new = {bar["trade_date"]: {field: bar[field] for field in ("open", "high", "low", "close")} for bar in manifest["bars"]}
    added = sorted(new.keys() - old.keys())
    revised = sorted(day for day in new.keys() & old.keys() if new[day] != old[day])
    if old != new:
        return "business_changed", added, revised
    if previous and previous["evidence"] == manifest["evidence"] and previous["completion_basis"] == manifest["completion_basis"]:
        return "unchanged", [], []
    return "evidence_changed", [], []


def _ledger_path(parent: Path) -> Path:
    # 隔离实测可共用预算账本；正式产品仍只记录本子根账本，不受验证8job上限影响。
    configured = os.environ.get("WOLF_INDEX_BUDGET_LEDGER")
    return safe_path(Path(configured)) if configured else index_root(parent) / "network-ledger.jsonl"


def _record_attempt(parent: Path, entry: dict) -> None:
    """出站前持久化尝试，失败/中断同样计数；隔离验证共用8job/12次/64MiB预算。

    八job为2026-10-06腾讯换源追加后的授权；沿用旧账本，不重置历史尝试。
    """
    path = _ledger_path(parent)
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        lines = [json.loads(line) for line in stream if line.strip()]
        if entry["event"] == "attempt" and os.environ.get("WOLF_INDEX_BUDGET_LEDGER"):
            attempts = [line for line in lines if line["event"] == "attempt"]
            jobs = {line["job_id"] for line in attempts}
            # 未完成尝试按整个8MiB预留，防止中断后低估正文预算。
            completed = {line["attempt_id"]: line["bytes"] for line in lines if line["event"] == "finished"}
            used = sum(completed.get(line["attempt_id"], 8 * 1024 * 1024) for line in attempts)
            if len(attempts) >= 12 or len(jobs | {entry["job_id"]}) > 8 or used + 8 * 1024 * 1024 > 64 * 1024 * 1024:
                raise SnapshotError("受控真实出站预算不足，停止请求")
        stream.seek(0, 2)
        stream.write(canonical(entry).decode() + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def fetch_bounded(parent: Path, source: Source, days: tuple[str, ...], job_id: str) -> Original:
    """每源单次子进程45秒硬截止，父消失关闭管道即退出；失败保留计数。

    主机冷却至少5秒，冷却在父根锁内；不绕过代理/TLS或重试。
    """
    if source not in SOURCES:
        raise SnapshotError("来源只读或未准入，禁止新增出站")
    ledger = _ledger_path(parent)
    if ledger.exists():
        entries = [json.loads(line) for line in ledger.read_text().splitlines()]
        previous = [line for line in entries if line["event"] == "attempt" and line["source"] == source]
        if previous:
            elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(previous[-1]["started_at"])).total_seconds()
            if elapsed < 5:
                time.sleep(5 - elapsed)
    started_at = datetime.now(timezone.utc).isoformat()
    attempt_id = uuid.uuid4().hex
    _record_attempt(parent, {"event": "attempt", "job_id": job_id, "attempt_id": attempt_id, "source": source,
                             "url": source_url(source, days), "started_at": started_at})
    success = False
    bytes_read = 0
    with tempfile.TemporaryDirectory(prefix="thewolf-index-fetch-") as directory:
        process = None
        try:
            process = subprocess.Popen([sys.executable, "-m", "pmi.index_fetch", "--source", source,
                                        "--start", days[0], "--end", days[-1], "--output", directory],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                process.wait(timeout=_FETCH_DEADLINE_SECONDS)
            except subprocess.TimeoutExpired as error:
                raise SnapshotError("来源45秒硬截止，旧快照保留") from error
            if process.returncode != 0:
                failure = Path(directory) / "failure.json"
                raise SnapshotError(json.loads(failure.read_text())["message"] if failure.exists() else "来源获取子进程中断")
            receipt = json.loads(Path(directory, "receipt.json").read_text())
            content = Path(directory, "original").read_bytes()
            if len(content) > 8 * 1024 * 1024:
                raise SnapshotError("来源正文超过8MiB")
            success = True
            return Original(source, content, started_at, receipt["completed_at"])
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
                if process.stdin:
                    process.stdin.close()
            receipt_path = Path(directory, "receipt.json")
            try:
                bytes_read = json.loads(receipt_path.read_text())["bytes"] if receipt_path.exists() else 0
            except (ValueError, KeyError):
                bytes_read = 8 * 1024 * 1024
            _record_attempt(parent, {"event": "finished", "job_id": job_id, "attempt_id": attempt_id,
                                     "source": source, "success": success, "bytes": bytes_read,
                                     "finished_at": datetime.now(timezone.utc).isoformat()})


def perform_update(parent: Path, state: dict, days: tuple[str, ...],
                   fetch: Callable[[Path, Source, tuple[str, ...], str], Original] = fetch_bounded,
                   checkpoint: Callable[[str], None] | None = None) -> dict:
    """持父根锁完成双源获取和发布；失败保留旧指针，提交后由job记录恢复。"""
    try:
        previous = read_snapshot(parent)
        if previous and days[-1] < previous["window"]["end"]:
            raise SnapshotError("stale_window: 不能回退完整截止日")
        state["previous_snapshot_id"] = previous["snapshot_id"] if previous else None
        originals = []
        for source in SOURCES:
            state["stage"] = "fetching_" + source
            _save_state(parent, state)
            original = fetch(parent, source, days, state["job_id"])
            originals.append(original)
            object_id = write_object(index_root(parent), original.content)
            receipt_path = safe_path(index_root(parent) / "original-observations.jsonl")
            with receipt_path.open("ab") as stream:
                stream.write(canonical({"job_id": state["job_id"], "source": source, "url": source_url(source, days),
                                        "object_id": object_id, "started_at": original.started_at,
                                        "completed_at": original.completed_at, "published_at": None}) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        state["stage"] = "validating"
        _save_state(parent, state)
        manifest = build_manifest(days, tuple(originals))
        result, added, revised = classify_change(previous, manifest)
        state.update(stage="publishing", result=result, added_dates=added, revised_dates=revised,
                     message={"business_changed": "价格数据已更新", "evidence_changed": "四值无变化，仅依据更新", "unchanged": "检查成功，价格与依据无变化"}[result])
        _save_state(parent, state)
        publish(parent, manifest, tuple(originals), state, checkpoint)
        state = committed_job(parent, state["job_id"])
        if checkpoint:
            checkpoint("before_status")
        _save_state(parent, state)
    except (SnapshotError, ValueError, OSError, sqlite3.Error) as error:
        _LOGGER.error("index update failed; job=%s stage=%s error_type=%s", state["job_id"], state["stage"], type(error).__name__)
        committed = committed_job(parent, state["job_id"])
        if committed:
            return {**committed, "message": "提交成功，状态可由本地job标识恢复"}
        ready = isinstance(error, SourceNotReady)
        state.update(stage="completed" if ready else "failed", result="source_not_ready" if ready else "failed",
                     message=str(error) if isinstance(error, SnapshotError) else f"本地更新失败（{type(error).__name__}），旧数据保留",
                     finished_at=datetime.now(timezone.utc).isoformat())
        _save_state(parent, state)
    return state


def start_update(parent: Path, now: datetime | None = None,
                 fetch: Callable = fetch_bounded) -> dict:
    """联网前冻结完整目标并获取父根锁；争用409，空根也可首轮手动获取。"""
    with _MUTEX:
        parent = safe_path(parent)
        root = index_root(parent)
        days = complete_window(now or datetime.now(timezone.utc))
        lock = writer_lock(parent)
        lock.__enter__()
        try:
            previous_state = _read_state(parent)
            if previous_state["stage"] in ACTIVE:
                previous_state = committed_job(parent, previous_state.get("job_id")) or previous_state
            previous = read_snapshot(parent)
            if previous and days[-1] < previous["window"]["end"]:
                raise SnapshotError("stale_window: 不能回退完整截止日")
            root.mkdir(parents=True, exist_ok=True)
            state = {"job_id": uuid.uuid4().hex, "stage": "preparing", "result": None,
                     "started_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
                     "target_start": days[0], "target_end": days[-1], "last_success_at": previous_state.get("last_success_at"),
                     "message": "正在准备沪深300完整260日窗口", "added_dates": [], "revised_dates": []}
            _save_state(parent, state)
            initial = dict(state)
            def worker() -> None:
                try:
                    perform_update(parent, state, days, fetch)
                finally:
                    lock.__exit__(None, None, None)
            threading.Thread(target=worker, daemon=True).start()
        except BaseException:
            lock.__exit__(None, None, None)
            raise
        return initial
