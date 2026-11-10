import { useEffect, useMemo, useRef, useState } from 'react';
import type { ApiClient } from './apiClient';
import { etfConnectionDescriptor, indexConnectionDescriptor } from './browserHost';
import { IndexSeriesClient } from './indexSeriesClient';
import { StoredViews, type Version } from './storedViews';
import { EtfFlowClient, etfReason, type EtfCurrent, type EtfView, type EtfPeriod, type EtfMode } from './etfFlowClient';
import { EtfFlowChart, type EtfChartMarker } from './EtfFlowChart';
import { EtfConditions, EtfConfiguration, EtfDisclosures, EtfEvents, EtfEvidenceDialog } from './EtfFlowDetails';
import { etfAmount, etfNumber, etfPercent, etfState, etfTime, etfTone } from './etfFlowDisplay';
import type { Theme } from './OverviewCharts';
import './overview.css';
import './etfFlow.css';

type RecordSelection = { snapshot: string; result: string; instance: string; config: string };
type Query = { mode: EtfMode; period: EtfPeriod; end: string; group: string; record?: RecordSelection };
type Loaded = { key: string; view?: EtfView; error?: string };
const failure = (error: unknown) => error instanceof TypeError ? '本地服务连接不可用，请重新连接。' : error instanceof Error ? error.message : 'ETF读取失败';

/** 连接只来自受控宿主；查询按固定快照与完整选择归属，取消及迟到结果不得覆盖新选择。 */
export function useEtfData(legacy: ApiClient | undefined, refresh: number, query: Query) {
  const [connection, setConnection] = useState<{ owner: ApiClient; client?: EtfFlowClient; versions?: StoredViews; error?: string }>();
  const [state, setState] = useState<{ client: EtfFlowClient; current?: EtfCurrent; published?: Version | null; error?: string }>();
  const [loaded, setLoaded] = useState<Loaded>();
  const [retry, setRetry] = useState(0);
  const [viewRetry, setViewRetry] = useState(0);
  const viewFailed = useRef(false);
  useEffect(() => {
    if (!legacy) return;
    const abort = new AbortController(); let owned: EtfFlowClient | undefined, versionClient: IndexSeriesClient | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setConnection({ owner: legacy });
    void (async () => {
      const descriptor = await etfConnectionDescriptor(legacy.expected, abort.signal);
      if (!descriptor) throw new Error('未配置大资金动向服务');
      const next = await EtfFlowClient.connect(descriptor, legacy.instance, abort.signal);
      if (abort.signal.aborted) { next.close(); return; }
      owned = next;
      const expected = await indexConnectionDescriptor(legacy.expected, abort.signal);
      if (!expected) throw new Error('未配置本地版本连接');
      versionClient = await IndexSeriesClient.connect(expected, legacy.instance, abort.signal);
      if (abort.signal.aborted) { versionClient.close(); return; }
      setConnection({ owner: legacy, client: next, versions: new StoredViews(versionClient) });
    })().catch(error => {
      if (abort.signal.aborted) return;
      owned?.close(); versionClient?.close(); setConnection({ owner: legacy, error: failure(error) });
      timer = setTimeout(() => { if (!abort.signal.aborted) setRetry(value => value + 1); }, 30000);
    });
    return () => { abort.abort(); if (timer) clearTimeout(timer); owned?.close(); versionClient?.close(); };
  }, [legacy, retry]);
  const active = connection?.owner === legacy ? connection : undefined;
  const client = active?.client;
  const versions = active?.versions;
  useEffect(() => {
    if (!client || !versions) return;
    const abort = new AbortController(); setState({ client });
    let timer: ReturnType<typeof setTimeout> | undefined, last: string | undefined;
    const inspect = async () => {
      try {
        const version = await versions.versions(abort.signal);
        const identity = JSON.stringify([version.store_id, version.etf]);
        if (identity !== last) {
          // 计划/额度是显式状态读取；正常轮询只取得SQL版本，不重复装配计划。
          const current = await client.current(abort.signal);
          // current是计划/现行目录；期间有新发布，也只按先前固定的发布ID读取图表。
          if (!abort.signal.aborted) { client.clearViews(); last = identity; setState({ client, current, published: version.etf }); }
        }
        if (!abort.signal.aborted && viewFailed.current) { client.clearViews(); viewFailed.current = false; setViewRetry(value => value + 1); }
      } catch (error) {
        last = undefined; client.clearViews();
        if (!abort.signal.aborted) setState({ client, error: failure(error) });
      }
      if (!abort.signal.aborted) timer = setTimeout(inspect, 30000);
    };
    void inspect();
    return () => { abort.abort(); if (timer) clearTimeout(timer); };
  }, [client, versions, refresh]);
  const currentState = state?.client === client ? state : undefined;
  const current = currentState?.current;
  const record = query.record?.instance === client?.instance && query.record?.config === client?.expected.config_id ? query.record : undefined;
  const snapshot = record?.snapshot ?? currentState?.published?.publication_id;
  const key = JSON.stringify([client?.instance, client?.expected.config_id, snapshot, query, viewRetry]);
  useEffect(() => {
    if (!client || !snapshot) return;
    const abort = new AbortController(); setLoaded({ key }); viewFailed.current = false;
    void client.view(snapshot, query.mode, query.period, abort.signal, query.end || undefined, query.group || undefined)
      .then(view => {
        if (record && view.summary.evaluation?.result_id !== record.result) throw new Error('观察记录与所选固定版本不符，请重新读取。');
        if (!abort.signal.aborted) setLoaded({ key, view });
      })
      .catch(error => { if (!abort.signal.aborted) { viewFailed.current = true; setLoaded({ key, error: failure(error) }); } });
    return () => abort.abort();
  }, [client, snapshot, key, query.mode, query.period, query.end, query.group, record]);
  const result = snapshot && loaded?.key === key ? loaded : undefined;
  return { client, current, snapshot, lastDate: currentState?.published?.source_coverage.end,
    view: current ? result?.view : undefined, error: active?.error ?? currentState?.error ?? result?.error };
}

/** 已认可的ETF页面：真实服务结果驱动全部分组、成员、时间版本和证据，不提供样例后备。 */
export function EtfFlowPage({ legacyClient, connectionError, reconnect, navigate, refreshToken, onUpdate }: {
  legacyClient?: ApiClient; connectionError?: string; reconnect: () => void; navigate: (page: string) => void;
  refreshToken: number; onUpdate: (target: string) => void;
}) {
  const [theme, setTheme] = useState<Theme>('light');
  const [notes, setNotes] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const navToggle = useRef<HTMLButtonElement>(null);
  const [reload, setReload] = useState(0);
  const [query, setQuery] = useState<Query>({ mode: 'original', period: 60, end: '', group: '' });
  useEffect(() => setQuery(previous => ({ ...previous, record: undefined })), [legacyClient]);
  const [memberId, setMemberId] = useState('');
  const [singleMode, setSingleMode] = useState<'delta' | 'turnover'>('delta');
  const [dialog, setDialog] = useState<{ type: 'configuration' } | { type: 'evidence'; id: string }>();
  const { client, current, snapshot, lastDate, view, error } = useEtfData(legacyClient, refreshToken + reload, query);
  const visibleError = connectionError ?? error;
  const selected = view?.members.find(member => member.id === memberId) ?? view?.members[0];
  const modeLabel = query.mode === 'original' ? '当时版本' : '当前版本重算';
  // 选择变更时关闭旧快照弹窗，避免旧证据挂到新日期或新服务。
  useEffect(() => setDialog(undefined), [view, client]);
  const rows = useMemo(() => {
    if (!view || !current) return [];
    const groupName = view.groups.find(group => group.id === view.group_id)?.name;
    const all = new Map(current.members.map(member => [member.id, member]));
    view.members.forEach(member => all.set(member.id, member));
    return [...all.values()].filter(member => !groupName || member.group === groupName)
      .map(member => ({ config: member, data: view.members.find(row => row.id === member.id) }));
  }, [view, current]);
  const aggregatePoints = useMemo(() => view?.series.map(point => ({ date: point.date,
    bar: point.evaluation?.amount ?? null, line: point.cumulative,
    readout: <><span>{point.evaluation?.partial ? '部分小计' : '当日'} {etfAmount(point.evaluation?.amount)}</span>
      <span>累计 {etfAmount(point.cumulative)}</span><span>{etfState(point.state)}</span>
      {point.evaluation && <><span>有效 {point.evaluation.valid_count}/{point.evaluation.active_count}</span>
        <span>成员：{point.evaluation.valid_ids.map(id => view.members.find(m => m.id === id)?.name ?? id).join('、') || '无'}</span>
        <span>池 {point.evaluation.pool_version} · 规则 {point.evaluation.rule_version}</span></>}</> })) ?? [], [view]);
  const singlePoints = useMemo(() => selected?.series.map(point => ({ date: point.metrics.date,
    bar: point.metrics[singleMode], line: point.metrics.shares,
    readout: <><span>总份额 {etfNumber(point.metrics.shares, 1e8)} 亿份</span>
      <span>{singleMode === 'delta' ? `份额增减 ${etfNumber(point.metrics.delta, 1e8)} 亿份` : `成交额 ${etfAmount(point.metrics.turnover)}`}</span>
      <span>净申赎 {etfAmount(point.metrics.amount)}</span>{point.metrics.adjustment && <span>已按核验折算调整</span>}
      {point.adjustment_detail ? <span className="etf-adjustment">
        {point.adjustment_detail.kind === 'adjustment' ? '折算依据' : '已核验普通份额'}：倍率 {point.adjustment_detail.factor} · 尾差 {point.adjustment_detail.tail} 份
        <small>确认依据：{point.adjustment_detail.confirmation} · {etfTime(point.adjustment_detail.confirmed_at)}（北京时间）</small>
        {point.adjustment_detail.source_ids.map(id => <button key={id} onClick={() => setDialog({ type: 'evidence', id })}>查看调整证据 {id.slice(0, 8)}</button>)}
      </span> : <span>调整依据待核实</span>}
      {point.metrics.reason && <span>{etfReason(point.metrics.reason)}</span>}
      {point.source_ids.map(id => <button key={id} onClick={() => setDialog({ type: 'evidence', id })}>来源 {id.slice(0, 8)}</button>)}</> })) ?? [], [selected, singleMode]);
  const evaluation = view?.summary.evaluation;
  // 只使用当前固定投影的标注日期及所选成员，不从当前配置或其他快照补事件。
  const singleMarkers = useMemo<EtfChartMarker[]>(() => {
    if (!view || !selected) return [];
    const adjustments = selected.series.flatMap(point => {
      const detail = point.adjustment_detail;
      if (!detail || detail.kind !== 'adjustment' || detail.start !== point.metrics.date) return [];
      return [{ id: `adjustment:${point.metrics.date}`, date: detail.start, label: '折算', detail: <>
        <p>核验倍率 {detail.factor} · 尾差 {detail.tail} 份</p>
        <p>{detail.confirmation} · 确认 {etfTime(detail.confirmed_at)}（北京时间）</p>
        {detail.source_ids.map(id => <button key={id} onClick={() => setDialog({ type: 'evidence', id })}>查看折算标记证据 {id.slice(0, 8)}</button>)}
      </> }];
    });
    const events = view.events.filter(event => event.member_ids.includes(selected.id)).map(event => ({
      id: `event:${event.id}`, date: event.marker_date,
      description: `${event.description} · ${event.locator}`,
      label: (event.marker_kind === 'occurrence' ? '事件' : event.publication_unknown ? '已知时间（公开日未知）' : '公告')
        + (event.knowledge === 'later_comparison' ? ' · 事后对照' : ''),
      detail: <><p>{event.description}</p>
        <p>发生区间 {event.occurred_start ?? '未知'} 至 {event.occurred_end ?? '未知'} · 公告日 {event.published_date ?? '未知'}</p>
        {event.knowledge === 'later_comparison' && <p className="m-warning">后来资料，仅作事后对照；评估日当时不可知。</p>}
        {event.publication_unknown && <p>公开日未知；服务提供的已知时间 {event.known_date}，不冒充公告日。</p>}
        <p>事件定位：{event.locator}</p>
        <button onClick={() => setDialog({ type: 'evidence', id: event.source_id })}>查看标记事件证据</button>
      </>,
    }));
    return [...adjustments, ...events];
  }, [view, selected]);
  const changeQuery = (next: Partial<Query>) => setQuery(previous => ({ ...previous, record: undefined, ...next }));
  return <div className={`overview-app etf-app ${navOpen ? 'm-nav-open' : ''}`} data-theme={theme}
    data-view-identity={view ? JSON.stringify([view.snapshot_id, view.mode, view.period, view.end, view.group_id,
      view.input_version, view.summary.evaluation?.result_id ?? null]) : undefined}
    onKeyDown={event => { if (event.key === 'Escape' && navOpen) { setNavOpen(false); navToggle.current?.focus(); } }}>
    <a href="#etf-main" className="m-skip" onClick={event => { event.preventDefault(); document.getElementById('etf-main')?.focus(); }}>跳到页面内容</a>
    <aside className="m-sidebar" id="etf-navigation" aria-label="全站导航">
      <div className="m-brand"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 5l8 5 5-4 5 4 8-5-4 17-9 6-9-6zM8 13l8 10 8-10M16 23v5" /></svg><span>THE WOLF<small>个人研究工作台</small></span></div>
      <p className="m-nav-group">市场研究</p><nav aria-label="市场研究">
        <button onClick={() => navigate('overview')}><span aria-hidden="true">↗</span>行情总览</button>
        <button aria-current="page" onClick={() => setNavOpen(false)}><span aria-hidden="true">◇</span>大资金动向</button>
        <button disabled title="尚未接入正式页面"><span aria-hidden="true">◇</span>标的查询</button>
        {['量价分析', '题材概念', '大事新闻'].map(name => <button disabled key={name}><span>◇</span>{name}</button>)}
      </nav><div className="m-nav-bottom"><span>●</span> 本地研究工作台</div>
    </aside>
    {navOpen && <button className="m-backdrop" aria-label="关闭导航" onClick={() => setNavOpen(false)} />}
    <main id="etf-main" className="m-main" tabIndex={-1}>
      <div className="m-topbar"><div className="m-breadcrumb"><button ref={navToggle} className="m-mobile-toggle" aria-expanded={navOpen} aria-controls="etf-navigation" aria-label="展开或收起导航" onClick={() => setNavOpen(value => !value)}>☰</button>市场研究<span>/</span><strong>大资金动向</strong></div>
        <div className="m-top-actions"><label><input type="checkbox" checked={notes} onChange={event => setNotes(event.target.checked)} />数据说明</label>
          <button aria-pressed={theme === 'dark'} aria-label="深色备选主题" onClick={() => setTheme(value => value === 'light' ? 'dark' : 'light')}>{theme === 'light' ? '深色模式' : '浅色模式'}</button></div></div>
      <header className="m-heading"><div><p className="etf-eyebrow">ETF 份额监测</p><h1>大资金动向</h1>
        <p className="m-muted">{current ? `${current.members.length} 只配置成员 · ${[...new Set(current.members.map(m => m.group))].join(' / ')}` : '观察池配置由本地服务提供'}</p></div>
        <button disabled={!client} onClick={() => onUpdate('etf.flow.update')}>更新数据</button></header>
      <div className="m-connection"><p role={visibleError ? 'alert' : 'status'}>{visibleError ?? (!current ? '正在连接并读取观察池…' : !snapshot ? '尚无已发布数据，请完成获准的历史初始化与更新。' : !view ? '正在读取固定版本…' : `已读取 ${view.end} · ${modeLabel}`)}</p>
        <div><button disabled={!client} onClick={() => { changeQuery({}); setReload(value => value + 1); }}>重新读取</button><button onClick={reconnect}>重新连接</button></div></div>
      {query.record && view && <p className="etf-note">正在查看所点记录的固定版本；重新读取可回到当前快照。</p>}
      {query.group && visibleError && <button onClick={() => changeQuery({ group: '' })}>清除分组筛选</button>}
      {current?.configuration_pending && <p className="m-warning">当前配置尚未发布到结果；{etfReason(current.configuration_reason)}。已有结果保留原配置。</p>}
      {current?.blocked_reason && <p className="m-warning">更新状态：{etfReason(current.blocked_reason)}；已有保存版本仍可回看。</p>}
      <section className="etf-scope" aria-label="观察范围" data-module="fund-flows.01">
        <div className="etf-toolbar">
          <label>观察分组<select aria-label="观察分组" value={query.group} disabled={!view} onChange={event => changeQuery({ group: event.target.value })}>
            <option value="">全部观察池</option>{view?.groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
          <label>观察日期<input aria-label="观察日期" type="date" value={query.end || lastDate || ''} max={lastDate}
            disabled={!snapshot} onChange={event => changeQuery({ end: event.target.value })} /></label>
          <div><span className="etf-field-label">回看方式</span><div className="m-segmented" role="group" aria-label="回看方式">
            <button aria-pressed={query.mode === 'original'} onClick={() => changeQuery({ mode: 'original' })}>当时版本</button>
            <button aria-pressed={query.mode === 'current'} onClick={() => changeQuery({ mode: 'current' })}>当前版本重算</button></div></div>
          {view && <div className="etf-version"><span className="etf-tag">{view.pool_version}</span><small>{modeLabel}</small></div>}
        </div><p className="etf-note">ⓘ 份额变化估算 ETF 净申赎，是资金活动线索，不能直接识别国家队买卖。</p>
        {query.mode === 'current' && <p className="m-warning">事后重算：固定当前有效成员和已选输入版本，不能作为评估日当时已经发布的信号。</p>}
        {view?.data_status.input_basis === 'posthoc_inputs' && <p className="m-warning">{view.mode === 'original' ? '当时没有保存的信号。单只数据取自事后输入，仅供回看；可切换“当前版本重算”。' : '输入包含事后取得或修订的资料；不代表当时可知。'}</p>}
      </section>
      {view && current && <>
        <section className="etf-metrics" aria-label="净申赎摘要" data-module="fund-flows.06">
          {[[evaluation?.partial ? '当日部分小计' : '当日净申赎估算', evaluation?.amount, '份额变化 × 同日单位净值'],
            ['近 5 日累计', view.summary.amount_5, '逐日估算额相加'], ['近 20 日累计', view.summary.amount_20, '缺失不按零计']].map(([label, amount, note]) => <div key={label}>
              <span>{label}</span><p className={etfTone(amount)}>{etfAmount(amount)}</p><small>{note}</small></div>)}
          <div><span>有效 / 启用 ETF</span><p>{evaluation ? `${evaluation.valid_count} / ${evaluation.active_count}` : '— / —'}</p><small>{evaluation ? `已准入 ${evaluation.ready_count} 只` : view.mode === 'original' ? '当时未记录，不补造覆盖数' : '当前口径无可用记录，不补造覆盖数'}</small></div>
        </section>
        <div className="etf-main-grid"><section className="etf-panel" data-module="fund-flows.07" aria-labelledby="etf-trend">
          <header className="etf-panel-head"><div><h2 id="etf-trend">净申赎趋势</h2><small>{view.series[0]?.date} 至 {view.end} · {modeLabel}</small></div>
            <div className="m-segmented" role="group" aria-label="图表范围">{([20, 60, 120, 260] as const).map(period => <button key={period} aria-pressed={query.period === period} onClick={() => changeQuery({ period })}>{period}日</button>)}</div></header>
          <p className="etf-legend"><span className="m-up">■ 净申购</span><span className="m-down">■ 净赎回</span><span>— 区间累计（右轴）</span></p>
          <EtfFlowChart points={aggregatePoints} theme={theme} label="每日净申赎及区间累计" barLabel="亿元" lineLabel="累计亿元" />
          <p className="etf-note">按逐日版本计算；缺失或部分小计会使完整累计断开，不补零。左右键查看每日成员与版本。</p>
        </section><EtfConditions view={view} /></div>
        <section className="etf-panel etf-member-panel" data-module="fund-flows.09" aria-labelledby="etf-members">
          <header className="etf-panel-head"><div><h2 id="etf-members">观察池成员</h2><small>按配置生成；停用保留历史，未准入不进合计</small></div><button onClick={() => setDialog({ type: 'configuration' })}>查看配置与版本 ↗</button></header>
          <div className="etf-table-scroll" role="region" tabIndex={0} aria-label="观察池成员表，窄窗口可横向滚动"><table className="etf-table"><thead><tr>
            <th>ETF / 跟踪指数</th><th>分组</th><th>份额日变化</th><th>净申赎估算</th><th>收盘折溢价</th><th>数据状态</th></tr></thead>
            <tbody>{rows.map(({ config, data }) => <tr key={config.id} className={selected?.id === config.id ? 'selected' : ''}>
              <th><button aria-pressed={selected?.id === config.id} disabled={!data} onClick={() => setMemberId(config.id)}>{config.name} <small>{config.code} · {config.tracking_index}</small></button></th>
              <td>{config.group}</td><td className={etfTone(data?.metrics.delta)}>{etfNumber(data?.metrics.delta, 1e8)} 亿份<small>{etfPercent(data?.metrics.change_rate)}</small></td>
              <td className={etfTone(data?.metrics.amount)}>{etfAmount(data?.metrics.amount)}</td><td>{etfPercent(data?.metrics.premium)}</td>
              <td>{!data ? '不在所选版本（现行目录）' : data.reason ? etfReason(data.reason) : !data.active ? '未参与所选口径' : '有效'}
                {data?.input_basis === 'posthoc_inputs' && <small>事后输入</small>}</td></tr>)}</tbody></table></div>
          <p className="etf-note">{evaluation?.exclusions.map(item => `${view.members.find(m => m.id === item.member_id)?.name ?? item.member_id}：${etfReason(item.reason)}`).join('；') || '排除情况以所选日服务记录为准。'}</p>
        </section>
        <div className="etf-detail-grid"><section className="etf-panel" data-module="fund-flows.10" aria-labelledby="etf-single">
          <header className="etf-panel-head"><div><p className="etf-eyebrow">单只明细</p><h2 id="etf-single">{selected?.name ?? '暂无成员'}</h2><small>{selected ? `${selected.code} · ${selected.tracking_index}` : '所选版本无成员'}</small></div>
            <div className="m-segmented" role="group" aria-label="单只图表副图"><button aria-pressed={singleMode === 'delta'} onClick={() => setSingleMode('delta')}>份额增减</button><button aria-pressed={singleMode === 'turnover'} onClick={() => setSingleMode('turnover')}>成交额</button></div></header>
          {selected && <><div className="etf-single-metrics">
            {[['总份额', `${etfNumber(selected.metrics.shares, 1e8)} 亿份`], ['单位净值', `${etfNumber(selected.metrics.nav, 1, 4)} 元`],
              ['收盘价', `${etfNumber(selected.metrics.close, 1, 3)} 元`], ['净资产估算', etfAmount(selected.metrics.net_assets)],
              ['成交额', etfAmount(selected.metrics.turnover)], ['成交额 / 净资产', etfPercent(selected.metrics.turnover_ratio)],
              ['单只近 5 日累计', etfAmount(selected.amount_5)], ['单只近 20 日累计', etfAmount(selected.amount_20)]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
            <EtfFlowChart points={singlePoints} theme={theme} label="所选ETF总份额与副图" barLabel={singleMode === 'delta' ? '增减亿份' : '成交亿元'} lineLabel="总亿份" markers={singleMarkers} />
            {selected.metrics.reason && <p className="m-warning">{etfReason(selected.metrics.reason)}</p>}
            <p className="etf-note">{selected.admission ? `历史准备记录：${selected.admission.start} 至 ${selected.admission.end}，${selected.admission.required_days} 个连续交易日；首次达标 ${etfTime(selected.admission.first_qualified_at)}（北京时间）。`
              : '历史不足：尚无符合所选版本的历史准备达标记录，不进入观察池合计。'}</p>
            <div className="etf-context"><strong>市场背景 · 事后保存的同日资料</strong>
              {view.context.indices.filter(index => index.index_id === selected.index_id).map(index => <p key={index.index_id}>{selected.tracking_index}：当日 {index.return_1 === null ? '—' : etfNumber(index.return_1) + '%'} · 近5日 {index.return_5 === null ? '—' : etfNumber(index.return_5) + '%'}</p>)}
              {!view.context.indices.some(index => index.index_id === selected.index_id) && <p>对应指数：暂无同日背景数据</p>}
              {view.context.market ? <p>{view.context.market.scope_label}：{etfAmount(view.context.market.turnover)} · 较此前20日均值 {etfNumber(view.context.market.ratio_20)} 倍</p> : <p>市场成交额背景：暂无数据</p>}
              <small>背景不判断资金主体；成交额 / 净资产不是交易所换手率。</small></div></>}
        </section><EtfDisclosures view={view} member={selected} evidence={id => setDialog({ type: 'evidence', id })} /></div>
        <div className="etf-detail-grid"><section className="etf-panel" data-module="fund-flows.12" aria-labelledby="etf-history">
          <header className="etf-panel-head"><h2 id="etf-history">观察记录</h2><span className="etf-tag">{modeLabel}</span></header>
          {!view.history.length && <p>{view.mode === 'original' ? '没有当时保存的记录。首次补历史不补造过去已经发布的信号。' : '所选窗口没有已保存的重算记录，不以缺失代替零。'}</p>}
          {view.history.slice(-5).reverse().map(item => <article className="etf-record" key={item.result_id}>
            <button onClick={() => client && changeQuery({ end: item.date, mode: view.mode, group: item.group_id ?? '',
              record: { snapshot: view.snapshot_id, result: item.result_id, instance: client.instance, config: client.expected.config_id } })}>{item.date} · {etfState(item.state)}</button><span> {item.partial ? '部分小计 ' : ''}{etfAmount(item.amount)}</span>
            <p>有效 {item.valid_count}/{item.active_count} · 池 {item.pool_version} · 规则 {item.rule_version}</p>
            <small>计算时间 {etfTime(item.calculated_at)}（北京时间）</small>
          </article>)}<p className="etf-note">显示最近 5 条；可用观察日期回看其他交易日。当前重算不会覆盖当时记录。</p>
        </section><EtfEvents view={view} member={selected} evidence={id => setDialog({ type: 'evidence', id })} /></div>
        <section className="etf-data-strip" data-module="fund-flows.14" aria-label="数据与版本状态">
          <p>输入所属日 {view.end} · 显示窗口 {view.data_status.history_first} 至 {view.data_status.history_last} · 准入至少 {view.data_status.required_days} 个连续交易日</p>
          <p>{view.data_status.complete_amount_through ? `完整金额覆盖至 ${view.data_status.complete_amount_through}` : '完整金额覆盖截止日：未知'} · 所选口径最近完整金额日，不保证此前无缺口。</p>
          <p>池 {view.pool_version} · 规则 {view.rule_version} · 公式 {view.formula_version} · 资料 {view.data_status.evidence_version}</p>
          <p>输入选定 {etfTime(view.selection_at)} · 计算 {etfTime(view.calculated_at)}（北京时间）</p>
          <details><summary>输入版本及来源时点</summary><p className="etf-digest">固定快照 {view.snapshot_id}<br />输入 {view.input_version}</p>
            {view.sources.map((source, index) => <p key={index}>{source.publisher} / {source.channel} · {source.locator} · 获取 {etfTime(source.retrieved_at)} · 公开 {etfTime(source.published_at)} <button onClick={() => setDialog({ type: 'evidence', id: source.object_id })}>核对证据</button></p>)}</details>
        </section>
        {notes && <aside className="etf-data-strip" aria-label="数据说明"><h2>数据说明</h2><p>可比前日份额＝前日份额×核验折算倍率＋确认尾差；净申赎估算＝可比份额变化×同日单位净值。全部计算由可信本地服务提供。不同ETF的份额不相加；缺净值、缺前日或折算未核验均不补零。</p>
          <p>C1固定同一名单、使用此前窗口和样本标准差；C2分母为有效ETF只数。历史不足不进观察池合计，未确认参数不生成正式异常结论。停用日起不参与，历史记录保留。后来的披露仅作明确标识的事后对照。</p></aside>}
      </>}
      <footer className="m-footer"><span>本地已保存数据 · 研究线索，不识别具体买卖主体</span><span>THE WOLF / MARKET RESEARCH</span></footer>
    </main>
    {dialog?.type === 'configuration' && view && current && <EtfConfiguration view={view} current={current} close={() => setDialog(undefined)} />}
    {dialog?.type === 'evidence' && view && client && <EtfEvidenceDialog key={dialog.id} client={client} view={view} sourceId={dialog.id} close={() => setDialog(undefined)} />}
  </div>;
}
