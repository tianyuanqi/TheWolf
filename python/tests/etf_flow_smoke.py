"""ETF托管入口和正式操作区的隔离浏览器联调，无真实来源或运行配置。"""
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

from etf_flow_fixture import AT, END, stored_sample
from pmi.market_data.etf_flow.budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.model import canonical
from pmi.market_data.storage.etf_store import Store

REPO = Path(__file__).resolve().parents[2]


def isolated_service(root: Path, args: list[str]) -> None:
    """测试进程固定时钟、拒绝真实出站；真实权限、HTTP和发布逻辑原样执行。"""
    from pmi import service
    from pmi.api import create_app as actual_app
    clock_file = root/'test-clock.json'
    clock_at = json.loads(clock_file.read_text())['at'] if clock_file.exists() else AT
    def app(config):
        runtime = config.market_data._etf_runtime
        runtime.clock = lambda: datetime.fromisoformat(clock_at)
        runtime.budget.clock = runtime.clock
        result = actual_app(config)
        @result.middleware('http')
        async def audit(request, call_next):
            with (root/'http.jsonl').open('a') as stream:
                stream.write(json.dumps({'method': request.method, 'path': request.url.path})+'\n')
            return await call_next(request)
        return result
    with patch('pmi.api.create_app', app):
        sys.argv = ['pmi.service', *args]; service.main()


def seed(root: Path) -> dict:
    """合成份额/NAV先存已核验缓存；正式页面的发布须经过实际更新POST。"""
    for name in ('price', 'etf', 'runtime', 'cache'): (root/name).mkdir(mode=0o700)
    from sqlite_fixture import initialize
    initialize(root/'etf')
    store = Store(root/'etf'); store.initialize()
    with store.writer():
        config, inputs, evidence, dates = stored_sample(store)
        Cache(store, None, config).save_inputs(inputs)
        grant = Grant.parse({'id': 'isolated-browser-no-network', 'confirmed_at': AT,
            'confirmation': '仅本隔离测试，禁止真实网络', 'expires_at': '2026-11-06T12:00:00+08:00',
            'members': [m.id for m in config.pools[-1].members], 'start': dates[0], 'end': END,
            'domains': ['query.sse.com.cn', 'api.fund.eastmoney.com'], 'max_requests': 0, 'max_bytes': 0,
            'response_limit': 1024, 'interval_seconds': 3, 'timeout_seconds': 1})
        Budget(store, grant).initialize()
    for name, value in (('pool', config.raw), ('evidence', evidence.raw), ('grant', grant.raw)):
        path = root/(name+'.json'); path.write_bytes(canonical(value)); path.chmod(0o600)
    return {'root': str(root/'etf'), 'configuration': str(root/'pool.json'), 'evidence': str(root/'evidence.json'),
        'grant': str(root/'grant.json'), 'write_enabled': True, 'refresh_revision': None}


def main(seed_fixture=seed, browser_script='etf_flow_browser.mjs') -> None:
    output = Path(sys.argv[1]).resolve()
    if output.exists(): raise ValueError('证据目录须为新目录，不能覆盖此前结果')
    output.mkdir(parents=False)
    temporary = tempfile.TemporaryDirectory(prefix='etf-browser-test-', dir='/private/tmp')
    root = Path(temporary.name)
    record = {'root': str(root), 'synthetic_only': True, 'passed': False}
    children = []
    config = None
    try:
        etf = seed_fixture(root)
        wrapper = root/'test-python'
        wrapper.write_text(f'''#!{REPO/'python/.venv/bin/python'}
import sys,runpy
sys.path.insert(0,{str(REPO/'python/tests')!r})
def guard(event,args):
 if event=='socket.connect' and isinstance(args[1],tuple) and args[1][0] not in ('127.0.0.1','::1','localhost'):raise RuntimeError('测试禁止外网')
sys.addaudithook(guard)
a=sys.argv[1:]
if a[:3]==['-B','-m','pmi.service']:
 from etf_flow_smoke import isolated_service
 from pathlib import Path
 isolated_service(Path({str(root)!r}),a[3:])
elif a[:3]==['-B','-m','pmi.managed_runtime']:
 sys.argv=['pmi.managed_runtime',*a[3:]];runpy.run_module('pmi.managed_runtime',run_name='__main__')
else:raise RuntimeError('invalid test invocation')
'''); wrapper.chmod(0o700)
        def port():
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); return sock.getsockname()[1]
        config = {'python': str(wrapper), 'data_root': etf['root'], 'runtime_base': str(root/'runtime'),
            'service_port': port(), 'browser_port': port(), 'etf_flow': etf}
        (root/'config.json').write_text(json.dumps(config)); (root/'config.json').chmod(0o600)
        record['ports'] = [config['service_port'], config['browser_port']]
        env = {k: v for k,v in os.environ.items() if not k.startswith('WOLF_') and k not in ('PYTHONHOME','PYTHONPYCACHEPREFIX','NODE_OPTIONS','NODE_COMPILE_CACHE')}
        env.update(PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(root), XDG_CACHE_HOME=str(root/'cache'))
        with (root/'entry.log').open('wb') as stream:
            child = subprocess.Popen(['node', str(REPO/'apps/desktop/scripts/start_daily.mjs'), '--config', str(root/'config.json'), '--no-open'],
                cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        children.append(child)
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            urls = [line.split('：',1)[1] for line in (root/'entry.log').read_text().splitlines() if line.startswith('行情总览：')]
            if urls: break
            if child.poll() is not None: raise RuntimeError('isolated managed entry failed')
            time.sleep(.1)
        else: raise RuntimeError('isolated managed entry timeout')
        env.update(WOLF_ETF_TEST_ROOT=str(root), WOLF_UI_ORIGIN=urls[0], WOLF_PLAYWRIGHT_MODULE=os.environ['WOLF_PLAYWRIGHT_MODULE'])
        if os.environ.get('WOLF_BROWSER_EXECUTABLE'):
            env['WOLF_BROWSER_EXECUTABLE'] = os.environ['WOLF_BROWSER_EXECUTABLE']
        with (root/'browser.log').open('wb') as stream:
            browser = subprocess.Popen(['node', 'apps/desktop/scripts/'+browser_script], cwd=REPO, env=env,
                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            children.append(browser)
            if browser.wait(timeout=180) != 0: raise RuntimeError('isolated browser checks failed')
        record['passed'] = True
    finally:
        for process in reversed(children):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try: process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5); record['forced_cleanup'] = True
        record['child_exit_codes'] = [p.returncode for p in children]
        record['ports_closed'] = []
        if config:
            for key in ('service_port','browser_port'):
                with socket.socket() as sock: record['ports_closed'].append(sock.connect_ex(('127.0.0.1',config[key])) != 0)
        record['runtime_removed'] = not list((root/'runtime').iterdir()) if (root/'runtime').exists() else True
        processes = subprocess.check_output(['ps','-axo','pid=,pgid=,comm='], text=True)
        record['own_groups_empty'] = not any(int(line.split()[1]) in {p.pid for p in children} for line in processes.splitlines())
        for path in [*root.glob('*.log'), *root.glob('*.png'), *root.glob('*browser.json'), *root.glob('http.jsonl'), *root.glob('page-expectations.json')]:
            shutil.copyfile(path, output/path.name)
        for path in (root/'runtime').glob('*/service.log'):
            shutil.copyfile(path, output/'service-failed.log')
        record['restored'] = all(record['ports_closed']) and record['runtime_removed'] and record['own_groups_empty'] and not record.get('forced_cleanup')
        if record['restored']: temporary.cleanup()
        else: temporary._finalizer.detach()  # 未证明进程退出时保留自有数据与诊断，不自动删除。
        record['temporary_removed'] = not root.exists()
        (output/'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)); print(json.dumps(record), flush=True)
        assert record['restored'] and record['temporary_removed'], record


if __name__ == '__main__': main()
