/** 可控计时验证长期观察、取消、失败保旧与版本去重；不调用网络。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const id='sse:000001:price', market='cn-a-turnover-sse-szse', three='cn-a-turnover';
function setup(){
 const module={exports:{}},timers=new Map(),listeners=new Set();let serial=0;
 const document={hidden:false,addEventListener:(_n,fn)=>listeners.add(fn),removeEventListener:(_n,fn)=>listeners.delete(fn)};
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/periodicUpdates.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,
 {module,exports:module.exports,require:name=>name==='./indexSeriesTypes'?{OVERVIEW_INDICES:[{id}]}:{MARKET:market,LEGACY_MARKET:three,isMarket:x=>[market,three].includes(x)},document,Date,Map,Set,Promise,
 setTimeout:fn=>{const n=++serial;timers.set(n,fn);return n},clearTimeout:n=>timers.delete(n)});
 const controller=new AbortController(),notices=[],loads=[],errors=[];
 let state={revision:1,state:'idle',reason:null,server_day:'2026-10-30',market_anchor_date:'2026-10-30',next_check_at:'2026-10-31T07:00:00+08:00',resume_at:null,daily:{requests:12,bytes:10616832},monthly:{requests:12,bytes:10616832},reserved:{requests:0,bytes:0},warning:false};
 let version='new',fail=false,calls=0;
 const price={closed:false,expected:{policy:{periodic:{daily_requests:80,daily_bytes:33554432,monthly_requests:500,monthly_bytes:536870912}}},overviewStatus:async()=>{calls++;return state},status:async()=>({stage:'completed',snapshot_id:version})};
 const prices=new Map([[id,'old']]),quantities=new Map();
 const drain=async()=>{for(let i=0;i<40;i++)await Promise.resolve()};
 return {price,prices,quantities,controller,notices,loads,errors,timers,document,listeners,drain,get calls(){return calls},set fail(v){fail=v},set state(v){state={...state,...v}},
 start:(activity,loadActivity=async()=>assert.fail('no activity'),demand)=>module.exports.watchPeriodicUpdates(price,activity,controller.signal,prices,quantities,async()=>{loads.push(version);if(fail)throw Error('offline');return version},loadActivity,x=>notices.push(x),(...x)=>errors.push(x),undefined,demand),
 tick:async()=>{for(const [n,fn] of [...timers]){timers.delete(n);fn()}await drain()}};
}
test('读取成功才去重，失败后按间隔再读；跨五分钟继续观察',async()=>{const x=setup();x.fail=true;const run=x.start();await x.drain();assert.equal(x.prices.get(id),'old');assert.equal(x.loads.length,1);x.fail=false;await x.tick();assert.equal(x.prices.get(id),'new');for(let i=0;i<12;i++)await x.tick();assert.equal(x.loads.length,2);assert.ok(x.calls>10);x.controller.abort();await run;assert.equal(x.timers.size,0);assert.equal(x.listeners.size,0)});
test('隐藏暂停，前台恢复；状态版本回退不触发读取',async()=>{const x=setup();x.document.hidden=true;const run=x.start();await x.drain();assert.equal(x.calls,0);x.document.hidden=false;for(const fn of [...x.listeners])fn();await x.drain();assert.equal(x.calls,1);x.state={revision:0};await x.tick();assert.equal(x.loads.length,1);x.controller.abort();await run});
test('取消后迟到状态不能变更视图，80%和月额度停止原因可见',async()=>{const x=setup();x.state={state:'blocked',reason:'periodic_monthly_exhausted',warning:true,resume_at:'2026-11-01T00:00:00+08:00'};const run=x.start();await x.drain();assert.match(x.notices[0],/80%/);assert.match(x.notices[0],/本月额度不足/);assert.match(x.notices[0],/预计额度恢复/);x.controller.abort();await run;
 const y=setup();let resolve;y.price.overviewStatus=()=>new Promise(r=>resolve=r);const late=y.start();await y.drain();y.controller.abort();resolve({revision:1});await late;assert.equal(y.loads.length,0);assert.equal(y.notices.length,0)});

test('仅观察可见三市的已发布锚点，隐藏两市变化不读取；空锚点不猜测新日期',async()=>{
 const x=setup(),targets=[];x.state={market_anchors:{sse_szse:'2026-10-30',sse_szse_bse:'2026-10-29'}};
 const activity={closed:false,currentVersion:async(s,t)=>{targets.push([s,t]);return s===id?undefined:s+t}};
 const loads=[];const run=x.start(activity,async(s,t)=>{loads.push([s,t]);return s+t});await x.drain();
 assert.deepEqual(loads,[[three,'2026-10-29']]);assert.ok(!targets.some(([s])=>s===market));
 x.state={revision:2,market_anchors:{sse_szse:'2026-10-31',sse_szse_bse:'2026-10-29'}};await x.tick();
 assert.deepEqual(loads.at(-1),[three,'2026-10-29']);assert.equal(loads.length,1);assert.ok(!targets.some(([s])=>s===market));
 x.state={revision:3,market_anchors:{sse_szse:'2026-10-31',sse_szse_bse:null}};const before=targets.length;await x.tick();
 assert.ok(!targets.slice(before).some(([s])=>s===three));assert.equal(x.quantities.get(three),three+'2026-10-29');
 x.controller.abort();await run;
});

test('量额需求随选择变化，未选不读；重新纳入仍检查独立量额修订，价格观察保持',async()=>{
 const x=setup(),queried=[],loaded=[];let selected=[three],version='a1';
 const activity={closed:false,currentVersion:async(s,t)=>{queried.push([s,t]);return s+version}};
 const run=x.start(activity,async(s,t)=>{loaded.push([s,t,version]);return s+version},()=>selected);
 try{await x.drain();assert.deepEqual(queried.map(x=>x[0]),[three]);assert.equal(x.prices.get(id),'new');
  selected=[id,three];await x.tick();assert.equal(loaded.filter(x=>x[0]===id).length,1);
  selected=[three];version='a2';const before=queried.length;await x.tick();assert.ok(!queried.slice(before).some(x=>x[0]===id));
  selected=[id,three];await x.tick();assert.equal(loaded.filter(x=>x[0]===id).length,2);assert.equal(x.quantities.get(id),id+'a2');
 }finally{x.controller.abort();await run;assert.equal(x.timers.size,0);assert.equal(x.listeners.size,0)}
});
