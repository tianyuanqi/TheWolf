"""行情数据公开入口：按标的代码读取和更新，不依赖HTTP、界面或模型。"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import threading
from types import MappingProxyType

from pmi.market_data.read_only import ReadUnavailable, checked_path

from pmi.market_data.activity.model import ActivityError, Options as ActivityOptions, SERIES as ACTIVITY_SERIES, MARKET as ACTIVITY_MARKET

__all__ = ["MarketData", "ReadUnavailable", "SnapshotError", "ActivityError", "ActivityOptions", "ACTIVITY_SERIES", "ACTIVITY_MARKET"]


class SnapshotError(ValueError):
    """待发布或已保存的快照不符合切片契约。"""


@dataclass(frozen=True, init=False)
class MarketData:
    """冻结既有数据定位和显式写权限；构造只查元数据，不建库或恢复。

    Args:
        root: 已存在、无符号链接的规范绝对父根。
        writes: 已登记代码的布尔写开关；未提供者默认禁写。
    """

    _root: Path = field(repr=False)
    _writes: Mapping[str, bool] = field(repr=False)
    _locations: tuple[tuple[Path, int, int], ...] = field(repr=False)
    _series_locations: dict[Path, tuple[int, int]] = field(repr=False)
    _location_mutex: threading.RLock = field(repr=False)
    _series_runtime: object = field(repr=False)
    _series_budget: object = field(repr=False)
    _activity_runtime: object = field(repr=False)

    def __init__(self, root: Path, writes: Mapping[str, bool], *,
                 index_max_attempts: int = 16, index_max_bytes: int = 16 * 1024 * 1024, activity_options: ActivityOptions | None = None, periodic_options=None):
        from pmi.market_data.index_catalog import search_indices
        from pmi.market_data.index_series_fetch import NetworkBudget
        from pmi.market_data.index_series_update import Runtime
        definitions = search_indices(None)
        allowed = {item.index_id for item in definitions}
        if any(code not in allowed or type(enabled) is not bool for code, enabled in writes.items()):
            raise ValueError("未登记的标的代码或无效写开关")
        checked_path(root)
        if not root.is_dir() or root.resolve() != root:
            raise ValueError("data root必须是已有的规范绝对目录")
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "_writes", MappingProxyType(dict(writes)))
        object.__setattr__(self, "_locations", tuple(
            (path, path.stat().st_dev, path.stat().st_ino)
            for path in (root, *root.parents, root / "indices") if path.exists()))
        object.__setattr__(self, "_location_mutex", threading.RLock())
        series_paths = (root / "indices", *(path for item in definitions
                         for path in (root / item.relative_dir, root / item.relative_dir / "objects")))
        locations = {}
        for path in series_paths:
            checked_path(path)
            if path.exists():
                if not path.is_dir():
                    raise ReadUnavailable("指数目录类型不安全")
                value = path.stat()
                locations[path] = (value.st_dev, value.st_ino)
        object.__setattr__(self, "_series_locations", locations)
        object.__setattr__(self, "_series_budget", NetworkBudget(index_max_attempts, index_max_bytes))
        object.__setattr__(self, "_series_runtime", Runtime())
        activity_runtime = None
        if activity_options is not None:
            from pmi.market_data.activity.runtime import Runtime as ActivityRuntime
            if activity_options.root.is_relative_to(root) or root.is_relative_to(activity_options.root):
                raise ValueError("量额根与价格根不得嵌套")
            if activity_options.budget_ledger is not None and activity_options.budget_ledger.is_relative_to(root):
                raise ValueError("量额预算账本不得写入价格根")
            activity_runtime = ActivityRuntime(self, activity_options)
        object.__setattr__(self, "_activity_runtime", activity_runtime)
        periodic = None
        if periodic_options is None and (root / "overview-periodic-ledger.json").exists() and (
                any(writes.values()) or activity_options and activity_options.write_series):
            raise ValueError("周期账本已存在，启写必须携带周期策略；旧模式只读仍可使用")
        if periodic_options is not None:
            from pmi.market_data.periodic_budget import Budget, INDEX_IDS, MARKET_ID
            from pmi.market_data.periodic_runtime import Coordinator
            if activity_runtime is None or any(enabled and code not in INDEX_IDS for code, enabled in writes.items()):
                raise ValueError("周期预算仅支持四指数和显式量额根")
            if not set(activity_options.write_series) <= {*INDEX_IDS, MARKET_ID, "cn-a-turnover"}:
                raise ValueError("周期预算不得扩大市场范围")
            periodic = Coordinator(self, Budget(root, activity_options.root, periodic_options))
        object.__setattr__(self, "_periodic", periodic)

    @property
    def scope_id(self) -> str:
        """返回总览数据范围摘要；布局及序列化留在本层，无业务I/O。"""
        value = {"identity_format": "wolf-data-scope-v2", "data_root": str(self._root),
                 "mapping": {"index_series": "indices"}}
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def check_location(self) -> None:
        """业务访问前复核启动定位；换根不能沿用原配置身份。"""
        checked_path(self._root)
        for path, device, inode in self._locations:
            actual = path.stat()
            if (actual.st_dev, actual.st_ino) != (device, inode):
                raise ReadUnavailable("配置根定位已变化，请检查后重新启动")
        with self._location_mutex:
            for path, identity in self._series_locations.items():
                checked_path(path)
                actual = path.stat()
                if not stat.S_ISDIR(actual.st_mode) or (actual.st_dev, actual.st_ino) != identity:
                    raise ReadUnavailable("指数目录定位已变化，请检查后重新启动")

    def check_write_paths(self) -> None:
        """复核总览可写定位；只查元数据，不创建目录或打开业务库。"""
        self.check_location()
        for directory in (self._root, self._root / "indices"):
            checked_path(directory)
            if directory.exists() and not directory.is_dir():
                raise ReadUnavailable("更新目录类型不安全")
        lock = checked_path(self._root / ".writer.lock")
        if lock.exists() and not stat.S_ISREG(lock.stat().st_mode):
            raise ReadUnavailable("父根写锁类型不安全")
        from pmi.market_data.index_catalog import search_indices
        for item in search_indices(None):
            root = checked_path(self._root / item.relative_dir)
            for path in (root, root / "objects"):
                checked_path(path)
                if path.exists() and not path.is_dir():
                    raise ReadUnavailable("指数目录类型不安全")
            for name in ("index-v2.sqlite", "index-v2.sqlite-journal", "index-v2.sqlite-wal",
                         "index-v2.sqlite-shm", "update-v2-status.json", ".index-v2-activity.lock",
                         "index-v2-original-observations.jsonl"):
                path = checked_path(root / name)
                if path.exists() and not stat.S_ISREG(path.stat().st_mode):
                    raise ReadUnavailable("指数文件类型不安全")
        ledger = checked_path(self._root / "index-v2-network-ledger.jsonl")
        if ledger.exists() and not stat.S_ISREG(ledger.stat().st_mode):
            raise ReadUnavailable("指数预算账本类型不安全")

    def _remember_index_locations(self, index_id: str) -> None:
        """由持父独占锁的更新器登记本次新目录；已登记位置只能核对。"""
        from pmi.market_data.index_catalog import get_index
        item = get_index(index_id)
        self.check_location()
        with self._location_mutex:
            for path in (self._root / "indices", self._root / item.relative_dir,
                         self._root / item.relative_dir / "objects"):
                checked_path(path)
                actual = path.stat()
                identity = (actual.st_dev, actual.st_ino)
                if not stat.S_ISDIR(actual.st_mode) or self._series_locations.get(path, identity) != identity:
                    raise ReadUnavailable("新指数目录不能登记到已变更位置")
                self._series_locations[path] = identity

    @property
    def index_policy(self) -> dict:
        """公开影响新特性配置身份的固定策略，不暴露存储布局或金融数据。"""
        from pmi.market_data.index_catalog import CATALOG_VERSION, search_indices
        from pmi.market_data.index_history_calendar import CALENDAR_VERSION
        return {"feature_version": "index-series-v2", "catalog_version": CATALOG_VERSION,
                "calendar_version": CALENDAR_VERSION, "window_years": 3,
                "source_policy_versions": sorted({item.source_policy_version for item in search_indices(None)}),
                **({"periodic": {**self._periodic.budget.options.public(), "scope_id": self._periodic.budget.scope}} if self._periodic is not None else {}),
                "network": {"max_attempts": self._series_budget.max_attempts,
                            "max_bytes": self._series_budget.max_bytes, "max_response_bytes": 1048576,
                            "min_host_interval_seconds": 5, "deadline_seconds": 45}}

    def index_catalog(self, query: str | None = None) -> dict:
        """从已核登记表列出或解析指数；名称候选不触发任何数据I/O。"""
        from pmi.market_data.index_catalog import CATALOG_VERSION, public_index, resolve_index, search_indices
        resolved = None
        if query:
            try:
                resolved = resolve_index(query).index_id
            except SnapshotError:
                pass
        return {"catalog_version": CATALOG_VERSION, "query": query, "resolved_index_id": resolved,
                "indices": [public_index(item, self._writes.get(item.index_id, False))
                            for item in search_indices(query)]}

    def resolve_index(self, query: str) -> str:
        """将已登记名称或代码解析为canonical身份；未知与歧义不猜测。"""
        from pmi.market_data.index_catalog import resolve_index
        return resolve_index(query).index_id

    @staticmethod
    def _require_code(code: str) -> None:
        if not isinstance(code, str):
            raise ValueError("未登记的标的代码")
        from pmi.market_data.index_catalog import get_index
        try:
            get_index(code)
        except SnapshotError as error:
            raise ValueError("未登记的标的代码") from error

    def _read(self, code: str, operation: str, **identifiers: str | None) -> dict | bytes | None:
        self._require_code(code)
        self.check_location()
        try:
            value = self._read_series(code, operation, **identifiers)
            self.check_location()
            return value
        except sqlite3.Error as error:
            # 只转换读取错误；更新交接异常必须继续由请求协调者标为unknown。
            raise ReadUnavailable("本地数据库不能安全读取") from error

    def _read_series(self, code: str, operation: str, *, snapshot_id: str | None = None,
                     object_id: str | None = None) -> dict | None:
        from pmi.market_data.index_catalog import get_index
        from pmi.market_data import index_series_store as store
        item = get_index(code)
        if operation == "status":
            return {**store.read_status(self._root, item), "enabled": self._writes.get(code, False)}
        current = store.read_snapshot(self._root, item, snapshot_id)
        if current is not None:
            value = (store.read_evidence(self._root, item, snapshot_id or current["snapshot_id"], object_id)
                     if operation == "index_evidence" else current)
            return {"index_id": code, "format": "v2", "evidence" if operation == "index_evidence" else "snapshot": value}
        return None

    def read_daily(self, code: str, snapshot_id: str | None = None) -> dict | None:
        """读取现有完整日线视图及依据；缺库返回None，固定版本不随当前指针变化。"""
        return self._read(code, "index", snapshot_id=snapshot_id)

    def latest_date(self, code: str) -> str | None:
        """返回已保存日线末行的交易日；无日线为None，不用更新时间代替。"""
        value = self.read_daily(code)
        if value:
            value = value["snapshot"]
        return value["bars"][-1]["trade_date"] if value and value["bars"] else None

    def read_evidence(self, code: str, snapshot_id: str, object_id: str) -> dict | bytes | None:
        """按固定快照成员读取原依据；不接受文件路径，缺快照返回None。"""
        return self._read(code, "index_evidence",
                          snapshot_id=snapshot_id, object_id=object_id)

    def status(self, code: str) -> dict:
        """只读观察业务状态和提交证明；不恢复写入，不认领旧请求结果。"""
        return self._read(code, "status")

    def is_active(self, code: str, stage: str) -> bool:
        """判断已登记切片的既有活动阶段；不读盘、不启动来源。"""
        self._require_code(code)
        from pmi.market_data.index_series_update import ACTIVE
        return stage in ACTIVE

    def update(self, code: str, **kwargs) -> dict:
        """公开更新入口统一服从周期协调器，非周期模式使用显式指数更新器。"""
        if any(key.startswith('_') for key in kwargs):
            raise ValueError("私有更新参数不属于公共门面")
        if self._periodic is not None:
            self._require_code(code)
            if not self._writes.get(code, False):
                raise SnapshotError("该标的更新未启用")
            return self._periodic.manual_price(code, **kwargs)
        return self._update(code, **kwargs)

    def _update(self, code: str, *, accepted: Callable[[dict, bool], None] | None = None,
               notify: Callable[[dict], None] | None = None,
               uncertain: Callable[[str], None] | None = None,
               guard: Callable[[], None] | None = None,
               trigger: str = "manual", only_missing: bool = False, _periodic=None) -> dict:
        """显式启动既有更新；受理早于worker，异常原样交回，不自动重发。

        回调只传业务状态或job；不接收HTTP对象。位置和写权限由本层复核，
        上层guard仅补充约束，不能代替数据层检查。
        """
        if self._periodic is not None:
            if _periodic is None or _periodic[0] is not self._periodic:
                raise SnapshotError("periodic_lease_required")
            _periodic[2].lease.ensure()
        self._require_code(code)
        if not self._writes.get(code, False):
            raise SnapshotError("该标的更新未启用")

        def checked_guard() -> None:
            self.check_write_paths()
            if guard:
                guard()

        checked_guard()
        from pmi.market_data.index_catalog import get_index
        from pmi.market_data.index_history_calendar import complete_window
        from pmi.market_data import index_series_update
        item = get_index(code)
        window = _periodic[1] if _periodic is not None else complete_window(datetime.now(timezone.utc))
        return index_series_update.start_update(self._root, item, window,
            budget=_periodic[2] if _periodic is not None else self._series_budget, guard=checked_guard,
            remember_locations=lambda: self._remember_index_locations(code),
            accepted=accepted, notify=notify, uncertain=uncertain, trigger=trigger, only_missing=only_missing,
            runtime=self._series_runtime)

    def close_updates(self, timeout: float = 50) -> bool:
        """停止新指数的后续采集并等待本实例worker退出，不干预其他实例。"""
        if self._periodic is not None:
            self._periodic.stop.set()
        if self._activity_runtime is not None:
            self._activity_runtime.close()
        closed = self._series_runtime.close(timeout)
        return closed and (self._periodic is None or self._periodic.close())

    def wait_updates(self, timeout: float = 1) -> bool:
        """只等待本实例指数worker释放资源；不停止任务或持有金融写锁。"""
        return self._series_runtime.wait(timeout)

    def read_index_range(self, index_id: str, start: str, end: str, *,
                         fields: str = "open,high,low,close", snapshot_id: str | None = None) -> dict | None:
        """在单一已核快照中选日期与OHLC字段；不足时拒绝，不拼版本或联网。"""
        from pmi.market_data.index_catalog import get_index
        get_index(index_id)
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except (TypeError, ValueError) as error:
            raise SnapshotError("index_range_invalid: 日期无效") from error
        names = fields.split(",")
        if (first > last or len(names) != len(set(names)) or not names
                or not set(names) <= {"open", "high", "low", "close"}):
            raise SnapshotError("index_range_invalid: 日期或字段未准入")
        view = self.read_daily(index_id, snapshot_id)
        if view is None:
            return None
        value = view["snapshot"]
        if start < value["window"]["start"] or end > value["window"]["end"]:
            raise SnapshotError("coverage_insufficient: 范围超出此固定快照")
        return {"index_id": index_id, "format": view["format"], "snapshot_id": value["snapshot_id"],
                "start": start, "end": end, "fields": names, "unit": "点", "pit_grade": "latest_only",
                "storage_decimals": value.get("storage_decimals", 2),
                "coverage": {"start": value["window"]["start"], "end": value["window"]["end"]},
                "rows": [{"trade_date": row["trade_date"], "values": {name: row[name] for name in names}}
                         for row in value["bars"] if start <= row["trade_date"] <= end]}

    def read_index_calculations(self, index_id: str, snapshot_id: str, formula_version: str) -> dict | None:
        """仅对明确固定v2快照现算；不访问current、不回退旧协议、不产生写入。

        参数在读取之前准入；固定快照由现有只读存储完整重放校验。
        """
        from pmi.market_data.index_calculations import INDEX_IDS, FORMULA_VERSION, calculate
        if index_id not in INDEX_IDS or formula_version != FORMULA_VERSION or not snapshot_id:
            raise SnapshotError("calculation_parameters_invalid")
        view = self.read_daily(index_id, snapshot_id)
        if view is None:
            return None
        if view["format"] != "v2" or view["snapshot"]["snapshot_id"] != snapshot_id:
            raise SnapshotError("calculation_input_mismatch")
        result = calculate(index_id, view["snapshot"], formula_version)
        self.check_location()
        return result


    def read_index_original(self, index_id: str, snapshot_id: str, object_id: str):
        """只读完整价格原件供量额配对，成员校验留在数据层，不扩大HTTP证据接口。"""
        from pmi.market_data.index_catalog import get_index
        from pmi.market_data.index_series_store import read_original
        self.check_location()
        result = read_original(self._root, get_index(index_id), snapshot_id, object_id)
        self.check_location()
        return result

    def activity(self, action: str, *args):
        """量额用例公开门面；显式白名单，不将HTTP对象传给领域或存储。"""
        from pmi.market_data.activity.model import ActivityError
        if self._activity_runtime is None:
            raise ActivityError("activity_disabled", 404)
        if action not in {"current", "fixed", "calculations", "evidence", "start", "lookup", "startup"}:
            raise ActivityError("unknown_activity_operation", 422)
        self.check_location()
        operations = {"current": self._activity_runtime.current, "fixed": self._activity_runtime.fixed,
                      "calculations": self._activity_runtime.calculations, "evidence": self._activity_runtime.evidence,
                      "start": self._activity_runtime.start, "lookup": self._activity_runtime.lookup,
                      "startup": self._activity_runtime.startup}
        if self._periodic is not None:
            if action == "start":
                return self._periodic.manual_activity(*args)
            if action == "startup":
                raise ActivityError("periodic_coordinator_required")
        return operations[action](*args)

    @property
    def activity_anchor_date(self) -> str:
        """本服务实例冻结的市场日期，独立于价格快照，不触发读取或采集。"""
        if self._activity_runtime is None:
            raise ActivityError("activity_disabled", 404)
        return self._activity_runtime.market_anchor_date

    @property
    def activity_market_anchors(self) -> dict[str, str | None]:
        """同服务下两种市场实际发布日；只读，不触发补更。"""
        runtime = self._activity_runtime
        if runtime is None:
            raise ActivityError("activity_disabled", 404)
        return runtime.market_anchors(runtime.clock().date().isoformat())

    @property
    def activity_scope_id(self) -> str | None:
        """公开量额根身份不泄露真实路径，不读金融事实。"""
        return self._activity_runtime.scope if self._activity_runtime else None

    def periodic_status(self) -> dict:
        """读取周期状态，不开启或推进调度。"""
        if self._periodic is None:
            raise ActivityError("periodic_disabled", 404)
        return self._periodic.status()

    def periodic_check(self, indices: tuple[str, ...], config_id: str, instance: str) -> bool:
        """服务生命周期显式调用；只执行启写集合内的固定自动目标。"""
        if self._periodic is None or any(not self._writes.get(x, False) for x in indices):
            raise SnapshotError("periodic_disabled")
        return self._periodic.automatic(indices, config_id, instance)
