"""三市官方原分项与独立北交所日历；旧三市v1重放留在facts。"""
from __future__ import annotations

from datetime import date, timedelta
import json

from . import two_market
from .facts import fact, missing
from .model import ActivityError, MARKET, MARKET_MAX_BYTES, Original, Snapshot, unique

POLICY = 'activity-source-policy-sse-szse-bse-v1'
CALENDAR = 'cn-markets-sse-szse-bse-2023-2026-v1'
# 独立从北交所四份年度公告提取；不借用沪深休市常量。
HOLIDAYS = {2023: (('2022-12-31', '2023-01-02'),
        ('2023-01-21', '2023-01-27'),
        ('2023-04-05', '2023-04-05'),
        ('2023-04-29', '2023-05-03'),
        ('2023-06-22', '2023-06-24'),
        ('2023-09-29', '2023-10-06')),
 2024: (('2023-12-30', '2024-01-01'),
        ('2024-02-09', '2024-02-17'),
        ('2024-04-04', '2024-04-06'),
        ('2024-05-01', '2024-05-05'),
        ('2024-06-10', '2024-06-10'),
        ('2024-09-15', '2024-09-17'),
        ('2024-10-01', '2024-10-07')),
 2025: (('2025-01-01', '2025-01-01'),
        ('2025-01-28', '2025-02-04'),
        ('2025-04-04', '2025-04-06'),
        ('2025-05-01', '2025-05-05'),
        ('2025-05-31', '2025-06-02'),
        ('2025-10-01', '2025-10-08')),
 2026: (('2026-01-01', '2026-01-03'),
        ('2026-02-15', '2026-02-23'),
        ('2026-04-04', '2026-04-06'),
        ('2026-05-01', '2026-05-05'),
        ('2026-06-19', '2026-06-21'),
        ('2026-09-25', '2026-09-27'),
        ('2026-10-01', '2026-10-07'))}
SOURCES = ({'year': 2023,
  'exchange': 'bse',
  'url': 'https://www.bse.cn/important_news/200014364.html',
  'evidence_kind': 'http_original',
  'evidence_sha256': '111997d447d650a059c4926563f3f949cbf03cb475adb67ae2d4ca4749078529'},
 {'year': 2024,
  'exchange': 'bse',
  'url': 'https://www.bse.cn/important_news/200020235.html',
  'evidence_kind': 'http_original',
  'evidence_sha256': 'cc6195f278a3bf0ecddd1699ca7995724006d6e02969a2adc68bb1d2d4fbf837'},
 {'year': 2025,
  'exchange': 'bse',
  'url': 'https://www.bse.cn/important_news/200024437.html',
  'evidence_kind': 'http_original',
  'evidence_sha256': 'a493234de8ddb5d1a60a7ed360e02cfb65af6ab4cfa01cc1e0e22d1fa078b5a6'},
 {'year': 2026,
  'exchange': 'bse',
  'url': 'https://www.bse.cn/important_news/200027428.html',
  'evidence_kind': 'http_original',
  'evidence_sha256': '1d6178157837f021dcb98c1206ee2f6f8cafcadbbb5b1cb0ac3637bbe82387ab'})


def bse_dates(start: str, anchor: str) -> list[str]:
    """按北交所年度公告生成完成日，未知年份关闭；不由空日报推断休市。"""
    day, end = date.fromisoformat(start), date.fromisoformat(anchor)
    if any(year not in HOLIDAYS for year in range(day.year, end.year + 1)):
        raise ActivityError('calendar_uncovered')
    dates = []
    while day < end:
        if day.weekday() < 5 and not any(left <= day.isoformat() <= right for left, right in HOLIDAYS[day.year]):
            dates.append(day.isoformat())
        day += timedelta(days=1)
    return dates


def daily_url(market: str, day: str) -> str:
    """仅固定官网公开日报，日期须为规范ISO日；不接受调用方URL。"""
    if date.fromisoformat(day).isoformat() != day:
        raise ActivityError('source_date_mismatch')
    if market != 'bse':
        return two_market.daily_url(market, day)
    return 'https://www.bse.cn/marketStatController/dailyReport.do?HQJSRQ=' + day.replace('-', '')


def original_parts(original: Original, market: str, day: str) -> list[tuple[str, str]]:
    """JSONP仅剥离固定null包装，精确解析唯一主记录；绝不执行远端代码。"""
    if market != 'bse':
        return two_market.original_parts(original, market, day)
    if len(original.content) > MARKET_MAX_BYTES:
        raise ActivityError('source_size_exceeded')
    if original.source != 'bse' or original.url != daily_url('bse', day):
        raise ActivityError('source_identity_mismatch')
    try:
        text = original.content.decode('utf-8').strip()
        if not text.startswith('null(') or not text.endswith(')'):
            raise ValueError()
        rows = json.loads(text[5:-1], object_pairs_hook=unique, parse_float=str, parse_int=str,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(r, dict) for r in rows):
            raise ValueError()
        if any(r.get('rq') != day.replace('-', '') for r in rows):
            raise ActivityError('source_date_mismatch')
        selected = [r for r in rows if r.get('xxzrlx') == '2']
        if len(selected) > 1:
            raise ActivityError('source_identity_mismatch')
        if not selected or selected[0].get('hqcjje') is None:
            return []
        # fact执行非负、最多分精度及数值上限验证；解析入口也立即验证以停止坏批。
        raw = selected[0]['hqcjje']
        fact('bse-a-json', 'amount', raw, original, 'category=2')
        return [('2', raw)]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
        if isinstance(error, ActivityError):
            raise
        raise ActivityError('invalid_source_response') from error


def calendars(window) -> dict[str, list[str]]:
    """分别生成日历，合计按并集逐日保留缺市。"""
    return {'sse': list(window.dates), 'szse': list(window.dates),
            'bse': bse_dates(window.natural_start, window.anchor_date)}


def manifest(window, originals: list[Original]) -> Snapshot:
    """保存原分项和来源回执引用；同日三市求和仍在既有读取公式中执行。"""
    cal = calendars(window)
    dates = sorted(set().union(*map(set, cal.values())))
    expected = {daily_url(m, d): (m, d) for m, days in cal.items() for d in days}
    values, members = {}, []
    for original in originals:
        location = expected.get(original.url)
        if location is None or original.source != location[0] or location in values:
            raise ActivityError('source_identity_mismatch')
        market, day = location
        key = market + '-a-json'
        parts = original_parts(original, market, day)
        values[location] = [fact(key, 'amount', raw, original, 'category='+label) for label, raw in parts] or [missing(key, 'amount', 'source_missing')]
        members.append({'source': market, 'object_id': original.object_id, 'url': original.url})
    result = two_market.manifest(window, [])
    basis = window.completion_basis
    basis['sources'] += [dict(x) for x in SOURCES]
    basis['limitations'] += ['北交所日历独立依据年度公告；临时休市及交易方式细分未穷尽核验。']
    result.update(series_id=MARKET, calendar_version=CALENDAR, calendar_dates=dates,
                  window={**window.as_dict(), 'start': dates[0], 'end': dates[-1], 'expected_count': len(dates), 'actual_count': len(dates)},
                  market_calendars=cal, completion_basis=basis, source_policy_version=POLICY,
                  parser_version='activity-parser-sse-szse-bse-v1',
                  source_scope='SSE-main-A+STAR;SZSE-main-A+ChiNext;BSE-stocks-xxzrlx-2;single-official-source;trading-method-scope-unverified',
                  sources=sorted(members, key=lambda m: m['url']),
                  rows=[{'trade_date': d, 'components': {m: values.get((m, d), [missing(m+'-a-json', 'amount', 'source_missing' if d in cal[m] else 'calendar_unknown')]) for m in cal}} for d in dates])
    return result
