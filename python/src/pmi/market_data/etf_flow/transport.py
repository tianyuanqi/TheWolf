"""ETF单次有界请求：沿用现有子进程隔离方式，独立预算且保留部分原件。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import subprocess
import sys
import threading
import time
from typing import Any

from .budget import Budget, Request
from .model import FlowError, decode, exact, instant

ERRORS = frozenset({"etf_source_http_rejected", "etf_source_encoding_rejected", "etf_source_length_rejected",
                    "etf_source_incomplete_body", "etf_source_body_limit", "etf_source_network_error",
                    "etf_source_deadline_exceeded", "etf_update_interrupted", "etf_source_receipt_invalid"})


@dataclass(frozen=True)
class Original:
    request: Request
    attempt_id: str
    object_id: str
    raw: bytes
    retrieved_at: str
    receipt_id: str


def receipt(raw: bytes | None, size: int, started_at: str) -> dict[str, Any] | None:
    """只接受完整、有限且时间不倒退的子进程回执；空或半写保持未知。"""
    if not raw:
        return None
    try:
        v = exact(decode(raw), {"status", "bytes", "complete", "code", "finished_at"})
        if (type(v["bytes"]) is not int or v["bytes"] != size or type(v["complete"]) is not bool
                or (v["status"] is not None and (type(v["status"]) is not int or not 100 <= v["status"] <= 599))
                or (v["code"] is not None and v["code"] not in ERRORS)
                or v["complete"] != (v["code"] is None and v["status"] == 200)
                or instant(v["finished_at"]) < instant(started_at)):
            return None
        return v
    except (ValueError, TypeError, FlowError):
        return None


def reap(process: subprocess.Popen) -> None:
    """只回收本次启动的子进程；先等待退出再释放根锁。"""
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


class Transport:
    def __init__(self, budget: Budget, stop: threading.Event):
        self.budget, self.stop = budget, stop

    def fetch(self, request: Request, operation_key: str) -> Original:
        """串行、有界、无重试；任何失败都保存占额和已收到原件，再停止整个批次。"""
        budget, store = self.budget, self.budget.store
        store._require_writer()
        _, ledger = budget.read()
        if ledger["attempts"]:
            last = ledger["attempts"][-1]["closed_at"]
            if last is None:
                raise FlowError("etf_unsettled_attempt")
            elapsed = (budget.clock() - instant(last)).total_seconds()
            if elapsed < 0:
                raise FlowError("etf_clock_regressed")
            delay = budget.grant.interval_seconds - elapsed
            if delay > 0 and self.stop.wait(delay):
                raise FlowError("etf_update_interrupted")
        if self.stop.is_set():
            raise FlowError("etf_update_interrupted")
        attempt = budget.charge(request, operation_key)
        _, ledger = budget.read()
        started = ledger["attempts"][-1]["started_at"]
        descriptors: list[int] = []
        process = None
        failure = None
        try:
            descriptors.append(store.create_spool(attempt, "raw"))
            descriptors.append(store.create_spool(attempt, "receipt"))
            command = [sys.executable, "-B", "-m", "pmi.market_data.etf_flow.transport_worker", request.url,
                       str(budget.grant.response_limit), str(budget.grant.timeout_seconds),
                       str(descriptors[0]), str(descriptors[1])]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, pass_fds=(*descriptors, store.inherited_lock()))
            deadline = time.monotonic() + budget.grant.timeout_seconds
            while process.poll() is None:
                if self.stop.is_set():
                    failure = "etf_update_interrupted"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failure = "etf_source_deadline_exceeded"
                    break
                try:
                    process.wait(timeout=min(remaining, .1))
                except subprocess.TimeoutExpired:
                    pass
        except OSError:
            failure = "etf_source_network_error"
        finally:
            if process is not None:
                reap(process)
            for fd in descriptors:
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        raw = store.read_spool(attempt, "raw", budget.grant.response_limit)
        metadata = store.read_spool(attempt, "receipt", 4096)
        # 未建文件也扣额；读到不安全或超限文件则保持未知，不放宽原预算。
        raw = raw if raw is not None else b""
        result = receipt(metadata, len(raw), started)
        if process is not None and process.returncode != 0:
            failure = failure or "etf_source_network_error"
        if result is None:
            failure = failure or "etf_source_receipt_invalid"
        else:
            failure = failure or result["code"]
        original = budget.settle(attempt, raw, failure is None)
        record = {"attempt_id": attempt, "request_key": request.key, "object_id": original,
                  "worker_receipt": result, "code": failure, "closed_at": budget.clock().isoformat()}
        reference = store.put_json(record)
        # 每个请求有独立的可恢复回执指针，成功/失败原件均保留。
        from .model import digest
        store.write_journal(digest({"receipt": attempt}), record, None)
        if failure:
            raise FlowError(failure)
        return Original(request, attempt, original, raw, result["finished_at"], reference)

    def recover(self, operation_key: str) -> None:
        """只在取得根锁后显式核验孤立回执，无网络，无自动重试。"""
        store, budget = self.budget.store, self.budget
        store._require_writer()
        _, ledger = budget.read()
        for row in ledger["attempts"]:
            if row["operation_key"] != operation_key or row["closed_at"] is not None:
                continue
            raw = store.read_spool(row["id"], "raw", budget.grant.response_limit)
            metadata = store.read_spool(row["id"], "receipt", 4096)
            result = receipt(metadata, len(raw or b""), row["started_at"])
            if raw is not None and result is not None:
                budget.settle(row["id"], raw, result["complete"])
            elif raw is not None:
                store.put(raw)  # 部分正文留存；不能据此编造完整字节/成功回执。
        budget.close_unknown(operation_key)
