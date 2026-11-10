/** 实际SQL读取hook的选择、绑定和迟到结果检查。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {harness, IDS, MARKET} from './overview_hook.harness.mjs';
test('首屏四概况与市场概况；仅所选指数请求价格和配对量额范围',async()=>{
  const h=harness();try{await h.start();assert.equal(h.calls.filter(x=>x.kind==='overview').length,4);assert.equal(h.calls.filter(x=>x.kind==='market').length,1);
    assert.deepEqual(h.calls.filter(x=>['price','quantity'].includes(x.kind)).map(x=>[x.kind,x.id]),[['price',IDS[0]],['quantity',IDS[0]]]);
    await h.select(IDS[1]);assert.equal(h.view.detail.price.id,IDS[1]);assert.equal(h.view.detail.activity.id,IDS[1]);
    assert.equal(h.calls.filter(x=>x.kind==='overview').length,4);await h.select('three-market');assert.equal(h.view.detail.price,undefined);
    assert.equal(h.view.detail.activity.id,MARKET);assert.equal(h.view.busy,false);
  }finally{await h.close()}
});

test('概况和详情分别等待；快速选择后迟到的旧详情不得覆盖当前选择',async()=>{
  const h=harness(),overview=h.hold('overview',IDS[1]);try{await h.start();assert.equal(h.view.busy,true);overview.resolve();await h.drain();
    const old=h.hold('price',IDS[1]);await h.select(IDS[1]);assert.equal(h.view.detail.price,undefined);assert.equal(h.view.busy,true);
    await h.select(IDS[2]);assert.equal(h.view.detail.price.id,IDS[2]);old.resolve();await h.drain();assert.equal(h.view.detail.price.id,IDS[2]);
    assert.equal(h.view.busy,false);
  }finally{overview.resolve();await h.close()}
});

test('新价格发布且量额缺失时不展示旧配对；旧请求迟到不延长loading，后续量额发布可恢复',async()=>{
  const h=harness();try{await h.start();const old=h.hold('quantity',IDS[1]);await h.select(IDS[1]);
    h.priceVersions.set(IDS[1],'p2');h.quantityVersions.set(IDS[1],null);await h.poll();
    assert.equal(h.view.detail.price.publication,'p2');assert.equal(h.view.detail.activity,undefined);assert.equal(h.view.busy,false);
    old.resolve();await h.drain();assert.equal(h.view.detail.activity,undefined);assert.equal(h.view.busy,false);
    h.quantityVersions.set(IDS[1],'a2');await h.poll();assert.equal(h.view.detail.activity.publication,'a2');assert.equal(h.view.detail.price.publication,'p2');
  }finally{await h.close()}
});

test('量额连接延迟或失败时保留最新选择，未配置量额也可读取价格',async()=>{
  for(const options of [{failedConnection:true},{noQuantity:true}]){
    const h=harness(options),gate=h.holdConnection();try{await h.start();await h.select(IDS[2]);gate.resolve();await h.drain();
      assert.equal(h.view.detail.price.id,IDS[2]);assert.equal(h.view.detail.activity,undefined);assert.equal(h.view.busy,false);
      await h.select(IDS[3]);assert.equal(h.view.detail.price.id,IDS[3]);assert.equal(h.calls.filter(x=>x.kind==='quantity').length,0);
    }finally{gate.resolve();await h.close()}
  }
});

test('范围读取失败保留明确错误且不自动重试；旧连接和旧参数的迟到结果被丢弃',async()=>{
  const h=harness();try{await h.start();const failed=h.hold('price',IDS[1]);await h.select(IDS[1]);failed.reject(Error('range unavailable'));await h.drain();
    assert.equal(h.view.detail.price,undefined);assert.equal(h.view.detail.activity,undefined);assert.match(h.view.detail.activityError,/当前周期价格计算未取得/);assert.match(h.view.detail.priceError,/range unavailable/);assert.equal(h.calls.filter(x=>x.kind==='price'&&x.id===IDS[1]).length,1);
    const late=h.hold('price',IDS[2]);await h.select(IDS[2]);h.priceVersions.set(IDS[2],'p2');await h.reconnect();
    late.resolve();await h.drain();assert.equal(h.view.detail.price.publication,'p2');
    const daily=h.hold('price',IDS[3]);await h.select(IDS[3]);await h.change({frequency:'weekly'});daily.resolve();await h.drain();
    assert.equal(h.view.detail.price.frequency,'weekly');assert.equal(h.view.detail.activity.frequency,'weekly');
  }finally{await h.close()}
});

test('版本检查失败立即停止展示；同版本恢复也重新读取；正常检查只查版本',async()=>{
  const h=harness();try{await h.start();const count=h.calls.length;await h.poll();assert.equal(h.calls.length,count);
    h.failVersions(true);await h.poll();assert.equal(Object.keys(h.view.rows).length,0);assert.equal(h.view.market,undefined);assert.equal(h.view.detail.price,undefined);
    assert.match(h.view.phase,/版本核对失败/);h.failVersions(false);await h.poll();assert.ok(h.view.detail.price);assert.ok(h.calls.length>count);assert.equal(h.view.busy,false);
  }finally{await h.close()}
});

test('首次描述、握手或版本失败在30秒后恢复；刷新失败不留下旧行',async()=>{
  for(const stage of ['descriptor','handshake','versions']){
    const h=harness();try{
      if(stage==='descriptor')h.failDescriptor(1);
      if(stage==='handshake')h.failHandshake(1);
      if(stage==='versions')h.failVersions(true);
      await h.start();assert.equal(Object.keys(h.view.rows).length,0);assert.equal(h.view.detail.price,undefined);
      h.failVersions(false);await h.poll();assert.equal(h.calls.filter(x=>x.kind==='overview').length,4);assert.ok(h.view.detail.price);
      h.failVersions(true);await h.change({refreshToken:1});assert.equal(Object.keys(h.view.rows).length,0);assert.equal(h.view.market,undefined);
      assert.equal(h.view.detail.price,undefined);h.failVersions(false);await h.poll();assert.ok(h.view.detail.price);
      const count=h.calls.length;await h.poll();assert.equal(h.calls.length,count);
    }finally{await h.close()}
  }
});

test('首次失败的重试随卸载取消；重连后旧内容迟到不覆盖新版本',async()=>{
  const failed=harness();failed.failVersions(true);await failed.start();await failed.close();
  const h=harness(),late=h.hold('overview',IDS[0]);try{
    await h.start();h.failVersions(true);await h.change({refreshToken:1});
    h.failVersions(false);h.priceVersions.set(IDS[0],'p2');await h.reconnect();late.resolve();await h.drain();
    assert.equal(h.view.rows[IDS[0]].snapshot.snapshot_id,'p2');assert.equal(h.view.detail.price.publication,'p2');
  }finally{late.resolve();await h.close()}
});
