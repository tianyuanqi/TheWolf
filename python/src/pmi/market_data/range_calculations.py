"""范围投影复用原公式；源日历和缺失标记用于能力说明，不补造数值。"""
from __future__ import annotations

from decimal import Context, ROUND_HALF_UP, localcontext

from pmi.market_data import SnapshotError
from pmi.market_data.index_history_calendar import from_manifest_window, period_calendar
from pmi.market_data import index_calculations as price
from pmi.market_data.activity import calculations as activity
from pmi.market_data.activity.model import ActivityError, MARKET_IDS, SERIES, VERSION, identifier


def groups(dates: tuple[str, ...], frequency: str) -> list[list[str]]:
    result: list[list[str]] = []
    for day in dates:
        if not result or price._bounds(result[-1][0], frequency) != price._bounds(day, frequency):
            result.append([])
        result[-1].append(day)
    return result


def price_availability(snapshot: dict, source_dates: tuple[str, ...], frequency: str) -> list[dict]:
    """与完整输入的周期资格一致；裁剪不把历史周期误认成最后临时周期。"""
    count = 0
    for days in groups(source_dates, frequency):
        expected = period_calendar(*price._bounds(days[0], frequency), snapshot['calendar_version'])
        count += int(days[-1] == source_dates[-1] or bool(expected and expected[-1] == days[-1]))
    return [{'period': period, 'available': count >= period, 'sample_count': count,
             'required_count': period, 'reason': None if count >= period else 'insufficient_samples'} for period in price.PERIODS]


def check_price(snapshot: dict, source_dates: tuple[str, ...]) -> None:
    """完整源日历仍验证；价格只验证实际SQL取回的预热及显示行。"""
    from_manifest_window({**snapshot, 'calendar_dates': list(source_dates)})
    identifier(snapshot['snapshot_id'])
    days = tuple(row['trade_date'] for row in snapshot['bars'])
    if days != tuple(sorted(set(days))) or not set(days) <= set(source_dates):
        raise SnapshotError('calculation_calendar_mismatch')
    price._check_prices(snapshot)


def price_series(snapshot: dict, source_dates: tuple[str, ...], visible_periods: tuple[str, ...],
                 frequency: str, periods: tuple[int, ...], version: str) -> dict:
    """仅生成所选周期/均线，返回行与旧完整结果的对应行逐字段相同。"""
    index = snapshot['instrument']['id']
    if (index not in price.INDEX_IDS or version != price.FORMULA_VERSION or frequency not in ('daily', 'weekly', 'monthly')
            or len(set(periods)) != len(periods) or any(type(n) is not int or n not in price.PERIODS for n in periods)):
        raise SnapshotError('calculation_parameters_invalid')
    check_price(snapshot, source_dates)
    result = price._series(index, snapshot, frequency, periods=tuple(sorted(periods)), source_end=source_dates[-1],
                           availability=price_availability(snapshot, source_dates, frequency))
    wanted = set(visible_periods)
    result['rows'] = [row for row in result['rows'] if row['period_start'] in wanted]
    return result


def price_overview(snapshot: dict, source_dates: tuple[str, ...], version: str) -> dict:
    index = snapshot['instrument']['id']
    if index not in price.INDEX_IDS or version != price.FORMULA_VERSION:
        raise SnapshotError('calculation_parameters_invalid')
    check_price(snapshot, source_dates)
    if not snapshot['bars'] or snapshot['bars'][-1]['trade_date'] != source_dates[-1]:
        raise SnapshotError('calculation_input_mismatch')
    return {**price._header(index, snapshot), 'performance': price._performance(index, snapshot)}


def activity_availability(snapshot: dict, presence: dict[str, bool], frequency: str) -> list[dict]:
    """按完整源末端的连续周期统计缺失；SQL只提供是否缺失，不读取多余数值。"""
    valid = []
    for days in groups(tuple(presence), frequency):
        known = frequency == 'daily' or period_calendar(*price._bounds(days[0], frequency), snapshot['calendar_version']) is not None
        valid.append(known and all(presence[day] for day in days))
    result = []
    for period in activity.PERIODS:
        selected = valid[-period:]
        reason = 'insufficient_samples' if len(selected) < period else 'missing_window_value' if not all(selected) else None
        result.append({'period': period, 'available': reason is None, 'sample_count': sum(selected), 'required_count': period, 'reason': reason})
    return result


def activity_series(snapshot: dict, source_dates: tuple[str, ...], presence: dict[str, bool],
                    visible_periods: tuple[str, ...], field: str, frequency: str,
                    periods: tuple[int, ...], version: str) -> dict:
    """沿用Decimal48及原缺失/完整性语义，只裁去计算预热行。"""
    series = snapshot['series_id']
    if (series not in SERIES or snapshot['schema_version'] != VERSION or version != activity.formula_for(series)
            or field not in ('amount', 'volume') or frequency not in ('daily', 'weekly', 'monthly')
            or series in MARKET_IDS and (field != 'amount' or frequency != 'daily')
            or len(set(periods)) != len(periods) or any(type(n) is not int or n not in activity.PERIODS for n in periods)):
        raise ActivityError('calculation_parameters_invalid', 422)
    identifier(snapshot['activity_id'])
    days = tuple(row['trade_date'] for row in snapshot['rows'])
    if (days != tuple(sorted(set(days))) or not set(days) <= set(source_dates)
            or tuple(presence) != source_dates or any(type(value) is not bool for value in presence.values())):
        raise ActivityError('activity_calendar_invalid')
    with localcontext(Context(prec=48, rounding=ROUND_HALF_UP)):
        result = activity._series(snapshot, field, frequency, periods=periods,
            source_availability=activity_availability(snapshot, presence, frequency))
    wanted = set(visible_periods)
    result['rows'] = [row for row in result['rows'] if row['period_start'] in wanted]
    return result


def market_comparison(snapshot: dict) -> dict:
    """独立三市摘要仍按原一年/交易日窗口现算，不计算其他周期。"""
    if snapshot['series_id'] not in MARKET_IDS or not snapshot['rows']:
        raise ActivityError('calculation_parameters_invalid', 422)
    with localcontext(Context(prec=48, rounding=ROUND_HALF_UP)):
        return activity._comparison(snapshot)
