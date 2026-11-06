"""实际浏览器、托管入口与服务周期更新联调；仅自有临时合成根。"""
from contextlib import ExitStack
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

from periodic_fixture import seed, transport
from pmi.market_data.index_history_calendar import SHANGHAI
from pmi.market_data.periodic_budget import Budget
from pmi.periodic_scheduler import Scheduler

REPO=Path(__file__).resolve().parents[2]


def isolated_service(root: Path,args: list[str]):
    """仅测试进程注入可控墙钟和响应；权限、整批预检、HTTP及发布不替换。"""
    import logging
    logging.basicConfig(filename=str(root/'service.log'),level=logging.INFO)
    from pmi import service
    from pmi.api import create_app as actual_app
    original_init=Budget.__init__
    def control():return json.loads((root/'control.json').read_text())
    def clock():return datetime.fromisoformat(control()['clock']).replace(tzinfo=SHANGHAI)
    def initialize(self,*args,**kwargs): original_init(self,*args,**kwargs);self.clock=clock
    def run(self):
        self.clock=clock
        while not self.stop.is_set():self.tick();self.stop.wait(.2)
    with ExitStack() as stack:
        def app(config):
            config.market_data._activity_runtime.clock=clock
            stack.enter_context(transport(config.market_data,control))
            result=actual_app(config)
            @result.middleware('http')
            async def audit(request,call_next):
                with (root/'http.jsonl').open('a') as out:out.write(json.dumps({'method':request.method,'path':request.url.path})+'\n')
                return await call_next(request)
            return result
        stack.enter_context(patch.object(Budget,'__init__',initialize))
        stack.enter_context(patch.object(Scheduler,'run',run))
        stack.enter_context(patch('pmi.api.create_app',app))
        sys.argv=['pmi.service',*args];service.main()


def main():
    parent=Path(sys.argv[1]).resolve()
    if not str(parent).startswith('/private/tmp/wolf-periodic-smoke-') or not parent.is_dir():raise ValueError('只接受本次隔离根')
    root=Path(tempfile.mkdtemp(prefix='run-',dir=parent));seed(root)
    (root/'control.json').write_text(json.dumps({'clock':'2026-10-30T06:50:00','release':False,'fail_ids':[]}))
    wrapper=root/'test-python'
    wrapper.write_text(f'''#!{REPO/'python/.venv/bin/python'}
import sys,runpy
sys.path.insert(0,{str(REPO/'python/tests')!r})
def guard(event,args):
 if event=='socket.connect' and isinstance(args[1],tuple) and args[1][0] not in ('127.0.0.1','::1','localhost'):raise RuntimeError('禁止测试连接外网')
sys.addaudithook(guard)
a=sys.argv[1:]
if a[:3]==['-B','-m','pmi.service']:
 from periodic_smoke import isolated_service
 from pathlib import Path
 isolated_service(Path({str(root)!r}),a[3:])
elif a[:3]==['-B','-m','pmi.managed_runtime']:
 sys.argv=['pmi.managed_runtime',*a[3:]];runpy.run_module('pmi.managed_runtime',run_name='__main__')
else:raise RuntimeError('invalid test invocation')
''');wrapper.chmod(0o700)
    def port():
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
    from pmi.market_data.activity.model import INDEX_IDS,TWO_MARKET
    config=dict(python=str(wrapper),data_root=str(root/'data'),runtime_base=str(root/'runtime'),service_port=port(),browser_port=port(),
       index=dict(write_ids=list(INDEX_IDS),startup_ids=list(INDEX_IDS),max_attempts=0,max_bytes=0),
       activity=dict(root=str(root/'activity'),write_series=[*INDEX_IDS,TWO_MARKET],startup_series=[*INDEX_IDS,TWO_MARKET],blocked_series=[],budget_ledger=None,budget_cycle='fixture',max_attempts=0,max_bytes=0),
       periodic=dict(daily_requests=80,daily_bytes=33554432,monthly_requests=500,monthly_bytes=536870912))
    (root/'config.json').write_text(json.dumps(config));(root/'config.json').chmod(0o600)
    env={k:v for k,v in os.environ.items() if not k.startswith('WOLF_') and k not in ('PYTHONHOME','PYTHONPYCACHEPREFIX','NODE_OPTIONS','NODE_COMPILE_CACHE')}
    env.update(PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(root),XDG_CACHE_HOME=str(root/'cache'))
    record={'root':str(root),'synthetic_only':True,'passed':False}
    child=None;browser=None
    try:
        with (root/'entry.log').open('wb') as out:
            child=subprocess.Popen(['node',str(REPO/'apps/desktop/scripts/start_daily.mjs'),'--config',str(root/'config.json'),'--no-open'],cwd=REPO,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        record['launcher_pid']=child.pid
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            lines=(root/'entry.log').read_text().splitlines();urls=[x.split('：',1)[1] for x in lines if x.startswith('行情总览：')]
            if urls:break
            if child.poll() is not None:raise RuntimeError('test launcher failed')
            time.sleep(.1)
        else:raise RuntimeError('test launcher timeout')
        env.update(WOLF_PERIODIC_ROOT=str(root),WOLF_UI_ORIGIN=urls[0],WOLF_PLAYWRIGHT_MODULE=os.environ['WOLF_PLAYWRIGHT_MODULE'])
        with (root/'browser.log').open('wb') as out:
            browser=subprocess.Popen(['node','apps/desktop/scripts/periodic_browser.mjs'],cwd=REPO,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
            record['browser_pid']=browser.pid
            if browser.wait(timeout=360)!=0:raise RuntimeError('browser checks failed')
        record['passed']=True
    finally:
        for process in (browser,child):
            if process is not None and process.poll() is None:
                os.killpg(process.pid,signal.SIGINT)
                try:process.wait(timeout=60)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5);record['forced_cleanup']=True
        record['ports_closed']=[]
        for key in ('service_port','browser_port'):
            with socket.socket() as sock:record['ports_closed'].append(sock.connect_ex(('127.0.0.1',config[key]))!=0)
        record['runtime_removed']=list((root/'runtime').iterdir())==[]
        (root/'result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
        assert all(record['ports_closed']) and record['runtime_removed'] and not record.get('forced_cleanup'),record

if __name__=='__main__':main()
