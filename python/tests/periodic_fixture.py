"""周期更新共用合成夹具；来源响应替身保留真实预留、解析及发布。"""
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import datetime
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from pmi.market_data import MarketData, ActivityOptions, SnapshotError
from pmi.market_data import index_series_fetch as price_fetch, index_series_store as store
from pmi.market_data.activity import fetch, runtime
from pmi.market_data.activity.model import INDEX_IDS, TWO_MARKET, Original, canonical
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_history_calendar import complete_window, SHANGHAI
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.writer_lock import writer_lock
from pmi.market_data.periodic_budget import initialize, MIB
from test_index_series_contract import originals
from test_index_series_runtime import state
from test_two_market import market_original


def price_originals(index, window):
    """固定合成OHLC并加入已确认来源格式的量额；不读取既有金融数据。"""
    items = list(originals(index, window))
    if index.provider == 'csindex':
        raw = json.loads(items[0].content)
        for row in raw['data']:
            row.update(tradingValue='1.23', tradingVol='10000')
        items[0] = replace(items[0], content=canonical(raw))
    stamp = window.anchor_date+'T00:00:00Z'
    return tuple(replace(item, started_at=stamp, completed_at=stamp) for item in items)


def activity_original(data: MarketData, series: str, dates: list[str]) -> Original:
    if series.endswith('-a-json'):
        return market_original(series.split('-')[0], dates[0])
    from pmi.market_data.activity.sources import url
    index = get_index(series)
    price = data.read_daily(series)['snapshot']
    rows = []
    for row in price['evidence'][0]['rows']:
        v = row['raw_values']; stamp = int(datetime.fromisoformat(row['trade_date']).replace(tzinfo=SHANGHAI).timestamp()*1000)
        rows.append([str(stamp),v['close'],v['high'],v['open'],v['low'],v['close'],'0','0','123000000.00','10000','0'])
    body = {'code':'200','message':'','data':{'indexCode':index.code,'indexName':index.name,'indexEName':index.english_name,
            'item':['timestamp','current','high','open','low','close','chg','percent','amount','volume','avg'],'data':rows}}
    return Original('cnindex-raw', canonical(body), url(series,dates), '2026-10-31T00:00:00Z', '2026-10-31T00:00:01Z')


def seed(root: Path, anchor='2026-10-29') -> None:
    """创建隔离旧版本，供一个新增交易日消耗12次的独立预期。"""
    for name in ('data','activity','runtime','cache'):
        (root/name).mkdir(mode=0o700)
    price_root, activity_root = root/'data', root/'activity'
    window = complete_window(datetime.fromisoformat(anchor+'T07:00:00+08:00'))
    with writer_lock(price_root):
        for sid in INDEX_IDS:
            index = get_index(sid); items = price_originals(index, window)
            store.prepare_directories(price_root,index)
            store.publish(price_root,index,window,build_manifest(index,window,items),items,{**state(index),'target_start':window.start,'target_end':window.end})
    ledger = root/'seed-budget.json'
    ledger.write_bytes(canonical({'cycle':'fixture','attempts':0,'bytes':0,'limit_attempts':2200,'limit_bytes':160*MIB}))
    data = MarketData(price_root,{},activity_options=ActivityOptions(activity_root,write_series=(*INDEX_IDS,TWO_MARKET),max_attempts=2200,max_bytes=160*MIB,budget_cycle='fixture',budget_ledger=ledger))
    def obtain(series, dates, options, cancel): return activity_original(data, series, dates)
    with patch.object(fetch,'fetch',obtain):
        for sid in (*INDEX_IDS,TWO_MARKET):
            key = 'anchor_date' if sid==TWO_MARKET else 'price_snapshot_id'
            target = anchor if sid==TWO_MARKET else data.read_daily(sid)['snapshot']['snapshot_id']
            result = data.activity('start',sid,'seed-'+str(len(list((activity_root/'operations').glob('*'))) if (activity_root/'operations').exists() else 0), {key:target,'expected_activity_id':None},'fixture','fixture')
            assert result['state']=='completed', result
    data.close_updates(); initialize(price_root,activity_root)


@contextmanager
def transport(data: MarketData, control=lambda: {}):
    """价格子进程响应替身；量额只替换HTTP响应，其他出站控制不变。"""
    def price(parent,index,source,window,job_id,*,budget,guard=None,stop=None):
        while not control().get('release', True):
            if stop.wait(.1):
                raise SnapshotError('source_fetch_failed')
        entry = price_fetch.reserve(parent,index,source,window,job_id,budget,stop)
        success = False
        try:
            if index.index_id in control().get('fail_ids',[]): raise SnapshotError('source_fetch_failed')
            result = next(x for x in price_originals(index,window) if x.source==source)
            success = True
            return result
        finally:
            count = len(result.content) if success else MIB
            if budget.lease: budget.lease.settle(entry['periodic_attempt'],count if success else None,success)
            store.append_record(parent/'index-v2-network-ledger.jsonl',{'event':'finished','attempt_id':entry['attempt_id'],'index_id':index.index_id,'job_id':job_id,'source':source,'success':success,'charged_bytes':count,'finished_at':entry['started_at']})
    class Response(BytesIO):
        status=200
        def __init__(self,original):
            super().__init__(original.content); self.target=original.url; self.headers=Message();self.headers['Content-Type']='application/json'
        def geturl(self):return self.target
    class Opener:
        def open(self,request,timeout):
            parts=urlsplit(request.full_url);query=parse_qs(parts.query)
            if 'szse.cn' in parts.hostname:
                series,dates='szse-a-json',[query['txtQueryDate'][0]]
            elif 'sse.com.cn' in parts.hostname:
                series,dates='sse-a-json',[query['SEARCH_DATE'][0]]
            else:
                series='szse:'+query['indexCode'][0]+':price'
                dates=data.read_daily(series)['snapshot']['calendar_dates']
            original=activity_original(data,series,dates)
            assert original.url==request.full_url
            return Response(original)
    with ExitStack() as stack:
        stack.enter_context(patch('pmi.market_data.index_series_update.fetch_bounded',price))
        stack.enter_context(patch.object(price_fetch,'MIN_HOST_INTERVAL_SECONDS',0))
        stack.enter_context(patch.object(fetch,'build_opener',lambda *args:Opener()))
        yield
