"""六指数价格快照契约：原件解析、精度核验及确定性重放。"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import TypedDict
from urllib.parse import urlencode

from pmi.market_data import SnapshotError
from pmi.market_data.price_formulas import CHANGE_V1, change_pct_v1
from pmi.market_data.index_catalog import CATALOG_VERSION, ROUNDING_LIMIT, IndexDefinition, get_index
from pmi.market_data.index_history_calendar import FrozenWindow, from_manifest_window, validate_window

SCHEMA_VERSION = "index-series-price-snapshot-v2"
SOURCES = ("csindex", "cnindex", "eastmoney")
FIELDS = ("open", "high", "low", "close")
_CNI_ITEMS = ["timestamp", "current", "high", "open", "low", "close", "chg", "percent", "amount", "volume", "avg"]


class MismatchDetail(TypedDict):
    """单日单字段的完整差异证据。"""

    date: str
    field: str
    official_raw: str
    comparison_value: str
    eastmoney_raw: str


class SourceMismatch(SnapshotError):
    """价格核验失败，保留全部差异而非截断的摘要。"""

    def __init__(self, details: list[MismatchDetail]):
        super().__init__("source_mismatch")
        self.details = details


class SourceNotReady(SnapshotError):
    """身份、结构及重叠价格通过，但某来源缺连续尾部日期。"""


@dataclass(frozen=True)
class Original:
    """单次来源响应原字节与独立观察记录。"""

    source: str
    content: bytes
    started_at: str
    completed_at: str
    url: str


@dataclass(frozen=True)
class _SourceRow:
    trade_date: str
    values: tuple[str, str, str, str]
    raw_values: tuple[str, str, str, str]
    comparison_values: tuple[str, str, str, str]
    locator: str


class EvidenceRow(TypedDict):
    """公开证据保留原值、存储值和比较值。"""

    trade_date: str
    open: str
    high: str
    low: str
    close: str
    locator: str
    raw_values: dict[str, str]
    comparison_values: dict[str, str]


class Evidence(TypedDict):
    """可由单个原件确定性恢复的来源证据。"""

    source: str
    object_id: str
    url: str
    rows: list[EvidenceRow]


class SeriesManifest(TypedDict):
    """存储层内容寻址的稳定契约，不包含运行或观察元数据。"""

    schema_version: str
    catalog_version: str
    instrument: dict
    source_policy_version: str
    calendar_version: str
    unit: str
    timezone: str
    pit_grade: str
    storage_decimals: int
    window: dict
    calendar_dates: list[str]
    completion_basis: dict
    verification: dict
    bars: list[dict]
    summary: dict
    evidence: list[Evidence]


class _JsonNumber(str):
    """保留 JSON 数值 token，避免 float 及字符串类型混淆。"""


def canonical(value: object) -> bytes:
    """生成内容寻址所用的稳定 UTF-8 JSON 字节。"""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise SnapshotError("invalid_canonical_json") from error


def digest(content: bytes) -> str:
    """计算原件或规范内容的 SHA-256。"""
    return hashlib.sha256(content).hexdigest()


def utc(stamp: str) -> str:
    """核验带时区观察时刻并转换为 UTC；不进入内容 hash。"""
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("naive")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, AttributeError) as error:
        raise SnapshotError("invalid_observation_time") from error


def _registered(index: IndexDefinition) -> None:
    if not isinstance(index, IndexDefinition) or get_index(index.index_id) != index:
        raise SnapshotError("unknown_index_definition")


def source_url(index: IndexDefinition, source: str, window: FrozenWindow) -> str:
    """从注册身份和实际交易日边界构造唯一白名单 URL。"""
    _registered(index)
    validate_window(window)
    if source not in index.sources:
        raise SnapshotError("wrong_source")
    if source == "csindex":
        endpoint = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
        parameters = {"indexCode": index.code, "startDate": window.start.replace("-", ""), "endDate": window.end.replace("-", "")}
    elif source == "cnindex":
        endpoint = "https://hq.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat"
        parameters = {"indexCode": index.code, "startDate": window.start, "endDate": window.end, "frequency": "day"}
    else:
        endpoint = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        parameters = {"secid": f"{index.eastmoney_market}.{index.code}", "fields1": "f1,f2,f3,f4,f5",
                      "fields2": "f51,f52,f53,f54,f55,f56,f57,f58", "klt": 101, "fqt": 0,
                      "beg": window.start.replace("-", ""), "end": window.end.replace("-", "")}
    return endpoint + "?" + urlencode(parameters)


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError("duplicate_json_member")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise SnapshotError("invalid_json_number")


def _load(content: bytes) -> dict:
    try:
        if type(content) is not bytes:
            raise TypeError("bytes required")
        result = json.loads(content.decode("utf-8"), parse_int=_JsonNumber, parse_float=_JsonNumber,
                            parse_constant=_invalid_constant, object_pairs_hook=_unique)
        if not isinstance(result, dict):
            raise ValueError("object required")
        return result
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise SnapshotError("invalid_source_json") from error


def _integer(value: object, expected: int) -> bool:
    return type(value) is _JsonNumber and value == str(expected)


def _literal(value: object, expected: str | None) -> bool:
    return type(value) is str and value == expected


def _point(value: object, decimals: int, *, number: bool) -> tuple[str, str]:
    if type(value) is not (_JsonNumber if number else str):
        raise SnapshotError("invalid_price_type")
    raw = str(value)
    if len(raw) > 40 or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", raw) is None:
        raise SnapshotError("invalid_price")
    try:
        with localcontext() as context:
            context.prec = 48
            value_decimal = Decimal(raw)
            if not value_decimal.is_finite() or not 0 < value_decimal <= Decimal("1000000000000"):
                raise SnapshotError("invalid_price")
            exact = value_decimal.quantize(Decimal(1).scaleb(-decimals))
            if value_decimal != exact:
                raise SnapshotError("unsupported_price_precision")
            return format(exact, f".{decimals}f"), raw
    except InvalidOperation as error:
        raise SnapshotError("invalid_price") from error


def _row(day: str, values: list[object], locator: str, decimals: int, *, number: bool) -> _SourceRow:
    try:
        if type(day) is not str or date.fromisoformat(day).isoformat() != day:
            raise ValueError("date required")
    except (ValueError, TypeError) as error:
        raise SnapshotError("invalid_trade_date") from error
    points = tuple(_point(value, decimals, number=number) for value in values)
    stored = tuple(point[0] for point in points)
    raw = tuple(point[1] for point in points)
    opening, high, low, close = map(Decimal, stored)
    if not low <= opening <= high or not low <= close <= high:
        raise SnapshotError("invalid_ohlc")
    with localcontext() as context:
        context.prec = 48
        comparison = tuple(format(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f") for value in stored)
    return _SourceRow(day, stored, raw, comparison, locator)


def _parse(index: IndexDefinition, window: FrozenWindow, original: Original) -> list[_SourceRow]:
    if original.source not in index.sources or original.url != source_url(index, original.source, window):
        raise SnapshotError("wrong_source_url")
    started, completed = utc(original.started_at), utc(original.completed_at)
    if datetime.fromisoformat(started.replace("Z", "+00:00")) > datetime.fromisoformat(completed.replace("Z", "+00:00")):
        raise SnapshotError("invalid_observation_order")
    root = _load(original.content)
    rows = []
    try:
        data = root["data"]
        if original.source == "csindex":
            if not (_literal(root["code"], "200") and _literal(root["msg"], "Success") and root["success"] is True and isinstance(data, list)):
                raise SnapshotError("invalid_csindex_response")
            identities = {"indexCode": index.code, "indexNameCn": index.name, "indexNameCnAll": index.full_name,
                          "indexNameEn": index.english_name, "indexNameEnAll": index.english_full_name}
            for position, item in enumerate(data):
                if not isinstance(item, dict) or not all(_literal(item[key], value) for key, value in identities.items()):
                    raise SnapshotError("wrong_index_identity")
                day = item["tradeDate"]
                if type(day) is not str or re.fullmatch(r"[0-9]{8}", day) is None:
                    raise SnapshotError("invalid_trade_date")
                rows.append(_row(f"{day[:4]}-{day[4:6]}-{day[6:]}", [item[field] for field in FIELDS], f"data[{position}]", index.storage_decimals, number=True))
        elif original.source == "cnindex":
            if not (_integer(root["code"], 200) and _literal(root["message"], "") and isinstance(data, dict)):
                raise SnapshotError("invalid_cnindex_response")
            if not all(_literal(data[key], value) for key, value in {"indexCode": index.code, "indexName": index.name, "indexEName": index.english_name}.items()):
                raise SnapshotError("wrong_index_identity")
            if data["item"] != _CNI_ITEMS or any(type(value) is not str for value in data["item"]):
                raise SnapshotError("unknown_cnindex_fields")
            if not isinstance(data["data"], list) or not _integer(root["total"], len(data["data"])):
                raise SnapshotError("invalid_cnindex_total")
            for position, item in enumerate(data["data"]):
                if not isinstance(item, list) or len(item) != len(_CNI_ITEMS):
                    raise SnapshotError("invalid_cnindex_row")
                rows.append(_row(item[0], [item[column] for column in (3, 2, 4, 5)], f"data.data[{position}]", index.storage_decimals, number=True))
        else:
            if not (_integer(root["rc"], 0) and isinstance(data, dict)):
                raise SnapshotError("invalid_eastmoney_response")
            if not (_literal(data["code"], index.code) and _literal(data["name"], index.name) and _integer(data["market"], index.eastmoney_market) and _integer(data["decimal"], 2)):
                raise SnapshotError("wrong_index_identity")
            if not isinstance(data["klines"], list):
                raise SnapshotError("invalid_eastmoney_rows")
            for position, line in enumerate(data["klines"]):
                if type(line) is not str or len(line.split(",")) != 8:
                    raise SnapshotError("invalid_eastmoney_row")
                parts = line.split(",")
                rows.append(_row(parts[0], [parts[column] for column in (1, 3, 4, 2)], f"data.klines[{position}]", 2, number=False))
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise SnapshotError("invalid_source_shape") from error
    days = [row.trade_date for row in rows]
    if not rows or len(days) != len(set(days)):
        raise SnapshotError("empty_or_duplicate_dates")
    if days != sorted(days, reverse=original.source == "cnindex"):
        raise SnapshotError("invalid_source_order")
    if set(days) - set(window.dates):
        raise SnapshotError("unexpected_trade_dates")
    return sorted(rows, key=lambda row: row.trade_date)


def _evidence(original: Original, rows: list[_SourceRow]) -> Evidence:
    return {"source": original.source, "object_id": digest(original.content), "url": original.url,
            "rows": [{"trade_date": row.trade_date, **dict(zip(FIELDS, row.values)), "locator": row.locator,
                      "raw_values": dict(zip(FIELDS, row.raw_values)), "comparison_values": dict(zip(FIELDS, row.comparison_values))} for row in rows]}


def summarize(bars: list[dict]) -> dict:
    """用官方存储价格计算相邻预期交易日涨跌，最终百分比 HALF_UP 两位。"""
    current = bars[-1]
    references = [{"trade_date": row["trade_date"], "close": row["close"], "evidence_refs": row["evidence_refs"]} for row in bars[-2:]]
    change = None
    reason = "first_row_without_previous_close"
    if len(bars) > 1:
        change = change_pct_v1(current["close"], bars[-2]["close"])
        reason = None
    return {"trade_date": current["trade_date"], "close": current["close"], "daily_change_pct": change,
            "reason": reason, "formula_version": CHANGE_V1, "input_refs": references}


def build_manifest(index: IndexDefinition, window: FrozenWindow, originals: tuple[Original, ...] | list[Original]) -> SeriesManifest:
    """解析二源、完整核验后构造不含观察时间的确定性快照。

    Args:
        index: 固定注册身份。
        window: 上海当日冻结的完整三自然年窗口。
        originals: 按官方、东财次序排列的原始字节及观察记录。

    Returns:
        只含已核验价格、日历和来源证据的 manifest。
    """
    _registered(index)
    validate_window(window)
    if not isinstance(originals, (tuple, list)) or len(originals) != 2 or not all(isinstance(original, Original) for original in originals) or tuple(original.source for original in originals) != index.sources:
        raise SnapshotError("wrong_source_set")
    parsed = [_parse(index, window, original) for original in originals]
    by_day = [{row.trade_date: row for row in rows} for rows in parsed]
    differences: list[MismatchDetail] = []
    for day in window.dates:
        if day not in by_day[0] or day not in by_day[1]:
            continue
        official, verified = by_day[0][day], by_day[1][day]
        for position, field in enumerate(FIELDS):
            if official.comparison_values[position] != verified.values[position]:
                differences.append({"date": day, "field": field, "official_raw": official.raw_values[position],
                                    "comparison_value": official.comparison_values[position], "eastmoney_raw": verified.raw_values[position]})
    if differences:
        raise SourceMismatch(differences)
    for rows in parsed:
        days = tuple(row.trade_date for row in rows)
        if days != window.dates[:len(days)]:
            raise SnapshotError("incomplete_source_calendar")
    if any(len(rows) != len(window.dates) for rows in parsed):
        raise SourceNotReady("source_not_ready")
    evidence = [_evidence(original, rows) for original, rows in zip(originals, parsed)]
    bars = [{"trade_date": day, **dict(zip(FIELDS, by_day[0][day].values)),
             "evidence_refs": [{"source": item["source"], "object_id": item["object_id"], "locator": by_day[position][day].locator}
                               for position, item in enumerate(evidence)]} for day in window.dates]
    rounding = index.storage_decimals == 4
    return {"schema_version": SCHEMA_VERSION, "catalog_version": CATALOG_VERSION,
            "instrument": {"id": index.index_id, "code": index.code, "name": index.name, "full_name": index.full_name,
                           "provider": index.provider, "return_type": "price", "frequency": "daily"},
            "source_policy_version": index.source_policy_version, "calendar_version": window.calendar_version,
            "unit": "点", "timezone": "Asia/Shanghai", "pit_grade": "latest_only", "storage_decimals": index.storage_decimals,
            "window": window.as_dict(), "calendar_dates": list(window.dates), "completion_basis": window.completion_basis,
            "verification": {"mode": "rounding_aware" if rounding else "exact", "primary_source": index.sources[0],
                             "verification_source": "eastmoney", "comparison_decimals": 2,
                             "comparison_rounding": "ROUND_HALF_UP" if rounding else None,
                             "result": "matched", "limitations": [ROUNDING_LIMIT] if rounding else []},
            "bars": bars, "summary": summarize(bars), "evidence": evidence}


def rebuild_manifest(index: IndexDefinition, manifest: dict, originals: tuple[Original, ...] | list[Original]) -> dict:
    """按历史 D 重建完整内容并逐字节核对，拒绝派生事实被改写。"""
    rebuilt = build_manifest(index, from_manifest_window(manifest), originals)
    if canonical(rebuilt) != canonical(manifest):
        raise SnapshotError("manifest_replay_mismatch")
    return rebuilt


def parse_evidence(index: IndexDefinition, manifest: dict, original: Original) -> Evidence:
    """恢复并核对一份来源证据；调用者须先重放完整二源 manifest。"""
    _registered(index)
    if (manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("catalog_version") != CATALOG_VERSION
            or manifest.get("instrument", {}).get("id") != index.index_id
            or manifest.get("source_policy_version") != index.source_policy_version):
        raise SnapshotError("wrong_manifest_identity")
    window = from_manifest_window(manifest)
    result = _evidence(original, _parse(index, window, original))
    matches = [item for item in manifest.get("evidence", []) if item.get("source") == original.source]
    if len(matches) != 1 or canonical(matches[0]) != canonical(result) or len(result["rows"]) != len(window.dates):
        raise SnapshotError("evidence_replay_mismatch")
    return result
