/** 实际SQL范围读取hook的可控交错；HTTP字段与缓存由stored_views.harness另验。 */
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
export const IDS = ['sse:000001:price', 'szse:399001:price', 'szse:399006:price', 'sse:000688:price'];
export const MARKET = 'cn-a-turnover';
const coverage = {start:'2026-01-05',end:'2026-10-28'};
const deferred = () => { let resolve,reject; const promise=new Promise((a,b)=>{resolve=a;reject=b}); return {promise,resolve,reject}; };
export function harness({noQuantity=false,failedConnection=false}={}) {
  const slots=[], effects=[], pending=[], calls=[], waits=new Map(), timers=new Map();
  const priceVersions=new Map(IDS.map(id=>[id,'p1'])), quantityVersions=new Map(IDS.map(id=>[id,'a1']));
  let hook=0,queued=false,mounted=true,view,serial=0,connectionHold,failVersions=false,connectionFailures=0,marketVersion='market1';
  let descriptorFailures=0,handshakeFailures=0;
  let props={connection:{expected:{config_id:'base'},instance:'instance'},refreshToken:0,selected:IDS[0],
    range:{preset:'12'},frequency:'daily',ma:[5],field:'volume',activityMA:[5]};
  const drain=async()=>{for(let i=0;i<150;i++) {
    await Promise.resolve();
    for(const [key,timer] of [...timers]) if(timer.ms<30000){timers.delete(key);timer.fn()}
  }};
  async function request(kind,id,value) {
    const gate=waits.get(kind+':'+id); waits.delete(kind+':'+id); calls.push({kind,id,value});
    if(gate)await gate.promise; return value;
  }
  class Price {closed=false;instance='instance';expected={config_id:'price'};static async connect(){if(handshakeFailures-->0)throw Error('handshake unavailable');return new Price()};close(){this.closed=true}}
  class Activity {closed=false;static async connect(){if(connectionHold)await connectionHold.promise;if(failedConnection||connectionFailures-->0)throw Error('offline');return new Activity()};close(){this.closed=true}}
  const range=(id,version,frequency)=>({id,publication:version.publication_id,frequency,calendar_version:'calendar',requested_range:coverage,series:{rows:[{start:coverage.end,end:coverage.end}]}});
  class StoredViews {
    constructor(price,activity){this.price=price;this.activity=activity}
    clear(){}
    async versions(){if(failVersions)throw Error('version unavailable');return {store_id:'store',indices:IDS.map(id=>({index_id:id,
      price:priceVersions.get(id)?{publication_id:priceVersions.get(id),source_coverage:coverage}:null,
      activity:quantityVersions.get(id)?{publication_id:quantityVersions.get(id),binding:priceVersions.get(id),source_coverage:coverage}:null})),
      markets:[{series_id:MARKET,activity:marketVersion?{publication_id:marketVersion,binding:'2026-10-29',source_coverage:coverage}:null}]}}
    async overview(id,version){return request('overview',id,{snapshot_id:version.publication_id,performance:{checked:true}})}
    async marketOverview(id,version){return request('market',id,{activity_id:version.publication_id})}
    async priceRange(id,version,_range,frequency){return request('price',id,range(id,version,frequency))}
    async activityRange(id,version,_range,_field,frequency){return request('quantity',id,range(id,version,frequency))}
  }
  const schedule=()=>{if(!queued&&mounted){queued=true;queueMicrotask(()=>{queued=false;if(mounted)render()})}};
  const react={
    useState:initial=>{const n=hook++;if(!(n in slots))slots[n]=initial;return [slots[n],v=>{const next=typeof v==='function'?v(slots[n]):v;if(!Object.is(next,slots[n])){slots[n]=next;schedule()}}]},
    useRef:initial=>{const n=hook++;return slots[n]??={current:initial}},
    useEffect:(fn,deps)=>{const n=hook++,old=effects[n];if(!old||deps.some((x,i)=>x!==old.deps[i])){effects[n]={deps,cleanup:old?.cleanup};pending.push([n,fn])}}
  };
  const module={exports:{}};
  const imports={react,'./browserHost':{indexConnectionDescriptor:async()=>{if(descriptorFailures-->0)throw Error('descriptor unavailable');return {}},activityConnectionDescriptor:async()=>noQuantity?undefined:{}},
    './indexSeriesClient':{IndexSeriesClient:Price},'./activityClient':{ActivityClient:Activity},
    './indexSeriesTypes':{OVERVIEW_INDICES:IDS.map(id=>({id}))},'./activityTypes':{LEGACY_MARKET:MARKET},
    './storedViews':{StoredViews,requestedRange:()=>coverage}};
  const source=readFileSync(new URL('../src/useStoredOverview.ts',import.meta.url),'utf8');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText,
    {module,exports:module.exports,require:name=>{assert.ok(name in imports,name);return imports[name]},AbortController,Error,Map,Set,JSON,
      setTimeout:(fn,ms)=>{const key=++serial;timers.set(key,{fn,ms});return key},clearTimeout:key=>timers.delete(key)});
  function render(){hook=0;view=module.exports.useStoredOverview(props);for(const [n,fn] of pending.splice(0)){effects[n].cleanup?.();effects[n].cleanup=fn()}}
  return {calls,priceVersions,quantityVersions,drain,get view(){return view},
    hold:(kind,id)=>{const d=deferred();waits.set(kind+':'+id,d);return d},holdConnection:()=>connectionHold=deferred(),
    failVersions:value=>{failVersions=value}, failConnections:count=>{connectionFailures=count}, marketVersion:value=>{marketVersion=value},start:async()=>{render();await drain()},
    failDescriptor:count=>{descriptorFailures=count},failHandshake:count=>{handshakeFailures=count},
    change:async fields=>{props={...props,...fields};render();await drain()},
    select:async selected=>{props={...props,selected};render();await drain()},
    reconnect:async()=>{props={...props,connection:{...props.connection,instance:'changed'}};render();await drain()},
    poll:async()=>{const entry=[...timers].find(([,v])=>v.ms===30000);assert.ok(entry,'应安排轻量版本检查');timers.delete(entry[0]);await entry[1].fn();await drain()},
    close:async()=>{mounted=false;for(const effect of effects)effect?.cleanup?.();await drain();assert.equal(timers.size,0)}};
}
