"""独立服务的显式冻结配置及公开身份；不探测业务数据库。"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import re

from pmi.market_data import MarketData
from pmi.market_data import ActivityOptions, ACTIVITY_SERIES
from pmi.market_data.periodic_budget import PeriodicOptions

SERVICE_ID = "thewolf-local-service"
SERVICE_VERSION = "0.1.0"
IDENTITY_FORMAT = "wolf-config-v2"


def digest(value: dict) -> str:
    """按固定配置的UTF-8规范序列化计算公开摘要。"""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class ServiceConfig:
    """只接受本机浏览器显式配置；不能靠环境继承打开写入。"""

    data_root: Path
    port: int
    allowed_origins: tuple[str, ...]
    index_write_ids: tuple[str, ...] = field(default=(), kw_only=True)
    startup_index_ids: tuple[str, ...] = field(default=(), kw_only=True)
    index_max_attempts: int = field(default=16, kw_only=True)
    index_max_bytes: int = field(default=16 * 1024 * 1024, kw_only=True)
    activity_options: ActivityOptions | None = field(default=None, kw_only=True)
    periodic_options: PeriodicOptions | None = field(default=None, kw_only=True)
    market_data: MarketData = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.port) is not int or not 0 < self.port < 65536:
            raise ValueError("服务端口无效")
        if "WOLF_INDEX_BUDGET_LEDGER" in os.environ:
            raise ValueError("独立服务不接受继承的预算账本覆盖")
        if not self.allowed_origins or len(set(self.allowed_origins)) != len(self.allowed_origins):
            raise ValueError("必须显式提供互不重复的浏览器Origin")
        for origin in self.allowed_origins:
            match = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", origin)
            if not match or not 0 < int(match[1]) < 65536 or int(match[1]) == self.port:
                raise ValueError("仅接受独立端口的精确本机浏览器Origin")
        object.__setattr__(self, "allowed_origins", tuple(sorted(self.allowed_origins)))
        for values in (self.index_write_ids, self.startup_index_ids):
            if (not isinstance(values, tuple) or any(not isinstance(value, str) or ":" not in value for value in values)
                    or len(set(values)) != len(values)):
                raise ValueError("指数特性配置必须是互不重复的canonical身份")
        if not set(self.startup_index_ids) <= set(self.index_write_ids):
            raise ValueError("启动补齐指数必须显式启写")
        object.__setattr__(self, "index_write_ids", tuple(sorted(self.index_write_ids)))
        object.__setattr__(self, "startup_index_ids", tuple(sorted(self.startup_index_ids)))
        object.__setattr__(self, "market_data", MarketData(self.data_root,
            {key: True for key in self.index_write_ids},
            index_max_attempts=self.index_max_attempts, index_max_bytes=self.index_max_bytes, activity_options=self.activity_options, periodic_options=self.periodic_options))

    def check_location(self) -> None:
        """委托数据层复核冻结定位，不在HTTP配置层拼接业务路径。"""
        self.market_data.check_location()

    def check_write_paths(self) -> None:
        """委托数据层复核既有写入定位；HTTP写开关仍在协议边界判断。"""
        self.market_data.check_write_paths()

    @property
    def authority(self) -> str:
        return f"127.0.0.1:{self.port}"


    @property
    def data_scope_id(self) -> str:
        return self.market_data.scope_id

    @property
    def config_id(self) -> str:
        return digest({"identity_format": IDENTITY_FORMAT, "data_scope_id": self.data_scope_id,
                       "backend_authority": self.authority,
                       "allowed_origins": list(self.allowed_origins), "contract_major": 2})

    def public_descriptor(self) -> dict:
        """从同一计算器给浏览器受控预期，不输出根路径或接纳ready自证。"""
        raw = files("pmi.http_contract").joinpath("openapi.resource").read_bytes()
        return {"endpoint": "http://" + self.authority, "service_id": SERVICE_ID,
                "service_version": SERVICE_VERSION, "contract_version": "2.0.0",
                "contract_sha256": hashlib.sha256(raw).hexdigest(),
                "identity_format": IDENTITY_FORMAT, "data_scope_id": self.data_scope_id,
                "config_id": self.config_id}

    @property
    def index_config_id(self) -> str:
        """新指数特性单独绑定权限、补齐和预算；绑定当前协议主版本。"""
        return digest({"identity_format": "wolf-index-config-v2", "data_scope_id": self.data_scope_id,
                       "write_indices": list(self.index_write_ids), "startup_indices": list(self.startup_index_ids),
                       "policy": self.market_data.index_policy, "backend_authority": self.authority,
                       "allowed_origins": list(self.allowed_origins), "contract_major": 2})

    def public_index_descriptor(self) -> dict:
        """生成新特性可信本地连接描述；不以服务ready替代调用者的预期。"""
        old = self.public_descriptor()
        return {key: old[key] for key in ("endpoint", "service_id", "service_version", "contract_version",
                                         "contract_sha256", "data_scope_id")} | {
            "identity_format": "wolf-index-config-v2", "config_id": self.index_config_id,
            "feature_version": "index-series-v2", "write_indices": list(self.index_write_ids),
            "startup_indices": list(self.startup_index_ids), "policy": self.market_data.index_policy}


    @property
    def activity_config_id(self) -> str:
        """独立量额身份绑定价格范围、启写、预算、来源策略与撤回，不改变旧摘要。"""
        if self.activity_options is None:
            return digest({"identity_format": "wolf-activity-config-v1", "enabled": False})
        return digest({"identity_format": "wolf-activity-config-v1", "feature_version": "market-activity-v1",
                       "data_scope_id": self.data_scope_id, "price_index_config_id": self.index_config_id,
                       "activity_scope_id": self.market_data.activity_scope_id, "series": list(ACTIVITY_SERIES),
                       "write_series": sorted(self.activity_options.write_series), "startup_series": sorted(self.activity_options.startup_series),
                       "blocked_series": [{"series_id": s, "evidence_id": e, "reason": "source_withdrawn"}
                                          for s, e in sorted(self.activity_options.blocked_series)],
                       "policy": self.activity_options.policy(), "backend_authority": self.authority,
                       "allowed_origins": list(self.allowed_origins), "contract_major": 2})

    def public_activity_descriptor(self) -> dict:
        """受控启动配置生成独立预期；不能从ready学习根、权限或预算。"""
        from pmi.market_data import ActivityError
        if self.activity_options is None:
            raise ActivityError("activity_disabled", 404)
        old = self.public_descriptor()
        return {key: old[key] for key in ("endpoint", "service_id", "service_version", "contract_version",
                                         "contract_sha256", "data_scope_id")} | {
            "identity_format": "wolf-activity-config-v1", "feature_version": "market-activity-v1",
            "config_id": self.activity_config_id, "price_index_config_id": self.index_config_id,
            "activity_scope_id": self.market_data.activity_scope_id, "series": list(ACTIVITY_SERIES),
            "write_series": sorted(self.activity_options.write_series), "startup_series": sorted(self.activity_options.startup_series),
            "blocked_series": [{"series_id": s, "evidence_id": e, "reason": "source_withdrawn"}
                               for s, e in sorted(self.activity_options.blocked_series)],
            "policy": self.activity_options.policy()}
