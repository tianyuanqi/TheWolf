"""沪深两市固定官方日报；不含北交所，不改变旧三市来源或金额精度。"""
from __future__ import annotations

from html import unescape
import json
import re
from urllib.parse import urlencode

from .facts import fact, missing
from .model import ActivityError, MARKET_MAX_BYTES, Original, Snapshot, TWO_MARKET, TWO_POLICY, VERSION, load, number, rule, unique
from .sources import market_url, sse_parts


def daily_url(market: str, day: str) -> str:
    """仅构造已确认官方日报URL；调用者的冻结日历限制日期。"""
    if market == 'sse':
        return market_url(market, day)
    if market == 'szse':
        return 'https://www.szse.cn/api/report/ShowReport/data?' + urlencode({
            'SHOWTYPE': 'JSON', 'CATALOGID': '1803_sczm', 'TABKEY': 'tab1', 'txtQueryDate': day})
    raise ActivityError('source_unverified')


def szse_parts(content: bytes, day: str) -> list[tuple[str, str]]:
    """日期和亿元列来自同份JSON；合法空报表为缺日，拒绝猜测XLSX日期。"""
    try:
        root = json.loads(content, object_pairs_hook=unique, parse_int=str, parse_float=str,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(root, list) or not 1 <= len(root) <= 4:
            raise ValueError()
        tabs = [r for r in root if r['metadata']['catalogid'] == '1803_sczm' and r['metadata']['tabkey'] == 'tab1']
        if len(tabs) != 1:
            raise ValueError()
        meta, rows = tabs[0]['metadata'], tabs[0]['data']
        if meta['cols']['cjje'] != '成交金额<br>(亿元)' or meta['cols']['lbmc'] != '证券类别' or not isinstance(rows, list) or len(rows) > 100:
            raise ValueError()
        if not rows and meta['subname'] in ('', day):
            return []
        if meta['subname'] != day:
            raise ActivityError('source_date_mismatch')
        wanted = ('主板A股', '创业板A股')
        selected = [(unescape(r['lbmc']).strip(), r['cjje']) for r in rows if unescape(r['lbmc']).strip() in wanted]
        if len(selected) != 2 or {x[0] for x in selected} != set(wanted):
            raise ValueError()
        result = []
        for name, value in selected:
            if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)\.[0-9]{2}', value):
                raise ActivityError('source_precision_mismatch')
            raw = value.replace(',', '')
            number(raw)
            result.append((name, raw))
        return result
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        if isinstance(error, ActivityError):
            raise
        raise ActivityError('invalid_source_response') from error


def original_parts(original: Original, market: str, day: str) -> list[tuple[str, str]]:
    """逐份检查与重放共用；不为校验单份日报构造整个三年快照。"""
    if len(original.content) > MARKET_MAX_BYTES:
        raise ActivityError('source_size_exceeded')
    if original.source != market or original.url != daily_url(market, day):
        raise ActivityError('source_identity_mismatch')
    if market == 'sse':
        return [] if load(original.content, source=True).get('result') == [] else sse_parts(original.content, day)
    return szse_parts(original.content, day)


def manifest(window, originals: list[Original], *, policy_version: str = TWO_POLICY) -> Snapshot:
    """只从同日两市原分项重建事实；缺任一市场保留null，合计在读取时算。"""
    if policy_version != TWO_POLICY:
        raise ActivityError('source_policy_version_unknown')
    dates = list(window.dates)
    expected = {daily_url(m, d): (m, d) for m in ('sse', 'szse') for d in dates}
    values: dict[tuple[str, str], list] = {}
    members = []
    for original in originals:
        location = expected.get(original.url)
        if location is None or original.source != location[0] or location in values:
            raise ActivityError('source_identity_mismatch')
        market, day = location
        key = market + '-a-json'
        parts = original_parts(original, market, day)
        values[location] = [fact(key, 'amount', raw, original, 'category='+label) for label, raw in parts] or [missing(key, 'amount', 'source_missing')]
        members.append({'source': original.source, 'object_id': original.object_id, 'url': original.url})
    rows = [{'trade_date': day, 'components': {m: values.get((m, day), [missing(m+'-a-json', 'amount', 'source_missing')])
                                            for m in ('sse', 'szse')}} for day in dates]
    return {'schema_version': VERSION, 'series_id': TWO_MARKET, 'price_snapshot_id': None,
            'anchor_date': window.anchor_date, 'window': window.as_dict(), 'calendar_version': window.calendar_version,
            'calendar_dates': dates, 'market_calendars': {'sse': dates, 'szse': dates},
            'completion_basis': window.completion_basis, 'source_policy_version': TWO_POLICY,
            'parser_version': 'activity-parser-sse-szse-v1', 'pit_grade': 'latest_only', 'currency': 'CNY',
            'source_scope': 'SSE-main-A+STAR;SZSE-main-A+ChiNext;excludes-BSE;single-official-source',
            'source_revision_relation': 'unknown', 'source_revision_id': None, 'binding': None,
            'sources': sorted(members, key=lambda m: m['url']), 'rows': rows}
