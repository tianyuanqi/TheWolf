/** 实际合成HTTP产物的语义门禁与缓存；不读取真实库、不重算金融公式。 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import * as validators from '../../../contracts/generated/validators.mjs';
const modules = new Map();
function load(name) {
  if (name.endsWith('validators.mjs')) return validators;
  const file = path.resolve('apps/desktop/src', name + '.ts');
  if (modules.has(file)) return modules.get(file);
  const module = { exports: {} }; modules.set(file, module.exports);
  const code = ts.transpileModule(readFileSync(file, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  vm.runInNewContext(code, { module, exports: module.exports, require: load, Date, Set, Map, BigInt, Number,
    AbortController, AbortSignal, DOMException, URL, structuredClone });
  return module.exports;
}
const { StoredViews } = load('storedViews');
const fixture = JSON.parse(readFileSync(process.env.WOLF_STORED_FIXTURE, 'utf8'));
assert.equal(fixture.prices.length, 12); assert.equal(fixture.activities.length, 26); assert.equal(fixture.markets.length, 2);
const signal = new AbortController().signal;
let response, versions = fixture.versions, requests = 0;
const price = { expected: { config_id: 'price-config' }, instance: 'one-instance', closed: false,
  storedVersions: async () => structuredClone(versions), storedView: async () => { requests++; return structuredClone(response); } };
const activity = { expected: { config_id: 'activity-config' }, closed: false,
  storedView: async () => { requests++; return structuredClone(response); } };
const views = new StoredViews(price, activity);
await views.versions(signal);
let valid = 0, rejected = 0;
const version = (value, kind) => kind === 'price' ? fixture.versions.indices.find(x => x.index_id === value.index_id).price
  : [...fixture.versions.indices, ...fixture.versions.markets].find(x => (x.index_id ?? x.series_id) === value.series_id).activity;
async function exercise(value, invoke, mutations) {
  response = value; views.clear(); await invoke(); valid++;
  for (const mutate of mutations) {
    response = structuredClone(value); mutate(response); views.clear();
    await assert.rejects(invoke, `应拒绝畸形响应: ${mutate}`); rejected++;
  }
}
for (const { overview: value, range } of fixture.prices) {
  const v = version(value, 'price');
  await exercise(value, () => views.overview(value.index_id, v, signal), [
    x => x.instrument.code = '999999', x => x.instrument.provider = 'eastmoney',
    x => x.bars[0].high = '0.00', x => x.bars[1].trade_date = x.bars[0].trade_date,
    x => x.performance.day_5.unit = '点', x => x.performance.day_20.parameters.period = '5',
    x => x.performance.year_1.input_ref.snapshot_id = '0'.repeat(64),
    x => { x.performance.year_1.value = null; x.performance.year_1.reason = 'insufficient_samples'; },
    x => x.verification.primary_source = 'eastmoney', x => x.sources[1] = x.sources[0],
    x => x.summary.close = '1.00', x => x.requested_range.start = '2026-02-30',
  ]);
  await exercise(range, () => views.priceRange(value.index_id, v, range.requested_range, range.frequency, [5,20], signal), [
    x => x.navigation_periods = [], x => x.navigation_periods[0].start = '2026-02-30',
    x => x.navigation_periods[1] = x.navigation_periods[0],
    x => x.series.rows[0].period_start = '2026-02-30', x => x.series.rows[0].high = '0.00',
    x => x.series.rows[0].input_ref.snapshot_id = '0'.repeat(64),
    x => x.series.rows.at(-1).ma[0].parameters.period = '20', x => x.ma_periods = [5,5],
    x => x.series.rows.at(-1).change_pct.unit = '点', x => x.returned_range.end = x.returned_range.start,
  ]);
}
for (const value of fixture.activities) {
  await exercise(value, () => views.activityRange(value.series_id, version(value,'activity'), value.requested_range, value.field, value.frequency, [5,20], signal), [
    x => x.navigation_periods = [], x => x.navigation_periods[1] = x.navigation_periods[0],
    x => x.series.rows[0].total.input_ref.activity_id = '0'.repeat(64),
    x => x.series.rows[0].total.unit = '%', x => x.series.rows.at(-1).ma[0].parameters.operation = 'sum',
    x => x.series.rows[0].total.complete = !x.series.rows[0].total.complete,
    x => x.series.rows[0].period_end = '2026-02-30', x => x.source_revision_relation = 'same',
    x => x.price_snapshot_id = '0'.repeat(64), x => x.source_scope = '',
  ]);
}
for (const value of fixture.markets) {
  await exercise(value, () => views.marketOverview(value.series_id, version(value,'activity'), signal), [
    x => x.navigation_periods = [],
    x => x.comparisons = null, x => x.comparisons.year_1.baseline.parameters.operation = 'sum',
    x => x.comparisons.day_5.comparison.unit = '元', x => x.comparisons.day_20.sample_count = -1,
    x => x.comparisons.day_60.comparison.input_ref.activity_id = '0'.repeat(64),
    x => x.series.rows.at(-1).total.unit = '%', x => x.series.rows[0].period_start = '2026-02-30',
  ]);
}
for (const mutate of [x => x.indices.pop(), x => x.indices[1] = x.indices[0], x => x.markets.pop(),
  x => x.indices.find(item => item.price).price.observation_id = null, x => x.indices.find(item => item.activity).activity.binding = '0'.repeat(64)]) {
  versions = structuredClone(fixture.versions); mutate(versions); await assert.rejects(() => views.versions(signal)); rejected++;
}
versions = fixture.versions; await views.versions(signal);
const value = fixture.prices[0].overview, v = version(value, 'price'); response = value; views.clear();
const before = requests, invoke = () => views.overview(value.index_id, v, signal);
const first = await invoke(); first.bars[0].close = '999.00';
assert.equal((await invoke()).bars[0].close, value.bars[0].close); assert.equal(requests, before + 1);
versions = { ...versions, store_id: '0'.repeat(32) };
await views.versions(signal); await invoke(); assert.equal(requests, before + 2);
const cancelled = new AbortController(); cancelled.abort();
await assert.rejects(() => views.overview(value.index_id, v, cancelled.signal));
// 两个调用者共享进行中固定读取；取消其中一个不取消另一个，也不串可变对象。
views.clear();
const normalRead=price.storedView;
let release;
price.storedView=async()=>{requests++;return new Promise(resolve=>{release=resolve;});};
const cancelledPending=new AbortController(),countBefore=requests;
const pendingFirst=views.overview(value.index_id,v,cancelledPending.signal);
const pendingSecond=views.overview(value.index_id,v,signal);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(requests,countBefore+1);cancelledPending.abort();
await assert.rejects(pendingFirst,/取消/);
release(structuredClone(value));const shared=await pendingSecond;
shared.bars[0].close='999.00';assert.equal((await invoke()).bars[0].close,value.bars[0].close);
// clear之后迟到的旧连接响应不允许重新填入缓存。
views.clear();const discarded=invoke();await new Promise(resolve=>setImmediate(resolve));
views.clear();release(structuredClone(value));await assert.rejects(discarded,/取消/);
price.storedView=normalRead;const afterClear=requests;response=value;await invoke();assert.equal(requests,afterClear+1);
price.closed = true; await assert.rejects(invoke);
console.log(JSON.stringify({ valid, rejected, cacheIsolation: true, storeIdentity: true, cancellation: true, closedConnection: true, inFlightDeduplication: true, independentCancellation: true, lateClear: true }));
