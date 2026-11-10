"""macOS托管监护：自有管道确认实例，自有进程组退出后才清理运行资源。"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, build_opener, ProxyHandler

from pmi.managed_config import parse, location, service_arguments


def members() -> list[int]:
    """只观察当前存活监护者所在组；不按旧PID或端口追杀。"""
    probe = subprocess.Popen(['/bin/ps', '-axo', 'pid=,pgid='], stdout=subprocess.PIPE, text=True)
    output, _ = probe.communicate()
    return [int(p) for p, group in (line.split() for line in output.splitlines()) if int(group) == os.getpgrp() and int(p) not in (os.getpid(), probe.pid)]


def remove_tree(fd: int) -> None:
    """相对已持有的目录FD清理，不跟随链接；遇异常保留余项。"""
    for name in os.listdir(fd):
        item = os.stat(name, dir_fd=fd, follow_symlinks=False)
        import stat
        if stat.S_ISDIR(item.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try: remove_tree(child)
            finally: os.close(child)
            os.rmdir(name, dir_fd=fd)
        elif stat.S_ISREG(item.st_mode) and item.st_nlink == 1:
            os.unlink(name, dir_fd=fd)
        else:
            raise ValueError('运行资源含链接或未知类型，保留')


def main() -> None:
    """执行一次有限生命周期；任何失败均回收自有子进程，不接管占用者。"""
    if sys.platform != 'darwin' or os.getpid() != os.getpgrp():
        raise ValueError('监护者必须在macOS独占进程组中启动')
    node, repo = sys.argv[1], Path(sys.argv[2]).resolve()
    payload = json.loads(sys.stdin.readline(131073))
    value, config, base = parse(payload['config'], repo)
    location(payload['config_path'], directory=False)
    if any(key.startswith('WOLF_') for key in os.environ):
        raise ValueError('托管配置禁止环境覆盖')
    # 只探测端口可绑定性；真正监听仍严格失败，不以探测结果认领外部服务。
    for port in (config.port, value['browser_port']):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))
    run_id = str(uuid.uuid4()); run = base / run_id
    run.mkdir(mode=0o700)
    directory_fd = os.open(run, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identity = os.fstat(directory_fd)
    lease = os.open('lease', os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory_fd)
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker = {'run_id': run_id, 'device': identity.st_dev, 'inode': identity.st_ino, 'pid': os.getpid()}
    (run/'owner.json').write_text(json.dumps(marker))
    for name in ('tmp', 'cache', 'vite-cache'): (run/name).mkdir(mode=0o700)
    registered = {}
    def register(name: str):
        item = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        registered[name] = (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode))
    for name in ('lease', 'owner.json', 'tmp', 'cache', 'vite-cache'): register(name)
    env = {**os.environ, 'TMPDIR': str(run/'tmp'), 'TMP': str(run/'tmp'), 'TEMP': str(run/'tmp'), 'XDG_CACHE_HOME': str(run/'cache'),
           'PYTHONPATH': str(repo/'python/src'), 'PYTHONDONTWRITEBYTECODE': '1'}
    env.pop('PYTHONPYCACHEPREFIX', None); env.pop('PYTHONHOME', None)
    stop = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.read(), stop.set()), daemon=True).start()
    signal.signal(signal.SIGINT, lambda *_: stop.set()); signal.signal(signal.SIGTERM, lambda *_: stop.set())
    children: list[subprocess.Popen] = []; watches: list[int] = []; streams = []; failed = False
    opener = build_opener(ProxyHandler({}))

    def request(url: str) -> tuple[dict, object]:
        with opener.open(Request(url, headers={'X-Wolf-Client':'1'}), timeout=.5) as response:
            return json.load(response), response.headers

    def wait_ready(test, deadline: float):
        while time.monotonic() < deadline and not stop.is_set():
            if any(child.poll() is not None for child in children): raise ValueError('自有子进程提前退出')
            try:
                if test(): return
            except (URLError, TimeoutError, ConnectionError): pass
            stop.wait(.1)
        raise ValueError('启动超时或已停止')

    try:
        record_read, record_write = os.pipe()
        read_fd, write_fd = os.pipe(); watches.append(write_fd)
        stream = (run/'service.log').open('wb'); streams.append(stream); register('service.log')
        command = [value['python'], '-B', '-m', 'pmi.service', *service_arguments(value), '--managed-run-id', run_id,
                   '--managed-control-fd', str(record_write), '--managed-watch-fd', str(read_fd)]
        service = subprocess.Popen(command, cwd=repo, env=env, pass_fds=(read_fd,record_write), stdin=subprocess.DEVNULL, stdout=stream, stderr=stream)
        children.append(service);os.close(read_fd);os.close(record_write)
        deadline = time.monotonic()+30
        buffer = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(record_read, selectors.EVENT_READ)
            def read_record():
                if not selector.select(.05): return False
                chunk = os.read(record_read, 8192)
                if not chunk: raise ValueError('服务控制管道提前断开')
                buffer.extend(chunk)
                if len(buffer)>8192: raise ValueError('服务控制记录超限')
                return b'\n' in buffer
            try: wait_ready(read_record, deadline)
            finally: os.close(record_read)
        record = json.loads(buffer)
        expected = {'version':1,'run_id':run_id,'instance_id':record.get('instance_id'),'config_id':config.config_id,
                    'index_config_id':config.index_config_id,'activity_config_id':config.activity_config_id if config.activity_options else None}
        if config.etf_options:
            expected['etf_config_id'] = config.etf_config_id
        if record != expected or str(uuid.UUID(record['instance_id'])) != record['instance_id']: raise ValueError('自有控制记录不匹配')
        descriptors = [(config.public_descriptor(),'/api/session/ready','connection.json'),
                       (config.public_index_descriptor(),'/api/index-series/session','index.json')]
        if config.activity_options: descriptors.append((config.public_activity_descriptor(),'/api/market-activity/session','activity.json'))
        if config.etf_options: descriptors.append((config.public_etf_descriptor(),'/api/etf-flow/session','etf.json'))
        def service_ready():
            for descriptor,path,_ in descriptors:
                body,headers = request(descriptor['endpoint']+path)
                expected_body = {k:v for k,v in descriptor.items() if k!='endpoint'} | {'status':'ready','instance_id':record['instance_id']}
                if path == '/api/market-activity/session':
                    from datetime import date
                    anchor = body.get('market_anchor_date')
                    if not isinstance(anchor, str) or date.fromisoformat(anchor).isoformat() != anchor:
                        raise ValueError('市场日期无效')
                    expected_body['market_anchor_date'] = anchor
                    anchors = body.get('market_anchors')
                    if not isinstance(anchors, dict) or set(anchors) != {'sse_szse', 'sse_szse_bse'}:
                        raise ValueError('市场发布日期无效')
                    for published in anchors.values():
                        if published is not None and (not isinstance(published, str) or date.fromisoformat(published).isoformat() != published or published > anchor):
                            raise ValueError('市场发布日期无效')
                    expected_body['market_anchors'] = anchors
                if body != expected_body or headers.get('X-Wolf-Instance')!=record['instance_id'] or headers.get('X-Wolf-Config')!=descriptor['config_id']:
                    raise ValueError('HTTP就绪与自有控制链不符')
            return True
        wait_ready(service_ready, deadline)
        for descriptor,_,name in descriptors:
            if name=='connection.json': descriptor |= {'connection_mode':'managed','run_id':run_id,'expected_instance_id':record['instance_id']}
            (run/name).write_text(json.dumps(descriptor)); register(name)
        read_fd, write_fd = os.pipe(); watches.append(write_fd)
        stream=(run/'vite.log').open('wb');streams.append(stream);register('vite.log')
        vite_env = env | {'WOLF_DEV_PORT':str(value['browser_port']),'WOLF_BROWSER_CONFIG':str(run/'connection.json'),
                         'WOLF_INDEX_BROWSER_CONFIG':str(run/'index.json'),'WOLF_VITE_CACHE':str(run/'vite-cache'),
                         'WOLF_MANAGED_RUN':str(run),'WOLF_MANAGED_WATCH_FD':str(read_fd),'WOLF_MANAGED_PGID':str(os.getpid())}
        if config.activity_options: vite_env['WOLF_ACTIVITY_BROWSER_CONFIG']=str(run/'activity.json')
        if config.etf_options: vite_env['WOLF_ETF_BROWSER_CONFIG']=str(run/'etf.json')
        vite = subprocess.Popen([node,str(repo/'apps/desktop/scripts/managed_vite.mjs')],cwd=repo,env=vite_env,pass_fds=(read_fd,),stdin=subprocess.DEVNULL,stdout=stream,stderr=stream)
        children.append(vite);os.close(read_fd)
        origin=f"http://127.0.0.1:{value['browser_port']}"
        def browser_ready():
            body,_=request(origin+'/__wolf/config')
            if body != json.loads((run/'connection.json').read_text()): raise ValueError('浏览器宿主配置不匹配')
            with opener.open(origin+'/', timeout=.5) as response:
                return response.status==200 and response.headers.get('X-Frame-Options')=='DENY'
        wait_ready(browser_ready,time.monotonic()+30)
        print(json.dumps({'event':'ready','url':origin+f'/#wolf-run={run_id}&wolf-instance={record["instance_id"]}&page=overview'}),flush=True)
        while not stop.wait(.2):
            if any(child.poll() is not None for child in children): raise ValueError('受管进程意外退出')
    except (OSError, ValueError, KeyError, BrokenPipeError) as error:
        failed=True;print('托管启动／运行失败：'+str(error),file=sys.stderr)
    finally:
        for fd in watches:
            try: os.write(fd,b'stop\n')
            except OSError: pass
            os.close(fd)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and any(p.poll() is None for p in children): time.sleep(.05)
        if members():
            os.killpg(os.getpgrp(),signal.SIGTERM)
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                for p in children: p.poll()
                if not members(): break
                time.sleep(.05)
        for stream in streams: stream.close()
        remaining = members()
        if remaining:
            print('自有进程未在退出期限内结束：'+','.join(map(str,remaining)),file=sys.stderr)
            print(subprocess.run(['/bin/ps','-o','pid=,ppid=,pgid=,stat=,comm=','-p',','.join(map(str,remaining))],text=True,capture_output=True).stdout,file=sys.stderr)
            print(json.dumps({'event':'retained','path':str(run)}),flush=True)
            os.killpg(os.getpgrp(),signal.SIGKILL)
        try:
            current=run.stat(follow_symlinks=False)
            if (current.st_dev,current.st_ino)!=(identity.st_dev,identity.st_ino) or json.loads((run/'owner.json').read_text())!=marker or set(os.listdir(directory_fd))!=set(registered):
                raise ValueError('运行目录身份或登记资源改变')
            for name, expected_identity in registered.items():
                item = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode)) != expected_identity or (stat.S_ISREG(item.st_mode) and item.st_nlink != 1):
                    raise ValueError('登记资源身份改变，保留')
            held = os.fstat(lease)
            if registered['lease'][:2] != (held.st_dev, held.st_ino):
                raise ValueError('租约不再对应已持有的锁，保留')
            location(str(base));parse(payload['config'],repo)
            remove_tree(directory_fd);run.rmdir()
        except (OSError, ValueError) as error:
            print('运行目录未清理：'+str(error),file=sys.stderr)
            print(json.dumps({'event':'retained','path':str(run)}),flush=True);failed=True
        finally: os.close(lease);os.close(directory_fd)
    if failed: sys.exit(1)


if __name__=='__main__':
    try: main()
    except (ValueError, OSError, KeyError) as error:
        print('托管配置／启动失败：'+str(error),file=sys.stderr);sys.exit(1)
