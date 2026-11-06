/** 量额启动观察：只读、成功后去重、失败恢复、迟到取消及共享限时。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const id='cn-a-turnover-sse-szse';
function harness(enabled=true) {
  let clock=0,serial=0,reply=async()=> 'new',loader=async()=> 'new';
  const timers=new Map(),calls=[],loads=[],errors=[],notices=[],module={exports:{}};
  const code=ts.transpileModule(readFileSync(new URL('../src/startupActivity.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{module,exports:module.exports,require:()=>({createStartupPriceObservation:()=>({nextCheckAt:0,deadline:300000})}),Date:{now:()=>clock},Map,Promise,
    setTimeout:fn=>{const n=++serial;timers.set(n,fn);return n;},clearTimeout:n=>timers.delete(n)});
  const signal=new AbortController(),state={nextCheckAt:0,deadline:300000};
  const client={expected:{startup_series:enabled?[id]:[]},closed:false,currentVersion:async(...args)=>{calls.push(args.slice(0,2));return reply();}};
  const drain=async()=>{for(let n=0;n<15;n++)await Promise.resolve();};
  return {client,signal,state,calls,loads,errors,notices,timers,drain,set reply(fn){reply=fn;},set loader(fn){loader=fn;},
    set clock(value){clock=value;},
    run:(initial=new Map(),targets=new Map([[id,'2026-10-31']]))=>module.exports.watchStartupActivity(client,targets,initial,signal.signal,async key=>{loads.push(key);return loader();},(...a)=>errors.push(a),s=>notices.push(s),state),
    tick:async(ms=3000)=>{clock+=ms;for(const [key,fn] of [...timers]){timers.delete(key);fn();}await drain();}};
}
test('空启动集合没有GET或加载',async()=>{const h=harness(false);await h.run();assert.equal(h.calls.length,0);assert.equal(h.loads.length,0);});
test('只查询冻结目标，同版本不重复读取，下一版本才加载',async()=>{const h=harness(),run=h.run();await h.drain();assert.deepEqual(h.calls,[[id,'2026-10-31']]);assert.equal(h.loads.length,1);await h.tick();assert.equal(h.loads.length,1);h.reply=async()=> 'next';h.loader=async()=> 'next';await h.tick();assert.equal(h.loads.length,2);h.signal.abort();await run;assert.equal(h.timers.size,0);});
test('失败不记成成功，三秒后恢复加载且期限不重置',async()=>{const h=harness();h.loader=async()=>{throw Error('transient');};const run=h.run();await h.drain();assert.equal(h.errors.length,1);h.loader=async()=> 'new';await h.tick();assert.equal(h.loads.length,2);await h.tick();assert.equal(h.loads.length,2);assert.equal(h.state.deadline,300000);h.signal.abort();await run;});
test('取消后迟到current不得加载',async()=>{const h=harness();let release;h.reply=()=>new Promise(r=>release=r);const run=h.run();await h.drain();h.signal.abort();release('late');await run;assert.equal(h.loads.length,0);});
test('服务身份改变关闭client不得采纳响应',async()=>{const h=harness();h.reply=async()=>{h.client.closed=true;return 'other-instance';};await h.run();assert.equal(h.loads.length,0);});
test('首屏已读版本不重读，五分钟后明确停止观察而非宣称更新成功',async()=>{const h=harness(),run=h.run(new Map([[id,'new']]));await h.drain();assert.equal(h.loads.length,0);await h.tick(300000);await run;assert.equal(h.calls.length,1);assert.match(h.notices.at(-1),/服务可能仍在执行/);assert.equal(h.timers.size,0);});

for(const version of [undefined,'late-new'])test(`首个GET跨期返回${version??'空'}，不得进入load或下一系列`,async()=>{
  const h=harness(),other='sse:000001:price';h.client.expected.startup_series.push(other);h.clock=299999;
  h.reply=async()=>{h.clock=300001;return version;};
  await h.run(new Map(),new Map([[id,'2026-10-31'],[other,'a'.repeat(64)]]));
  assert.equal(h.calls.length,1);assert.equal(h.loads.length,0);assert.equal(h.state.deadline,300000);
  assert.match(h.notices.at(-1),/自动跟进已暂停/);assert.equal(h.timers.size,0);
});
test('首个固定读取跨期完成，不再发下一系列GET',async()=>{
  const h=harness(),other='sse:000001:price';h.client.expected.startup_series.push(other);h.clock=299999;
  h.loader=async()=>{h.clock=300001;return 'new';};
  await h.run(new Map(),new Map([[id,'2026-10-31'],[other,'a'.repeat(64)]]));
  assert.equal(h.calls.length,1);assert.equal(h.loads.length,1);assert.equal(h.state.deadline,300000);
  assert.match(h.notices.at(-1),/自动跟进已暂停/);
});
