/** 执行真实总览读取effect与观察器：发布成功但首轮重读失败，恢复后必须自动显示。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { delimiter } from 'node:path';
import ts from 'typescript';

async function verifyEffect(cases) {
  const id = 'sse:000001:price', timers = new Map(), slots = [];
  let now = 0, serial = 0, hook = 0, pendingRender = false, mounted = true, cleanup, effectDeps, nextEffect;
  let available = 'old', failNext = false, attempts = 0, statusCalls = 0, view;
  const legacy = { expected: { config_id: 'config', data_scope_id: 'scope' }, instance: 'instance', closed: false };
  const drain = async () => { for (let i = 0; i < 120; i++) await Promise.resolve(); };
  const schedule = () => {
    if (pendingRender || !mounted) return;
    pendingRender = true;
    queueMicrotask(() => { pendingRender = false; if (mounted) render(); });
  };
  class Client {
    expected = { startup_indices: [id] }; instance = 'instance'; closed = false;
    static async connect() { return new Client(); }
    async current() {
      attempts++;
      if (failNext) { failNext = false; throw new TypeError('synthetic transient failure'); }
      return cases[available].current;
    }
    async calculations() { return {}; }
    async status() { statusCalls++; return cases[available].status; }
    close() { this.closed = true; }
  }
  const context = vm.createContext({ module: { exports: {} }, exports: {}, Map, Set, Promise, AbortController, Error, TypeError, Date: { now: () => now },
    setTimeout: (fn, delay) => { const key = ++serial; timers.set(key, { fn, at: now + delay }); return key; }, clearTimeout: key => timers.delete(key),
    require: name => { assert.equal(name, './indexSeriesTypes'); return { OVERVIEW_INDICES: [{ id, name: '上证指数' }] }; },
    useState: initial => { const n = hook++; if (!(n in slots)) slots[n] = initial; return [slots[n], value => { const next = typeof value === 'function' ? value(slots[n]) : value; if (!Object.is(next, slots[n])) { slots[n] = next; schedule(); } }]; },
    useRef: initial => { const n = hook++; return slots[n] ??= { current: initial }; },
    useEffect: (effect, deps) => { if (!effectDeps || deps.some((x, i) => !Object.is(x, effectDeps[i]))) { effectDeps = deps; nextEffect = effect; } },
    IndexSeriesClient: Client, IndexReadError: class extends Error {},
    indexConnectionDescriptor: async () => ({ policy: { periodic: false } }), activityConnectionDescriptor: async () => undefined,
    OVERVIEW_INDICES: [{ id, name: '上证指数' }], DEFAULT_MA: [5,10,20,30,250], errorText: error => error.message,
  });
  const compile = code => ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
  context.exports = context.module.exports;
  vm.runInContext(compile(readFileSync(new URL('../src/startupPrices.ts', import.meta.url), 'utf8')), context);
  Object.assign(context, context.module.exports);
  // 只截取组件的hooks与真实读取effect；实际DOM另由隔离浏览器验证。
  const source = readFileSync(new URL('../src/ProductionOverview.tsx', import.meta.url), 'utf8');
  const begin = source.indexOf('export function ProductionOverview('), end = source.indexOf('  const trends = useMemo');
  assert.ok(begin >= 0 && end > begin);
  vm.runInContext(compile(source.slice(begin, end) + '\nreturn { rows, startupNotice };\n}'), context);
  function render() {
    hook = 0; view = context.module.exports.ProductionOverview({ connectionClient: legacy });
    if (nextEffect) { const effect = nextEffect; nextEffect = undefined; cleanup?.(); cleanup = effect(); }
  }
  async function tick(ms) {
    now += ms;
    for (const [key, timer] of [...timers]) if (timer.at <= now) { timers.delete(key); timer.fn(); }
    await drain();
  }
  try {
    render(); await drain(); assert.equal(view.rows[id].snapshot.snapshot_id, cases.old.current.snapshot_id); assert.equal(attempts, 1);
    for (let i = 0; i < 10; i++) await tick(3000);
    assert.equal(attempts, 1, '同一快照的后续观察不得导致重读');
    available = 'new'; failNext = true; await tick(3000);
    assert.equal(attempts, 2); assert.equal(view.rows[id].snapshot.snapshot_id, cases.old.current.snapshot_id); assert.equal(view.rows[id].stale, true);
    await tick(2999); assert.equal(attempts, 2, '重读失败后不能无间隔循环');
    await tick(1); assert.equal(attempts, 3); assert.equal(view.rows[id].snapshot.snapshot_id, cases.new.current.snapshot_id); assert.equal(view.rows[id].stale, false);
    for (let i = 0; i < 10; i++) await tick(3000);
    assert.equal(attempts, 3, '成功后同版本不再重读');
    await tick(300000 - now); const atDeadline = statusCalls; await tick(3000); assert.equal(statusCalls, atDeadline); assert.match(view.startupNotice, /已暂停/);
  } finally { mounted = false; cleanup?.(); await drain(); assert.equal(timers.size, 0); }
}

test('同连接瞬时current失败保旧，恢复后自动取得同一已发布版本且停止重复读取', async () => {
  const cases = Object.fromEntries(['old', 'new'].map(id => [id, {
    current: { snapshot_id: id, observation_id: id, window: { anchor_date: '2026-10-30' } },
    status: { stage: 'completed', snapshot_id: id, observation_id: id },
  }]));
  await verifyEffect(cases);
});

test('真实存储首次／后续观察差异：同快照稳定，新快照失败后自动恢复且稳定', async () => {
  const python = fileURLToPath(new URL('../../../python/.venv/bin/python', import.meta.url));
  const fixture = fileURLToPath(new URL('../../../python/tests/startup_observation_fixture.py', import.meta.url));
  const paths = ['../../../python/src', '../../../python/tests'].map(path => fileURLToPath(new URL(path, import.meta.url))).join(delimiter);
  const cases = JSON.parse(execFileSync(python, ['-B', fixture], { encoding: 'utf8', env: { ...process.env, PYTHONPATH: paths, PYTHONDONTWRITEBYTECODE: '1' } }));
  for (const item of Object.values(cases)) {
    assert.equal(item.current.snapshot_id, item.status.snapshot_id);
    assert.notEqual(item.current.observation_id, item.status.observation_id);
    assert.equal(item.status.result, 'unchanged');
  }
  await verifyEffect(cases);
});
