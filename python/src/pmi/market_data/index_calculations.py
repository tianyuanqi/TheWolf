"""固定价格快照的只读计算；没有网络、持久化、缓存或当前时钟依赖。"""
from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from datetime import date, timedelta
import re
from typing import Literal, TypedDict

from pmi.market_data import SnapshotError
from pmi.market_data.index_history_calendar import from_manifest_window, period_calendar
from pmi.market_data.price_formulas import CHANGE_V1, MA_V1, change_pct_v1, close_sma_v1, positive_price

FORMULA_VERSION = "index-price-calculations-v1"
PERIODS = (5, 10, 20, 30, 60, 120, 180, 250)
INDEX_IDS = frozenset({"sse:000001:price", "szse:399001:price", "szse:399006:price", "sse:000688:price"})
Frequency = Literal["daily", "weekly", "monthly"]


class InputRef(TypedDict):
    """计算所用的固定快照及实际价格日期范围。"""
    index_id: str
    snapshot_id: str
    start: str | None
    end: str


class Parameters(TypedDict):
    frequency: Frequency
    period: str


class Scalar(TypedDict):
    """每个金融计算独立携带公式、参数、单位和输入引用。"""
    value: str | None
    reason: str | None
    unit: str
    formula_version: str
    parameters: Parameters
    input_ref: InputRef


class Bar(TypedDict):
    period_start: str
    period_end: str
    start: str
    end: str
    open: str
    high: str
    low: str
    close: str
    sample_count: int
    complete: bool
    incomplete_reasons: list[str]
    formula_version: str
    input_ref: InputRef
    change_pct: Scalar
    ma: list[Scalar]


class Availability(TypedDict):
    period: int
    available: bool
    sample_count: int
    required_count: int
    reason: str | None


class Series(TypedDict):
    frequency: Frequency
    ma_availability: list[Availability]
    rows: list[Bar]


class Calculations(TypedDict):
    index_id: str
    snapshot_id: str
    formula_version: str
    calendar_version: str
    anchor_date: str
    pit_grade: str
    unit: str
    daily: Series
    weekly: Series
    monthly: Series
    performance: dict[str, Scalar]


def _ref(index_id: str, snapshot: dict, start: str | None, end: str) -> InputRef:
    return {"index_id": index_id, "snapshot_id": snapshot["snapshot_id"], "start": start, "end": end}


def _scalar(value: str | None, reason: str | None, unit: str, formula: str,
            frequency: Frequency, period: str, reference: InputRef) -> Scalar:
    return {"value": value, "reason": reason, "unit": unit, "formula_version": formula,
            "parameters": {"frequency": frequency, "period": period}, "input_ref": reference}


def _bounds(day: str, frequency: Frequency) -> tuple[date, date]:
    current = date.fromisoformat(day)
    if frequency == "daily":
        return current, current
    if frequency == "weekly":
        start = current - timedelta(days=current.weekday())
        return start, start + timedelta(days=6)
    return current.replace(day=1), current.replace(day=monthrange(current.year, current.month)[1])


def _aggregate(index_id: str, snapshot: dict, frequency: Frequency, *, source_end: str | None = None) -> tuple[list[dict], list[bool]]:
    groups: list[list[dict]] = []
    for row in snapshot["bars"]:
        if not groups or _bounds(groups[-1][0]["trade_date"], frequency) != _bounds(row["trade_date"], frequency):
            groups.append([])
        groups[-1].append(row)
    rows, eligible = [], []
    for position, group in enumerate(groups):
        first, last = group[0]["trade_date"], group[-1]["trade_date"]
        start, end = _bounds(first, frequency)
        expected = period_calendar(start, end, snapshot["calendar_version"])
        reasons = []
        if expected is None:
            reasons.append("calendar_unknown")
        else:
            if expected and expected[0] < first:
                reasons.append("window_start_truncated")
            if expected and expected[-1] > last:
                reasons.append("period_in_progress")
        # 末周期的临时收盘已获准参与；历史周期须有已知期末收盘。
        eligible.append((last == source_end if source_end is not None else position == len(groups) - 1)
                        or bool(expected and expected[-1] == last))
        rows.append({"period_start": start.isoformat(), "period_end": end.isoformat(),
            "start": first, "end": last, "open": group[0]["open"], "close": group[-1]["close"],
            "high": max(group, key=lambda item: positive_price(item["high"]))["high"],
            "low": min(group, key=lambda item: positive_price(item["low"]))["low"],
            "sample_count": len(group), "complete": not reasons, "incomplete_reasons": reasons,
            "formula_version": "raw-daily-price-v1" if frequency == "daily" else "calendar-ohlc-v1",
            "input_ref": _ref(index_id, snapshot, first, last)})
    return rows, eligible


def _series(index_id: str, snapshot: dict, frequency: Frequency, *, periods: tuple[int, ...] = PERIODS,
            source_end: str | None = None, availability: list[dict] | None = None) -> Series:
    rows, eligible = _aggregate(index_id, snapshot, frequency, source_end=source_end)
    for i, row in enumerate(rows):
        previous = rows[i - 1] if i and eligible[i - 1] else None
        value = change_pct_v1(row["close"], previous["close"]) if previous else None
        row["change_pct"] = _scalar(value, None if previous else "missing_previous_close", "%",
            CHANGE_V1 if frequency == "daily" else "period-close-pct-half-up-v1", frequency, "1",
            _ref(index_id, snapshot, previous["end"] if previous else None, row["end"]))
        row["ma"] = []
        for period in periods:
            enough = i + 1 >= period and all(eligible[i + 1 - period:i + 1])
            sample = rows[i + 1 - period:i + 1] if enough else []
            row["ma"].append(_scalar(close_sma_v1([item["close"] for item in sample]) if enough else None,
                None if enough else "insufficient_samples", "点", MA_V1, frequency, str(period),
                _ref(index_id, snapshot, sample[0]["end"] if enough else None, row["end"])))
    count = sum(eligible)
    return {"frequency": frequency, "ma_availability": availability if availability is not None else [
        {"period": period, "available": count >= period, "sample_count": count, "required_count": period,
         "reason": None if count >= period else "insufficient_samples"} for period in PERIODS], "rows": rows}


def _performance(index_id: str, snapshot: dict) -> dict[str, Scalar]:
    bars = snapshot["bars"]
    target = bars[-1]
    result = {}
    for size in (5, 20, 60):
        previous = bars[-size - 1] if len(bars) > size else None
        result[f"day_{size}"] = _scalar(change_pct_v1(target["close"], previous["close"]) if previous else None,
            None if previous else "insufficient_samples", "%", "trading-window-close-pct-v1", "daily", str(size),
            _ref(index_id, snapshot, previous["trade_date"] if previous else None, target["trade_date"]))
    day = date.fromisoformat(target["trade_date"])
    base = day.replace(year=day.year - 1, day=min(day.day, monthrange(day.year - 1, day.month)[1])).isoformat()
    position = bisect_right([item["trade_date"] for item in bars], base) - 1
    previous = bars[position] if position >= 0 else None
    result["year_1"] = _scalar(change_pct_v1(target["close"], previous["close"]) if previous else None,
        None if previous else "missing_year_baseline", "%", "natural-year-close-pct-v1", "daily", "1y",
        _ref(index_id, snapshot, previous["trade_date"] if previous else None, target["trade_date"]))
    return result


def _check_input(index_id: str, snapshot: dict) -> None:
    # 固定输入已由存储层完整重放；此处再次检查计算前提，拒绝坏值而非返回零。
    from_manifest_window(snapshot)
    if snapshot["instrument"]["id"] != index_id or not re.fullmatch(r"[a-f0-9]{64}", snapshot["snapshot_id"]):
        raise SnapshotError("calculation_input_mismatch")
    bars = snapshot["bars"]
    if [item["trade_date"] for item in bars] != snapshot["calendar_dates"]:
        raise SnapshotError("calculation_calendar_mismatch")
    _check_prices(snapshot)
    # overview也保留发布摘要逐位校验；调用同一个冻结涨跌公式，不写第二套。
    latest_change = change_pct_v1(bars[-1]['close'], bars[-2]['close']) if len(bars) > 1 else None
    if latest_change != snapshot['summary']['daily_change_pct']:
        raise SnapshotError('calculation_summary_mismatch')


def _check_prices(snapshot: dict) -> None:
    """完整和范围计算共用价格精度/OHLC检查；不把显示裁剪当成源窗口。"""
    digits = snapshot["storage_decimals"]
    if digits not in (2, 4):
        raise SnapshotError("invalid_calculation_precision")
    for bar in snapshot['bars']:
        for field in ("open", "high", "low", "close"):
            if not isinstance(bar[field], str) or not re.fullmatch(r"[0-9]{1,40}\.\d{" + str(digits) + "}", bar[field]):
                raise SnapshotError("invalid_calculation_price")
            positive_price(bar[field])
        if not positive_price(bar["low"]) <= min(positive_price(bar["open"]), positive_price(bar["close"])) <= max(
                positive_price(bar["open"]), positive_price(bar["close"])) <= positive_price(bar["high"]):
            raise SnapshotError("invalid_calculation_ohlc")


def _header(index_id: str, snapshot: dict) -> dict:
    return {"index_id": index_id, "snapshot_id": snapshot["snapshot_id"], "formula_version": FORMULA_VERSION,
        "calendar_version": snapshot["calendar_version"], "anchor_date": snapshot["window"]["anchor_date"],
        "pit_grade": "latest_only", "unit": "点"}


def _calculate_v1(index_id: str, snapshot: dict) -> Calculations:
    _check_input(index_id, snapshot)
    daily = _series(index_id, snapshot, "daily")
    if daily["rows"][-1]["change_pct"]["value"] != snapshot["summary"]["daily_change_pct"]:
        raise SnapshotError("calculation_summary_mismatch")
    return {**_header(index_id, snapshot), "daily": daily,
        "weekly": _series(index_id, snapshot, "weekly"), "monthly": _series(index_id, snapshot, "monthly"),
        "performance": _performance(index_id, snapshot)}


def calculate_overview(index_id: str, snapshot: dict, formula_version: str) -> dict:
    """同输入、同公式的概况投影；完整前提校验，不生成未请求的周期逐行结果。"""
    if index_id not in INDEX_IDS or formula_version != FORMULA_VERSION:
        raise SnapshotError('calculation_parameters_invalid')
    _check_input(index_id, snapshot)
    return {**_header(index_id, snapshot), 'performance': _performance(index_id, snapshot)}


def calculate(index_id: str, snapshot: dict, formula_version: str) -> Calculations:
    """按显式集合版本读取时现算，未知版本拒绝，不静默采用最新版本。

    Args:
        index_id: 本批准入的四指数固定身份。
        snapshot: 存储层已校验的完整固定v2快照，不得拼接current。
        formula_version: 受支持的冻结集合版本，旧版本分支不得删除或改义。
    Returns:
        独立新对象；不修改输入，无持久化或联网。
    """
    if index_id not in INDEX_IDS or formula_version != FORMULA_VERSION:
        raise SnapshotError("calculation_parameters_invalid")
    return _calculate_v1(index_id, snapshot)
