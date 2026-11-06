"""冻结的价格纯函数；发布摘要和读取计算共用，旧版本不原地改义。"""
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from pmi.market_data import SnapshotError

CHANGE_V1 = "adjacent-expected-close-pct-half-up-v1"
MA_V1 = "close-sma-half-up-4-v1"


def positive_price(value: str) -> Decimal:
    """读取有限正十进制价格；拒绝浮点、零分母及非有限数。"""
    if not isinstance(value, str):
        raise SnapshotError("invalid_calculation_price")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise SnapshotError("invalid_calculation_price") from error
    if not number.is_finite() or number <= 0:
        raise SnapshotError("invalid_calculation_price")
    return number


def change_pct_v1(current: str, previous: str) -> str:
    """按原摘要v1的48位上下文计算百分数，HALF_UP两位并归一负零。

    Args:
        current: 已核验的当前收盘原字符串。
        previous: 同一快照的正前收盘原字符串。
    Returns:
        固定两位百分数；不修改输入或访问外部状态。
    """
    current_value, previous_value = positive_price(current), positive_price(previous)
    with localcontext(Context(prec=48)):
        value = ((current_value / previous_value - 1) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return "0.00" if value == 0 else format(value, ".2f")


def close_sma_v1(closes: list[str]) -> str:
    """已核验周期收盘的简单平均，含当前周期，仅最终HALF_UP四位。"""
    if not closes:
        raise SnapshotError("empty_calculation_samples")
    with localcontext(Context(prec=48)):
        value = (sum((positive_price(item) for item in closes), Decimal(0)) / len(closes)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return format(value, ".4f")
