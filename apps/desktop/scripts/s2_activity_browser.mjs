/** S2隔离托管页面：启动后自动出数，不点击更新、不接真实来源。 */
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE, 'index.mjs')).href);
const root = process.env.WOLF_S2_ROOT;
const browser = await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}), headless: true, proxy: { server: 'http://127.0.0.1:9', bypass: '127.0.0.1' } });
const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
const page = await context.newPage();
const record = { checks: [], errors: [], external: [], requests: [], passed: false };
page.on('pageerror', error => record.errors.push(String(error)));
page.on('request', request => {
  record.requests.push({ method: request.method(), url: request.url() });
  if (!/^http:\/\/127\.0\.0\.1:\d+\//.test(request.url())) record.external.push(request.url());
});
const readout = () => page.getByLabel('量额读数', { exact: true });
const loaded = () => page.getByText('读取结束 · 当前读取不采集新行情', { exact: true }).waitFor({ timeout: 90000 });
async function shot(name) {
  await page.evaluate(() => {
    if (!document.querySelector('#synthetic-label')) {
      const label = document.createElement('div'); label.id = 'synthetic-label'; label.textContent = '隔离合成数据 · 非实际行情';
      Object.assign(label.style, { position: 'fixed', bottom: '8px', right: '8px', zIndex: '9999', background: '#fff1c2', padding: '8px' }); document.body.append(label);
    }
  });
  await page.screenshot({ path: path.join(root, name), fullPage: true });
}
try {
  await page.goto(process.env.WOLF_UI_ORIGIN); await loaded();
  assert.equal(await page.locator('.m-table tbody tr').count(), 5);
  await writeFile(path.join(root, 'release'), 'release synthetic responses');
  await page.locator('.m-activity-chart canvas').waitFor({ timeout: 180000 });
  assert.match(await readout().innerText(), /1\.23/);
  assert.match(await page.locator('.m-activity-provenance').innerText(), /未经双源核验.*中证指数.*2026-10-27/);
  record.checks.push('managed-entry-auto-index-values-no-update-click', 'single-source-label-source-date');
  await page.getByLabel('指数K线副图', { exact: true }).selectOption('volume');
  assert.equal(await readout().locator('b').innerText(), '0');
  await page.getByRole('button', { name: '均线设置 ▾', exact: true }).click();
  assert.equal(await page.locator('fieldset').last().locator('input').count(), 8);
  await page.keyboard.press('Escape');
  for (const name of ['深证成指', '创业板指', '科创50']) {
    await page.getByRole('button', { name: new RegExp(name) }).click();
    await page.locator('.m-activity-chart canvas').waitFor({ timeout: 180000 });
    assert.match(await page.locator('.m-activity-provenance').innerText(), /未经双源核验/);
    assert.equal(await readout().locator('b').innerText(), '0');
  }
  record.checks.push('four-indices-vol-amount-eight-ma-real-http');
  await page.getByRole('button', { name: /沪深两市合计/ }).click();
  await page.locator('.m-activity-chart canvas').waitFor({ timeout: 180000 });
  await page.getByRole('region', { name: '沪深两市合计图表', exact: true }).focus();
  await page.keyboard.press('End');
  assert.equal(await readout().locator('b').innerText(), '4');
  assert.match(await page.locator('.m-activity-provenance').innerText(), /不含北交所.*未经双源核验.*上交所.*深交所/);
  const marketDate = await readout().locator('strong').first().innerText();
  assert.ok(marketDate > '2026-10-27', '旧价格不能限制独立市场数据截至日');
  record.checks.push('market-anchor-independent-of-old-prices', 'two-market-excludes-bse');
  await page.getByRole('region', { name: '沪深两市合计图表', exact: true }).focus();
  await page.keyboard.press('End');
  for (let i=0; i<3; i++) await page.keyboard.press('ArrowLeft');
  assert.match(await readout().innerText(), /暂无数据/);
  await page.keyboard.press('End');
  await shot('s2-market.png');
  const countBefore = record.requests.filter(r => /\/snapshots\//.test(r.url)).length;
  await page.waitForTimeout(6500);
  assert.equal(record.requests.filter(r => /\/snapshots\//.test(r.url)).length, countBefore, '同量额版本不重复读完整快照');
  record.checks.push('missing-one-market-no-partial-sum', 'stable-version-no-repeat-snapshot');
  await page.setViewportSize({ width: 820, height: 1000 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await shot('s2-narrow.png');
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.getByRole('button', { name: /上证指数/ }).click();
  await page.getByLabel('指数K线副图', { exact: true }).selectOption('amount');
  await page.getByRole('button', { name: '周 K', exact: true }).click();
  assert.match(await readout().innerText(), /周频/);
  await page.getByRole('button', { name: '月 K', exact: true }).click();
  assert.match(await readout().innerText(), /月频/);
  await page.getByRole('button', { name: '日 K', exact: true }).click();
  await page.getByRole('button', { name: '深色备选主题', exact: true }).click();
  await shot('s2-index-dark.png');
  await page.reload(); await loaded(); await page.locator('.m-activity-chart canvas').waitFor();
  assert.match(await readout().innerText(), /1\.23/);
  const selectedCurrent = url => decodeURIComponent(url.pathname) === '/api/market-activity/sse:000001:price';
  let aborted = false;
  await page.route(selectedCurrent, async route => { aborted = true; await route.abort('connectionfailed'); }, { times: 1 });
  for (let i=0; i<100 && !aborted; i++) await page.waitForTimeout(100);
  assert.equal(aborted, true, '实际current请求中断已命中');
  assert.match(await readout().innerText(), /1\.23/, '瞬时请求失败保留已有量额');
  let release, held;
  const waiting = new Promise(resolve => { held = resolve; });
  const blocked = new Promise(resolve => { release = resolve; });
  await page.route(selectedCurrent, async route => {
    const response = await route.fetch(); held(); await blocked;
    await route.fulfill({ response }).catch(() => {}); // 原页面取消后允许浏览器拒收。
  }, { times: 1 });
  await Promise.race([waiting, page.waitForTimeout(40000).then(() => { throw Error('未命中迟到响应'); })]);
  await page.getByRole('button', { name: '重新连接', exact: true }).click();
  release(); await loaded(); await page.locator('.m-activity-chart canvas').waitFor();
  assert.match(await readout().innerText(), /1\.23/);
  record.checks.push('real-browser-current-interruption-keeps-old', 'late-old-client-response-ignored-after-reconnect');
  await page.getByRole('button', { name: '重新连接', exact: true }).click(); await loaded();
  await page.locator('.m-activity-chart canvas').waitFor();
  record.checks.push('daily-weekly-monthly-dark-narrow-reload-reconnect');
  assert.equal(record.requests.some(r => r.method === 'POST'), false);
  assert.deepEqual(record.errors, []); assert.deepEqual(record.external, []); record.passed = true;
} catch (error) {
  record.failure = String(error); record.body = await page.locator('body').innerText(); await shot('s2-failure.png'); throw error;
} finally {
  await browser.close(); await writeFile(path.join(root, 'browser-result.json'), JSON.stringify(record, null, 2));
}
