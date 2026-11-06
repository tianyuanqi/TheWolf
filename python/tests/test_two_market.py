"""S2两市官方格式及隔离HTTP/启动链；网络替身不替换准入、计算或存储。"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from email.message import Message

from pmi.market_data.activity import calculations, fetch, two_market
from pmi.market_data.activity.model import ActivityError, Options, Original, TWO_MARKET, TWO_POLICY, MARKET_MAX_BYTES, canonical, digest
from pmi.market_data.index_history_calendar import complete_window, SHANGHAI
from test_market_activity import Client
from test_index_series_contract import WINDOW
from http_test_support import disk

STAMP = '2026-10-31T00:00:00+00:00'


def market_original(market, day, *, empty=False, value='1.00'):
    """带明确合成值的官方结构替身，仅供隔离测试。"""
    if market == 'sse':
        content = {'result': [] if empty else [{'PRODUCT_CODE': code, 'TRADE_DATE': day.replace('-', ''), 'TRADE_AMT': value} for code in ('01', '03')]}
    else:
        content = [{'metadata': {'catalogid': '1803_sczm', 'tabkey': 'tab1', 'subname': '' if empty else day,
                                 'cols': {'cjje': '成交金额<br>(亿元)', 'lbmc': '证券类别'}},
                    'data': [] if empty else [{'lbmc': name, 'cjje': value} for name in ('主板A股', '创业板A股')]}]
    return Original(market, canonical(content), two_market.daily_url(market, day), STAMP, STAMP)


class TwoMarketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wolf-s2-two-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.price, self.activity = self.base/'price', self.base/'activity'
        self.price.mkdir(); self.activity.mkdir()
        self.ledger = self.base/'budget.json'
        self.ledger.write_bytes(canonical({'cycle': 's2-test', 'attempts': 0, 'bytes': 0, 'limit_attempts': 2200, 'limit_bytes': 2200*MARKET_MAX_BYTES}))

    def client(self, **kwargs):
        client = Client(self.price, self.activity, write_series=(TWO_MARKET,), max_attempts=2200,
                        max_bytes=2200*MARKET_MAX_BYTES, budget_cycle='s2-test', budget_ledger=self.ledger, **kwargs)
        self.addCleanup(client.app.state.updates.close)
        return client

    def test_two_market_formula_missing_and_old_formula_not_reinterpreted(self):
        originals = [market_original(m, d, empty=m=='szse' and d==WINDOW.dates[-2]) for d in WINDOW.dates for m in ('sse', 'szse')]
        manifest = two_market.manifest(WINDOW, originals)
        result = calculations.calculate({**manifest, 'activity_id': digest(manifest)}, calculations.TWO_FORMULA)
        self.assertEqual(result['series'][0]['rows'][-1]['total']['value'], '400000000.00')
        self.assertIsNone(result['series'][0]['rows'][-2]['total']['value'])
        self.assertIsNone(result['comparisons']['day_5']['comparison']['value'])
        with self.assertRaises(ActivityError):
            calculations.calculate({**manifest, 'activity_id': digest(manifest)}, calculations.FORMULA)
        self.assertNotIn('bse', manifest['rows'][-1]['components'])

    def test_json_date_unit_categories_and_bounds(self):
        raw = json.loads(market_original('szse', WINDOW.end).content)
        self.assertEqual(two_market.szse_parts(canonical(raw), WINDOW.end), [('主板A股', '1.00'), ('创业板A股', '1.00')])
        for mutate in (lambda v: v[0]['metadata'].update(subname='2020-01-01'),
                       lambda v: v[0]['metadata']['cols'].update(cjje='成交金额(元)'),
                       lambda v: v[0]['data'].append(v[0]['data'][0]),
                       lambda v: v[0]['data'][0].update(cjje='1.001')):
            bad = deepcopy(raw); mutate(bad)
            with self.assertRaises(ActivityError): two_market.szse_parts(canonical(bad), WINDOW.end)
        with self.assertRaises(ActivityError):
            two_market.manifest(WINDOW, [Original('szse', b'x'*(MARKET_MAX_BYTES+1), two_market.daily_url('szse', WINDOW.end), STAMP, STAMP)])

    def test_synthetic_official_json_date_precision_and_empty(self):
        for day in ('2023-10-30','2026-10-29','2023-11-04'):
            self.assertEqual(two_market.szse_parts(market_original('szse',day,value='123.45').content,day), [('主板A股','123.45'),('创业板A股','123.45')])
            self.assertEqual(two_market.szse_parts(market_original('szse',day,empty=True).content,day), [])

    def test_budget_first_window_bound_and_restart(self):
        client = self.client(); options = client.config.activity_options
        before = self.ledger.read_bytes()
        fetch.preflight(options, 1454, 1454*MARKET_MAX_BYTES)
        fetch.preflight(options, 2200, 2200*MARKET_MAX_BYTES)
        self.assertEqual(self.ledger.read_bytes(), before)
        fetch.reserve(options, MARKET_MAX_BYTES)
        with self.assertRaises(ActivityError): fetch.preflight(options, 2200, 2200*MARKET_MAX_BYTES)
        restart = self.client().config.activity_options
        self.assertEqual(json.loads(self.ledger.read_bytes())['attempts'], 1)
        fetch.reserve(restart)
        self.assertEqual(json.loads(self.ledger.read_bytes())['bytes'], MARKET_MAX_BYTES+1048576)

    def test_insufficient_ledger_zero_network_and_no_current(self):
        client = self.client(); rt = client.config.market_data._activity_runtime
        self.ledger.write_bytes(canonical({'cycle':'s2-test','attempts':2199,'bytes':2199*MARKET_MAX_BYTES,'limit_attempts':2200,'limit_bytes':2200*MARKET_MAX_BYTES}))
        with patch.object(fetch, 'fetch', side_effect=AssertionError('必须零网络')) as network:
            result = rt.start(TWO_MARKET, 'budget-short', {'anchor_date':WINDOW.anchor_date,'expected_activity_id':None}, client.config.activity_config_id, client.app.state.boundary.instance)
        self.assertEqual(result['reason'], 'activity_budget_exhausted'); network.assert_not_called()
        self.assertIsNone(rt.current(TWO_MARKET, WINDOW.anchor_date))

    def test_transport_caps_charge_once_and_cancel_never_requests(self):
        options=self.client().config.activity_options
        target=two_market.daily_url('szse',WINDOW.end)
        class Response(BytesIO):
            status=200
            headers=Message()
            headers['Content-Type']='application/json'
            def geturl(self):return target
        class Cancel:
            def wait(self, seconds):return False
            def is_set(self):return False
        for size,success in ((MARKET_MAX_BYTES,True),(MARKET_MAX_BYTES+1,False)):
            response=Response(b'x'*size)
            with patch.object(fetch,'build_opener') as opener:
                opener.return_value.open.return_value=response
                if success:
                    self.assertEqual(len(fetch.fetch('szse-a-json',[WINDOW.end],options,Cancel()).content),size)
                else:
                    with self.assertRaisesRegex(ActivityError,'source_size_exceeded'):
                        fetch.fetch('szse-a-json',[WINDOW.end],options,Cancel())
                self.assertEqual(opener.return_value.open.call_count,1)
        self.assertEqual(json.loads(self.ledger.read_bytes())['bytes'],2*MARKET_MAX_BYTES)
        cancel=Event();cancel.set();before=self.ledger.read_bytes()
        with patch.object(fetch,'build_opener') as opener:
            with self.assertRaisesRegex(ActivityError,'activity_cancelled'):
                fetch.fetch('szse-a-json',[WINDOW.end],options,cancel)
            opener.assert_not_called()
        self.assertEqual(self.ledger.read_bytes(),before)

    def test_real_http_publish_replay_and_cross_anchor_reuse(self):
        client = self.client(); rt = client.config.market_data._activity_runtime
        calls = []
        def obtain(series, days, options, cancel):
            calls.append((series,days[0])); fetch.reserve(options, MARKET_MAX_BYTES)
            return market_original(series.split('-')[0], days[0])
        path = '/api/market-activity/'+TWO_MARKET
        with patch.object(fetch, 'fetch', side_effect=obtain):
            result = client.request(path+'/update','POST',body=canonical({'anchor_date': WINDOW.anchor_date,'expected_activity_id':None}))
            self.assertEqual(result.status,200,result.body);self.assertEqual(result.json()['state'],'completed',result.body)
            aid = result.json()['activity_id']
            current = client.request(path+'?anchor_date='+WINDOW.anchor_date)
            self.assertEqual(current.status,200,current.body)
            fixed = client.request(path+'/snapshots/'+aid)
            self.assertEqual(fixed.status,200,fixed.body)
            calculated = client.request(path+'/snapshots/'+aid+'/calculations?formula_version='+calculations.TWO_FORMULA)
            self.assertEqual(calculated.status,200,calculated.body)
            self.assertEqual(calculated.json()['series'][0]['rows'][-1]['total']['value'],'400000000.00')
            self.assertEqual(len(calls),len(WINDOW.dates)*2)
            newer = complete_window(datetime(2026,10,31,tzinfo=SHANGHAI))
            next_result = rt.start(TWO_MARKET, 'next-anchor', {'anchor_date':newer.anchor_date,'expected_activity_id':None},client.config.activity_config_id,client.app.state.boundary.instance)
            self.assertEqual(next_result['state'],'completed',next_result)
            self.assertEqual(len(calls),len(set(WINDOW.dates)|set(newer.dates))*2)
            self.assertEqual(rt.fixed(TWO_MARKET,aid)['activity_id'],aid)
            self.assertEqual(rt.current(TWO_MARKET,WINDOW.anchor_date)['activity_id'],aid)
            # 显式更新的来源失败不移动已发布指针，启动失败不自动重试。
            latest=rt.current(TWO_MARKET,newer.anchor_date)['activity_id']
            with patch.object(rt,'_obtain_market',side_effect=ActivityError('source_fetch_failed')) as broken:
                failed=rt.start(TWO_MARKET,'failed-refresh',{'anchor_date':newer.anchor_date,'expected_activity_id':latest},client.config.activity_config_id,client.app.state.boundary.instance)
            self.assertEqual(failed['state'],'failed');self.assertEqual(broken.call_count,1)
            self.assertEqual(rt.current(TWO_MARKET,newer.anchor_date)['activity_id'],latest)

    def test_startup_empty_is_read_only_and_market_target_does_not_use_price(self):
        client=self.client();before=disk(self.base)
        client.app.state.updates.start_startup()
        self.assertIsNone(client.app.state.updates._startup_thread)
        self.assertEqual(disk(self.base),before)
        enabled=self.client(startup_series=(TWO_MARKET,)); rt=enabled.config.market_data._activity_runtime
        captured=[]
        with patch.object(rt,'start',side_effect=lambda s,r,p,c,i,**kw: captured.append(p) or {'state':'completed'}):
            enabled.app.state.updates.start_startup();enabled.app.state.updates._startup_thread.join(5)
        self.assertEqual(captured,[{'anchor_date':rt.market_anchor_date,'expected_activity_id':None}])
        ready=enabled.request('/api/market-activity/session').json()
        self.assertEqual(ready['market_anchor_date'],rt.market_anchor_date)
        self.assertEqual(ready['startup_series'],[TWO_MARKET])
        self.assertNotEqual(client.config.activity_config_id,enabled.config.activity_config_id)
        self.assertEqual(client.config.index_config_id,enabled.config.index_config_id)
        with self.assertRaises(ValueError): Options(self.activity,startup_series=(TWO_MARKET,))

    def test_mixed_startup_missing_or_failed_price_does_not_skip_market(self):
        index='sse:000001:price'
        for missing_price in (True,False):
            with self.subTest(missing_price=missing_price):
                client=Client(self.price,self.activity,write_series=(index,TWO_MARKET),startup_series=(index,TWO_MARKET))
                self.addCleanup(client.app.state.updates.close)
                rt=client.config.market_data._activity_runtime;calls=[]
                price=None if missing_price else {'format':'v2','snapshot':{'snapshot_id':'a'*64}}
                def start(series, request, params, config, instance, **kwargs):
                    calls.append((series,params))
                    return {'series_id':series,'state':'failed' if series==index else 'completed','reason':'source_fetch_failed' if series==index else None}
                before=disk(self.base)
                with patch.object(type(rt.parent),'read_daily',return_value=price),patch.object(rt,'start',side_effect=start):
                    client.app.state.updates.start_startup();client.app.state.updates._startup_thread.join(5)
                self.assertFalse(client.app.state.updates._startup_thread.is_alive())
                results=client.app.state.updates.activity_startup_results
                self.assertEqual([r['series_id'] for r in results],[index,TWO_MARKET])
                self.assertEqual(results[0]['reason'],'price_binding_unverifiable' if missing_price else 'source_fetch_failed')
                self.assertEqual(results[1]['state'],'completed')
                self.assertEqual(calls[-1],(TWO_MARKET,{'anchor_date':rt.market_anchor_date,'expected_activity_id':None}))
                self.assertEqual([s for s,_ in calls],[TWO_MARKET] if missing_price else [index,TWO_MARKET])
                self.assertEqual(disk(self.base),before)

    def test_mixed_startup_cancellation_stops_later_explicit_series(self):
        index='sse:000001:price'
        client=Client(self.price,self.activity,write_series=(index,TWO_MARKET),startup_series=(index,TWO_MARKET))
        self.addCleanup(client.app.state.updates.close);rt=client.config.market_data._activity_runtime
        def cancelled(*args,**kwargs):
            rt.cancel.set();return {'series_id':index,'state':'failed','reason':'activity_cancelled'}
        with patch.object(type(rt.parent),'read_daily',return_value={'format':'v2','snapshot':{'snapshot_id':'a'*64}}),patch.object(rt,'start',side_effect=cancelled) as start:
            result=rt.startup(client.config.activity_config_id,client.app.state.boundary.instance)
        self.assertEqual(start.call_count,1);self.assertEqual(len(result),1)
        self.assertIsNone(rt.store.current(TWO_MARKET,rt.market_anchor_date))
