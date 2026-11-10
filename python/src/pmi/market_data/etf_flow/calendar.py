"""ETF交易日期只取已有核验日历，不用工作日推测未知年份。"""
from datetime import date, timedelta

from pmi.market_data.index_history_calendar import CALENDAR_VERSION, period_calendar
from .model import FlowError, day


def trading_dates(start: str, end: str) -> tuple[str, ...]:
    """分段调用公共日历函数；未知版本/年份或反向范围拒绝。"""
    left, finish = date.fromisoformat(day(start)), date.fromisoformat(day(end))
    if left > finish:
        raise FlowError("etf_invalid_range", 422)
    result: list[str] = []
    while left <= finish:
        right = min(left + timedelta(days=30), finish)
        part = period_calendar(left, right, CALENDAR_VERSION)
        if part is None:
            raise FlowError("etf_calendar_uncovered", 409)
        result.extend(part)
        left = right + timedelta(days=1)
    return tuple(result)


def preceding_window(end: str, count: int) -> tuple[str, ...]:
    """从已覆盖年份内寻找指定交易日数；没有足够核验日历不缩窗。"""
    target = date.fromisoformat(day(end))
    if type(count) is not int or count < 1 or count > 2000:
        raise FlowError("etf_calendar_uncovered", 409)
    # 已有日历支持的最早年份不在ETF层复制；逐月向前查询，未知即拒绝。
    collected: tuple[str, ...] = ()
    right = target
    while len(collected) < count:
        left = right - timedelta(days=30)
        collected = trading_dates(left.isoformat(), right.isoformat()) + collected
        right = left - timedelta(days=1)
    return collected[-count:]
