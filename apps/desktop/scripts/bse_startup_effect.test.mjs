/** Actual component effect + actual non-periodic observer; frozen startup target differs from displayed snapshot. */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const INDEX='sse:000001:price';
const TWO='cn-a-turnover-sse-szse',THREE='cn-a-turnover',NEW='2026-11-05',OLD='2026-11-04';
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
const read=n=>readFileSync(new URL('../src/'+n,import.meta.url),'utf8');
function harness(anchor){
 const slots=[],timers=new Map(),calls=[],loads=[];let hook=0,serial=0,clock=0,queued=false,mounted=true,deps,nextEffect,cleanup,view,published=false,fail=false;
 const legacy={expected:{config_id:'legacy',data_scope_id:'scope'},instance:'i',closed:false},expected={policy:{},startup_indices:[]};
 const descriptor={startup_series:[TWO,THREE]};
 class Price {expected=expected;instance='i';closed=false;static async connect(){return new Price()};async current(){return {snapshot_id:'price',instrument:{id:INDEX},window:{anchor_date:NEW}}};async calculations(){return {}};close(){this.closed=true}}
 class Activity {expected=descriptor;closed=false;marketAnchor=NEW;marketAnchors={sse_szse:anchor,sse_szse_bse:anchor};
  static async connect(){return new Activity()};close(){this.closed=true}
  async currentVersion(id,target){calls.push([id,target]);return target===NEW&&published?id+NEW:undefined}
  async load(id,target){loads.push([id,target]);if(target===NEW&&fail)throw Error('temporary read failure');return {snapshot:{activity_id:id+target,anchor_date:target}}}
 }
 const schedule=()=>{if(!queued&&mounted){queued=true;queueMicrotask(()=>{queued=false;if(mounted)render()})}};
 const context=vm.createContext({module:{exports:{}},exports:{},Map,Set,Promise,AbortController,Error,DOMException,TypeError,Date:class extends Date{static now(){return clock}},
  setTimeout:fn=>{const id=++serial;timers.set(id,fn);return id},clearTimeout:id=>timers.delete(id),
  require:()=>({createStartupPriceObservation:()=>({deadline:300000,nextCheckAt:0})}),
  useState:initial=>{const n=hook++;if(!(n in slots))slots[n]=initial;return[slots[n],v=>{slots[n]=typeof v==='function'?v(slots[n]):v;schedule()}]},
  useRef:initial=>{const n=hook++;return slots[n]??={current:initial}},
  useEffect:(f,d)=>{if(!deps||d.some((v,i)=>v!==deps[i])){deps=d;nextEffect=f}},
  IndexSeriesClient:Price,ActivityClient:Activity,IndexReadError:class extends Error{},ActivityReadError:class extends Error{},
  indexConnectionDescriptor:async()=>expected,activityConnectionDescriptor:async()=>descriptor,activityGate:()=>null,
  createStartupPriceObservation:()=>({deadline:300000,nextCheckAt:0}),watchStartupPrices:()=>{},
  OVERVIEW_INDICES:[{id:INDEX}],MARKET:TWO,LEGACY_MARKET:THREE,isMarket:id=>[TWO,THREE].includes(id),DEFAULT_MA:[5,10,20,30,250],errorText:e=>e.message});
 context.exports=context.module.exports;vm.runInContext(compile(read('startupActivity.ts')),context);Object.assign(context,context.module.exports);
 const source=read('ProductionOverview.tsx');vm.runInContext(compile(source.slice(source.indexOf('export function ProductionOverview('),source.indexOf('  const trends = useMemo'))+'\nreturn activityState;\n}'),context);
 function render(){hook=0;view=context.module.exports.ProductionOverview({connectionClient:legacy});if(nextEffect){const f=nextEffect;nextEffect=undefined;cleanup?.();cleanup=f()}}
 const drain=async()=>{for(let i=0;i<150;i++)await Promise.resolve()};
 return {calls,loads,timers,get view(){return view},set published(x){published=x},set fail(x){fail=x},
  start:async()=>{render();await drain()},tick:async(ms=3000)=>{clock+=ms;for(const[id,fn]of[...timers]){timers.delete(id);fn()}await drain()},
  close:async()=>{mounted=false;cleanup?.();await drain();assert.equal(timers.size,0)}};
}
for(const anchor of [null,OLD])test(`非周期首屏${anchor??'空库'}仍跟进ready冻结新目标`,async()=>{
 const h=harness(anchor);try{await h.start();assert.ok(h.calls.length>=2);assert.ok(h.calls.every(([,d])=>d===NEW));
  assert.equal(h.view.entries[THREE]?.bundle?.snapshot.anchor_date,anchor??undefined);
  h.published=true;await h.tick();assert.equal(h.view.entries[TWO].bundle.snapshot.anchor_date,NEW);assert.equal(h.view.entries[THREE].bundle.snapshot.anchor_date,NEW);
  const n=h.loads.length;await h.tick();assert.equal(h.loads.length,n,'成功读取才去重');
 }finally{await h.close()}
});
test('新目标读取失败保旧，间隔后恢复；满五分钟不再发GET',async()=>{
 const h=harness(OLD);try{await h.start();h.published=true;h.fail=true;await h.tick();assert.equal(h.view.entries[THREE].bundle.snapshot.anchor_date,OLD);
  const n=h.loads.length;h.fail=false;await h.tick();assert.equal(h.loads.length,n+2);assert.equal(h.view.entries[THREE].bundle.snapshot.anchor_date,NEW);
  const calls=h.calls.length;await h.tick(300000);assert.equal(h.calls.length,calls);
 }finally{await h.close()}
});
