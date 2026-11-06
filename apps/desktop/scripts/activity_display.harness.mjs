/** 合成量额真实HTTP/UI；不放行外网，不给生产页面写入测试数据。 */
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const {chromium}=await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const fixture=JSON.parse(await readFile(process.env.WOLF_ACTIVITY_FIXTURE,'utf8'));
const browser=await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}),channel:'chromium',headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const record={errors:[],external:[],checks:[],passed:false};
const context=await browser.newContext({viewport:{width:1440,height:1080}}),page=await context.newPage();
const requests=[];
page.on('pageerror',e=>record.errors.push(String(e)));
page.on('request',r=>{requests.push(r);if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(r.url()))record.external.push(r.url());});
const waitLoaded=()=>page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor({timeout:90000});
const activityRead=()=>page.getByLabel('量额读数',{exact:true}).innerText();
const waitCursorSync=()=>page.waitForFunction(()=>document.querySelector('#overview-readout strong')?.textContent===document.querySelector('[aria-label="量额读数"] strong')?.textContent);
async function screenshot(name){
  await page.evaluate(()=>{const b=document.createElement('div');b.textContent='隔离合成数据 · 仅验证展示';Object.assign(b.style,{position:'fixed',bottom:'8px',right:'8px',background:'#fff1c2',color:'#604800',zIndex:9999});document.body.append(b);});
  await page.screenshot({path:path.join(process.env.WOLF_UI_OUTPUT,name),fullPage:true});
}
try{
  const began=Date.now(); await page.goto(process.env.WOLF_UI_ORIGIN);await waitLoaded();record.initial_load_ms=Date.now()-began;
  await page.locator('.m-activity-chart canvas').waitFor();
  assert.match(await activityRead(),/1\.23/);
  assert.equal(await page.getByRole('button',{name:'更新数据',exact:true}).isDisabled(),true);
  assert.equal(await page.locator('.m-table tbody tr').count(),5);
  await screenshot('p3-light.png');
  const count=requests.filter(r=>r.url().includes('/api/')).length;
  await page.getByLabel('指数K线副图',{exact:true}).selectOption('volume');
  assert.match(await activityRead(),/VOL/);assert.equal(await page.getByLabel('量额读数',{exact:true}).locator('b').innerText(),'0');
  assert.match(await page.getByLabel('量额均线读数',{exact:true}).innerText(),/0\.8/);
  await page.getByRole('button',{name:'均线设置 ▾',exact:true}).click();
  const field=page.locator('fieldset').filter({has:page.locator('legend').filter({hasText:'成交量 VOL'})});
  assert.equal(await field.locator('input').count(),8);await field.getByLabel('MA5',{exact:true}).uncheck();
  await page.keyboard.press('Escape');
  await page.getByLabel('指数K线副图',{exact:true}).selectOption('amount');
  assert.match(await page.getByLabel('量额均线读数',{exact:true}).innerText(),/MA5/);
  await page.getByLabel('指数K线副图',{exact:true}).selectOption('volume');
  assert.doesNotMatch(await page.getByLabel('量额均线读数',{exact:true}).innerText(),/MA5 /);
  await page.getByRole('button',{name:'周 K',exact:true}).click();assert.match(await activityRead(),/周频/);
  await page.getByRole('button',{name:'月 K',exact:true}).click();assert.match(await activityRead(),/月频/);
  await page.getByRole('button',{name:'均线设置 ▾',exact:true}).click();
  assert.equal(await field.getByLabel('MA60',{exact:true}).isDisabled(),true);assert.match(await field.innerText(),/有效样本不足/);await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'日 K',exact:true}).click();
  await page.getByRole('region',{name:'日K图表',exact:true}).focus();await page.keyboard.press('Home');
  const date=(await page.locator('#overview-readout strong').innerText());assert.ok((await activityRead()).startsWith(date));
  await page.getByRole('group',{name:'图表显示范围',exact:true}).getByRole('button',{name:'1 月',exact:true}).click();
  await waitCursorSync();
  assert.ok((await activityRead()).startsWith(await page.locator('#overview-readout strong').innerText()),'缩放排除旧游标后，价格与量额仍须选择同一可见日期');
  await page.getByRole('region',{name:'指数成交量 VOL图表',exact:true}).focus();await page.keyboard.press('ArrowRight');
  await waitCursorSync();
  assert.ok((await activityRead()).startsWith(await page.locator('#overview-readout strong').innerText()));
  for(const name of ['深证成指','创业板指','科创50']){await page.getByRole('button',{name:new RegExp(name)}).click();await page.locator('.m-activity-chart canvas').waitFor();assert.match(await activityRead(),/万股/);}
  await page.getByRole('button',{name:/全市场成交额/}).click();
  assert.match(await activityRead(),/全市场成交额/);
  await page.getByRole('region',{name:'全市场成交额图表',exact:true}).focus();await page.keyboard.press('End');
  assert.equal(await page.getByLabel('量额读数',{exact:true}).locator('b').innerText(),'6');
  const marketRow=page.locator('.m-table tbody tr').last();assert.match(await marketRow.innerText(),/6 亿元/);assert.match(await marketRow.innerText(),/暂无数据/);
  await page.keyboard.press('ArrowLeft');await page.keyboard.press('ArrowLeft');await page.keyboard.press('ArrowLeft');assert.match(await activityRead(),/暂无数据/);
  await page.getByRole('checkbox',{name:'显示数据说明',exact:true}).check();assert.match(await page.locator('.m-activity-details').innerText(),/bse/);assert.match(await page.locator('.m-activity-details').innerText(),/来源修订一致性未知/);
  await page.getByRole('group',{name:'图表显示范围',exact:true}).getByRole('button',{name:'3 月',exact:true}).click();
  assert.equal(requests.filter(r=>r.url().includes('/api/')).length,count);
  await screenshot('p3-market.png');
  await page.getByRole('button',{name:'深色备选主题',exact:true}).click();await screenshot('p3-dark.png');
  await page.setViewportSize({width:820,height:1000});await screenshot('p3-narrow.png');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  record.checks.push('four-index-and-market-real-http','independent-eight-ma-preferences','daily-weekly-monthly','zero-not-missing','missing-market-no-partial-total','linked-cursor','local-range-no-fetch','metadata-themes-narrow');
  // 模拟收到撤回错误；清除既有值，无旧有效量额兜底。
  await page.route('**/api/market-activity/cn-a-turnover?*',async route=>{
    const response=await route.fetch();await route.fulfill({response,status:409,body:JSON.stringify({detail:{code:'source_withdrawn',message:'synthetic withdrawal'}})});
  });
  await page.getByRole('button',{name:'重新读取',exact:true}).click();await waitLoaded();assert.equal(await page.locator('.m-activity-chart').count(),0);assert.match(await page.locator('.m-activity-empty').innerText(),/撤回/);
  await page.unroute('**/api/market-activity/cn-a-turnover?*');
  // 结构正确但量额属于别的价格，不能展示。
  await page.route('**/api/market-activity/sse%3A000001%3Aprice?*',async route=>{
    const response=await route.fetch();const data=await response.json();data.price_snapshot_id='0'.repeat(64);await route.fulfill({response,json:data});
  });
  await page.getByRole('button',{name:/上证指数/}).click();await page.getByRole('button',{name:'重新读取',exact:true}).click();await waitLoaded();assert.equal(await page.locator('.m-activity-chart').count(),0);assert.match(await page.locator('.m-activity-empty').innerText(),/归属/);
  record.checks.push('withdrawn-clears-old-values','cross-price-current-rejected');
  await page.unroute('**/api/market-activity/sse%3A000001%3Aprice?*');
  await page.getByRole('button',{name:'周 K',exact:true}).click();
  await page.route('**/api/index-series/**/calculations?*',route=>route.abort());
  await page.getByRole('button',{name:'重新读取',exact:true}).click();await waitLoaded();
  assert.equal(await page.locator('.m-activity-chart').count(),0);
  assert.match(await page.locator('.m-activity-empty').innerText(),/当前周期价格计算未取得/);
  await page.getByRole('button',{name:'日 K',exact:true}).click();await page.locator('.m-activity-chart canvas').waitFor();
  assert.match(await activityRead(),/万股/);
  record.checks.push('missing-weekly-price-does-not-use-daily-price-colors');
  assert.equal(requests.some(r=>r.method()==='POST'),false);
  assert.deepEqual(record.errors,[]);assert.deepEqual(record.external,[]);record.passed=true;
}catch(error){record.failure=String(error);record.body=await page.locator("body").innerText();record.requests=requests.map(r=>({url:r.url(),method:r.method()}));await page.screenshot({path:path.join(process.env.WOLF_UI_OUTPUT,"failure.png"),fullPage:true});throw error;}finally{await browser.close();await writeFile(path.join(process.env.WOLF_UI_OUTPUT,'browser-result.json'),JSON.stringify(record,null,2)+'\n');}
