/** 实际B输出作为输入；反例针对展示边界，不在测试镜像金融公式。 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const app=path.resolve(import.meta.dirname,'..');
const require=createRequire(path.join(app,'src/activityClient.ts'));
const fixture=JSON.parse(readFileSync(process.env.WOLF_ACTIVITY_FIXTURE,'utf8'));
const id='sse:000001:price', bundle=fixture.bundles[id], instance='00000000-0000-4000-8000-000000000000';
function harness() {
  const queue=[],calls=[],cache={};
  function load(name) {
    if(cache[name])return cache[name];
    const module={exports:{}};
    const source=ts.transpileModule(readFileSync(path.join(app,'src',name+'.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
    vm.runInNewContext(source,{module,exports:module.exports,URL,AbortController,AbortSignal,DOMException,structuredClone,
      fetch:async(url,options)=>{calls.push({url,options});assert.ok(queue.length,'无预定响应');return queue.shift()();},
      require:request=>request.startsWith('./')?load(request.slice(2)):require(request)});
    return cache[name]=module.exports;
  }
  const types=load('activityTypes'),client=load('activityClient');
  const response=(value,status=200,config=fixture.descriptor.config_id)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','X-Wolf-Config':config,'X-Wolf-Instance':instance}});
  async function connect(expected=fixture.descriptor) {
    const {endpoint,...ready}=expected; queue.push(()=>response({...ready,status:'ready',instance_id:instance,market_anchor_date:fixture.ready?.market_anchor_date ?? bundle.snapshot.anchor_date}));
    return client.ActivityClient.connect(client.parseActivityDescriptor(expected,fixture.price_descriptor),instance,new AbortController().signal);
  }
  return {types,client,response,connect,queue,calls};
}
test('十进制显示不丢精度，真零和缺失区分',()=>{
  const {types}=harness();
  for(const [value,field,result] of [['123000000.00','amount','1.23'],['0','volume','0'],[null,'amount','暂无数据'],['1234567890123456789012345.1234','amount','12,345,678,901,234,567.890123451234'],['10000.0001','volume','1.00000001']])assert.equal(types.activityText(value,field),result);
});
test('生产门禁、撤回优先，无current请求且无写入',async()=>{
  for(const mutate of [v=>v.policy.sources.forEach(r=>r.admitted=false),v=>v.blocked_series=[{series_id:id,evidence_id:'a'.repeat(64),reason:'source_withdrawn'}]]){
    const h=harness(),expected=structuredClone(fixture.descriptor);mutate(expected);const client=await h.connect(expected);
    await assert.rejects(client.load(id,bundle.snapshot.anchor_date,bundle.price,undefined,new AbortController().signal));assert.equal(h.calls.length,1);
  }
});
test('真实服务四指数和全市场输出均通过归属检查',()=>{
  const {types}=harness();
  for(const [sid,b] of Object.entries(fixture.bundles)){
    const snapshot=types.parseActivitySnapshot(b.snapshot,sid,b.current.activity_id,b.current.anchor_date,b.price??undefined);
    types.parseActivityCalculations(b.calculations,snapshot);
  }
});
test('current→固定快照→计算，固定P/A查询且只读',async()=>{
  const h=harness(),client=await h.connect();
  for(const value of [bundle.current,bundle.snapshot,bundle.calculations])h.queue.push(()=>h.response(value));
  const value=await client.load(id,bundle.snapshot.anchor_date,bundle.price,undefined,new AbortController().signal);
  assert.equal(value.snapshot.activity_id,bundle.current.activity_id);
  assert.equal(h.calls.length,4);assert.ok(h.calls[1].url.endsWith('price_snapshot_id='+bundle.price.snapshot_id));
  assert.ok(h.calls.every(c=>!c.options.body && !c.options.method && c.options.credentials==='omit' && c.options.redirect==='error'));
});
test('不接受外层/嵌套引用、单位、参数、缺失、周期和可用性错配',()=>{
  const {types}=harness();
  for(const change of [v=>v.activity_id='0'.repeat(64),v=>v.formula_version='market-activity-calculations-sse-szse-v1',v=>v.series[0].rows[0].total.input_ref.price_snapshot_id='0'.repeat(64),
    v=>v.series[0].rows[0].total.unit='手',v=>v.series[0].rows[0].ma[0].parameters.period='99',
    v=>v.series[0].rows[0].total.reason='missing_date',v=>v.series[0].rows[0].total.value='NaN',
    v=>v.series[0].rows[0].total.complete=false,v=>v.series[0].rows[1].end=v.series[0].rows[0].end,
    v=>v.series[0].ma_availability[0].available=false]){
      const value=structuredClone(bundle.calculations);change(value);assert.throws(()=>types.parseActivityCalculations(value,bundle.snapshot));
    }
  for(const change of [v=>v.price_snapshot_id='0'.repeat(64),v=>v.rows[0].volume.unit='手',v=>v.observations[0].activity_id='0'.repeat(64)]){
    const value=structuredClone(bundle.snapshot);change(value);assert.throws(()=>types.parseActivitySnapshot(value,id,bundle.current.activity_id,bundle.snapshot.anchor_date,bundle.price));
  }
});
test('current错配、固定响应错配、连接失配及迟到正文均拒绝',async()=>{
  for(const mutate of [v=>v.price_snapshot_id='0'.repeat(64),v=>v.anchor_date='2025-01-01',v=>v.series_id='cn-a-turnover']){
    const h=harness(),client=await h.connect(),current=structuredClone(bundle.current);mutate(current);h.queue.push(()=>h.response(current));
    await assert.rejects(client.load(id,bundle.snapshot.anchor_date,bundle.price,undefined,new AbortController().signal));assert.equal(h.calls.length,2);
  }
  const h=harness(),client=await h.connect();
  h.queue.push(()=>h.response(bundle.current,200,'0'.repeat(64)));
  await assert.rejects(client.load(id,bundle.snapshot.anchor_date,bundle.price,undefined,new AbortController().signal),/身份改变/);
  const late=harness(),c=await late.connect(),controller=new AbortController();let resolve;
  late.queue.push(()=>({ok:true,headers:new Headers({'Content-Type':'application/json','X-Wolf-Config':fixture.descriptor.config_id,'X-Wolf-Instance':instance}),json:()=>new Promise(done=>resolve=done)}));
  const pending=c.load(id,bundle.snapshot.anchor_date,bundle.price,undefined,controller.signal);
  await new Promise(done=>setImmediate(done));controller.abort();resolve(bundle.current);await assert.rejects(pending,/取消/);
});

test('固定源精度及单一市场准入缺口不能被数值响应掩盖',()=>{
  const {types}=harness();
  for(const b of Object.values(fixture.bundles)) types.checkActivityPolicy(b.snapshot,fixture.descriptor);
  for(const mutate of [v=>v.rows[0].amount.source_quantum='0.001',v=>v.rows[0].volume.raw_unit='手',v=>v.sources[0].source='other']){
    const value=structuredClone(bundle.snapshot);mutate(value);assert.throws(()=>types.checkActivityPolicy(value,fixture.descriptor));
  }
  const descriptor=structuredClone(fixture.descriptor);descriptor.policy.sources.find(r=>r.series==='bse').admitted=false;
  assert.match(types.activityGate(descriptor,'cn-a-turnover'),/未准入/);
  const market=fixture.bundles['cn-a-turnover'], invalid=structuredClone(market.calculations);
  const missing=invalid.series[0].rows.find(row=>row.total.value===null);missing.total.value='300000000.00';missing.total.reason=null;
  assert.throws(()=>types.parseActivityCalculations(invalid,market.snapshot),/缺日或缺市场/);
});

test('启动集合须唯一且属于启写，ready日期须为真实自然日',async()=>{
  for(const mutate of [v=>{v.startup_series=[id,id];v.write_series=[id];},v=>{v.startup_series=[id];v.write_series=[];}]){
    const h=harness(),bad=structuredClone(fixture.descriptor);mutate(bad);
    assert.throws(()=>h.client.parseActivityDescriptor(bad,fixture.price_descriptor));
  }
  for(const day of ['2026-02-30',undefined]){
    const h=harness(),{endpoint,...ready}=fixture.descriptor;
    h.queue.push(()=>h.response({...ready,status:'ready',instance_id:instance,market_anchor_date:day}));
    await assert.rejects(h.client.ActivityClient.connect(fixture.descriptor,instance,new AbortController().signal));
  }
});

test('两市与三市公式的顶层版本也不能互换',()=>{
  const market=fixture.bundles['cn-a-turnover-sse-szse'];
  if(!market)return; // 旧P3夹具仍可单独复用；S2夹具覆盖此分支。
  const {types}=harness(),wrong=structuredClone(market.calculations);
  wrong.formula_version='market-activity-calculations-v1';
  assert.throws(()=>types.parseActivityCalculations(wrong,market.snapshot));
});
