"""依据深交所 2026 年休市通知选择完整日线窗口。"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pmi.snapshot import SnapshotError


CALENDAR_SOURCES = (
    "https://investor.szse.cn/disclosure/notice/general/t20251222_618087.html",
    "https://investor.szse.cn/disclosure/notice/general/t20260917_622911.html",
)
CALENDAR_VERSION = "szse-2026-notices-20251222-20260917"
_CLOSURES = (("2026-01-01", "2026-01-03"), ("2026-02-15", "2026-02-23"),
             ("2026-04-04", "2026-04-06"), ("2026-05-01", "2026-05-05"),
             ("2026-06-19", "2026-06-21"), ("2026-09-25", "2026-09-27"),
             ("2026-10-01", "2026-10-07"))


def complete_window(now: datetime) -> tuple[str, ...]:
    """返回上海日期之前的最近 60 个开市日；拒绝覆盖外或不足窗口。

    不纳入当日，即使盘后也不推定两源已完成。周末调休工作日仍休市。
    2026 年之外没有本版日历依据，不猜测跨年节假日。
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise SnapshotError("calendar clock must include timezone")
    today = now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    if today.year != 2026:
        raise SnapshotError("calendar_uncovered: 已核验日历仅覆盖 2026 年")
    days: list[str] = []
    current = date(2026, 1, 1)
    while current < today:
        day = current.isoformat()
        if current.weekday() < 5 and not any(start <= day <= end for start, end in _CLOSURES):
            days.append(day)
        current += timedelta(days=1)
    if len(days) < 60:
        raise SnapshotError("calendar_uncovered: 已核验日历不足 60 个开市日")
    return tuple(days[-60:])


def completion_basis() -> str:
    """提供可追溯日历版本、覆盖和不含当日的完成口径。"""
    return f"{CALENDAR_VERSION}; coverage=2026-01-01/2026-12-31; Asia/Shanghai before today; " + "; ".join(CALENDAR_SOURCES)
