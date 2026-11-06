"""量额版本化纯计算：固定输入、缺口不压缩、Decimal48、读取时现算。"""
from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from datetime import date, timedelta
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from typing import TypedDict

from pmi.market_data.index_history_calendar import period_calendar
from .model import ActivityError, MARKET, MARKET_IDS, TWO_MARKET, MARKETS, SERIES, VERSION, identifier, number

FORMULA = 'market-activity-calculations-v1'
TWO_FORMULA = 'market-activity-calculations-sse-szse-v1'

def formula_for(series: str) -> str:
    """合计范围绑定系列及公式版本，旧三市公式不改变含义。"""
    return TWO_FORMULA if series == TWO_MARKET else FORMULA

PERIODS = (5, 10, 20, 30, 60, 120, 180, 250)


class Scalar(TypedDict):
    """各结果独立携带公式、输入、参数、单位及未完整状态。"""
    value: str | None
    reason: str | None
    unit: str
    formula_version: str
    parameters: dict[str, str]
    input_ref: dict[str, str | None]
    complete: bool
    incomplete_reasons: list[str]


def _format(value: Decimal, digits: int) -> str:
    rounded = value.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return format(abs(rounded) if rounded == 0 else rounded, f'.{digits}f')


def _scalar(snapshot: dict, value: Decimal | None, reason: str | None, kind: str, frequency: str,
            operation: str, period: str, start: str | None, end: str, incomplete: list[str], digits: int) -> Scalar:
    return {'value': _format(value, digits) if value is not None else None, 'reason': reason,
            'unit': '%' if operation.endswith('pct') else '股' if kind == 'volume' else '元',
            'formula_version': formula_for(snapshot['series_id']), 'parameters': {'field': kind, 'frequency': frequency, 'operation': operation, 'period': period},
            'input_ref': {'series_id': snapshot['series_id'], 'activity_id': snapshot['activity_id'],
                          'price_snapshot_id': snapshot['price_snapshot_id'], 'start': start, 'end': end},
            'complete': not incomplete, 'incomplete_reasons': incomplete}


def _bounds(day: str, frequency: str) -> tuple[date, date]:
    current = date.fromisoformat(day)
    if frequency == 'daily':
        return current, current
    if frequency == 'weekly':
        start = current - timedelta(days=current.weekday())
        return start, start + timedelta(days=6)
    return current.replace(day=1), current.replace(day=monthrange(current.year, current.month)[1])


def _daily(snapshot: dict, kind: str) -> list[dict]:
    result = []
    for item in snapshot['rows']:
        if snapshot['series_id'] in MARKET_IDS:
            markets = ('sse', 'szse') if snapshot['series_id'] == TWO_MARKET else MARKETS
            if set(item['components']) != set(markets) or any(not item['components'].get(m) for m in markets):
                raise ActivityError('missing_market_input')
            parts = [part for m in markets for part in item['components'][m]]
            value = None if any(p['value'] is None for p in parts) else sum(number(p['value']) for p in parts)
            reason = next((p['reason'] for p in parts if p['value'] is None), None)
        else:
            value = number(item[kind]['value']) if item[kind]['value'] is not None else None
            reason = item[kind]['reason']
        result.append({'day': item['trade_date'], 'value': value, 'reason': reason})
    return result


def _series(snapshot: dict, kind: str, frequency: str) -> dict:
    groups: list[list[dict]] = []
    for item in _daily(snapshot, kind):
        if not groups or _bounds(groups[-1][0]['day'], frequency) != _bounds(item['day'], frequency):
            groups.append([])
        groups[-1].append(item)
    rows = []
    for group in groups:
        start, end = _bounds(group[0]['day'], frequency)
        reasons = []
        if frequency != 'daily':
            expected = period_calendar(start, end, snapshot['calendar_version'])
            if expected is None:
                reasons = ['calendar_unknown']
            else:
                if expected and expected[0] < group[0]['day']:
                    reasons.append('window_start_truncated')
                if expected and expected[-1] > group[-1]['day']:
                    reasons.append('period_in_progress')
        reason = next((x['reason'] for x in group if x['value'] is None), None)
        if 'calendar_unknown' in reasons:
            reason = 'calendar_unknown'
        value = None if reason else sum(x['value'] for x in group)
        rows.append({'start': group[0]['day'], 'end': group[-1]['day'], 'period_start': start.isoformat(),
                     'period_end': end.isoformat(), 'sample_count': len(group), 'value': value, 'reason': reason,
                     'incomplete': reasons})
    output = []
    availability = []
    for i, item in enumerate(rows):
        scalar = lambda v, r, op, n, first, inc, digits=4: _scalar(snapshot, v, r, kind, frequency, op, str(n), first, item['end'], inc, digits)
        total = scalar(item['value'], item['reason'], 'sum', 1, item['start'], item['incomplete'], 0 if kind == 'volume' else 2)
        previous = rows[i-1] if i else None
        why = 'insufficient_samples' if previous is None else 'missing_window_value' if previous['value'] is None or item['value'] is None else 'zero_baseline' if previous['value'] == 0 else None
        change = (item['value'] / previous['value'] - 1) * 100 if why is None else None
        incomplete = sorted(set(item['incomplete'] + (previous['incomplete'] if previous else [])))
        changes = scalar(change, why, 'change_pct', 1, previous['start'] if previous else None, incomplete, 2)
        averages, capabilities = [], []
        for n in PERIODS:
            sample = rows[max(0, i + 1 - n):i + 1]
            why = 'insufficient_samples' if len(sample) < n else 'missing_window_value' if any(r['value'] is None for r in sample) else None
            inc = sorted({reason for r in sample for reason in r['incomplete']})
            averages.append(scalar(sum(r['value'] for r in sample)/n if why is None else None, why, 'ma', n, sample[0]['start'], inc))
            capabilities.append({'period': n, 'available': why is None, 'sample_count': sum(r['value'] is not None for r in sample), 'required_count': n, 'reason': why})
        output.append({'start': item['start'], 'end': item['end'], 'period_start': item['period_start'],
                       'period_end': item['period_end'], 'sample_count': item['sample_count'], 'total': total, 'change_pct': changes, 'ma': averages})
        availability = capabilities
    return {'frequency': frequency, 'field': kind, 'rows': output, 'ma_availability': availability}


def _comparison(snapshot: dict) -> dict:
    rows = _daily(snapshot, 'amount')
    last = rows[-1]
    day = date.fromisoformat(last['day'])
    year = day.replace(year=day.year-1, day=min(day.day, monthrange(day.year-1, day.month)[1])).isoformat()
    starts = {f'day_{n}': len(rows)-n-1 for n in (5, 20, 60)}
    starts['year_1'] = bisect_right([r['day'] for r in rows], year)-1
    result = {}
    for key, start in starts.items():
        sample = rows[start:-1] if start >= 0 else []
        why = 'insufficient_samples' if not sample else 'missing_window_value' if any(r['value'] is None for r in [*sample, last]) else None
        mean = sum(r['value'] for r in sample) / len(sample) if why is None else None
        baseline = _scalar(snapshot, mean, why, 'amount', 'daily', 'baseline_mean', key, sample[0]['day'] if sample else None, rows[-2]['day'] if len(rows)>1 else last['day'], [], 4)
        change_reason = 'zero_baseline' if mean == 0 else why
        change = _scalar(snapshot, (last['value']/mean-1)*100 if change_reason is None else None, change_reason,
                         'amount', 'daily', 'window_mean_pct', key, sample[0]['day'] if sample else None, last['day'], [], 2)
        result[key] = {'baseline': baseline, 'comparison': change, 'sample_count': len(sample)}
    return result


def calculate(snapshot: dict, version: str) -> dict:
    """仅接受明确公式版本；不读取current、时钟或网络，不修改输入。"""
    if version != formula_for(snapshot['series_id']) or snapshot['series_id'] not in SERIES or snapshot['schema_version'] != VERSION:
        raise ActivityError('calculation_parameters_invalid', 422)
    identifier(snapshot['activity_id'])
    if not snapshot['rows'] or [r['trade_date'] for r in snapshot['rows']] != snapshot['calendar_dates']:
        raise ActivityError('activity_calendar_invalid')
    with localcontext(Context(prec=48, rounding=ROUND_HALF_UP)) as context:
        context.prec = 48
        fields = ('amount',) if snapshot['series_id'] in MARKET_IDS else ('volume', 'amount')
        frequencies = ('daily',) if snapshot['series_id'] in MARKET_IDS else ('daily', 'weekly', 'monthly')
        return {'series_id': snapshot['series_id'], 'activity_id': snapshot['activity_id'], 'price_snapshot_id': snapshot['price_snapshot_id'],
                'formula_version': formula_for(snapshot['series_id']), 'pit_grade': 'latest_only',
                'series': [_series(snapshot, field, frequency) for field in fields for frequency in frequencies],
                'comparisons': _comparison(snapshot) if snapshot['series_id'] in MARKET_IDS else None}
