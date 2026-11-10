/** P1-R0-01：保持真实页面打开，跨根重连不可继续显示旧根；不替换业务响应。 */
import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp, writeFile, readFile, readdir, realpath, rm } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { createServer } from 'node:net';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const repo = path.resolve(import.meta.dirname, '../../..');
const parent = process.env.WOLF_TEST_ROOT, source = process.env.WOLF_SYNTHETIC_DATA;
assert.ok(parent?.startsWith('/private/tmp/') && await realpath(parent) === parent);
assert.ok(source?.startsWith(parent + '/') && await realpath(source) === source);
const root = await mkdtemp(path.join(parent, 'overview-scope-'));
const py = process.env.WOLF_SCOPE_PYTHON;
assert.ok(py && path.isAbsolute(py), '需要调用者的已有Python解释器');
const { chromium } = await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE, 'index.mjs')));
const env = { ...process.env };
const record = { synthetic_only: true, root, children: [], requests: [], external_attempts: [], page_errors: [], cases: [] };
const children = [], streams = [];
let browser, service, host, before, beforeB, initialCache;

async function port() {
  const server = createServer();
  await new Promise((ok, fail) => server.once('error', fail).listen(0, '127.0.0.1', ok));
  const number = server.address().port; await new Promise(ok => server.close(ok)); return number;
}
const backend = await port(); let frontend = await port(); while (frontend === backend) frontend = await port();
const api = `http://127.0.0.1:${backend}`, origin = `http://127.0.0.1:${frontend}`;
record.ports = [backend, frontend];
async function hashes(dir) {
  const out = {};
  async function visit(folder) {
    for (const entry of (await readdir(folder, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
      const filename = path.join(folder, entry.name);
      if (entry.isDirectory()) await visit(filename);
      else out[path.relative(dir, filename)] = createHash('sha256').update(await readFile(filename)).digest('hex');
    }
  }
  await visit(dir); return out;
}
function start(label, command, args, extra = {}) {
  const stream = createWriteStream(path.join(root, label + '.log')); streams.push(stream);
  const child = spawn(command, args, { cwd: repo, env: { ...env, ...extra }, detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.pipe(stream); child.stderr.pipe(stream); children.push(child); record.children.push({ label, pid: child.pid }); return child;
}
async function stop(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const closed = once(child, 'close'); process.kill(-child.pid, 'SIGTERM');
  const timer = setTimeout(() => { try { process.kill(-child.pid, 'SIGKILL'); } catch {} }, 8000);
  try { await closed; } finally { clearTimeout(timer); }
}
async function ready(url, headers) {
  for (let i = 0; i < 150; i++) {
    try { if ((await fetch(url, { headers, signal: AbortSignal.timeout(1000) })).ok) return; } catch {}
    await new Promise(ok => setTimeout(ok, 100));
  }
  throw new Error('隔离服务未启动：' + url);
}
function startService(kind) {
  return start(kind + '-service-' + children.length, py, ['-B', '-m', 'pmi.service', 'serve', '--data-root', path.join(root, kind),
    '--port', String(backend), '--origin', origin]);
}
async function startPair(kind, mode = 'valid') {
  const command = 'from pathlib import Path;import json,sys;from pmi.service_config import ServiceConfig; c=ServiceConfig(Path(sys.argv[1]),int(sys.argv[2]),(sys.argv[3],)); Path(sys.argv[4]).write_text(json.dumps(c.public_descriptor()));Path(sys.argv[5]).write_text(json.dumps(c.public_index_descriptor()))';
  const result = spawnSync(py, ['-B', '-c', command, path.join(root, kind), String(backend), origin, root + '/legacy.json', root + '/index.json'], { cwd: repo, env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  record[kind + '_scope'] = JSON.parse(await readFile(root + '/legacy.json', 'utf8')).data_scope_id;
  if (mode === 'mismatch') {
    const descriptor = JSON.parse(await readFile(root + '/index.json', 'utf8'));
    descriptor.config_id = '0'.repeat(64); // 合成错误预期；真实服务ready保持原值。
    await writeFile(root + '/index.json', JSON.stringify(descriptor));
  }
  service = startService(kind);
  host = start(kind + '-host-' + mode + '-' + children.length, 'node', ['apps/desktop/node_modules/vite/bin/vite.js', 'preview', 'apps/desktop', '--config', 'apps/desktop/vite.config.ts', '--configLoader', 'runner', '--outDir', root + '/build'], {
    WOLF_DEV_PORT: String(frontend), WOLF_BROWSER_CONFIG: root + '/legacy.json',
    WOLF_INDEX_BROWSER_CONFIG: mode === 'missing' ? '' : root + '/index.json', WOLF_VITE_CACHE: root + '/vite-cache',
  });
  await ready(api + '/api/session/ready', { 'X-Wolf-Client': '1' }); await ready(origin + '/__wolf/config');
}
try {
  initialCache = await readFile(path.join(repo, 'apps/desktop/tsconfig.tsbuildinfo')).catch(error=>{if(error.code==='ENOENT')return null;throw error;});
  await cp(source, root + '/a', { recursive: true, errorOnExist: true }); await mkdir(root + '/b');
  const initialized = spawnSync(py, ['-B','-c','from pathlib import Path;import sys;from sqlite_fixture import initialize;initialize(Path(sys.argv[1]))',root+'/b'],{cwd:repo,env,encoding:'utf8'});
  assert.equal(initialized.status,0,initialized.stderr);beforeB=await hashes(root+'/b');
  before = await hashes(root + '/a');
  await writeFile(root + '/environment-before.json', JSON.stringify({ root, source, before, ports: record.ports, user_config_changes: false }, null, 2));
  // 使用正式构建与相同受控宿主，避免开发服务器重启时刷新页面掩盖状态缺陷。
  const build = spawnSync(process.execPath, ['apps/desktop/node_modules/vite/bin/vite.js', 'build', 'apps/desktop', '--config', 'apps/desktop/vite.config.ts', '--configLoader', 'runner', '--outDir', root + '/build'], { cwd: repo, env: { ...env, WOLF_VITE_CACHE: root + '/vite-cache' }, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  await writeFile(root + '/build.log', build.stdout + build.stderr); assert.equal(build.status, 0, build.stderr);
  await startPair('a');
  browser = await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}), ...(process.env.WOLF_BROWSER_EXECUTABLE ? {} : {channel:'chromium'}), headless: true, proxy: { server: 'http://127.0.0.1:9', bypass: '127.0.0.1' } });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
  const page = await context.newPage();
  context.on('request', request => {
    const url = request.url(); record.requests.push({ url, method: request.method(), document: request.isNavigationRequest() });
    if (!url.startsWith(origin + '/') && !url.startsWith(api + '/') && !url.startsWith('blob:' + origin + '/')) record.external_attempts.push(url);
  });
  page.on('pageerror', error => record.page_errors.push(String(error)));
  const loaded = async () => { await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))); await page.getByText('读取结束 · 当前读取不采集新行情', { exact: true }).waitFor(); };
  const reconnect = () => page.getByRole('button', { name: '重新连接', exact: true }).click();
  async function emptyOfA() {
    assert.equal(await page.locator('.m-metric-value').count(), 0);
    assert.equal(await page.locator('.m-price-chart canvas, .m-table canvas').count(), 0);
    assert.equal(await page.locator('.m-up, .m-down, .m-ma-readout').count(), 0);
    assert.doesNotMatch(await page.locator('.m-notes').innerText(), /快照：|观察：|最新涨跌公式：|https?:\/\//);
    assert.match(await page.locator('.m-footer').innerText(), /数据来源：暂无数据/);
  }
  async function switchRoot(kind, mode) {
    await stop(host); await stop(service); await startPair(kind, mode);
    const response = page.waitForResponse(value => value.url() === api + '/api/session/ready' && value.status() === 200);
    await reconnect(); assert.equal((await (await response).json()).data_scope_id, record[kind + '_scope']);
  }
  await page.goto(origin); await loaded();
  const values = await page.locator('.m-metric-value').allTextContents(); assert.equal(values.length, 4);
  await page.getByLabel('显示数据说明').check();
  await stop(service); await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await page.getByRole('button', { name: '重新读取', exact: true }).waitFor();
  await page.waitForFunction(() => !Array.from(document.querySelectorAll('button')).find(button => button.textContent === '重新读取').disabled);
  assert.deepEqual(await page.locator('.m-metric-value').allTextContents(), values);
  await page.locator('.m-table tbody tr').first().getByText(/上次数据/).waitFor();
  assert.equal(await page.locator('.m-price-chart canvas').count(),0);
  service = startService('a'); await ready(api + '/api/session/ready', { 'X-Wolf-Client': '1' }); await reconnect(); await loaded();
  assert.deepEqual(await page.locator('.m-metric-value').allTextContents(), values);
  assert.doesNotMatch(await page.locator('.m-table tbody').innerText(),/上次数据/);
  record.cases.push('same-root-offline-keeps-labelled-snapshot-and-reconnect-recovers');

  // 只延迟真实响应的正文完成时机，不改fetch、响应内容或数据来源。
  await page.evaluate(api => {
    const original = Response.prototype.json, held = [];
    Response.prototype.json = async function () {
      const value = await original.call(this);
      if (this.url.startsWith(api + '/api/index-series/') && value.instrument && value.index_id) await new Promise(resolve => held.push(resolve));
      return value;
    };
    window.__scopeHeld = held;
    window.__scopeRelease = () => { Response.prototype.json = original; held.forEach(resolve => resolve()); };
  }, api);
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await page.waitForFunction(() => window.__scopeHeld.length === 4);
  await switchRoot('b', 'missing'); assert.notEqual(record.a_scope, record.b_scope);
  await page.locator('.m-connection').getByText('指数连接未配置', { exact: true }).waitFor();
  await emptyOfA(); await page.evaluate(() => window.__scopeRelease());
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))); await emptyOfA();
  record.cases.push('new-root-missing-v2-clears-all-a-display-and-rejects-four-late-bodies');
  await page.evaluate(() => { const label = document.createElement('div'); label.textContent = '隔离合成数据 · 空B根，无A根残留'; label.id = 'scope-test-label'; Object.assign(label.style, { position: 'fixed', right: '12px', bottom: '12px', background: '#fff1c2', color: '#3f3200', padding: '10px', zIndex: '100' }); document.body.append(label); });
  await page.screenshot({ path: root + '/cross-root-missing-v2.png', fullPage: true });

  await switchRoot('a', 'valid'); await loaded(); assert.equal(await page.locator('.m-metric-value').count(), 4);
  await page.evaluate(api => {
    const original = Response.prototype.json, held = [];
    Response.prototype.json = async function () {
      const value = await original.call(this);
      if (this.url.startsWith(api + '/api/index-series/') && value.series && value.index_id) await new Promise(resolve => held.push(resolve));
      return value;
    };
    window.__scopeHeld = held;
    window.__scopeRelease = () => { Response.prototype.json = original; held.forEach(resolve => resolve()); };
  }, api);
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await page.waitForFunction(() => window.__scopeHeld.length === 1);
  await switchRoot('b', 'missing');
  await page.locator('.m-connection').getByText('指数连接未配置', { exact: true }).waitFor();
  await emptyOfA(); await page.evaluate(() => window.__scopeRelease());
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))); await emptyOfA();
  record.cases.push('late-range-body-cannot-repopulate-new-root');
  await switchRoot('a', 'valid'); await loaded(); assert.equal(await page.locator('.m-metric-value').count(), 4);
  await switchRoot('b', 'mismatch');
  await page.locator('.m-connection').getByText('指数服务实例或冻结配置不匹配，请重新连接', { exact: true }).waitFor(); await emptyOfA();
  record.cases.push('new-root-v2-ready-mismatch-clears-all-a-display');
  await page.screenshot({ path: root + '/cross-root-ready-mismatch.png', fullPage: true });
  await switchRoot('a', 'valid'); await loaded(); assert.equal(await page.locator('.m-metric-value').count(), 4);
  await page.evaluate(() => {
    const original = Response.prototype.json;
    Response.prototype.json = async function () {
      const value = await original.call(this);
      if (this.url.endsWith('/api/session/ready')) await new Promise(resolve => {
        window.__scopeReadyRelease = () => { Response.prototype.json = original; resolve(); };
      });
      return value;
    };
  });
  await switchRoot('b', 'valid'); await page.waitForFunction(() => typeof window.__scopeReadyRelease === 'function');
  const oldInstance = (await (await fetch(api + '/api/session/ready', { headers: { 'X-Wolf-Client': '1' } })).json()).instance_id;
  await stop(service); service = startService('b'); await ready(api + '/api/session/ready', { 'X-Wolf-Client': '1' });
  const newInstance = (await (await fetch(api + '/api/session/ready', { headers: { 'X-Wolf-Client': '1' } })).json()).instance_id;
  assert.notEqual(oldInstance, newInstance); await page.evaluate(() => window.__scopeReadyRelease());
  await page.locator('.m-connection').getByText('指数服务实例或冻结配置不匹配，请重新连接', { exact: true }).waitFor(); await emptyOfA();
  record.cases.push('new-root-v1-v2-instance-change-clears-all-a-display');
  await switchRoot('b', 'valid'); await loaded(); await emptyOfA();
  assert.equal(await page.locator('.m-table .m-metric-value').count(),0);assert.match(await page.locator('.m-empty').innerText(),/暂无数据/);
  record.cases.push('same-b-root-valid-reconnect-is-truly-empty');
  await switchRoot('a', 'valid'); await loaded(); assert.deepEqual(await page.locator('.m-metric-value').allTextContents(), values);
  assert.equal(await page.getByRole('button', {name:/沪深300资料|002245资料/}).count(),0);
  record.cases.push('return-to-a-restores-prices-with-retired-entries-absent');
  assert.deepEqual(record.external_attempts, []); assert.deepEqual(record.page_errors, []);
  assert.ok(record.requests.every(request => request.method === 'GET'));
  assert.equal(record.requests.filter(request => request.document && request.url === origin + '/').length, 1, '跨根检查不得通过刷新页面重置状态');
  record.passed = true;
} catch (error) { record.failure = String(error.stack || error); process.exitCode = 1; }
finally {
  if (browser) { await browser.close(); record.browser_closed = !browser.isConnected(); }
  for (const child of [...children].reverse()) await stop(child);
  for (const stream of streams) stream.end();
  record.exits = children.map(child => ({ pid: child.pid, code: child.exitCode, signal: child.signalCode }));
  if (before) record.synthetic_a_unchanged = JSON.stringify(await hashes(root + '/a')) === JSON.stringify(before);
  record.synthetic_b_empty = JSON.stringify(await hashes(root+'/b'))===JSON.stringify(beforeB);
  record.ports_closed = {};
  for (const number of record.ports) {
    try { await fetch(`http://127.0.0.1:${number}/`, { signal: AbortSignal.timeout(1000) }); record.ports_closed[number] = false; }
    catch { record.ports_closed[number] = true; }
  }
  const finalCache=await readFile(path.join(repo, 'apps/desktop/tsconfig.tsbuildinfo')).catch(error=>{if(error.code==='ENOENT')return null;throw error;});
  record.tsbuildinfo_unchanged=initialCache===null ? finalCache===null : !!initialCache && !!finalCache && initialCache.equals(finalCache);
  await writeFile(root + '/result.json', JSON.stringify(record, null, 2) + '\n');
  for (const folder of ['a', 'b', 'vite-cache']) await rm(path.join(root, folder), { recursive: true, force: true });
  console.log(JSON.stringify({ root, passed: record.passed, cases: record.cases, failure: record.failure, ports_closed: record.ports_closed }));
  assert.ok(record.browser_closed && record.synthetic_a_unchanged && record.synthetic_b_empty && record.tsbuildinfo_unchanged && Object.values(record.ports_closed).every(Boolean));
}
