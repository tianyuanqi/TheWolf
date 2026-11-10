/** 标签页公开操作记录。记录不授予连接权限；终态落盘并读回后才消除未决。 */
import type { EtfIdentity } from './etfFlowClient';
type ExistingKind = 'index.series.update' | 'market.activity.update';
export type Kind = ExistingKind | 'etf.flow.update';
export type Identity = EtfIdentity | { instance_id: string; config_id: string; request_id: string; operation: ExistingKind; index_id?: string; series_id?: string;
  parameters?: { price_snapshot_id: string; expected_activity_id: string | null } | { anchor_date: string; expected_activity_id: string | null } };
export type Scope = { endpoint: string; data_scope_id: string; operation: Kind; target: string };
export type Terminal = 'completed' | 'failed' | 'interrupted' | 'rejected';
type Settled = { identity: Identity; state: Terminal; source: 'local' | 'carried' };
export type Book = { pending: Identity | null; history: Identity[]; settled: Settled[]; continuity_unverified: boolean };
const kinds = ['index.series.update','market.activity.update','etf.flow.update'];
const ids = ['csi:000300:price','sse:000001:price','csi:000852:price','szse:399001:price','szse:399006:price','sse:000688:price'];
const activities = ['sse:000001:price','szse:399001:price','szse:399006:price','sse:000688:price','cn-a-turnover','cn-a-turnover-sse-szse'];
const digest = /^[a-f0-9]{64}$/;
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const terminals = new Set(['completed','failed','interrupted','rejected']);
const listeners = new Set<() => void>();
let revision = 0;
const errors = new Map<string,string>();
const preserved = new Map<string,Book>();
export const subscribeOperations = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const operationsRevision = () => revision;
function changed() { revision++; listeners.forEach(x=>x()); }
function exact(value: unknown, keys: string[]): asserts value is Record<string, unknown> {
  if (!value || typeof value!=='object' || Array.isArray(value) || Object.keys(value).sort().join('|')!==[...keys].sort().join('|')) throw new Error('操作记录字段无效');
}
function targetValid(kind: Kind, target: string) {
  if(kind==='etf.flow.update')return digest.test(target);
  return kind==='index.series.update' ? ids.includes(target) : activities.includes(target);
}
/** 严格校验公开作用域；读取存储只供展示，不据其端点建立连接。 */
export function validScope(value: unknown): Scope {
  exact(value,['endpoint','data_scope_id','operation','target']);
  if (typeof value.endpoint!=='string' || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(value.endpoint) || Number(new URL(value.endpoint).port)>65535
      || typeof value.data_scope_id!=='string' || !digest.test(value.data_scope_id) || !kinds.includes(String(value.operation))
      || typeof value.target!=='string' || !targetValid(value.operation as Kind,value.target)) throw new Error('操作记录范围无效');
  return value as Scope;
}
/** 身份包含完整目标／参数，不能把旧四元组猜成另一个指数或量额请求。 */
export function validIdentity(value: unknown, scope: Scope): Identity {
  const keys=['instance_id','config_id','request_id','operation',...(scope.operation==='index.series.update'?['index_id']:scope.operation==='market.activity.update'?['series_id','parameters']:scope.operation==='etf.flow.update'?['parameters']:[])];
  exact(value,keys);
  if (value.operation!==scope.operation || typeof value.instance_id!=='string' || !uuid.test(value.instance_id) || typeof value.config_id!=='string' || !digest.test(value.config_id)
      || typeof value.request_id!=='string' || !(scope.operation==='etf.flow.update'?/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$/:scope.operation==='market.activity.update'?/^[A-Za-z0-9_-]{1,80}$/:/^[A-Za-z0-9_-]{1,128}$/).test(value.request_id)) throw new Error('操作身份无效');
  if(scope.operation==='etf.flow.update'){
    exact(value.parameters,['expected_snapshot_id','plan_id']);const p=value.parameters;
    if(typeof p.plan_id!=='string' || !digest.test(p.plan_id) || (p.expected_snapshot_id!==null && (typeof p.expected_snapshot_id!=='string' || !digest.test(p.expected_snapshot_id))))throw new Error('ETF原计划或前提无效');
  }
  if (scope.operation==='index.series.update' && value.index_id!==scope.target) throw new Error('指数目标不符');
  if (scope.operation==='market.activity.update') {
    if (value.series_id!==scope.target) throw new Error('量额目标不符');
    const key=['cn-a-turnover','cn-a-turnover-sse-szse'].includes(scope.target)?'anchor_date':'price_snapshot_id';
    exact(value.parameters,[key,'expected_activity_id']); const p=value.parameters;
    if (p.expected_activity_id!==null && (typeof p.expected_activity_id!=='string' || !digest.test(p.expected_activity_id))) throw new Error('量额前提无效');
    if (typeof p[key]!=='string' || (key==='price_snapshot_id' ? !digest.test(p[key]) : !/^\d{4}-\d{2}-\d{2}$/.test(p[key]) || new Date(p[key]+'T00:00:00Z').toISOString().slice(0,10)!==p[key])) throw new Error('量额固定目标无效');
  }
  return value as Identity;
}
function canonical(value: unknown): string { if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`; if (value && typeof value === "object") return `{${Object.entries(value).sort(([a],[b]) => a.localeCompare(b)).map(([k,v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`; return JSON.stringify(value); }
export function identityKey(identity: Identity): string { return canonical(identity); }
export function storageKey(scope: Scope): string {
  return `wolf-operations-v2:${encodeURIComponent(JSON.stringify(scope))}`;
}
function empty(): Book { return {pending:null,history:[],settled:[],continuity_unverified:true}; }
function validateBook(value: unknown, scope: Scope): Book {
  if (!value || typeof value!=='object' || Array.isArray(value)) throw new Error('记录无效');
  const raw=value as Book;
  const legacy=!Object.hasOwn(raw,'settled') && !Object.hasOwn(raw,'continuity_unverified');
  exact(raw,legacy?['pending','history']:['pending','history','settled','continuity_unverified']);
  if (raw.pending!==null) validIdentity(raw.pending,scope);
  if (!Array.isArray(raw.history)) throw new Error('历史记录无效');raw.history.forEach(x=>validIdentity(x,scope));
  if (legacy) return {...raw,settled:[],continuity_unverified:true};
  if (typeof raw.continuity_unverified!=='boolean' || !Array.isArray(raw.settled)) throw new Error('终态记录无效');
  raw.settled.forEach(x=>{ exact(x,['identity','state','source']);validIdentity(x.identity,scope);if(!terminals.has(String(x.state)) || !['local','carried'].includes(String(x.source)))throw new Error('终态无效'); });
  return raw;
}
export function readBook(scope: Scope): Book {
  const key=storageKey(scope);
  try { const raw=sessionStorage.getItem(key);return raw?validateBook(JSON.parse(raw),scope):empty(); }
  catch { errors.set(key,'操作记录无法读取，更新禁用；请保留记录');return preserved.get(key)??empty(); }
}
export function operationError(scope: Scope): string | undefined { return errors.get(storageKey(scope)); }
function save(scope: Scope, book: Book) {
  const key=storageKey(scope); const previous=readBook(scope);
  if(errors.has(key))throw new Error(errors.get(key));
  validateBook(book,scope);
  try {
    const text=JSON.stringify(book); sessionStorage.setItem(key,text);
    if(sessionStorage.getItem(key)!==text)throw new Error('读回不符');
  } catch { preserved.set(key,{...previous,history:[...previous.history,...(book.pending?[book.pending]:[])]});errors.set(key,'操作记录保存或读回失败，更新禁用；原身份保留');changed();throw new Error(errors.get(key)); }
  changed();
}
/** 在一次POST之前固定新身份，保留所有旧未决。 */
export function savePending(scope: Scope, identity: Identity) {
  validIdentity(identity,scope); const book=readBook(scope);
  save(scope,{...book,pending:identity,history:[...book.history,...(book.pending?[book.pending]:[])]});
}
/** 精确更新单个身份；保存失败不清未决，不误清另一目标的请求。 */
export function settle(scope: Scope, identity: Identity, state: Terminal) {
  validIdentity(identity,scope);const book=readBook(scope),key=identityKey(identity);
  const old=book.settled.find(x=>identityKey(x.identity)===key);
  if(old && old.state!==state)throw new Error('精确终态冲突');
  save(scope,{...book,pending:book.pending && identityKey(book.pending)===key?null:book.pending,
    history:book.history.filter(x=>identityKey(x)!==key),settled:[...book.settled.filter(x=>identityKey(x.identity)!==key),{identity,state,source:'local'}]});
}
export function needsExplicit(book: Book): boolean { return book.continuity_unverified || !!book.pending || book.history.length>0 || book.settled.some(x=>x.source==='carried'); }
export function allScopes(): Scope[] {
  const result: Scope[] = [];
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i) ?? '';
      if (!key.startsWith('wolf-operations-v2:')) continue;
      try { result.push(validScope(JSON.parse(decodeURIComponent(key.slice(19))))); }
      catch { /* 其他版本或损坏记录保留原文；不阻断后续有效目标。 */ }
    }
  } catch { /* 浏览器禁用存储时不清理任何既有值。 */ }
  return result;
}
/** 已退役请求只导出原记录，不请求服务、不解释为已完成。 */
export function retiredRecords(): { key: string; text: string }[] {
  const result: { key: string; text: string }[] = [];
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i) ?? '';
      if (!/^wolf-update:http:\/\/127\.0\.0\.1:\d+:[a-f0-9]{64}:(slice\.update|index\.000300\.update)$/.test(key)) continue;
      const text = sessionStorage.getItem(key);
      if (text !== null) result.push({ key, text });
    }
  } catch { /* 不改变原记录；不可访问时留待原环境恢复。 */ }
  return result;
}
/** 导出公开核对资料，不删除、不联网、不包含业务响应。 */
export function exportBook(scope: Scope): string {
  const book=readBook(scope);return JSON.stringify({version:2,page_origin:location.origin,...scope,unresolved:[...(book.pending?[book.pending]:[]),...book.history],settled:book.settled.map(({identity,state})=>({identity,state}))},null,2);
}
/** 导入只合并核对记录；带入终态不能提升未决或授予权限。 */
export function importBook(text: string, scope: Scope): void {
  if(new TextEncoder().encode(text).length>262144)throw new Error('接续文本超过256KiB');
  const value=JSON.parse(text);
  const keys=['version','page_origin','endpoint','data_scope_id','operation','unresolved','settled'];
  exact(value,[...keys,'target']);
  if(value.version!==2 || value.page_origin!==location.origin || value.endpoint!==scope.endpoint || value.data_scope_id!==scope.data_scope_id || value.operation!==scope.operation
      || value.target!==scope.target) throw new Error('接续范围或版本不符');
  if(!Array.isArray(value.unresolved) || !Array.isArray(value.settled))throw new Error('接续列表无效');
  const unresolved=value.unresolved.map(x=>validIdentity(x,scope));
  const incoming=value.settled.map(x=>{exact(x,['identity','state']);if(!terminals.has(String(x.state)))throw new Error('接续终态无效');return {identity:validIdentity(x.identity,scope),state:x.state as Terminal,source:'carried' as const};});
  const importedKeys=[...unresolved,...incoming.map(x=>x.identity)].map(identityKey);
  if(new Set(importedKeys).size!==importedKeys.length)throw new Error("接续文本含重复身份");
  const book=readBook(scope),current=[...(book.pending?[book.pending]:[]),...book.history];
  const identities=[...current,...book.settled.map(x=>x.identity),...unresolved,...incoming.map(x=>x.identity)];
  const seen=new Map<string,string>();
  for(const id of identities){const key=identityKey(id),old=seen.get(id.request_id);if(old && old!==key)throw new Error('同请求目标或参数冲突');seen.set(id.request_id,key);}
  let settled=[...book.settled];
  for(const item of incoming){const old=settled.find(x=>identityKey(x.identity)===identityKey(item.identity));if(old && old.state!==item.state)throw new Error('带入终态冲突');if(!old && !current.some(x=>identityKey(x)===identityKey(item.identity)))settled.push(item);}
  for(const id of unresolved)if(!current.some(x=>identityKey(x)===identityKey(id)) && !settled.some(x=>x.source==='local' && identityKey(x.identity)===identityKey(id)))current.push(id);
  // 旧副本未知优先于带入终态；本页精确终态保持。两种导入顺序同样去重。
  settled=settled.filter(x=>x.source==='local' || !current.some(id=>identityKey(id)===identityKey(x.identity)));
  save(scope,{pending:book.pending,history:current.filter(x=>!book.pending || identityKey(x)!==identityKey(book.pending)),settled,continuity_unverified:unresolved.length+incoming.length?false:book.continuity_unverified});
}
