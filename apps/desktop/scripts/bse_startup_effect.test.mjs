/** 用当前轻量版本入口观察沪深北发布；不再轮询旧current和重放全快照。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {harness, MARKET} from './overview_hook.harness.mjs';
for(const old of [null,'old-market'])test(`市场${old??'空库'}跟随固定版本发布，未选择市场时只取概况`,async()=>{
 const h=harness();h.marketVersion(old);try{await h.start();assert.equal(h.view.market?.activity_id,old??undefined);
  h.marketVersion('new-market');await h.poll();assert.equal(h.view.market.activity_id,'new-market');
  assert.equal(h.calls.filter(x=>x.kind==='quantity'&&x.id===MARKET).length,0);
  const n=h.calls.length;await h.poll();assert.equal(h.calls.length,n,'同一成功版本不重读');
  await h.select('three-market');assert.equal(h.view.detail.activity.publication,'new-market');
 }finally{await h.close()}
});
test('市场概况失败标明不可用，间隔到达后复核同版本并恢复',async()=>{
 const h=harness(),gate=h.hold('market',MARKET);try{await h.start();gate.reject(Error('temporary read failure'));await h.drain();
  assert.equal(h.view.market,undefined);assert.match(h.view.marketError,/temporary/);const n=h.calls.length;await h.drain();assert.equal(h.calls.length,n);
  await h.poll();assert.equal(h.view.market.activity_id,'market1');assert.equal(h.view.marketError,undefined);
 }finally{gate.resolve();await h.close()}
});
