/** S3审查反例：全部金融结果来自真实回环服务，响应不替换。 */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(pathToFileURL(path.join(process.env.WOLF_PLAYWRIGHT_MODULE,'index.mjs')).href);
const root=process.env.WOLF_ETF_TEST_ROOT, expected=JSON.parse(await readFile(path.join(root,'page-expectations.json'),'utf8'));
const browser=await chromium.launch({headless:true,proxy:{server:'http://127.0.0.1:9',bypass:'127.0.0.1'}});
const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage();
const result={checks:[],views:[],errors:[],external:[],passed:false};
page.on('pageerror',error=>result.errors.push(String(error)));
page.on('request',r=>{if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(r.url()))result.external.push(r.url());});
const app=page.locator('.etf-app'),section=n=>app.locator(`[data-module="fund-flows.${n}"]`);
let view;
const responses=new Map();
const identity=v=>JSON.stringify([v.snapshot_id,v.mode,v.period,v.end,v.group_id,v.input_version,v.summary.evaluation?.result_id??null]);
page.on('response',async response=>{
  if(/\/api\/etf-flow\/snapshots\/[a-f0-9]+\?/.test(response.url())&&response.status()===200){
    const value=await response.json();responses.set(identity(value),{value,url:response.url()});
  }
});
async function read(action){
  await action();
  // 成功固定视图可来自版本缓存；仍必须匹配实际渲染身份及此前真实HTTP产物。
  await page.waitForFunction(()=>{
    const app=document.querySelector('.etf-app'),raw=app?.getAttribute('data-view-identity');if(!raw)return false;
    const [,mode,period,end,group]=JSON.parse(raw);
    const dates=app.querySelector('[aria-label="观察日期"]'),groups=app.querySelector('[aria-label="观察分组"]');
    const selectedMode=app.querySelector('[aria-label="回看方式"] button[aria-pressed="true"]')?.textContent;
    const selectedPeriod=app.querySelector('[aria-label="图表范围"] button[aria-pressed="true"]')?.textContent;
    return dates?.value===end&&groups?.value===(group??'')&&selectedMode===(mode==='original'?'当时版本':'当前版本重算')&&selectedPeriod===period+'日';
  });
  const rendered=await app.getAttribute('data-view-identity');
  for(let i=0;i<100&&!responses.has(rendered);i++)await page.waitForTimeout(10);
  const received=responses.get(rendered);assert.ok(received,'必须是实际HTTP已验证视图的渲染或缓存命中');view=received.value;
  await app.getByText(`已读取 ${view.end} · ${view.mode==='original'?'当时版本':'当前版本重算'}`,{exact:true}).waitFor();
  await page.waitForFunction(v=>{const node=document.querySelector('[data-module="fund-flows.14"]');
    return node?.textContent.includes(v.snapshot_id)&&node.textContent.includes(v.input_version);},view);
  result.views.push({url:received.url,snapshot:view.snapshot_id,mode:view.mode,end:view.end,group:view.group_id,
    input:view.input_version,result:view.summary.evaluation?.result_id,amount:view.summary.evaluation?.amount,
    complete:view.data_status.complete_amount_through});return view;
}
async function clickRecord(date){
  const before=view, row=before.history.find(x=>x.date===date);assert.ok(row);
  await read(()=>section('12').getByRole('button',{name:new RegExp(date)}).click());
  assert.equal(view.snapshot_id,before.snapshot_id);assert.equal(view.mode,before.mode);assert.equal(view.group_id,before.group_id);
  for(const key of ['result_id','input_version','pool_version','rule_version','amount','valid_count'])assert.equal(view.summary.evaluation[key],row[key],key);
  assert.equal(await app.getByLabel('观察分组',{exact:true}).inputValue(),view.group_id??'');
}
async function adjustment(factor,tail,proof){
  const readout=section('10').locator('.etf-readout');
  await readout.getByText(new RegExp(`倍率 ${factor} · 尾差 ${tail.replace('.','\\.')} 份`)).waitFor();
  const response=page.waitForResponse(r=>r.url().endsWith('/evidence/'+proof)&&r.status()===200);
  await readout.getByRole('button',{name:new RegExp('查看调整证据 '+proof.slice(0,8))}).click();
  const data=await (await response).json();assert.equal(data.snapshot_id,view.snapshot_id);assert.equal(data.object_id,proof);
  await page.getByRole('dialog').getByText(/测试折算公告倍率和尾差段/).waitFor();
  await page.keyboard.press('Escape');assert.equal(await readout.locator('button:focus').count(),1);
}
try{
  await page.goto(process.env.WOLF_UI_ORIGIN);await page.getByText('读取结束 · 当前读取不采集新行情',{exact:true}).waitFor({timeout:30000});
  await read(()=>page.getByRole('navigation',{name:'市场研究',exact:true}).getByRole('button',{name:'大资金动向',exact:true}).click());
  const group=view.groups.find(g=>g.member_ids.includes(expected.members[0].id));
  await read(()=>app.getByLabel('观察分组',{exact:true}).selectOption(group.id));
  await clickRecord(expected.end);await clickRecord(expected.previous);
  assert.equal(view.summary.evaluation.amount,'40.0');assert.equal(view.summary.evaluation.valid_count,2);
  await adjustment('2','0.5',expected.old_proof);
  assert.ok((await section('13').innerText()).includes('同一公告第1段'));
  assert.ok((await section('13').innerText()).includes('同一公告第2段'));
  await section('13').getByRole('button',{name:'查看事件证据',exact:true}).last().click();
  await page.getByRole('dialog').getByText(/定位：测试折算公告倍率和尾差段/).waitFor();await page.keyboard.press('Escape');
  result.checks.push('original-group-same-cross-day-preserves-record-identity','old-adjustment-source-multiplier-tail-real-get','same-source-distinct-event-locators');
  await read(()=>app.getByRole('button',{name:'当前版本重算',exact:true}).click());
  await read(()=>app.getByLabel('观察日期',{exact:true}).fill(expected.end));
  await clickRecord(expected.end);await clickRecord(expected.previous);
  assert.equal(view.summary.evaluation.amount,'40.0');assert.equal(view.group_id,group.id);
  const pinned=structuredClone(view);
  const currentResponse=page.waitForResponse(async r=>r.url().endsWith('/api/etf-flow/current')&&r.status()===200
    &&(await r.json()).snapshot_id!==pinned.snapshot_id);
  await app.getByRole('button',{name:'更新数据',exact:true}).click();
  const center=page.locator('#operation-center');await center.getByRole('button',{name:'明确发起新检查',exact:true}).click();
  await center.getByText('该请求已精确确认完成；其他未知记录仍保留',{exact:true}).waitFor({timeout:30000});
  await currentResponse;
  // 等待更新后重新读取current的实际HTTP，再核对仍显示所点的旧快照。
  await app.getByText('正在查看所点记录的固定版本；重新读取可回到当前快照。',{exact:true}).waitFor();
  await page.waitForFunction(snapshot=>document.querySelector('[data-module="fund-flows.14"]')?.textContent.includes(snapshot),pinned.snapshot_id);
  await section('14').locator('summary').click();
  assert.ok((await section('14').innerText()).includes(pinned.input_version));
  await adjustment('2','0.5',view.members[0].series.at(-1).adjustment_detail.source_ids[0]);
  await read(()=>app.getByRole('button',{name:'重新读取',exact:true}).click());
  assert.notEqual(view.snapshot_id,pinned.snapshot_id);assert.notEqual(view.input_version,pinned.input_version);
  assert.equal(view.group_id,group.id);assert.equal(view.summary.evaluation.amount,'50.00');
  await adjustment('3','0.75',expected.new_proof);
  await read(()=>app.getByRole('button',{name:'当时版本',exact:true}).click());
  assert.equal(view.summary.evaluation.amount,'40.0');await adjustment('2','0.5',expected.old_proof);
  result.checks.push('current-group-cross-day-fixed-identity','explicit-update-keeps-pinned-old-result','explicit-read-unpins-to-new-snapshot','original-adjustment-unchanged-after-late-correction');
  await read(()=>app.getByLabel('观察分组',{exact:true}).selectOption(''));
  await read(()=>app.getByLabel('观察日期',{exact:true}).fill(expected.end));
  assert.equal(view.data_status.complete_amount_through,expected.previous);
  await section('14').getByText(new RegExp('完整金额覆盖至 '+expected.previous)).waitFor();
  await read(()=>app.getByRole('button',{name:'当前版本重算',exact:true}).click());
  assert.equal(view.data_status.complete_amount_through,expected.end);
  assert.equal(view.summary.evaluation.c2.positive_count,3);assert.equal(view.summary.evaluation.c2.denominator,4);
  await section('08').getByText('增加 3 / 4 只 · 减少 0 / 4 只',{exact:true}).waitFor();
  await section('14').getByText(new RegExp('完整金额覆盖至 '+expected.end)).waitFor();
  await read(()=>app.getByRole('button',{name:'当时版本',exact:true}).click());
  await read(()=>app.getByLabel('观察日期',{exact:true}).fill(expected.initial_end));
  assert.equal(view.data_status.complete_amount_through,null);
  await section('14').getByText(/完整金额覆盖截止日：未知/).waitFor();
  result.checks.push('partial-and-late-nav-coverage-original-current','c2-three-of-four-with-zero-in-denominator','unrecorded-coverage-remains-unknown');
  await read(()=>app.getByRole('button',{name:'当前版本重算',exact:true}).click());
  await read(()=>app.getByLabel('观察日期',{exact:true}).fill(expected.first_input));
  assert.equal(view.summary.evaluation,null,'超出已保存重算档案的日期保持未知，不能冒充0有效成员');
  await section('08').getByText('增加 — / — 只 · 减少 — / — 只',{exact:true}).waitFor();
  assert.ok((await section('08').innerText()).includes('有效成员 — 只'));
  await section('14').getByText(/完整金额覆盖截止日：未知/).waitFor();
  result.checks.push('outside-archive-c2-unknown-not-zero-count');
  await read(()=>app.getByRole('button',{name:'当时版本',exact:true}).click());
  await read(()=>app.getByLabel('观察日期',{exact:true}).fill(expected.previous));
  await page.screenshot({path:path.join(root,'etf-view-fix-light.png'),fullPage:true});
  await page.setViewportSize({width:980,height:900});await app.getByRole('button',{name:'深色备选主题',exact:true}).click();
  await page.screenshot({path:path.join(root,'etf-view-fix-dark-980.png'),fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const requests=(await readFile(path.join(root,'http.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
  assert.equal(requests.filter(r=>r.method==='POST').length,1);
  assert.deepEqual(result.errors,[]);assert.deepEqual(result.external,[]);result.passed=true;
}finally{
  if(!result.passed){result.text=await page.locator('body').innerText().catch(()=>'?');await page.screenshot({path:path.join(root,'etf-view-fix-failed.png'),fullPage:true}).catch(()=>{});}
  await context.close();await browser.close();await writeFile(path.join(root,'etf-view-browser.json'),JSON.stringify(result,null,2));
}
