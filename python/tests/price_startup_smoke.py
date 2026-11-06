"""价格启动自动跟进的隔离夹具；生产链不改，只替换外部来源，浏览器由CUA检查。"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
IDS = ('sse:000001:price', 'szse:399001:price', 'szse:399006:price', 'sse:000688:price')


def isolated_service(root: Path, args: list[str]) -> None:
    """仅合成来源；业务权限、预算、校验、发布和HTTP均使用生产代码。"""
    from pmi import service
    from pmi.market_data import index_series_update as update
    from pmi.market_data.index_series_fetch import reserve, FetchInterrupted
    from pmi.market_data.index_series_contract import SnapshotError
    from test_index_series_contract import originals
    from pmi.api import create_app as real_app
    from pmi.market_data import MarketData
    from pmi.update_service import UpdateService
    real_start = UpdateService.start_startup
    real_read = MarketData.read_daily

    def startup(instance):
        if not json.loads((root/'control.json').read_text()).get('defer_start'):
            return real_start(instance)
        def release_start():
            while not instance._startup_stop.is_set():
                if json.loads((root/'control.json').read_text()).get('start_release'):
                    real_start(instance)
                    return
                instance._startup_stop.wait(.1)
        threading.Thread(target=release_start, daemon=True).start()

    def read_daily(instance, code, snapshot_id=None):
        value = real_read(instance, code, snapshot_id)
        control = json.loads((root/'control.json').read_text())
        if (code == IDS[0] and snapshot_id is None and control.get('fail_new_current') and value
                and value['snapshot']['bars'][-1]['close'] == '205.12'):
            with (root/'read-failures.jsonl').open('a') as out:
                out.write(json.dumps({'index': code, 'snapshot_id': value['snapshot']['snapshot_id'], 'reason': 'synthetic_transient_read'})+'\n')
            raise SnapshotError('synthetic_transient_read')
        return value
    def fetch(parent, index, source, window, job, **kwargs):
        reserve(parent, index, source, window, job, kwargs['budget'], kwargs['stop'])
        with (root/'source-calls.jsonl').open('a') as out:
            out.write(json.dumps({'index': index.index_id, 'source': source, 'job': job})+'\n')
        while not json.loads((root/'control.json').read_text())['release']:
            if kwargs['stop'].wait(.1):
                raise FetchInterrupted('update_interrupted')
        control = json.loads((root/'control.json').read_text())
        if index.index_id in control['fail_ids']:
            raise SnapshotError('synthetic_failure')
        prices = ('200.0049','210.0050','190.0000','205.1234') if index.storage_decimals == 4 else ('200.01','210.02','190.00','205.12')
        original = next(x for x in originals(index, window, prices=prices) if x.source == source)
        # 多次观察回归需让新获取晚于旧记录，不能绕开生产的时间正确性保护。
        if observed_at := control.get('source_observed_at'):
            from dataclasses import replace
            original = replace(original, started_at=observed_at, completed_at=observed_at)
        return original
    def app(*values, **kwargs):
        result = real_app(*values, **kwargs)
        @result.middleware('http')
        async def audit(request, call_next):
            with (root/'http-methods.jsonl').open('a') as out:
                out.write(json.dumps({'method':request.method,'path':request.url.path})+'\n')
            return await call_next(request)
        return result
    sys.argv = ['pmi.service', *args]
    with patch.object(update, 'fetch_bounded', fetch), patch.object(UpdateService, 'start_startup', startup), patch.object(MarketData, 'read_daily', read_daily), patch('pmi.api.create_app', app), patch('requests.sessions.Session.request', side_effect=AssertionError('no external network')):
        service.main()


def prepare(root: Path) -> None:
    """只创建全新/private/tmp隔离目录，不接受业务根。"""
    from test_index_series_contract import WINDOW, originals
    from test_index_series_runtime import state
    from pmi.market_data.index_catalog import get_index
    from pmi.market_data.index_series_contract import build_manifest
    from pmi.market_data import index_series_store as store
    from pmi.market_data.writer_lock import writer_lock
    if root.exists() or root.resolve() != root or not str(root).startswith('/private/tmp/wolf-price-startup-'):
        raise ValueError('must be a new owned temporary root')
    root.mkdir(mode=0o700)
    for name in ('data','runtime','cache'):
        (root/name).mkdir(mode=0o700)
    with writer_lock(root/'data'):
        for index_id in IDS:
            index = get_index(index_id); items = originals(index, WINDOW)
            store.prepare_directories(root/'data', index)
            store.publish(root/'data', index, WINDOW, build_manifest(index, WINDOW, items), items, state(index))
    (root/'control.json').write_text(json.dumps({'release': False, 'fail_ids': [IDS[1]]}))
    wrapper = root/'test-python'
    wrapper.write_text(f'''#!{REPO/'python/.venv/bin/python'}
import sys,runpy
sys.path.insert(0,{str(REPO/'python/tests')!r})
def guard(event,args):
 if event=='socket.connect' and isinstance(args[1],tuple) and args[1][0] not in ('127.0.0.1','::1','localhost'):
  raise RuntimeError('test blocks external network')
sys.addaudithook(guard)
args=sys.argv[1:]
if args[:3]==['-B','-m','pmi.service']:
 from price_startup_smoke import isolated_service
 from pathlib import Path
 isolated_service(Path({str(root)!r}),args[3:])
elif args[:3]==['-B','-m','pmi.managed_runtime']:
 sys.argv=['pmi.managed_runtime',*args[3:]]
 runpy.run_module('pmi.managed_runtime',run_name='__main__')
else:raise RuntimeError('invalid test invocation')
'''); wrapper.chmod(0o700)
    def port():
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]
    config = dict(python=str(wrapper), data_root=str(root/'data'), runtime_base=str(root/'runtime'),service_port=port(), browser_port=port(),
                  index=dict(write_ids=list(IDS),startup_ids=list(IDS),max_attempts=10,max_bytes=10*1048576),activity=None)
    (root/'config.json').write_text(json.dumps(config));(root/'config.json').chmod(0o600)
    print('Prepared isolated fixture; activity=null; 4 startup prices; 10 synthetic requests maximum')


def start(root: Path) -> None:
    """保留启动日志与PID，调用既有启动器，不自动打开用户浏览器。"""
    if root.resolve()!=root or not str(root).startswith('/private/tmp/wolf-price-startup-'):
        raise ValueError('invalid fixture root')
    env = {k:v for k,v in os.environ.items() if not k.startswith('WOLF_') and k not in ('PYTHONHOME','PYTHONPYCACHEPREFIX','NODE_OPTIONS','NODE_COMPILE_CACHE')}
    env.update(PYTHONDONTWRITEBYTECODE='1',XDG_CACHE_HOME=str(root/'cache'),TMPDIR=str(root))
    with (root/'entry.log').open('w') as out:
        child = subprocess.Popen(['node',str(REPO/'apps/desktop/scripts/start_daily.mjs'),'--config',str(root/'config.json'),'--no-open'],env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    (root/'launcher.pid').write_text(str(child.pid))
    until=time.monotonic()+60
    while time.monotonic()<until:
        lines=(root/'entry.log').read_text().splitlines()
        for line in lines:
            if line.startswith('行情总览：'):
                (root/'url.txt').write_text(line.split('：',1)[1]);print(line);return
        if child.poll() is not None:raise RuntimeError('launcher failed, inspect entry.log')
        time.sleep(.1)
    raise RuntimeError('launcher timeout; preserve scene')


def repeat_observation(root: Path) -> None:
    """仅在自有prepare夹具中重复原价格，制造真实current/status观察编号差异。"""
    from dataclasses import replace
    from test_index_series_contract import WINDOW, originals
    from test_index_series_runtime import state
    from pmi.market_data.index_catalog import get_index
    from pmi.market_data.index_series_contract import build_manifest
    from pmi.market_data import index_series_store as store
    from pmi.market_data.writer_lock import writer_lock
    if root.resolve() != root or not str(root).startswith('/private/tmp/wolf-price-startup-'):
        raise ValueError('invalid fixture root')
    assert json.loads((root/'config.json').read_text())['data_root'] == str(root/'data')
    assert not (root/'launcher.pid').exists(), 'only prepare before starting owned service'
    index = get_index(IDS[0])
    items = tuple(replace(item, started_at='2026-10-28T02:00:00Z', completed_at='2026-10-28T02:00:01Z')
                  for item in originals(index, WINDOW))
    with writer_lock(root/'data'):
        pending = {**state(index, 'repeat-old'), 'result': 'unchanged'}
        store.save_status(root/'data', index, pending)
        store.publish(root/'data', index, WINDOW, build_manifest(index, WINDOW, items), items, pending)
    current = store.read_snapshot(root/'data', index)
    status = store.read_status(root/'data', index)
    assert current['snapshot_id'] == status['snapshot_id']
    assert current['observation_id'] != status['observation_id']
    (root/'observation-case.json').write_text(json.dumps({
        'snapshot_id': current['snapshot_id'], 'current_observation': current['observation_id'],
        'status_observation': status['observation_id'], 'result': status['result']}))
    print('Same price snapshot; distinct first/current and later/status observations verified')


if __name__ == '__main__':
    command, value = sys.argv[1:]
    {'prepare':prepare,'start':start,'repeat-observation':repeat_observation}[command](Path(value))
