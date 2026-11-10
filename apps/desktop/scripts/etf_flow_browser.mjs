/** 正式托管页面/操作区/HTTP；只有Python隔离种子，浏览器没有金融响应替身。 */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const root=process.env.WOLF_ETF_TEST_ROOT;
const browser=await chromium.launch({headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const result={checks:[],errors:[],external:[],passed:false};
page.on('pageerror',error=>result.errors.push(String(error)));
page.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(r.url()))result.external.push(r.url());});
const center=page.locator('#operation-center');
try{
 await page.goto(process.env.WOLF_UI_ORIGIN);
 await page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor({timeout:30000});
 await center.locator('summary').click();
 await page.getByLabel('更新对象',{exact:true}).selectOption('etf.flow.update');
 const create=center.getByRole('button',{name:'明确发起新检查',exact:true});
 await create.waitFor();await page.waitForFunction(()=>[...document.querySelectorAll('#operation-center button')].some(b=>b.textContent==='明确发起新检查'&&!b.disabled));
 let requests=(await readFile(path.join(root,'http.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 assert.equal(requests.filter(r=>r.method==='POST').length,0,'打开/连接不能自动更新');
 await create.click();
 await center.getByText('该请求已精确确认完成；其他未知记录仍保留',{exact:true}).waitFor({timeout:30000});
 result.checks.push('actual-managed-descriptor-and-browser-client','explicit-etf-update-publishes-cached-input-with-zero-network');
 await center.getByRole('button',{name:'复制当前核对记录',exact:true}).click();
 const book=JSON.parse(await page.getByLabel('公开核对文本',{exact:true}).inputValue());
 assert.equal(book.operation,'etf.flow.update');assert.equal(book.settled.length,1);assert.equal(book.settled[0].state,'completed');
 await page.reload();await page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor();
 await center.locator('summary').click();await page.getByLabel('更新对象',{exact:true}).selectOption('etf.flow.update');
 await center.getByText(/本页精确核对的终态/).waitFor();
 requests=(await readFile(path.join(root,'http.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 assert.equal(requests.filter(r=>r.method==='POST'&&r.path==='/api/etf-flow/update').length,1);
 result.checks.push('refresh-retains-exact-operation-without-post-retry');
 await page.setViewportSize({width:980,height:900});
 await page.getByLabel('更新对象',{exact:true}).focus();await page.keyboard.press('Tab');
 assert.ok(await page.locator(':focus').count());
 await page.screenshot({path:path.join(root,'etf-operation-center.png'),fullPage:true});
 assert.deepEqual(result.errors,[]);assert.deepEqual(result.external,[]);result.passed=true;
}finally{
 if(!result.passed){await page.screenshot({path:path.join(root,'etf-browser-failed.png'),fullPage:true}).catch(()=>{});result.text=await page.locator('body').innerText().catch(()=>'?');}
 await context.close();await browser.close();await writeFile(path.join(root,'etf-browser.json'),JSON.stringify(result,null,2));
}
