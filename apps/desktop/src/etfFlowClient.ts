/** ETF独立可信连接与响应核对；不计算金融结果、不自动重试POST、不提供假数据。 */
import type { components } from '../../../contracts/generated/http';
import { EtfDescriptor as validDescriptor, EtfReady as validReady, EtfCurrent as validCurrent,
  EtfView as validView, EtfOperation as validOperation, EtfEvidence as validEvidence,
  EtfError as validError, BusinessError as validBoundaryError } from '../../../contracts/generated/validators.mjs';
import generation from '../../../contracts/generated/manifest.json';
import type { ConnectionDescriptor } from './apiClient';
import { validDay } from './indexSeriesTypes';

export type EtfDescriptor = components['schemas']['EtfDescriptor'];
export type EtfCurrent = components['schemas']['EtfCurrent'];
export type EtfView = components['schemas']['EtfView'];
export type EtfOperation = components['schemas']['EtfOperation'];
export type EtfEvaluation = components['schemas']['EtfEvaluation'];
export type EtfPeriod = 20 | 60 | 120 | 260;
export type EtfMode = 'original' | 'current';
export type EtfIdentity = { operation: 'etf.flow.update'; instance_id: string; config_id: string; request_id: string;
  parameters: components['schemas']['EtfUpdateBody']; index_id?: never; series_id?: never };
const hash = /^[a-f0-9]{64}$/;
const sourceHosts = new Set(['www.sse.com.cn','query.sse.com.cn','static.sse.com.cn','www.huatai-pb.com',
  'huatai-pb.com','api.fund.eastmoney.com','fund.eastmoney.com']);

function stable(value: unknown): string {
  if (Array.isArray(value)) return '['+value.map(stable).join(',')+']';
  if (value && typeof value === 'object') return '{'+Object.entries(value).sort(([a],[b])=>a<b?-1:a>b?1:0)
    .map(([k,v])=>JSON.stringify(k)+':'+stable(v)).join(',')+'}';
  return JSON.stringify(value);
}
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {Object.values(value).forEach(freeze);Object.freeze(value);}
  return value;
}
function unique(values: string[]): boolean {return new Set(values).size===values.length;}
function time(value: string): boolean {return Number.isFinite(Date.parse(value));}
function source(value: string): boolean {
  try {const url=new URL(value);return url.protocol==='https:' && sourceHosts.has(url.hostname)
    && !url.username && !url.password && !url.hash && (!url.port || url.port==='443');}catch{return false;}
}
function numericTree(value: unknown, key=''): void {
  if (typeof value==='number' && (!Number.isSafeInteger(value) || value<0)) throw new Error('ETF整数响应无效');
  if (typeof value==='string' && ['shares','delta','comparable_previous','change_rate','amount','nav','close','turnover','volume',
    'net_assets','premium','turnover_ratio','mean','standard_deviation','upper','lower','positive_ratio','negative_ratio',
    'threshold','amount_5','amount_20','cumulative','k','min_in','min_out','direction_ratio','percentage','return_1','return_5','ratio_20','factor','tail'].includes(key)
    && !Number.isFinite(Number(value))) throw new Error('ETF显示数值超出有限范围');
  if (value && typeof value==='object') for (const [name,item] of Object.entries(value)) numericTree(item,name);
}

/** 预期只能来自受控宿主，同一服务数据根及当前生成契约必须匹配。 */
export function parseEtfDescriptor(value: unknown, legacy: ConnectionDescriptor): EtfDescriptor {
  if (!validDescriptor(value) || value.endpoint!==legacy.endpoint || value.data_scope_id!==legacy.data_scope_id
      || value.contract_sha256!==generation.source_sha256 || value.contract_sha256!==legacy.contract_sha256
      || (value.write_enabled && !value.grant_id)) throw new Error('ETF连接预期不匹配');
  return freeze(structuredClone(value));
}

export const etfReason = (code?: string | null): string => ({
  etf_disabled:'未配置大资金动向服务',etf_not_initialized:'ETF数据尚未初始化',etf_update_disabled:'ETF更新未启用',
  etf_budget_exhausted:'本次取数授权额度已用尽',etf_grant_expired:'本次取数授权已到期',etf_plan_changed:'计划或已保存版本已变化，请重新读取',
  etf_unresolved_operation:'存在未核对的原请求，请先核对',etf_busy:'ETF数据正在处理',periodic_busy:'其他更新正在处理',
  etf_commit_uncertain:'本次写入结果尚未确认，请核对并显式恢复原请求',
  etf_operation_not_found:'未找到可确证的原请求记录，结果仍待确认',etf_source_http_rejected:'来源拒绝请求，本批已停止',
  etf_source_network_error:'来源请求失败，本批已停止',etf_source_deadline_exceeded:'来源请求超时，本批已停止',
  etf_update_interrupted:'更新中断，已保存数据保留',history_insufficient:'历史不足',shares_missing:'份额缺失',
  previous_day_missing:'缺少前一交易日份额',adjustment_unverified:'份额调整情况待核实',waiting_nav:'等待同日净值',
  baseline_insufficient:'基准历史不足',partial_coverage:'部分成员金额小计',fewer_than_two_valid_members:'有效ETF不足两只，数据不足',
  parameters_pending:'参数待确认',zero_variance:'历史波动不足',disabled:'已停用',not_enabled:'尚未启用',input_missing:'暂无输入',
  context_not_available:'市场背景暂无数据',configuration_changed:'已生效配置待发布',configuration_not_published:'观察池尚未发布',
  etf_group_not_found:'所选分组不在该版本中；请调整日期或回看方式，或明确清除分组筛选。',
} as Record<string,string>)[code??''] ?? (code ? '资料或状态暂不可核验（'+code+'）' : '暂无数据');

export class EtfReadError extends Error {constructor(readonly code: string){super(etfReason(code));}}

/** 校验日期、成员归属、版本和状态关系；金融计算仍完全使用服务结果。 */
export function parseEtfView(value: unknown, expected: {snapshot: string;mode: EtfMode;period: EtfPeriod;end?: string;group?: string}): EtfView {
  if (!validView(value) || value.snapshot_id!==expected.snapshot || value.mode!==expected.mode || value.period!==expected.period
      || value.group_id!==(expected.group??null) || (expected.end!==undefined && value.end!==expected.end)
      || !validDay(value.end) || !validDay(value.server_day) || !time(value.selection_at) || value.end>value.server_day
      || value.series.length!==value.period || value.series.at(-1)?.date!==value.end || value.data_status.history_first!==value.series[0]?.date
      || value.data_status.history_last!==value.end || !unique(value.members.map(m=>m.id)) || !unique(value.groups.map(g=>g.id))) {
    throw new Error('ETF固定视图身份、日期或窗口不符');
  }
  numericTree(value);
  const completeThrough = value.data_status.complete_amount_through;
  if (completeThrough !== null && (!validDay(completeThrough) || completeThrough > value.end
      || (value.mode === 'original' && !value.data_status.original_recorded))) throw new Error('ETF完整金额截止日无效');
  if (completeThrough !== null && completeThrough >= value.data_status.history_first) {
    const row = value.series.find(point => point.date === completeThrough)?.evaluation;
    if (!row || row.amount === null || row.partial) throw new Error('ETF完整金额截止日与日记录不符');
  }
  const known = new Set(value.groups.flatMap(g=>g.member_ids));
  if (value.groups.some(g=>!unique(g.member_ids)) || value.members.some(m=>!known.has(m.id)
      || !value.groups.some(g=>g.id===m.group_id && g.name===m.group && g.member_ids.includes(m.id)))) throw new Error('ETF配置分组不符');
  const evaluation=(row: EtfEvaluation): void => {
    if (!validDay(row.date) || row.date>value.end || row.mode!==value.mode || row.group_id!==value.group_id
        || !time(row.calculated_at) || !time(row.selection_at) || row.calculated_at!==row.selection_at
        || !unique(row.valid_ids) || row.valid_ids.some(id=>!known.has(id)) || row.valid_count!==row.valid_ids.length
        || row.ready_count<row.valid_count || row.active_count<row.ready_count
        || !unique(row.exclusions.map(x=>x.member_id)) || row.exclusions.some(x=>!known.has(x.member_id))
        || (row.valid_count===0 && row.amount!==null) || (row.partial && row.state!=='insufficient')) throw new Error('ETF评估成员或状态不符');
    if (value.mode==='current' && (row.pool_version!==value.pool_version || row.rule_version!==value.rule_version
        || row.input_version!==value.input_version || row.selection_at!==value.selection_at)) throw new Error('ETF重算版本不符');
    if (row.valid_count<2 && (row.c2.state!=='insufficient' || row.c2.positive_ratio!==null || row.c2.negative_ratio!==null
        || row.c2.incoming!==null || row.c2.outgoing!==null)) throw new Error('单只C2不能作为正常或零比例');
    for (const condition of [row.c1,row.c2]) if (condition.state!=='evaluated' && (condition.incoming!==null || condition.outgoing!==null)) throw new Error('未确认条件不得给出正式判断');
    if (row.c2.denominator!==null && (row.c2.denominator!==row.valid_count || row.c2.positive_count===null
        || row.c2.negative_count===null || row.c2.positive_count+row.c2.negative_count>row.c2.denominator)) throw new Error('ETF方向分子分母不符');
  };
  value.series.forEach((point,i)=>{
    if (!validDay(point.date) || point.date>value.end || (i>0 && point.date<=value.series[i-1].date)) throw new Error('ETF交易日序列无效');
    if (point.evaluation) {evaluation(point.evaluation);if(point.evaluation.date!==point.date || point.state!==point.evaluation.state)throw new Error('ETF日记录归属无效');}
    else if (point.cumulative!==null || (value.mode==='original' && point.state!=='unrecorded')) throw new Error('未记录日不得补造累计');
  });
  value.history.forEach(evaluation);
  if (value.summary.evaluation) {
    evaluation(value.summary.evaluation);
    if (value.summary.evaluation.date!==value.end || stable(value.summary.evaluation)!==stable(value.series.at(-1)?.evaluation)
        || stable(value.selected_member_ids)!==stable(value.summary.evaluation.valid_ids)) throw new Error('ETF摘要与末日不符');
  } else if(value.selected_member_ids.length) throw new Error('未记录摘要不能有有效成员');
  for (const member of value.members) {
    if (!validDay(member.enabled_date) || (member.disabled_date!==null && (!validDay(member.disabled_date) || member.disabled_date<=member.enabled_date))
        || !source(member.basis.url) || !validDay(member.basis.published_date) || (member.basis.report_date!==null && !validDay(member.basis.report_date))
        || member.metrics.date!==value.end || member.series.length!==value.period || member.input_version!==value.input_version
        || member.input_selected_at!==value.selection_at || member.input_basis!==value.data_status.input_basis) throw new Error('ETF成员资料归属不符');
    member.series.forEach((point,i)=>{
      if(point.metrics.date!==value.series[i].date || !unique(point.source_ids))throw new Error('ETF单只序列错日');
      const detail = point.adjustment_detail;
      if (detail === null) {
        if (point.metrics.adjustment) throw new Error('ETF折算依据缺失');
        return;
      }
      if (!validDay(detail.start) || !validDay(detail.end) || detail.start > point.metrics.date || detail.end < point.metrics.date
          || !time(detail.confirmed_at) || Date.parse(detail.confirmed_at) > Date.parse(value.selection_at)
          || Number(detail.factor) <= 0 || !detail.source_ids.length || !unique(detail.source_ids)
          || detail.source_ids.some(id => !value.sources.some(source => source.object_id === id))
          || point.metrics.adjustment !== (detail.kind === 'adjustment')
          || (detail.kind === 'normal' && (Number(detail.factor) !== 1 || Number(detail.tail) !== 0))
          || (detail.kind === 'adjustment' && detail.start !== detail.end)) throw new Error('ETF调整依据归属或状态不符');
    });
    if (member.admission && (member.admission.member_id!==member.id || member.admission.required_days<value.data_status.required_days
        || Date.parse(member.admission.first_qualified_at)>Date.parse(member.admission.checked_at)
        || Date.parse(member.admission.checked_at)>Date.parse(value.selection_at))) throw new Error('ETF历史准入证据无效');
  }
  for (const item of [...value.sources,...value.disclosures,...value.events]) if (!source(item.url) || !time(item.retrieved_at)
      || Date.parse(item.retrieved_at)>Date.parse(value.selection_at)) throw new Error('ETF来源或取得时刻无效');
  if (value.disclosures.some(d=>!known.has(d.member_id) || !validDay(d.report_date) || !validDay(d.known_date)
      || (d.published_date!==null && (!validDay(d.published_date) || d.report_date>d.published_date))
      || (d.state==='not_disclosed' && d.holders.length>0)) || value.events.some(e=>e.member_ids.some(id=>!known.has(id)))) throw new Error('ETF披露归属无效');
  if (value.mode==='original' && [...value.disclosures,...value.events].some(e=>e.known_date>value.end || e.knowledge==='later_comparison')) throw new Error('原版本不得混入后来披露');
  if (!unique(value.context.indices.map(row=>row.index_id)) || value.context.indices.some(row=>!value.members.some(m=>m.index_id===row.index_id))
      || [...value.context.indices,...(value.context.market?[value.context.market]:[])].some(row=>row.date!==value.end
        || !time(row.calculated_at) || Date.parse(row.calculated_at)>Date.parse(value.selection_at))) throw new Error('ETF背景日期或输入归属不符');
  return freeze(value);
}

export class EtfFlowClient {
  private readonly lifetime=new AbortController();
  private readonly recovery=new Set<string>();
  private readonly views=new Map<string,EtfView>();
  private viewGeneration=0;
  clearViews():void{this.viewGeneration++;this.views.clear();}
  get closed():boolean{return this.lifetime.signal.aborted;}
  close():void{this.lifetime.abort();this.recovery.clear();this.clearViews();}
  private constructor(readonly expected:EtfDescriptor,readonly instance:string){}

  static async connect(expected:EtfDescriptor, ownerInstance:string, signal:AbortSignal):Promise<EtfFlowClient>{
    const response=await fetch(expected.endpoint+'/api/etf-flow/session',{credentials:'omit',redirect:'error',cache:'no-store',
      headers:{'X-Wolf-Client':'1'},signal:AbortSignal.any([signal,AbortSignal.timeout(8000)])});
    if(!response.ok || !response.headers.get('content-type')?.startsWith('application/json'))throw new Error('ETF服务不可用');
    const value:unknown=await response.json();
    if(signal.aborted)throw new DOMException('连接已取消','AbortError');
    if(!validReady(value))throw new Error('ETF就绪契约不符');
    const {endpoint:_endpoint,...identity}=expected;const {status:_status,instance_id,...actual}=value;
    if(stable(identity)!==stable(actual) || instance_id!==ownerInstance || response.headers.get('X-Wolf-Instance')!==instance_id
        || response.headers.get('X-Wolf-Config')!==expected.config_id)throw new Error('ETF服务身份不匹配');
    return new EtfFlowClient(expected,instance_id);
  }

  private async request(path:string,signal:AbortSignal,identity?:EtfIdentity):Promise<unknown>{
    const response=await fetch(this.expected.endpoint+path,{method:identity?'POST':'GET',body:identity?JSON.stringify(identity.parameters):undefined,
      credentials:'omit',redirect:'error',cache:'no-store',signal:AbortSignal.any([signal,this.lifetime.signal,AbortSignal.timeout(30000)]),
      headers:{'X-Wolf-Client':'1','X-Wolf-Expected-Instance':this.instance,'X-Wolf-Expected-Config':this.expected.config_id,
        ...(identity?{'Content-Type':'application/json','X-Wolf-Request-Id':identity.request_id}:{})}});
    if(response.headers.get('X-Wolf-Instance')!==this.instance || response.headers.get('X-Wolf-Config')!==this.expected.config_id){
      this.close();throw new Error('ETF连接身份改变，请重新连接；原操作记录保留');}
    if(!response.headers.get('content-type')?.startsWith('application/json'))throw new Error('ETF响应媒体无效');
    const value:unknown=await response.json();
    if(signal.aborted || this.closed)throw new DOMException('读取已取消','AbortError');
    if(!response.ok){if(!validError(value) && !validBoundaryError(value))throw new Error('ETF错误响应契约不符');throw new EtfReadError(value.detail.code);}
    if(identity ? ![200,202].includes(response.status) : response.status!==200)throw new Error('ETF响应状态不符');
    return value;
  }

  async current(signal:AbortSignal):Promise<EtfCurrent>{
    const value=await this.request('/api/etf-flow/current',signal);
    if(!validCurrent(value) || !validDay(value.server_day) || !unique(value.members.map(m=>m.id)) || !unique(value.plan.member_ids)
        || !value.plan.member_ids.every(id=>value.members.some(m=>m.id===id)) || !validDay(value.plan.start) || !validDay(value.plan.end)
        || value.plan.start>value.plan.end || value.plan.end>value.server_day || value.write_enabled!==this.expected.write_enabled
        || (value.snapshot_id===null ? value.selection_at!==null || value.end!==null || !value.configuration_pending
          : value.selection_at===null || !time(value.selection_at) || value.end===null || !validDay(value.end)))throw new Error('ETF当前状态不符');
    numericTree(value);return freeze(value);
  }

  async view(snapshot:string,mode:EtfMode,period:EtfPeriod,signal:AbortSignal,end?:string,group?:string):Promise<EtfView>{
    if(!hash.test(snapshot) || ![20,60,120,260].includes(period) || !['original','current'].includes(mode)
        || (end!==undefined && !validDay(end)) || (group!==undefined && !hash.test(group)))throw new Error('ETF查询参数无效');
    const query=new URLSearchParams({mode,period:String(period),...(end?{end}:{}),...(group?{group}:{})});
    if(signal.aborted || this.closed)throw new DOMException('读取已取消','AbortError');
    const key=snapshot+'?'+query, cached=this.views.get(key), generation=this.viewGeneration;
    if(cached){this.views.delete(key);this.views.set(key,cached);return cached;}
    const value=parseEtfView(await this.request('/api/etf-flow/snapshots/'+snapshot+'?'+query,signal),{snapshot,mode,period,end,group});
    if(generation===this.viewGeneration){this.views.set(key,value);if(this.views.size>32)this.views.delete(this.views.keys().next().value!);}
    return value;
  }

  async evidence(snapshot:string,sourceId:string,signal:AbortSignal){
    if(!hash.test(snapshot) || !hash.test(sourceId))throw new Error('ETF证据引用无效');
    const value=await this.request('/api/etf-flow/snapshots/'+snapshot+'/evidence/'+sourceId,signal);
    if(!validEvidence(value) || value.snapshot_id!==snapshot || value.object_id!==sourceId
        || value.references.some(s=>s.object_id!==sourceId || !source(s.url)))throw new Error('ETF证据归属无效');
    return freeze(value);
  }

  private async operationResult(value:unknown,identity:EtfIdentity):Promise<EtfOperation>{
    if(!validOperation(value) || value.request_id!==identity.request_id || value.config_id!==identity.config_id || value.instance_id!==identity.instance_id
        || value.plan_id!==identity.parameters.plan_id || value.expected_snapshot_id!==identity.parameters.expected_snapshot_id
        || value.serving_instance_id!==this.instance || value.serving_config_id!==this.expected.config_id
        || (value.recovered_from_instance!==null && value.recovered_from_instance!==identity.instance_id)
        || (value.state==='completed' ? value.snapshot_id===null || value.reason!==null : value.snapshot_id!==null)
        || (value.state==='queued' || value.state==='running') && value.lease_closed)throw new Error('ETF原请求身份或结果不符');
    const canonical=stable({scope:this.expected.etf_scope_id,config_id:identity.config_id,request_id:identity.request_id,
      plan_id:identity.parameters.plan_id,expected_snapshot_id:identity.parameters.expected_snapshot_id});
    const key=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical)))].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(key!==value.operation_key)throw new Error('ETF原请求摘要不符');
    if(value.recovery_required)this.recovery.add(stable(identity));else this.recovery.delete(stable(identity));
    return freeze(value);
  }

  async operation(identity:EtfIdentity,signal:AbortSignal):Promise<EtfOperation>{
    if(identity.operation!=='etf.flow.update' || (this.expected.write_enabled && identity.config_id!==this.expected.config_id))throw new Error('ETF原配置不匹配');
    return this.operationResult(await this.request('/api/etf-flow/operations/'+encodeURIComponent(identity.request_id),signal),identity);
  }

  async startUpdate(identity:EtfIdentity,signal:AbortSignal,recovering=false):Promise<EtfOperation>{
    if(!this.expected.write_enabled || identity.config_id!==this.expected.config_id || identity.operation!=='etf.flow.update'
        || (recovering?!this.recovery.has(stable(identity)):identity.instance_id!==this.instance))throw new Error('ETF更新或恢复未获许可');
    this.recovery.delete(stable(identity));
    return this.operationResult(await this.request('/api/etf-flow/update',signal,identity),identity);
  }
}
