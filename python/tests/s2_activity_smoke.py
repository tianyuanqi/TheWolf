"""S2真实托管入口与浏览器隔离夹具；只替换外部响应，不替换准入与发布。"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime
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

from pmi.market_data.storage import index_store as prices
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.index_history_calendar import complete_window, SHANGHAI
from sqlite_fixture import initialize, price_writer as writer_lock
from pmi.market_data.activity import fetch
from pmi.market_data.activity.model import INDEX_IDS, TWO_MARKET, MARKET_MAX_BYTES, Original, canonical
from pmi.market_data.activity.sources import url
from http_test_support import disk
from test_index_series_contract import originals, WINDOW
from test_index_series_runtime import state
from test_two_market import market_original

REPO = Path(__file__).resolve().parents[2]


def isolated_service(root: Path, args: list[str]) -> None:
    from pmi import service
    from pmi.api import create_app as real_app
    from pmi.market_data import MarketData
    market_window = complete_window(datetime.now(SHANGHAI))
    def obtain(series, dates, options, cancel):
        while not (root/'release').exists():
            if cancel.wait(.1):
                raise fetch.ActivityError('activity_cancelled')
        fetch.reserve(options, MARKET_MAX_BYTES if series.endswith('-a-json') else 1048576)
        with (root/'requests.jsonl').open('a') as stream: stream.write(json.dumps({'series':series,'dates':dates})+'\n')
        if series.endswith('-a-json'):
            return market_original(series.split('-')[0],dates[0],empty=series.startswith('szse') and dates[0]==market_window.dates[-4])
        index=get_index(series)
        manifest=prices.read_snapshot(root/'data',index)
        rows=[]
        for i,row in enumerate(manifest['evidence'][0]['rows']):
            values=row['raw_values'];stamp=int(datetime.fromisoformat(row['trade_date']).replace(tzinfo=SHANGHAI).timestamp()*1000)
            rows.append([str(stamp),values['close'],values['high'],values['open'],values['low'],values['close'],'0','0','123000000.00','0' if i==len(dates)-1 else '10000','0'])
        body={'code':'200','message':'','data':{'indexCode':index.code,'indexName':index.name,'indexEName':index.english_name,
              'item':['timestamp','current','high','open','low','close','chg','percent','amount','volume','avg'],'data':rows}}
        return Original('cnindex-raw',canonical(body),url(series,dates),'2026-10-31T00:00:00Z','2026-10-31T00:00:01Z')
    def app(*args,**kwargs):
        result=real_app(*args,**kwargs)
        @result.middleware('http')
        async def audit(request, call_next):
            with (root/'http.jsonl').open('a') as stream:stream.write(json.dumps({'method':request.method,'path':request.url.path})+'\n')
            return await call_next(request)
        return result
    sys.argv=['pmi.service',*args]
    with patch.object(fetch,'fetch',obtain), patch('pmi.api.create_app',app), patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('禁止真实外网')):
        service.main()


def prepare(root: Path) -> None:
    for name in ('data','activity','runtime','cache','budget'):(root/name).mkdir(mode=0o700)
    initialize(root/'data')
    with writer_lock(root/'data'):
        for sid in INDEX_IDS:
            index=get_index(sid);items=list(originals(index,WINDOW))
            if index.provider=='csindex':
                raw=json.loads(items[0].content)
                for i,row in enumerate(raw['data']):row.update(tradingValue='1.23',tradingVol='0' if i==len(raw['data'])-1 else '10000')
                items[0]=replace(items[0],content=canonical(raw))
            prices.prepare_directories(root/'data',index)
            prices.publish(root/'data',index,WINDOW,build_manifest(index,WINDOW,items),items,state(index))
    from sqlite_fixture import set_activity_budget
    set_activity_budget(root/'data', canonical({'cycle':'s2-smoke','attempts':0,'bytes':0,'limit_attempts':2200,'limit_bytes':160000000}))
    wrapper=root/'test-python'
    wrapper.write_text(f'''#!{REPO/'python/.venv/bin/python'}
import sys,runpy
sys.path.insert(0,{str(REPO/'python/tests')!r})
def guard(event,args):
 if event=='socket.connect' and isinstance(args[1],tuple) and args[1][0] not in ('127.0.0.1','::1','localhost'):raise RuntimeError('禁止测试外网')
sys.addaudithook(guard)
args=sys.argv[1:]
if args[:3]==['-B','-m','pmi.service']:
 from s2_activity_smoke import isolated_service
 from pathlib import Path
 isolated_service(Path({str(root)!r}),args[3:])
elif args[:3]==['-B','-m','pmi.managed_runtime']:
 sys.argv=['pmi.managed_runtime',*args[3:]];runpy.run_module('pmi.managed_runtime',run_name='__main__')
else:raise RuntimeError('invalid invocation')
''');wrapper.chmod(0o700)
    def port():
        with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
    config=dict(python=str(wrapper),data_root=str(root/'data'),runtime_base=str(root/'runtime'),service_port=port(),browser_port=port(),
                index=dict(write_ids=[],startup_ids=[],max_attempts=0,max_bytes=0),
                activity=dict(root=str(root/'data'),write_series=[*INDEX_IDS,TWO_MARKET],startup_series=[*INDEX_IDS,TWO_MARKET],blocked_series=[],budget_ledger=str(root/'data/facts.sqlite'),budget_cycle='s2-smoke',max_attempts=2200,max_bytes=160000000))
    (root/'config.json').write_text(json.dumps(config));(root/'config.json').chmod(0o600)


def main():
    parent=Path(os.environ['WOLF_TEST_ROOT']).resolve()
    if not str(parent).startswith('/private/tmp/wolf-s2-') or not parent.is_dir():raise ValueError('仅自有隔离根')
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));prepare(root)
    before=disk(root/'data')
    env={k:v for k,v in os.environ.items() if not k.startswith('WOLF_') and k not in ('PYTHONHOME','PYTHONPYCACHEPREFIX','NODE_OPTIONS','NODE_COMPILE_CACHE')}
    env.update(TMPDIR=str(root),XDG_CACHE_HOME=str(root/'cache'),PYTHONDONTWRITEBYTECODE='1')
    out=(root/'entry.log').open('wb')
    child=subprocess.Popen(['node',str(REPO/'apps/desktop/scripts/start_daily.mjs'),'--config',str(root/'config.json'),'--no-open'],cwd=REPO,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    record={'synthetic_only':True,'root':str(root),'launcher':child.pid,'passed':False}
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            lines=(root/'entry.log').read_text().splitlines();urls=[x.split('：',1)[1] for x in lines if x.startswith('行情总览：')]
            if urls:break
            if child.poll() is not None:raise RuntimeError('启动失败：'+str(root))
            time.sleep(.2)
        else:raise RuntimeError('启动超时')
        env.update(WOLF_S2_ROOT=str(root),WOLF_UI_ORIGIN=urls[0],WOLF_PLAYWRIGHT_MODULE=os.environ['WOLF_PLAYWRIGHT_MODULE'])
        with (root/'browser.log').open('wb') as log:
            browser=subprocess.Popen(['node','apps/desktop/scripts/s2_activity_browser.mjs'],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            record['browser_pid']=browser.pid
            try:
                if browser.wait(timeout=600):raise RuntimeError('浏览器验证失败：'+str(root))
            finally:
                if browser.poll() is None:
                    os.killpg(browser.pid,signal.SIGTERM);browser.wait(timeout=20)
        record['passed']=True
    finally:
        if child.poll() is None:os.kill(child.pid,signal.SIGTERM)
        try:child.wait(timeout=30)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=20)
        out.close()
        record['price_unchanged']=before==disk(root/'data')
        record['runtime_empty']=not any((root/'runtime').iterdir())
        config=json.loads((root/'config.json').read_text());closed=[]
        for port in (config['service_port'],config['browser_port']):
            with socket.socket() as sock:closed.append(sock.connect_ex(('127.0.0.1',port))!=0)
        record['ports_closed']=closed;record['exit_code']=child.returncode
        (root/'result.json').write_text(json.dumps(record,indent=2))
        print(json.dumps(record))


if __name__=='__main__':main()
