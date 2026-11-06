/** 实际页面与HTTP，服务时钟由隔离夹具控制，来源响应只含合成数据。 */
import assert from 'node:assert/strict';
import {readFile,writeFile,rename} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const root=process.env.WOLF_PERIODIC_ROOT;
const browser=await chromium.launch({...(process.env.WOLF_BROWSER_EXECUTABLE ? {executablePath:process.env.WOLF_BROWSER_EXECUTABLE} : {}),headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const context=await browser.newContext({viewport:{width:1440,height:1080}}),page=await context.newPage();
const record={checks:[],errors:[],responses:[],external:[],passed:false};
page.on('response',r=>{if(r.url().includes('/api/'))record.responses.push({url:r.url(),status:r.status()})});
page.on('pageerror',e=>record.errors.push(String(e)));
page.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(r.url()))record.external.push(r.url())});
async function control(value){const old=JSON.parse(await readFile(path.join(root,'control.json'),'utf8'));await writeFile(path.join(root,'control.tmp'),JSON.stringify({...old,...value}));await rename(path.join(root,'control.tmp'),path.join(root,'control.json'))}
async function ledger(){return JSON.parse(await readFile(path.join(root,'data/overview-periodic-ledger.json'),'utf8'))}
async function settled(day){const deadline=Date.now()+120000;while(Date.now()<deadline){try{const value=await ledger(),batch=value.batches.at(-1);if(batch?.day===day&&batch.state!=='running')return value}catch{}await new Promise(r=>setTimeout(r,150))}throw Error('batch did not settle '+day)}
async function pageShows(text){await page.getByText(text,{exact:false}).first().waitFor({timeout:120000})}
async function shot(name){await page.evaluate(()=>{let e=document.getElementById('synthetic-label');if(!e){e=document.createElement('div');e.id='synthetic-label';document.body.append(e)}e.textContent='隔离合成数据 · 非实际行情';Object.assign(e.style,{position:'fixed',bottom:'8px',right:'8px',zIndex:'9999',background:'#fff1c2',padding:'8px'})});await page.screenshot({path:path.join(root,name),fullPage:true})}
try{
 await page.clock.install();
 let failedHandshakes=0;
 await page.route('**/api/market-activity/session',route=>{failedHandshakes++;return route.abort()});
 await page.goto(process.env.WOLF_UI_ORIGIN);await pageShows('读取结束 · 当前读取不采集新行情');
 await pageShows('每天北京时间07:00检查');assert.ok(failedHandshakes>0,'initial activity handshake was interrupted');
 await page.unroute('**/api/market-activity/session');
 await control({release:true});let value=await settled('2026-10-30');
 assert.equal(value.days['2026-10-30'].requests,12);assert.equal(value.days['2026-10-30'].bytes,10616832);
 await page.clock.fastForward(30000);
 await pageShows('2026-10-29');await pageShows('今日12/80次');
 record.checks.push('managed-start-full-batch-12-requests-10.125MiB','real-http-page-follows-new-prices-and-activity');
 assert.match(await page.locator('.m-activity-provenance').innerText(),/未经双源核验/);
 record.checks.push('initial-activity-handshake-failure-recovers-get-only-without-reconnect');
 await page.clock.fastForward(360000);await page.waitForTimeout(100);
 assert.equal((await ledger()).attempts.length,12);record.checks.push('past-five-minutes-no-stop-no-repeat-source');
 await control({clock:'2026-10-31T07:00:00',fail_ids:['sse:000001:price']});value=await settled('2026-10-31');
 assert.equal(value.days['2026-10-31'].requests,11);assert.equal(value.months['2026-10'].requests,23);
 await page.clock.fastForward(30000);await pageShows('本批部分更新未成功');
 await page.getByRole('button',{name:/上证指数/}).click();assert.match(await page.locator('.m-table tbody tr').filter({hasText:'上证指数'}).innerText(),/2026-10-29/);
 await page.getByRole('button',{name:/深证成指/}).click();await page.locator('.m-table tbody tr').filter({hasText:'深证成指'}).getByText('2026-10-30',{exact:true}).waitFor({timeout:120000});
 for(const name of ['深证成指','创业板指','科创50','沪深两市合计']) {
   await page.locator('.m-table tbody tr').filter({hasText:name}).getByText('2026-10-30',{exact:true}).waitFor({timeout:120000});
 }
 record.checks.push('next-day-recomputed-failed-index-keeps-old-independent-indices-publish');
 const before=await page.locator('.m-table').innerText();
 await page.route('**/api/overview-update/status',route=>route.abort());await page.clock.fastForward(30000);await pageShows('暂时无法核对自动更新状态');assert.equal(await page.locator('.m-table').innerText(),before);
 await page.unroute('**/api/overview-update/status');await page.clock.fastForward(30000);await pageShows('今日11/80次');
 record.checks.push('connection-interruption-keeps-view-and-recovers-get-only');
 await page.getByRole('button',{name:'重新连接',exact:true}).click();await pageShows('读取结束 · 当前读取不采集新行情');await pageShows('每天北京时间07:00检查');
 assert.equal((await ledger()).attempts.length,23);record.checks.push('reconnect-does-not-reissue-sources');
 await shot('periodic-main.png');await page.setViewportSize({width:820,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await shot('periodic-narrow.png');
 assert.deepEqual(record.errors,[]);assert.deepEqual(record.external,[]);record.passed=true;
}finally{if(!record.passed){await page.screenshot({path:path.join(root,'failure.png'),fullPage:true});await writeFile(path.join(root,'failure.txt'),await page.locator('body').innerText())}await writeFile(path.join(root,'browser-result.json'),JSON.stringify(record,null,2));await context.close();await browser.close()}
