"""ETF有限授权账本：独立于既有额度，出站前持久扣额，失败不退。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from .model import (FlowError, SOURCE_HOSTS, canonical, day, decode, digest, exact, identifier,
                    instant, integer, object_id, source_url, text)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pmi.market_data.storage.etf_store import Store


@dataclass(frozen=True)
class Grant:
    id: str
    confirmed_at: str
    confirmation: str
    expires_at: str
    members: tuple[str, ...]
    start: str
    end: str
    domains: tuple[str, ...]
    max_requests: int
    max_bytes: int
    response_limit: int
    interval_seconds: int
    timeout_seconds: int
    hash: str
    raw: dict[str, Any]

    @classmethod
    def parse(cls, raw: Any) -> Grant:
        """授权必须完整显式给定；没有默认成员、日期、重试或无限预算。"""
        v = exact(raw, set(cls.__dataclass_fields__) - {"hash", "raw"})
        confirmed, expires = instant(v["confirmed_at"]), instant(v["expires_at"])
        start, end = day(v["start"]), day(v["end"])
        if (expires <= confirmed or start > end or not isinstance(v["members"], list) or not v["members"]
                or not isinstance(v["domains"], list) or not v["domains"]
                or not set(v["domains"]) <= SOURCE_HOSTS
                or len(set(v["domains"])) != len(v["domains"]) or len(set(v["members"])) != len(v["members"])):
            raise FlowError("etf_invalid_grant", 422)
        limit = integer(v["response_limit"], 1)
        timeout = integer(v["timeout_seconds"], 1)
        if limit > 8 * 1024 * 1024 or timeout > 30:
            raise FlowError("etf_invalid_grant", 422)
        return cls(identifier(v["id"]), v["confirmed_at"], text(v["confirmation"], 1000), v["expires_at"],
                   tuple(identifier(x) for x in v["members"]), start, end, tuple(v["domains"]),
                   integer(v["max_requests"]), integer(v["max_bytes"]), limit,
                   integer(v["interval_seconds"], 3), timeout, digest(v), decode(canonical(v)))


@dataclass(frozen=True)
class Request:
    kind: str
    member_id: str
    start: str
    end: str
    url: str

    @property
    def key(self) -> str:
        return digest({"kind": self.kind, "member_id": self.member_id, "start": self.start, "end": self.end, "url": self.url})


class Budget:
    """一个授权ID只初始化一次；改变配置或重启不能获得新的余额。"""

    def __init__(self, store: Store, grant: Grant, clock: Callable[[], datetime] | None = None):
        self.store, self.grant = store, grant
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.key = digest({"kind": "etf-finite-grant-v1", "scope": store.scope, "id": grant.id})

    def initialize(self) -> None:
        """只供明确授权的初始化CLI；不能从构造、GET或更新隐式调用。"""
        if self.store.journal(self.key)[0] is not None:
            raise FlowError("etf_grant_already_initialized")
        value = {"format": "etf-flow-budget-v1", "scope": self.store.scope, "grant": self.grant.raw,
                 "attempts": [], "last_started_at": None}
        self.store.write_journal(self.key, value, None)

    def read(self) -> tuple[str, dict[str, Any]]:
        """从尝试明细重新求额度，不信任可被遗漏的计数器或空账本。"""
        reference, value = self.store.journal(self.key)
        if reference is None:
            raise FlowError("etf_grant_not_initialized")
        v = exact(value, {"format", "scope", "grant", "attempts", "last_started_at"})
        if (v["format"] != "etf-flow-budget-v1" or v["scope"] != self.store.scope
                or v["grant"] != self.grant.raw or not isinstance(v["attempts"], list)):
            raise FlowError("etf_budget_invalid")
        ids: set[str] = set()
        last = None
        previous = None
        for raw in v["attempts"]:
            a = exact(raw, {"id", "operation_key", "request_key", "started_at", "closed_at", "limit", "actual_bytes", "success", "object_id"})
            identifier(a["id"])
            object_id(a["operation_key"])
            object_id(a["request_key"])
            point = instant(a["started_at"])
            if last is not None and point < last:
                raise FlowError("etf_budget_invalid")
            if previous is not None and (previous["closed_at"] is None or
                    (point - instant(previous["closed_at"])).total_seconds() < self.grant.interval_seconds):
                raise FlowError("etf_budget_invalid")
            last = point
            if a["id"] in ids or a["limit"] != self.grant.response_limit:
                raise FlowError("etf_budget_invalid")
            ids.add(a["id"])
            if a["actual_bytes"] is not None and integer(a["actual_bytes"]) > a["limit"]:
                raise FlowError("etf_budget_invalid")
            if a["success"] is not None and type(a["success"]) is not bool:
                raise FlowError("etf_budget_invalid")
            if a["object_id"] is not None:
                object_id(a["object_id"])
            if a["closed_at"] is not None and instant(a["closed_at"]) < point:
                raise FlowError("etf_budget_invalid")
            if a["success"] is not None and (a["actual_bytes"] is None or a["object_id"] is None or a["closed_at"] is None):
                raise FlowError("etf_budget_invalid")
            previous = a
        if (len(ids) > self.grant.max_requests or len(ids) * self.grant.response_limit > self.grant.max_bytes
                or v["last_started_at"] != (v["attempts"][-1]["started_at"] if v["attempts"] else None)):
            raise FlowError("etf_budget_invalid")
        return reference, v

    def usage(self) -> dict[str, Any]:
        _, v = self.read()
        attempts = v["attempts"]
        return {"grant_id": self.grant.id, "requests": len(attempts),
                "reserved_bytes": len(attempts) * self.grant.response_limit,
                "actual_bytes": sum(x["actual_bytes"] or 0 for x in attempts),
                "unknown_attempts": sum(x["success"] is None for x in attempts),
                "max_requests": self.grant.max_requests, "max_bytes": self.grant.max_bytes,
                "expires_at": self.grant.expires_at}

    def preflight(self, requests: tuple[Request, ...]) -> None:
        """整批先核对固定授权；预算到期只阻止出站，不阻止原请求核验。"""
        _, v = self.read()
        now = self.clock()
        if now.tzinfo is None:
            raise FlowError("etf_clock_invalid")
        if v["last_started_at"] is not None and now < instant(v["last_started_at"]):
            raise FlowError("etf_clock_regressed")
        if requests and not instant(self.grant.confirmed_at) <= now <= instant(self.grant.expires_at):
            raise FlowError("etf_grant_expired")
        if requests and any(a["closed_at"] is None for a in v["attempts"]):
            raise FlowError("etf_unsettled_attempt")
        for request in requests:
            source_url(request.url)
            if (request.kind not in {"shares", "quote", "nav"} or request.member_id not in self.grant.members
                    or not self.grant.start <= day(request.start) <= day(request.end) <= self.grant.end
                    or urlsplit(request.url).hostname not in self.grant.domains):
                raise FlowError("etf_request_not_authorized", 403)
        count = len(v["attempts"]) + len(requests)
        if count > self.grant.max_requests or count * self.grant.response_limit > self.grant.max_bytes:
            raise FlowError("etf_budget_exhausted")

    def charge(self, request: Request, operation_key: str) -> str:
        """每次出站前保存未知回执占位；失败与进程中断均不退还预留量。"""
        self.preflight((request,))
        reference, v = self.read()
        point = self.clock()
        if v["attempts"] and (point - instant(v["attempts"][-1]["closed_at"])).total_seconds() < self.grant.interval_seconds:
            raise FlowError("etf_request_too_soon")
        attempt = uuid4().hex
        now = point.isoformat()
        v["attempts"].append({"id": attempt, "operation_key": object_id(operation_key), "request_key": request.key,
                              "started_at": now, "closed_at": None, "limit": self.grant.response_limit, "actual_bytes": None,
                              "success": None, "object_id": None})
        v["last_started_at"] = now
        self.store.write_journal(self.key, v, reference)
        return attempt

    def settle(self, attempt: str, raw: bytes, success: bool) -> str:
        """原件先保存，后关联账本；同一次回执只能确认一次且不能扩限。"""
        reference, value = self.read()
        found = [x for x in value["attempts"] if x["id"] == attempt]
        if len(found) != 1 or found[0]["closed_at"] is not None or len(raw) > self.grant.response_limit or type(success) is not bool:
            raise FlowError("etf_invalid_receipt")
        point = self.clock()
        if point.tzinfo is None or point < instant(found[0]["started_at"]):
            raise FlowError("etf_clock_regressed")
        source = self.store.put(raw)
        found[0].update(actual_bytes=len(raw), success=success, object_id=source, closed_at=point.isoformat())
        self.store.write_journal(self.key, value, reference)
        return source

    def close_unknown(self, operation_key: str) -> None:
        """仅明确恢复调用：结束失去回执的尝试，保留未知字节和全部已扣额度。"""
        self.store._require_writer()
        object_id(operation_key)
        reference, value = self.read()
        now = self.clock()
        if now.tzinfo is None:
            raise FlowError("etf_clock_invalid")
        changed = False
        for row in value["attempts"]:
            if row["operation_key"] == operation_key and row["closed_at"] is None:
                if now < instant(row["started_at"]):
                    raise FlowError("etf_clock_regressed")
                row["closed_at"] = now.isoformat()
                changed = True
        if changed:
            self.store.write_journal(self.key, value, reference)
