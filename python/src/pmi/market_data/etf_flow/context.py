"""从既有只读用例取得背景，在ETF发布时冻结；不采集、不替代ETF输入。"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

from pmi.market_data import ActivityError, ReadUnavailable, SnapshotError
from pmi.market_data.activity.calculations import formula_for
from pmi.market_data.activity.model import MARKET, TWO_MARKET
from pmi.market_data.index_calculations import FORMULA_VERSION as INDEX_FORMULA, INDEX_IDS
from pmi.market_data.price_formulas import change_pct_v1
from .calendar import preceding_window
from .model import Configuration, FlowError, day, exact, identifier, instant, number, object_id

if TYPE_CHECKING:
    from pmi.market_data import MarketData

FORMAT = "etf-flow-context-v1"


def empty() -> dict[str, Any]:
    return {"format": FORMAT, "rows": []}


def validate(raw: Any) -> dict[str, Any]:
    """重开固定背景时验证日期、有限值和输入归属；缺失保持空值。"""
    value = exact(raw, {"format", "rows"})
    if value["format"] != FORMAT or not isinstance(value["rows"], list):
        raise FlowError("etf_invalid_context")
    dates = []
    for entry in value["rows"]:
        entry = exact(entry, {"date", "indices", "market", "reason"})
        dates.append(day(entry["date"]))
        if not isinstance(entry["indices"], list) or entry["reason"] not in {None, "context_not_available", "context_partial"}:
            raise FlowError("etf_invalid_context")
        ids = set()
        for row in entry["indices"]:
            exact(row, {"index_id", "snapshot_id", "formula_version", "date", "return_1", "return_5", "input_basis", "calculated_at"})
            if row["index_id"] not in INDEX_IDS or row["index_id"] in ids:
                raise FlowError("etf_invalid_context")
            ids.add(row["index_id"])
            _validate_row(row, entry["date"], "snapshot_id", ("return_1", "return_5"))
        row = entry["market"]
        if row is not None:
            exact(row, {"series_id", "activity_id", "formula_version", "date", "scope_label", "turnover", "ratio_20", "input_basis", "calculated_at"})
            if row["series_id"] not in {MARKET, TWO_MARKET} or row["scope_label"] != ("沪深" if row["series_id"] == TWO_MARKET else "沪深北"):
                raise FlowError("etf_invalid_context")
            _validate_row(row, entry["date"], "activity_id", ("turnover", "ratio_20"))
    if dates != sorted(set(dates)):
        raise FlowError("etf_invalid_context")
    return value


def _validate_row(row: dict, on: str, key: str, values: tuple[str, ...]) -> None:
    object_id(row[key]); identifier(row["formula_version"]); instant(row["calculated_at"])
    if row["date"] != on or row["input_basis"] != "posthoc_context":
        raise FlowError("etf_invalid_context")
    for field in values:
        if row[field] is not None:
            try:
                numeric = Decimal(row[field])
            except (ValueError, TypeError, ArithmeticError) as error:
                raise FlowError("etf_invalid_context") from error
            if not isinstance(row[field], str) or not numeric.is_finite():
                raise FlowError("etf_invalid_context")


def capture(parent: MarketData, config: Configuration, end: str, selected_at: str) -> dict[str, Any]:
    """发布时只读现存价格/量额固定结果，并保存260日的事后背景。

    对应指数来自成员配置；市场优先采用已有三市结果，缺失时采用明确标记的
    两市结果。各日只使用该日以前的输入，单个背景失败不使ETF发布失败。
    """
    pool, _ = config.selected(selected_at)
    wanted = {m.index_id for m in pool.members if m.index_id is not None}
    dates = preceding_window(end, 260)
    entries = {on: {"date": on, "indices": [], "market": None, "reason": None} for on in dates}
    for index in sorted(wanted & set(INDEX_IDS)):
        try:
            fixed = parent.read_daily(index)
            if fixed is None or fixed["format"] != "v2":
                continue
            snapshot = fixed["snapshot"]["snapshot_id"]
            calculated = parent.read_index_calculations(index, snapshot, INDEX_FORMULA)
            if calculated is None:
                continue
            rows = calculated["daily"]["rows"]
            for i, row in enumerate(rows):
                on = row["end"]
                if on not in entries:
                    continue
                entries[on]["indices"].append({"index_id": index, "snapshot_id": snapshot,
                    "formula_version": INDEX_FORMULA, "date": on, "return_1": row["change_pct"]["value"],
                    "return_5": change_pct_v1(row["close"], rows[i-5]["close"]) if i >= 5 else None,
                    "input_basis": "posthoc_context", "calculated_at": selected_at})
        except (ActivityError, ReadUnavailable, SnapshotError, OSError):
            continue
    if parent.activity_scope_id is not None:
        try:
            anchors = parent.activity_market_anchors
        except (ActivityError, ReadUnavailable, SnapshotError, OSError):
            anchors = {}
        for series, name in ((MARKET, "sse_szse_bse"), (TWO_MARKET, "sse_szse")):
            anchor = anchors.get(name)
            if anchor is None:
                continue
            try:
                current = parent.activity("current", series, anchor)
                if current is None:
                    continue
                calculated = parent.activity("calculations", series, current["activity_id"], formula_for(series))
                if calculated is None:
                    continue
                rows = next(s["rows"] for s in calculated["series"] if s["field"] == "amount" and s["frequency"] == "daily")
                for i, row in enumerate(rows):
                    on = row["end"]
                    if on not in entries or entries[on]["market"] is not None or row["total"]["value"] is None:
                        continue
                    sample = rows[max(0, i-20):i]
                    ratio = None
                    if len(sample) == 20 and all(x["total"]["value"] is not None for x in sample):
                        with localcontext() as context:
                            context.prec = 48
                            total = sum(Decimal(x["total"]["value"]) for x in sample)
                            ratio = number(Decimal(row["total"]["value"]) * 20 / total) if total != 0 else None
                    entries[on]["market"] = {"series_id": series, "activity_id": current["activity_id"],
                        "formula_version": FORMAT, "date": on, "scope_label": "沪深" if series == TWO_MARKET else "沪深北",
                        "turnover": row["total"]["value"], "ratio_20": ratio,
                        "input_basis": "posthoc_context", "calculated_at": selected_at}
            except (ActivityError, ReadUnavailable, SnapshotError, OSError):
                continue
    for entry in entries.values():
        complete = {x["index_id"] for x in entry["indices"]} == wanted and entry["market"] is not None
        entry["reason"] = None if complete else "context_partial" if entry["indices"] or entry["market"] else "context_not_available"
    return validate({"format": FORMAT, "rows": list(entries.values())})


def select(raw: dict[str, Any], on: str, indices: set[str]) -> dict[str, Any]:
    """固定输入只按观察日/配置成员筛选；无对应日不借后来一天的背景。"""
    entry = next((row for row in validate(raw)["rows"] if row["date"] == on), None)
    if entry is None:
        return {"indices": [], "market": None, "reason": "context_not_available"}
    rows = [row for row in entry["indices"] if row["index_id"] in indices]
    complete = {row["index_id"] for row in rows} == indices and entry["market"] is not None
    return {"indices": rows, "market": entry["market"], "reason": None if complete else
            "context_partial" if rows or entry["market"] else "context_not_available"}
