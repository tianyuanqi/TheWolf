/** 启动观察只读、发布后重读、失败保旧、取消与有界性；不采集来源。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const ids=['sse:000001:price','szse:399001:price','szse:399006:price','sse:000688:price'];
function setup(configured=ids){
 let clock=0,versions=0;const timers=new Map(),notices=[],calls=[];let serial=0;
 const module={exports:{}};
 vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/startupPrices.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,
 {module,exports:module.exports,require:name=>{assert.equal(name,'./indexSeriesTypes');return {OVERVIEW_INDICES:ids.map((id,i)=>({id,name:'指数'+i}))};},Date:{now:()=>clock},Map,Set,Promise,
 setTimeout:fn=>{const id=++serial;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id)});
 const controller=new AbortController();let reply=()=>({stage:'completed',snapshot_id:'one',observation_id:'first',result:'business_changed'});
 const client={expected:{startup_indices:configured},closed:false,status:async id=>{calls.push(id);return reply(id);},startUpdate:()=>assert.fail('不能POST'),activity:()=>assert.fail('不能读取量额')};
 const drain=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
 return {client,controller,notices,calls,timers,drain,get versions(){return versions;},set reply(value){reply=value;},
 observation:()=>module.exports.createStartupPriceObservation(),
 start:(initial=new Map(),observation)=>module.exports.watchStartupPrices(client,controller.signal,()=>versions++,x=>notices.push(x),initial,observation),
 tick:async(ms=3000)=>{clock+=ms;for(const [id,fn] of [...timers]){timers.delete(id);fn();}await drain();}};
}
test('无启动授权不轮询、不采集，清楚说明未启用',async()=>{const x=setup([]);await x.start();assert.equal(x.calls.length,0);assert.equal(x.versions,0);assert.match(x.notices[0],/未启用/);});
test('仅观察服务端配置系列；新快照刷新，只有获取记录变化不重复刷新',async()=>{const x=setup([ids[1]]),run=x.start();await x.drain();assert.deepEqual(x.calls,[ids[1]]);assert.equal(x.versions,1);await x.tick();assert.equal(x.versions,1);x.reply=()=>({stage:'completed',snapshot_id:'two',observation_id:'second'});await x.tick();assert.equal(x.versions,2);x.reply=()=>({stage:'completed',snapshot_id:'two',observation_id:'third'});await x.tick();assert.equal(x.versions,2);x.controller.abort();await run;assert.equal(x.timers.size,0);});
test('采集中与失败不冒称发布，不触发替换旧版本',async()=>{const x=setup([ids[0]]);x.reply=()=>({stage:'fetching_csindex',trigger:'startup',snapshot_id:null});const run=x.start();await x.drain();assert.equal(x.versions,0);assert.match(x.notices.at(-1),/正在自动更新/);x.reply=()=>({stage:'failed',snapshot_id:null});await x.tick();assert.equal(x.versions,0);assert.match(x.notices.at(-1),/更新未成功/);x.reply=()=>{throw Error('offline')};await x.tick();assert.match(x.notices.at(-1),/暂时无法读取/);x.controller.abort();await run;});
test('取消后的迟到响应不能刷新页面或覆盖新连接提示',async()=>{const x=setup([ids[0]]);let resolve;x.reply=()=>new Promise(r=>resolve=r);const run=x.start();await x.drain();x.controller.abort();resolve({stage:'completed',snapshot_id:'late'});await run;assert.equal(x.versions,0);assert.equal(x.notices.length,0);});
test('身份校验关闭client后的响应不采纳',async()=>{const x=setup([ids[0]]);x.reply=()=>{x.client.closed=true;return {stage:'completed',snapshot_id:'wrong-instance'}};await x.start();assert.equal(x.versions,0);assert.equal(x.notices.length,0);});
test('五分钟后结束观察，不声称更新已完成或取消',async()=>{const x=setup([ids[0]]);const run=x.start();await x.drain();await x.tick(300000);await run;assert.match(x.notices.at(-1),/不代表服务端更新已停止/);assert.equal(x.calls.length,1);assert.equal(x.timers.size,0);});

test('首屏已加载版本不触发重复刷新，后续发布才通知',async()=>{const x=setup([ids[0]]);const run=x.start(new Map([[ids[0],'one']]));await x.drain();assert.equal(x.versions,0);x.reply=()=>({stage:'completed',snapshot_id:'new',observation_id:'next'});await x.tick();assert.equal(x.versions,1);x.controller.abort();await run;});

test('页面重读失败后按间隔再通知；成功读取才去重，同连接期限不延长',async()=>{
 const x=setup([ids[0]]),state=x.observation();let run=x.start(new Map(),state);await x.drain();assert.equal(x.versions,1);
 x.client.closed=true;await x.tick(100);await run;x.client.closed=false;
 run=x.start(new Map([[ids[0],'old']]),state);await x.drain();assert.equal(x.versions,1);assert.equal(x.calls.length,1);
 await x.tick(2900);assert.equal(x.versions,2);assert.equal(x.calls.length,2);
 x.client.closed=true;await x.tick(100);await run;x.client.closed=false;
 run=x.start(new Map([[ids[0],'one']]),state);await x.tick(2900);assert.equal(x.versions,2);assert.equal(x.calls.length,3);
 await x.tick(294000);await run;assert.equal(state.deadline,300000);assert.equal(x.calls.length,3);assert.match(x.notices.at(-1),/已暂停/);assert.equal(x.timers.size,0);
});
