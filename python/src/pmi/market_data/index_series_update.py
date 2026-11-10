"""指数 v2 更新编排：任务隔离、失败保旧、提交恢复及实例生命周期。"""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import time
from typing import Callable
import uuid

from pmi.market_data import SnapshotError
from pmi.market_data.index_activity import activity
from pmi.market_data.index_catalog import IndexDefinition
from pmi.market_data.index_history_calendar import FrozenWindow, validate_window
from pmi.market_data.index_series_contract import Original, SourceMismatch, SourceNotReady, build_manifest, canonical, digest
from pmi.market_data.index_series_fetch import FetchInterrupted, NetworkBudget, fetch_bounded
from pmi.market_data.storage import index_store as store
from pmi.market_data.storage.tasks import Task

ACTIVE = store.ACTIVE
_LOGGER = logging.getLogger(__name__)
_SAFE_FAILURE_CODES = frozenset({"network_budget_exhausted", "network_clock_regressed", "invalid_network_ledger",
                                 "incomplete_network_ledger", "source_deadline_exceeded", "source_fetch_failed",
                                 "source_http_rejected", "source_encoding_rejected", "source_length_rejected",
                                 "source_incomplete_body", "source_body_limit", "source_network_error",
                                 "source_mismatch", "stale_window", "object_hash_mismatch", "wrong_database_index"})


class Runtime:
    """只拥有本门面启动的线程和停止事件，不停止其他实例。"""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.mutex = threading.RLock()
        self.threads: list[threading.Thread] = []

    def wait(self, timeout: float = 50) -> bool:
        """同一有界期限内等待现有 worker；不触发停止。"""
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 300:
            raise ValueError("invalid_wait_timeout")
        deadline = time.monotonic() + timeout
        with self.mutex:
            workers = tuple(self.threads)
        for worker in workers:
            if worker is threading.current_thread():
                return False
            worker.join(max(0, deadline - time.monotonic()))
        with self.mutex:
            self.threads[:] = [worker for worker in self.threads if worker.is_alive()]
            return not self.threads

    def close(self, timeout: float = 50) -> bool:
        """先禁止后续采集，再等待本实例资源释放；可重复调用。"""
        with self.mutex:
            self.stop.set()
        return self.wait(timeout)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _Notifications:
    """回调失败只令请求结果不确定，不伪装金融事务回滚。"""

    def __init__(self, notify: Callable[[dict], None] | None, uncertain: Callable[[str], None] | None, job_id: str):
        self.notify, self.uncertain, self.job_id = notify, uncertain, job_id
        self.failed = False

    def unknown(self) -> None:
        if self.failed:
            return
        self.failed = True
        if self.uncertain:
            try:
                self.uncertain(self.job_id)
            except Exception as error:
                _LOGGER.error("index series uncertain callback failed job=%s error_type=%s", self.job_id, type(error).__name__)

    def send(self, state: dict) -> None:
        if self.notify and not self.failed:
            try:
                self.notify(deepcopy(state))
            except Exception as error:
                _LOGGER.error("index series notification failed job=%s error_type=%s", self.job_id, type(error).__name__)
                self.unknown()


def classify_change(previous: dict | None, manifest: dict) -> tuple[str, list[str], list[str]]:
    """价格差异按官方保存精度比较；依据变化与业务变化分开报告。"""
    fields = ("open", "high", "low", "close")
    before = {row["trade_date"]: tuple(row[field] for field in fields) for row in previous["bars"]} if previous else {}
    after = {row["trade_date"]: tuple(row[field] for field in fields) for row in manifest["bars"]}
    added = sorted(after.keys() - before.keys())
    revised = sorted(day for day in after.keys() & before.keys() if after[day] != before[day])
    if added or revised or before.keys() != after.keys():
        return "business_changed", added, revised
    return ("unchanged" if previous and previous["snapshot_id"] == digest(canonical(manifest)) else "evidence_changed"), added, revised


def perform_update(parent: Path, index: IndexDefinition, window: FrozenWindow, state: dict, *,
                   budget: NetworkBudget, stop: threading.Event, fetch: Callable | None = None,
                   guard: Callable[[], None] | None = None, checkpoint: Callable[[str], None] | None = None,
                   notifications: _Notifications | None = None) -> dict:
    """调用者持父锁及本指数活动锁；原件先归档，完成核验才发布。"""
    notices = notifications or _Notifications(None, None, state["job_id"])
    fetch = fetch or fetch_bounded

    def check() -> None:
        if guard:
            guard()
        if stop.is_set():
            raise FetchInterrupted("update_interrupted")

    def save() -> None:
        if guard:
            guard()
        store.save_status(parent, index, state)
        notices.send(state)

    try:
        check()
        previous = store.read_snapshot_locked(parent, index)
        if previous and (window.end < previous["window"]["end"] or window.anchor_date < previous["window"]["anchor_date"]):
            raise SnapshotError("stale_window")
        originals: list[Original] = []
        root = store.index_root(parent, index)
        for source in index.sources:
            check()
            state["stage"] = "fetching_" + source
            save()
            original = fetch(parent, index, source, window, state["job_id"], budget=budget, guard=guard, stop=stop)
            if guard:
                guard()
            # 即使随后身份、日历、精度不合格，已完整收到的原件也保留。
            object_id = store.write_object(root, original.content)
            store.record_original(parent, index, {
                "index_id": index.index_id, "job_id": state["job_id"], "source": source,
                "url": original.url, "object_id": object_id, "started_at": original.started_at,
                "completed_at": original.completed_at, "published_at": None})
            originals.append(original)
        check()
        state["stage"] = "validating"
        save()
        manifest = build_manifest(index, window, tuple(originals))
        result, added, revised = classify_change(previous, manifest)
        state.update(stage="publishing", result=result, added_dates=added, revised_dates=revised,
                     message={"business_changed": "指数价格已更新", "evidence_changed": "价格未变化，依据已更新",
                              "unchanged": "检查完成，价格及依据未变化"}[result])
        check()
        save()

        def guarded_checkpoint(stage: str) -> None:
            if stage != "after_commit":
                check()
            elif guard:
                guard()
            if checkpoint:
                checkpoint(stage)

        completed = store.publish(parent, index, window, manifest, tuple(originals), state, guarded_checkpoint)
        if checkpoint:
            checkpoint("before_status")
        if guard:
            guard()
        store.save_status(parent, index, completed)
        notices.send(completed)
        return completed
    except Exception as error:
        from .storage.database import CommitUncertain
        if isinstance(error, (store.PublicationUncertain, CommitUncertain)):
            # 建名/替换已发生，但同步或最终身份未获确认。库中 job 不能在
            # 本请求的通用兜底中把这种不确定性改成 completed。
            notices.unknown()
            raise
        if guard:
            guard()
        committed = store.committed_job_locked(parent, index, state["job_id"])
        if committed:
            # 精确 job 提交证明优先；状态文件故障不改写已发布金融事实。
            notices.send(committed)
            return committed
        interrupted = isinstance(error, FetchInterrupted)
        not_ready = isinstance(error, SourceNotReady)
        reason = str(error) if isinstance(error, SnapshotError) and str(error) in _SAFE_FAILURE_CODES else type(error).__name__
        state.update(stage="interrupted" if interrupted else "completed" if not_ready else "failed",
                     result="interrupted" if interrupted else "source_not_ready" if not_ready else "failed",
                     message="任务已中断，旧快照保留" if interrupted else "来源尚未完整，旧快照保留" if not_ready else
                             "核验或本地更新失败，旧快照保留（" + reason + ")",
                     finished_at=_now(), differences=deepcopy(error.details) if isinstance(error, SourceMismatch) else [])
        save()
        return state


def start_update(parent: Path, index: IndexDefinition, window: FrozenWindow, *, budget: NetworkBudget,
                 runtime: Runtime, guard: Callable[[], None] | None = None,
                 remember_locations: Callable[[], None] | None = None,
                 accepted: Callable[[dict, bool], None] | None = None,
                 notify: Callable[[dict], None] | None = None, uncertain: Callable[[str], None] | None = None,
                 trigger: str = "manual", only_missing: bool = False, fetch: Callable | None = None,
                 checkpoint: Callable[[str], None] | None = None) -> dict:
    """冻结身份、拿父锁和精确活动证明后先登记回执，再启动本实例线程。"""
    validate_window(window)
    if trigger not in {"manual", "startup"}:
        raise SnapshotError("invalid_update_trigger")
    if type(only_missing) is not bool:
        raise ValueError("invalid_only_missing")
    with runtime.mutex:
        if runtime.stop.is_set():
            raise SnapshotError("runtime_closed")
        if guard:
            guard()
        store.reject_sidecars(parent, index)
        lock = ExitStack()
        task = Task.acquire(parent, budget.lease.task if budget.lease else None)
        lock.callback(task.close)
        try:
            with task.use():
                if guard:
                    guard()
                store.reject_sidecars(parent, index)
                root = store.prepare_directories(parent, index)
                if remember_locations:
                    remember_locations()
                if guard:
                    guard()
                store.recover_locked(parent, index, guard=guard)
                previous = store.read_snapshot_locked(parent, index)
                if only_missing and previous and set(window.dates) <= set(previous["calendar_dates"]):
                    lock.close()
                    return {"index_id": index.index_id, "stage": "completed", "result": "already_covered"}
                if previous and (window.end < previous["window"]["end"] or window.anchor_date < previous["window"]["anchor_date"]):
                    raise SnapshotError("stale_window")
                previous_state = store.raw_status(parent, index)
                store.committed_job_locked(parent, index, previous_state.get("job_id"))
                last_success = store.latest_success_at_locked(parent, index)
                state = {**store.idle_state(index), "job_id": uuid.uuid4().hex, "trigger": trigger, "stage": "preparing",
                         "started_at": _now(), "target_start": window.start, "target_end": window.end,
                         "previous_snapshot_id": previous["snapshot_id"] if previous else None,
                         "last_success_at": last_success, "message": "正在准备指数完整三年窗口"}
                notices = _Notifications(notify, uncertain, state["job_id"])
                lock.enter_context(activity(root, index.index_id, state["job_id"]))
                store.save_status(parent, index, state)
                initial = deepcopy(state)
                if accepted:
                    try:
                        accepted(deepcopy(initial), False)
                    except BaseException:
                        notices.unknown()
                        raise

                def worker() -> None:
                    try:
                        with task.use():
                            perform_update(parent, index, window, state, budget=budget, stop=runtime.stop,
                                           fetch=fetch, guard=guard, checkpoint=checkpoint, notifications=notices)
                    except BaseException as error:
                        _LOGGER.error("index series worker outcome unknown index=%s job=%s error_type=%s", index.index_id, state["job_id"], type(error).__name__)
                        notices.unknown()
                    finally:
                        lock.close()

                thread = threading.Thread(target=worker, name="index-series-" + state["job_id"], daemon=True)
                runtime.threads.append(thread)
                try:
                    if runtime.stop.is_set():
                        raise FetchInterrupted("runtime_closed")
                    thread.start()
                except Exception:
                    runtime.threads.remove(thread)
                    state.update(stage="failed", result="failed", finished_at=_now(), message="后台任务未启动，旧快照保留")
                    try:
                        if guard:
                            guard()
                        store.save_status(parent, index, state)
                        notices.send(state)
                    except Exception:
                        notices.unknown()
                    lock.close()
                return initial
        except BaseException:
            lock.close()
            raise
