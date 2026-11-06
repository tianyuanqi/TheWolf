import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { ApiClient } from './apiClient';
import { indexConnectionDescriptor, activityConnectionDescriptor } from './browserHost';
import { IndexSeriesClient } from './indexSeriesClient';
import { ActivityClient, ActivityReadError } from './activityClient';
import { OVERVIEW_INDICES, type OverviewIndexId } from './indexSeriesTypes';
import { activityGate, type ActivityId, LEGACY_MARKET, isMarket } from './activityTypes';
import { allScopes, retiredRecords, exportBook, identityKey, importBook, needsExplicit, operationError, operationsRevision, readBook, savePending, settle, subscribeOperations, type Identity, type Scope, type Terminal } from './operationSession';

const terminal = new Set(['idle','completed','failed','interrupted']);
const choices = [
  ...OVERVIEW_INDICES.map(x=>({key:'price:'+x.id,label:x.name+' · 价格',operation:'index.series.update' as const,target:x.id})),
  ...OVERVIEW_INDICES.map(x=>({key:'activity:'+x.id,label:x.name+' · 量额',operation:'market.activity.update' as const,target:x.id})),
  {key:'activity:'+LEGACY_MARKET,label:'沪深北三市合计',operation:'market.activity.update' as const,target:LEGACY_MARKET},
];
function explain(error: unknown) { return error instanceof Error?error.message:'操作结果待确认'; }
function pause(signal: AbortSignal) { return new Promise<void>(resolve=>{const done=()=>{clearTimeout(timer);signal.removeEventListener('abort',done);resolve();};const timer=setTimeout(done,1000);signal.addEventListener('abort',done,{once:true});if(signal.aborted)done();}); }

/** App常驻核对区；失联仍可复制记录，连接权限只来自受控Client。 */
export function OperationCenter({client, requested, onPublished, reconnect}: {client?:ApiClient;requested?:string;onPublished:()=>void;reconnect:()=>void}) {
  useSyncExternalStore(subscribeOperations,operationsRevision);
  const [selection,setSelection]=useState(choices[0].key);
  const [connections,setConnections]=useState<{owner:ApiClient;price?:IndexSeriesClient;activity?:ActivityClient}>();
  const [message,setMessage]=useState(''); const [busy,setBusy]=useState(false);
  const [paste,setPaste]=useState(''); const [copy,setCopy]=useState('');
  const [recoverable,setRecoverable]=useState<string>();
  const action=useRef<AbortController|undefined>(undefined);const posting=useRef(false);
  const publish=useRef(onPublished);publish.current=onPublished;
  const details=useRef<HTMLDetailsElement>(null);
  const choice=choices.find(x=>x.key===selection)!;
  const connection=connections?.owner===client?connections:undefined;
  const price=connection?.price, activity=connection?.activity;
  const scope:Scope|undefined=client?{endpoint:client.expected.endpoint,data_scope_id:client.expected.data_scope_id,operation:choice.operation,target:choice.target}:undefined;
  const selectedClient = choice.operation === "index.series.update" ? price : activity;
  const canQuery=!!client && !client.closed && (choice.operation === "index.series.update" ? !!price && !price.closed : !!activity && !activity.closed);
  const book=scope?readBook(scope):undefined;
  const storedError=scope?operationError(scope):undefined;
  const reason=!client || client.closed?'本地服务未连接':choice.operation==='index.series.update'?(!price || price.closed?'指数连接未就绪':!price.expected.write_indices.includes(choice.target as OverviewIndexId)?'所选指数未启写':undefined)
    :(!activity || activity.closed?'量额连接未就绪':activityGate(activity.expected,choice.target as ActivityId)??(!activity.expected.write_series.includes(choice.target as ActivityId)?'量额未启写':undefined));

  useEffect(()=>{
    if(requested && choices.some(x=>x.key===requested)){setSelection(requested);if(details.current){details.current.open=true;details.current.scrollIntoView({block:'nearest'});}}
  },[requested]);
  useEffect(()=>{
    const controller=new AbortController();let p:IndexSeriesClient|undefined,a:ActivityClient|undefined;
    setConnections(undefined);setRecoverable(undefined);
    if(client) void (async()=>{
      const descriptor=await indexConnectionDescriptor(client.expected,controller.signal);
      if(!descriptor)return;
      p=await IndexSeriesClient.connect(descriptor,client.instance,controller.signal);
      if(controller.signal.aborted){p.close();return;}
      setConnections({owner:client,price:p});
      const quantity=await activityConnectionDescriptor(descriptor,controller.signal);
      if(quantity)a=await ActivityClient.connect(quantity,client.instance,controller.signal);
      if(!controller.signal.aborted)setConnections({owner:client,price:p,activity:a});
    })().catch(error=>{if(!controller.signal.aborted)setMessage(explain(error));});
    return()=>{controller.abort();action.current?.abort();p?.close();a?.close();};
  },[client]);

  async function currentStatus(signal:AbortSignal) {
    if(!client || client.closed)throw new Error('连接不可用');
    if(choice.operation==='index.series.update')return price!.status(choice.target as OverviewIndexId,signal);
    if(choice.operation==='market.activity.update')return undefined;
  }
  async function query(identity:Identity, signal:AbortSignal) {
    if(!client || client.closed)throw new Error('连接不可用');
    if(identity.operation==='index.series.update')return price!.operation(identity,signal);
    if(identity.operation==='market.activity.update')return activity!.operation(identity,signal);
    throw new Error('该操作已退役，原记录仅可导出');
  }
  async function confirm(identity:Identity, signal:AbortSignal, ownRequest=false) {
    if(!scope)return;
    const until=Date.now()+120000;
    do {
      try {
        const result=await query(identity,signal);
        if(signal.aborted)return;
        if(['completed','failed','interrupted','rejected'].includes(result.state)) {
          settle(scope,identity,result.state as Terminal);
          setMessage(result.state==='completed'?'该请求已精确确认完成；其他未知记录仍保留':'该请求未成功，已保存数据保持原样');
          if(ownRequest && result.state==='completed')publish.current();
          return;
        }
        setMessage(result.state==='unknown'?'结果待确认；查无记录不代表未执行':`当前请求：${result.state}；现有数据保留`);
        if(result.state==='unknown')return;
      } catch(error) {
        if(signal.aborted)return;
        if(error instanceof ActivityReadError && error.code==='activity_recovery_required')setRecoverable(identityKey(identity));
        setMessage('结果待确认：'+explain(error));return;
      }
      await pause(signal);
    } while(!signal.aborted && Date.now()<until);
    if(!signal.aborted)setMessage('自动核对已暂停；原请求保留，可再次核对');
  }
  async function check(identity:Identity) {
    if(busy || !canQuery)return;
    action.current?.abort();const controller=new AbortController();action.current=controller;setBusy(true);
    try {await confirm(identity,controller.signal);}catch(error){if(!controller.signal.aborted)setMessage(explain(error));}
    finally{if(!controller.signal.aborted)setBusy(false);}
  }
  useEffect(()=>{
    action.current?.abort();const controller=new AbortController();action.current=controller;
    posting.current=false;setBusy(false);setRecoverable(undefined);setMessage('');
    if(client && scope) void (async()=>{
      try{
        if(book?.pending && (choice.operation==='index.series.update'?price:choice.operation==='market.activity.update'?activity:client))await confirm(book.pending,controller.signal);
        else if(choice.operation!=='market.activity.update' && (choice.operation!=='index.series.update'||price)){
          const until=Date.now()+120000;
          do {
            const status=await currentStatus(controller.signal);
            if(controller.signal.aborted)return;
            setMessage(status?`当前业务状态：${status.stage} · ${status.message??''}；不是旧请求的结论`:'');
            if(!status || terminal.has(status.stage))break;
            await pause(controller.signal);
          } while(!controller.signal.aborted && Date.now()<until);
        }
      }catch(error){if(!controller.signal.aborted)setMessage(explain(error));}
    })();
    return()=>controller.abort();
  },[client,selectedClient,selection]);

  async function start(explicit:boolean, recoveryIdentity?:Identity) {
    if(!client || !scope || reason || storedError || posting.current || busy || (!explicit && needsExplicit(readBook(scope))))return;
    posting.current=true;setBusy(true);action.current?.abort();const controller=new AbortController();action.current=controller;
    try {
      const status=await currentStatus(controller.signal);
      if(controller.signal.aborted)return;
      if(status && !terminal.has(status.stage))throw new Error('已有业务任务，不能另发检查');
      let identity:Identity;
      if(recoveryIdentity){identity=recoveryIdentity;if(identityKey(identity)!==recoverable)throw new Error('请先核对原请求');}
      else {
        identity={instance_id:client.instance,config_id:choice.operation==='index.series.update'?price!.expected.config_id:choice.operation==='market.activity.update'?activity!.expected.config_id:client.expected.config_id,request_id:crypto.randomUUID(),operation:choice.operation};
        if(choice.operation==='index.series.update')identity.index_id=choice.target;
        if(choice.operation==='market.activity.update'){
          identity.series_id=choice.target;
          const target=isMarket(choice.target) ? (price!.expected.policy.periodic ? (await price!.overviewStatus(controller.signal)).server_day : activity!.marketAnchor) : (await price!.current(choice.target as OverviewIndexId,controller.signal)).snapshot_id;
          identity.parameters=await activity!.updateParameters(choice.target as ActivityId,target,controller.signal);
        }
        if(controller.signal.aborted)return;
        savePending(scope,identity);
      }
      try{
        if(identity.operation==='index.series.update')await price!.startUpdate(identity,controller.signal);
        else if(identity.operation==='market.activity.update'){
          const result=await activity!.startUpdate(identity,controller.signal,!!recoveryIdentity);
          if(!controller.signal.aborted && ['completed','failed','interrupted'].includes(result.state)){
            settle(scope,identity,result.state as Terminal);setMessage(result.state==='completed'?'量额请求已精确确认完成':'量额未更新，原数据保留');if(result.state==='completed')publish.current();return;
          }
        }
      }catch{/* 丢失或拒绝的POST回执不触发第二POST；仅GET核对。 */}
      if(!controller.signal.aborted)await confirm(identity,controller.signal,true);
    }catch(error){if(!controller.signal.aborted)setMessage(explain(error));}
    finally{posting.current=false;if(!controller.signal.aborted)setBusy(false);}
  }
  const all=allScopes();
  return <details id="operation-center" ref={details} className="operation-center">
    <summary>更新与操作核对记录</summary>
    <p>启动补齐由服务端显式配置执行；页面重连与核对只读，不重发请求。关闭页面不等于取消更新。</p>
    <label>更新对象 <select aria-label="更新对象" value={selection} disabled={busy} onChange={e=>setSelection(e.target.value)}>{choices.map(x=><option key={x.key} value={x.key}>{x.label}</option>)}</select></label>
    <button disabled={!!reason || !!storedError || busy || !book || needsExplicit(book)} onClick={()=>void start(false)}>检查更新</button>
    {book && needsExplicit(book) && <><p className="warning">{book.continuity_unverified?'本页尚未接续此前操作。':''}先前操作可能已执行。接续记录只能帮助核对，不能保证此前没有执行；继续将创建全新请求。</p>
      <button disabled={!!reason || !!storedError || busy} onClick={()=>void start(true)}>明确发起新检查</button></>}
    {reason&&<p>{reason}；未准入或缺失量额仍为“暂无数据”，G1—G4保留。</p>}
    {storedError&&<p role="alert">{storedError}</p>}
    {message&&<p role="status">{message}</p>}<button onClick={reconnect}>重新连接服务</button>
    {scope&&book&&<>
      {[...(book.pending?[book.pending]:[]),...book.history,...book.settled.filter(x=>x.source==='carried').map(x=>x.identity)].map((identity,i)=><div key={identityKey(identity)+i}>
        <code>{identity.request_id}</code><span> · 原实例 {identity.instance_id} · 结果待核对</span>
        <button disabled={!canQuery || busy} onClick={()=>void check(identity)}>核对结果</button>
        {recoverable===identityKey(identity)&&<><p>明确恢复只使用原请求与原参数，不代表此前已失败。</p><button disabled={!!reason||busy||!!storedError} onClick={()=>void start(true,identity)}>明确恢复原请求</button></>}
      </div>)}
      {book.settled.map(x=><p key={identityKey(x.identity)}>{x.identity.request_id} · {x.state} · {x.source==='local'?'本页精确核对的终态':'旧页带入的既往终态，当前未重新验证'}</p>)}
      <label>接续旧页记录<textarea aria-label="接续旧页记录" value={paste} onChange={e=>setPaste(e.target.value)} /></label>
      <button disabled={busy||!client||client.closed} onClick={()=>{try{importBook(paste,scope);setMessage('已接续这份记录；未证明其他标签页没有请求');}catch(error){setMessage(explain(error));}}}>接续记录</button>
      <button onClick={()=>setCopy(exportBook(scope))}>复制当前核对记录</button>
    </>}
    <h3>本标签页已有记录（断连仍可导出）</h3>
    {all.map(s=><p key={JSON.stringify(s)}>{s.target} · {s.operation} <button onClick={()=>setCopy(exportBook(s))}>显示可复制记录</button></p>)}
    {retiredRecords().map(record => <p key={record.key}>旧操作已退役，结果未重新核对；原记录保留。
      <button onClick={() => setCopy(JSON.stringify({ retired: true, key: record.key, original_record: record.text }, null, 2))}>导出旧操作记录</button>
    </p>)}
    {copy&&<label>公开核对文本（选择后复制）<textarea aria-label="公开核对文本" readOnly value={copy} onFocus={e=>e.target.select()} /></label>}
  </details>;
}
