/** P2在真实浏览器直连真实ASGI服务；只有独占临时根中的合成金融资料。 */
import assert from 'node:assert/strict';
import { readFile, writeFile, rename } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE, 'index.mjs')).href);
const origin = process.env.WOLF_UI_ORIGIN, api = process.env.WOLF_API_ORIGIN, output = process.env.WOLF_UI_OUTPUT;
const fixture = JSON.parse(await readFile(process.env.WOLF_SERIES_FIXTURE, 'utf8'));
const browser = await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}), ...(process.env.WOLF_BROWSER_EXECUTABLE ? {} : {channel:'chromium'}), headless: true,
  proxy: { server: 'http://127.0.0.1:9', bypass: '127.0.0.1' } });
const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
const records = { synthetic_only: true, requests: [], external_attempts: [], page_errors: [], cases: [] };
context.on('request', request => {
  const url = request.url(); records.requests.push({ url, method: request.method() });
  if (!url.startsWith(origin + '/') && !url.startsWith(api + '/')) records.external_attempts.push(url);
});
const page = await context.newPage(); page.on('pageerror', error => records.page_errors.push(error.stack || String(error)));
const displayPrice = value => value == null ? '暂无数据' : new Intl.NumberFormat('en-US',{useGrouping:false,minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(value));
const readout = () => page.locator('.m-readout').innerText();
const apiCalls = () => records.requests.filter(value => value.url.startsWith(api + '/api/index-series/')).length;
async function waitLoaded() { await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))); await page.getByText('读取结束 · 当前读取不采集新行情', { exact: true }).waitFor(); }
async function screenshot(name) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(() => {
    if (!document.getElementById('synthetic-test-badge')) {
      const badge = document.createElement('div'); badge.id = 'synthetic-test-badge';
      badge.textContent = '隔离合成数据 · 仅用于验证';
      Object.assign(badge.style, { position: 'fixed', right: '12px', bottom: '12px', padding: '5px 10px',
        background: '#fff1c2', color: '#604800', fontSize: '11px', zIndex: '50', border: '1px solid #ddc67b' });
      document.body.append(badge);
    }
  });
  await page.screenshot({ path: path.join(output, name), fullPage: true });
}
let movedIndex;
try {
  const scenario = process.env.WOLF_OVERVIEW_CASE;
  if (scenario === 'empty' || scenario === 'missing-config') {
    await page.goto(origin);
    if (scenario === 'empty') {
      await waitLoaded();
      assert.equal(await page.locator('.m-table .m-metric-value').count(), 0);
      assert.equal(await page.locator('.m-price-chart canvas').count(), 0);
      assert.ok((await page.locator('.m-empty').innerText()).includes('暂无数据'));
      assert.equal(await page.getByRole('alert').count(), 0);
      await screenshot('overview-empty.png');
    } else {
      await page.getByText('指数连接未配置，请检查本地启动配置。', { exact: true }).waitFor();
      assert.equal(apiCalls(), 0);
      assert.equal(await page.getByRole('button', { name: /沪深300资料|002245资料/ }).count(),0);
    }
    assert.deepEqual(records.external_attempts, []); assert.deepEqual(records.page_errors, []);
    records.cases.push(scenario); records.passed = true;
  } else {
  await page.goto(origin); await waitLoaded();
  await page.locator('.m-price-chart canvas').waitFor();
  assert.equal(await page.locator('.m-table tbody tr').count(), 5);
  for (const [id, label] of [['sse:000001:price', '上证指数'], ['szse:399001:price', '深证成指'],
    ['szse:399006:price', '创业板指'], ['sse:000688:price', '科创50']]) {
    const row = page.locator('.m-table tr').filter({ has: page.getByRole('button', { name: new RegExp(label) }) });
    assert.ok((await row.innerText()).includes(displayPrice(fixture.views[id].snapshot.summary.close)));
  }
  assert.equal(await page.getByRole('button', { name: '更新数据', exact: true }).isDisabled(), false);
  assert.equal(await page.getByRole('button', { name: '周 K', exact: true }).isDisabled(), false);
  assert.equal(await page.getByRole('button', { name: '月 K', exact: true }).isDisabled(), false);
  await screenshot('overview-light.png'); records.cases.push('four-real-index-snapshots-and-explicit-missing-values');

  const count = apiCalls();
  await page.getByRole('button', { name: /深证成指/ }).click();
  await page.getByRole('heading', { name: '深证成指', exact: true }).waitFor();
  assert.ok((await readout()).includes(displayPrice(fixture.views['szse:399001:price'].snapshot.bars.at(-1).close)));
  await page.getByRole('group', { name: '观察窗口', exact: true }).getByRole('button', { name: '5 日', exact: true }).click();
  await page.getByRole('group', { name: '图表显示范围', exact: true }).getByRole('button', { name: '3 月', exact: true }).click();
  const chart = page.getByRole('region', { name: '日K图表', exact: true });
  await chart.focus(); await page.keyboard.press('Home');
  const start = await page.getByLabel('显示区间开始日期', { exact: true }).inputValue();
  assert.ok((await readout()).includes(start));
  const startCalculation = fixture.calculations['szse:399001:price'].daily.rows.find(row => row.end === start);
  assert.ok((await readout()).includes(startCalculation.change_pct.value + '%'));
  assert.ok((await page.locator('.m-ma-readout').innerText()).includes(displayPrice(startCalculation.ma[7].value)));
  await page.keyboard.press('ArrowRight'); assert.ok(!(await readout()).startsWith(start));
  await page.keyboard.press('End');
  const box = await chart.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction(last => document.querySelector('.m-readout strong').textContent !== last, fixture.views['szse:399001:price'].snapshot.bars.at(-1).trade_date);
  await page.mouse.wheel(0, -420);
  await page.waitForFunction(before => document.querySelector('input[aria-label="显示区间开始日期"]').value !== before, start);
  const zoomStart = await page.getByLabel('显示区间开始日期', { exact: true }).inputValue();
  await page.mouse.move(box.x + box.width * .5, box.y + box.height * .5); await page.mouse.down();
  await page.mouse.move(box.x + box.width * .75, box.y + box.height * .5, { steps: 12 }); await page.mouse.up();
  await page.waitForFunction(before => document.querySelector('input[aria-label="显示区间开始日期"]').value !== before, zoomStart);
  const full = fixture.views['szse:399001:price'].snapshot.bars;
  const first = full[full.length - 12], last = full.at(-1);
  await page.getByLabel('显示区间开始日期', { exact: true }).fill(first.trade_date);
  await page.getByLabel('显示区间结束日期', { exact: true }).fill(last.trade_date);
  assert.equal(await page.getByLabel('显示区间开始日期', { exact: true }).inputValue(), first.trade_date, '日期草稿不得被迟到拖动覆盖');
  await page.getByRole('button', { name: '应用', exact: true }).click();
  await page.waitForFunction(day => document.querySelector('.m-readout strong').textContent >= day, first.trade_date);
  const expectedHigh = full.slice(-12).reduce((a, b) => Number(b.high) > Number(a.high) ? b : a);
  const expectedLow = full.slice(-12).reduce((a, b) => Number(b.low) < Number(a.low) ? b : a);
  const extrema = await page.getByLabel('可见区间高低点').innerText();
  assert.ok(extrema.includes(`${displayPrice(expectedHigh.high)}（${expectedHigh.trade_date}）`));
  assert.ok(extrema.includes(`${displayPrice(expectedLow.low)}（${expectedLow.trade_date}）`));
  await page.getByLabel('显示区间开始日期', { exact: true }).fill('2020-01-01');
  await page.getByRole('button', { name: '应用', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: '请选择已保存范围内' }).waitFor();
  assert.equal(apiCalls(), count); records.cases.push('switch-window-precision-keyboard-wheel-drag-dates-extrema-zero-new-requests');

  await page.getByRole('button', { name: '均线设置', exact: false }).click();
  const panel = page.locator('#overview-ma-panel');
  assert.equal(await panel.locator('input:disabled').count(), 8);
  assert.equal(await panel.locator('input:checked').count(), 10);
  await page.keyboard.press('Escape'); assert.equal(await panel.count(), 0);
  const calculation = fixture.calculations['szse:399001:price'];
  const summaryRow = page.locator('.m-table tr').filter({ has: page.getByRole('button', { name: /深证成指/ }) });
  for (const [label, key] of [['5 日', 'day_5'], ['20 日', 'day_20'], ['60 日', 'day_60'], ['1 年', 'year_1']]) {
    await page.getByRole('group', { name: '观察窗口', exact: true }).getByRole('button', { name: label, exact: true }).click();
    assert.ok((await summaryRow.locator('td').nth(2).innerText()).includes(calculation.performance[key].value + '%'));
  }
  await page.getByRole('group', { name: '图表显示范围', exact: true }).getByRole('button', { name: '全部', exact: true }).click();
  for (const [label, frequency, disabled] of [['周', 'weekly', 2], ['月', 'monthly', 4], ['日', 'daily', 0]]) {
    await page.getByRole('button', { name: `${label} K`, exact: true }).click();
    const activeChart = page.getByRole('region', { name: `${label}K图表`, exact: true });
    await activeChart.focus(); await page.keyboard.press('End');
    const last = calculation[frequency].rows.at(-1);
    for (const key of ['open', 'high', 'low', 'close']) assert.ok((await readout()).includes(displayPrice(last[key])));
    assert.ok((await readout()).includes(last.change_pct.value + '%'));
    const maReadout = await page.locator('.m-ma-readout').innerText();
    assert.ok(maReadout.includes(displayPrice(last.ma[0].value)));
    if (frequency !== 'daily') {
      assert.match(await page.locator('.m-period-readout').innerText(), /未完整：周期尚未结束/);
      assert.match(maReadout, /MA250 暂无数据/);
    } else assert.ok(maReadout.includes(displayPrice(last.ma[7].value)));
    await page.getByRole('button', { name: '均线设置', exact: false }).click();
    const priceGroup = panel.getByRole('group', { name: `价格 · ${label}均线`, exact: true });
    assert.equal(await priceGroup.locator('input:disabled').count(), disabled);
    assert.equal(await priceGroup.getByLabel('MA250', { exact: true }).isChecked(), true);
    if (disabled) assert.match(await priceGroup.innerText(), /MA250：暂无数据；需要250根有效/);
    await page.keyboard.press('Escape');
    await activeChart.focus(); await page.keyboard.press('Home');
    assert.match(await page.locator('.m-ma-readout').innerText(), /暂无数据.*有效样本不足/);
    if (frequency === 'monthly') assert.match(await page.locator('.m-period-readout').innerText(), /历史窗口起点截断/);
    await page.keyboard.press('End');
    await screenshot(`overview-${frequency}.png`);
  }
  await page.getByRole('button', { name: '均线设置', exact: false }).click();
  await panel.getByRole('group', { name: '价格 · 日均线', exact: true }).getByLabel('MA10', { exact: true }).uncheck();
  assert.doesNotMatch(await page.locator('.m-ma-readout').innerText(), /MA10 /);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: /上证指数/ }).click();
  assert.doesNotMatch(await page.locator('.m-ma-readout').innerText(), /MA10 /);
  await page.getByRole('button', { name: /深证成指/ }).click();
  assert.doesNotMatch(await page.locator('.m-ma-readout').innerText(), /MA10 /);
  assert.equal(apiCalls(), count, '窗口、周期、均线、指数与范围选择不得发出新的读取');
  records.cases.push('all-performance-windows-server-values-daily-weekly-monthly-ma-availability-incomplete-and-preference');
  await page.getByLabel('指数K线副图', { exact: true }).selectOption('volume');
  assert.ok((await page.locator('.m-activity-empty').innerText()).includes('VOL · 万股'));
  await page.getByRole('button', { name: '均线设置', exact: false }).click();
  await page.getByRole('heading', { name: '行情总览', exact: true }).click(); assert.equal(await panel.count(), 0);
  await page.getByRole('button', { name: '深色备选主题', exact: true }).click();
  await screenshot('overview-dark.png');
  await page.getByRole('checkbox', { name: '显示数据说明', exact: true }).check();
  assert.ok((await page.locator('.m-notes').innerText()).includes(fixture.views['szse:399001:price'].snapshot.snapshot_id));
  await page.getByRole('button', { name: /沪深北三市合计/ }).click();
  await page.getByRole('heading', { name: '沪深北三市合计', exact: true }).waitFor();
  assert.ok((await page.locator('.m-empty').innerText()).includes('暂无数据'));
  assert.equal(await page.locator('.m-price-chart canvas').count(), 0);
  records.cases.push('folded-eight-ma-vol-unavailable-market-theme-and-provenance');

  await page.getByRole('button', { name: /上证指数/ }).click();
  await page.setViewportSize({ width: 420, height: 900 });
  // ECharts通过ResizeObserver调整画布；等待实际布局完成，仍要求无横向溢出。
  await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth, null, { timeout: 5000 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.equal(await page.locator('.m-sidebar').isVisible(), false);
  await page.getByRole('button', { name: '展开或收起导航', exact: true }).click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.m-sidebar').isVisible(), false);
  assert.equal(await page.getByRole('button', { name: '展开或收起导航', exact: true }).evaluate(node => document.activeElement === node), true);
  await page.getByRole('button', { name: '展开或收起导航', exact: true }).click();
  await page.getByRole('button', { name: '关闭导航', exact: true }).click();
  await screenshot('overview-420.png');
  await page.setViewportSize({ width: 1440, height: 1080 });
  await context.setOffline(true); await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await page.getByText('当前显示上次成功读取的快照；连接或读取完成前不代表最新数据。', { exact: true }).waitFor();
  assert.ok((await readout()).includes(displayPrice(fixture.views['sse:000001:price'].snapshot.bars.at(-1).close)));
  await screenshot('overview-offline-preserved.png');
  await context.setOffline(false); await page.getByRole('button', { name: '重新读取', exact: true }).click(); await waitLoaded();
  records.cases.push('narrow-layout-and-offline-old-snapshot-preserved');

  // 独立注入计算传输失败；原始价格仍经真实HTTP读取，不用旧计算填补。
  await page.route('**/calculations?*', route => route.abort('failed'));
  await page.getByRole('button', { name: '重新读取', exact: true }).click(); await waitLoaded();
  assert.equal(await page.locator('.m-metric-value').count(), 4);
  assert.equal(await page.getByRole('button', { name: '周 K', exact: true }).isDisabled(), true);
  assert.match(await page.locator('.m-ma-readout').innerText(), /暂无数据/);
  assert.doesNotMatch(await page.locator('.m-ma-readout').innerText(), /MA5 \d/);
  assert.equal(await page.getByRole('alert').filter({ hasText: '计算结果暂无数据' }).count(), 4);
  for (let i = 0; i < 4; i++) assert.equal(await page.locator('.m-table tbody tr').nth(i).locator('td').nth(2).innerText(), '暂无数据');
  await page.unroute('**/calculations?*');
  await page.getByRole('button', { name: '重新读取', exact: true }).click(); await waitLoaded();
  assert.equal(await page.getByRole('button', { name: '周 K', exact: true }).isDisabled(), false);
  records.cases.push('calculation-only-failure-keeps-raw-price-clears-all-derived-results-and-recovers');

  // 运行中移开已绑定的合成目录应安全报错，不能把资料损坏伪装为空库。
  const original = path.join(process.env.WOLF_SYNTHETIC_DATA, 'indices/sse000688');
  const held = path.join(output, 'held-synthetic-index');
  await rename(original, held); movedIndex = { original, held };
  await page.reload(); await waitLoaded();
  await page.getByRole('button', { name: /科创50/ }).click();
  assert.ok((await page.locator('.m-empty').innerText()).includes('价格读取失败'));
  await screenshot('overview-invalid.png');
  await rename(held, original); movedIndex = undefined;
  await page.getByRole('button', { name: '重新读取', exact: true }).click(); await waitLoaded();
  await page.locator('.m-price-chart canvas').waitFor();
  assert.equal(await page.locator('button:not([disabled])').filter({hasText:/沪深300资料|002245资料|大资金动向|标的查询/}).count(),0);
  await page.reload(); await waitLoaded();
  records.cases.push('actual-api-invalid-recovery-and-retired-entries-absent');
  assert.deepEqual(records.external_attempts, []); assert.deepEqual(records.page_errors, []);
  assert.ok(records.requests.every(value => value.method === 'GET'));
  records.passed = true;
  }
} catch (error) {
  records.failure = String(error); await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {}); throw error;
} finally {
  if (movedIndex) await rename(movedIndex.held, movedIndex.original);
  await context.setOffline(false); await browser.close();
  records.browser_closed = !browser.isConnected();
  const suffix = process.env.WOLF_OVERVIEW_CASE ? '-' + process.env.WOLF_OVERVIEW_CASE : '';
  await writeFile(path.join(output, 'browser-result' + suffix + '.json'), JSON.stringify(records, null, 2) + '\n');
}
