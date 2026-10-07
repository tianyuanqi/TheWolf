"""沪深300价格指数双源契约，Decimal点位及固定原件行定位。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
from urllib.parse import urlencode

from pmi.index_calendar import completion_basis, trading_days
from pmi.snapshot import SnapshotError

Source = Literal["eastmoney", "tencent", "csindex"]
SOURCES: tuple[Source, ...] = ("tencent", "csindex")
LEGACY_SOURCES: tuple[Source, ...] = ("eastmoney", "csindex")
URLS = {"eastmoney": "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        "tencent": "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
        "csindex": "https://www.csindex.com.cn/csindex-home/perf/index-perf"}
INSTRUMENT = {"id": "csi:000300:price", "code": "000300", "name": "沪深300",
              "provider": "中证", "return_type": "price", "frequency": "daily"}
FIELDS = ("open", "high", "low", "close")
LEGACY_CONTRACT = {"version": "csi300-exact-ohlc-v1", "normalization": "decimal-two-places-v1",
            "sources": {source: URLS[source] for source in LEGACY_SOURCES}, "unused_fields": ["volume", "amount", "changePct", "peg"],
            "publication_time": "unknown", "identity_basis": "PLAN-P01 official factsheet; H00300/N00300 excluded"}
CONTRACT = {**LEGACY_CONTRACT, "version": "csi300-tencent-exact-ohlc-v2",
            "sources": {source: URLS[source] for source in SOURCES},
            "unused_fields": ["volume", "amount", "changePct", "peg", "prec", "version"],
            "tencent_branch": "day", "request_qfq_semantics": "SDK compatibility parameter; price index day only",
            "date_selection": "exclude earlier rows; reject later, duplicate or unordered dates; retain original array index"}


def contract_sources(version: str) -> tuple[Source, ...]:
    """按已登记策略选择来源；旧版本仅供固定原件重放和只读核验。

    Args:
        version: 固定快照的来源契约版本，未知版本不能推定为当前来源。
    Returns:
        对应双源的固定顺序。
    Raises:
        SnapshotError: 版本未登记。
    """
    if version == CONTRACT["version"]:
        return SOURCES
    if version == LEGACY_CONTRACT["version"]:
        return LEGACY_SOURCES
    raise SnapshotError("未知指数来源契约版本")


class SourceNotReady(SnapshotError):
    """合法结构仅缺窗口末尾连续日期，不降低目标窗口。"""


@dataclass(frozen=True)
class SourceRow:
    """标准点位与未经舍入的原值/JSON定位。"""

    trade_date: str
    open: str
    high: str
    low: str
    close: str
    locator: str
    raw_values: dict[str, str]


@dataclass(frozen=True)
class Original:
    """原件内容及一次获取观察；时间不参与内容快照身份。"""

    source: Source
    content: bytes
    started_at: str
    completed_at: str


def digest(content: bytes) -> str:
    """计算固定对象的SHA-256，不作为Git版本使用。"""
    return hashlib.sha256(content).hexdigest()


def canonical(value: object) -> bytes:
    """固定UTF-8清单序列化，禁止非有限JSON数值。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def utc(value: str) -> str:
    """统一观察时区身份，拒绝无时区时间。"""
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise SnapshotError("观察时间必须含时区")
    return stamp.astimezone(timezone.utc).isoformat()


def source_url(source: Source, days: tuple[str, ...]) -> str:
    """构造固定来源/窗口URL；东财URL只用于验证旧归档，不授予出站权限。"""
    if source not in URLS:
        raise SnapshotError("未知指数来源")
    if source == "tencent":
        return URLS[source] + "?" + urlencode({"_var": "kline_dayqfq",
            "param": f"sh000300,day,{days[0]},{days[-1]},640,qfq", "r": "0.8205512681390605"})
    params = ({"secid": "1.000300", "fields1": "f1,f2,f3,f4,f5", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
               "klt": "101", "fqt": "0", "beg": days[0].replace("-", ""), "end": days[-1].replace("-", "")}
              if source == "eastmoney" else {"indexCode": "000300", "startDate": days[0].replace("-", ""), "endDate": days[-1].replace("-", "")})
    return URLS[source] + "?" + urlencode(params)


def point(value: object) -> str:
    """保真解析正点位；仅允许尾零超过两位，绝不舍入后掩盖差异。"""
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise SnapshotError("点位必须使用原始十进制值")
    try:
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or number > Decimal("1000000000000"):
            raise SnapshotError("点位必须有限且为正，超出支持范围")
        normalized = number.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as error:
        raise SnapshotError("非法十进制点位") from error
    if number != normalized:
        raise SnapshotError("点位超过两位非零精度")
    return format(normalized, ".2f")


def _row(day: str, values: dict, locator: str) -> SourceRow:
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise SnapshotError("非法交易日")
    date.fromisoformat(day)
    normalized = {name: point(values[name]) for name in FIELDS}
    if not (Decimal(normalized["low"]) <= min(Decimal(normalized["open"]), Decimal(normalized["close"]))
            <= max(Decimal(normalized["open"]), Decimal(normalized["close"])) <= Decimal(normalized["high"])):
        raise SnapshotError(f"{day}: 高低不包开收")
    return SourceRow(day, **normalized, locator=locator,
                     raw_values={name: str(values[name]) for name in FIELDS})


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """腾讯JSON拒绝重复键，避免身份或day分支被后一个同名键覆盖。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError("tencent: 重复JSON字段")
        result[key] = value
    return result


def parse_source(source: Source, content: bytes) -> tuple[SourceRow, ...]:
    """核验来源身份并显式映射OHLC，JSON小数从原始文本进入Decimal。

    Raises:
        SnapshotError: 身份、成功状态、结构、日期或点位不符合契约。
    """
    try:
        if source not in URLS:
            raise SnapshotError("未知指数来源")
        text = content.decode("utf-8")
        if source == "tencent" and not text.lstrip().startswith("{"):
            match = re.fullmatch(r"\s*kline_dayqfq=(\{.*\});?\s*", text, re.S)
            if match is None:
                raise SnapshotError("tencent: 仅允许指定变量的JSON，不执行脚本")
            text = match[1]
        raw = json.loads(text, parse_float=Decimal, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                         **({"object_pairs_hook": _unique_fields} if source == "tencent" else {}))
        rows = []
        if source == "tencent":
            data = raw["data"]["sh000300"]
            identity = data["qt"]["sh000300"]
            if type(raw["code"]) is not int or raw["code"] != 0 or not isinstance(identity, list) or identity[1:3] != ["沪深300", "000300"]:
                raise SnapshotError("tencent: 指数身份或成功状态不符")
            if not isinstance(data.get("day"), list) or "qfqday" in data or "hfqday" in data:
                raise SnapshotError("tencent: 只准入day分支，不降级至复权分支")
            for index, fields in enumerate(data["day"]):
                if not isinstance(fields, list) or len(fields) < 5 or not all(isinstance(value, str) for value in fields[:5]):
                    raise SnapshotError("tencent: day字段结构不符")
                # 腾讯同样按日期、开、收、高、低返回；原数组下标不因裁剪改变。
                rows.append(_row(fields[0], dict(zip(("open", "close", "high", "low"), fields[1:5])), f"$.data.sh000300.day[{index}]"))
        elif source == "eastmoney":
            data = raw["data"]
            if raw["rc"] != 0 or any(data.get(k) != v for k, v in {"code": "000300", "market": 1, "name": "沪深300", "decimal": 2}.items()):
                raise SnapshotError("eastmoney: 指数身份或成功状态不符")
            for index, line in enumerate(data["klines"]):
                fields = line.split(",")
                if len(fields) != 8:
                    raise SnapshotError("eastmoney: kline字段结构不符")
                # 东财原顺序为开、收、高、低，与标准OHLC顺序不同。
                rows.append(_row(fields[0], dict(zip(("open", "close", "high", "low"), fields[1:5])), f"$.data.klines[{index}]"))
        else:
            if raw["code"] != "200" or raw["msg"] != "Success" or not isinstance(raw["data"], list):
                raise SnapshotError("csindex: 成功状态不符")
            for index, item in enumerate(raw["data"]):
                if item["indexCode"] != "000300" or item["indexNameCn"] != "沪深300" or item["indexNameCnAll"] != "沪深300指数":
                    raise SnapshotError("csindex: 指数身份不符")
                compact = item["tradeDate"]
                if not isinstance(compact, str) or not re.fullmatch(r"\d{8}", compact):
                    raise SnapshotError("csindex: 非法交易日")
                rows.append(_row(f"{compact[:4]}-{compact[4:6]}-{compact[6:]}", item, f"$.data[{index}]"))
        days = [row.trade_date for row in rows]
        if len(set(days)) != len(days):
            raise SnapshotError(f"{source}: 重复交易日")
        if source == "tencent" and days != sorted(days):
            raise SnapshotError("tencent: 日期未按原数组递增")
        return tuple(sorted(rows, key=lambda row: row.trade_date))
    except SnapshotError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation) as error:
        raise SnapshotError(f"{source}: 非法来源结构（{type(error).__name__}）") from error


def validate_window(days: tuple[str, ...]) -> None:
    """只准入完整260日已核验交易日窗口，不接受任意工作日集合。"""
    if len(days) != 260 or days != trading_days(date.fromisoformat(days[0]), date.fromisoformat(days[-1])):
        raise SnapshotError("指数窗口必须为260个完整、唯一、递增的已核验交易日")


def build_manifest(days: tuple[str, ...], originals: tuple[Original, ...], *,
                   contract_version: str = CONTRACT["version"]) -> dict:
    """精确对账两个独立来源并生成不含观察时刻的不可变内容清单。

    缺中间日期/额外日期为失败，仅末尾连续缺失为未就绪；两源不互补。
    腾讯只排除窗口前的日期，完整原件和原数组定位保持；旧策略仅由只读核验显式指定。
    """
    validate_window(days)
    sources = contract_sources(contract_version)
    contract = CONTRACT if sources == SOURCES else LEGACY_CONTRACT
    if tuple(item.source for item in originals) != sources:
        raise SnapshotError("需要两份固定来源原件且顺序一致")
    parsed = [parse_source(item.source, item.content) for item in originals]
    if sources == SOURCES:
        if any(row.trade_date > days[-1] for row in parsed[0]):
            raise SnapshotError("tencent: 存在晚于冻结截止日的日期")
        parsed[0] = tuple(row for row in parsed[0] if row.trade_date >= days[0])
    incomplete = []
    for source, rows in zip(sources, parsed):
        actual = tuple(row.trade_date for row in rows)
        if actual != days:
            if len(actual) < len(days) and actual == days[:len(actual)]:
                incomplete.append(f"{source}: 缺末尾日期 {days[len(actual)]}—{days[-1]}")
            else:
                missing = sorted(set(days) - set(actual))
                extra = sorted(set(actual) - set(days))
                raise SnapshotError(f"{source}: 内部缺日或额外日期 missing={missing} extra={extra}")
    overlap_left = {row.trade_date: row for row in parsed[0]}
    overlap_right = {row.trade_date: row for row in parsed[1]}
    for day in overlap_left.keys() & overlap_right.keys():
        for field in FIELDS:
            if getattr(overlap_left[day], field) != getattr(overlap_right[day], field):
                raise SnapshotError(f"双源不一致: {day} {field}")
    # 两源都完成结构及重叠值校验后才能将合法尾部缺失分类为未就绪。
    if incomplete:
        raise SourceNotReady("source_not_ready: " + "; ".join(incomplete))
    evidence = [{"source": item.source, "object_id": digest(item.content), "url": source_url(item.source, days),
                 "rows": [asdict(row) for row in rows]} for item, rows in zip(originals, parsed)]
    bars = []
    for left, right in zip(*parsed):
        for field in FIELDS:
            if getattr(left, field) != getattr(right, field):
                raise SnapshotError(f"双源不一致: {left.trade_date} {field} {sources[0]}={getattr(left, field)} csindex={getattr(right, field)}")
        bars.append({"trade_date": left.trade_date, **{field: getattr(left, field) for field in FIELDS},
                     "evidence_refs": [{"object_id": item["object_id"], "locator": rows[len(bars)].locator} for item, rows in zip(evidence, parsed)]})
    return {"schema_version": "csi300-price-snapshot-v1", "instrument": INSTRUMENT, "unit": "点", "timezone": "Asia/Shanghai",
            "pit_grade": "latest_only", "calendar_dates": list(days), "window": {"start": days[0], "end": days[-1], "expected_count": 260, "actual_count": 260},
            "bars": bars, "summary": summarize(bars), "completion_basis": completion_basis(), "source_contract": contract, "evidence": evidence}


def summarize(bars: list[dict]) -> dict:
    """按相邻预期交易日收盘计算百分比，最后才ROUND_HALF_UP两位。

    首行缺前收为null；来源changePct不参与计算。零统一0.00。
    """
    last = bars[-1]
    change = None
    if len(bars) > 1:
        change = (Decimal(last["close"]) / Decimal(bars[-2]["close"]) - 1) * 100
        change = change.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"trade_date": last["trade_date"], "close": last["close"],
            "daily_change_pct": ("0.00" if change == 0 else format(change, ".2f")) if change is not None else None,
            "reason": "first_row_without_previous_close" if change is None else None,
            "formula_version": "adjacent-expected-close-pct-half-up-v1",
            "input_refs": [{"trade_date": bar["trade_date"], "close": bar["close"], "evidence_refs": bar["evidence_refs"]} for bar in bars[-2:]]}
