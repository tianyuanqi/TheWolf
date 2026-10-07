/** 运行真实 App 按钮和轮询回调；隔离替代时钟、React 调度及本地传输，不访问来源或数据根。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { test } = require('node:test');

const desktop = path.resolve(__dirname, '..');
const dependency = createRequire(path.join(desktop, 'package.json'));
const ts = dependency('typescript');
const code = ts.transpileModule(fs.readFileSync(path.join(desktop, 'src/LegacySliceView.tsx'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const oldSuccess = '2026-10-02T16:22:42.271564Z';
const oldMessage = '旧任务检查成功';

/** 每个实例有独立调度器；末尾卸载真实 effect，校验不遗留任务或计时器。 */
async function harness(initial = { stage: 'idle', job_id: null }) {
  const hooks = [], effects = [], timers = new Map();
  let cursor = 0, clock = 1000, timerId = 0, tree;
  const state = { status: { ...initial, enabled: true, last_success_at: oldSuccess },
    posts: 0, gets: 0, slices: 0, getFails: false,
    post: async () => { throw new Error('合成请求未送达'); } };
  const react = {
    useState(initialValue) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { value: initialValue };
      return [hooks[index].value, next => {
        hooks[index].value = typeof next === 'function' ? next(hooks[index].value) : next;
      }];
    },
    useRef(initialValue) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { current: initialValue };
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
  const response = value => ({ ok: true, json: async () => ({ ...value }) });
  vm.runInNewContext(code, {
    module, exports: module.exports,
    require: name => name === 'react' ? react : name === '@tauri-apps/api/core'
      ? { isTauri: () => true, invoke: async () => 'synthetic-session' } : dependency(name),
    AbortSignal, URL, Date: ClockDate,
    window: { setTimeout: callback => { timers.set(++timerId, callback); return timerId; },
      clearTimeout: id => timers.delete(id) },
    fetch: async (url, options) => {
      if (options.method === 'POST') { state.posts++; return state.post(); }
      if (url === '/api/slice/update') {
        state.gets++;
        if (state.getFails) throw new Error('合成本地读取失败');
        return response(state.status);
      }
      assert.equal(url, '/api/slice');
      state.slices++;
      return response({ snapshot_id: 'fixed', instrument_code: '002245', instrument_name: '合成',
        exchange: 'SZSE', source_id: 'synthetic', market_contract: { raw_publisher: 'synthetic' },
        calendar_dates: ['2026-09-30'], bars: [], observed_count: 0, open_session_count: 1,
        unknown_missing_dates: [], complete_through_date: '2026-09-30', documents: [] });
    },
  }, { filename: 'actual-App.cjs' });
  async function settle() {
    for (let step = 0; step < 8; step++) {
      cursor = 0; tree = module.exports.LegacySliceView({ sessionToken: "synthetic-session" });
      while (effects.length) effects.shift()();
      await new Promise(resolve => setImmediate(resolve));
    }
  }
  function nodes(value) {
    if (Array.isArray(value)) return value.flatMap(nodes);
    if (!value || typeof value !== 'object') return [];
    return [value, ...nodes(value.props?.children)];
  }
  function text(value) {
    if (Array.isArray(value)) return value.map(text).join('');
    if (!value || typeof value !== 'object') return value == null ? '' : String(value);
    return text(value.props?.children);
  }
  function button(label) { return nodes(tree).find(node => node.type === 'button' && node.props.children === label); }
  async function click(label) {
    const node = button(label);
    assert.ok(node, `存在按钮：${label}`);
    assert.equal(node.props.disabled, false, `按钮可操作：${label}`);
    await node.props.onClick(); await settle();
  }
  async function advance(ms) {
    clock += ms;
    const callbacks = [...timers.values()]; timers.clear();
    for (const callback of callbacks) callback();
    await settle();
  }
  await settle();
  return { state, response, settle, button, click, advance,
    text: () => text(tree),
    close: () => { for (const hook of hooks) hook?.cleanup?.(); assert.equal(timers.size, 0); } };
}

for (const stage of ['idle', 'completed', 'failed', 'interrupted']) {
  test(`R01：请求未送达，核对 ${stage} 后可显式重新更新`, async () => {
    const h = await harness({ stage, job_id: stage === 'idle' ? null : 'old-job', message: oldMessage });
    try {
      await h.click('更新日线');
      assert.equal(h.button('更新日线').props.disabled, true);
      assert.ok(!h.text().includes(oldMessage), '不把旧结果显示为本次结果');
      await h.advance(120001);
      assert.equal(h.button('更新日线').props.disabled, true, '等待结束仍须核对');
      await h.click('核对结果');
      assert.equal(h.button('更新日线').props.disabled, false);
      assert.match(h.text(), /未发现新的更新任务/);
      assert.ok(!h.text().includes(oldMessage));
      assert.equal(h.state.posts, 1, '核对不自动重发');
      assert.equal(h.state.slices, 1, '不把旧完成任务当作新成功刷新');
      assert.equal(h.state.status.last_success_at, oldSuccess);
      await h.click('更新日线');
      assert.equal(h.state.posts, 2, '仅用户再次操作才发送新请求');
    } finally { h.close(); }
  });
}

for (const terminal of ['completed', 'failed', 'interrupted']) {
  test(`响应丢失但已有新任务：${terminal} 正确终止，且不重发`, async () => {
    const h = await harness({ stage: 'completed', job_id: 'old-job' });
    h.state.post = async () => {
      h.state.status = { ...h.state.status, stage: 'fetching_sina', job_id: 'new-job' };
      throw new Error('合成响应丢失');
    };
    try {
      await h.click('更新日线');
      assert.equal(h.button('更新日线').props.disabled, true);
      h.state.status = { ...h.state.status, stage: terminal, message: '新任务结果' };
      await h.advance(800);
      assert.equal(h.button('更新日线').props.disabled, false);
      assert.match(h.text(), /新任务结果/);
      assert.equal(h.state.posts, 1);
      assert.equal(h.state.slices, terminal === 'completed' ? 2 : 1);
    } finally { h.close(); }
  });
}

test('已提交结果但响应丢失：直接读到新完成任务，无重复 POST', async () => {
  const h = await harness();
  h.state.post = async () => {
    h.state.status = { ...h.state.status, stage: 'completed', job_id: 'committed', message: '新提交成功' };
    throw new Error('合成响应丢失');
  };
  try {
    await h.click('更新日线');
    assert.equal(h.button('更新日线').props.disabled, false);
    assert.match(h.text(), /新提交成功/);
    assert.equal(h.state.posts, 1);
    assert.equal(h.state.slices, 2);
  } finally { h.close(); }
});

test('POST 被拒绝：只读核对后解除等待，不声称更新成功', async () => {
  const h = await harness();
  h.state.post = async () => ({ ok: false, status: 503, json: async () => ({ detail: { message: '合成拒绝' } }) });
  try {
    await h.click('更新日线'); await h.advance(120001); await h.click('核对结果');
    assert.equal(h.button('更新日线').props.disabled, false);
    assert.match(h.text(), /未发现新的更新任务/);
    assert.equal(h.state.posts, 1);
    assert.equal(h.state.slices, 1);
  } finally { h.close(); }
});

test('GET 故障不能解除等待；恢复后成功核对可恢复按钮', async () => {
  const h = await harness();
  try {
    await h.click('更新日线');
    h.state.getFails = true;
    await h.advance(120001); await h.click('核对结果'); await h.advance(120001);
    assert.equal(h.button('更新日线').props.disabled, true);
    assert.equal(h.state.posts, 1);
    h.state.getFails = false;
    await h.click('核对结果');
    assert.equal(h.button('更新日线').props.disabled, false);
    assert.equal(h.state.posts, 1);
  } finally { h.close(); }
});

test('同编号任务仍在运行时，核对不能解除更新禁用', async () => {
  const h = await harness();
  try {
    await h.click('更新日线'); await h.advance(120001);
    h.state.status = { ...h.state.status, stage: 'publishing' };
    await h.click('核对结果');
    assert.equal(h.button('更新日线').props.disabled, true);
    await h.advance(120001);
    assert.equal(h.button('更新日线').props.disabled, true);
    assert.equal(h.state.posts, 1);
  } finally { h.close(); }
});

test('重复点击保护及正常受理后运行/完成路径保持', async () => {
  const h = await harness();
  let accept;
  h.state.post = () => new Promise(resolve => { accept = resolve; });
  try {
    const handler = h.button('更新日线').props.onClick;
    const first = handler(); await handler();
    assert.equal(h.state.posts, 1);
    h.state.status = { ...h.state.status, stage: 'validating', job_id: 'accepted' };
    accept(h.response(h.state.status)); await first; await h.settle();
    assert.equal(h.button('更新日线').props.disabled, true);
    h.state.status = { ...h.state.status, stage: 'completed', message: '正常检查成功' };
    await h.advance(800);
    assert.equal(h.button('更新日线').props.disabled, false);
    assert.equal(h.state.posts, 1);
    assert.equal(h.state.slices, 2);
  } finally { h.close(); }
});

for (const route of ['direct', 'running', 'poll']) {
  for (const terminal of ['completed', 'failed', 'interrupted']) {
    test(`R02：恢复后只读核对晚到任务，${route}/${terminal} 清除过期提示`, async () => {
      const h = await harness({ stage: 'interrupted', job_id: 'old-job', message: '旧中断结果' });
      try {
        await h.click('更新日线'); await h.advance(120001); await h.click('核对结果');
        assert.equal(h.button('更新日线').props.disabled, false, '保持R01有限恢复');
        assert.match(h.text(), /未发现新的更新任务/);
        await h.click('核对结果');
        assert.match(h.text(), /未发现新的更新任务/, '旧任务未变时仍保留恢复提示');
        assert.equal(h.state.slices, 1);
        if (route === 'running') {
          h.state.status = { ...h.state.status, stage: 'fetching_sina', job_id: 'late-job' };
          await h.click('核对结果');
          assert.equal(h.button('更新日线').props.disabled, true);
          assert.match(h.text(), /获取新浪日线/);
        }
        if (route === 'poll') {
          // 人工 GET 暂时失败，随后由轮询首次发现晚到任务，单独覆盖轮询清理提示的路径。
          h.state.getFails = true;
          await h.click('核对结果');
          assert.equal(h.button('更新日线').props.disabled, true);
          h.state.getFails = false;
        }
        const message = `晚到任务真实结果：${terminal}`;
        const successAt = terminal === 'completed' ? '2026-10-03T01:00:00Z' : oldSuccess;
        h.state.status = { ...h.state.status, job_id: 'late-job', stage: terminal, message,
          last_success_at: successAt };
        if (route === 'direct') await h.click('核对结果');
        else await h.advance(800);
        assert.match(h.text(), new RegExp(message));
        assert.ok(!h.text().includes('未发现新的更新任务'));
        assert.equal(h.button('更新日线').props.disabled, false);
        assert.equal(h.state.posts, 1, '全部核对和轮询均只读，不自动重发');
        assert.equal(h.state.slices, terminal === 'completed' ? 2 : 1, '仅成功刷新，失败和中断保留旧数据');
        const displayedSuccess = new Date(successAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
        assert.ok(h.text().includes(displayedSuccess), '消费者显示服务端确认的成功时间');
      } finally { h.close(); }
    });
  }
}
