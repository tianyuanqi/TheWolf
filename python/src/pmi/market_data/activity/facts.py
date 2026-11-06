"""固定量额事实生成与重放；不持久化衍生结果，不混接来源精度。"""
from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from .model import ActivityError, BINDING, Fact, INDEX_IDS, MARKET, MARKETS, Original, Rule, Snapshot, VERSION, number, source_number, rule, identifier
from .sources import parse_index
from pmi.market_data.index_history_calendar import from_manifest_window


def missing(series: str, kind: str, reason: str, *, policy: Rule | None = None) -> Fact:
    policy = policy or rule(series)
    return {'value': None, 'unit': '股' if kind == 'volume' else '元', 'reason': reason,
            'raw_value': None, 'raw_unit': policy.volume_unit or 'not_applicable' if kind == 'volume' else policy.amount_unit,
            'source_quantum': '1' if kind == 'volume' else policy.amount_quantum, 'object_id': None, 'locator': None}


def fact(series: str, kind: str, raw: str | None, original: Original, locator: str, *, policy: Rule | None = None) -> Fact:
    """按固定源刻度十进制转换；未准入时永不输出有效值。"""
    policy = policy or rule(series)
    if not policy.admitted:
        return missing(series, kind, 'source_unverified', policy=policy)
    if raw is None:
        return missing(series, kind, 'source_missing', policy=policy)
    with localcontext(Context(prec=48, rounding=ROUND_HALF_UP)):
        value = source_number(raw, integer=kind == 'volume')
        quantum = Decimal('1' if kind == 'volume' else policy.amount_quantum)
        if value % quantum:
            raise ActivityError('source_precision_mismatch')
        normalized = value * (Decimal(10)**8 if kind == 'amount' and policy.amount_unit == '亿元' else 1)
        result = missing(series, kind, 'source_missing', policy=policy)
        result.update(value=format(normalized, '.0f' if kind == 'volume' else '.2f'), reason=None,
                      raw_value=raw, object_id=original.object_id, locator=locator)
        return result


def index_manifest(series: str, price: dict, original: Original, *, policy_version: str | None = None) -> Snapshot:
    """使用固定P及单个量额原件，精确比较可得OHLC并保留修订未知。"""
    if series not in INDEX_IDS or price['instrument']['id'] != series:
        raise ActivityError('price_binding_unverifiable')
    policy = rule(series) if policy_version is None else rule(series, policy_version)
    window = from_manifest_window(price)
    identifier(price['snapshot_id'])
    parsed = {r['trade_date']: r for r in parse_index(series, original, list(window.dates))}
    primary = price['evidence'][0]
    prices = {r['trade_date']: r for r in primary['rows']}
    rows, comparisons = [], []
    for day in window.dates:
        raw = parsed.get(day)
        if raw is not None and any(raw[k] is not None for k in ('volume', 'amount')):
            try:
                same = all(number(raw['ohlc'][k]) == number(prices[day]['raw_values'][k]) for k in ('open', 'high', 'low', 'close'))
            except (KeyError, TypeError, ActivityError) as error:
                raise ActivityError('price_binding_unverifiable') from error
            if not same:
                raise ActivityError('price_values_mismatch')
            comparisons.append({'trade_date': day, 'price_locator': prices[day]['locator'], 'activity_locator': raw['locator']})
        rows.append({'trade_date': day, **{kind: fact(series, kind, raw[kind], original, raw['locator'], policy=policy) if raw else
                     missing(series, kind, 'source_missing' if policy.admitted else 'source_unverified', policy=policy) for kind in ('volume', 'amount')}})
    return {'schema_version': VERSION, 'series_id': series, 'price_snapshot_id': price['snapshot_id'],
            'anchor_date': window.anchor_date, 'window': window.as_dict(), 'calendar_version': window.calendar_version,
            'calendar_dates': list(window.dates), 'completion_basis': window.completion_basis, 'source_policy_version': policy.version, 'parser_version': 'activity-parser-v1',
            'pit_grade': 'latest_only', 'currency': 'CNY', 'source_scope': policy.scope,
            'source_revision_relation': 'unknown', 'source_revision_id': None,
            'binding': {'version': BINDING, 'price_object_id': primary['object_id'], 'activity_object_id': original.object_id,
                        'relation': 'same_source_object' if primary['object_id'] == original.object_id else 'different_source_objects',
                        'comparison': 'exact_available_values_match', 'rows': comparisons},
            'sources': [{'source': original.source, 'object_id': original.object_id, 'url': original.url}], 'rows': rows}


def market_manifest(anchor: str, window: dict, calendar_version: str, calendars: dict[str, list[str] | None],
                    components: dict[str, dict[str, list[Fact]]]) -> Snapshot:
    """三市固定日历与原分项；未知市场不借沪深日历，合计留给读取计算。"""
    if set(calendars) != set(MARKETS) or set(components) != set(MARKETS):
        raise ActivityError('calendar_unknown')
    dates = sorted(set(day for values in calendars.values() if values is not None for day in values))
    if not dates or len(dates) > 1100 or dates[0] < window['start'] or dates[-1] > window['end']:
        raise ActivityError('calendar_unknown')
    rows = []
    for day in dates:
        values = {}
        for market in MARKETS:
            if not rule(market).admitted:
                values[market] = [missing(market, 'amount', 'source_unverified')]
            elif calendars[market] is None or day not in calendars[market]:
                values[market] = [missing(market, 'amount', 'calendar_unknown')]
            else:
                values[market] = components[market].get(day, [missing(market, 'amount', 'source_missing')])
        rows.append({'trade_date': day, 'components': values})
    return {'schema_version': VERSION, 'series_id': MARKET, 'price_snapshot_id': None, 'anchor_date': anchor,
            'window': window, 'calendar_version': calendar_version, 'calendar_dates': dates, 'market_calendars': calendars,
            'source_policy_version': 'activity-source-policy-v1', 'parser_version': 'activity-parser-v1',
            'pit_grade': 'latest_only', 'currency': 'CNY', 'source_scope': 'SSE-main-A+STAR;SZSE-main-A+ChiNext;BSE-stocks',
            'source_revision_relation': 'unknown', 'source_revision_id': None, 'binding': None, 'sources': [], 'rows': rows}


def market_from_originals(window, originals: list[Original]) -> Snapshot:
    """重放已核日期的沪市日报；深北证据不足保持未知，不能猜导出日期或单位。"""
    from .sources import market_url, sse_parts
    dates = list(window.dates)
    components = {m: {} for m in MARKETS}
    calendars = {m: dates if m == 'sse' and rule(m).admitted else None for m in MARKETS}
    members = []
    for original in originals:
        if original.source != 'sse' or not rule('sse').admitted:
            raise ActivityError('source_unverified')
        matching = [day for day in dates if original.url == market_url('sse', day)]
        if len(matching) != 1 or matching[0] in components['sse']:
            raise ActivityError('source_date_mismatch')
        day = matching[0]
        parts = sse_parts(original.content, day)
        components['sse'][day] = [fact('sse', 'amount', value, original, 'result[PRODUCT_CODE='+code+']') for code, value in parts]
        members.append({'source': 'sse', 'object_id': original.object_id, 'url': original.url})
    result = market_manifest(window.anchor_date, window.as_dict(), window.calendar_version, calendars, components)
    result['sources'] = sorted(members, key=lambda m: m['url'])
    result['completion_basis'] = window.completion_basis
    return result
