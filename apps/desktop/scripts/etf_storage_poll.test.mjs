/** 实际ETF hook：版本轮询不替代计划身份，失败和迟到请求不跨连接。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

function harness(){
  const slots=[],effects=[],pending=[],timers=new Map(),calls=[];
  let hook=0,queued=false,mounted=true,serial=0,result,version='p1',currentVersion='p1',versionFailure=false,viewFailure=false,hold;
  let legacy={expected:{config_id:'base'},instance:'instance-1'},refresh=0,query={mode:'original',period:20,end:'',group:''};
  const drain=async()=>{for(let i=0;i<150;i++)await Promise.resolve()};
  const schedule=()=>{if(!queued&&mounted){queued=true;queueMicrotask(()=>{queued=false;if(mounted)render()})}};
  const react={useState:initial=>{const n=hook++;if(!(n in slots))slots[n]=initial;return[slots[n],value=>{const next=typeof value==='function'?value(slots[n]):value;if(!Object.is(next,slots[n])){slots[n]=next;schedule()}}]},
    useRef:initial=>{const n=hook++;return slots[n]??={current:initial}},useEffect:(fn,deps)=>{const n=hook++,old=effects[n];if(!old||deps.some((v,i)=>v!==old.deps[i])){effects[n]={deps,cleanup:old?.cleanup};pending.push([n,fn])}}};
  class Index{static async connect(){return new Index()}close(){}}
  class Etf{
    expected={config_id:'etf'};constructor(instance){this.instance=instance}static async connect(_,instance){return new Etf(instance)}close(){}clearViews(){calls.push('clear')}
    async current(){calls.push('current');return{snapshot_id:currentVersion}}
    async view(snapshot,mode,period){calls.push('view:'+snapshot+':'+period);const gate=hold;hold=undefined;if(gate)await gate.promise;if(viewFailure)throw Error('view unavailable');return{snapshot_id:snapshot,summary:{evaluation:null}}}
  }
  class Versions{async versions(){calls.push('versions');if(versionFailure)throw Error('version unavailable');return{store_id:'store',etf:version?{publication_id:version,source_coverage:{start:'2026-01-05',end:'2026-11-04'}}:null}}}
  const imports={react,'./browserHost':{etfConnectionDescriptor:async()=>({}),indexConnectionDescriptor:async()=>({})},
    './indexSeriesClient':{IndexSeriesClient:Index},'./storedViews':{StoredViews:Versions},'./etfFlowClient':{EtfFlowClient:Etf},
    'react/jsx-runtime':{},'./EtfFlowChart':{},'./EtfFlowDetails':{},'./etfFlowDisplay':{},'./overview.css':{},'./etfFlow.css':{}};
  const module={exports:{}};
  const source=readFileSync(new URL('../src/EtfFlowPage.tsx',import.meta.url),'utf8');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,
    {module,exports:module.exports,require:name=>{assert.ok(name in imports,name);return imports[name]},AbortController,Error,TypeError,JSON,
      setTimeout:(fn,ms)=>{assert.equal(ms,30000);const id=++serial;timers.set(id,fn);return id},clearTimeout:id=>timers.delete(id)});
  function render(){hook=0;result=module.exports.useEtfData(legacy,refresh,query);for(const[n,fn]of pending.splice(0)){effects[n].cleanup?.();effects[n].cleanup=fn()}}
  return{calls,drain,get result(){return result},start:async()=>{render();await drain()},failVersions:v=>{versionFailure=v},failView:v=>{viewFailure=v},
    publish:v=>{version=v;currentVersion=v},mismatch:()=>{currentVersion='raced'},hold:()=>{let resolve;const promise=new Promise(r=>resolve=r);hold={promise};return resolve},
    poll:async()=>{const entry=[...timers][0];assert.ok(entry);timers.delete(entry[0]);await entry[1]();await drain()},
    refresh:async()=>{refresh++;render();await drain()},select:async period=>{query={...query,period};render();await drain()},
    reconnect:async()=>{legacy={...legacy,instance:'instance-2'};render();await drain()},
    close:async()=>{mounted=false;for(const effect of effects)effect?.cleanup?.();await drain();assert.equal(timers.size,0)}};
}

test('ETF正常轮询只查版本；变化才读计划状态和固定窗口',async()=>{
  const h=harness();try{await h.start();assert.equal(h.result.view.snapshot_id,'p1');const count=h.calls.length;await h.poll();assert.deepEqual(h.calls.slice(count),['versions']);
    h.publish('p2');await h.poll();assert.equal(h.result.view.snapshot_id,'p2');assert.equal(h.calls.filter(x=>x==='current').length,2);
    const plans=h.calls.filter(x=>x==='current').length;await h.select(60);assert.equal(h.calls.at(-1),'view:p2:60');assert.equal(h.calls.filter(x=>x==='current').length,plans);
  }finally{await h.close()}
});
test('ETF冷启动及刷新版本失败清内容，同版本恢复不复用失败；计划竞态不拼接',async()=>{
  const h=harness();try{h.failVersions(true);await h.start();assert.equal(h.result.current,undefined);assert.equal(h.calls.filter(x=>x==='current').length,0);
    h.failVersions(false);await h.poll();assert.equal(h.result.view.snapshot_id,'p1');h.failVersions(true);await h.refresh();assert.equal(h.result.view,undefined);
    h.failVersions(false);await h.poll();assert.equal(h.result.view.snapshot_id,'p1');h.mismatch();await h.refresh();assert.equal(h.result.view.snapshot_id,'p1');assert.equal(h.result.current.snapshot_id,'raced');assert.ok(!h.calls.some(x=>x.startsWith('view:raced')));
    h.publish('p2');await h.poll();assert.equal(h.result.view.snapshot_id,'p2');
  }finally{await h.close()}
});
test('ETF窗口失败下次轮询重试；旧连接迟到结果不覆盖新固定版本',async()=>{
  const h=harness();let release;try{h.failView(true);await h.start();assert.equal(h.result.view,undefined);h.failView(false);await h.poll();assert.equal(h.result.view.snapshot_id,'p1');
    release=h.hold();await h.select(60);h.publish('p2');await h.reconnect();release();await h.drain();assert.equal(h.result.view.snapshot_id,'p2');
  }finally{release?.();await h.close()}
});
