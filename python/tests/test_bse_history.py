"""真实操作辅助工具仅用隔离根、合成行情和固定研究档案核验。"""
from pathlib import Path
import sys
import json
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from bse_history import History
from test_three_market import ThreeMarketTests, ANCHOR, WINDOW, original
from pmi.market_data.activity import fetch
from sqlite_fixture import activity_budget_bytes, set_activity_budget
from pmi.market_data.storage import state as sql_state
from pmi.market_data.activity.model import ActivityError, MARKET, canonical


class HistoryTests(unittest.TestCase):
    setUp = ThreeMarketTests.setUp
    obtain = ThreeMarketTests.obtain
    # 只沿用隔离setUp，不重复执行父类已有产品测试。
    def test_stage_and_offline_commit_recovery(self):
        stage=self.root/'stage';stage.mkdir();h=History(self.rt,stage,ANCHOR)
        items=[original(m,d) for m in ('sse','szse','bse') for d in WINDOW.dates]
        plan=h.prepare(items[:-2]);self.assertEqual(plan['requests'],2)
        with patch.object(fetch,'fetch',side_effect=self.obtain) as call:
            self.assertEqual(h.collect()['requests'],0);self.assertEqual(call.call_count,2)
        h=History(self.rt,stage,ANCHOR)
        with patch.object(fetch,'fetch',side_effect=AssertionError('已取不重取')):
            self.assertEqual(h.collect()['requests'],0)
            pending={'request_id':'unrelated','state':'preparing','series_id':MARKET,'target':ANCHOR,'signature':'0'*64,'config_id':'other','instance_id':'other','activity_id':None,'reason':None,'observation_id':None,'recovered_from_instance':None}
            with self.rt.store.lock(write=True):self.rt.store.write(('operations','unrelated.json'),canonical(pending))
            with self.assertRaisesRegex(ActivityError,'history_existing_operation_unresolved'):h.publish('history-publish')
            self.assertEqual(self.rt.store.json('operations','unrelated.json'),pending)
            # 显式结束本测试未决操作；保留其历史，不删除业务记录。
            with self.rt.store.lock(write=True):
                self.rt.store.write(('operations','unrelated.json'),canonical({**pending,'state':'interrupted','reason':'activity_interrupted'}))
            result=h.publish('history-publish');self.assertEqual(result['state'],'completed')
            self.assertEqual(h.publish('history-publish'),result)
            (stage/'published.json').unlink() # 仅模拟自有合成暂存的提交后中断。
            self.assertEqual(h.publish('history-publish'),result)
        self.assertIsNotNone(self.rt.current(MARKET,ANCHOR))
        self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],2)

    def test_failure_no_implicit_retry_and_budget_no_reset(self):
        stage=self.root/'stage';stage.mkdir();h=History(self.rt,stage,ANCHOR);h.prepare()
        calls=[]
        def fail(key,dates,*args,**kwargs):
            calls.append(dates[0]);fetch.reserve(self.rt.options,65536)
            if len(calls)==2:raise ActivityError('source_fetch_failed')
            return original(key.split('-')[0],dates[0])
        with patch.object(fetch,'fetch',fail),self.assertRaisesRegex(ActivityError,'source_fetch_failed'):h.collect()
        with patch.object(fetch,'fetch',side_effect=AssertionError('失败不可隐式重试')):
            with self.assertRaisesRegex(ActivityError,'history_attempt_unresolved'):History(self.rt,stage,ANCHOR).collect()
            with self.assertRaisesRegex(ActivityError,'history_incomplete'):h.publish('history-incomplete')
        self.assertEqual(len(calls),2);self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],2)
        self.assertIsNone(self.rt.current(MARKET,ANCHOR))

    def test_stage_tamper_and_archived_evidence(self):
        stage=self.root/'stage';stage.mkdir();h=History(self.rt,stage,ANCHOR)
        repo=Path(__file__).resolve().parents[2]
        research=[original('bse',d) for d in ('2025-04-21','2026-10-29','2026-11-04')];self.assertEqual(len(research),3)
        plan=h.prepare(research);self.assertEqual(plan['requests'],2175)
        (stage/'raw'/research[0].object_id).write_bytes(b'changed')
        with patch.object(fetch,'fetch',side_effect=AssertionError('篡改不可联网')):
            with self.assertRaisesRegex(ActivityError,'history_stage_invalid'):h.collect()
        self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],0)



class HistoryPacingTests(unittest.TestCase):
    """仅隔离原件、真实账本与替身HTTP；等待由可控Event替身记录。"""
    setUp = ThreeMarketTests.setUp
    obtain = ThreeMarketTests.obtain

    def prepare(self, name, missing):
        stage=self.root/name;stage.mkdir();h=History(self.rt,stage,ANCHOR)
        items=[original(m,d) for m in ('sse','szse','bse') for d in WINDOW.dates]
        self.assertEqual(h.prepare(items[:-missing])['requests'],missing)
        return h,stage

    def test_twenty_then_resume_keeps_boundary_and_no_redownload(self):
        h,stage=self.prepare('pace',23);waits=[]
        def wait(seconds):waits.append(seconds);return seconds==20
        with patch.object(self.rt.cancel,'wait',wait),patch.object(fetch,'fetch',side_effect=self.obtain) as call:
            with self.assertRaisesRegex(ActivityError,'activity_cancelled'):h.collect(bse_batch_pacing=True)
            self.assertEqual(call.call_count,20)
            self.assertTrue(all(c.kwargs=={'history_batch_paced':True} for c in call.call_args_list))
        self.assertEqual(waits,[3]*19+[20])
        self.assertTrue(all(x['state']=='saved' for x in json.loads((stage/'attempts.json').read_bytes()).values()))
        self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],20)
        with patch.object(fetch,'fetch',side_effect=self.obtain) as call,patch.object(self.rt.cancel,'wait',side_effect=lambda s:waits.append(s) or False):
            self.assertEqual(History(self.rt,stage,ANCHOR).collect(bse_batch_pacing=True)['requests'],0)
            self.assertEqual(call.call_count,3)
        self.assertEqual(waits,[3]*19+[20,20,3,3])
        self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],23)
        with patch.object(fetch,'fetch',side_effect=AssertionError('不得重取')):
            self.assertEqual(h.collect(bse_batch_pacing=True)['requests'],0)

    def test_normal_fetch_delay_unchanged_and_history_parameter_scoped(self):
        from io import BytesIO
        from email.message import Message
        class Response(BytesIO):
            status=200
            def __init__(self,item):
                super().__init__(item.content);self.target=item.url;self.headers=Message();self.headers['Content-Type']='text/html'
            def geturl(self):return self.target
        item=original('bse',WINDOW.end)
        class Opener:
            def open(self,*a,**kw):return Response(item)
        with patch.object(fetch,'build_opener',return_value=Opener()),patch.object(self.rt.cancel,'wait',return_value=False) as wait:
            fetch.fetch('bse-a-json',[WINDOW.end],self.rt.options,self.rt.cancel)
            self.assertEqual(wait.call_args_list[-1].args,(60,))
            fetch.fetch('bse-a-json',[WINDOW.end],self.rt.options,self.rt.cancel,history_batch_paced=True)
            self.assertEqual(wait.call_args_list[-1].args,(0,))
            for key,kwargs in [('sse-a-json',{}),('bse-a-json',{'lease':object()})]:
                with self.assertRaisesRegex(ActivityError,'invalid_history_pacing'):
                    fetch.fetch(key,[WINDOW.end],self.rt.options,self.rt.cancel,history_batch_paced=True,**kwargs)
        self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],2)

    def test_first_twenty_verified_then_next_batch_automatically(self):
        h,stage=self.prepare('continue',21);waits=[]
        def wait(seconds):
            waits.append(seconds)
            if seconds==20:
                attempts=json.loads((stage/'attempts.json').read_bytes())
                self.assertEqual(len(attempts),20)
                self.assertTrue(all(x['state']=='saved' for x in attempts.values()))
            return False
        with patch.object(self.rt.cancel,'wait',wait),patch.object(fetch,'fetch',side_effect=self.obtain) as call:
            self.assertEqual(h.collect(bse_batch_pacing=True)['requests'],0)
            self.assertEqual(call.call_count,21)
        self.assertEqual(waits,[3]*19+[20])

    def test_http_or_validation_failure_stops_without_retry(self):
        from urllib.error import HTTPError
        from io import BytesIO
        from email.message import Message
        from dataclasses import replace
        cases=[HTTPError('https://www.bse.cn/',403,'blocked',None,None),
               HTTPError('https://www.bse.cn/',429,'limited',None,None),TimeoutError('synthetic'),
               ActivityError('source_redirect_rejected'),b'<html>captcha</html>',
               b'null([{"xxzrlx":"2","rq":"19990101","hqcjje":"1"}])']
        for n,failure in enumerate(cases):
            with self.subTest(case=n):
                h,stage=self.prepare('failure-'+str(n),2);calls=[]
                before=json.loads(activity_budget_bytes(self.act))['attempts']
                class Response(BytesIO):
                    status=200
                    def __init__(self,item):
                        super().__init__(item.content);self.target=item.url;self.headers=Message();self.headers['Content-Type']='text/html'
                    def geturl(self):return self.target
                class Opener:
                    def open(self,request,timeout):
                        raw=request.full_url.rsplit('=',1)[1];day=raw[:4]+'-'+raw[4:6]+'-'+raw[6:];calls.append(day)
                        item=original('bse',day)
                        if len(calls)==2:
                            if isinstance(failure,Exception):raise failure
                            item=replace(item,content=failure)
                        return Response(item)
                with patch.object(fetch,'build_opener',return_value=Opener()),patch.object(self.rt.cancel,'wait',return_value=False):
                    with self.assertRaises(ActivityError):h.collect(bse_batch_pacing=True)
                self.assertEqual(len(calls),2)
                self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],before+2)
                with patch.object(fetch,'fetch',side_effect=AssertionError('失败不得重试')):
                    with self.assertRaisesRegex(ActivityError,'history_attempt_unresolved'):History(self.rt,stage,ANCHOR).collect(bse_batch_pacing=True)
                self.assertIsNone(self.rt.current(MARKET,ANCHOR))

    def test_new_pacing_still_preflights_entire_remaining_batch(self):
        h,_=self.prepare('short-budget',2)
        ledger=json.loads(activity_budget_bytes(self.act));ledger['limit_attempts']=1;set_activity_budget(self.act, canonical(ledger))
        with patch.object(fetch,'fetch',side_effect=AssertionError('不足不得开始')):
            with self.assertRaisesRegex(ActivityError,'activity_budget_exhausted'):h.collect(bse_batch_pacing=True)
        self.assertEqual(json.loads(activity_budget_bytes(self.act))['attempts'],0)
