/** 独立审查探针：运行固定源码的真实 App 回调，替代 React 调度和网络，不改业务代码。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');

const sourceRoot = path.resolve(process.argv[2] || '.');
const desktop = path.join(sourceRoot, 'apps/desktop');
const dependency = createRequire(path.join(desktop, 'package.json'));
const ts = dependency('typescript');
const code = ts.transpileModule(fs.readFileSync(path.join(desktop, 'src/App.tsx'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

async function scenario(initialJob) {
  const hooks = [], effects = [], timers = new Map();
  let cursor = 0, clock = 0, timerId = 0, tree, postCount = 0, getCount = 0;
  let status = { stage: initialJob ? 'completed' : 'idle', job_id: initialJob, enabled: true };
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { value: initial };
      return [hooks[index].value, next => { hooks[index].value = typeof next === 'function' ? next(hooks[index].value) : next; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { current: initial };
      return hooks[index];
    },
    useEffect(callback, dependencies) {
      const index = cursor++;
      const previous = hooks[index];
      if (!previous || dependencies.some((value, i) => value !== previous.dependencies[i])) {
        hooks[index] = { dependencies };
        effects.push(() => { previous?.cleanup?.(); hooks[index].cleanup = callback(); });
      }
    },
  };
  class ClockDate extends Date { static now() { return clock; } }
  const module = { exports: {} };
  const sandbox = {
    module, exports: module.exports,
    require: name => name === 'react' ? react : name === '@tauri-apps/api/core'
      ? { isTauri: () => true, invoke: async () => 'synthetic-session' } : dependency(name),
    AbortSignal, URL, Date: ClockDate,
    window: { setTimeout: callback => { timers.set(++timerId, callback); return timerId; }, clearTimeout: id => timers.delete(id) },
    fetch: async (url, options) => {
      if (options.method === 'POST') { postCount++; throw new Error('synthetic request never delivered'); }
      if (url === '/api/slice/update') { getCount++; return { ok: true, json: async () => ({ ...status }) }; }
      return { ok: true, json: async () => ({ snapshot_id: 'fixed', instrument_code: '002245', instrument_name: '合成',
        exchange: 'SZSE', source_id: 'synthetic', market_contract: { raw_publisher: 'synthetic' },
        calendar_dates: ['2026-09-30'], bars: [], observed_count: 0, open_session_count: 1,
        unknown_missing_dates: [], complete_through_date: '2026-09-30', documents: [] }) };
    },
  };
  vm.runInNewContext(code, sandbox, { filename: 'fixed-App.cjs' });
  async function settle() {
    for (let step = 0; step < 8; step++) {
      cursor = 0; tree = module.exports.App();
      while (effects.length) effects.shift()();
      await new Promise(resolve => setImmediate(resolve));
    }
  }
  function nodes(value) {
    if (Array.isArray(value)) return value.flatMap(nodes);
    if (!value || typeof value !== 'object') return [];
    return [value, ...nodes(value.props?.children)];
  }
  function button(label) { return nodes(tree).find(node => node.type === 'button' && node.props.children === label); }
  async function exhaustPoll() {
    clock += 120001;
    const callbacks = [...timers.values()]; timers.clear();
    for (const callback of callbacks) callback();
    await settle();
  }
  await settle();
  assert.equal(button('更新日线').props.disabled, false);
  await button('更新日线').props.onClick(); await settle(); await exhaustPoll();
  const rows = [];
  for (let check = 1; check <= 2; check++) {
    assert.equal(button('更新日线').props.disabled, true);
    assert.equal(button('核对结果').props.disabled, false);
    await button('核对结果').props.onClick(); await settle(); await exhaustPoll();
    rows.push({ check, postCount, getCount, updateDisabled: button('更新日线').props.disabled,
      checkDisabled: button('核对结果').props.disabled, serverStage: status.stage, serverJob: status.job_id });
  }
  assert.equal(postCount, 1);
  // 对照：服务端真正产生新任务时，同一真实回调可正常恢复按钮。
  status = { stage: 'failed', job_id: 'new-server-job', enabled: true, message: 'synthetic terminal result' };
  await button('核对结果').props.onClick(); await settle();
  assert.equal(button('更新日线').props.disabled, false);
  return { initialJob, rows, newJobControlRestoresButton: true };
}

(async () => {
  console.log(JSON.stringify({ finding: 'R01', scenarios: [await scenario(null), await scenario('previous-completed-job')] }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
