"""过期量额加载状态的真实HTTP/浏览器反例；只发布本轮合成版本。"""
from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
import traceback
from unittest.mock import patch

from overview_performance import REPO, seed_complete, port, opened, process, network_guard
from pmi.api import create_app
from pmi.service_config import ServiceConfig
from pmi.market_data import MarketData, SnapshotError, StorageError
from pmi.market_data.activity.model import Options, canonical, digest
from pmi.market_data.activity.facts import index_manifest
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_history_calendar import complete_window
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.storage import index_store as store
from sqlite_fixture import initialize, price_writer as writer_lock
from pmi.market_data.periodic_budget import PeriodicOptions
from pmi.periodic_scheduler import Scheduler
from test_index_series_contract import originals
from test_index_series_runtime import state

INDEX = 'sse:000001:price'


@contextmanager
def fixture_writer(root):
    """观察轮询可能持共享锁；仅等待取锁，不重试发布或任何取数。"""
    deadline=time.monotonic()+10
    while True:
        lock=writer_lock(root)
        try:
            lock.__enter__()
            break
        except (SnapshotError, StorageError) as error:
            if not (str(error).startswith('writer_busy:') or str(error)=='storage_writer_busy') or time.monotonic()>deadline:raise
            time.sleep(.02)
    try:yield
    finally:lock.__exit__(None,None,None)


def config(root, backend, frontend):
    return ServiceConfig(root/'data', backend, (f'http://127.0.0.1:{frontend}',),
                         index_max_attempts=0, index_max_bytes=0, periodic_options=PeriodicOptions(),
                         activity_options=Options(root/'data', max_attempts=0, max_bytes=0))


def serve(root, backend, frontend):
    """产品读服务保持原路径；测试发布器只接受两个固定合成动作，不开放HTTP写口。"""
    import uvicorn
    stop=Event(); configuration=config(root,backend,frontend)
    data=MarketData(root/'data',{},activity_options=Options(root/'data',max_attempts=0,max_bytes=0))
    original_id=data.read_daily(INDEX)['snapshot']['snapshot_id']
    def producer():
        done=set()
        while not stop.wait(.05):
            action=(root/'control.txt').read_text()
            if action in done or action not in ('price','quantity'): continue
            try:
                if action=='price':
                    index=get_index(INDEX);window=complete_window(datetime.fromisoformat('2026-10-29T07:00:00+08:00'))
                    items=list(originals(index,window,prices=('101.00','111.00','91.00','106.00')))
                    raw=json.loads(items[0].content)
                    for row in raw['data']:row.update(tradingValue='1.23',tradingVol='10000')
                    items[0]=replace(items[0],content=canonical(raw))
                    # 新观察须晚于种子回执，否则产品会正确保留较新的当前指针。
                    items=[replace(item,started_at='2026-10-30T00:00:00Z',completed_at='2026-10-30T00:00:01Z') for item in items]
                    with fixture_writer(root/'data'):
                        completed=store.publish(root/'data',index,window,build_manifest(index,window,items),tuple(items),
                                                {**state(index,'quantity-race-p2'),'target_start':window.start,'target_end':window.end})
                        store.save_status(root/'data',index,completed)
                    p2=data.read_daily(INDEX)['snapshot']['snapshot_id'];assert p2!=original_id,'P2应成为新的当前价格'
                    assert data.activity('current',INDEX,p2) is None
                    (root/'p2.json').write_text(json.dumps({'snapshot_id':p2,'missing_quantity':True}))
                else:
                    price=data.read_daily(INDEX)['snapshot'];p2=price['snapshot_id']
                    rt=data._activity_runtime
                    # 固定上证样本沿产品路径复用同一中证价格原件，无网络采集。
                    item=rt._obtain(INDEX,price)
                    manifest=index_manifest(INDEX,price,item)
                    operation={'series_id':INDEX,'request_id':'quantity-race-p2','config_id':'fixture','instance_id':'fixture',
                               'target':p2,'signature':digest({'synthetic_race':True}),'state':'preparing',
                               'activity_id':None,'reason':None,'recovered_from_instance':None,'observation_id':None}
                    with rt.store.lock(write=True):
                        rt.store.publish(manifest,{item.object_id:item.content},None,operation,
                                         {'series_id':INDEX,'sources':[{'source':item.source,'object_id':item.object_id,'url':item.url,
                                         'started_at':item.started_at,'completed_at':item.completed_at,'published_at':None}]})
                        rt.store.write(('operations','quantity-race-p2.json'),canonical(rt.store.current(INDEX,p2)['operation']))
                    assert data.activity('current',INDEX,p2)['price_snapshot_id']==p2
                    assert data.read_daily(INDEX,original_id)['snapshot']['snapshot_id']==original_id
                    (root/'published.json').write_text(json.dumps({'old_price_replay':True,'new_pair':p2,'state':'completed'}))
                done.add(action)
            except Exception as error:
                (root/'producer-error.txt').write_text(traceback.format_exc());return
    # 可控测试发布器取代服务定时器；读取观察、原子发布和所有校验均用产品代码。
    with patch.object(Scheduler,'run',lambda self:self.stop.wait()):
        worker=Thread(target=producer,daemon=True);worker.start()
        try:uvicorn.run(create_app(configuration),host='127.0.0.1',port=backend,log_level='warning',access_log=False)
        finally:stop.set();worker.join(timeout=10);data.close_updates();assert not worker.is_alive()


def main(parent):
    if not parent.is_dir() or parent.is_symlink() or parent.resolve()!=parent or not str(parent).startswith('/private/tmp/wolf-overview-perf-'):
        raise ValueError('仅接受本任务专有合成根')
    root=Path(tempfile.mkdtemp(prefix='quantity-race-',dir=parent));seed_complete(root);(root/'control.txt').write_text('idle')
    backend,frontend=port(),port()
    while frontend==backend:frontend=port()
    configuration=config(root,backend,frontend)
    for name,descriptor in [('base',configuration.public_descriptor()),('index',configuration.public_index_descriptor()),('activity',configuration.public_activity_descriptor())]:
        (root/(name+'.json')).write_text(json.dumps(descriptor))
    configuration.market_data.close_updates()
    env={k:v for k,v in os.environ.items() if not k.startswith('WOLF_') and k not in ('NODE_OPTIONS','PYTHONHOME','NODE_COMPILE_CACHE')}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(REPO/'python/src')+os.pathsep+str(REPO/'python/tests'),
               WOLF_DEV_PORT=str(frontend),WOLF_BROWSER_CONFIG=str(root/'base.json'),WOLF_INDEX_BROWSER_CONFIG=str(root/'index.json'),
               WOLF_ACTIVITY_BROWSER_CONFIG=str(root/'activity.json'),WOLF_VITE_CACHE=str(root/'vite-cache'),WOLF_UI_ORIGIN=f'http://127.0.0.1:{frontend}',
               WOLF_RACE_ROOT=str(root),WOLF_PLAYWRIGHT_MODULE=os.environ['WOLF_PLAYWRIGHT_MODULE'],WOLF_BROWSER_EXECUTABLE=os.environ['WOLF_BROWSER_EXECUTABLE'])
    result={'root':str(root),'synthetic_only':True,'passed':False,'external_fetches':0};print(root,flush=True)
    try:
        with process([sys.executable,'-B',__file__,'--serve',str(root),str(backend),str(frontend)],root,'service',env),\
             process(['node','apps/desktop/node_modules/vite/bin/vite.js','apps/desktop','--config','apps/desktop/vite.config.ts','--configLoader','runner'],root,'frontend',env):
            deadline=time.monotonic()+40
            while not(opened(backend) and opened(frontend)):
                if time.monotonic()>deadline:raise RuntimeError('temporary service not ready')
                time.sleep(.05)
            with (root/'browser.log').open('wb') as log:
                subprocess.run(['node','apps/desktop/scripts/overview_quantity_race.mjs'],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
            result['passed']=json.loads((root/'browser-result.json').read_text())['passed']
            result.update(json.loads((root/'published.json').read_text()))
    finally:
        result['ports_closed']=[not opened(backend),not opened(frontend)]
        result['producer_error']=(root/'producer-error.txt').read_text() if (root/'producer-error.txt').exists() else None
        (root/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
        assert all(result['ports_closed']),result


if __name__=='__main__':
    sys.addaudithook(network_guard)
    if sys.argv[1]=='--serve':serve(Path(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]))
    else:main(Path(sys.argv[1]))
