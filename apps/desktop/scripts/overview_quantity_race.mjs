/** 真实服务/Client与React页面；仅延迟P1响应交付并加速观察等待，不伪造响应。 */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const root=process.env.WOLF_RACE_ROOT, result={passed:false,errors:[],external:[],checks:[]};
const browser=await chromium.launch({executablePath:process.env.WOLF_BROWSER_EXECUTABLE,headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const context=await browser.newContext({viewport:{width:1440,height:1080}});const page=await context.newPage();
// 只加速产品30秒/3秒观察等待，金融日期、API内容和请求次序均不替换。
await page.addInitScript(()=>{const timer=window.setTimeout;window.setTimeout=(fn,delay,...args)=>timer(fn,delay===30000||delay===3000?100:delay,...args)});
page.on('pageerror',e=>result.errors.push(String(e)));
let hold=false,release,received;
await context.route('**/*',async route=>{
 const u=new URL(route.request().url());
 if(u.protocol!=='http:'||u.hostname!=='127.0.0.1'){result.external.push(u.href);return route.abort()}
 if(hold && decodeURIComponent(u.pathname)==='/api/market-activity/sse:000001:price/view'){
  hold=false;const response=await route.fetch();assert.equal(response.status(),200);received();
  await new Promise(resolve=>{release=resolve});return route.fulfill({response});
 }
 return route.continue();
});
const loaded=()=>page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor({timeout:60000});
try{
 await page.goto(process.env.WOLF_UI_ORIGIN);await loaded();await page.locator('.m-activity-chart canvas').waitFor();
 await page.getByRole('button',{name:/深证成指/}).click();await loaded();await page.locator('.m-activity-chart canvas').waitFor();
 await page.getByRole('group',{name:'图表显示范围',exact:true}).getByRole('button',{name:'3 月',exact:true}).click();await loaded();
 const held=new Promise(resolve=>{received=resolve});hold=true;
 await page.getByRole('button',{name:/上证指数/}).click();await held;
 await writeFile(path.join(root,'control.txt'),'price');
 await page.waitForFunction(()=>document.querySelector('.m-table tbody tr:first-child .m-metric-value')?.textContent==='106.00',null,{timeout:60000});
 assert.equal((JSON.parse(await readFile(path.join(root,'p2.json'),'utf8'))).missing_quantity,true);
 release();release=undefined;
 await loaded();
 assert.equal(await page.getByRole('button',{name:'重新读取',exact:true}).isEnabled(),true);
 assert.equal(await page.locator('.m-activity-chart canvas').count(),0,'旧配对不可挂到P2');
 assert.match(await page.locator('.m-activity-empty').innerText(),/暂无数据/);
 result.checks.push('p1-late-p2-missing-loading-ended-reread-enabled-no-stale-pair');
 await page.screenshot({path:path.join(root,'missing-pair.png'),fullPage:true});
 await writeFile(path.join(root,'control.txt'),'quantity');
 await page.locator('.m-activity-chart canvas').waitFor({timeout:60000});await loaded();
 assert.equal(await page.getByRole('button',{name:'重新读取',exact:true}).isEnabled(),true);
 assert.equal(await page.locator('.m-table tbody tr:first-child .m-metric-value').innerText(),'106.00');
 result.checks.push('later-p2-quantity-publish-observed-and-rendered');
 await page.screenshot({path:path.join(root,'recovered-pair.png'),fullPage:true});
 assert.deepEqual(result.errors,[]);assert.deepEqual(result.external,[]);result.passed=true;
}finally{
 release?.();result.phase=await page.locator('.m-connection').innerText().catch(()=>'?');
 await context.close();await browser.close();await writeFile(path.join(root,'browser-result.json'),JSON.stringify(result,null,2));
}
