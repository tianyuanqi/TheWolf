/** 实际图表/解析/总览消费者的确定性检查，隔离替代React调度和传输。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');
const desktop = path.resolve(__dirname, '..');
function load(name, overrides = {}, cache = {}) {
  if (overrides[name]) return overrides[name];
  if (cache[name]) return cache[name];
  const filename = path.join(desktop, 'src', name + (name === 'MarketOverview' || name === 'DailyCandlestick' ? '.tsx' : '.ts'));
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, Date: overrides.Date ?? Date,
    window: overrides.window, AbortSignal, URL,
    require: request => overrides[request] ?? (request.startsWith('./') ? load(request.slice(2), overrides, cache) : require(request)),
  });
  cache[name] = module.exports; return module.exports;
}
const bar = (trade_date, close = '105.00') => ({ trade_date, open: '100.00', high: '110.00', low: '90.00', close,
  evidence_refs: [{ object_id: 'a'.repeat(64), locator: 'row' }, { object_id: 'b'.repeat(64), locator: 'row' }] });
function view(id = 'c') {
  const bars = Array.from({ length: 260 }, (_, i) => bar(new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0,10)));
  return { schema_version: 'csi300-price-snapshot-v1', snapshot_id: id.repeat(64), observation_id: 'd'.repeat(64),
    instrument: { id: 'csi:000300:price', code: '000300', name: '沪深300' }, unit: '点', timezone: 'Asia/Shanghai', pit_grade: 'latest_only',
    source_contract: {version: 'csi300-exact-ohlc-v1'}, bars, calendar_dates: bars.map(item => item.trade_date),
    window: { start: bars[0].trade_date, end: bars.at(-1).trade_date, expected_count: 260, actual_count: 260 },
    summary: { trade_date: bars.at(-1).trade_date, close: '105.00', daily_change_pct: '0.00', reason: null },
    evidence: [{ object_id: 'a'.repeat(64), source: 'eastmoney', url: 'https://east.invalid' }, { object_id: 'b'.repeat(64), source: 'csindex', url: 'https://csi.invalid' }] };
}
function nodes(value) {
  if (Array.isArray(value)) return value.flatMap(nodes);
  if (!value || typeof value !== 'object') return [];
  return [value, ...nodes(value.props?.children)];
}
function text(value) {
  if (Array.isArray(value)) return value.map(text).join('');
  if (!value || typeof value !== 'object') return value == null ? '' : String(value);
  return text(value.props?.children);
}
/** 与生产组件使用同一回调，卸载时检查计时器清理。 */
async function harness(component, props, request) {
  const hooks = [], effects = [], timers = new Map();
  let cursor = 0, timerId = 0, clock = 1000, tree;
  const react = {
    useState(initial) { const i = cursor++; if (!hooks[i]) hooks[i] = { value: initial }; return [hooks[i].value, value => { hooks[i].value = typeof value === 'function' ? value(hooks[i].value) : value; }]; },
    useRef(initial) { const i = cursor++; if (!hooks[i]) hooks[i] = { current: initial }; return hooks[i]; },
    useMemo(callback) { cursor++; return callback(); },
    useEffect(callback, dependencies) { const i = cursor++, old = hooks[i]; if (!old || dependencies.some((value,j) => value !== old.dependencies[j])) { hooks[i] = { dependencies }; effects.push(() => { old?.cleanup?.(); hooks[i].cleanup = callback(); }); } },
  };
  class ClockDate extends Date { static now() { return clock; } }
  const modules = load(component, { react, Date: ClockDate,
    './LegacySliceView': { request }, window: { setTimeout: callback => { timers.set(++timerId,callback);return timerId; }, clearTimeout: id => timers.delete(id) } });
  async function settle() { for (let n=0;n<8;n++) { cursor=0;tree=modules[component](props);while(effects.length) effects.shift()();await new Promise(resolve=>setImmediate(resolve)); } }
  function find(label) { return nodes(tree).find(node=>node.type==='button' && node.props.children===label); }
  await settle();
  return { settle, nodes:()=>nodes(tree), tree:()=>tree, text:()=>text(tree), button:find,
    click: async label=>{const node=find(label);assert.ok(node);assert.equal(!!node.props.disabled,false);await node.props.onClick();await settle();},
    advance:async ms=>{clock+=ms;const callbacks=[...timers.values()];timers.clear();for(const callback of callbacks)callback();await settle();},
    close:()=>{for(const hook of hooks)hook?.cleanup?.();assert.equal(timers.size,0);},
  };
}

test('真实四值实体/影线、方向与缩放边界',()=>{
  const { candleGeometry, zoomRange, panRange }=load('candlestickGeometry');
  const geometry=candleGeometry(bar('2026-09-30'),0,10,90,110);
  assert.equal(geometry.high,24);assert.equal(geometry.low,232);assert.equal(geometry.top,76);assert.equal(geometry.height,52);assert.equal(geometry.color,'#ff8a80');
  assert.equal(candleGeometry(bar('2026-09-30','95.00'),0,10,90,110).color,'#69d6b0');
  assert.equal(candleGeometry(bar('2026-09-30','100.00'),0,10,90,110).height,0);
  const small=zoomRange({start:0,count:8},8,7,.1);assert.equal(small.count,8);assert.equal(small.start,0);
  const zoom=zoomRange({start:200,count:60},260,250,.01);assert.equal(zoom.count,10);assert.ok(zoom.start<=250 && zoom.start+zoom.count>250);
  assert.equal(panRange({start:0,count:60},260,-1).start,0);assert.equal(panRange({start:200,count:60},260,1).start,200);
});

test('运行时拒绝错单位/摘要/精度/固定依据和未知状态',()=>{
  const {parseIndexView,parseIndexStatus,parseIndexEvidence}=load('indexTypes');
  const item=view();assert.equal(parseIndexView(item).bars.length,260);
  for(const mutate of [x=>x.unit='CNY',x=>x.bars[0].close='100.001',x=>x.summary.close='99.00',x=>x.bars[2].trade_date=x.bars[0].trade_date]) {
    const invalid=structuredClone(item);mutate(invalid);assert.throws(()=>parseIndexView(invalid));
  }
  assert.throws(()=>parseIndexStatus({enabled:true,stage:'mystery'}));
  assert.throws(()=>parseIndexEvidence({snapshot_id:'e'.repeat(64)},item,'a'.repeat(64)));
});

test('来源契约按版本校验，不将旧东财证据重标腾讯',()=>{
  const {parseIndexView,parseIndexStatus}=load('indexTypes');
  const old=view();const next=structuredClone(old);
  next.source_contract.version='csi300-tencent-exact-ohlc-v2';next.evidence[0].source='tencent';
  assert.equal(parseIndexView(next).evidence[0].source,'tencent');
  assert.equal(parseIndexView(old).evidence[0].source,'eastmoney');
  for(const mutate of [x=>x.source_contract.version='unknown',x=>delete x.source_contract,
      x=>x.evidence[0].source='eastmoney',x=>x.evidence.reverse()]){
    const invalid=structuredClone(next);mutate(invalid);assert.throws(()=>parseIndexView(invalid));
  }
  assert.equal(parseIndexStatus({enabled:true,stage:'fetching_tencent'}).stage,'fetching_tencent');
});

for(const source of ['eastmoney','tencent']){
  test(`实际总览显示固定 ${source} 来源与原字段定位`,async()=>{
    const item=view();if(source==='tencent'){item.source_contract.version='csi300-tencent-exact-ohlc-v2';item.evidence[0].source=source;}
    const h=await harness('MarketOverview',{token:'synthetic',restart:async()=>{}},async url=>{
      if(url.endsWith('/update'))return {json:async()=>({enabled:true,stage:'idle'})};
      if(url.includes('/evidence/')){
        const member=item.evidence.find(entry=>url.endsWith(entry.object_id));
        return {json:async()=>({...member,snapshot_id:item.snapshot_id,observation_id:item.observation_id,
          retrieval:{started_at:'2026-10-06T01:00:00Z',completed_at:'2026-10-06T01:00:01Z',published_at:null},
          rows:item.bars.map(row=>({...row,locator:'$.data.sh000300.day[380]',raw_values:row})),
          verification:'合成精确核对',unused_fields:['prec','version'],text_preview:'合成',preview_truncated:false})};
      }
      return {json:async()=>item};
    });
    try{
      const chart=h.nodes().find(node=>typeof node.type==='function'&&node.type.name==='DailyCandlestick');
      await chart.props.onEvidence(item.bars[0].trade_date);await h.settle();
      assert.match(h.text(),source==='tencent'?/腾讯/:/东方财富/);
      assert.match(h.text(),/中证官方/);assert.match(h.text(),/\$\.data\.sh000300\.day\[380\]/);
      assert.match(h.text(),/prec（未解释元数据）/);
    }finally{h.close();}
  });
}

test('实际图表首尾键盘、范围无交集、缺口空位及输入错误保留范围',async()=>{
  const bars=[bar('2026-09-28'),bar('2026-09-30','95.00')];const expected=['2026-09-28','2026-09-29','2026-09-30'];let chosen;
  const h=await harness('DailyCandlestick',{bars,expectedDates:expected,onSelect:day=>chosen=day,onEvidence:day=>chosen=day});
  try {
    assert.match(h.text(),/缺失交易日：2026-09-29/);
    assert.equal(h.nodes().filter(node=>node.type==='g').length,2);
    const svg=h.nodes().find(node=>node.type==='svg');
    svg.props.onKeyDown({key:'Home',preventDefault(){}});await h.settle();assert.equal(chosen,'2026-09-28');
    svg.props.onKeyDown({key:'End',preventDefault(){}});await h.settle();assert.equal(chosen,'2026-09-30');
    let inputs=h.nodes().filter(node=>node.type==='input');inputs[0].props.onChange({target:{value:'2026-10-01'}});inputs[1].props.onChange({target:{value:'2026-10-05'}});await h.settle();
    h.nodes().find(node=>node.type==='form').props.onSubmit({preventDefault(){}});await h.settle();assert.match(h.text(),/空范围/);assert.equal(h.nodes().filter(node=>node.type==='g').length,0);
    inputs=h.nodes().filter(node=>node.type==='input');inputs[0].props.onChange({target:{value:'2026-10-10'}});await h.settle();
    h.nodes().find(node=>node.type==='form').props.onSubmit({preventDefault(){}});await h.settle();assert.match(h.text(),/范围无效/);assert.match(h.text(),/空范围/);
  } finally {h.close();}
});

test('指数POST未送达，旧终态不得成功刷新；有界核对不自动重发',async()=>{
  let posts=0,reads=0;const status={stage:'idle',job_id:null,enabled:true};
  const h=await harness('MarketOverview',{token:'synthetic',restart:async()=>{}},async(url,token,method)=>{
    if(method==='POST'){posts++;throw new Error('合成未送达');}
    if(url.endsWith('/update'))return {json:async()=>({...status})};reads++;return {json:async()=>view()};
  });
  try {
    await h.click('检查更新');assert.equal(h.button('检查更新').props.disabled,true);
    await h.advance(120001);await h.click('核对结果');
    assert.equal(h.button('检查更新').props.disabled,false);assert.equal(posts,1);assert.equal(reads,1);assert.match(h.text(),/未发现新的更新任务/);
  }finally{h.close();}
});

test('迟到旧证据不能覆盖当前选择，切页卸载后响应不写入',async()=>{
  const pending=[];const item=view();
  const evidence=(member)=>({...member,snapshot_id:item.snapshot_id,observation_id:item.observation_id,
    rows:item.bars.map(row=>({...row,locator:'row',raw_values:{open:row.open,high:row.high,low:row.low,close:row.close}})),
    retrieval:{started_at:'2026-10-05T01:00:00Z',completed_at:'2026-10-05T01:00:01Z',published_at:null},
    verification:'合成双源核对',unused_fields:[],text_preview:'合成',preview_truncated:false});
  const h=await harness('MarketOverview',{token:'synthetic',restart:async()=>{}},async(url)=>{
    if(url.endsWith('/update'))return {json:async()=>({enabled:true,stage:'idle'})};
    if(url.includes('/evidence/')) return {json:()=>new Promise(resolve=>{pending.push(()=>resolve(evidence(item.evidence.find(member=>url.endsWith(member.object_id)))));})};
    return {json:async()=>item};
  });
  try {
    const chart=()=>h.nodes().find(node=>typeof node.type==='function' && node.type.name==='DailyCandlestick');
    const old=chart().props.onEvidence(item.bars[0].trade_date);await h.settle();
    chart().props.onSelect(item.bars[1].trade_date);await h.settle();
    assert.ok(!h.text().includes('本地双源依据'));
    assert.equal(pending.length,2);pending.splice(0).forEach(resolve=>resolve());await old;await h.settle();
    assert.ok(!h.text().includes('本地双源依据'));
    const fresh=chart().props.onEvidence(item.bars[1].trade_date);await h.settle();
    pending.splice(0).forEach(resolve=>resolve());await fresh;await h.settle();
    assert.match(h.text(),/本地双源依据/);
    const unmounted=chart().props.onEvidence(item.bars[2].trade_date);await h.settle();h.close();
    pending.splice(0).forEach(resolve=>resolve());await unmounted;
  }finally{h.close();}
});

for (const result of ['business_changed','evidence_changed','unchanged','source_not_ready','failed','interrupted']) {
  test(`实际总览更新结果 ${result}：成功整份刷新，失败/未就绪保留旧图`,async()=>{
    let reads=0,posts=0;let state={enabled:true,stage:'idle'};
    const h=await harness('MarketOverview',{token:'synthetic',restart:async()=>{}},async(url,token,method)=>{
      if(method==='POST'){posts++;state={enabled:true,job_id:'new-job',stage:['failed','interrupted'].includes(result)?result:'completed',result,message:'合成'+result};return {json:async()=>state};}
      if(url.endsWith('/update'))return {json:async()=>state};
      reads++;return {json:async()=>view(reads>1?'e':'c')};
    });
    try{
      await h.click('检查更新');assert.equal(posts,1);
      assert.equal(reads,['business_changed','evidence_changed','unchanged'].includes(result)?2:1);
      assert.match(h.text(),new RegExp('合成'+result));
      assert.equal(h.button('检查更新').props.disabled,false);
      assert.equal(h.nodes().find(node=>typeof node.type==='function'&&node.type.name==='DailyCandlestick').props.bars.length,260);
    }finally{h.close();}
  });
}
