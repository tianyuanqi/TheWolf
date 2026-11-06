/** 核对公开操作记录边界；失败断言不依赖实现生成期望。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const scope={endpoint:'http://127.0.0.1:18880',data_scope_id:'a'.repeat(64),operation:'index.series.update',target:'sse:000001:price'};
const first={instance_id:'00000000-0000-4000-8000-000000000001',config_id:'b'.repeat(64),request_id:'request-A',operation:scope.operation,index_id:scope.target};
function load(){const data=new Map();let fail=false;const module={exports:{}};const storage={getItem:k=>data.get(k)??null,setItem:(k,v)=>{if(fail)throw Error('quota');data.set(k,v);},key:i=>[...data.keys()][i],get length(){return data.size;}};
 const source=ts.transpileModule(readFileSync(new URL('../src/operationSession.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(source,{module,exports:module.exports,sessionStorage:storage,URL,TextEncoder,location:{origin:'http://127.0.0.1:18881'}});
 return {m:module.exports,data,fail:()=>{fail=true;}};
}
const json=x=>JSON.parse(JSON.stringify(x));
test('首次无记录仍未接续，普通更新不得自动开放',()=>{const {m}=load();assert.equal(m.needsExplicit(m.readBook(scope)),true);assert.equal(m.readBook(scope).continuity_unverified,true);});
test('精确终态保存只移除对应身份，另一请求和未接续保持',()=>{const {m}=load();const second={...first,request_id:'request-B'};m.savePending(scope,first);m.savePending(scope,second);m.settle(scope,first,'completed');const b=m.readBook(scope);assert.equal(b.pending.request_id,'request-B');assert.equal(b.settled[0].source,'local');assert.equal(b.continuity_unverified,true);});
test('新标签接续未知记录不授予普通写权限，导出不删除',()=>{const a=load(),b=load();a.m.savePending(scope,first);b.m.importBook(a.m.exportBook(scope),scope);assert.equal(a.m.readBook(scope).pending.request_id,'request-A');assert.equal(b.m.readBook(scope).history[0].instance_id,first.instance_id);assert.equal(b.m.needsExplicit(b.m.readBook(scope)),true);});
test('带入终态保留carried并阻止普通写，刷新不提升来源',()=>{const a=load(),b=load();a.m.savePending(scope,first);a.m.settle(scope,first,'completed');b.m.importBook(a.m.exportBook(scope),scope);assert.equal(b.m.readBook(scope).settled[0].source,'carried');assert.equal(b.m.needsExplicit(b.m.readBook(scope)),true);assert.equal(JSON.parse([...b.data.values()][0]).settled[0].source,'carried');});
test('同身份冲突终态／参数拒绝且原字节不变',()=>{const {m,data}=load();m.savePending(scope,first);m.settle(scope,first,'completed');const envelope=JSON.parse(m.exportBook(scope));envelope.settled[0].state='failed';const before=[...data.values()][0];assert.throws(()=>m.importBook(JSON.stringify(envelope),scope));assert.equal([...data.values()][0],before);});
test('空封套、错误范围、未知字段和超限不能解除门槛',()=>{const {m}=load();m.importBook(m.exportBook(scope),scope);assert.equal(m.readBook(scope).continuity_unverified,true);const e=JSON.parse(m.exportBook(scope));for(const change of [v=>v.endpoint='http://127.0.0.1:19999',v=>v.target='szse:399001:price',v=>v.extra=true]){const c=json(e);change(c);assert.throws(()=>m.importBook(JSON.stringify(c),scope));}assert.throws(()=>m.importBook(' '.repeat(262145),scope));});
test('退役记录仅按原字节导出，不变更、不列为可查询作用域',()=>{const {m,data}=load();const key=`wolf-update:${scope.endpoint}:${scope.data_scope_id}:index.000300.update`;const raw='{"pending":{"request_id":"old-unknown"},"history":[]}';data.set(key,raw);assert.deepEqual(json(m.retiredRecords()),[{key,text:raw}]);assert.equal(m.allScopes().length,0);assert.equal(data.get(key),raw);assert.throws(()=>m.validScope({...scope,operation:'index.000300.update',target:'000300'}));});
test('保存失败保留原未知记录并禁写，不伪称持久成功',()=>{const {m,fail}=load();m.savePending(scope,first);fail();assert.throws(()=>m.settle(scope,first,'completed'));assert.equal(m.readBook(scope).pending.request_id,'request-A');assert.ok(m.operationError(scope));});
test('B严格保存固定P及CAS参数，请求ID遵守80字符上限',()=>{const {m}=load();const s={...scope,operation:'market.activity.update'},id={...first,operation:s.operation,series_id:s.target,parameters:{price_snapshot_id:'c'.repeat(64),expected_activity_id:null}};delete id.index_id;m.savePending(s,id);const b=m.readBook(s);assert.equal(b.pending.parameters.price_snapshot_id,'c'.repeat(64));assert.throws(()=>m.validIdentity({...id,request_id:'z'.repeat(81)},s));assert.equal(m.identityKey(id),m.identityKey({...id,parameters:{expected_activity_id:null,price_snapshot_id:'c'.repeat(64)}}));});
test('断连扫描只能列出公开作用域，不构造网络权限',()=>{const {m}=load();m.savePending(scope,first);assert.deepEqual(json(m.allScopes()),[scope]);assert.equal(typeof m.allScopes()[0].instance_id,'undefined');});
for(const order of ['carried-first','unknown-first'])test('重复接续可再次导入且未知优先：'+order,()=>{
 const unknown=load(),done=load(),merged=load(),next=load();unknown.m.savePending(scope,first);done.m.savePending(scope,first);done.m.settle(scope,first,'completed');
 const texts=order==='carried-first'?[done.m.exportBook(scope),unknown.m.exportBook(scope)]:[unknown.m.exportBook(scope),done.m.exportBook(scope)];
 for(const text of texts)merged.m.importBook(text,scope);
 const book=merged.m.readBook(scope);assert.equal(book.history.length,1);assert.equal(book.settled.length,0);assert.equal(merged.m.needsExplicit(book),true);
 next.m.importBook(merged.m.exportBook(scope),scope);assert.deepEqual(json(next.m.readBook(scope)),json(book));
});
test('旧未知不能覆盖本页精确终态，冲突带入仍拒绝',()=>{
 const unknown=load(),done=load();unknown.m.savePending(scope,first);done.m.savePending(scope,first);done.m.settle(scope,first,'completed');done.m.importBook(unknown.m.exportBook(scope),scope);
 assert.equal(done.m.readBook(scope).history.length,0);assert.equal(done.m.readBook(scope).settled[0].source,'local');
});
