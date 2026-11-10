/** 正式ETF页面→公共Client→实际回环HTTP。身份来自独立假配置，响应不替换成样例。 */
import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const root=process.env.WOLF_ETF_TEST_ROOT;
const expected=JSON.parse(await readFile(path.join(root,'page-expectations.json'),'utf8'));
const browser=await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}),headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const context=await browser.newContext({viewport:{width:1440,height:1050}}), page=await context.newPage();
const result={case:expected.case,checks:[],errors:[],external:[],views:[],operations:[],passed:false};
page.on('pageerror',e=>result.errors.push(String(e)));
page.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(r.url()))result.external.push(r.url());});
page.on('response',async r=>{if(/\/api\/etf-flow\/operations/.test(r.url())) {
 const value=await r.json().catch(()=>null);if(value)result.operations.push(value);
}});
page.on('response',async r=>{if(/\/api\/etf-flow\/snapshots\/[a-f0-9]+\?/.test(r.url())&&r.status()===200){
 const v=await r.json().catch(()=>null);if(v)result.views.push({mode:v.mode,period:v.period,end:v.end,group:v.group_id,
  amount:v.summary.evaluation?.amount??null,valid:v.summary.evaluation?.valid_count??null,pool:v.pool_version,input:v.input_version,
  c2:v.summary.evaluation?.c2??null,complete:v.data_status.complete_amount_through});}});
const app=page.locator('.etf-app'), center=page.locator('#operation-center');
const section=n=>app.locator(`[data-module="fund-flows.${n}"]`);
async function loaded(mode){await app.getByText(`已读取 ${expected.end} · ${mode}`,{exact:true}).waitFor({timeout:30000});}
async function postCount(){const log=(await readFile(path.join(root,'http.jsonl'),'utf8')).trim();return log?log.split('\n').map(JSON.parse).filter(r=>r.method==='POST').length:0;}
try{
 await page.goto(process.env.WOLF_UI_ORIGIN);
 await page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor({timeout:30000});
 if(expected.case==='four'){
  const overview=page.locator('.overview-app');
  assert.equal(await overview.locator('.m-table tbody tr').count(),5,'保留当前已验收四指数及沪深北三市合计');
  assert.equal(await overview.locator('.m-table .m-metric-value').count(),4);
  for(let i=0;i<4;i++){
   await overview.locator('.m-table tbody tr').nth(i).getByRole('button').click();
   await overview.locator('.m-price-chart canvas').first().waitFor();
   assert.ok((await overview.locator('.m-readout').innerText()).includes('收'));
  }
  result.checks.push('current-five-row-overview-four-real-price-series-and-charts');
 }
 await page.getByRole('navigation',{name:'市场研究',exact:true}).getByRole('button',{name:'大资金动向',exact:true}).click();
 await app.getByRole('heading',{name:'大资金动向',exact:true}).waitFor();
 assert.match(page.url(),/wolf-run=/);assert.match(page.url(),/page=fund-flows/);
 if(expected.case==='single'){
  await app.getByText('尚无已发布数据，请完成获准的历史初始化与更新。',{exact:true}).waitFor();
  assert.equal(await app.locator('canvas').count(),0);assert.equal(await postCount(),0);
  await app.getByRole('button',{name:'更新数据',exact:true}).click();
  await center.getByRole('button',{name:'明确发起新检查',exact:true}).click();
  await center.getByText('该请求已精确确认完成；其他未知记录仍保留',{exact:true}).waitFor({timeout:30000});
  result.checks.push('empty-no-fallback','explicit-update-through-existing-operation-center');
 }
 await loaded('当时版本');
 assert.equal(await app.getByRole('button',{name:'60日',exact:true}).getAttribute('aria-pressed'),'true');
 assert.equal(await section('09').locator('tbody tr').count(),expected.expected_count);
 for(const member of expected.members)assert.ok((await section('09').innerText()).includes(member.name));
 if(!expected.original_recorded)assert.ok((await app.innerText()).includes('当时没有保存的信号'));
 else assert.ok((await section('12').innerText()).includes(expected.end));
 assert.equal(await section('11').getByText('虚构持有人',{exact:true}).count(),0,'原模式不得泄漏后来披露');
 result.checks.push('default-60-real-http','config-driven-member-catalog','original-record-or-unrecorded-without-backfill-forgery');
 await app.getByRole('button',{name:'当前版本重算',exact:true}).click();await loaded('当前版本重算');
 assert.ok((await section('11').innerText()).includes('10.00%'));
 assert.ok(!(await section('11').innerText()).includes('1,000.00%'));
 assert.ok((await section('11').innerText()).includes('后来披露，仅作事后对照'));
 assert.ok((await section('11').innerText()).includes('未披露，不代表持仓为零'));
 assert.ok((await section('13').innerText()).includes('公告'));
 if(expected.case==='single'){
  assert.ok((await section('08').innerText()).includes('有效ETF不足两只，数据不足'));
  assert.ok((await section('08').innerText()).includes('参数待确认'));
 }
 if(expected.case==='states'){
  const rows=section('09').locator('tbody tr');
  assert.match(await rows.nth(0).innerText(),/等待同日净值/);
  assert.match(await rows.nth(1).innerText(),/已停用/);
  assert.match(await rows.nth(2).innerText(),/重新分组测试/);
  assert.match(await rows.nth(2).innerText(),/0 亿份/);
  assert.match(await rows.nth(4).innerText(),/历史不足/);
  assert.match(await section('06').innerText(),/当日部分小计/);
  result.checks.push('missing-nav-null','disabled-retained','new-member-history-insufficient','zero-distinct','partial-total','configuration-only-regroup');
 }
 if(expected.case==='four'){
  const text=await section('10').locator('.etf-context').innerText();
  assert.ok(text.includes('当日 1.25%'));assert.ok(text.includes('近5日 -2.50%'));
  assert.ok(text.includes('123.00 亿元'));assert.ok(text.includes('1.25 倍'));
  result.checks.push('existing-index-percentage-points-and-market-background-units');
 }
 result.checks.push('current-recalculation-labelled','holder-percentage-is-percentage-points','late-disclosure-and-event-labelled');
 const actual=result.views.findLast(v=>v.mode==='current'&&v.end===expected.end&&v.group===null);
 assert.equal(actual?.amount,({single:'40',four:'160',expanded:'200',states:'40'})[expected.case]);
 const counts=actual.c2;
 await section('08').getByText(`增加 ${counts.positive_count??'—'} / ${counts.denominator??'—'} 只 · 减少 ${counts.negative_count??'—'} / ${counts.denominator??'—'} 只`,{exact:true}).waitFor();
 assert.equal(actual.complete,expected.case==='states'?expected.previous:expected.end);
 await section('14').getByText(new RegExp('完整金额覆盖至 '+actual.complete)).waitFor();
 assert.ok((await section('10').innerText()).includes('已核验普通份额'));
 result.checks.push('service-c2-numerators-denominator','complete-amount-cutoff-separate-from-window','ordinary-share-basis-visible');
 for(const days of [20,120,260,60]){
  const response=page.waitForResponse(r=>r.url().includes('/api/etf-flow/snapshots/')&&r.url().includes(`period=${days}`)&&r.status()===200);
  await app.getByRole('button',{name:`${days}日`,exact:true}).click();await response;await loaded('当前版本重算');
  assert.equal(await app.getByRole('button',{name:`${days}日`,exact:true}).getAttribute('aria-pressed'),'true');
 }
 const groups=await app.getByLabel('观察分组',{exact:true}).locator('option').evaluateAll(opts=>opts.map(o=>({value:o.value,text:o.textContent})));
 assert.equal(groups.length,1+new Set(expected.members.map(m=>m.group)).size);
 await app.getByLabel('观察分组',{exact:true}).selectOption(groups[1].value);await loaded('当前版本重算');
 assert.equal(await section('09').locator('tbody tr').count(),expected.members.filter(m=>m.group===groups[1].text).length);
 await app.getByLabel('观察分组',{exact:true}).selectOption('');await loaded('当前版本重算');
 result.checks.push('20-60-120-260-trading-days','configuration-groups-filter-through-service');
 const last=expected.members.at(-1);
 await section('09').getByRole('button',{name:new RegExp(last.name)}).click();
 assert.equal(await app.getByRole('heading',{name:last.name,exact:true}).count(),1);
 await section('10').getByRole('button',{name:'成交额',exact:true}).click();
 assert.equal(await section('10').getByRole('button',{name:'成交额',exact:true}).getAttribute('aria-pressed'),'true');
 await section('09').getByRole('button',{name:new RegExp(expected.members[0].name)}).click();
 const chart=section('07').getByRole('region');await chart.focus();await page.keyboard.press('Home');
 assert.ok(!(await section('07').locator('.etf-readout time').innerText()).includes(expected.end));
 await page.keyboard.press('End');assert.equal(await section('07').locator('.etf-readout time').innerText(),expected.end);
 const open=app.getByRole('button',{name:'查看配置与版本 ↗',exact:true});await open.click();
 await page.getByRole('dialog').waitFor();assert.equal(await page.locator('dialog :focus').count(),1);
 const dialogText=await page.getByRole('dialog').innerText();
 for(const m of expected.members)for(const value of [m.name,m.code,m.manager,m.exchange,m.tracking_index,m.group,m.enabled_date,m.basis.locator])assert.ok(dialogText.includes(value));
 await page.keyboard.press('Escape');assert.equal(await open.evaluate(e=>document.activeElement===e),true);
 await section('11').getByRole('button',{name:'查看披露证据',exact:true}).first().click();
 await page.getByRole('dialog').getByText(/服务已核对保存原件的摘要及归属/).waitFor();
 assert.ok((await page.getByRole('dialog').innerText()).includes('SHA-256'));
 assert.ok((await page.getByRole('dialog').getByRole('link').first().getAttribute('href')).startsWith('https://'));
 await page.getByRole('dialog').getByRole('button',{name:'关闭 ×',exact:true}).click();
 result.checks.push('member-selection-and-turnover','chart-keyboard-home-end','configuration-nine-fields','dialog-focus-restored','fixed-snapshot-evidence-http');
 if(expected.case==='states'){
  const unready=groups.find(g=>g.text===expected.members.at(-1).group);
  await app.getByLabel('观察分组',{exact:true}).selectOption(unready.value);await loaded('当前版本重算');
  assert.ok((await section('08').innerText()).includes('有效成员 0 只'));
  assert.ok((await section('08').innerText()).includes('增加 — / — 只'));
  assert.ok((await section('08').innerText()).includes('数据不足'));
  await section('14').getByText(/完整金额覆盖截止日：未知/).waitFor();
  const renamed=groups.find(g=>g.text===expected.members[2].group);
  await app.getByLabel('观察分组',{exact:true}).selectOption(renamed.value);await loaded('当前版本重算');
  assert.ok((await section('08').innerText()).includes('有效成员 1 只'));
  assert.ok((await section('08').innerText()).includes('增加 — / — 只'));
  await app.getByRole('button',{name:'当时版本',exact:true}).click();
  await app.getByRole('alert').filter({hasText:'所选分组不在该版本中'}).waitFor();
  assert.equal(await app.locator('canvas').count(),0);
  await app.getByRole('button',{name:'清除分组筛选',exact:true}).click();await loaded('当时版本');
  assert.equal(await app.getByLabel('观察分组',{exact:true}).inputValue(),'');
  await app.getByRole('button',{name:'当前版本重算',exact:true}).click();await loaded('当前版本重算');
  result.checks.push('zero-one-valid-c2-insufficient','missing-version-group-error-no-silent-whole-pool','explicit-clear-group-recovers');
 }
 if(expected.original_recorded){
  await app.getByRole('button',{name:'当时版本',exact:true}).click();await loaded('当时版本');
  const originalText=await section('12').innerText();
  await section('12').getByRole('button',{name:new RegExp(expected.end)}).click();await loaded('当时版本');
  assert.equal(await section('12').innerText(),originalText);
  await app.getByLabel('观察日期',{exact:true}).fill(expected.previous);
  await app.getByText(`已读取 ${expected.previous} · 当时版本`,{exact:true}).waitFor();
  assert.ok((await app.innerText()).includes('当时没有保存的信号'));
  await app.getByLabel('观察日期',{exact:true}).fill(expected.end);await loaded('当时版本');
  await app.getByRole('button',{name:'当前版本重算',exact:true}).click();await loaded('当前版本重算');
  result.checks.push('historical-date-and-original-record-preserved');
 }
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:path.join(root,'etf-page-light.png'),fullPage:true});
 await page.setViewportSize({width:980,height:900});
 await app.getByRole('button',{name:'深色备选主题',exact:true}).click();
 await app.getByLabel('数据说明',{exact:true}).check();
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:path.join(root,'etf-page-dark-980.png'),fullPage:true});
 const widths=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));
 assert.ok(widths.scroll<=widths.width,JSON.stringify(widths));
 result.checks.push('light-dark-980-no-document-overflow','data-notes');
 // 只延迟/中断真实HTTP，不提供替身金融响应；过期请求不得覆盖后选口径。
 let release;const held=new Promise(resolve=>{release=resolve;});let hit;
 const arrived=new Promise(resolve=>{hit=resolve;});
 const handler=async route=>{if(route.request().url().includes('mode=original')){hit();await held;}await route.continue().catch(()=>{});};
 await page.route('**/api/etf-flow/snapshots/*?*',handler);
 await app.getByRole('button',{name:'当时版本',exact:true}).click();await arrived;
 await app.getByText('正在读取固定版本…',{exact:true}).waitFor();
 await app.getByRole('button',{name:'当前版本重算',exact:true}).click();await loaded('当前版本重算');
 release();await page.unroute('**/api/etf-flow/snapshots/*?*',handler);
 assert.equal(await app.getByRole('button',{name:'当前版本重算',exact:true}).getAttribute('aria-pressed'),'true');
 const abortRoute=route=>route.abort('failed');await page.route('**/api/etf-flow/snapshots/*?*',abortRoute);
 await app.getByRole('button',{name:'重新读取',exact:true}).click();
 await app.getByRole('alert').filter({hasText:'本地服务连接不可用'}).waitFor();assert.equal(await app.locator('canvas').count(),0);
 await page.unroute('**/api/etf-flow/snapshots/*?*',abortRoute);
 await app.getByRole('button',{name:'重新读取',exact:true}).click();await loaded('当前版本重算');
 result.checks.push('loading-with-no-fallback','cancel-late-response-ownership','error-no-fake-data-and-explicit-read-recovery');
 const before=await postCount(),entry=page.url();
 const reconnected=page.waitForResponse(r=>r.url().endsWith('/api/etf-flow/session')&&r.status()===200);
 const reread=page.waitForResponse(r=>r.url().includes('/api/etf-flow/snapshots/')&&r.url().includes('mode=current')&&r.status()===200);
 await app.getByRole('button',{name:'重新连接',exact:true}).click();await reconnected;await reread;await loaded('当前版本重算');
 assert.equal(page.url(),entry);assert.equal(await postCount(),before);
 result.checks.push('explicit-reconnect-preserves-managed-entry-and-never-posts');
 await page.reload();await loaded('当时版本');assert.equal(await postCount(),before);
 await app.getByRole('navigation',{name:'市场研究',exact:true}).getByRole('button',{name:'行情总览',exact:true}).click();
 await page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:/沪深300资料|002245资料/}).count(),0);
 await page.getByRole('navigation',{name:'市场研究',exact:true}).getByRole('button',{name:'大资金动向',exact:true}).click();await loaded('当时版本');
 assert.equal(await app.getByRole('button',{name:/沪深300资料|002245资料/}).count(),0);
 assert.equal(await app.getByRole('button',{name:'标的查询',exact:true}).isDisabled(),true);
 assert.equal(await postCount(),expected.case==='single'?1:0);
 result.checks.push('refresh-navigation-get-only','overview-etf-navigation-retired-pages-absent');
 assert.deepEqual(result.errors,[]);assert.deepEqual(result.external,[]);result.passed=true;
}finally{
 if(!result.passed){await page.screenshot({path:path.join(root,'etf-page-failed.png'),fullPage:true}).catch(()=>{});result.text=await page.locator('body').innerText().catch(()=>'?');}
 await context.close();await browser.close();await writeFile(path.join(root,'etf-page-browser.json'),JSON.stringify(result,null,2));
}
