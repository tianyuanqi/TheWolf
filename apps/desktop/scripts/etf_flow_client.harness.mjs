/** 真实隔离HTTP输出交给正式Client；坏响应反例及写请求不重试。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import {webcrypto} from 'node:crypto';
import ts from 'typescript';
const app=path.resolve(import.meta.dirname,'..'),req=createRequire(path.join(app,'src/etfFlowClient.ts'));
const f=JSON.parse(readFileSync(process.env.WOLF_ETF_CLIENT_FIXTURE,'utf8'));
const signal=()=>new AbortController().signal;
const json=value=>JSON.parse(JSON.stringify(value));
const identity=operation=>({operation:'etf.flow.update',request_id:operation.request_id,instance_id:operation.instance_id,
  config_id:operation.config_id,parameters:{plan_id:operation.plan_id,expected_snapshot_id:operation.expected_snapshot_id}});
function harness(){const queue=[],calls=[],cache={};
  function load(name){if(cache[name])return cache[name];const module={exports:{}};
    const source=ts.transpileModule(readFileSync(path.join(app,'src',name+'.ts'),'utf8'),{
      compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
    vm.runInNewContext(source,{module,exports:module.exports,URL,URLSearchParams,AbortController,AbortSignal,DOMException,
      structuredClone,crypto:webcrypto,TextEncoder,fetch:async(url,options)=>{calls.push({url,options});assert.ok(queue.length,'没有预定响应');return queue.shift()();},
      require:r=>r.startsWith('./')?load(r.slice(2)):req(r)});return cache[name]=module.exports;
  }
  const m=load('etfFlowClient');
  const response=(body,status=200,config=f.descriptor.config_id)=>new Response(JSON.stringify(body),{status,headers:{
    'Content-Type':'application/json','X-Wolf-Instance':f.ready.instance_id,'X-Wolf-Config':config}});
  return {m,queue,calls,response,connect:async()=>{queue.push(()=>response(f.ready));return m.EtfFlowClient.connect(
    m.parseEtfDescriptor(structuredClone(f.descriptor),f.legacy),f.ready.instance_id,signal());}};
}
const expected={snapshot:f.view.snapshot_id,mode:'current',period:60};
test('实际HTTP当时无记录与当前重算输出通过，C2保留数据不足',()=>{
  const h=harness();const view=h.m.parseEtfView(structuredClone(f.view),expected);
  const original=h.m.parseEtfView(structuredClone(f.original),{...expected,mode:'original'});
  assert.equal(view.summary.evaluation.c2.state,'insufficient');assert.equal(view.summary.evaluation.amount,'40');
  assert.equal(original.summary.evaluation,null);assert.equal(original.data_status.input_basis,'posthoc_inputs');
});
test('负数计数、伪零C2、混入未来来源或错日都拒绝',()=>{
  const h=harness();
  for(const mutate of [v=>v.summary.evaluation.valid_count=-1,v=>v.summary.evaluation.c2.positive_ratio='0',
    v=>v.members[0].admission.required_days=320,v=>v.members[0].metrics.date='2026-11-03',
    v=>v.sources[0].retrieved_at='2026-11-06T12:00:00+08:00',v=>v.sources[0].url='https://example.com/untrusted',
    v=>v.summary.evaluation.rule_version='unrelated-rule',v=>v.series[1].date=v.series[0].date]){
    const value=structuredClone(f.view);mutate(value);assert.throws(()=>h.m.parseEtfView(value,expected));
  }
});
test('v2调整依据和完整截止严格校验，旧结构不兜底',()=>{
  const h=harness();
  for(const mutate of [v=>v.schema_version='etf-flow-view-v1',v=>delete v.data_status.complete_amount_through,
    v=>v.data_status.complete_amount_through='2026-11-05',v=>delete v.members[0].series[0].adjustment_detail,
    v=>v.members[0].series.at(-1).adjustment_detail.source_ids=[],
    v=>v.members[0].series.at(-1).adjustment_detail.source_ids=['a'.repeat(64)],
    v=>v.members[0].series.at(-1).adjustment_detail.confirmed_at='2026-11-06T12:00:00+08:00',
    v=>v.members[0].series.at(-1).adjustment_detail.factor='2',
    v=>v.members[0].series.at(-1).adjustment_detail.end='2026-11-03',
    v=>v.members[0].series.at(-1).metrics.adjustment=true]){
    const value=structuredClone(f.view);mutate(value);assert.throws(()=>h.m.parseEtfView(value,expected));
  }
  const original=structuredClone(f.original);original.data_status.complete_amount_through=original.end;
  assert.throws(()=>h.m.parseEtfView(original,{...expected,mode:'original'}));
  const descriptor={...f.descriptor,contract_sha256:'a'.repeat(64)};
  assert.throws(()=>h.m.parseEtfDescriptor(descriptor,f.legacy));
});
test('当前与固定版本使用真实接口路径及绑定头，全程不写',async()=>{
  const h=harness(),c=await h.connect();h.queue.push(()=>h.response(f.current));await c.current(signal());
  h.queue.push(()=>h.response(f.view));await c.view(f.view.snapshot_id,'current',60,signal());
  assert.equal(h.calls.length,3);assert.ok(h.calls[2].url.endsWith(f.view.snapshot_id+'?mode=current&period=60'));
  assert.ok(h.calls.every(x=>!x.options.body && x.options.credentials==='omit' && x.options.redirect==='error'));
  assert.equal(h.calls[2].options.headers['X-Wolf-Expected-Config'],f.descriptor.config_id);
});
test('ETF成功视图按固定版本缓存；失败、取消和clear后的迟到结果不入缓存',async()=>{
  const h=harness(),c=await h.connect();h.queue.push(()=>h.response(f.view));
  const first=await c.view(f.view.snapshot_id,'current',60,signal());const before=h.calls.length;
  assert.equal(await c.view(f.view.snapshot_id,'current',60,signal()),first);assert.equal(h.calls.length,before);
  c.clearViews();h.queue.push(()=>{throw Error('synthetic unavailable')});await assert.rejects(c.view(f.view.snapshot_id,'current',60,signal()));
  h.queue.push(()=>h.response(f.view));await c.view(f.view.snapshot_id,'current',60,signal());assert.equal(h.calls.length,before+2);
  c.clearViews();let release;const gate=new Promise(resolve=>release=resolve);
  h.queue.push(()=>({ok:true,status:200,headers:h.response({}).headers,json:async()=>{await gate;return f.view}}));
  const late=c.view(f.view.snapshot_id,'current',60,signal());c.clearViews();release();await late;
  h.queue.push(()=>h.response(f.view));await c.view(f.view.snapshot_id,'current',60,signal());assert.equal(h.calls.length,before+4);
  const abort=new AbortController();abort.abort();await assert.rejects(c.view(f.view.snapshot_id,'current',60,abort.signal));
  c.close();await assert.rejects(c.view(f.view.snapshot_id,'current',60,signal()));
});
test('真实原请求结果摘要核验；错误实例或参数不得认领',async()=>{
  const h=harness(),c=await h.connect(),id=identity(f.operation);
  h.queue.push(()=>h.response(f.operation));assert.equal((await c.operation(id,signal())).snapshot_id,f.operation.snapshot_id);
  for(const change of [{operation_key:'a'.repeat(64)},{instance_id:'00000000-0000-4000-8000-000000000099'},
    {expected_snapshot_id:'a'.repeat(64)}]){
    h.queue.push(()=>h.response({...f.operation,...change}));await assert.rejects(c.operation(id,signal()));
  }
});
test('恢复须先本次GET核验，原POST不换请求，终态不保留恢复权限',async()=>{
  const h=harness(),c=await h.connect(),id=identity(f.recovery);
  await assert.rejects(c.startUpdate(id,signal(),true));assert.equal(h.calls.length,1);
  h.queue.push(()=>h.response(f.recovery));const pending=await c.operation(id,signal());assert.equal(pending.recovery_required,true);
  h.queue.push(()=>h.response(f.recovered));assert.equal((await c.startUpdate(id,signal(),true)).state,'interrupted');
  assert.deepEqual(JSON.parse(h.calls.at(-1).options.body),id.parameters);
  assert.equal(h.calls.at(-1).options.headers['X-Wolf-Request-Id'],id.request_id);
  await assert.rejects(c.startUpdate(id,signal(),true));assert.equal(h.calls.filter(x=>x.options.method==='POST').length,1);
});
test('POST断连不自动重发，连接改变及迟到正文均拒绝',async()=>{
  const h=harness(),c=await h.connect();h.queue.push(()=>{throw Error('simulated lost response');});
  await assert.rejects(c.startUpdate(identity(f.operation),signal()));assert.equal(h.calls.filter(x=>x.options.method==='POST').length,1);
  h.queue.push(()=>h.response(f.current,200,'a'.repeat(64)));await assert.rejects(c.current(signal()));assert.equal(c.closed,true);
  const late=harness(),lc=await late.connect(),controller=new AbortController();
  late.queue.push(()=>({ok:true,status:200,headers:late.response({}).headers,json:async()=>{controller.abort();return f.current;}}));
  await assert.rejects(lc.current(controller.signal));
});
