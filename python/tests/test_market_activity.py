"""B量额：隔离合成原件、实际文件发布与真实ASGI调用；不连接任何真实行情。"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, Inexact, localcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmi.api import create_app
from pmi.http_contract import response_value
from pmi.service_config import ServiceConfig
from pmi.market_data import index_series_store as price_store
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_series_contract import Original as PriceOriginal, build_manifest
from pmi.market_data.writer_lock import writer_lock
from pmi.market_data.activity import model, facts, sources, calculations, runtime, fetch
from pmi.market_data.activity.model import ActivityError, Options, Original, canonical, digest
from pmi.market_data.activity.store import Store
from pmi.market_data.activity.fetch import reserve
from http_test_support import ReadClient, disk
from test_index_series_contract import originals, WINDOW
from test_index_series_runtime import state

SID = 'sse:000001:price'
INDEX = get_index(SID)


def synthetic():
    items = list(originals(INDEX, WINDOW))
    raw = json.loads(items[0].content)
    for row in raw['data']:
        row.update(tradingVol=1000, tradingValue=1.23)
    old = items[0]
    items[0] = PriceOriginal(old.source, json.dumps(raw, ensure_ascii=False).encode(), old.started_at, old.completed_at, old.url)
    return tuple(items)


@contextmanager
def admitted():
    """只在本测试进程临时替换来源准入结论，不存在生产配置开关。"""
    original = model.rule
    with ExitStack() as stack:
        for module in ('model', 'facts', 'sources', 'runtime', 'fetch'):
            stack.enter_context(patch(f'pmi.market_data.activity.{module}.rule', side_effect=lambda s, version=None: replace(original(s, version), admitted=True, amount_unit='元' if s=='bse' else original(s, version).amount_unit, amount_quantum='0.01')))
        yield


class Client(ReadClient):
    def __init__(self, price, activity, **options):
        self.config = ServiceConfig(price, 18080, ('http://127.0.0.1:18081',),
                                    activity_options=Options(activity, **options))
        self.app = create_app(self.config)
        self.headers = {'host': self.config.authority, 'origin': self.config.allowed_origins[0], 'x-wolf-client': '1',
                        'x-wolf-expected-instance': self.app.state.boundary.instance,
                        'x-wolf-expected-config': self.config.activity_config_id,
                        'content-type': 'application/json', 'x-wolf-request-id': 'activity-test'}

    def update(self, price_id, expected=None, request='activity-test', **kwargs):
        return self.request(f'/api/market-activity/{SID}/update', 'POST',
                            body=canonical({'price_snapshot_id': price_id, 'expected_activity_id': expected}),
                            headers={'x-wolf-request-id': request, **kwargs})


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='thewolf-b-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.price, self.activity = self.base/'price', self.base/'activity'
        self.price.mkdir();self.activity.mkdir()

    def client(self, **kwargs):
        client = Client(self.price, self.activity, **kwargs)
        self.addCleanup(client.app.state.updates.close)
        return client

    def price_fixture(self):
        items = synthetic()
        with writer_lock(self.price):
            price_store.prepare_directories(self.price, INDEX)
            price_store.publish(self.price, INDEX, WINDOW, build_manifest(INDEX, WINDOW, items), items, state(INDEX))
        return price_store.read_snapshot(self.price, INDEX)

    def test_admission_does_not_enable_three_market_writes(self):
        client = self.client(write_series=(SID,))
        before = disk(self.base)
        ready = client.request('/api/market-activity/session')
        self.assertEqual(ready.status, 200, ready.body)
        self.assertEqual([s['series'] for s in ready.json()['policy']['sources'] if s['admitted']], [*model.INDEX_IDS, *model.THREE_SOURCE_KEYS])
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('no network')):
            result = client.request('/api/market-activity/cn-a-turnover/update', 'POST',
                                    body=canonical({'anchor_date': '2026-10-30', 'expected_activity_id': None}))
            self.assertEqual(result.status, 403, result.body)
            self.assertEqual(result.json()['detail']['code'], 'index_update_disabled')
            self.assertEqual(client.request(f'/api/market-activity/{SID}?price_snapshot_id='+ 'a'*64).status,404)
        self.assertEqual(disk(self.base),before)

    def test_wrong_config_instance_body_permission_no_side_effect(self):
        client=self.client(write_series=(SID,));before=disk(self.base)
        for headers in [{'x-wolf-expected-config':client.config.index_config_id}, {'x-wolf-expected-instance':'00000000-0000-4000-8000-000000000000'}]:
            self.assertEqual(client.update('a'*64,**headers).status,409)
        for body in [b'{}',b'{"anchor_date":"2026-10-30","expected_activity_id":null}', b'{"price_snapshot_id":"'+b'a'*64+b'","price_snapshot_id":"'+b'a'*64+b'","expected_activity_id":null}', b' '*4097]:
            self.assertEqual(client.request(f'/api/market-activity/{SID}/update','POST',body=body).status,422)
        other=self.client();self.assertEqual(other.update('a'*64).status,403)
        self.assertEqual(disk(self.base),before)

    def test_identity_changes_do_not_change_v1_v2(self):
        one=self.client();otherroot=self.base/'other';otherroot.mkdir()
        two=Client(self.price,otherroot,write_series=(SID,))
        self.addCleanup(two.app.state.updates.close)
        self.assertNotEqual(one.config.activity_config_id,two.config.activity_config_id)
        self.assertEqual(one.config.config_id,two.config.config_id)
        self.assertEqual(one.config.index_config_id,two.config.index_config_id)
        with self.assertRaises(ValueError):Client(self.price,self.price)

    def test_actual_publish_replay_calculate_and_read_only(self):
        price=self.price_fixture()
        with admitted():
            client=self.client(write_series=(SID,));before_price=disk(self.price)
            result=client.update(price['snapshot_id']);self.assertEqual(result.status,200,result.body)
            self.assertEqual(result.json()['state'],'completed',result.body)
            aid=result.json()['activity_id'];base=f'/api/market-activity/{SID}/snapshots/{aid}'
            fixed=client.request(base);self.assertEqual(fixed.status,200,fixed.body)
            snap=fixed.json();self.assertEqual(snap['rows'][0]['amount']['value'],'123000000.00')
            self.assertEqual(snap['rows'][0]['volume']['value'],'1000')
            self.assertEqual(snap['source_revision_relation'],'unknown')
            self.assertEqual(snap['binding']['relation'],'same_source_object')
            before=disk(self.base)
            computed=client.request(base+'/calculations?formula_version='+calculations.FORMULA)
            self.assertEqual(computed.status,200,computed.body[:1000])
            volume=computed.json()['series'][0];self.assertEqual(volume['rows'][-1]['ma'][0]['value'],'1000.0000')
            self.assertEqual(volume['rows'][-1]['change_pct']['value'],'0.00')
            self.assertEqual(client.request(base+'/evidence/'+snap['sources'][0]['object_id']).status,200)
            self.assertEqual(client.request(base+'/evidence/'+'a'*64).status,404)
            self.assertEqual(disk(self.base),before);self.assertEqual(disk(self.price),before_price)
            self.assertEqual(client.update(price['snapshot_id']).json(),result.json())
            self.assertEqual(client.update(price['snapshot_id'],aid).status,409)

    def test_changed_price_is_rejected_not_rounded_or_nullified(self):
        price=self.price_fixture();item=synthetic()[0];raw=json.loads(item.content)
        raw['data'][0]['close']=str(Decimal(str(raw['data'][0]['close']))+Decimal('0.00001'))
        original=Original('csindex',json.dumps(raw).encode(),item.url,item.started_at,item.completed_at)
        with admitted(),self.assertRaisesRegex(ActivityError,'price_values_mismatch'):
            facts.index_manifest(SID,price,original)
        raw['data'][0]['close']=json.loads(item.content)['data'][0]['close'];raw['data'][0]['tradingValue']=2.00
        candidate=Original('csindex',json.dumps(raw).encode(),item.url,item.started_at,item.completed_at)
        with admitted():
            result=facts.index_manifest(SID,price,candidate)
        self.assertEqual(result['binding']['relation'],'different_source_objects')
        self.assertEqual(result['source_revision_relation'],'unknown')
        self.assertEqual(result['rows'][0]['amount']['value'],'200000000.00')

    def test_precision_null_zero_negative_and_no_admission(self):
        item=Original('csindex',b'{}','', '', '')
        self.assertIsNone(facts.fact('sse','amount','1.23',item,'x')['value'])
        with admitted():
            self.assertEqual(facts.fact(SID,'amount','0',item,'x')['value'],'0.00')
            self.assertIsNone(facts.fact(SID,'amount',None,item,'x')['value'])
            for value in ['-1','NaN','1.001']:
                with self.assertRaises(ActivityError):facts.fact(SID,'amount',value,item,'x')
            with self.assertRaises(ActivityError):facts.fact(SID,'volume','1.5',item,'x')

    def test_missing_comparison_evidence_rejects_candidate(self):
        price = self.price_fixture(); item = synthetic()[0]
        raw = json.loads(item.content); raw['data'][0]['high'] = None
        with admitted(), self.assertRaisesRegex(ActivityError, 'price_binding_unverifiable'):
            facts.index_manifest(SID, price, Original('csindex', json.dumps(raw).encode(), item.url, '', ''))

    def test_cancellation_before_publish_preserves_pointer(self):
        price = self.price_fixture()
        with admitted():
            client = self.client(write_series=(SID,)); rt = client.config.market_data._activity_runtime
            rt.cancel.set()
            result = client.update(price['snapshot_id']).json()
            self.assertEqual(result['reason'], 'activity_cancelled')
            self.assertIsNone(rt.current(SID, price['snapshot_id']))
            self.assertFalse((self.activity / 'snapshots').exists())

    def test_market_raw_parts_replay_without_partial_total(self):
        from pmi.market_data.activity.sources import market_url
        with admitted():
            raw = canonical({'result': [{'TRADE_DATE': WINDOW.dates[0].replace('-', ''), 'PRODUCT_CODE': code, 'TRADE_AMT': value}
                                        for code, value in [('01', '1.23'), ('03', '2.34')]]})
            original = Original('sse', raw, market_url('sse', WINDOW.dates[0]), '', '')
            manifest = facts.market_from_originals(WINDOW, [original])
            store = Store(self.activity)
            operation = {'series_id': model.MARKET, 'request_id': 'market-parts', 'config_id': 'a'*64,
                         'instance_id': 'test', 'target': WINDOW.anchor_date, 'signature': 'b'*64,
                         'state': 'preparing', 'activity_id': None, 'reason': None, 'recovered_from_instance': None, 'observation_id': None}
            with store.lock(write=True):
                store.write(('operations', operation['request_id']+'.json'), canonical(operation))
                observation = {'series_id': model.MARKET, 'sources': [{**manifest['sources'][0], 'started_at': '2026-10-30T00:00:00+00:00', 'completed_at': '2026-10-30T00:00:01+00:00', 'published_at': None}]}
                aid = store.publish(manifest, {original.object_id: raw}, None, operation, observation)
                store.write(('operations', operation['request_id']+'.json'), canonical(store.current(model.MARKET, WINDOW.anchor_date)['operation']))
            client = self.client(); before = disk(self.base)
            route = f'/api/market-activity/{model.MARKET}/snapshots/{aid}'
            response = client.request(route)
            self.assertEqual(response.status, 200, response.body)
            self.assertEqual([f['value'] for f in response.json()['rows'][0]['components']['sse']], ['123000000.00', '234000000.00'])
            calculated = client.request(route + '/calculations?formula_version=' + calculations.FORMULA)
            self.assertEqual(calculated.status, 200, calculated.body[:500])
            self.assertIsNone(calculated.json()['series'][0]['rows'][0]['total']['value'])
            self.assertEqual(disk(self.base), before)
            pointer = store.current(model.MARKET, WINDOW.anchor_date)
            pointer['target'] = '2026-10-31'
            with store.lock(write=True):
                store.write(store.location(model.MARKET, WINDOW.anchor_date), canonical(pointer))
            before = disk(self.base)
            mismatch = client.request('/api/market-activity/cn-a-turnover?anchor_date=2026-10-31')
            self.assertEqual(mismatch.status, 409, mismatch.body)
            self.assertEqual(disk(self.base), before)

    def test_current_cross_price_pointer_rejected_and_old_fixed_retained(self):
        price = self.price_fixture()
        with admitted():
            client = self.client(write_series=(SID,)); result = client.update(price['snapshot_id']).json()
            rt = client.config.market_data._activity_runtime
            pointer = rt.store.current(SID, price['snapshot_id']); pointer['target'] = 'a'*64
            with rt.store.lock(write=True):
                rt.store.write(rt.store.location(SID, 'a'*64), canonical(pointer))
            before = disk(self.base)
            response = client.request(f'/api/market-activity/{SID}?price_snapshot_id='+ 'a'*64)
            self.assertEqual(response.status, 409, response.body)
            self.assertEqual(client.request(f'/api/market-activity/{SID}/snapshots/'+result['activity_id']).status, 200)
            self.assertEqual(disk(self.base), before)

    def test_repeat_observation_keeps_v_and_old_v_survives_current_advance(self):
        price = self.price_fixture()
        with admitted():
            client = self.client(write_series=(SID,)); first = client.update(price['snapshot_id']).json()
            rt = client.config.market_data._activity_runtime
            original = rt._obtain(SID, price)
            repeated = replace(original, started_at='2026-10-30T01:00:00+00:00', completed_at='2026-10-30T01:00:01+00:00')
            with patch.object(rt, '_obtain', return_value=repeated):
                second = client.update(price['snapshot_id'], first['activity_id'], request='repeat').json()
            self.assertEqual(second['activity_id'], first['activity_id'])
            self.assertNotEqual(second['observation_id'], first['observation_id'])
            raw = json.loads(original.content); raw['data'][0]['tradingValue'] = '2.34'
            revised = replace(repeated, content=canonical(raw))
            with patch.object(rt, '_obtain', return_value=revised):
                third = client.update(price['snapshot_id'], second['activity_id'], request='revision').json()
            self.assertNotEqual(third['activity_id'], first['activity_id'])
            before = disk(self.base)
            old = client.request(f'/api/market-activity/{SID}/snapshots/'+first['activity_id']).json()
            self.assertEqual([x['observation_id'] for x in old['observations']], [first['observation_id'], second['observation_id']])
            self.assertEqual(old['observations'][1]['sources'][0]['started_at'], repeated.started_at)
            self.assertTrue(all(x['activity_id'] == first['activity_id'] for x in old['observations']))
            self.assertEqual(client.request('/api/market-activity/operations/repeat?series_id='+SID).json()['observation_id'], second['observation_id'])
            self.assertEqual(disk(self.base), before)

    def test_missing_corrupt_and_misbound_observation_refuses_all_reads(self):
        price = self.price_fixture()
        with admitted():
            client = self.client(write_series=(SID,)); operation = client.update(price['snapshot_id']).json()
            aid, oid = operation['activity_id'], operation['observation_id']
            rt = client.config.market_data._activity_runtime
            manifest = rt.store.fixed(aid); original_id = manifest['sources'][0]['object_id']
            observation_path = self.activity/'observations'/(oid+'.json'); content = observation_path.read_bytes()
            routes = [f'/api/market-activity/{SID}?price_snapshot_id='+price['snapshot_id'],
                      f'/api/market-activity/{SID}/snapshots/{aid}',
                      f'/api/market-activity/{SID}/snapshots/{aid}/calculations?formula_version='+calculations.FORMULA,
                      f'/api/market-activity/{SID}/snapshots/{aid}/evidence/'+original_id,
                      '/api/market-activity/operations/activity-test?series_id='+SID]
            for invalid in (None, content+b' ', canonical({**json.loads(content), 'activity_id': 'a'*64})):
                if invalid is None:
                    observation_path.unlink()
                else:
                    observation_path.write_bytes(invalid)
                before = disk(self.base)
                for route in routes:
                    response = client.request(route)
                    self.assertEqual(response.status, 409, (route, response.body))
                self.assertEqual(disk(self.base), before)
                observation_path.write_bytes(content)
            # 即便把错误回执重新算摘要并更新全部引用，归属交叉检查仍不能绕过。
            wrong = {**json.loads(content), 'activity_id': 'a'*64}; bad_id = digest(wrong)
            (self.activity/'observations'/(bad_id+'.json')).write_bytes(canonical(wrong))
            for path in [self.activity/'observation-refs'/(aid+'.json'), self.activity/'operations/activity-test.json',
                         rt.store.path(*rt.store.location(SID, price['snapshot_id']))]:
                path.write_text(path.read_text().replace(oid, bad_id))
            before = disk(self.base)
            for route in routes:
                self.assertEqual(client.request(route).status, 409)
            self.assertEqual(disk(self.base), before)

    def test_precommit_observation_is_not_published_or_recovered_as_success(self):
        price = self.price_fixture()
        with admitted():
            client = self.client(write_series=(SID,)); first = client.update(price['snapshot_id']).json()
            rt = client.config.market_data._activity_runtime; write = rt.store.write
            def fail_before_pointer(parts, content, **kwargs):
                if 'current-by-price' in parts:
                    raise OSError('synthetic failure before commit')
                return write(parts, content, **kwargs)
            with patch.object(rt.store, 'write', side_effect=fail_before_pointer):
                self.assertEqual(client.update(price['snapshot_id'], first['activity_id'], request='precommit').status, 409)
            before = disk(self.base)
            fixed = client.request(f'/api/market-activity/{SID}/snapshots/'+first['activity_id']).json()
            self.assertEqual(len(fixed['observations']), 1)
            self.assertEqual(disk(self.base), before)
            self.assertEqual(client.update(price['snapshot_id'], first['activity_id'], request='precommit').json()['state'], 'interrupted')
            self.assertEqual(rt.current(SID, price['snapshot_id'])['activity_id'], first['activity_id'])

    def test_missing_day_propagates_and_incomplete_period_marked(self):
        price=self.price_fixture();item=synthetic()[0];raw=json.loads(item.content);raw['data'].pop(-2)
        with admitted():
            snap=facts.index_manifest(SID,price,Original('csindex',json.dumps(raw).encode(),item.url,item.started_at,item.completed_at))
        snap['activity_id']=digest(snap);before=deepcopy(snap)
        value=calculations.calculate(snap,calculations.FORMULA)
        daily=value['series'][0]['rows'];self.assertIsNone(daily[-1]['change_pct']['value'])
        self.assertIsNone(daily[-1]['ma'][0]['value']);self.assertEqual(snap,before)
        weekly=value['series'][1]['rows'];self.assertFalse(weekly[-1]['total']['complete'])
        self.assertIn('period_in_progress',weekly[-1]['total']['incomplete_reasons'])

    def test_withdrawal_blocks_fixed_values_but_retains_evidence(self):
        price=self.price_fixture()
        with admitted():
            client=self.client(write_series=(SID,));op=client.update(price['snapshot_id']).json();aid=op['activity_id']
            snap=client.request(f'/api/market-activity/{SID}/snapshots/{aid}').json();oid=snap['sources'][0]['object_id']
            evidence = b'synthetic official withdrawal evidence'
            evidence_id = hashlib.sha256(evidence).hexdigest()
            evidence_store = Store(self.activity)
            with evidence_store.lock(write=True):
                evidence_store.write(('objects', evidence_id), evidence, immutable=True)
            blocked=self.client(write_series=(SID,),blocked_series=((SID,evidence_id),));before=disk(self.base)
            base=f'/api/market-activity/{SID}/snapshots/{aid}'
            for route in [base,base+'/calculations?formula_version='+calculations.FORMULA]:
                result=blocked.request(route);self.assertEqual(result.status,409);self.assertEqual(result.json()['detail']['code'],'source_withdrawn')
            self.assertEqual(blocked.request(base+'/evidence/'+oid).status,200)
            self.assertEqual(disk(self.base),before)

    def test_pointer_commit_recovers_operation_without_refetch(self):
        price=self.price_fixture()
        with admitted():
            client=self.client(write_series=(SID,));runtime=client.config.market_data._activity_runtime;write=runtime.store.write
            def interrupted(parts,content,**kw):
                if parts[0]=='operations' and json.loads(content).get('state')=='completed':raise OSError('synthetic post-commit crash')
                return write(parts,content,**kw)
            with patch.object(runtime.store,'write',side_effect=interrupted):
                result=client.update(price['snapshot_id']);self.assertEqual(result.status,409)
            before=disk(self.base)
            status=client.request('/api/market-activity/operations/activity-test?series_id='+SID)
            self.assertEqual(status.json()['state'],'completed');self.assertEqual(disk(self.base),before)
            with patch.object(runtime,'_obtain',side_effect=AssertionError('must not fetch')):
                self.assertEqual(client.update(price['snapshot_id']).json()['state'],'completed')

    def test_budget_persists_across_root_change_and_never_refunds(self):
        ledger=self.base/'budget.json';ledger.write_bytes(canonical({'cycle':'test','attempts':0,'bytes':0,'limit_attempts':1,'limit_bytes':model.MAX_BYTES}))
        options=Options(self.activity,max_attempts=5,max_bytes=model.MAX_BYTES*5,budget_cycle='test',budget_ledger=ledger)
        reserve(options)
        another=self.base/'another';another.mkdir()
        with self.assertRaisesRegex(ActivityError,'activity_budget_exhausted'):reserve(replace(options,root=another))
        self.assertEqual(json.loads(ledger.read_bytes())['attempts'],1)
        replacement = self.base/'replacement.json'; replacement.write_bytes(ledger.read_bytes()); replacement.replace(ledger)
        with self.assertRaisesRegex(ActivityError,'activity_budget_invalid'):reserve(options)

    def test_symlink_object_and_nonmember_rejected(self):
        store=Store(self.activity);outside=self.base/'outside';outside.write_text('preserve')
        (self.activity/'objects').symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(ValueError):store.original('a'*64)
        self.assertEqual(outside.read_text(),'preserve')

    def test_market_sum_scope_zero_and_window_average(self):
        from pmi.market_data.index_history_calendar import CALENDAR_VERSION
        days=['2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23','2026-10-26']
        original=Original('synthetic',b'{}','', '', '')
        with admitted():
            comps={m:{d:[facts.fact(m,'amount','1.00' if m=='sse' else '2.01',original,'synthetic')] for d in days} for m in model.MARKETS}
            snap=facts.market_manifest('2026-10-27',{'start':days[0],'end':days[-1]},CALENDAR_VERSION,{m:days for m in model.MARKETS},comps)
        snap['activity_id']=digest(snap)
        value=calculations.calculate(snap,calculations.FORMULA)
        self.assertEqual(len(value['series']),1)
        self.assertEqual(value['series'][0]['rows'][-1]['total']['value'],'100000004.02')
        self.assertEqual(value['comparisons']['day_5']['baseline']['value'],'100000004.0200')
        self.assertEqual(value['comparisons']['day_5']['comparison']['value'],'0.00')
        snap['rows'][-2]['components']['bse'][0]['value']=None;snap['rows'][-2]['components']['bse'][0]['reason']='source_missing'
        value=calculations.calculate(snap,calculations.FORMULA)
        self.assertIsNone(value['series'][0]['rows'][-2]['total']['value'])
        self.assertIsNone(value['comparisons']['day_5']['comparison']['value'])
        self.assertIsNone(value['series'][0]['rows'][-1]['change_pct']['value'])

    def test_degradation_and_cas_preserve_previous_pointer(self):
        price=self.price_fixture()
        with admitted():
            client=self.client(write_series=(SID,));first=client.update(price['snapshot_id']).json()
            rt=client.config.market_data._activity_runtime;before=disk(self.activity)
            self.assertEqual(client.update(price['snapshot_id'],None,request='wrong-cas').status,409)
            self.assertEqual(disk(self.activity),before)
            original=rt._obtain(SID,price);raw=json.loads(original.content);raw['data'][0]['tradingVol']=None
            bad=replace(original,content=json.dumps(raw).encode())
            with patch.object(rt,'_obtain',return_value=bad):
                result=client.update(price['snapshot_id'],first['activity_id'],request='missing-value').json()
            self.assertEqual(result['state'],'failed');self.assertEqual(result['reason'],'activity_degradation_rejected')
            self.assertEqual(rt.current(SID,price['snapshot_id'])['activity_id'],first['activity_id'])

    def test_explicit_restart_recovers_ownership_without_network(self):
        price=self.price_fixture()
        with admitted():
            first=self.client(write_series=(SID,));op=first.update(price['snapshot_id']).json()
            second=self.client(write_series=(SID,));rt=second.config.market_data._activity_runtime
            self.assertEqual(second.request('/api/market-activity/operations/activity-test?series_id='+SID).json()['detail']['code'],'activity_recovery_required')
            with patch.object(rt,'_obtain',side_effect=AssertionError('no refetch')):
                recovered=second.update(price['snapshot_id']).json()
            self.assertEqual(recovered['activity_id'],op['activity_id']);self.assertEqual(recovered['recovered_from_instance'],op['instance_id'])

    def test_unknown_calendar_and_rounding_context_do_not_invent_values(self):
        price=self.price_fixture();item=synthetic()[0]
        with admitted():snap=facts.index_manifest(SID,price,Original('csindex',item.content,item.url,item.started_at,item.completed_at))
        snap['activity_id']=digest(snap)
        expected=calculations.calculate(snap,calculations.FORMULA)
        with localcontext() as ctx:
            ctx.prec=3;ctx.traps[Inexact]=True
            self.assertEqual(calculations.calculate(snap,calculations.FORMULA),expected)
        with self.assertRaisesRegex(ActivityError,'calculation_parameters_invalid'):calculations.calculate(snap,'future')

    def test_zip_bomb_external_xml_and_formula_rejected(self):
        from io import BytesIO
        import zipfile
        for content in [b'<!DOCTYPE x><x/>',b'<root><f>1+1</f></root>',b'<root><Relationship TargetMode="External"/></root>']:
            buffer=BytesIO()
            with zipfile.ZipFile(buffer,'w') as z:z.writestr('sheet.xml',content)
            with self.assertRaises(ActivityError):sources.inspect_szse_xlsx(buffer.getvalue())

    def test_retained_financial_contracts_match_accepted_baseline(self):
        current=json.loads((Path(__file__).resolve().parents[2]/"contracts/openapi.yaml").read_bytes())["components"]["schemas"]
        expected={'IndexSeriesId': '748022b1caacf04039da02fdf3aebb02e3538423d496911a2dc8c8b11d41bc4b', 'IndexSeriesSource': 'c6ef5676a2ae472fd7936caed750cb65e6879613d8d2e4471ec2f6e912ad7a07', 'IndexSeriesSourcePolicy': '92f1fceff3d6d92ef0ed5682982df05aaa247bd7de78907b49c8e07e4f172c43', 'IndexSeriesPoint': '6c56d062a8105620e855ba3709249edb882600e27135aab36a25a85773234090', 'IndexSeriesRawPoint': 'cd6f7aa11327b34de3366ce7b373c51373f4d5c7ef7596d7f8f84345689f01c1', 'IndexSeriesRawPriceFields': 'a5a38749e9bb3bd98111e4b34d301dc1796ef009d7d3f6b839d1f0470632f5df', 'IndexSeriesComparisonFields': '063281b082f04f4d825bb3f7405fd2b57030d9a1ac0aeb51bcc84e12971465ca', 'IndexSeriesField': 'bac74eac7958d22542f9b2a35b7caf2658e05ad07ecf049f5f5a72b8a1ba9a7c', 'IndexSeriesNetworkPolicy': '8337e8f0b66cdd0caf724fce054860334e5f48f421375b6e1be06ed60825bc9f', 'IndexSeriesPolicy': 'f1604bbd763e18e57bd5f62e5699eb5739404ce15b76c140c9faaba7020b1f2e', 'IndexSeriesReady': 'd9f7f946ec5a0330b83253ba0361af06db88b3b5c1176a0d0e3b07ef5008a39a', 'IndexSeriesCatalogEntry': 'def44e8ed3479349ace567f4fa5846cffaba9da84765e4abdeee29b165290414', 'IndexSeriesCatalog': '2c7b006665d18c12a6fba5858feda8b880ba201122635f61a4f1db048213626c', 'IndexSeriesInstrument': '2ea1060c4f88130bee80aa16dd665519c35c625f003a2a3bd1bc0198cce04d21', 'IndexSeriesWindow': 'b89fa676b222512f9c0d51f4f9b335c5db02a7a0ec7be755e33a83f81bc366d7', 'IndexSeriesCalendarSource': '1611858990f74080752185c46242a034240ee7823f0c36a3a3b2fe8d42a47072', 'IndexSeriesCompletionBasis': 'e2060339af456485bdb907fefb7608df7a933e75ca98c0d13996fd122044232c', 'IndexSeriesVerification': '1eafb036e5cd570fdea508acf29d8b324adb1ab77fcae1ea2b287a68d645e646', 'IndexSeriesEvidenceRef': 'a6b312644fb1148a9efdf3552fedd26f0f3dd69fdc0f190cbe1f304c580b629f', 'IndexSeriesBar': 'f0246e77bec34a9dfc9f2b6f92f8c8ee42633ef9f98555fa116c1e3b858233e7', 'IndexSeriesSourceRow': 'e34f4e8be3828acca458245520cb55521c35b14bc8dcb320ae6fa7428c26a5c0', 'IndexSeriesEvidence': '39f6f1f763d5ce5e44ff88149be3d995f87f0755c7bd8809905a433985493411', 'IndexSeriesSummaryInput': 'ba3ea7e2b3e94f7066afcf9c073764b5aff80fa0ab3e1a5ef5f9d48303af8b35', 'IndexSeriesSummary': '6225488aefebdf871989dd793205d33bc7a927439f234931d5038d8ab130e535', 'IndexSeriesRetrievalSource': '7c520816cfde595a69da297f3bb85f440cca948cc767e20a2e97f33eee947375', 'IndexSeriesRetrieval': '7f4839f9ac4f97d52e0b1b90b5dbb9f4977a33f9e5ab0d0ce681f176c9aeb631', 'IndexSeriesSnapshot': '2d5b7a8a2060aaf2b679a70dfec09d4527e8c6f28712e2cbcbbdfa81e33de883', 'IndexSeriesEvidenceDetail': 'cf715aadc8b880525a29859fa08ce96ea29fdb2d3fa64fa9df6db9f7c991ac0f', 'IndexSeriesEvidenceView': 'f9ea325505248a8a1aa9bd3f14ab1bc56289578cc43b604c3308e6afb992d90f', 'IndexSeriesRangeRow': '4218816e53d5ed2ed117873135d9499e5744d2577d5488f87fc8f08d29a50bc4', 'IndexSeriesRange': 'cf605dfe5495f34ee2a7a532a3267bdb1daf2d637252a07c3853be656b39c9ef', 'IndexSeriesDifference': '03faa248d48fb9eaf2d05b52c91ab657fb17ae3ec6e85217bd92b798ea7b04c2', 'IndexSeriesUpdateStatus': 'a87d06faf27683cf0c5261b47db7372ede0e9898c7ccd64d5fd316e992c8f410', 'IndexSeriesError': 'e600527e7b09db20011ed1d31995a28befd81ef19acd0cfc964f00cc2214206b', 'IndexSeriesRecordedRejection': 'e3e2473a47df26f4c4c5099a6934f3f57b4fd9db83bf1b17e2fac7819d74079e', 'IndexSeriesOperationKind': '4b37f7c29633327a2fd6b12cbc2dbd0e7dbd82863658a88d7757e4c362723f05', 'IndexSeriesAcceptedOperation': '297cf8c601768d259c8c7dbd054a091bf217c1cf03d5a915ea8ddbb225128abb', 'IndexSeriesOperationResult': '719d9003cc55c9e18edb9af665fc66ef23e1264d3dcdd6c5598ad2b46227287d', 'IndexSeriesCalculationInput': '45b75eb36e8f74d124a5d3e9e58ca66a07fbf001617c29fd7cb02b71d8a09184', 'IndexSeriesCalculationParameters': '57dd77d9aa25ef7cf4b34d49ca4b7266f76c7e481dcf68abe3baa019636c351a', 'IndexSeriesCalculationScalar': 'dd6b1a22ab18193e122e09726f3cb068c2fb0f0c09de47d17246d5ba568aa153', 'IndexSeriesCalculationBar': '048e1a437f7f95408d97186cfc713a56a43c54560182fa7b211e6ba3495b128f', 'IndexSeriesCalculationAvailability': 'a68191ca9743c97b5c75dbb27f747f388e02ee508526fe1d5b32145a3d3a2e7c', 'IndexSeriesCalculationSeries': '3f28f1955e32c74ee14b56dabd7f27deba0f4dea90c5e90d127d5b58f351c041', 'IndexSeriesCalculations': '270b87f801633996a41d1cb8a4402dda6651104563518ef49c398f94c19cb723', 'IndexSeriesCalculationError': 'dbecbd09ab88f5dee7e17b17dcf7f600e2d05eecf51e50100f5a7746cacd7778', 'MarketActivityPolicy': '89e640a630157f1bf4fe603f052d2f2ddd96c96c99cac5ccea7d0d9a57e50038', 'MarketActivitySeriesId': 'da22a05a175d43245ef2a8f0adadceb8dd876b8788229339aaf6cd233d265507', 'MarketActivityFact': '882736d8f5c11f02fd2e20c56ce8c743c70dedf7eb0c4c197cb0ecd9e450c759', 'MarketActivitySnapshot': 'a49e3647f8228867bd8b47b363d7f3393bef4b828845f16cdcd656eec6348e11', 'MarketActivityCurrent': 'd82bc92145a1a49c29a6f5eaf2cf4dbc9aad7d98e84be3bb1b70a011c1d3eeea', 'MarketActivityScalar': '79dbac29899123dc019509a57c83e08c8246064d16c4fc0f16656a357f5b8306', 'MarketActivityCalculations': '0bd9f497bfc130bdc49e876a9f7528219d1a69cb773d3f7a0b6ea72ed3148017', 'MarketActivityEvidence': '241cfbf17cf07d6ca231fabec4c4bfcae630cc656c93adae084f85730f28bdb0', 'MarketActivityOperation': 'fb79a6a9c0ead06d09b31e44bdca477890ddc665018751fe0da3dc211d1f8dac', 'MarketActivityUpdateBody': 'cfe32b3b598da1bbe130524991232b9a3860c122e8a94210d11c632162b74ba5', 'MarketActivityError': 'b319f2a9a0f4e0df4441c63ddee4c5caf73b70be711c35b2e47400ee7041e1d1', 'MarketActivityReady': '983f77ce236a6db9891b905afa6d3c237474961d8b45b0afa4d802f4cc0a84d8', 'MarketActivityIndexSnapshot': '70a63d1fb5cdc1e6162ff089b8fd685cdb41b1e217329d1a8100918539bb8ede', 'MarketActivityMarketSnapshot': 'bbba37ec1bdf6d082fd05466eefd50ae773652bf9b51c54a7ed22b6f869bb5a2', 'MarketActivityObservedSource': '29a426e2fdb5cad851baa045dee1c657b7ffd92b9955b0990e1e79f83a7b801c', 'MarketActivityObservation': '55044596ba72e227db29ef9556e1f94fa7552f3456d2d77d6392000402d571fd', 'MarketActivityTwoMarketSnapshot': '9df49971b4a3b6a84958c58d32075485aa912bdd09ba1b5e59b3b85792a34b5b', 'OverviewPeriodicPolicy': 'bbd55d1b56ada6e227e2039e9c92938921be3caa3f192bf78fc83aae4962968d', 'OverviewBudgetCounter': '6e7a6c2bf496754a7794d82cc6737fea36069916fc7c89d484b977bbea403687', 'OverviewUpdateStatus': 'fbecb0e0157e654006007a72e1f37210d8e2797ba2b930b1edaf9a79ba7bbceb', 'MarketActivityAnchors': 'c57e77c9351d788c8cf1cf3afd1d61d20bc17e1d2e8cd737992c9747c73bdde9'}
        for name, fingerprint in expected.items():
            self.assertEqual(hashlib.sha256(json.dumps(current[name],sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest(),fingerprint,name)


if __name__=='__main__':unittest.main()
