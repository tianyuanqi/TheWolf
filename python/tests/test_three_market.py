"""北交所接入：归档原件离线验证、隔离发布与真实预算调用链。"""
from dataclasses import replace
from datetime import datetime
from email.message import Message
from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from pmi.market_data import MarketData, ActivityOptions
from pmi.market_data.activity import three_market, two_market, fetch, calculations
from pmi.market_data.activity.model import ActivityError, Original, MARKET, TWO_MARKET, MARKET_MAX_BYTES, canonical, digest, rule
from pmi.market_data.index_history_calendar import complete_window
from pmi.market_data.periodic_budget import initialize, PeriodicOptions
from test_two_market import market_original
from test_market_activity import Client
from sqlite_fixture import initialize as initialize_sqlite, set_activity_budget, activity_budget_bytes
from test_periodic_budget import Clock

ANCHOR = '2026-11-05'
WINDOW = complete_window(datetime.fromisoformat(ANCHOR+'T07:00:00+08:00'))
STAMP = '2026-11-05T00:00:00+00:00'


def original(market, day, *, empty=False):
    """明确合成数据；仅替换来源字节，不替换准入、日期、预算、存储和计算。"""
    if market != 'bse':
        return replace(market_original(market, day, empty=empty), started_at=STAMP, completed_at=STAMP)
    raw = [] if empty else [{'xxzrlx':'2','rq':day.replace('-',''),'hqcjje':'123.45'}]
    return Original('bse', b'null('+canonical(raw)+b')', three_market.daily_url('bse', day), STAMP, STAMP)


class ThreeMarketTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wolf-bse-test-',dir='/private/tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.price=self.act=self.root/'data';self.price.mkdir();initialize_sqlite(self.price)
        self.ledger=self.price/'facts.sqlite';set_activity_budget(self.price, canonical({'cycle':'bse-test','attempts':0,'bytes':0,'limit_attempts':2200,'limit_bytes':2200*MARKET_MAX_BYTES}))
        self.client=Client(self.price,self.act,write_series=(TWO_MARKET,MARKET),max_attempts=2200,max_bytes=2200*MARKET_MAX_BYTES,budget_cycle='bse-test',budget_ledger=self.ledger)
        self.addCleanup(self.client.app.state.updates.close)
        self.rt=self.client.config.market_data._activity_runtime
        self.rt.clock=lambda:datetime.fromisoformat(ANCHOR+'T08:00:00+08:00')

    def publish(self,series=MARKET,anchor=ANCHOR,request='new',expected=None):
        return self.rt.start(series,request,{'anchor_date':anchor,'expected_activity_id':expected},self.client.config.activity_config_id,self.client.app.state.boundary.instance)

    def obtain(self,key,days,options,cancel,**kwargs):
        item=original(key.split('-')[0],days[0]);lease=kwargs.get('lease')
        if lease:
            attempt=lease.charge(item.url,MARKET_MAX_BYTES);lease.settle(attempt,len(item.content),True)
        else:fetch.reserve(options,MARKET_MAX_BYTES)
        return item

    def test_synthetic_raw_values_and_calendar(self):
        for day in ('2025-04-21','2026-10-29','2023-11-04'):
            self.assertEqual(three_market.original_parts(original('bse',day),'bse',day),[('2','123.45')])
            self.assertEqual(three_market.original_parts(original('bse',day,empty=True),'bse',day),[])
        dates=three_market.bse_dates('2023-11-05',ANCHOR)
        self.assertEqual(len(dates),726);self.assertEqual(dates[0],'2023-11-06');self.assertEqual(dates[-1],'2026-11-04')
        self.assertNotIn('2024-02-09',dates);self.assertNotIn('2026-02-23',dates)
        with self.assertRaisesRegex(ActivityError,'calendar_uncovered'):three_market.bse_dates('2024-01-01','2027-01-01')

    def test_parser_rejects_date_duplicate_precision_and_executable_wrapper(self):
        with self.assertRaisesRegex(ActivityError, "source_policy_version_unknown"):
            rule("sse:000001:price", three_market.POLICY)
        item=original('bse',WINDOW.end)
        for raw in [b'alert([])', b'null([{ "xxzrlx":"2","rq":"20261103","hqcjje":1}])',
                    b'null([{ "xxzrlx":"2","rq":"20261104","hqcjje":1.001}])',
                    b'null([{ "xxzrlx":"2","rq":"20261104","hqcjje":-1}])',
                    b'null([{ "xxzrlx":"2","rq":"20261104","hqcjje":1,"hqcjje":2}])',
                    b'null('+canonical([{'xxzrlx':'2','rq':'20261104','hqcjje':'1'}]*2)+b')']:
            with self.subTest(raw=raw),self.assertRaises(ActivityError):three_market.original_parts(replace(item,content=raw),'bse',WINDOW.end)
        with self.assertRaises(ActivityError):three_market.original_parts(replace(item,content=b'x'*(65537)),'bse',WINDOW.end)

    def test_http_three_markets_replay_missing_and_cross_anchor(self):
        with patch.object(fetch,'fetch',self.obtain):
            two=self.publish(TWO_MARKET,request='two');self.assertEqual(two['state'],'completed',two)
            result=self.publish();self.assertEqual(result['state'],'completed',result)
        self.assertEqual(json.loads(activity_budget_bytes(self.price))['attempts'],726*3)
        aid=result['activity_id'];value=self.rt.fixed(MARKET,aid)
        calc=self.rt.calculations(MARKET,aid,calculations.FORMULA)
        self.assertEqual(calc['series'][0]['rows'][-1]['total']['value'],'400000123.45')
        reply=self.client.request('/api/market-activity/'+MARKET+'/snapshots/'+aid)
        self.assertEqual(reply.status,200,reply.body)
        reply=self.client.request('/api/market-activity/session');self.assertEqual(reply.status,200,reply.body)
        self.assertEqual(json.loads(reply.body)['market_anchors'],{'sse_szse_bse':ANCHOR,'sse_szse':ANCHOR})
        self.rt.clock=lambda:datetime.fromisoformat('2026-11-06T08:00:00+08:00')
        with patch.object(fetch,'fetch',side_effect=ActivityError('source_fetch_failed')):
            failed=self.publish(anchor='2026-11-06',request='fail')
        self.assertEqual(failed['state'],'failed');self.assertEqual(self.rt.latest_market_anchor('2026-11-06',MARKET),ANCHOR)
        with patch.object(fetch,'fetch',self.obtain):new=self.publish(anchor='2026-11-06',request='next')
        self.assertEqual(new['state'],'completed',new);self.assertEqual(self.rt.latest_market_anchor('2026-11-06',MARKET),'2026-11-06')
        self.assertEqual(self.rt.fixed(MARKET,aid),value)
        # 新快照缺任一市必须为null，空主记录不是0。
        partial=three_market.manifest(WINDOW,[original('sse',WINDOW.end),original('szse',WINDOW.end),original('bse',WINDOW.end,empty=True)])
        output=calculations.calculate({**partial,'activity_id':digest(partial)},calculations.FORMULA)
        self.assertIsNone(output['series'][0]['rows'][-1]['total']['value'])

    def test_late_anchor_http_does_not_rollback_and_same_anchor_cas(self):
        with patch.object(fetch,'fetch',self.obtain):
            result=self.publish(request='seed-late')
        before=self.rt.store.json(*self.rt.store.location(MARKET,ANCHOR))
        ledger=activity_budget_bytes(self.price)
        def post(anchor,expected,request):
            return self.client.request('/api/market-activity/'+MARKET+'/update','POST',
                body=canonical({'anchor_date':anchor,'expected_activity_id':expected}),headers={'x-wolf-request-id':request})
        with patch.object(fetch,'fetch',side_effect=AssertionError('旧目标/错误CAS不得取数')):
            for anchor,expected,name in [('2026-11-04',None,'late-old'),(ANCHOR,None,'same-wrong')]:
                response=post(anchor,expected,name)
                self.assertEqual(response.status,409,response.body)
                self.assertEqual(json.loads(response.body)['detail']['code'],'activity_cas_conflict')
                self.assertEqual(self.rt.store.json(*self.rt.store.location(MARKET,ANCHOR)),before)
                self.assertIsNone(self.rt._operation(name))
            response=post(ANCHOR,result['activity_id'],'same-correct')
            self.assertEqual(response.status,200,response.body)
            self.assertEqual(json.loads(response.body)['state'],'completed')
        self.assertEqual(activity_budget_bytes(self.price),ledger)
        self.assertEqual(self.rt.latest_market_anchor(ANCHOR,MARKET),ANCHOR)
        self.assertIsNotNone(self.rt.fixed(MARKET,result['activity_id']))

    def test_budget_insufficient_no_network(self):
        set_activity_budget(self.price, canonical({'cycle':'bse-test','attempts':2199,'bytes':0,'limit_attempts':2200,'limit_bytes':2200*MARKET_MAX_BYTES}))
        with patch.object(fetch,'fetch',side_effect=AssertionError('不应联网')) as call:
            result=self.publish()
        self.assertEqual(result['reason'],'activity_budget_exhausted');call.assert_not_called()
        self.assertIsNone(self.rt.current(MARKET,ANCHOR))

    def test_shared_partial_failure_never_retries_and_withdrawn_not_reused(self):
        shared={};calls=[]
        def broken(key,days,*args,**kwargs):
            calls.append((key,days[0]))
            if key=='szse-a-json':raise ActivityError('source_fetch_failed')
            return original(key.split('-')[0],days[0])
        with patch.object(fetch,'fetch',broken):
            one=self.rt.start(TWO_MARKET,'shared-1',{'anchor_date':ANCHOR,'expected_activity_id':None},'c','i',shared=shared)
            n=len(calls)
            two=self.rt.start(MARKET,'shared-2',{'anchor_date':ANCHOR,'expected_activity_id':None},'c','i',shared=shared)
        self.assertEqual(one['state'],'failed');self.assertEqual(two['state'],'failed');self.assertEqual(len(calls),n)
        with patch.object(fetch,'fetch',self.obtain):self.publish(TWO_MARKET,request='commit')
        self.rt.blocked[TWO_MARKET]='0'*64
        plan=self.rt.network_plan(MARKET,WINDOW)
        self.assertEqual(len(plan),2178)

    def test_transport_limit_mime_interval_cancel_and_no_redirect(self):
        item=original('bse',WINDOW.end)
        class Response(BytesIO):
            status=200
            headers=Message();headers['Content-Type']='text/html;charset=utf-8'
            def geturl(self):return item.url
        class Cancel:
            def __init__(self):self.waits=[]
            def wait(self,value):self.waits.append(value);return False
            def is_set(self):return False
        cancel=Cancel()
        with patch.object(fetch,'build_opener') as opener:
            opener.return_value.open.return_value=Response(item.content)
            got=fetch.fetch('bse-a-json',[WINDOW.end],self.rt.options,cancel)
            self.assertEqual(got.content,item.content);self.assertEqual(cancel.waits,[60]);self.assertEqual(opener.return_value.open.call_count,1)
        event=Event();event.set()
        with patch.object(fetch,'build_opener') as opener,self.assertRaisesRegex(ActivityError,'activity_cancelled'):
            fetch.fetch('bse-a-json',[WINDOW.end],self.rt.options,event)
        opener.assert_not_called()

    def test_periodic_dedup_daily_next_day_and_failure_keeps_three(self):
        with patch.object(fetch,'fetch',self.obtain):
            for sid in (TWO_MARKET,MARKET):self.publish(sid,request='seed-'+sid)
        initialize(self.price,self.act)
        data=MarketData(self.price,{},activity_options=ActivityOptions(self.act,write_series=(MARKET,TWO_MARKET),startup_series=(MARKET,TWO_MARKET)),periodic_options=PeriodicOptions())
        self.addCleanup(data.close_updates)
        clock=Clock('2026-11-06T07:00:00');data._periodic.budget.clock=clock;data._activity_runtime.clock=clock
        with patch.object(fetch,'fetch',self.obtain):data.periodic_check((),'c','i')
        status=data.periodic_status();self.assertIsNone(status['reason'],status)
        self.assertEqual(status['daily'],{'requests':3,'bytes':3*65536})
        self.assertEqual(status['market_anchors'],{'sse_szse_bse':'2026-11-06','sse_szse':'2026-11-06'})
        with patch.object(fetch,'fetch',side_effect=AssertionError('重复不请求')):data.periodic_check((),'c','i')
        clock.set('2026-11-07T07:00:00')
        def fail_bse(key,*args,**kwargs):
            if key=='bse-a-json':raise ActivityError('source_fetch_failed')
            return self.obtain(key,*args,**kwargs)
        with patch.object(fetch,'fetch',fail_bse):data.periodic_check((),'c','i')
        status=data.periodic_status();self.assertEqual(status['market_anchors'],{'sse_szse_bse':'2026-11-06','sse_szse':'2026-11-07'})
        self.assertEqual(status['reason'],'periodic_update_failed')
