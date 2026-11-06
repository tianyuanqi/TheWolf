"""指数单请求受控传输：父根持久预算、固定期限及父退出回收。"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from pmi.market_data.periodic_budget import Lease
from urllib.parse import urlsplit

from pmi.market_data import SnapshotError
from pmi.market_data.index_catalog import IndexDefinition, get_index
from pmi.market_data.index_history_calendar import FrozenWindow, complete_window
from pmi.market_data.index_series_contract import Original, canonical, source_url, utc
from pmi.market_data.index_series_store import append_record, load_json
from pmi.market_data.read_only import checked_path, read_bytes

MAX_RESPONSE_BYTES = 1024 * 1024
MIN_HOST_INTERVAL_SECONDS = 5
DEADLINE_SECONDS = 45
_FAILURE_CODES = frozenset({"source_http_rejected", "source_encoding_rejected", "source_length_rejected",
                            "source_incomplete_body", "source_body_limit", "source_network_error"})


@dataclass(frozen=True)
class NetworkBudget:
    """由可信门面冻结的父根累计预算；进程重启不清零。"""

    max_attempts: int = 16
    max_bytes: int = 16 * MAX_RESPONSE_BYTES
    lease: Lease | None = None

    def __post_init__(self) -> None:
        if (type(self.max_attempts) is not int or type(self.max_bytes) is not int
                or not 0 <= self.max_attempts <= 160 or not 0 <= self.max_bytes <= 160 * MAX_RESPONSE_BYTES):
            raise ValueError("invalid_index_network_budget")


class FetchInterrupted(SnapshotError):
    """所属 Runtime 停止；调用者不得开始下一个来源。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entries(parent: Path) -> list[dict]:
    path = checked_path(parent / "index-v2-network-ledger.jsonl")
    if not path.exists():
        return []
    content = read_bytes(path)
    if content and not content.endswith(b"\n"):
        raise SnapshotError("incomplete_network_ledger")
    return [load_json(line) for line in content.splitlines()]


def _totals(entries: list[dict]) -> tuple[dict[str, dict], dict[str, int]]:
    attempts: dict[str, dict] = {}
    settled: dict[str, int] = {}
    for entry in entries:
        try:
            attempt_id = entry["attempt_id"]
            if not isinstance(attempt_id, str) or not attempt_id:
                raise ValueError("id")
            if entry["event"] == "attempt":
                if attempt_id in attempts or entry["reserved_bytes"] != MAX_RESPONSE_BYTES:
                    raise ValueError("reservation")
                index = get_index(entry["index_id"])
                if entry["source"] not in index.sources or entry["host"] not in {"www.csindex.com.cn", "hq.cnindex.com.cn", "push2his.eastmoney.com"}:
                    raise ValueError("source")
                utc(entry["started_at"])
                attempts[attempt_id] = entry
            elif entry["event"] == "finished":
                prior = attempts[attempt_id]
                if attempt_id in settled or any(entry[key] != prior[key] for key in ("index_id", "source", "job_id")):
                    raise ValueError("settlement")
                count = entry["charged_bytes"]
                if type(count) is not int or not 0 <= count <= MAX_RESPONSE_BYTES or type(entry["success"]) is not bool:
                    raise ValueError("bytes")
                if not entry["success"] and count != MAX_RESPONSE_BYTES:
                    raise ValueError("failed_reservation")
                settled[attempt_id] = count
            else:
                raise ValueError("event")
        except (KeyError, TypeError, ValueError) as error:
            raise SnapshotError("invalid_network_ledger") from error
    return attempts, settled


def reserve(parent: Path, index: IndexDefinition, source: str, window: FrozenWindow, job_id: str,
            budget: NetworkBudget, stop: threading.Event) -> dict:
    """父 EX 锁内在出站前 fsync 一整响应预留，失败或中断均不返还。"""
    import uuid

    url = source_url(index, source, window)
    entries = _entries(parent)
    attempts, settled = _totals(entries)
    used = sum(settled.get(identifier, MAX_RESPONSE_BYTES) for identifier in attempts)
    if budget.lease is None and (len(attempts) >= budget.max_attempts or used + MAX_RESPONSE_BYTES > budget.max_bytes):
        raise SnapshotError("network_budget_exhausted")
    host = urlsplit(url).hostname
    same_host = [entry for entry in attempts.values() if entry["host"] == host]
    if same_host:
        stamp = datetime.fromisoformat(utc(same_host[-1]["started_at"]).replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - stamp).total_seconds()
        if elapsed < 0:
            raise SnapshotError("network_clock_regressed")
        if elapsed < MIN_HOST_INTERVAL_SECONDS and stop.wait(MIN_HOST_INTERVAL_SECONDS - elapsed):
            raise FetchInterrupted("update_interrupted")
    if stop.is_set():
        raise FetchInterrupted("update_interrupted")
    entry = {"event": "attempt", "attempt_id": uuid.uuid4().hex, "index_id": index.index_id,
             "job_id": job_id, "source": source, "url": url, "host": host,
             "started_at": _now(), "reserved_bytes": MAX_RESPONSE_BYTES}
    if budget.lease is not None:
        if budget.lease.budget.root != parent:
            raise SnapshotError("periodic_scope_mismatch")
        entry["periodic_attempt"] = budget.lease.charge(url, MAX_RESPONSE_BYTES)
    append_record(parent / "index-v2-network-ledger.jsonl", entry)
    return entry


def _reap(process: subprocess.Popen) -> None:
    """所有路径均关闭父存活管道并有界 terminate/kill/wait。"""
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
    finally:
        if process.stdin:
            process.stdin.close()


def fetch_bounded(parent: Path, index: IndexDefinition, source: str, window: FrozenWindow, job_id: str, *,
                  budget: NetworkBudget, guard: Callable[[], None] | None = None,
                  stop: threading.Event | None = None) -> Original:
    """父 EX 锁内每源一次请求；没有自动重试或环境预算覆盖。"""
    stop = stop or threading.Event()
    if guard:
        guard()
    entry = reserve(parent, index, source, window, job_id, budget, stop)
    success = False
    charged = MAX_RESPONSE_BYTES
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="thewolf-index-v2-fetch-") as directory:
            output = Path(directory).resolve()
            try:
                if stop.is_set():
                    raise FetchInterrupted("update_interrupted")
                process = subprocess.Popen([sys.executable, "-m", "pmi.market_data.index_series_fetch",
                    "--index-id", index.index_id, "--source", source, "--anchor", window.anchor_date, "--output", str(output)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + DEADLINE_SECONDS
                while process.poll() is None:
                    if stop.is_set():
                        raise FetchInterrupted("update_interrupted")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SnapshotError("source_deadline_exceeded")
                    try:
                        process.wait(timeout=min(.1, remaining))
                    except subprocess.TimeoutExpired:
                        continue
                if process.returncode != 0:
                    failure = output / "failure.json"
                    code = load_json(read_bytes(failure)).get("code") if failure.exists() else None
                    raise SnapshotError(code if code in _FAILURE_CODES else "source_fetch_failed")
                receipt = load_json(read_bytes(output / "receipt.json"))
                content = read_bytes(output / "original")
                if receipt.get("bytes") != len(content) or len(content) > MAX_RESPONSE_BYTES or receipt.get("complete") is not True:
                    raise SnapshotError("invalid_fetch_receipt")
                completed = utc(receipt["completed_at"])
                if datetime.fromisoformat(completed.replace("Z", "+00:00")) < datetime.fromisoformat(entry["started_at"].replace("Z", "+00:00")):
                    raise SnapshotError("invalid_fetch_time")
                success, charged = True, len(content)
                return Original(source, content, entry["started_at"], completed, entry["url"])
            finally:
                if process is not None:
                    _reap(process)
    finally:
        if budget.lease is not None:
            budget.lease.settle(entry["periodic_attempt"], charged if success else None, success)
        if guard:
            guard()
        append_record(parent / "index-v2-network-ledger.jsonl", {
            "event": "finished", "attempt_id": entry["attempt_id"], "index_id": index.index_id,
            "job_id": job_id, "source": source, "success": success, "charged_bytes": charged, "finished_at": _now()})


def fetch_once(url: str, output: Path) -> None:
    """子进程单请求：保留系统代理与 TLS，拒绝重定向、压缩及超限正文。"""
    import requests

    size = 0
    with requests.get(url, stream=True, timeout=(5, 15), allow_redirects=False,
                      headers={"User-Agent": "TheWolf-index-series/2", "Accept-Encoding": "identity"}) as response:
        if response.status_code != 200:
            raise SnapshotError("source_http_rejected")
        if response.headers.get("Content-Encoding", "identity").strip().lower() not in ("identity", ""):
            raise SnapshotError("source_encoding_rejected")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isascii() or not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
            raise SnapshotError("source_length_rejected")
        with (output / "original").open("xb") as stream:
            while size < MAX_RESPONSE_BYTES:
                chunk = response.raw.read(min(8192, MAX_RESPONSE_BYTES - size), decode_content=False)
                if not chunk:
                    break
                size += len(chunk)
                stream.write(chunk)
            if size == MAX_RESPONSE_BYTES and length != str(MAX_RESPONSE_BYTES):
                raise SnapshotError("source_body_limit")
            if length is not None and size != int(length):
                raise SnapshotError("source_incomplete_body")
            stream.flush()
            os.fsync(stream.fileno())
    (output / "receipt.json").write_bytes(canonical({"bytes": size, "complete": True, "completed_at": _now()}))


def _watch_parent() -> None:
    while True:
        try:
            if not os.read(sys.stdin.fileno(), 1):
                break
        except InterruptedError:
            continue
        except OSError:
            break
    os.kill(os.getpid(), signal.SIGTERM)


def main() -> None:
    """子进程只接受登记身份和已覆盖窗口，拒绝任意 URL。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-id", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    threading.Thread(target=_watch_parent, daemon=True).start()
    try:
        index = get_index(args.index_id)
        window = complete_window(datetime.fromisoformat(args.anchor + "T00:00:00+08:00"))
        fetch_once(source_url(index, args.source, window), args.output)
    except Exception as error:
        code = str(error) if isinstance(error, SnapshotError) and str(error) in _FAILURE_CODES else "source_network_error"
        # 只保存本地白名单代码和异常类型；不记录请求异常中的代理凭据或服务正文。
        try:
            (args.output / "failure.json").write_bytes(canonical({"code": code, "error_type": type(error).__name__}))
        except OSError:
            pass
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
