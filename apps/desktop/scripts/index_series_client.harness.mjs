/** v2实际消费者的反例；输入由隔离真实服务夹具生成，不复制生产验证器。 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
const app = path.resolve(import.meta.dirname, '..');
const require = createRequire(path.join(app, 'src/indexSeriesClient.ts'));
const fixture = JSON.parse(readFileSync(process.env.WOLF_SERIES_FIXTURE, 'utf8'));
const descriptor = fixture.descriptor, legacy = fixture.legacy;
const instance = '00000000-0000-4000-8000-000000000000';
const clone = value => structuredClone(value);

function harness() {
  const calls = [], queue = [], cache = {};
  function load(name) {
    if (cache[name]) return cache[name];
    const filename = path.join(app, 'src', name + '.ts');
    const module = { exports: {} };
    const source = ts.transpileModule(readFileSync(filename, 'utf8'), { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
    } }).outputText;
    vm.runInNewContext(source, { module, exports: module.exports, URL, AbortController, AbortSignal, DOMException, structuredClone,
      fetch: async (url, options) => { calls.push({ url, options }); assert.ok(queue.length, '缺少受控响应'); return queue.shift()(url, options); },
      require: request => request.startsWith('./') ? load(request.slice(2)) : require(request),
    });
    return cache[name] = module.exports;
  }
  const clientModule = load('indexSeriesClient'), types = load('indexSeriesTypes'), calculations = load('indexCalculationTypes');
  function response(value, { status = 200, headers = {} } = {}) {
    return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json',
      'X-Wolf-Config': descriptor.config_id, 'X-Wolf-Instance': instance, ...headers } });
  }
  const ready = () => ({ ...clone(descriptor), endpoint: undefined, status: 'ready', instance_id: instance });
  async function connect() {
    queue.push(() => response(ready()));
    return clientModule.IndexSeriesClient.connect(clientModule.parseIndexDescriptor(descriptor, legacy), instance, new AbortController().signal);
  }
  return { ...clientModule, types, calculations, calls, queue, response, ready, connect };
}

test('描述来源、集合语义、额外字段与嵌套冻结', () => {
  const h = harness();
  for (const mutate of [v => v.endpoint = 'http://localhost:8000', v => v.endpoint += '/api',
    v => v.endpoint = 'http://127.0.0.1:65536', v => v.contract_sha256 = '0'.repeat(64),
    v => v.identity_format = 'wolf-config-v2', v => v.data_scope_id = '0'.repeat(64), v => v.extra = true,
    v => v.write_indices = ['sse:000001:price', 'sse:000001:price'],
    v => v.startup_indices = ['sse:000001:price'],
    v => v.policy.source_policy_versions = [v.policy.source_policy_versions[0], v.policy.source_policy_versions[0]]]) {
    const value = clone(descriptor); mutate(value); assert.throws(() => h.parseIndexDescriptor(value, legacy));
  }
  const original = clone(descriptor), parsed = h.parseIndexDescriptor(original, legacy);
  original.policy.network.max_bytes = 0;
  assert.equal(parsed.policy.network.max_bytes, descriptor.policy.network.max_bytes);
  assert.ok(Object.isFrozen(parsed.policy.network) && Object.isFrozen(parsed.write_indices));
});

test('握手不学习错误配置，所有反例只允许一次ready请求', async () => {
  for (const mutate of [v => v.config_id = legacy.config_id, v => v.data_scope_id = '0'.repeat(64),
    v => v.policy.network.max_bytes++, v => v.write_indices = ['sse:000001:price'],
    v => v.instance_id = '11111111-1111-4111-8111-111111111111', v => v.extra = 1]) {
    const h = harness(), ready = h.ready(); mutate(ready); h.queue.push(() => h.response(ready));
    await assert.rejects(h.IndexSeriesClient.connect(descriptor, instance, new AbortController().signal));
    assert.equal(h.calls.length, 1);
  }
  const h = harness(); h.queue.push(() => h.response(h.ready(), { headers: { 'X-Wolf-Config': legacy.config_id } }));
  await assert.rejects(h.IndexSeriesClient.connect(descriptor, instance, new AbortController().signal));
});

test('实际完整视图保留四位原值；跨指数、精度丢失与窗口错配拒绝', async () => {
  const h = harness(), client = await h.connect();
  const view = fixture.views['szse:399001:price'];
  h.queue.push(() => h.response(view));
  const snapshot = await client.current(view.index_id, new AbortController().signal);
  assert.equal(snapshot.bars.at(-1).close, view.snapshot.bars.at(-1).close);
  assert.match(snapshot.bars.at(-1).close, /\.\d{4}$/);
  for (const mutate of [v => v.index_id = 'sse:000001:price', v => v.snapshot.retrieval.snapshot_id = '0'.repeat(64),
    v => v.snapshot.bars[0].close = '100.00', v => v.snapshot.calendar_dates[0] = '2024-02-30',
    v => v.snapshot.window.actual_count--, v => v.snapshot.summary.close = '999.9999']) {
    const invalid = clone(view); mutate(invalid); assert.throws(() => h.types.parseSeriesView(invalid, view.index_id));
  }
  const requests = h.calls.length;
  await assert.rejects(client.current('../arbitrary', new AbortController().signal), /未登记/);
  assert.equal(h.calls.length, requests);
  assert.ok(h.calls.every(({ options }) => options.credentials === 'omit' && options.redirect === 'error' && !options.body));
});

test('错误归属关闭连接，404与409不互换；迟到正文不得返回', async () => {
  const h = harness(), client = await h.connect(), id = 'sse:000001:price';
  for (const [status, code] of [[404, 'index_series_empty'], [409, 'index_series_invalid']]) {
    h.queue.push(() => h.response({ detail: { code, message: '合成错误' } }, { status }));
    await assert.rejects(client.current(id, new AbortController().signal), error => error.status === status && error.code === code);
  }
  let resolve;
  h.queue.push(() => ({ ok: true, headers: new Headers({ 'Content-Type': 'application/json', 'X-Wolf-Instance': instance, 'X-Wolf-Config': descriptor.config_id }),
    json: () => new Promise(done => { resolve = done; }) }));
  const controller = new AbortController(), result = client.current(id, controller.signal);
  await new Promise(done => setImmediate(done)); controller.abort(); resolve(fixture.views[id]);
  await assert.rejects(result, /取消/);
  h.queue.push(() => h.response(fixture.views[id], { headers: { 'X-Wolf-Config': legacy.config_id } }));
  await assert.rejects(client.current(id, new AbortController().signal), /不属于/); assert.equal(client.closed, true);
});

test('高低点仅选择可见原值，包含四位差异与并列最早；月份不按固定天数换算', () => {
  const { types } = harness();
  const bars = [{ trade_date: '2026-01-01', high: '110.0001', low: '90.0000' },
    { trade_date: '2026-01-02', high: '110.0002', low: '89.9999' },
    { trade_date: '2026-01-03', high: '110.0002', low: '89.9999' },
    { trade_date: '2026-01-04', high: '999.0000', low: '1.0000' }];
  const result = types.visibleExtrema(bars, 0, 2);
  assert.equal(result.high, bars[1]); assert.equal(result.low, bars[1]);
  assert.equal(types.monthsBefore('2024-03-31', 1), '2024-02-29');
  assert.equal(types.monthsBefore('2024-02-29', 12), '2023-02-28');
  assert.equal(types.validDay('2024-02-30'), false);
  const full = fixture.views['sse:000001:price'].snapshot.bars;
  assert.equal(types.trendBars(full, '5').length, 6);
  assert.equal(types.trendBars(full, '20').length, 21);
});


test('固定计算请求使用快照和显式版本；未知公式、跨快照及错误引用均拒绝', async () => {
  const h = harness(), client = await h.connect(), id = 'szse:399001:price';
  const snapshot = fixture.views[id].snapshot, calculation = fixture.calculations[id];
  h.queue.push(() => h.response(calculation));
  const parsed = await client.calculations(snapshot, new AbortController().signal);
  assert.equal(parsed.daily.rows.at(-1).change_pct.value, snapshot.summary.daily_change_pct);
  assert.equal(parsed.weekly.rows.at(-1).ma[0].value, calculation.weekly.rows.at(-1).ma[0].value);
  assert.equal(h.calls.at(-1).url, descriptor.endpoint + '/api/index-series/' + encodeURIComponent(id) + '/snapshots/' + snapshot.snapshot_id + '/calculations?formula_version=index-price-calculations-v1');
  assert.equal(h.calls.at(-1).options.headers['X-Wolf-Expected-Config'], descriptor.config_id);
  for (const mutate of [v => v.snapshot_id = '0'.repeat(64), v => v.index_id = 'sse:000001:price',
    v => v.formula_version = 'latest', v => v.daily.rows.at(-1).change_pct.value = '1.23',
    v => v.daily.rows[2].close = '999.0000', v => v.daily.rows[2].ma[0].reason = null,
    v => v.monthly.rows[0].input_ref.snapshot_id = '0'.repeat(64),
    v => v.weekly.rows[50].ma[0].input_ref.end = snapshot.window.start,
    v => v.weekly.rows[50].ma[0].parameters.frequency = 'daily',
    v => v.monthly.ma_availability[7].available = true,
    v => v.performance.day_60.parameters.period = '5',
    v => v.monthly.rows.at(-1).complete = true,
    v => v.weekly.rows[5].period_end = '2026-02-30',
    v => v.weekly.rows[5].ma[0].value = null,
    v => v.performance.year_1.unit = '点']) {
    const value = clone(calculation); mutate(value); assert.throws(() => h.calculations.parseCalculations(value, snapshot));
  }
});

test('计算404、错误媒体、错实例与迟到正文不会变成其他快照或自动重试', async () => {
  const h = harness(), client = await h.connect(), snapshot = fixture.views['sse:000001:price'].snapshot;
  h.queue.push(() => h.response({ detail: { code: 'index_series_snapshot_not_found', message: '合成快照不存在' } }, { status: 404 }));
  await assert.rejects(client.calculations(snapshot, new AbortController().signal), e => e.code === 'index_series_snapshot_not_found' && e.status === 404);
  h.queue.push(() => h.response(fixture.calculations[snapshot.instrument.id], { headers: { 'Content-Type': 'text/html' } }));
  await assert.rejects(client.calculations(snapshot, new AbortController().signal), /媒体/);
  let release;
  h.queue.push(() => ({ ok: true, headers: new Headers({ 'Content-Type': 'application/json', 'X-Wolf-Instance': instance, 'X-Wolf-Config': descriptor.config_id }),
    json: () => new Promise(done => { release = done; }) }));
  const controller = new AbortController(), pending = client.calculations(snapshot, controller.signal);
  await new Promise(done => setImmediate(done)); controller.abort(); release(fixture.calculations[snapshot.instrument.id]);
  await assert.rejects(pending, /取消/);
  h.queue.push(() => h.response(fixture.calculations[snapshot.instrument.id], { headers: { 'X-Wolf-Instance': 'wrong' } }));
  await assert.rejects(client.calculations(snapshot, new AbortController().signal), /不属于/);
  const count = h.calls.length;
  await assert.rejects(client.calculations(snapshot, new AbortController().signal), /取消/);
  assert.equal(h.calls.length, count); assert.equal(count, 5);
});
