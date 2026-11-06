"""B1配置、拒绝与真实自有进程生命周期；只用本次临时空根。"""
import fcntl, json, os, signal, socket, subprocess, tempfile, time, unittest, selectors
from pathlib import Path
from pmi.managed_config import parse, service_arguments
from pmi.managed_runtime import remove_tree
REPO=Path(__file__).resolve().parents[2]


def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wolf-b1-config-',dir='/private/tmp');self.root=Path(self.temp.name)
        for name in ('data','runtime','activity','ledger'):(self.root/name).mkdir(mode=0o700)
        self.value=dict(python=str(REPO/'python/.venv/bin/python'),data_root=str(self.root/'data'),runtime_base=str(self.root/'runtime'),service_port=18080,browser_port=18081)
    def tearDown(self):self.temp.cleanup()
    def test_zero_defaults_and_no_side_effect(self):
        value,config,_=parse(json.dumps(self.value),REPO)
        self.assertEqual(config.index_write_ids,());self.assertEqual(config.public_index_descriptor()['policy']['network']['max_attempts'],0)
        self.assertEqual(list((self.root/'data').iterdir()),[]);self.assertEqual(list((self.root/'runtime').iterdir()),[])
        self.assertIn('--index-max-attempts',service_arguments(value))
    def test_duplicate_unknown_boolean_budget_and_startup_subset(self):
        with self.assertRaises(ValueError):parse(json.dumps(self.value|{'slice_write':False}),REPO)
        for replacement in [{'unknown':1},{'index':{'write_ids':[],'startup_ids':['sse:000001:price'],'max_attempts':0,'max_bytes':0}},
                            {'index':{'write_ids':[],'startup_ids':[],'max_attempts':True,'max_bytes':0}}]:
            with self.assertRaises(ValueError):parse(json.dumps(self.value|replacement),REPO)
    def test_overlapping_paths_and_symlinks_rejected(self):
        for base in [self.root,self.root/'data',REPO]:
            with self.assertRaises(ValueError):parse(json.dumps(self.value|{'runtime_base':str(base)}),REPO)
        (self.root/'link').symlink_to(self.root/'data')
        with self.assertRaises(ValueError):parse(json.dumps(self.value|{'data_root':str(self.root/'link')}),REPO)
    def test_activity_does_not_admit_sources(self):
        act=dict(root=str(self.root/'activity'),write_series=['sse:000001:price'],blocked_series=[],budget_ledger=None,budget_cycle='test',max_attempts=0,max_bytes=0)
        _,config,_=parse(json.dumps(self.value|{'activity':act}),REPO)
        _,readonly,_=parse(json.dumps(self.value|{'activity':act|{'write_series':[]}}),REPO)
        self.assertEqual(config.public_activity_descriptor()['policy']['sources'],readonly.public_activity_descriptor()['policy']['sources'])
        self.assertFalse(any(x['admitted'] for x in config.public_activity_descriptor()['policy']['sources'] if x['series'] in ('sse','szse','bse')))
        self.assertEqual(config.public_activity_descriptor()['startup_series'],[])
    def test_cleanup_refuses_link_and_protects_outside(self):
        folder=self.root/'runtime';outside=self.root/'sentinel';outside.write_text('keep');(folder/'link').symlink_to(outside)
        fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
        try:
            with self.assertRaises(ValueError):remove_tree(fd)
        finally:os.close(fd)
        self.assertEqual(outside.read_text(),'keep')


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wolf-b1-life-',dir='/private/tmp');self.root=Path(self.temp.name);self.children=[];self.streams=[]
        for name in ('data','runtime'):(self.root/name).mkdir(mode=0o700)
        self.value=dict(python=str(REPO/'python/.venv/bin/python'),data_root=str(self.root/'data'),runtime_base=str(self.root/'runtime'),service_port=port(),browser_port=port())
    def launch(self, ready=True):
        path=self.root/'config.json';path.write_text(json.dumps(self.value));stream=(self.root/f'log-{len(self.children)}').open('w');self.streams.append(stream)
        env={k:v for k,v in os.environ.items() if not k.startswith('WOLF_')}
        child=subprocess.Popen(['node',str(REPO/'apps/desktop/scripts/start_daily.mjs'),'--config',str(path),'--no-open'],env=env,stdout=subprocess.PIPE,stderr=stream,text=True);self.children.append(child)
        if not ready:return child
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout,selectors.EVENT_READ)
            until=time.monotonic()+65
            while time.monotonic()<until:
                if selector.select(.2) and child.stdout.readline().startswith('行情总览：'):return child
                if child.poll() is not None:self.fail('入口未就绪')
        self.fail('入口超时')
    def stopped(self):
        until=time.monotonic()+12
        while time.monotonic()<until:
            opened=[]
            for p in (self.value['service_port'],self.value['browser_port']):
                with socket.socket() as s:opened.append(s.connect_ex(('127.0.0.1',p))==0)
            if not any(opened):return
            time.sleep(.1)
        self.fail('自有端口未关闭')
    def tearDown(self):
        if any(case is self for case,_ in self._outcome.result.failures + self._outcome.result.errors):
            for log in [*self.root.glob('log-*'),*self.root.glob('runtime/*/service.log'),*self.root.glob('runtime/*/vite.log')]: print('隔离失败日志：'+log.name+'\n'+log.read_text(),flush=True)
        for child in self.children:
            if child.poll() is None:child.send_signal(signal.SIGINT)
            child.wait(12)
            if child.stdout:child.stdout.close()
        for stream in self.streams:stream.close()
        self.stopped()
        # 仅清理本测试独占目录；先证明该自有PGID没有存活成员。
        for owner in (self.root/'runtime').glob('*/owner.json'):
            pgid=json.loads(owner.read_text())['pid']
            output=subprocess.check_output(['/bin/ps','-axo','pgid='],text=True)
            self.assertNotIn(str(pgid),output.split())
        self.temp.cleanup()
    def test_normal_stop_reclaims_run(self):
        child=self.launch();child.send_signal(signal.SIGINT);self.assertEqual(child.wait(12),0);self.stopped();self.assertEqual(list((self.root/'runtime').iterdir()),[])
    def test_startup_zero_budget_is_server_controlled(self):
        from urllib.request import Request,urlopen
        self.value['index']=dict(write_ids=['sse:000001:price'],startup_ids=['sse:000001:price'],max_attempts=0,max_bytes=0)
        child=self.launch();endpoint=f"http://127.0.0.1:{self.value['service_port']}"
        def get(path,headers):
            with urlopen(Request(endpoint+path,headers=headers),timeout=2) as response:return json.load(response)
        ready=get('/api/index-series/session',{'X-Wolf-Client':'1'})
        headers={'X-Wolf-Client':'1','X-Wolf-Expected-Instance':ready['instance_id'],'X-Wolf-Expected-Config':ready['config_id']}
        until=time.monotonic()+5
        while time.monotonic()<until:
            status=get('/api/index-series/sse%3A000001%3Aprice/update',headers)
            if status['stage']=='failed':break
            time.sleep(.1)
        self.assertEqual(status['trigger'],'startup');self.assertEqual(status['stage'],'failed')
        self.assertEqual(ready['startup_indices'],['sse:000001:price']);self.assertEqual(ready['policy']['network']['max_attempts'],0)
        self.assertFalse((self.root/'data/index-v2-network-ledger.jsonl').exists())
        child.send_signal(signal.SIGINT);self.assertEqual(child.wait(12),0,(self.root/'log-0').read_text())

    def test_occupied_port_not_taken_over(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',self.value['service_port']));occupied.listen()
            child=self.launch(False);self.assertNotEqual(child.wait(10),0)
            with socket.socket() as probe:self.assertEqual(probe.connect_ex(('127.0.0.1',self.value['service_port'])),0)
            self.assertEqual(list((self.root/'runtime').iterdir()),[])
    def test_launcher_sigkill_reclaims_children(self):
        child=self.launch();child.kill();child.wait(3);self.stopped()
        until=time.monotonic()+12
        while list((self.root/'runtime').iterdir()) and time.monotonic()<until:time.sleep(.1)
        self.assertEqual(list((self.root/'runtime').iterdir()),[])
    def test_replaced_lease_locked_by_other_owner_is_retained(self):
        child=self.launch();run=next((self.root/'runtime').iterdir())
        (run/'lease').rename(self.root/'original-lease')
        with (run/'lease').open('w+') as replacement:
            replacement.write('test-owned replacement');replacement.flush();fcntl.flock(replacement,fcntl.LOCK_EX|fcntl.LOCK_NB)
            child.send_signal(signal.SIGINT);self.assertNotEqual(child.wait(14),0);self.stopped()
            self.assertTrue((run/'lease').exists());self.assertEqual(os.fstat(replacement.fileno()).st_nlink,1)
            for stream in self.streams:stream.flush()
            self.assertIn(str(run),(self.root/'log-0').read_text())
    def test_replaced_registered_descriptor_is_retained(self):
        child=self.launch();run=next((self.root/'runtime').iterdir())
        replacement=self.root/'new.json';replacement.write_bytes((run/'connection.json').read_bytes());replacement.replace(run/'connection.json')
        child.send_signal(signal.SIGINT);self.assertNotEqual(child.wait(14),0);self.stopped();self.assertTrue((run/'connection.json').exists())

    def test_guardian_sigkill_stops_service_and_vite(self):
        child=self.launch();owner=next((self.root/'runtime').glob('*/owner.json'));pgid=json.loads(owner.read_text())['pid'];os.kill(pgid,signal.SIGKILL)
        child.wait(14);self.stopped()
        for stream in self.streams:stream.flush()
        diagnostic=(self.root/'log-0').read_text()
        self.assertIn('本次运行已失效',diagnostic);self.assertIn('已核验本次自有进程组退出',diagnostic);self.assertIn(str(owner.parent),diagnostic)
        output=subprocess.check_output(['/bin/ps','-axo','pgid='],text=True);self.assertNotIn(str(pgid),output.split())
        # 异常强杀允许留运行目录，不能谎称已自动清理。
        self.assertTrue(owner.exists())


if __name__=='__main__':unittest.main()
