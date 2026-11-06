/** Execute the actual component effect and periodic observer, with one transient activity handshake failure. */
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import ts from '../node_modules/typescript/lib/typescript.js';
const sourceRoot = new URL('../src/', import.meta.url);
function errorsFrom(name) {
 const mod={exports:{}};
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL(name,sourceRoot),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,
  {module:mod,exports:mod.exports,require:()=>({activityReason:code=>code}),Error,AbortController});
 return mod.exports;
}
const {IndexReadError}=errorsFrom('indexSeriesClient.ts'),{ActivityReadError}=errorsFrom('activityClient.ts');

const id='sse:000001:price', market='cn-a-turnover-sse-szse', timers=new Map(), slots=[], listeners=new Set();
let serial=0, hook=0, pendingRender=false, mounted=true, cleanup, effectDeps, nextEffect, view;
let activeLoads=0,maxActiveLoads=0;
let activityConnects=0, overviewCalls=0, activityLoads=0, failNext=true, deferred, refreshToken=0, lateClient, failStatus=false, statusError=false, identityMismatch=false, withdrawn=false;
const policy={daily_requests:80,daily_bytes:33554432,monthly_requests:500,monthly_bytes:536870912};
const expected={policy:{periodic:policy},startup_indices:[id]};
const legacy={expected:{config_id:'config',data_scope_id:'scope'},instance:'instance',closed:false};
const status={revision:1,state:'idle',reason:null,server_day:'2026-10-30',market_anchor_date:'2026-10-30',next_check_at:'2026-10-31T07:00:00+08:00',resume_at:null,daily:{requests:12,bytes:10616832},monthly:{requests:12,bytes:10616832},reserved:{requests:0,bytes:0},warning:false};
const snapshot={snapshot_id:'price',window:{anchor_date:'2026-10-30'}};
class Price { expected=expected; instance='instance'; closed=false;static async connect(){return new Price()};async current(){return snapshot};async calculations(){return {}};async overviewStatus(){overviewCalls++;if(identityMismatch){this.closed=true;throw new IndexReadError('identity mismatch','connection_context_mismatch',409)}if(statusError)throw new IndexReadError('暂时无法核验，保留已保存数据','index_series_invalid',409);if(failStatus){failStatus=false;throw TypeError('one anchor GET failure')}return status};async status(){return {stage:'completed',snapshot_id:'price'}};close(){this.closed=true} }
class Activity { closed=false;marketAnchor='2026-10-30';static async connect(){activityConnects++;if(failNext){failNext=false;throw TypeError('one transient handshake failure')}if(deferred)return await deferred;return new Activity()};async load(target){activityLoads++;activeLoads++;maxActiveLoads=Math.max(maxActiveLoads,activeLoads);try{await Promise.resolve();if(withdrawn&&target===id)throw new ActivityReadError('source_withdrawn');return {snapshot:{activity_id:'activity'}}}finally{activeLoads--}};async currentVersion(target){if(withdrawn&&target===id)throw new ActivityReadError('source_withdrawn');return 'activity'};close(){this.closed=true} }
const drain=async()=>{for(let i=0;i<150;i++)await Promise.resolve()};
const schedule=()=>{if(pendingRender||!mounted)return;pendingRender=true;queueMicrotask(()=>{pendingRender=false;if(mounted)render()})};
const document={hidden:false,addEventListener:(_n,fn)=>listeners.add(fn),removeEventListener:(_n,fn)=>listeners.delete(fn)};
const context=vm.createContext({module:{exports:{}},exports:{},Map,Set,Promise,AbortController,Error,TypeError,DOMException,Date,document,
 setTimeout:fn=>{const k=++serial;timers.set(k,fn);return k},clearTimeout:k=>timers.delete(k),
 require:name=>name==='./indexSeriesTypes'?{OVERVIEW_INDICES:[{id,name:'上证指数'}]}:{MARKET:market,LEGACY_MARKET:"cn-a-turnover",isMarket:id=>id===market||id==="cn-a-turnover"},
 useState:initial=>{const n=hook++;if(!(n in slots))slots[n]=initial;return [slots[n],value=>{const next=typeof value==='function'?value(slots[n]):value;if(!Object.is(next,slots[n])){slots[n]=next;schedule()}}]},
 useRef:initial=>{const n=hook++;return slots[n]??={current:initial}},useEffect:(effect,deps)=>{if(!effectDeps||deps.some((x,i)=>!Object.is(x,effectDeps[i]))){effectDeps=deps;nextEffect=effect}},
 IndexSeriesClient:Price,IndexReadError,ActivityClient:Activity,ActivityReadError,
 indexConnectionDescriptor:async()=>expected,activityConnectionDescriptor:async()=>({}),activityGate:()=>null,
 createStartupPriceObservation:()=>({nextCheckAt:0,deadline:300000}),OVERVIEW_INDICES:[{id,name:'上证指数'}],MARKET:market,LEGACY_MARKET:"cn-a-turnover",isMarket:id=>id===market||id==="cn-a-turnover",DEFAULT_MA:[5,10,20,30,250],errorText:error=>error.message});
const compile=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
context.exports=context.module.exports;
vm.runInContext(compile(readFileSync(new URL('periodicUpdates.ts',sourceRoot),'utf8')),context);Object.assign(context,context.module.exports);
const source=readFileSync(new URL('ProductionOverview.tsx',sourceRoot),'utf8');const begin=source.indexOf('export function ProductionOverview('),end=source.indexOf('  const trends = useMemo');
vm.runInContext(compile(source.slice(begin,end)+'\nreturn {rows,activityState,startupNotice};\n}'),context);
function render(){hook=0;view=context.module.exports.ProductionOverview({connectionClient:legacy,refreshToken});if(nextEffect){const effect=nextEffect;nextEffect=undefined;cleanup?.();cleanup=effect()}}
const report={scope:'actual effect + actual observer; mocked clients; no browser or network'};
try {
 render();await drain();assert.equal(activityConnects,1,'no immediate handshake retry');
 for(let i=0;i<20;i++){for(const [k,fn] of [...timers]){timers.delete(k);fn()}await drain()}
 assert.equal(activityConnects,2);assert.ok(activityLoads>0);assert.equal(Object.keys(view.activityState.entries).length,3);
 failStatus=true;refreshToken++;render();await drain();
 assert.equal(activityConnects,3);assert.equal(view.activityState.error,undefined,'successful load clears transient anchor error');assert.ok(view.activityState.descriptor);
 const before409=view.activityState.entries[id].bundle;statusError=true;refreshToken++;render();await drain();
 assert.equal(view.activityState.entries[id].bundle,before409,'actual IndexReadError409 keeps old bundle');assert.match(view.activityState.error,/暂时无法核验/);
 for(const [k,fn] of [...timers]){timers.delete(k);fn()}await drain();
 assert.equal(view.activityState.entries[id].bundle,before409,'old view survives full observation interval');
 statusError=false;for(const [k,fn] of [...timers]){timers.delete(k);fn()}await drain();
 assert.ok(view.activityState.entries[id].bundle);assert.equal(view.activityState.error,undefined);
 identityMismatch=true;refreshToken++;render();await drain();assert.equal(Object.keys(view.activityState.entries).length,0,'identity failure clears old view');
 const stoppedCalls=overviewCalls;for(const [k,fn] of [...timers]){timers.delete(k);fn()}await drain();assert.equal(overviewCalls,stoppedCalls,'closed identity cannot be reacquired automatically');
 identityMismatch=false;refreshToken++;render();await drain();assert.ok(view.activityState.entries[id].bundle);
 withdrawn=true;refreshToken++;render();await drain();assert.equal(view.activityState.entries[id].bundle,undefined,'withdrawal cannot retain prior bundle');
 withdrawn=false;refreshToken++;render();await drain();assert.ok(view.activityState.entries[id].bundle);
 const previous=view.activityState.entries[id].bundle;failNext=true;const connectBeforeFailure=activityConnects;refreshToken++;render();await drain();
 assert.equal(activityConnects,connectBeforeFailure+1);assert.equal(view.activityState.entries[id].bundle,previous,'same owner retains verified bundle after handshake failure');
 let resolve;deferred=new Promise(r=>{resolve=r});
 for(const [k,fn] of [...timers]){timers.delete(k);fn()}await drain();
 assert.equal(activityConnects,connectBeforeFailure+2);mounted=false;cleanup();const old=view;lateClient=new Activity();resolve(lateClient);await drain();
 assert.equal(lateClient.closed,true,'late connected client closed after cancellation');assert.equal(view,old);
 assert.equal(maxActiveLoads,1,'full-window activity loads must not pile up server validation requests');
 Object.assign(report,{activityConnects,overviewCalls,activityLoads,maxActiveLoads,checks:['transient handshake recovers after interval','same owner failure keeps prior bundle','actual IndexReadError409 keeps view through interval and recovery','identity mismatch closes and clears','source withdrawal clears previous bundle','cancel closes late client without view write'],passed:true});
} finally {mounted=false;cleanup?.();await drain();Object.assign(report,{timers_remaining:timers.size,listeners_remaining:listeners.size});assert.equal(timers.size,0);assert.equal(listeners.size,0)}
console.log(JSON.stringify(report,null,2));
