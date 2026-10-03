/** 第1轮独立复核：复用已提交调度夹具，运行真实 App 的晚到任务结果路径；不改业务或测试。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');

const root = path.resolve(process.argv[2] || '.');
const filename = path.join(root, 'apps/desktop/scripts/update_recovery.test.cjs');
const source = fs.readFileSync(filename, 'utf8');
const boundary = source.indexOf('for (const stage of');
assert.ok(boundary > 0, '已取得实际调度夹具，不执行或改写已有测试');
const moduleFixture = { exports: {} };
vm.runInNewContext(source.slice(0, boundary) + '\nmodule.exports = harness;', {
  module: moduleFixture, exports: moduleFixture.exports, require: createRequire(filename),
  __dirname: path.dirname(filename), setImmediate, AbortSignal, URL, console,
});

async function reproduce(terminal) {
  const h = await moduleFixture.exports({ stage: 'interrupted', job_id: 'previous-job', message: '上次中断' });
  h.state.post = async () => { throw new Error('合成响应超时，服务端稍后受理'); };
  try {
    await h.click('更新日线');
    await h.advance(120001);
    await h.click('核对结果');
    assert.equal(h.button('更新日线').props.disabled, false, 'R01原卡死已解除');
    assert.match(h.text(), /未发现新的更新任务/);
    // 原POST超时后延迟受理；旧 interrupted 仍保留核对按钮，用户只读核对新任务。
    h.state.status = { ...h.state.status, stage: 'fetching_sina', job_id: 'late-new-job' };
    await h.click('核对结果');
    assert.equal(h.button('更新日线').props.disabled, true);
    assert.match(h.text(), /获取新浪日线/);
    const message = terminal === 'completed' ? '新任务检查完成' : '新任务校验失败';
    h.state.status = { ...h.state.status, stage: terminal, message,
      last_success_at: terminal === 'completed' ? '2026-10-03T01:00:00Z' : h.state.status.last_success_at };
    await h.advance(800);
    assert.equal(h.button('更新日线').props.disabled, false);
    assert.equal(h.state.posts, 1, '只读核对没有新增采集');
    const result = { terminal, serverJob: h.state.status.job_id, posts: h.state.posts,
      sliceReads: h.state.slices, staleNoticeVisible: h.text().includes('未发现新的更新任务'),
      newResultVisible: h.text().includes(message), lastSuccessAt: h.state.status.last_success_at };
    assert.equal(result.staleNoticeVisible, true);
    assert.equal(result.newResultVisible, false);
    // 对照：显式新POST会清理notice；问题限定于恢复后对晚到任务的只读核对。
    h.state.post = async () => h.response({ ...h.state.status, stage: 'failed', job_id: 'explicit-new-job', message: '显式新任务结果' });
    await h.click('更新日线');
    assert.match(h.text(), /显式新任务结果/);
    assert.ok(!h.text().includes('未发现新的更新任务'));
    result.explicitPostControlClearsNotice = true;
    return result;
  } finally { h.close(); }
}

(async () => {
  console.log(JSON.stringify({ finding: 'R02', source: 'R01 fix 071cc57',
    scenarios: [await reproduce('completed'), await reproduce('failed')] }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
