"""采用来源A的精确适配：官方份额/成交，第三方单位净值，不混用量额。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
import hashlib
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlsplit

from .budget import Request
from .calendar import trading_dates
from .model import FlowError, Input, Member, Source, UNITS, day, decimal, decode, integer, number

SHARES_QUERY = "COMMON_SSE_ZQPZ_ETFZL_ETFJBXX_JJGM_SEARCH_L"
QUOTE_QUERY = "COMMON_SSE_CP_GPJCTPZ_GPLB_CJGK_MRGK_C"
EXCHANGES = {"上海证券交易所": "sse"}


def request_for(member: Member, kind: str, start: str, end: str, *, page: int = 1) -> Request:
    """路由只依赖配置交易所/身份；未核验交易所明确拒绝，不猜测替代源。"""
    if EXCHANGES.get(member.exchange) != "sse":
        raise FlowError("etf_exchange_not_supported", 422)
    day(start)
    day(end)
    if kind in {"shares", "quote"}:
        if start != end:
            raise FlowError("etf_invalid_source_request", 422)
        parameters = ({"sqlId": SHARES_QUERY, "isPagination": "false", "SEC_CODE": member.code, "STAT_DATE": start}
                      if kind == "shares" else {"sqlId": QUOTE_QUERY, "SEC_CODE": member.code, "TX_DATE": start, "isPagination": "false"})
        url = "https://query.sse.com.cn/commonQuery.do?" + urlencode(parameters)
    elif kind == "nav":
        integer(page, 1)
        url = "https://api.fund.eastmoney.com/f10/lsjz?" + urlencode({"fundCode": member.code, "pageIndex": page,
            "pageSize": 20, "startDate": start, "endDate": end})
    else:
        raise FlowError("etf_invalid_source_request", 422)
    return Request(kind, member.id, start, end, url)


def plan(member: Member, start: str, end: str, inputs: Mapping[tuple[str, str], Input], *, refresh: bool = False) -> tuple[Request, ...]:
    """按缺字段规划有界请求；NAV仍用20条小页，数量按实际日历而非固定成员数。"""
    dates = trading_dates(start, end)
    requests: list[Request] = []
    nav_missing: list[str] = []
    for on in dates:
        row = inputs.get((member.id, on))
        if refresh or row is None or row.value("shares") is None:
            requests.append(request_for(member, "shares", on, on))
        if refresh or row is None or any(row.value(f) is None for f in ("close", "turnover", "volume")):
            requests.append(request_for(member, "quote", on, on))
        if refresh or row is None or row.value("nav") is None:
            nav_missing.append(on)
    if nav_missing:
        first, last = nav_missing[0], nav_missing[-1]
        count = len(trading_dates(first, last))
        requests.extend(request_for(member, "nav", first, last, page=p) for p in range(1, (count + 19) // 20 + 1))
    return tuple(requests)


@dataclass(frozen=True)
class Parsed:
    rows: tuple[Input, ...]
    total: int | None = None
    page: int | None = None
    returned_dates: tuple[str, ...] = ()


def _value(raw: Any, scale: int, *, positive: bool = False) -> Decimal:
    """原披露刻度改变即停止，不静默四舍五入到旧精度。"""
    value = decimal(raw, minimum=Decimal(0), positive=positive)
    if -value.as_tuple().exponent > scale:
        raise FlowError("etf_source_precision_changed")
    return value


def parse(member: Member, request: Request, raw: bytes, original_id: str, retrieved_at: str) -> Parsed:
    """校验身份、日期、来源结构和原披露刻度；不把空大页或累计净值当输入。"""
    if request.member_id != member.id:
        raise FlowError("etf_source_identity_mismatch")
    if hashlib.sha256(raw).hexdigest() != original_id:
        raise FlowError("etf_source_hash_mismatch")
    query = parse_qs(urlsplit(request.url).query)
    try:
        page = int(query["pageIndex"][0]) if request.kind == "nav" else 1
    except (KeyError, ValueError, IndexError) as error:
        raise FlowError("etf_invalid_source_request") from error
    if request != request_for(member, request.kind, request.start, request.end, page=page):
        raise FlowError("etf_invalid_source_request")
    value = decode(raw)
    if not isinstance(value, dict):
        raise FlowError("etf_source_shape_changed")

    def field(name: str, on: str, amount: Decimal, original_unit: str, precision: str, locator: str) -> dict[str, Any]:
        source = {"object_id": original_id, "publisher": "上交所" if request.kind != "nav" else "原发布方未逐日核实",
                  "channel": "交易所公开日统计" if request.kind != "nav" else "东方财富转述单位净值；身份按受控请求绑定",
                  "url": request.url, "retrieved_at": retrieved_at, "published_at": None, "locator": locator,
                  "original_unit": original_unit, "precision": precision}
        Source.parse(source)
        return {"value": number(amount), "date": on, "unit": UNITS[name], "source": source}

    rows: list[Input] = []
    with localcontext() as context:
        context.prec = 100
        if request.kind in {"shares", "quote"}:
            if value.get("actionErrors") or value.get("fieldErrors") or value.get("sqlId") != (SHARES_QUERY if request.kind == "shares" else QUOTE_QUERY):
                raise FlowError("etf_source_rejected")
            records = value.get("result")
            if request.kind == "quote" and records == []:
                # 受控请求与成功结构均已核对；无辅助行情不等于核心输入无效。
                return Parsed(())
            if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
                raise FlowError("etf_source_day_missing")
            item = records[0]
            if item.get("SEC_CODE") != member.code:
                raise FlowError("etf_source_identity_mismatch")
            expected_day = request.start if request.kind == "shares" else request.start.replace("-", "")
            if item.get("STAT_DATE" if request.kind == "shares" else "TX_DATE") != expected_day:
                raise FlowError("etf_source_date_mismatch")
            if request.kind == "shares":
                fields = {"shares": field("shares", request.start, _value(item.get("TOT_VOL"), 2) * 10000,
                    "万份", "0.01万份（100份）", "result[0].TOT_VOL；STAT_DATE为份额归属日")}
            else:
                if item.get("DATE_TYPE") != "D":
                    raise FlowError("etf_source_date_mismatch")
                fields = {
                    "close": field("close", request.start, _value(item.get("CLOSE_PRICE"), 3, positive=True), "元/份", "0.001元/份", "result[0].CLOSE_PRICE；未复权日收盘"),
                    "turnover": field("turnover", request.start, _value(item.get("TRADE_AMT"), 2) * 10000, "万元", "0.01万元（100元）", "result[0].TRADE_AMT；官方统计范围，细分未穷尽"),
                    "volume": field("volume", request.start, _value(item.get("TRADE_VOL"), 2) * 10000, "万份", "0.01万份（100份）", "result[0].TRADE_VOL；不混用第三方手数"),
                }
            rows.append(Input.parse({"member_id": member.id, "date": request.start, "fields": fields, "revision_reason": "受控来源A日统计"}))
            return Parsed(tuple(rows), returned_dates=(request.start,))

        if value.get("ErrCode") != 0 or type(value.get("ErrCode")) is not int or not isinstance(value.get("Data"), dict):
            raise FlowError("etf_source_rejected")
        if type(value.get("PageIndex")) is not int or value.get("PageIndex") != page or value.get("PageSize") != 20:
            raise FlowError("etf_source_page_mismatch")
        total = integer(value.get("TotalCount"))
        expected_dates = trading_dates(request.start, request.end)
        if total > len(expected_dates):
            raise FlowError("etf_source_count_mismatch")
        records = value["Data"].get("LSJZList")
        if not isinstance(records, list) or len(records) != min(20, max(0, total - (page - 1) * 20)):
            raise FlowError("etf_source_count_mismatch")
        dates: list[str] = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                raise FlowError("etf_source_shape_changed")
            on = day(item.get("FSRQ"))
            if on not in expected_dates or on in dates or (dates and on >= dates[-1]):
                raise FlowError("etf_source_date_mismatch")
            dates.append(on)
            nav = field("nav", on, _value(item.get("DWJZ"), 4, positive=True), "元/份", "0.0001元/份",
                        f"Data.LSJZList[{index}].DWJZ；FSRQ归属日；不使用LJJZ")
            rows.append(Input.parse({"member_id": member.id, "date": on, "fields": {"nav": nav}, "revision_reason": "受控来源A单位净值小页"}))
        return Parsed(tuple(rows), total=total, page=page, returned_dates=tuple(dates))


def verify_nav_pages(pages: tuple[Parsed, ...], start: str, end: str) -> tuple[str, ...]:
    """全页总数和去重相互核对；返回真实缺日，绝不补零或伪造条目。"""
    if not pages or pages[0].total is None:
        raise FlowError("etf_source_page_missing")
    total = pages[0].total
    needed = max(1, (total + 19) // 20)
    if len(pages) != needed or [p.page for p in pages] != list(range(1, needed + 1)) or any(p.total != total for p in pages):
        raise FlowError("etf_source_page_mismatch")
    dates = tuple(d for p in pages for d in p.returned_dates)
    if len(dates) != total or len(set(dates)) != total or dates != tuple(sorted(dates, reverse=True)):
        raise FlowError("etf_source_count_mismatch")
    return tuple(d for d in trading_dates(start, end) if d not in dates)
