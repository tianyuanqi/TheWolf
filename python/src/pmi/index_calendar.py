"""沪深300首版日历；只使用P01已核验的2025/2026休市安排。"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pmi.snapshot import SnapshotError

CALENDAR_VERSION = "csi300-sse2025-szse-sse2026-v1"
CALENDAR_SOURCES = (
    ("https://www.sse.com.cn/disclosure/announcement/general/c/c_20241223_10767108.shtml", "b88e5777d868192c156b85f7514fafcba8638a8bcec0cd80190b2e67769f5fff"),
    ("https://investor.szse.cn/disclosure/notice/general/t20251222_618087.html", "1656d8708d5faed33c7588538639d96128f39fdface02cfa6eb66d796c40f14e"),
    ("https://investor.szse.cn/disclosure/notice/general/t20260917_622911.html", "7b0c4264d27f4ba14a1904ab31cb3b2b870e4e68d6b8d8c0f6cf4254c1a045a4"),
    ("https://www.sse.com.cn/disclosure/dealinstruc/closed/", "7ea10c16202c4748f0ad5bcdfe6ee07b85b5462589504604b17c9d63865e7d8c"),
)
_CLOSURES = (("2025-01-01", "2025-01-01"), ("2025-01-28", "2025-02-04"),
             ("2025-04-04", "2025-04-06"), ("2025-05-01", "2025-05-05"),
             ("2025-05-31", "2025-06-02"), ("2025-10-01", "2025-10-08"),
             ("2026-01-01", "2026-01-03"), ("2026-02-15", "2026-02-23"),
             ("2026-04-04", "2026-04-06"), ("2026-05-01", "2026-05-05"),
             ("2026-06-19", "2026-06-21"), ("2026-09-25", "2026-09-27"),
             ("2026-10-01", "2026-10-07"))


def trading_days(start: date, end: date) -> tuple[str, ...]:
    """返回已验证范围内开市日，周末调休仍按休市处理。

    Raises:
        SnapshotError: 范围越过2025/2026或顺序无效，不猜测未知年份。
    """
    if start < date(2025, 1, 1) or end > date(2026, 12, 31) or end < start:
        raise SnapshotError("calendar_uncovered: 已核验日历仅覆盖2025/2026")
    days = []
    while start <= end:
        value = start.isoformat()
        if start.weekday() < 5 and not any(a <= value <= b for a, b in _CLOSURES):
            days.append(value)
        start += timedelta(days=1)
    return tuple(days)


def complete_window(now: datetime) -> tuple[str, ...]:
    """冻结上海日期之前最近260个开市日；当日完成判据本版未准入。"""
    if now.tzinfo is None or now.utcoffset() is None:
        raise SnapshotError("calendar clock must include timezone")
    today = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    if today.year not in (2025, 2026):
        raise SnapshotError("calendar_uncovered: 当前年份未验证")
    days = trading_days(date(2025, 1, 1), today - timedelta(days=1))
    if len(days) < 260:
        raise SnapshotError("calendar_uncovered: 已验证日历不足260日")
    return days[-260:]


def completion_basis() -> dict:
    """说明日历出处与P01已声明的2025深交所材料限制。"""
    return {"version": CALENDAR_VERSION, "coverage": ["2025-01-01", "2026-12-31"],
            "rule": "Asia/Shanghai before today; both sources exact OHLC",
            "sources": [{"url": url, "sha256": digest} for url, digest in CALENDAR_SOURCES],
            "limits": "2025依据为上交所年度通知，未另取得深交所2025原通知"}
