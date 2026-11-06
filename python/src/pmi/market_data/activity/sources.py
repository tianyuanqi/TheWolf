"""固定官方量额解析；准入缺口保留，网络与解析分离。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext
from io import BytesIO
import re
from urllib.parse import urlencode
import zipfile
from xml.etree import ElementTree

from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_history_calendar import SHANGHAI
from .model import ActivityError, INDEX_IDS, MAX_BYTES, Original, load, number, rule


def url(series: str, dates: list[str]) -> str:
    """只构造已登记指数端点；未知市场入口不猜测。"""
    if series not in INDEX_IDS or not dates:
        raise ActivityError('source_unverified')
    index = get_index(series)
    if index.provider == 'csindex':
        return 'https://www.csindex.com.cn/csindex-home/perf/index-perf?' + urlencode({
            'indexCode': index.code, 'startDate': dates[0].replace('-', ''), 'endDate': dates[-1].replace('-', '')})
    return 'https://hq.cnindex.com.cn/market/market/getIndexDailyData?' + urlencode({
        'indexCode': index.code, 'startDate': dates[0], 'endDate': dates[-1], 'frequency': 'day'})


def parse_index(series: str, original: Original, dates: list[str]) -> list[dict]:
    """读取官方原数值及同记录OHLC；不以解析成功取代来源准入。"""
    expected = url(series, dates)
    # B来源补证原件省略frequency；同一固定端点的两种已登记日线URL均保留。
    accepted = {expected}
    if expected.endswith('&frequency=day'):
        accepted.add(expected.removesuffix('&frequency=day'))
    if len(original.content) > MAX_BYTES or original.url not in accepted or original.source != rule(series).source:
        raise ActivityError('source_identity_mismatch')
    root = load(original.content, source=True)
    index = get_index(series)
    rows = []
    try:
        if index.provider == 'csindex':
            if root['code'] != '200' or root['success'] is not True or root['msg'] != 'Success':
                raise ActivityError('invalid_source_response')
            data = root['data']
            if not isinstance(data, list) or len(data) > 1100:
                raise ActivityError('invalid_source_response')
            for i, item in enumerate(data):
                if (item['indexCode'], item['indexNameCn'], item['indexNameCnAll']) != (index.code, index.name, index.full_name):
                    raise ActivityError('source_identity_mismatch')
                day = item['tradeDate']
                if not isinstance(day, str) or not re.fullmatch('[0-9]{8}', day):
                    raise ActivityError('source_date_mismatch')
                rows.append({'trade_date': f'{day[:4]}-{day[4:6]}-{day[6:]}',
                             'ohlc': {k: item[k] for k in ('open', 'high', 'low', 'close')},
                             'volume': item.get('tradingVol'), 'amount': item.get('tradingValue'), 'locator': f'data[{i}]'})
        else:
            data = root['data']
            if root['code'] != '200' or root['message'] != '' or (data['indexCode'], data['indexName'], data['indexEName']) != (index.code, index.name, index.english_name):
                raise ActivityError('source_identity_mismatch')
            if data['item'] != ['timestamp', 'current', 'high', 'open', 'low', 'close', 'chg', 'percent', 'amount', 'volume', 'avg']:
                raise ActivityError('invalid_source_response')
            if not isinstance(data['data'], list) or len(data['data']) > 1100:
                raise ActivityError('invalid_source_response')
            for i, item in enumerate(data['data']):
                if not isinstance(item, list) or len(item) != 11 or not isinstance(item[0], str) or not re.fullmatch('[0-9]{13}', item[0]):
                    raise ActivityError('source_date_mismatch')
                moment = datetime.fromtimestamp(int(item[0]) / 1000, SHANGHAI)
                if (moment.hour, moment.minute, moment.second, moment.microsecond) != (0, 0, 0, 0):
                    raise ActivityError('source_date_mismatch')
                rows.append({'trade_date': moment.date().isoformat(),
                             'ohlc': dict(zip(('open', 'high', 'low', 'close'), (item[3], item[2], item[4], item[5]))),
                             'volume': item[9], 'amount': item[8], 'locator': f'data.data[{i}]'})
    except (KeyError, TypeError, IndexError, OverflowError, OSError) as error:
        raise ActivityError('invalid_source_response') from error
    found = [x['trade_date'] for x in rows]
    if not rows or len(found) != len(set(found)) or set(found) - set(dates):
        raise ActivityError('source_date_mismatch')
    return sorted(rows, key=lambda x: x['trade_date'])


def sse_parts(content: bytes, day: str) -> list[tuple[str, str]]:
    """沪市01主板A和03科创板原亿元分项；仅解析原值，不存两项相加的衍生结果。"""
    root = load(content, source=True)
    try:
        records = root['result']
        selected = [r for r in records if r['PRODUCT_CODE'] in ('01', '03')]
        if len(selected) != 2 or {r['PRODUCT_CODE'] for r in selected} != {'01', '03'} or any(r['TRADE_DATE'] != day.replace('-', '') for r in selected):
            raise ActivityError('source_date_mismatch')
        with localcontext() as ctx:
            ctx.prec = 48
            values = [number(r['TRADE_AMT']) for r in selected]
            if any(x != x.quantize(Decimal('.01')) for x in values):
                raise ActivityError('source_precision_mismatch')
            return [(r['PRODUCT_CODE'], r['TRADE_AMT']) for r in selected]
    except (KeyError, TypeError) as error:
        raise ActivityError('invalid_source_response') from error


def inspect_szse_xlsx(content: bytes) -> dict[str, str]:
    """有界检查现有深圳导出，未证明日期绑定，结果不能直接成为有效金融输入。"""
    if len(content) > MAX_BYTES:
        raise ActivityError('source_size_exceeded')
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > 32 or len({x.filename for x in members}) != len(members) or sum(x.file_size for x in members) > 4 * MAX_BYTES:
                raise ActivityError('xlsx_bounds_exceeded')
            result, cells = {}, 0
            for item in members:
                if '..' in item.filename.split('/') or item.filename.startswith('/') or item.flag_bits & 1:
                    raise ActivityError('xlsx_unsafe_member')
                if not (item.filename.endswith('.xml') or item.filename.endswith('.rels')):
                    continue
                raw = archive.read(item)
                if len(raw) > MAX_BYTES or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
                    raise ActivityError('xlsx_unsafe_xml')
                root = ElementTree.fromstring(raw)
                for element in root.iter():
                    tag = element.tag.rsplit('}', 1)[-1]
                    if tag == 'Relationship' and element.attrib.get('TargetMode') == 'External':
                        raise ActivityError('xlsx_external_reference')
                    if tag == 'f':
                        raise ActivityError('xlsx_formula_rejected')
                    if tag == 'c':
                        cells += 1
                        if cells > 20000:
                            raise ActivityError('xlsx_bounds_exceeded')
                        result[item.filename + ':' + element.attrib.get('r', '')] = ''.join(element.itertext())
            return result
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError) as error:
        raise ActivityError('invalid_xlsx') from error


def market_url(market: str, day: str) -> str:
    """沪市已核对的固定日报请求；深圳日期和北交所入口未核准时不构造请求。"""
    if market != 'sse':
        raise ActivityError('source_unverified')
    return 'https://query.sse.com.cn/commonQuery.do?' + urlencode({
        'sqlId': 'COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C', 'PRODUCT_CODE': '01,02,03,11,17',
        'type': 'inParams', 'SEARCH_DATE': day})
