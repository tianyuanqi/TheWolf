"""量额身份、来源门槛和不可变配置；缺少证据不得靠启写开关准入。"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import TypedDict

INDEX_IDS = ('sse:000001:price', 'szse:399001:price', 'szse:399006:price', 'sse:000688:price')
MARKET = 'cn-a-turnover'
TWO_MARKET = 'cn-a-turnover-sse-szse'
MARKET_IDS = (MARKET, TWO_MARKET)
SERIES = (*INDEX_IDS, *MARKET_IDS)
MARKETS = ('sse', 'szse', 'bse')
TWO_POLICY = 'activity-source-policy-sse-szse-v1'
THREE_POLICY = 'activity-source-policy-sse-szse-bse-v1'
THREE_SOURCE_KEYS = ('sse-a-json', 'szse-a-json', 'bse-a-json')
TWO_SOURCE_KEYS = ('sse-a-json', 'szse-a-json')
MARKET_MAX_BYTES = 65536
VERSION = 'activity-facts-v1'
BINDING = 'exact-available-price-values-v1'
MAX_BYTES = 1048576


class ActivityError(ValueError):
    """仅公开稳定错误码，异常不含真实路径或源载荷。"""
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


def canonical(value: object) -> bytes:
    """唯一规范序列化，用于事实和配置身份；拒绝NaN。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def identifier(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch('[a-f0-9]{64}', value) is None:
        raise ActivityError('invalid_activity_id', 422)
    return value


def number(value: str, *, integer: bool = False) -> Decimal:
    """有界非负十进制原数值；禁止指数、布尔、浮点和非有限值。"""
    if not isinstance(value, str) or re.fullmatch(r'(?:0|[1-9][0-9]{0,24})(?:\.[0-9]{1,12})?', value) is None:
        raise ActivityError('invalid_source_number')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ActivityError('invalid_source_number') from error
    if integer and result != result.to_integral_value():
        raise ActivityError('invalid_source_number')
    return result


def source_number(value: str, *, integer: bool = False) -> Decimal:
    """官方JSON可用科学计数法；先精确展开，再沿用位数／整数界限。

    只接受有界非负数字词法，原词法仍留在Fact.raw_value及原件中。
    不经float，不改变金额刻度，也不放宽规范事实number的语法。
    """
    if not isinstance(value, str) or re.fullmatch(r'(?:0|[1-9][0-9]{0,24})(?:\.[0-9]{1,12})?(?:[eE][+-]?[0-9]{1,2})?', value) is None:
        raise ActivityError('invalid_source_number')
    return number(format(Decimal(value), 'f'), integer=integer)


def unique(pairs: list[tuple[str, object]]) -> dict:
    """本地及外部JSON重复键均拒绝。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ActivityError('duplicate_json_key', 422)
        result[key] = value
    return result


def load(content: bytes, *, source: bool = False) -> dict:
    try:
        value = json.loads(content, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                           **({'parse_float': str, 'parse_int': str} if source else {}))
    except (ValueError, UnicodeDecodeError) as error:
        raise ActivityError('invalid_json') from error
    if not isinstance(value, dict):
        raise ActivityError('invalid_json')
    return value


@dataclass(frozen=True)
class Rule:
    """代码固定的来源策略；证据门槛不能由HTTP或本地配置布尔开关绕过。"""
    source: str
    amount_unit: str
    amount_quantum: str
    volume_unit: str | None
    scope: str
    gaps: tuple[str, ...]
    admitted: bool = False
    version: str = 'activity-source-policy-v1'


def rule(series: str, version: str | None = None) -> Rule:
    """固定官方单源策略；v1保留原未准入事实，未知版本拒绝重放。

    v2依据已确认B/S1来源证据及2026-10-31单源决定，仅放行已适配指数。
    G4独立校核缺口仍存在；启写权限和网络预算不能由准入推导。
    """
    if version not in (None, 'activity-source-policy-v1', 'activity-source-policy-v2', TWO_POLICY, THREE_POLICY):
        raise ActivityError('source_policy_version_unknown')
    if series == 'bse-a-json':
        if version not in (None, THREE_POLICY):
            raise ActivityError('source_policy_version_unknown')
        return Rule('bse', '元', '0.01', None, 'BSE-stocks-xxzrlx-2;trading-method-scope-unverified',
                    ('G1', 'G4'), True, THREE_POLICY)
    if series in TWO_SOURCE_KEYS:
        if version not in (None, TWO_POLICY):
            raise ActivityError('source_policy_version_unknown')
        market = series.split('-')[0]
        return Rule(market, '亿元', '0.01', None,
                    'SSE-main-A+STAR' if market == 'sse' else 'SZSE-main-A+ChiNext',
                    ('G3' if market == 'sse' else 'G2', 'G4'), True, TWO_POLICY)
    if series in INDEX_IDS:
        if version in (TWO_POLICY, THREE_POLICY):
            raise ActivityError('source_policy_version_unknown')
        csi = series.startswith('sse:')
        admitted = version != 'activity-source-policy-v1'
        return Rule('csindex' if csi else 'cnindex-raw', '亿元' if csi else '元',
                    '0.01', '股', 'index-constituents; trading-method-scope-unverified', ('G4',),
                    admitted=admitted, version='activity-source-policy-v2' if admitted else 'activity-source-policy-v1')
    gaps = {'sse': ('G3', 'G4'), 'szse': ('G2', 'G4'), 'bse': ('G1', 'G4')}
    if series not in gaps:
        raise ActivityError('unknown_activity_series', 422)
    if version not in (None, 'activity-source-policy-v1'):
        raise ActivityError('source_policy_version_unknown')
    return Rule(series, '亿元' if series == 'sse' else '元' if series == 'szse' else 'unknown',
                '0.01' if series != 'bse' else 'unknown', None, 'A-shares; trading-method-scope-unverified', gaps[series])


@dataclass(frozen=True)
class Options:
    """显式量额根与权限；默认零网络预算，不隐式继承价格授权。"""
    root: Path
    write_series: tuple[str, ...] = ()
    blocked_series: tuple[tuple[str, str], ...] = ()
    max_attempts: int = 0
    max_bytes: int = 0
    budget_cycle: str = 'activity-budget-v1'
    budget_ledger: Path | None = None
    startup_series: tuple[str, ...] = ()
    ledger_identity: tuple[int, int] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('量额根必须是显式绝对目录')
        if len(set(self.write_series)) != len(self.write_series) or not set(self.write_series) <= set(SERIES):
            raise ValueError('量额启写系列无效')
        if len(set(self.startup_series)) != len(self.startup_series) or not set(self.startup_series) <= set(self.write_series):
            raise ValueError('量额启动集合必须唯一且属于启写集合')
        if len({x[0] for x in self.blocked_series}) != len(self.blocked_series):
            raise ValueError('量额阻断系列重复')
        for series, evidence in self.blocked_series:
            if series not in SERIES:
                raise ValueError('量额阻断系列无效')
            identifier(evidence)
        if any(type(x) is not int or not 0 <= x <= 10**9 for x in (self.max_attempts, self.max_bytes)):
            raise ValueError('量额预算无效')
        if (self.max_attempts or self.max_bytes) and self.budget_ledger is None:
            raise ValueError('非零量额预算须显式指定已有持久账本')
        if self.budget_ledger is not None and (not self.budget_ledger.is_absolute() or not self.budget_ledger.is_file()):
            raise ValueError('量额预算账本必须已存在')
        if self.budget_ledger is not None:
            from pmi.market_data.read_only import checked_path
            checked_path(self.budget_ledger)
            info = self.budget_ledger.stat()
            if info.st_nlink != 1:
                raise ValueError('量额账本不得硬链接')
            object.__setattr__(self, 'ledger_identity', (info.st_dev, info.st_ino))
        if not re.fullmatch('[a-z0-9-]{1,64}', self.budget_cycle):
            raise ValueError('量额预算周期无效')

    def policy(self) -> dict:
        """全部来源与网络限制进入连接身份；已消耗预算由持久账本执行。"""
        sources = [*INDEX_IDS, *MARKETS, *THREE_SOURCE_KEYS]
        return {'version': VERSION, 'binding_version': BINDING, 'window_years': 3,
                'sources': [{'series': s, **rule(s).__dict__, 'gaps': list(rule(s).gaps)} for s in sources],
                'network': {'max_attempts': self.max_attempts, 'max_bytes': self.max_bytes,
                            'max_response_bytes': MAX_BYTES, 'timeout_seconds': 15, 'deadline_seconds': 60,
                            'minimum_interval_seconds': 1, 'redirects': False, 'retries': 0,
                            'max_operation_requests': 2200, 'budget_cycle': self.budget_cycle,
                            'ledger_version': 'source-bounded-reservation-v2',
                            'ledger_scope': digest(str(self.budget_ledger)) if self.budget_ledger else None},
                'parser': {'version': 'activity-parser-v1', 'max_rows': 1100, 'xlsx_members': 32,
                           'xlsx_expanded_bytes': 4 * MAX_BYTES, 'xlsx_cells': 20000}}


class Fact(TypedDict):
    value: str | None
    unit: str
    reason: str | None
    raw_value: str | None
    raw_unit: str
    source_quantum: str
    object_id: str | None
    locator: str | None


class Row(TypedDict):
    trade_date: str
    volume: Fact
    amount: Fact


@dataclass(frozen=True)
class Original:
    """观察回执与不可变源字节；发布时间未知不推断。"""
    source: str
    content: bytes
    url: str
    started_at: str
    completed_at: str

    @property
    def object_id(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class SourceRef(TypedDict):
    source: str
    object_id: str
    url: str


class ObservedSource(SourceRef):
    """原件获取回执；发布时间未知保持null，不从获取时间推断。"""
    started_at: str
    completed_at: str
    published_at: None


class Observation(TypedDict):
    """独立于金融内容V的发布观察；由提交凭据及不可变回执核验。"""
    series_id: str
    activity_id: str
    price_snapshot_id: str | None
    observation_id: str
    request_id: str
    sources: list[ObservedSource]


class MarketRow(TypedDict):
    trade_date: str
    components: dict[str, list[Fact]]


class Snapshot(TypedDict, total=False):
    """不可变规范事实；activity_id为读取外壳，不参与自身摘要。"""
    schema_version: str
    series_id: str
    activity_id: str
    price_snapshot_id: str | None
    anchor_date: str
    window: dict
    calendar_version: str
    calendar_dates: list[str]
    market_calendars: dict[str, list[str] | None]
    completion_basis: dict
    source_policy_version: str
    parser_version: str
    pit_grade: str
    currency: str
    source_scope: str
    source_revision_relation: str
    source_revision_id: None
    binding: dict | None
    sources: list[SourceRef]
    observations: list[Observation]
    rows: list[Row] | list[MarketRow]


class Operation(TypedDict):
    """持久请求关联；completed只能由固定事实和提交凭据证明。"""
    series_id: str
    request_id: str
    config_id: str
    instance_id: str
    target: str
    signature: str
    state: str
    activity_id: str | None
    observation_id: str | None
    reason: str | None
    recovered_from_instance: str | None
