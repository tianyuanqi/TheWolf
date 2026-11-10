import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { components } from '../../../contracts/generated/http';
import { EtfFlowClient, etfReason, type EtfCurrent, type EtfView } from './etfFlowClient';
import { etfAmount, etfNumber, etfPercent, etfState, etfTime } from './etfFlowDisplay';

type Member = EtfView['members'][number];
type Evidence = components['schemas']['EtfEvidence'];

/** 原生模态框负责焦点约束；关闭或卸载恢复触发按钮，不修改URL或服务状态。 */
export function EtfDialog({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const dialog = ref.current!; dialog.showModal();
    return () => { dialog.close(); if (trigger?.isConnected) trigger.focus(); };
  }, []);
  return <dialog ref={ref} className="etf-dialog" aria-labelledby="etf-dialog-title" onCancel={event => { event.preventDefault(); close(); }}>
    <header className="etf-panel-head"><h2 id="etf-dialog-title">{title}</h2><button autoFocus onClick={close}>关闭 ×</button></header>{children}</dialog>;
}

/** 证据按固定快照取得校验结果，只展示来源元数据及原文链接，不伪称已在浏览器阅读原件。 */
export function EtfEvidenceDialog({ client, view, sourceId, close }: { client: EtfFlowClient; view: EtfView; sourceId: string; close: () => void }) {
  const [result, setResult] = useState<Evidence>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    const abort = new AbortController();
    void client.evidence(view.snapshot_id, sourceId, abort.signal).then(value => {
      if (!abort.signal.aborted) setResult(value);
    }).catch(reason => { if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : '证据读取失败'); });
    return () => abort.abort();
  }, [client, view.snapshot_id, sourceId]);
  return <EtfDialog title="证据与来源" close={close}>
    {error ? <p role="alert">{error}</p> : !result ? <p role="status">正在核对固定版本证据…</p> : <>
      <p>服务已核对保存原件的摘要及归属；大小 {result.bytes.toLocaleString()} 字节。</p>
      <p className="etf-digest">原件 SHA-256：{result.object_id}</p>
      {result.references.map((source, index) => <article className="etf-record" key={index}>
        <strong>{source.publisher} · {source.channel}</strong><p>定位：{source.locator}</p>
        <p>原始单位：{source.original_unit} · 披露精度：{source.precision}</p>
        <p>公开时间：{etfTime(source.published_at)} · 获取时间：{etfTime(source.retrieved_at)}（北京时间）</p>
        <a href={source.url} target="_blank" rel="noreferrer">打开来源原文 ↗</a>
      </article>)}
    </>}
  </EtfDialog>;
}

function ConfigurationMember({ member }: { member: EtfCurrent['members'][number] }) {
  return <article className="etf-record"><h3>{member.name} · {member.code}</h3>
    <dl className="etf-definitions"><dt>管理人</dt><dd>{member.manager}</dd><dt>交易所</dt><dd>{member.exchange}</dd>
      <dt>跟踪指数</dt><dd>{member.tracking_index}</dd><dt>所属分组</dt><dd>{member.group}</dd>
      <dt>启用日期（含）</dt><dd>{member.enabled_date}</dd><dt>停用日期（不含）</dt><dd>{member.disabled_date ?? '未停用'}</dd>
      <dt>加入依据</dt><dd><a href={member.basis.url} target="_blank" rel="noreferrer">{member.basis.locator} ↗</a>
        <br />报告期 {member.basis.report_date ?? '未提供'} · 披露日 {member.basis.published_date}</dd></dl></article>;
}

/** 所选版本与现行目录分列；没有当时记录时明确配置取自事后快照。 */
export function EtfConfiguration({ view, current, close }: { view: EtfView; current: EtfCurrent; close: () => void }) {
  return <EtfDialog title="观察池配置与版本" close={close}>
    <h3>本次结果的观察池 · {view.pool.version}</h3>
    <p>{view.mode === 'current' ? '当前版本重算' : view.data_status.original_recorded ? '当时保存版本' : '当时未记录；以下为事后快照配置，不证明当时已发布'}</p>
    <p>生效日 {view.pool.effective_date} · 确认时间 {etfTime(view.pool.confirmed_at)}（北京时间）</p>
    <p>变更：{view.pool.change}</p><p className="etf-digest">配置摘要：{view.pool.hash}</p>
    {view.members.map(member => <ConfigurationMember key={member.id} member={member} />)}
    <h3>现行完整目录 · {current.pool_version}</h3>
    <p>此目录单独展示，包括停用成员，不用于替换当时信号。增删、分组和启停只通过受控配置追加版本。</p>
    {current.members.map(member => <ConfigurationMember key={member.id} member={member} />)}
    <h3>规则版本 · {view.rule.version}</h3><p>生效日 {view.rule.effective_date} · {view.data_status.parameters_confirmed ? '参数已确认' : '参数待确认'}</p>
    <dl className="etf-definitions"><dt>比较窗口</dt><dd>{view.rule.window} 个交易日（不含当日）</dd>
      <dt>标准差倍数</dt><dd>{view.rule.k ?? '待确认'}</dd><dt>净申购下限</dt><dd>{etfAmount(view.rule.min_in)}</dd>
      <dt>净赎回下限</dt><dd>{etfAmount(view.rule.min_out)}</dd><dt>同步比例</dt><dd>{etfPercent(view.rule.direction_ratio)}</dd>
      <dt>连续日数</dt><dd>{view.rule.streak_days ?? '待确认'}</dd><dt>参数确认</dt><dd>{view.rule.confirmation ?? '未确认'}</dd></dl>
  </EtfDialog>;
}

export function EtfConditions({ view }: { view: EtfView }) {
  const evaluation = view.summary.evaluation;
  const c1 = evaluation?.c1, c2 = evaluation?.c2;
  const conditionState = (value: typeof c1) => !value ? (view.mode === 'original' ? '当时未记录' : '数据不足') : value.state === 'insufficient' ? '数据不足'
    : value.state === 'parameters_pending' ? '参数待确认' : value.incoming ? '净申购条件成立' : value.outgoing ? '净赎回条件成立' : '未触发';
  const streak = view.summary.streak;
  return <section className="etf-panel" aria-labelledby="etf-conditions" data-module="fund-flows.08">
    <header className="etf-panel-head"><h2 id="etf-conditions">当日观察</h2><span className="etf-tag">{view.data_status.parameters_confirmed ? '已确认规则' : '参数待确认'}</span></header>
    <p className="etf-signal">{etfState(view.data_status.state)}</p>
    {evaluation?.partial && <p className="m-warning">部分小计，不生成正式异常结论。</p>}
    <div className="etf-condition"><h3>C1 · 金额异常</h3><p>{conditionState(c1)}</p>
      <dl className="etf-definitions"><dt>此前 {view.rule.window} 日均值</dt><dd>{etfAmount(c1?.mean)}</dd>
        <dt>样本标准差</dt><dd>{etfAmount(c1?.standard_deviation)}</dd><dt>净申购上界</dt><dd>{etfAmount(c1?.upper)}</dd>
        <dt>净赎回下界</dt><dd>{etfAmount(c1?.lower)}</dd></dl>{c1?.reason && <small>{etfReason(c1.reason)}</small>}</div>
    <div className="etf-condition"><h3>C2 · 方向同步</h3><p>{conditionState(c2)}</p>
      <p>份额增加 {etfPercent(c2?.positive_ratio)} · 减少 {etfPercent(c2?.negative_ratio)}</p>
      <p>增加 {c2?.positive_count ?? '—'} / {c2?.denominator ?? '—'} 只 · 减少 {c2?.negative_count ?? '—'} / {c2?.denominator ?? '—'} 只</p>
      <small>有效成员 {evaluation?.valid_count ?? '—'} 只；不足 2 只为数据不足。零变化仅进入分母。</small>
      {c2?.reason && <p className="m-warning">{etfReason(c2.reason)}</p>}</div>
    <div className="etf-condition"><p>连续同向：{streak.state === 'parameters_pending' ? '参数待确认' : streak.state === 'insufficient' ? '数据不足'
      : streak.state === 'not_met' ? '未满足连续条件' : `${streak.direction === 'subscription' ? '净申购' : '净赎回'} ${streak.days} 日 · ${etfAmount(streak.amount)}`}</p></div>
    <p className="etf-note">份额变化是资金活动线索，不能确认交易主体。收盘低溢价不能排除盘中套利。</p>
  </section>;
}

/** 披露与事件沿用服务端时间筛选；后来资料逐条标识，不据披露比例推算每日资金。 */
export function EtfDisclosures({ view, member, evidence }: { view: EtfView; member?: Member; evidence: (id: string) => void }) {
  const items = view.disclosures.filter(item => item.member_id === member?.id);
  return <section className="etf-panel" data-module="fund-flows.11" aria-labelledby="etf-holders">
    <header className="etf-panel-head"><h2 id="etf-holders">持有人披露</h2><span className="etf-tag">证据参考</span></header>
    {!items.length && <p>所选成员与回看口径下暂无已核验披露。</p>}
    {items.map(item => <article className="etf-record" key={item.id}>
      <strong>报告期末 {item.report_date}</strong><p>披露日 {item.published_date ?? '未知'} · {item.locator}</p>
      {item.knowledge === 'later_comparison' && <p className="m-warning">后来披露，仅作事后对照；评估日当时不可知。</p>}
      {item.publication_unknown && <p className="m-warning">公开日未知；服务采用已知时间 {item.known_date} 限制可见范围。</p>}
      {item.state === 'not_disclosed' ? <p>未披露，不代表持仓为零。</p> : item.holders.map((holder, index) => <div className="etf-holder" key={index}>
        <strong>{holder.name}</strong><p>{etfNumber(holder.shares)} 份 · {holder.percentage === null ? '—' : etfNumber(holder.percentage) + '%'}</p>
        {holder.classification && <small>{holder.classification} · 依据：{holder.classification_basis ?? '未提供'}</small>}</div>)}
      <p>{item.note}</p><button onClick={() => evidence(item.source_id)}>查看披露证据</button>
    </article>)}<p className="etf-note">披露有滞后。不在前十名不代表持仓为零；持仓占比不能分摊每日净申赎。</p>
  </section>;
}

export function EtfEvents({ view, member, evidence }: { view: EtfView; member?: Member; evidence: (id: string) => void }) {
  const items = view.events.filter(item => item.member_ids.includes(member?.id ?? ''));
  return <section className="etf-panel" data-module="fund-flows.13" aria-labelledby="etf-events">
    <header className="etf-panel-head"><h2 id="etf-events">事件时间线</h2><small>所选 ETF</small></header>
    {!items.length && <p>暂无已核验且符合所选时间口径的事件，不代表期间没有事件。</p>}
    {items.map(item => <article className="etf-record" key={item.id}>
      <strong>{item.marker_date} · {item.marker_kind === 'announcement' ? '公告' : '发生'}</strong>
      <p>{item.description}</p><p>发生区间 {item.occurred_start ?? '未知'} 至 {item.occurred_end ?? '未知'} · 公告日 {item.published_date ?? '未知'}</p>
      <p>涉及主体：{item.subjects.join('、') || '未提供'}</p>
      <p>事件定位：{item.locator}</p>
      {item.knowledge === 'later_comparison' && <p className="m-warning">后来资料，仅作事后对照。</p>}
      {item.publication_unknown && <p className="m-warning">公开日未知；已知时间 {item.known_date}。</p>}
      <button onClick={() => evidence(item.source_id)}>查看事件证据</button>
    </article>)}
  </section>;
}
