/** 合成三年行情的实际页面性能；导航起点计时，完整渲染后两帧才停止。 */
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE, 'index.mjs')).href);
const root = process.env.WOLF_PERFORMANCE_ROOT;
const browser = await chromium.launch({ ...(process.env.WOLF_BROWSER_EXECUTABLE ? { executablePath: process.env.WOLF_BROWSER_EXECUTABLE } : {}),
  headless: true, proxy: { server: 'http://127.0.0.1:9', bypass: '127.0.0.1' } });
const result = { samples: [], switches: [], errors: [], requests: [], external: [], faults: [], functional: false, targetMet: false };
const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
let failUnselected = false, attempt = 0, withheldFull;
const requestAttempts = new WeakMap();
await context.route('**/*', async route => {
  const u = new URL(route.request().url());
  if (withheldFull && decodeURIComponent(u.pathname) === '/api/index-series/szse:399001:price/view'
      && u.searchParams.get('detail') !== 'overview') {
    const held = withheldFull; withheldFull = undefined; held.seen(); await held.wait;
    return route.continue();
  }
  if (failUnselected && decodeURIComponent(u.pathname) === '/api/index-series/sse:000688:price/view') return route.abort('failed');
  if (u.protocol === 'http:' && u.hostname === '127.0.0.1') return route.continue();
  result.external.push(u.href); return route.abort();
});
const page = await context.newPage();
page.on('pageerror', error => result.errors.push(String(error)));
page.on('request', request => requestAttempts.set(request, attempt));
page.on('response', response => result.requests.push({ attempt: requestAttempts.get(response.request()), url: response.url(), status: response.status() }));
async function complete(kind, start = 0) {
  await page.getByText('读取结束 · 当前读取不采集新行情', { exact: true }).waitFor({ timeout: 180000 });
  await page.locator('.m-price-chart canvas').waitFor();
  await page.locator('.m-activity-chart canvas').waitFor();
  assert.equal(await page.locator('.m-table tbody tr').count(), 5);
  const text = await page.locator('.m-table tbody').innerText();
  assert.ok(!text.includes('暂无数据'), '完整样本不能有读取缺失');
  assert.ok(!text.includes('上次数据'), '本轮读取未成功，不能以旧行计完整');
  assert.equal(await page.locator('.m-warning').count(), 0, '本轮读取有警告，不能计完整');
  const responses = result.requests.filter(x => x.attempt === attempt);
  for (const id of ['sse:000001:price', 'szse:399001:price', 'szse:399006:price', 'sse:000688:price']) {
    assert.ok(responses.some(x => decodeURIComponent(new URL(x.url).pathname) === `/api/index-series/${id}/view` && x.status === 200),
      `本轮没有成功读取 ${id}`);
  }
  assert.ok(!responses.some(x => new URL(x.url).pathname.startsWith('/api/') && x.status >= 400), '本轮接口读取失败');
  const value = await page.evaluate(async () => {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return { ms: performance.now(), resources: performance.getEntriesByType('resource').map(x => ({ name: x.name, ms: x.duration, bytes: x.transferSize })) };
  });
  result.samples.push({ kind, ms: value.ms - start, resources: value.resources });
}
try {
  await page.goto(process.env.WOLF_UI_ORIGIN, { waitUntil: 'commit' }); await complete('first-cold-service');
  const firstViews = result.requests.filter(x => new URL(x.url).pathname.endsWith('/view'));
  const firstPrices = firstViews.filter(x => new URL(x.url).pathname.startsWith('/api/index-series/'));
  assert.equal(firstPrices.length, 5);
  assert.equal(firstPrices.filter(x => new URL(x.url).searchParams.get('detail') === 'overview').length, 4);
  assert.deepEqual(firstViews.filter(x => new URL(x.url).pathname.startsWith('/api/market-activity/'))
    .map(x => decodeURIComponent(new URL(x.url).pathname)).sort(),
    ['/api/market-activity/cn-a-turnover/view', '/api/market-activity/sse:000001:price/view'].sort());
  for (let i = 0; i < Number(process.env.WOLF_PERFORMANCE_SAMPLES); i++) {
    attempt++;
    await page.reload({ waitUntil: 'commit' }); await complete('reload');
    attempt++;
    const start = await page.evaluate(() => performance.now());
    await page.getByRole('button', { name: '重新连接', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.m-connection')?.textContent.includes('读取结束'));
    await complete('reconnect', start);
  }
  // 实际故障反例：非选中指数重连失败时产品保旧，但基准不得计成功。
  failUnselected = true; attempt++;
  const sampleCount = result.samples.length;
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.m-connection')?.textContent.includes('读取结束'));
  await assert.rejects(() => complete('must-not-count'), /本轮读取未成功|本轮读取有警告|本轮没有成功读取/);
  assert.equal(result.samples.length, sampleCount);
  assert.match(await page.locator('.m-table tbody tr').filter({ has: page.getByRole('button', { name: /科创50/ }) }).innerText(), /上次数据/);
  const legacyWouldAccept = await page.locator('.m-activity-chart canvas').count() > 0
    && await page.locator('.m-table tbody tr').count() === 5
    && !(await page.locator('.m-table tbody').innerText()).includes('暂无数据');
  assert.equal(legacyWouldAccept, true, '反例须复现旧判据会误认成功的路径');
  result.faults.push({ case: 'unselected-current-failure-keeps-old', legacyWouldAccept, rejected: true, successSamplesUnchanged: true });
  failUnselected = false; attempt++;
  const recoveryStart = await page.evaluate(() => performance.now());
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.m-connection')?.textContent.includes('读取结束'));
  await complete('recovered-after-fault', recoveryStart);
  // 切换单独计时；成功必须包含完整价格图、配对量额图、均线及无失败状态。
  const indices = [['szse:399001:price','深证成指'],['szse:399006:price','创业板指'],['sse:000688:price','科创50'],['sse:000001:price','上证指数']];
  for (const repeat of [false,true]) for (const [id,label] of indices) {
    const before = result.requests.length;
    const start = await page.evaluate(() => performance.now());
    await page.getByRole('button', { name: new RegExp(label) }).click();
    await page.getByRole('heading', { name: label, exact: true }).waitFor();
    await page.getByText('读取结束 · 当前读取不采集新行情', { exact: true }).waitFor();
    await page.locator('.m-price-chart canvas').waitFor();
    await page.locator('.m-activity-chart canvas').waitFor();
    assert.equal(await page.locator('.m-warning').count(),0);
    assert.match(await page.locator('#overview-readout').innerText(), /开.*高.*低.*收/s);
    const ms = await page.evaluate(async () => { await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return performance.now(); });
    const reads = result.requests.slice(before).filter(x=>new URL(x.url).pathname.endsWith('/view'));
    assert.equal(reads.filter(x=>decodeURIComponent(new URL(x.url).pathname)===`/api/market-activity/${id}/view` && x.status===200).length,repeat || id==='sse:000001:price'?0:1);
    const full = reads.filter(x=>new URL(x.url).pathname.startsWith('/api/index-series/'));
    assert.equal(full.length,repeat || id==='sse:000001:price'?0:1);
    assert.ok(full.every(x=>new URL(x.url).searchParams.get('detail')!=='overview' && x.status===200));
    result.switches.push({id,repeat,ms:ms-start});
  }
  attempt++;
  await page.reload({waitUntil:'commit'});await complete('rapid-switch-reset');
  let release, seen;
  const started = new Promise(resolve=>{seen=resolve});
  withheldFull = {seen,wait:new Promise(resolve=>{release=resolve})};
  const beforeRapid = result.requests.length;
  try {
    await page.getByRole('button',{name:/深证成指/}).click();await started;
    await page.getByRole('button',{name:/创业板指/}).click();
    await page.getByRole('button',{name:/深证成指/}).click();
    assert.match(await page.locator('.m-connection').innerText(),/正在读取所选范围/);
    assert.equal(await page.locator('.m-price-chart canvas').count(),0,'概况不能绘成已取得完整详情');
  } finally {release();}
  await page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor();
  await page.locator('.m-price-chart canvas').waitFor();await page.locator('.m-activity-chart canvas').waitFor();
  const rapid = result.requests.slice(beforeRapid);
  assert.equal(rapid.filter(x=>decodeURIComponent(new URL(x.url).pathname)==='/api/index-series/szse:399001:price/view').length,1);
  assert.equal(rapid.filter(x=>decodeURIComponent(new URL(x.url).pathname)==='/api/market-activity/szse:399001:price/view').length,1);
  result.faults.push({case:'held-full-rapid-switch-no-partial-success-or-duplicate',passed:true});
  await page.evaluate(() => {
    const badge = document.createElement('div'); badge.textContent = '隔离合成数据 · 性能验证 · 非实际行情';
    Object.assign(badge.style, { position: 'fixed', bottom: '0', right: '0', zIndex: '99999', background: '#fff1c2' }); document.body.append(badge);
  });
  await page.screenshot({ path: path.join(root, 'page.png'), fullPage: true });
  assert.deepEqual(result.errors, []); assert.deepEqual(result.external, []);
  result.functional = true;
  result.targetMet = result.samples.every(x => x.ms <= 2000);
} finally {
  result.text = await page.locator('.m-connection').innerText().catch(() => 'unavailable');
  await context.close(); await browser.close();
  await writeFile(path.join(root, 'browser-result.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ ...result, requests: result.requests.length, samples: result.samples.map(({kind, ms}) => ({kind, ms})) }));
}
