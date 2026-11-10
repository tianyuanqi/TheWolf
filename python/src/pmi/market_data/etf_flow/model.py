"""ETF领域输入及版本模型：严格边界、十进制原值、来源与时间分离。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
FIELDS = frozenset({"shares", "nav", "close", "turnover", "volume"})
UNITS = {"shares": "份", "nav": "元/份", "close": "元/份", "turnover": "元", "volume": "份"}
SOURCE_HOSTS = frozenset({"www.sse.com.cn", "query.sse.com.cn", "static.sse.com.cn",
                          "www.huatai-pb.com", "huatai-pb.com", "api.fund.eastmoney.com", "fund.eastmoney.com"})
FORMULA_VERSION = "etf-flow-v1"


class FlowError(ValueError):
    """只携带稳定公开错误码，原异常/路径不穿过业务边界。"""

    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(code)


def canonical(value: object) -> bytes:
    """以确定JSON词法寻址；拒绝非有限数，不使用展示舍入值。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FlowError("etf_duplicate_key", 422)
        result[key] = value
    return result


def decode(raw: bytes | str) -> Any:
    """所有外部JSON拒绝重复键与JavaScript非有限数值。"""
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(FlowError("etf_invalid_input", 422)))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FlowError("etf_invalid_json", 422) from error


def exact(value: Any, keys: set[str] | frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise FlowError("etf_invalid_fields", 422)
    return value


def text(value: Any, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise FlowError("etf_invalid_text", 422)
    return value


def identifier(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", value) is None:
        raise FlowError("etf_invalid_id", 422)
    return value


def object_id(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise FlowError("etf_invalid_reference", 422)
    return value


def day(value: Any) -> str:
    try:
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError as error:
        raise FlowError("etf_invalid_date", 422) from error
    return value


def instant(value: Any) -> datetime:
    """时刻必须显式时区；不得把未知发布时间解释为本机时区。"""
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
        if parsed is None or parsed.tzinfo is None:
            raise ValueError()
    except ValueError as error:
        raise FlowError("etf_invalid_time", 422) from error
    return parsed


def decimal(value: Any, *, minimum: Decimal | None = None, positive: bool = False) -> Decimal:
    """只接受有限十进制字符串；原精度保留，计算不经过二进制浮点。"""
    if not isinstance(value, str) or re.fullmatch(r"-?(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,18})?", value) is None:
        raise FlowError("etf_invalid_decimal", 422)
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise FlowError("etf_invalid_decimal", 422) from error
    if not result.is_finite() or (minimum is not None and result < minimum) or (positive and result <= 0):
        raise FlowError("etf_invalid_decimal", 422)
    return result


def number(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def integer(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise FlowError("etf_invalid_integer", 422)
    return value


def source_url(value: Any) -> str:
    value = text(value, 2048)
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise FlowError("etf_invalid_source", 422) from error
    if (parsed.scheme != "https" or parsed.hostname not in SOURCE_HOSTS or port not in (None, 443)
            or parsed.username is not None or parsed.password is not None or parsed.fragment):
        raise FlowError("etf_invalid_source", 422)
    return value


@dataclass(frozen=True)
class Basis:
    url: str
    report_date: str | None
    published_date: str
    locator: str

    @classmethod
    def parse(cls, raw: Any) -> Basis:
        value = exact(raw, {"url", "report_date", "published_date", "locator"})
        report = day(value["report_date"]) if value["report_date"] is not None else None
        published = day(value["published_date"])
        if report is not None and report > published:
            raise FlowError("etf_invalid_basis", 422)
        return cls(source_url(value["url"]), report, published, text(value["locator"], 500))


@dataclass(frozen=True)
class Member:
    id: str
    code: str
    name: str
    manager: str
    exchange: str
    tracking_index: str
    index_id: str | None
    group: str
    enabled_date: str
    disabled_date: str | None
    basis: Basis

    @classmethod
    def parse(cls, raw: Any) -> Member:
        v = exact(raw, set(cls.__dataclass_fields__))
        enabled = day(v["enabled_date"])
        disabled = day(v["disabled_date"]) if v["disabled_date"] is not None else None
        if disabled is not None and disabled <= enabled:
            raise FlowError("etf_invalid_membership", 422)
        return cls(identifier(v["id"]), identifier(v["code"]), text(v["name"]), text(v["manager"]),
                   text(v["exchange"]), text(v["tracking_index"]),
                   identifier(v["index_id"]) if v["index_id"] is not None else None,
                   text(v["group"], 80), enabled, disabled, Basis.parse(v["basis"]))

    def active(self, on: str) -> bool:
        return self.enabled_date <= on and (self.disabled_date is None or on < self.disabled_date)

    @property
    def group_id(self) -> str:
        return digest(self.group)


@dataclass(frozen=True)
class PoolVersion:
    version: str
    effective_date: str
    confirmed_at: str
    confirmation: str
    change: str
    members: tuple[Member, ...]
    hash: str

    @classmethod
    def parse(cls, raw: Any) -> PoolVersion:
        v = exact(raw, {"version", "effective_date", "confirmed_at", "confirmation", "change", "members"})
        confirmed = instant(v["confirmed_at"])
        effective = day(v["effective_date"])
        if effective < confirmed.astimezone(SHANGHAI).date().isoformat() or not isinstance(v["members"], list):
            raise FlowError("etf_invalid_pool", 422)
        members = tuple(Member.parse(x) for x in v["members"])
        if len({x.id for x in members}) != len(members) or len({(x.exchange, x.code) for x in members}) != len(members):
            raise FlowError("etf_duplicate_member", 422)
        return cls(identifier(v["version"]), effective, v["confirmed_at"], text(v["confirmation"], 1000),
                   text(v["change"], 1000), members, digest(v))


@dataclass(frozen=True)
class RuleVersion:
    version: str
    effective_date: str
    confirmed_at: str | None
    confirmation: str | None
    window: int
    k: Decimal | None
    min_in: Decimal | None
    min_out: Decimal | None
    direction_ratio: Decimal | None
    streak_days: int | None
    hash: str

    @classmethod
    def parse(cls, raw: Any) -> RuleVersion:
        v = exact(raw, set(cls.__dataclass_fields__) - {"hash"})
        confirmed = v["confirmed_at"]
        if (confirmed is None) != (v["confirmation"] is None):
            raise FlowError("etf_invalid_rule", 422)
        if confirmed is not None:
            if day(v["effective_date"]) < instant(confirmed).astimezone(SHANGHAI).date().isoformat():
                raise FlowError("etf_rule_backdated", 422)
            text(v["confirmation"], 1000)
        values = {key: decimal(v[key], positive=True) if v[key] is not None else None
                  for key in ("k", "min_in", "min_out", "direction_ratio")}
        if values["direction_ratio"] is not None and values["direction_ratio"] > 1:
            raise FlowError("etf_invalid_rule", 422)
        return cls(identifier(v["version"]), day(v["effective_date"]), confirmed, v["confirmation"],
                   integer(v["window"], 2), **values,
                   streak_days=integer(v["streak_days"], 2) if v["streak_days"] is not None else None, hash=digest(v))

    @property
    def required_days(self) -> int:
        return max(321, 260 + self.window + 1)

    def confirmed(self, at: str) -> bool:
        return self.confirmed_at is not None and instant(self.confirmed_at) <= instant(at)


@dataclass(frozen=True)
class Configuration:
    pools: tuple[PoolVersion, ...]
    rules: tuple[RuleVersion, ...]
    hash: str
    raw: Mapping[str, Any]

    @classmethod
    def parse(cls, raw: Any) -> Configuration:
        """配置只接受追加版本；每版保留停用成员，身份不得隐式更换。"""
        v = exact(raw, {"format", "pool_versions", "rule_versions"})
        if v["format"] != "etf-flow-config-v1" or not isinstance(v["pool_versions"], list) or not isinstance(v["rule_versions"], list):
            raise FlowError("etf_invalid_config", 422)
        pools = tuple(PoolVersion.parse(x) for x in v["pool_versions"])
        rules = tuple(RuleVersion.parse(x) for x in v["rule_versions"])
        for versions in (pools, rules):
            if (not versions or len({x.version for x in versions}) != len(versions)
                    or any(a.effective_date > b.effective_date for a, b in zip(versions, versions[1:]))):
                raise FlowError("etf_invalid_versions", 422)
        for previous, current in zip(pools, pools[1:]):
            members = {x.id: x for x in current.members}
            for old in previous.members:
                new = members.get(old.id)
                if (new is None or (new.exchange, new.code, new.enabled_date) != (old.exchange, old.code, old.enabled_date)
                        or (old.disabled_date is not None and old.disabled_date != new.disabled_date)):
                    raise FlowError("etf_membership_history_changed", 422)
                if old.disabled_date is None and new.disabled_date is not None and new.disabled_date < current.effective_date:
                    raise FlowError("etf_membership_backdated", 422)
        previous_ids: set[str] = set()
        for pool in pools:
            if any(x.enabled_date < pool.effective_date for x in pool.members if x.id not in previous_ids):
                raise FlowError("etf_membership_backdated", 422)
            previous_ids.update(x.id for x in pool.members)
        return cls(pools, rules, digest(v), decode(canonical(v)))

    def selected(self, at: str) -> tuple[PoolVersion, RuleVersion]:
        """选择固定时点已生效配置；未确认规则仍可显示参数待确认。"""
        point = instant(at)
        on = point.astimezone(SHANGHAI).date().isoformat()
        pools = [v for v in self.pools if v.effective_date <= on and instant(v.confirmed_at) <= point]
        rules = [v for v in self.rules if v.effective_date <= on]
        if not pools or not rules:
            raise FlowError("etf_config_not_effective", 409)
        return pools[-1], rules[-1]

    def extends(self, old: Configuration) -> bool:
        """加载新配置不准修改已保存版本；同名版本也必须保持内容相同。"""
        return (len(self.pools) >= len(old.pools) and len(self.rules) >= len(old.rules)
                and [v.hash for v in self.pools[:len(old.pools)]] == [v.hash for v in old.pools]
                and [v.hash for v in self.rules[:len(old.rules)]] == [v.hash for v in old.rules])


@dataclass(frozen=True)
class Source:
    object_id: str
    publisher: str
    channel: str
    url: str
    retrieved_at: str
    published_at: str | None
    locator: str
    original_unit: str
    precision: str

    @classmethod
    def parse(cls, raw: Any) -> Source:
        v = exact(raw, set(cls.__dataclass_fields__))
        retrieved = instant(v["retrieved_at"])
        published = instant(v["published_at"]) if v["published_at"] is not None else None
        if published is not None and published > retrieved:
            raise FlowError("etf_invalid_source_time", 422)
        return cls(object_id(v["object_id"]), text(v["publisher"]), text(v["channel"]), source_url(v["url"]),
                   v["retrieved_at"], v["published_at"], text(v["locator"], 1000), text(v["original_unit"]), text(v["precision"]))


@dataclass(frozen=True)
class FieldValue:
    value: Decimal
    source: Source


@dataclass(frozen=True)
class Input:
    member_id: str
    date: str
    fields: Mapping[str, FieldValue]
    revision_reason: str
    hash: str
    raw: Mapping[str, Any]

    @classmethod
    def parse(cls, raw: Any) -> Input:
        """每字段必须与本条归属日相同且使用明确规范单位；缺项不填零。"""
        v = exact(raw, {"member_id", "date", "fields", "revision_reason"})
        on = day(v["date"])
        if not isinstance(v["fields"], dict) or not set(v["fields"]) <= FIELDS or not v["fields"]:
            raise FlowError("etf_invalid_input", 422)
        fields = {}
        for key, raw_field in v["fields"].items():
            item = exact(raw_field, {"value", "date", "unit", "source"})
            if day(item["date"]) != on or item["unit"] != UNITS[key]:
                raise FlowError("etf_input_date_or_unit_mismatch", 422)
            source = Source.parse(item["source"])
            if instant(source.retrieved_at).astimezone(SHANGHAI).date().isoformat() < on:
                raise FlowError("etf_future_input", 422)
            fields[key] = FieldValue(decimal(item["value"], minimum=Decimal(0), positive=key in {"nav", "close"}), source)
        return cls(identifier(v["member_id"]), on, fields, text(v["revision_reason"], 500), digest(v), decode(canonical(v)))

    def value(self, key: str) -> Decimal | None:
        field = self.fields.get(key)
        return field.value if field is not None else None


@dataclass(frozen=True)
class Adjustment:
    member_id: str
    kind: str
    start: str
    end: str
    factor: Decimal
    tail: Decimal
    source_ids: tuple[str, ...]
    confirmed_at: str
    confirmation: str

    @classmethod
    def parse(cls, raw: Any) -> Adjustment:
        v = exact(raw, set(cls.__dataclass_fields__))
        start, end = day(v["start"]), day(v["end"])
        factor, tail = decimal(v["factor"], positive=True), decimal(v["tail"])
        instant(v["confirmed_at"])
        if (v["kind"] not in {"normal", "adjustment"} or start > end
                or (v["kind"] == "normal" and (factor != 1 or tail != 0))
                or (v["kind"] == "adjustment" and start != end)
                or not isinstance(v["source_ids"], list) or not v["source_ids"]):
            raise FlowError("etf_invalid_adjustment", 422)
        return cls(identifier(v["member_id"]), v["kind"], start, end, factor, tail,
                   tuple(object_id(x) for x in v["source_ids"]), v["confirmed_at"], text(v["confirmation"], 1000))


def adjustment_for(rows: tuple[Adjustment, ...], member: str, on: str, at: str) -> Adjustment | None:
    """仅采用固定版本已确认覆盖；精确调整覆盖普通区间，同类冲突拒绝。"""
    matches = [x for x in rows if x.member_id == member and x.start <= on <= x.end
               and instant(x.confirmed_at) <= instant(at)]
    specific = [x for x in matches if x.kind == "adjustment"]
    normal = [x for x in matches if x.kind == "normal"]
    if len(specific) > 1 or len(normal) > 1:
        raise FlowError("etf_adjustment_conflict", 422)
    return (specific or normal or [None])[0]
