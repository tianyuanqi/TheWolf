"""六指数三自然年窗口，使用已核验的沪深年度休市公告。"""

import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pmi.market_data import SnapshotError

CALENDAR_VERSION = "cn-indices-sse-szse-2023-2026-v1"
WINDOW_VERSION = "three-natural-years-before-shanghai-day-v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
_HOLIDAYS = {
    2023: (("01-01", "01-02"), ("01-21", "01-27"), ("04-05", "04-05"), ("04-29", "05-03"), ("06-22", "06-24"), ("09-29", "10-06")),
    2024: (("01-01", "01-01"), ("02-09", "02-17"), ("04-04", "04-06"), ("05-01", "05-05"), ("06-10", "06-10"), ("09-15", "09-17"), ("10-01", "10-07")),
    2025: (("01-01", "01-01"), ("01-28", "02-04"), ("04-04", "04-06"), ("05-01", "05-05"), ("05-31", "06-02"), ("10-01", "10-08")),
    2026: (("01-01", "01-03"), ("02-15", "02-23"), ("04-04", "04-06"), ("05-01", "05-05"), ("06-19", "06-21"), ("09-25", "09-27"), ("10-01", "10-07")),
}
# 元组避免调用者污染；hash 为此次已保留证据，不表示永久授权或未来公告已覆盖。
_SOURCES = (
    (2023, "sse", "https://www.sse.com.cn/disclosure/announcement/general/c/c_20221227_5714459.shtml", "web_tool_text", "2fe701f0a49039cd3197baf7ca4b8c60354c72b786e476279c307a72bf727ead"),
    (2023, "szse", "https://www.szse.cn/disclosure/notice/general/t20221227_598022.html", "http_original", "85e2a05b8968f1a4cadd975184962b648cf2cb2cea0071314f0e81bc17f1df96"),
    (2024, "sse", "https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20231226_5733941.shtml", "http_original", "553c09f2b9482690b957f207a03a2a909a4b311e8985ed1fcf752d114af95bc9"),
    (2024, "szse", "https://www.szse.cn/disclosure/notice/t20231226_605108.html", "http_original", "2c9906bac2116f3bc6190f0d0a74e0be40f1e4307f71e34cc12007d411e88b13"),
    (2025, "sse", "https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20241223_10767110.shtml", "http_original", "a9ffc97241c0ffa81b8c3ee24b07ca79fe8414468528e94846dcac9900077feb"),
    (2025, "szse", "https://www.szse.cn/disclosure/notice/t20241223_611283.html", "http_original", "1c89289137907b6afd00c27059919dedcb8414f4402a38b995ff9eccd465874e"),
    (2026, "sse", "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml", "http_original", "090c75b3fb9bbcbd447fd93607e28cca821603b897a58ef7df84eb05ea4be841"),
    (2026, "szse", "https://investor.szse.cn/disclosure/notice/general/t20251222_618087.html", "http_original", "1656d8708d5faed33c7588538639d96128f39fdface02cfa6eb66d796c40f14e"),
)


@dataclass(frozen=True)
class FrozenWindow:
    """D、自然起点及完整日历一次冻结，嵌套公开值每次独立生成。"""

    dates: tuple[str, ...]
    anchor_date: str
    natural_start: str
    calendar_version: str = CALENDAR_VERSION

    @property
    def start(self) -> str:
        """第一个实际交易日，供来源请求使用。"""
        return self.dates[0]

    @property
    def end(self) -> str:
        """最后一个完成日，供来源请求使用。"""
        return self.dates[-1]

    @property
    def completion_basis(self) -> dict:
        """返回不共享可变成员的日历依据。"""
        return {"rule": "exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today",
                "timezone": "Asia/Shanghai", "exclude_anchor_day": True,
                "supported_years": [2023, 2024, 2025, 2026],
                "sources": [{"year": year, "exchange": exchange, "url": url, "evidence_kind": kind,
                             "evidence_sha256": sha} for year, exchange, url, kind, sha in _SOURCES],
                "limitations": ["年度公告不承诺未来无临时休市；新增公告须重新核验并更新日历版本。",
                                "2024-09-27 盘中异常不按全日休市剔除。",
                                "2023 上交所年度依据为已保存工具正文，非直接 HTTP 原件。"]}

    def as_dict(self) -> dict:
        """生成可直接 JSON 化的固定窗口字段。"""
        return {"version": WINDOW_VERSION, "anchor_date": self.anchor_date,
                "natural_start": self.natural_start, "start": self.start, "end": self.end,
                "expected_count": len(self.dates), "actual_count": len(self.dates)}


def _natural_start(anchor: date) -> date:
    year = anchor.year - 3
    return date(year, anchor.month, min(anchor.day, monthrange(year, anchor.month)[1]))


def _from_anchor(anchor: date) -> FrozenWindow:
    start = _natural_start(anchor)
    if any(year not in _HOLIDAYS for year in range(start.year, anchor.year + 1)):
        raise SnapshotError("calendar_uncovered")
    days = []
    day = start
    while day < anchor:
        marker = day.strftime("%m-%d")
        if day.weekday() < 5 and not any(left <= marker <= right for left, right in _HOLIDAYS[day.year]):
            days.append(day.isoformat())
        day += timedelta(days=1)
    if not days:
        raise SnapshotError("empty_calendar")
    return FrozenWindow(tuple(days), anchor.isoformat(), start.isoformat())


def complete_window(now: datetime) -> FrozenWindow:
    """按上海当日 D 冻结 [D−三自然年, D) 内完整交易日。

    Args:
        now: 带时区的实际观察时刻。

    Returns:
        请求和重放共用的不可变三年窗口。
    """
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise SnapshotError("naive_clock")
    return _from_anchor(now.astimezone(SHANGHAI).date())


def validate_window(window: FrozenWindow) -> None:
    """按记录的 D 重建并精确核对窗口，拒绝删日或改范围。"""
    try:
        anchor = date.fromisoformat(window.anchor_date)
        expected = _from_anchor(anchor)
    except (TypeError, ValueError, AttributeError) as error:
        raise SnapshotError("invalid_window") from error
    if type(window) is not FrozenWindow or window != expected:
        raise SnapshotError("invalid_window")


def from_manifest_window(manifest: dict) -> FrozenWindow:
    """重建历史快照窗口；不使用当前时钟，也不信任存入的派生范围。"""
    try:
        window = _from_anchor(date.fromisoformat(manifest["window"]["anchor_date"]))
        actual = {"window": manifest["window"], "calendar_dates": manifest["calendar_dates"],
                  "calendar_version": manifest["calendar_version"], "completion_basis": manifest["completion_basis"]}
        expected = {"window": window.as_dict(), "calendar_dates": list(window.dates),
                    "calendar_version": window.calendar_version, "completion_basis": window.completion_basis}
        if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
            raise SnapshotError("invalid_manifest_window")
        return window
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise SnapshotError("invalid_manifest_window") from error


def period_calendar(start: date, end: date, version: str) -> tuple[str, ...] | None:
    """按冻结日历版本列举周期交易日；未知年份返回None，不猜测或联网。

    仅查询日历元数据，不扩大快照价格范围；历史版本实现须保留。
    """
    if version != CALENDAR_VERSION:
        raise SnapshotError("calendar_version_unsupported")
    if end < start or (end - start).days > 31:
        raise SnapshotError("calendar_period_invalid")
    if any(year not in _HOLIDAYS for year in range(start.year, end.year + 1)):
        return None
    rows = []
    day = start
    while day <= end:
        marker = day.strftime("%m-%d")
        if day.weekday() < 5 and not any(left <= marker <= right for left, right in _HOLIDAYS[day.year]):
            rows.append(day.isoformat())
        day += timedelta(days=1)
    return tuple(rows)
