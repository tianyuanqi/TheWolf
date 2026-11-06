"""P3合成量额展示联调。指数走真实解析/存储/HTTP；全市场仅在测试进程替换未准入的来源重放器。"""
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from http_test_support import port, request
from market_overview_smoke import IDS, varied_originals
from http_test_support import disk
from test_index_series_contract import WINDOW, encoded
from test_index_series_runtime import state
from test_market_activity import admitted
from pmi.api import create_app
from pmi.market_data import index_series_store as prices
from pmi.market_data.index_catalog import INDICES
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.writer_lock import writer_lock
from pmi.market_data.activity import facts, runtime, calculations
from pmi.market_data.activity.model import Options, Original, MARKET, canonical, digest
from pmi.market_data.activity.sources import url
from pmi.market_data.activity.store import Store
from pmi.service_config import ServiceConfig

REPO = Path(__file__).resolve().parents[2]
STAMP = '2026-10-30T00:00:00+00:00'


def publish(store, manifest, originals, request_id):
    operation = {'series_id': manifest['series_id'], 'request_id': request_id, 'config_id': 'a'*64,
                 'instance_id': '00000000-0000-4000-8000-000000000000', 'target': manifest['price_snapshot_id'] or manifest['anchor_date'],
                 'signature': 'b'*64, 'state': 'preparing', 'activity_id': None, 'reason': None,
                 'recovered_from_instance': None, 'observation_id': None}
    observation = {'series_id': manifest['series_id'], 'sources': [{**item, 'started_at': STAMP, 'completed_at': STAMP, 'published_at': None} for item in manifest['sources']]}
    with store.lock(write=True):
        store.write(('operations', request_id+'.json'), canonical(operation))
        aid = store.publish(manifest, originals, None, operation, observation)
        store.write(('operations', request_id+'.json'), canonical(store.current(manifest['series_id'], operation['target'])['operation']))
    return aid


def fixtures(root):
    """仅在新建独占临时根发布合成原件；不改生产来源规则。"""
    price_root, activity_root = root/'price', root/'activity'
    price_root.mkdir(); activity_root.mkdir()
    store = Store(activity_root)
    for index in INDICES:
        if index.index_id not in IDS:
            continue
        items = varied_originals(index)
        with writer_lock(price_root):
            prices.prepare_directories(price_root, index)
            prices.publish(price_root, index, WINDOW, build_manifest(index, WINDOW, items), items, state(index))
        price = prices.read_snapshot(price_root, index)
        if index.provider == 'csindex':
            body = json.loads(items[0].content)
            for n, row in enumerate(body['data']):
                row.update(tradingValue='1.23' if n != len(WINDOW.dates)-20 else None,
                           tradingVol='0' if n == len(WINDOW.dates)-1 else '10000')
            source = 'csindex'
        else:
            rows = []
            for n, row in enumerate(price['bars']):
                stamp = int(datetime.fromisoformat(row['trade_date']).replace(tzinfo=timezone(timedelta(hours=8))).timestamp()*1000)
                rows.append([str(stamp), row['close'], row['high'], row['open'], row['low'], row['close'], '0', '0',
                             '123000000.00' if n != len(WINDOW.dates)-20 else None, '10000', '0'])
            body = {'code':200, 'message':'', 'data':{'indexCode': index.code, 'indexName': index.name, 'indexEName': index.english_name,
                    'item':['timestamp','current','high','open','low','close','chg','percent','amount','volume','avg'], 'data':rows}}
            source = 'cnindex-raw'
        original = Original(source, encoded(body).encode(), url(index.index_id, list(WINDOW.dates)), STAMP, STAMP)
        manifest = facts.index_manifest(index.index_id, price, original)
        publish(store, manifest, {original.object_id: original.content}, 'p3-'+index.code)
    originals = [Original(m, canonical({'synthetic':True, 'market':m}), 'https://fixture.invalid/'+m, STAMP, STAMP) for m in ('sse','szse','bse')]
    components = {m:{} for m in ('sse','szse','bse')}
    for m, original in zip(components, originals):
        for day in WINDOW.dates:
            value = {'sse':'1.00','szse':'200000000.00','bse':'300000000.00'}[m]
            components[m][day] = [facts.fact(m, 'amount', None if m=='bse' and day==WINDOW.dates[-4] else value, original, day)]
    manifest = facts.market_manifest(WINDOW.anchor_date, WINDOW.as_dict(), WINDOW.calendar_version,
                                     {m:list(WINDOW.dates) for m in components}, components)
    manifest['completion_basis'] = WINDOW.completion_basis
    manifest['sources'] = [{'source':o.source,'object_id':o.object_id,'url':o.url} for o in originals]
    publish(store, manifest, {o.object_id:o.content for o in originals}, 'p3-market')
    (root/'market-test-replay.json').write_bytes(canonical(manifest))


def serve(root, backend, frontend):
    import uvicorn
    with admitted(), patch.object(runtime, 'market_from_originals', side_effect=lambda window, originals: json.loads((root/'market-test-replay.json').read_bytes())), \
         patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('P3测试禁止外部网络')):
        config = ServiceConfig(root/'price', backend, (f'http://127.0.0.1:{frontend}',), activity_options=Options(root/'activity'))
        for name, descriptor in [('legacy',config.public_descriptor()),('index',config.public_index_descriptor()),('activity',config.public_activity_descriptor())]:
            (root/(name+'.json')).write_text(json.dumps(descriptor))
        # 固定实际API输出供客户端反例，不用前端镜像金融公式。
        fixture = {'descriptor':config.public_activity_descriptor(), 'price_descriptor':config.public_index_descriptor(), 'bundles':{}}
        for sid in (*IDS, MARKET):
            price = config.market_data.read_daily(sid)['snapshot'] if sid != MARKET else None
            target = price['snapshot_id'] if price else WINDOW.anchor_date
            rt = config.market_data._activity_runtime
            current = rt.current(sid,target)
            snapshot = rt.fixed(sid,current['activity_id'])
            fixture['bundles'][sid] = {'price':price, 'current':current, 'snapshot':snapshot, 'calculations':rt.calculations(sid,current['activity_id'],calculations.FORMULA)}
        (root/'fixture.json').write_text(json.dumps(fixture))
        uvicorn.run(create_app(config), host='127.0.0.1', port=backend, log_level='warning', proxy_headers=False, server_header=False, access_log=False)


def main():
    parent = Path(os.environ['WOLF_TEST_ROOT'])
    if parent.resolve()!=parent or not str(parent).startswith('/private/tmp/'):
        raise ValueError('仅允许显式独占临时根')
    root = Path(tempfile.mkdtemp(prefix='display-',dir=parent))
    with admitted(): fixtures(root)
    before = disk(root/'price'), disk(root/'activity')
    backend, frontend = port(), port()
    while backend == frontend: frontend=port()
    origin=f'http://127.0.0.1:{frontend}'
    env={**os.environ,'WOLF_DEV_PORT':str(frontend),'WOLF_BROWSER_CONFIG':str(root/'legacy.json'),
         'WOLF_INDEX_BROWSER_CONFIG':str(root/'index.json'),'WOLF_ACTIVITY_BROWSER_CONFIG':str(root/'activity.json'),
         'WOLF_VITE_CACHE':str(root/'vite-cache'),'WOLF_UI_ORIGIN':origin,'WOLF_UI_OUTPUT':str(root),'WOLF_ACTIVITY_FIXTURE':str(root/'fixture.json')}
    children=[]; streams=[]
    record={'synthetic_only':True, 'market_source_replay_test_double':True, 'ports':[backend,frontend], 'before_files':[len(x) for x in before]}
    (root/'before.json').write_text(json.dumps(record))
    def start(label,command):
        stream=(root/(label+'.log')).open('wb');streams.append(stream)
        child=subprocess.Popen(command,cwd=REPO,env=env,stdout=stream,stderr=stream,start_new_session=True);children.append(child)
    def wait_ready(number,path):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if any(c.poll() is not None for c in children): raise RuntimeError('测试进程失败 '+str(root))
            try:
                if request(number,path,headers={'X-Wolf-Client':'1'})[0]==200:return
            except OSError:pass
            time.sleep(.1)
        raise RuntimeError('测试服务超时 '+str(root))
    try:
        start('service',[sys.executable,'-B',__file__,'--serve',str(root),str(backend),str(frontend)])
        wait_ready(backend,'/api/market-activity/session')
        start('vite',['node','apps/desktop/node_modules/vite/bin/vite.js','apps/desktop','--config','apps/desktop/vite.config.ts','--configLoader','runner'])
        wait_ready(frontend,'/__wolf/activity-config')
        for label, script in [('client','activity_client.harness.mjs'),('browser','activity_display.harness.mjs')]:
            with (root/(label+'.log')).open('wb') as log:
                result=subprocess.run(['node',*(['--test'] if label=='client' else []),'apps/desktop/scripts/'+script],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=360)
            assert result.returncode==0, str(root)+' '+label
        record['passed']=True
    finally:
        for c in reversed(children):
            if c.poll() is None:
                os.killpg(c.pid,signal.SIGTERM)
                try:c.wait(timeout=8)
                except subprocess.TimeoutExpired:os.killpg(c.pid,signal.SIGKILL);c.wait(timeout=5)
        for stream in streams:stream.close()
        record['exits']=[c.poll() for c in children]
        record['data_unchanged']=(disk(root/'price'),disk(root/'activity'))==before
        record['ports_closed']=[]
        for number in (backend,frontend):
            with socket.socket() as probe:record['ports_closed'].append(probe.connect_ex(('127.0.0.1',number))!=0)
        (root/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(root)
        assert record['data_unchanged'] and all(record['ports_closed'])


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--serve':serve(Path(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]))
    else:main()
