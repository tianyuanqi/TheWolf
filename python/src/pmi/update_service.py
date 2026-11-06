"""显式更新用例与进程内关联；读关联不访问金融数据、不重放业务。"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import logging
import threading

from pmi.http_boundary import Boundary, Rejected
from pmi.http_contract import response_value
from pmi.market_data import SnapshotError

_LOGGER = logging.getLogger(__name__)


@dataclass
class Association:
    """初始回执只写一次；可变进度与它分别持有深拷贝。"""

    identity: dict[str, str]
    settled: threading.Event = field(default_factory=threading.Event)
    receipt: tuple[int, dict | None] | None = None
    value: dict = field(default_factory=dict)


class UpdateService:
    """先预留再调用既有更新器；互斥区内从不等待父根锁或采集。"""

    def __init__(self, boundary: Boundary):
        self.boundary = boundary
        self.config = boundary.config
        self.capacity = boundary.spec["x-wolf-operation-semantics"]["capacity"]
        self._mutex = threading.Lock()
        self._rows: dict[str, Association] = {}
        self._series_active: dict[str, dict] = {}
        self._startup_stop = threading.Event()
        self._startup_thread: threading.Thread | None = None
        self.startup_results: list[dict] = []
        self.activity_startup_results: list[dict] = []


    def _unknown(self, identity: dict) -> dict:
        return {**identity, "state": "unknown", "job_id": None, "reused_job": None,
                "business_status": None, "rejection": None}

    def lookup(self, identity: dict) -> dict:
        """仅从原实例/配置/request/操作的内存行返回精确结果。"""
        with self._mutex:
            row = self._rows.get(identity["request_id"])
            if row is None or row.identity != identity:
                return self._unknown(identity)
            return deepcopy(row.value)


        # 此钩子在Thread.start前完成；settled由交接返回后设置，重复者不能抢先执行。





    def _handoff_unknown(self, row: Association) -> None:
        # 调用方持互斥锁；后续落盘错误不能推翻精确job已通知的确定终态。
        if row.value["state"] not in {"completed", "failed", "interrupted", "rejected"}:
            row.value.update(state="unknown", business_status=None)
        # 受理前无回执才登记500；已登记的初始回执始终不可变。
        if row.receipt is None:
            row.receipt = (500, None)



    def normalize_series(self, index_id: str, value: dict) -> dict:
        """新状态按指数核身份后验证独立Schema，不扩大旧状态枚举。"""
        if value.get("index_id") != index_id:
            raise ValueError("指数状态身份不符")
        properties = self.boundary.spec["components"]["schemas"]["IndexSeriesUpdateStatus"]["properties"]
        result = {key: ([] if schema.get("type") == "array" else None) for key, schema in properties.items()}
        result.update({key: deepcopy(item) for key, item in value.items() if key in properties})
        result["enabled"] = index_id in self.config.index_write_ids
        return response_value("IndexSeriesUpdateStatus", result)

    def _series_accept(self, row: Association, index_id: str, state: dict, reused: bool) -> None:
        status = self.normalize_series(index_id, state)
        if not status["job_id"] or not self.config.market_data.is_active(index_id, status["stage"]):
            raise ValueError("受理需要精确的指数活动job")
        value = {**row.identity, "state": "running" if reused else "accepted", "job_id": status["job_id"],
                 "reused_job": reused, "business_status": status, "rejection": None}
        response_value("IndexSeriesAcceptedOperation", value)
        with self._mutex:
            row.value = deepcopy(value)
            row.receipt = (202, deepcopy(value))
            self._series_active[index_id] = deepcopy(status)

    def _series_notify(self, index_id: str, state: dict) -> None:
        status = self.normalize_series(index_id, state)
        stage = status["stage"]
        active = self.config.market_data.is_active(index_id, stage)
        terminal = {"completed": {"business_changed", "evidence_changed", "unchanged", "source_not_ready"},
                    "failed": {"failed"}, "interrupted": {"interrupted"}}
        if (not status["job_id"] or (not active and stage not in terminal)
                or (stage in terminal and status["result"] not in terminal[stage])):
            raise ValueError("指数job阶段与结果不一致")
        with self._mutex:
            if active:
                self._series_active[index_id] = deepcopy(status)
            elif self._series_active.get(index_id, {}).get("job_id") == status["job_id"]:
                self._series_active.pop(index_id, None)
            for row in self._rows.values():
                if (row.identity.get("index_id") == index_id and row.identity["operation"] == "index.series.update"
                        and row.value["job_id"] == status["job_id"] and row.value["state"] in {"accepted", "running"}):
                    row.value.update(state="running" if active else stage, business_status=deepcopy(status))

    def _series_uncertain(self, index_id: str, job_id: str) -> None:
        with self._mutex:
            if self._series_active.get(index_id, {}).get("job_id") == job_id:
                self._series_active.pop(index_id, None)
            for row in self._rows.values():
                if (row.identity.get("index_id") == index_id and row.value["job_id"] == job_id
                        and row.value["state"] in {"accepted", "running", "unknown"}):
                    row.value.update(state="unknown", business_status=None, rejection=None)

    def _series_progress(self, row: Association, index_id: str, state: dict) -> None:
        try:
            if state.get("job_id") != row.value.get("job_id"):
                raise ValueError("指数通知job不属于受理请求")
            self._series_notify(index_id, state)
        except Exception as error:
            self._series_uncertain(index_id, row.value["job_id"])
            _LOGGER.error("指数通知失败 index=%s error_type=%s", index_id, type(error).__name__)

    def start_series(self, index_id: str, request_id: str) -> tuple[int, dict | None]:
        """新旧操作共用request登记，完整五元身份重复仅返回首次回执。"""
        self.config.check_write_paths()
        identity = {"instance_id": self.boundary.instance, "config_id": self.config.index_config_id,
                    "request_id": request_id, "operation": "index.series.update", "index_id": index_id}
        with self._mutex:
            row = self._rows.get(request_id)
            owner = row is None
            if row is not None and row.identity != identity:
                raise Rejected(409, "request_id_conflict", "请求标识已用于其他操作或指数")
            if owner:
                if len(self._rows) >= self.capacity:
                    raise Rejected(503, "operation_capacity_exceeded", "本实例关联容量已满")
                row = Association(identity, value=self._unknown(identity))
                self._rows[request_id] = row
        if not owner:
            row.settled.wait(5)
            with self._mutex:
                return deepcopy(row.receipt) if row.settled.is_set() and row.receipt else (500, None)
        try:
            self.config.market_data.update(index_id,
                accepted=lambda state, reused: self._series_accept(row, index_id, state, reused),
                notify=lambda state: self._series_progress(row, index_id, state),
                uncertain=lambda job: self._series_uncertain(index_id, job), guard=self.config.check_write_paths)
        except SnapshotError as error:
            with self._mutex:
                if row.receipt is None:
                    body = {"detail": {"code": "index_series_unavailable", "message": "更新未受理：已有写入或本地资料不可用"}}
                    row.receipt = (409, body)
                    row.value.update(state="rejected", rejection={"status": 409, "body": deepcopy(body)})
                else:
                    self._handoff_unknown(row)
            _LOGGER.warning("指数更新未受理 index=%s error_type=%s", index_id, type(error).__name__)
        except Exception as error:
            with self._mutex:
                self._handoff_unknown(row)
            _LOGGER.error("指数更新交接未知 index=%s error_type=%s", index_id, type(error).__name__)
        finally:
            row.settled.set()
        with self._mutex:
            return deepcopy(row.receipt) if row.receipt else (500, None)

    def series_status(self, index_id: str) -> dict:
        """活动通知按指数隔离，其余状态由数据层只读核验精确job。"""
        self.config.check_location()
        with self._mutex:
            current = deepcopy(self._series_active.get(index_id))
        if current is None:
            current = self.config.market_data.status(index_id)
            if current.get("job_id") and current.get("stage") in {"completed", "failed", "interrupted"}:
                self._series_notify(index_id, current)
        self.config.check_location()
        return self.normalize_series(index_id, current)

    def start_startup(self) -> None:
        """serve生命周期显式启动一次串行补齐；构造、describe和GET不调用。"""
        if self.config.periodic_options is not None:
            if self._startup_thread is None:
                from pmi.periodic_scheduler import Scheduler
                scheduler = Scheduler(lambda: self.config.market_data.periodic_check(
                    self.config.startup_index_ids, self.config.activity_config_id, self.boundary.instance), self._startup_stop)
                self._startup_thread = threading.Thread(target=scheduler.run, name="overview-periodic", daemon=True)
                self._startup_thread.start()
            return
        activity_startup = self.config.activity_options and self.config.activity_options.startup_series
        if (not self.config.startup_index_ids and not activity_startup) or self._startup_thread is not None:
            return

        def prepare() -> None:
            for index_id in self.config.startup_index_ids:
                if self._startup_stop.is_set():
                    break
                try:
                    initial = self.config.market_data.update(index_id, trigger="startup", only_missing=True)
                    while not self.config.market_data.wait_updates(1):
                        if self._startup_stop.is_set():
                            return
                    result = initial if initial.get("result") == "already_covered" else self.config.market_data.status(index_id)
                    self.startup_results.append(deepcopy(result))
                    if result.get("result") not in {"already_covered", "business_changed", "evidence_changed", "unchanged"}:
                        break
                except Exception as error:
                    self.startup_results.append({"index_id": index_id, "stage": "failed", "error_type": type(error).__name__})
                    _LOGGER.error("指数启动补齐失败 index=%s error_type=%s", index_id, type(error).__name__)
                    break
            if activity_startup and not self._startup_stop.is_set():
                try:
                    self.activity_startup_results = self.config.market_data.activity(
                        "startup", self.config.activity_config_id, self.boundary.instance)
                except Exception as error:
                    self.activity_startup_results = [{"state": "failed", "error_type": type(error).__name__}]
                    _LOGGER.error("量额启动补齐失败 error_type=%s", type(error).__name__)
        self._startup_thread = threading.Thread(target=prepare, name="index-series-startup", daemon=True)
        self._startup_thread.start()

    def close(self) -> bool:
        """停止后续启动项并有界回收本实例新指数worker；不修改业务结果。"""
        self._startup_stop.set()
        closed = self.config.market_data.close_updates(50)
        if self._startup_thread is not None:
            self._startup_thread.join(2)
        return closed and (self._startup_thread is None or not self._startup_thread.is_alive())
