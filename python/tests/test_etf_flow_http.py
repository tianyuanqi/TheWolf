"""正式回环HTTP/生成契约与隔离金融用例联测；实际浏览器界面检查另行执行。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import uvicorn
from pmi.api import create_app
from pmi.http_contract import ContractResponseError, response_value, verify_resources
from pmi.service_config import ServiceConfig
import test_etf_flow_runtime as runtime_fixture


class LocalClient:
    """用现有uvicorn与标准库访问真实回环服务，不为测试安装httpx。"""
    def __init__(self, port):
        self.endpoint = f'http://127.0.0.1:{port}'
        self.opener = build_opener(ProxyHandler({}))

    def request(self, method, path, headers, *, json_value=None, content=None):
        headers = dict(headers)
        body = content.encode() if content is not None else None
        if json_value is not None:
            body = json.dumps(json_value).encode()
            headers['Content-Type'] = 'application/json'
        request = Request(self.endpoint+path, data=body, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            code, text = response.status, response.read().decode()
        class Result:
            status_code = code
            def json(self): return json.loads(self.text)
        result = Result(); result.text = text
        return result

    def get(self, path, *, headers): return self.request('GET',path,headers)
    def post(self, path, *, headers, json=None, content=None):
        return self.request('POST',path,headers,json_value=json,content=content)


class EtfHttpTests(unittest.TestCase):
    def setUp(self):
        self.fixture = runtime_fixture.RuntimeTests(methodName='test_read_does_not_repair_queued_and_explicit_replay_recovers_before_begin')
        self.fixture.sample_name = getattr(self, 'sample_name', 'single')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        host = self.fixture.data
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1',0))
        port = listener.getsockname()[1]
        origin = 'http://127.0.0.1:' + str(18544 if port != 18544 else 18545)
        from pmi.market_data import ActivityOptions
        from pmi.market_data.periodic_budget import PeriodicOptions
        self.config = ServiceConfig(host, port, (origin,), etf_options=self.fixture.options,
            activity_options=ActivityOptions(host), periodic_options=PeriodicOptions())
        self.runtime = self.config.market_data._etf_runtime
        self.runtime.clock = lambda: self.fixture.now
        self.runtime.budget.clock = self.runtime.clock
        self.fixture.runtimes.append(self.runtime)
        no_network = patch.object(self.runtime.transport,'fetch',side_effect=AssertionError('只允许隔离已缓存输入'))
        no_network.start(); self.addCleanup(no_network.stop)
        server = uvicorn.Server(uvicorn.Config(create_app(self.config),log_level='error',lifespan='on'))
        worker = threading.Thread(target=server.run,kwargs={'sockets':[listener]},name='etf-test-http')
        def close():
            server.should_exit=True
            if worker.ident is not None: worker.join(10)
            self.assertFalse(worker.is_alive(),'回环测试服务必须实际退出')
        self.addCleanup(close)
        worker.start()
        deadline = time.monotonic()+10
        while not server.started and worker.is_alive() and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertTrue(server.started,'自有服务未成功启动；不得接管已有端口')
        self.client = LocalClient(port)
        self.headers = {"X-Wolf-Client": "1", "Origin": origin}
        ready = self.client.get('/api/etf-flow/session', headers=self.headers)
        self.assertEqual(ready.status_code, 200, ready.text)
        self.ready = ready.json()
        self.headers |= {"X-Wolf-Expected-Instance": self.ready['instance_id'], "X-Wolf-Expected-Config": self.ready['config_id']}

    def publish(self):
        current = self.client.get('/api/etf-flow/current', headers=self.headers)
        self.assertEqual(current.status_code, 200, current.text)
        current = current.json()
        parameters = {"expected_snapshot_id": current['snapshot_id'], "plan_id": current['plan']['id']}
        response = self.client.post('/api/etf-flow/update', headers=self.headers | {'X-Wolf-Request-Id':'http-test-operation'}, json=parameters)
        self.assertEqual(response.status_code, 202, response.text)
        self.runtime._worker.join(15)
        operation = self.client.get('/api/etf-flow/operations/http-test-operation', headers=self.headers)
        self.assertEqual(operation.status_code, 200, operation.text)
        self.assertEqual(operation.json()['state'], 'completed', operation.text)
        return operation.json()['snapshot_id'], parameters

    def test_ready_descriptor_current_update_both_views_evidence_and_replay(self):
        verify_resources()
        descriptor = self.config.public_etf_descriptor()
        self.assertEqual({k:v for k,v in self.ready.items() if k not in ('status','instance_id')},
                         {k:v for k,v in descriptor.items() if k != 'endpoint'})
        with patch.object(self.runtime.transport, 'fetch', side_effect=AssertionError('隔离数据已齐备，不应出站')):
            snapshot, parameters = self.publish()
        route = '/api/etf-flow/snapshots/' + snapshot
        original = self.client.get(route+'?mode=original&period=60', headers=self.headers)
        current = self.client.get(route+'?mode=current&period=60', headers=self.headers)
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(current.status_code, 200, current.text)
        ov, cv = original.json(), current.json()
        self.assertIsNone(ov['summary']['evaluation'])
        self.assertTrue(all(x['state']=='unrecorded' and x['evaluation'] is None for x in ov['series']))
        self.assertEqual(ov['data_status']['input_basis'], 'posthoc_inputs')
        self.assertEqual(cv['summary']['evaluation']['amount'], '40')
        self.assertEqual(cv['summary']['evaluation']['c2']['state'], 'insufficient')
        self.assertIsNone(cv['summary']['evaluation']['c2']['positive_ratio'])
        self.assertEqual(len(cv['series']),60)
        member = self.fixture.config.pools[-1].members[0]
        self.assertEqual(cv['members'][0]['code'],member.code)
        source = cv['sources'][0]['object_id']
        evidence = self.client.get(route+'/evidence/'+source,headers=self.headers)
        self.assertEqual(evidence.status_code,200,evidence.text)
        replay = self.client.post('/api/etf-flow/update',headers=self.headers|{'X-Wolf-Request-Id':'http-test-operation'},json=parameters)
        self.assertEqual(replay.status_code,200,replay.text)
        self.assertEqual(replay.json()['snapshot_id'],snapshot)
        self.assertEqual(self.runtime.budget.usage()['requests'],0)

    def test_boundary_rejects_unknown_duplicate_cross_instance_and_unbound_requests_before_io(self):
        with patch.object(self.runtime.transport, 'fetch', side_effect=AssertionError('边界不应出站')):
            cases = [
                ('/api/etf-flow/current?extra=1', self.headers,422),
                ('/api/etf-flow/current', {'X-Wolf-Client':'1'},400),
                ('/api/etf-flow/current', self.headers|{'X-Wolf-Expected-Config':'a'*64},409),
                ('/api/etf-flow/current', self.headers|{'Origin':'http://127.0.0.1:19000'},403),
                ('/api/etf-flow/snapshots/'+'a'*64+'?mode=current&period=60&period=20',self.headers,422),
                ('/api/etf-flow/snapshots/'+'a'*64+'?mode=current&period=4',self.headers,422),
            ]
            for route, headers, status in cases:
                with self.subTest(route=route,status=status):
                    response=self.client.get(route,headers=headers)
                    self.assertEqual(response.status_code,status,response.text)
            response=self.client.post('/api/etf-flow/update',headers=self.headers|{'X-Wolf-Request-Id':'invalid-body','Content-Type':'application/json'},
                content='{"plan_id":"'+'a'*64+'","plan_id":"'+'b'*64+'","expected_snapshot_id":null}')
            self.assertEqual(response.status_code,422,response.text)
            response=self.client.post('/api/etf-flow/update',headers=self.headers|{'X-Wolf-Request-Id':'invalid-body'},json={'expected_snapshot_id':None,'plan_id':'a'*64,'members':[]})
            self.assertEqual(response.status_code,422,response.text)
        self.assertIsNone(self.runtime.store.current_id())
        self.assertEqual(self.runtime.budget.usage()['requests'],0)

    def test_generated_minimum_rejects_negative_counts_and_view_reads_leave_files_unchanged(self):
        snapshot,_=self.publish()
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.fixture.data.rglob('*') if p.is_file()}
        value=self.client.get('/api/etf-flow/snapshots/'+snapshot+'?mode=current&period=260',headers=self.headers)
        self.assertEqual(value.status_code,200,value.text)
        view=value.json()
        self.assertEqual(len(view['series']),260)
        bad=deepcopy(view);bad['summary']['evaluation']['valid_count']=-1
        with self.assertRaises(ContractResponseError):response_value('EtfView',bad)
        bad=deepcopy(view);bad['members'][0]['admission']['required_days']=320
        with self.assertRaises(ContractResponseError):response_value('EtfView',bad)
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.fixture.data.rglob('*') if p.is_file()})

    def test_group_period_date_and_unreferenced_evidence_do_not_widen_scope(self):
        snapshot,_=self.publish()
        route='/api/etf-flow/snapshots/'+snapshot
        for period in (20,60,120,260):
            response=self.client.get(route+f'?mode=current&period={period}&group='+self.fixture.config.pools[-1].members[0].group_id,headers=self.headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(response.json()['series']),period)
        for suffix in ('?mode=current&period=60&end=2026-11-07','?mode=current&period=60&group='+'a'*64):
            self.assertEqual(self.client.get(route+suffix,headers=self.headers).status_code,422)
        self.assertEqual(self.client.get(route+'/evidence/'+'a'*64,headers=self.headers).status_code,404)


class EtfMultiHttpTests(unittest.TestCase):
    def test_five_members_disable_regroup_and_pending_config_use_same_http_logic(self):
        from pmi.market_data.etf_flow.model import Configuration, digest
        from etf_flow_fixture import AT, END
        fixture = EtfHttpTests(methodName='test_ready_descriptor_current_update_both_views_evidence_and_replay')
        fixture.sample_name = 'multiple'
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        snapshot, _ = fixture.publish()
        def view(identifier, group=None):
            path = '/api/etf-flow/snapshots/'+identifier+'?mode=current&period=60'+('&group='+group if group else '')
            response = fixture.client.get(path, headers=fixture.headers)
            self.assertEqual(response.status_code,200,response.text)
            return response.json()
        first = view(snapshot)
        self.assertEqual(len(first['members']), 5)
        self.assertEqual(first['summary']['evaluation']['valid_count'], 5)
        self.assertEqual(first['summary']['evaluation']['amount'], '200')
        self.assertEqual(first['summary']['evaluation']['c2']['positive_ratio'], '1')
        config = deepcopy(fixture.fixture.config.raw)
        changed = deepcopy(config['pool_versions'][-1])
        changed.update(version='test-disable-regroup', effective_date='2026-11-05', confirmed_at=AT, change='仅隔离配置变动')
        changed['members'][0]['disabled_date'] = '2026-11-05'
        changed['members'][-1]['group'] = '配置新增的跨指数分组'
        config['pool_versions'].append(changed)
        with fixture.runtime.store.writer():
            next_id = fixture.runtime.repository.publish(Configuration.parse(config), fixture.fixture.evidence, fixture.fixture.inputs,
                end=END,selection_at=AT,operation_key=digest('isolated-config-only'),expected=snapshot)
        after = view(next_id)
        self.assertEqual(len(after['members']),5)
        self.assertEqual(after['summary']['evaluation']['valid_count'],4)
        self.assertEqual(after['summary']['evaluation']['amount'],'160')
        stopped = next(m for m in after['members'] if m['id']==changed['members'][0]['id'])
        self.assertFalse(stopped['active']);self.assertEqual(stopped['reason'],'disabled')
        group = next(g for g in after['groups'] if g['name']==changed['members'][-1]['group'])
        filtered = view(next_id,group['id'])
        self.assertEqual(len(filtered['members']),1)
        self.assertEqual(filtered['summary']['evaluation']['c2']['state'],'insufficient')
        self.assertEqual(view(snapshot),first,'旧配置与旧输入版本必须保持可读且结果不变')
