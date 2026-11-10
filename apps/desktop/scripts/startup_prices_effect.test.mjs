/** 新发布的固定版本与读取失败恢复；不启动采集，真实观察身份另用SQL夹具核对。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {delimiter} from 'node:path';
import {harness, IDS} from './overview_hook.harness.mjs';
async function verify(oldVersion,newVersion){
 const h=harness();h.priceVersions.set(IDS[0],oldVersion);try{
  await h.start();assert.equal(h.view.rows[IDS[0]].snapshot.snapshot_id,oldVersion);
  const before=h.calls.length;await h.poll();assert.equal(h.calls.length,before);
  const fail=h.hold('overview',IDS[0]);h.priceVersions.set(IDS[0],newVersion);await h.poll();fail.reject(Error('transient read'));await h.drain();
  assert.equal(h.view.rows[IDS[0]].snapshot.snapshot_id,oldVersion);assert.equal(h.view.rows[IDS[0]].stale,true);
  const count=h.calls.length;await h.drain();assert.equal(h.calls.length,count,'不得无间隔重试');
  await h.poll();assert.equal(h.view.rows[IDS[0]].snapshot.snapshot_id,newVersion);assert.ok(!h.view.rows[IDS[0]].stale);
  const complete=h.calls.length;await h.poll();assert.equal(h.calls.length,complete);
 }finally{await h.close()}
}
test('新发布概况首次读取失败标旧，下一间隔固定同版本恢复且停止重复读取',()=>verify('old','new'));
test('真实SQL存储首次/后续观察保持身份，新发布版本读取故障可恢复',async()=>{
 const python=fileURLToPath(new URL('../../../python/.venv/bin/python',import.meta.url));
 const fixture=fileURLToPath(new URL('../../../python/tests/startup_observation_fixture.py',import.meta.url));
 const paths=['../../../python/src','../../../python/tests'].map(p=>fileURLToPath(new URL(p,import.meta.url))).join(delimiter);
 const cases=JSON.parse(execFileSync(python,['-B',fixture],{encoding:'utf8',env:{...process.env,PYTHONPATH:paths,PYTHONDONTWRITEBYTECODE:'1'}}));
 for(const item of Object.values(cases)){assert.equal(item.current.snapshot_id,item.status.snapshot_id);assert.notEqual(item.current.observation_id,item.status.observation_id);assert.equal(item.status.result,'unchanged')}
 await verify(cases.old.current.snapshot_id,cases.new.current.snapshot_id);
});
