/** 页面只观察已保存版本；采集调度与额度仍在后端，禁止页面触发金融更新。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {harness, IDS} from './overview_hook.harness.mjs';
test('量额握手瞬时失败不立即重试，间隔版本复核后恢复',async()=>{
 const h=harness();h.failConnections(1);try{await h.start();assert.equal(h.view.detail.activity,undefined);assert.match(h.view.connectionNotice,/offline/);
  const count=h.calls.length;await h.drain();assert.equal(h.calls.length,count);await h.poll();assert.ok(h.view.detail.activity);assert.equal(h.view.connectionNotice,undefined);
 }finally{await h.close()}
});
test('范围读取失败后间隔恢复；版本拒绝停止旧展示，断开后迟到连接关闭',async()=>{
 const h=harness();try{await h.start();const failure=h.hold('quantity',IDS[1]);await h.select(IDS[1]);failure.reject(Error('unavailable'));await h.drain();
  assert.equal(h.view.detail.activity,undefined);assert.match(h.view.detail.activityError,/unavailable/);await h.poll();assert.ok(h.view.detail.activity);
  h.failVersions(true);await h.poll();assert.equal(h.view.detail.price,undefined);assert.equal(h.view.detail.activity,undefined);assert.equal(Object.keys(h.view.rows).length,0);
  h.failVersions(false);await h.poll();assert.ok(h.view.detail.activity);
  const late=h.holdConnection();await h.reconnect();await h.change({connection:undefined});late.resolve();await h.drain();assert.equal(h.view.detail.price,undefined);
 }finally{await h.close()}
});
