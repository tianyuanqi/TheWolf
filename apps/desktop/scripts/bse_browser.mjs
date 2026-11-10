/** BSE实际托管浏览器联调；只读隔离合成行情，不调用真实来源。 */
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const root=process.env.WOLF_PERIODIC_ROOT;
const browser=await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}),headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const context=await browser.newContext({viewport:{width:1440,height:1080}});
const page=await context.newPage();
const result={checks:[],errors:[],external:[],responses:[],passed:false};
page.on('response',async r=>{if(r.status()>=400)result.responses.push({url:r.url(),status:r.status(),body:await r.text().catch(()=>'?')})});
page.on('pageerror',e=>result.errors.push(String(e)));
page.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(r.url()))result.external.push(r.url())});
const loaded=()=>page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor({timeout:120000});
const row=()=>page.locator('.m-table tbody tr').filter({has:page.getByRole('button',{name:/沪深北三市合计/})});
const two=()=>page.locator('.m-table tbody tr').filter({has:page.getByRole('button',{name:/沪深两市合计/})});
const control=async values=>{const f=path.join(root,'control.json');await writeFile(f,JSON.stringify({...JSON.parse(await readFile(f,'utf8')),...values}));};
const until=async fn=>{const end=Date.now()+240000;while(!await fn()){if(Date.now()>end)throw Error('condition timeout');await page.waitForTimeout(500);}};
try{
 await page.goto(process.env.WOLF_UI_ORIGIN);await loaded();
 assert.equal(await page.locator('.m-table tbody tr').count(),5);
 await control({release:true});
 await until(async()=>/2026-10-29/.test(await row().innerText()));
 assert.equal(await row().locator('.m-market-amount').innerText(),'4');
 assert.equal(await two().count(),0); // 已验收精简界面只显示三市；两市仍是服务共用计算。
 result.checks.push('managed-entry-real-http-two-and-three-market','startup-new-day-auto-follow');
 await page.getByRole('button',{name:/沪深北三市合计/}).click();
 await loaded();
 await page.getByRole('region',{name:'沪深北三市合计图表',exact:true}).waitFor();
 await page.getByRole('button',{name:'3 年',exact:true}).click();await loaded();
 const provenance=await page.locator('.m-activity-provenance').innerText();
 for(const label of ['未经双源核验','上交所','深交所','北交所'])assert.ok(provenance.includes(label),label);
 await page.getByRole('button',{name:'均线设置 ▾',exact:true}).click();assert.equal(await page.locator('fieldset').last().locator('input').count(),8);await page.keyboard.press('Escape');
 await page.getByRole('region',{name:'沪深北三市合计图表',exact:true}).focus();await page.keyboard.press('End');assert.match(await page.getByLabel('量额读数',{exact:true}).innerText(),/4\s+亿元/);
 await page.getByLabel('显示数据说明').check();assert.match(await page.locator('.m-notes').innerText(),/G1—G4/);
 result.checks.push('three-year-chart-eight-ma-source-date-scope');
 await page.getByLabel('成交额显示开始日期',{exact:true}).fill('2026-10-20');
 await page.getByLabel('成交额显示结束日期',{exact:true}).fill('2026-10-20');
 await page.getByRole('button',{name:'应用',exact:true}).click();await loaded();
 await page.getByRole('region',{name:'沪深北三市合计图表',exact:true}).focus();await page.keyboard.press('End');
 assert.match(await page.getByLabel('量额读数',{exact:true}).innerText(),/2026-10-20.*暂无数据/s);
 await page.getByRole('button',{name:'3 年',exact:true}).click();await loaded();
 result.checks.push('missing-one-market-shows-no-data-not-zero');
 // 新增日BSE失败，沪深推进；三市保留旧日期，刷新、重连后也不借新日期。
 await control({clock:'2026-10-31T07:00:00',fail_bse:true});
 await until(async()=>page.evaluate(async()=>{
   const d=await(await fetch('/__wolf/activity-config')).json();
   const ready=await(await fetch(d.endpoint+'/api/market-activity/session',{headers:{'X-Wolf-Client':'1'}})).json();
   return ready.market_anchors.sse_szse==='2026-10-31';
 }));
 assert.match(await row().innerText(),/2026-10-29/);
 await page.reload();await loaded();assert.match(await row().innerText(),/2026-10-29/);
 await page.getByRole('button',{name:'重新连接',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('.m-connection')?.textContent.includes('读取结束'));
 await loaded();assert.match(await row().innerText(),/2026-10-29/);
 result.checks.push('failed-bse-keeps-old-three-successful-two-persists','refresh-and-reconnect-separate-anchors');
 await page.getByRole('button',{name:/上证指数/}).click();await loaded();await page.getByLabel('指数K线副图',{exact:true}).selectOption('volume');await page.locator('.m-activity-chart canvas').waitFor();
 assert.match(await page.getByLabel('量额读数',{exact:true}).innerText(),/VOL|成交量/);
 await page.getByLabel('显示数据说明').uncheck();
 await page.setViewportSize({width:980,height:900});await page.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth,null,{timeout:5000});
 await page.getByRole('button',{name:/沪深北三市合计/}).click();
 await loaded();
 await page.evaluate(()=>{const d=document.createElement('div');d.textContent='隔离合成数据 · 非实际行情';Object.assign(d.style,{position:'fixed',bottom:'0',right:'0',zIndex:9999,background:'#fff1c2'});document.body.append(d)});
 await page.screenshot({path:path.join(root,'bse-page.png'),fullPage:true});
 assert.deepEqual(result.errors,[]);assert.deepEqual(result.external,[]);result.passed=true;
}finally{if(!result.passed){result.overflow=await page.locator('body *').evaluateAll(xs=>xs.filter(x=>x.getBoundingClientRect().right>innerWidth+1).map(x=>({tag:x.tagName,cls:x.className,width:x.getBoundingClientRect().width,right:x.getBoundingClientRect().right}))).catch(()=>[]);await page.screenshot({path:path.join(root,'bse-failed.png'),fullPage:true}).catch(()=>{});}result.visible=await page.locator('.m-missing').evaluateAll(xs=>xs.map(x=>x.title)).catch(()=>[]);result.text=await page.locator('.m-connection').innerText().catch(()=>'?');await context.close();await browser.close();await writeFile(path.join(root,'bse-browser.json'),JSON.stringify(result,null,2));}
