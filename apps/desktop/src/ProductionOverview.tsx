import { useEffect, useMemo, useRef, useState } from "react";
import type { ApiClient } from "./apiClient";
import { activityConnectionDescriptor, indexConnectionDescriptor } from "./browserHost";
import { IndexReadError, IndexSeriesClient } from "./indexSeriesClient";
import { OVERVIEW_INDICES, trendBars, type OverviewIndexId, type SeriesSnapshot } from "./indexSeriesTypes";
import { MA_PERIODS, FREQUENCIES, FREQUENCY_LABELS, RESULT_REASONS, percentDisplay, type Calculations, type CalculationSeries, type Frequency } from "./indexCalculationTypes";
import { ActivityChart, ActivityTrend, MiniTrend, PriceChart, type ChartWindow, type Theme } from "./OverviewCharts";
import { createStartupPriceObservation, watchStartupPrices, type StartupPriceObservation } from "./startupPrices";
import { watchPeriodicUpdates } from "./periodicUpdates";
import { watchStartupActivity } from "./startupActivity";
import { ActivityReadError, ActivityClient } from "./activityClient";
import { ActivityDetails } from "./ActivityDetails";
import { MARKET, LEGACY_MARKET, isMarket, activityGate, activityReason, activityText, type ActivityField, type ActivityId, type ActivityBundle, type ActivityDescriptor, type ActivitySeries } from "./activityTypes";
import { priceText } from "./overviewPriceText";
import "./overview.css";
type ActivityState = { owner: string; loading?: boolean; descriptor?: ActivityDescriptor; anchor?: string; error?: string; entries: Partial<Record<ActivityId, { bundle?: ActivityBundle; error?: string }>> };

type Row = { snapshot?: SeriesSnapshot; calculations?: Calculations; calculationError?: string; loading: boolean; error?: string; empty?: boolean; stale?: boolean };
type Rows = Partial<Record<OverviewIndexId, Row>>;
const DEFAULT_MA = [5, 10, 20, 30, 250];
const sources: Record<string, string> = { csindex: "中证指数", cnindex: "国证指数", eastmoney: "东方财富", sse: "上交所", szse: "深交所", bse: "北交所", "cnindex-raw": "国证指数" };
function errorText(reason: unknown): string {
  return reason instanceof TypeError ? "连接不可用，请检查本地服务并重新连接。"
    : reason instanceof Error ? reason.message : "指数读取失败";
}
function timeText(value: string) {
  const time = new Date(value);
  return Number.isFinite(time.getTime()) ? time.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "时间格式不可用";
}

function Missing({ reason }: { reason: string }) { return <span className="m-missing" title={reason}>暂无数据</span>; }

/** 按服务端能力灰显不可用档位，跨周期保留价格及量额各自偏好。 */
function MovingAverageSettings({ market, marketLabel, activity, frequency, series, selected, onSelect, activitySeries, activitySelected, onActivitySelect }: {
  market: boolean; marketLabel: string; activity: string; frequency: Frequency; series?: CalculationSeries; selected: number[]; onSelect: (period: number) => void; activitySeries?: ActivitySeries; activitySelected: number[]; onActivitySelect: (period: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    function pointer(event: PointerEvent) { if (!container.current?.contains(event.target as Node)) setOpen(false); }
    function keyboard(event: KeyboardEvent) { if (event.key === "Escape") { setOpen(false); toggle.current?.focus(); } }
    document.addEventListener("pointerdown", pointer); document.addEventListener("keydown", keyboard);
    return () => { document.removeEventListener("pointerdown", pointer); document.removeEventListener("keydown", keyboard); };
  }, [open]);
  return <div className="m-ma-settings" ref={container}>
    <button ref={toggle} aria-expanded={open} aria-controls="overview-ma-panel" onClick={() => setOpen(value => !value)}>均线设置 ▾</button>
    {open && <div id="overview-ma-panel" className="m-ma-panel">
      {!market && <fieldset><legend>价格 · {FREQUENCY_LABELS[frequency]}均线</legend><div className="m-ma-grid">
        {MA_PERIODS.map(period => {
          const ability = series?.ma_availability.find(item => item.period === period);
          const reason = ability ? `需要${ability.required_count}根有效${FREQUENCY_LABELS[frequency]}K，现有${ability.sample_count}根` : "计算结果未取得";
          return <label key={period} title={reason} className={ability?.available ? "" : "m-disabled"}>
            <input type="checkbox" checked={selected.includes(period)} disabled={!ability?.available} onChange={() => onSelect(period)}
              aria-describedby={!ability?.available ? `ma-reason-${period}` : undefined} /><span>MA{period}</span></label>;
        })}</div>
        {MA_PERIODS.filter(period => !series?.ma_availability.find(item => item.period === period)?.available).map(period => {
          const ability = series?.ma_availability.find(item => item.period === period);
          return <p key={period} id={`ma-reason-${period}`}>MA{period}：暂无数据；{ability
            ? `需要${ability.required_count}根有效${FREQUENCY_LABELS[frequency]}K，现有${ability.sample_count}根` : "计算结果未取得"}。</p>;
        })}</fieldset>}
      <fieldset><legend>{market ? marketLabel : activity === "volume" ? "成交量 VOL" : "成交额"} · {market ? "日" : FREQUENCY_LABELS[frequency]}均线</legend>
        <div className="m-ma-grid">{MA_PERIODS.map(period => {
          const ability = activitySeries?.ma_availability.find(item => item.period === period);
          const reason = ability ? `${activityReason(ability.reason)}；需要${period}根连续有效周期，窗口内有效${ability.sample_count}根` : "量额数据未取得";
          return <label className={ability?.available ? "" : "m-disabled"} key={period} title={reason}>
            <input type="checkbox" checked={activitySelected.includes(period)} disabled={!ability?.available} onChange={() => onActivitySelect(period)} /><span>MA{period}</span></label>;
        })}</div>
        {MA_PERIODS.filter(period => !activitySeries?.ma_availability.find(item => item.period === period)?.available).map(period => {
          const ability = activitySeries?.ma_availability.find(item => item.period === period);
          return <p key={period}>MA{period}：暂无数据；{ability ? `${activityReason(ability.reason)}，需要${period}根连续有效周期，窗口内有效${ability.sample_count}根` : "量额数据未取得"}。</p>;
        })}</fieldset>
    </div>}
  </div>;
}

/** 正式总览第三批：价格与量额按固定快照成对展示，不引入前端金融计算。 */
export function ProductionOverview({ connectionClient, connectionError, reconnect, refreshToken = 0, onUpdate }: {
  connectionClient?: ApiClient; refreshToken?: number; onUpdate?: (target: string) => void; connectionError?: string; reconnect: () => void;
}) {
  const [theme, setTheme] = useState<Theme>("light");
  const [navOpen, setNavOpen] = useState(false);
  const navToggle = useRef<HTMLButtonElement>(null);
  const [notes, setNotes] = useState(false);
  const [selected, setSelected] = useState<OverviewIndexId | "three-market">(OVERVIEW_INDICES[0].id);
  const [observation, setObservation] = useState("60");
  const [range, setRange] = useState<ChartWindow>({ preset: "12" });
  const [frequency, setFrequency] = useState<Frequency>("daily");
  const [maPeriods, setMaPeriods] = useState<number[]>(DEFAULT_MA);
  const [activity, setActivity] = useState<ActivityField>("amount");
  const [activityMA, setActivityMA] = useState({ amount: DEFAULT_MA, volume: DEFAULT_MA, market: DEFAULT_MA });
  const [cursor, setCursor] = useState<string>();
  const [activityState, setActivityState] = useState<ActivityState>({ owner: "", entries: {} });
  const [rows, setRows] = useState<Rows>({});
  const [activityNotice, setActivityNotice] = useState<string>();
  const [startupNotice, setStartupNotice] = useState<string>();
  const [phase, setPhase] = useState("正在连接本地服务…");
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(true);
  const generation = useRef(0);
  const previousScope = useRef<string | undefined>(undefined);
  const startupObservation = useRef<{ owner: ApiClient; state: StartupPriceObservation } | undefined>(undefined);

  const activityObservation = useRef<{ owner: ApiClient; state: StartupPriceObservation } | undefined>(undefined);

  const activityOwner = `${connectionClient?.expected.config_id ?? ""}:${connectionClient?.instance ?? ""}`;
  useEffect(() => {
    const sequence = ++generation.current;
    const controller = new AbortController();
    let client: IndexSeriesClient | undefined, activityClient: ActivityClient | undefined;
    const loaded: Rows = {};
    setStartupNotice(undefined);
    setActivityNotice(undefined);
    setActivityState(previous => ({ owner: activityOwner, entries: previous.owner === activityOwner ? previous.entries : {}, loading: true }));
    // v1已确认资料范围后立即隔离旧根；不能等可选v2配置或握手成功。
    const scope = connectionClient?.expected.data_scope_id;
    if (scope && previousScope.current !== scope) {
      previousScope.current = scope;
      setRows({});
    } else {
      setRows(previous => Object.fromEntries(Object.entries(previous).map(([key, value]) => [key, { ...value, stale: Boolean(value.snapshot), loading: false }])));
    }
    if (!connectionClient) { setActivityState({ owner: activityOwner, entries: {}, error: connectionError ?? "正在连接本地服务…" }); setPhase(connectionError ?? "正在连接本地服务…"); setBusy(!connectionError); return () => controller.abort(); }
    setBusy(true); setPhase("正在核对指数连接…");
    void (async () => {
      const expected = await indexConnectionDescriptor(connectionClient.expected, controller.signal);
      if (controller.signal.aborted) return;
      if (!expected) { setActivityState({ owner: activityOwner, entries: {}, error: "量额连接需要已配置的指数连接" }); setPhase("指数连接未配置，请检查本地启动配置。"); setBusy(false); return; }
      if (connectionClient.closed) throw new Error("原连接已失效，请重新连接");
      client = await IndexSeriesClient.connect(expected, connectionClient.instance, controller.signal);
      if (controller.signal.aborted) { client.close(); return; }
      setPhase("正在读取已保存价格及计算结果…");
      await Promise.all(OVERVIEW_INDICES.map(async item => {
        setRows(previous => ({ ...previous, [item.id]: { ...previous[item.id], loading: true, error: undefined } }));
        try {
          const snapshot = await client!.current(item.id, controller.signal);
          let calculations: Calculations | undefined, calculationError: string | undefined;
          try { calculations = await client!.calculations(snapshot, controller.signal); }
          catch (reason) { calculationError = errorText(reason); }
          loaded[item.id] = { snapshot, calculations, loading: false };
          // 新价格只能搭配自己的计算；失败时明确缺失，绝不挂接上次快照的计算。
          if (!controller.signal.aborted && sequence === generation.current) setRows(previous => ({ ...previous,
            [item.id]: { snapshot, calculations, calculationError, loading: false, stale: false } }));
        } catch (reason) {
          if (!controller.signal.aborted && sequence === generation.current) setRows(previous => ({ ...previous, [item.id]: {
            ...previous[item.id], loading: false, stale: Boolean(previous[item.id]?.snapshot),
            empty: reason instanceof IndexReadError && reason.status === 404 && reason.code === "index_series_empty",
            error: errorText(reason),
          } }));
        }
      }));
      // 首轮价格读取完成后才观察，避免启动通知取消首屏并重复完整快照读取。
      const initialVersions = new Map(Object.entries(loaded).flatMap(([id, row]) => row.snapshot
        ? [[id, row.snapshot.snapshot_id] as const] : []));
      if (!startupObservation.current || startupObservation.current.owner !== connectionClient) {
        startupObservation.current = { owner: connectionClient, state: createStartupPriceObservation() };
      }
      if (!expected.policy.periodic) void watchStartupPrices(client, controller.signal,
        () => { if (!controller.signal.aborted && sequence === generation.current) setReload(value => value + 1); },
        message => { if (!controller.signal.aborted && sequence === generation.current) setStartupNotice(message); }, initialVersions, startupObservation.current.state);
      if (!controller.signal.aborted) setPhase("价格读取完成，正在读取量额与计算结果…");
      const activityVersions = new Map<ActivityId, string>();
      let descriptor: Awaited<ReturnType<typeof activityConnectionDescriptor>>;
      let descriptorResolved = false;
      const connectActivity = async () => {
        if (controller.signal.aborted || sequence !== generation.current || client!.closed || connectionClient.closed) return undefined;
        if (activityClient) return activityClient;
        if (!descriptorResolved) {
          descriptor = await activityConnectionDescriptor(expected, controller.signal);
          if (controller.signal.aborted || sequence !== generation.current) return undefined;
          descriptorResolved = true;
        }
        if (!descriptor) return undefined;
        const received = await ActivityClient.connect(descriptor, client!.instance, controller.signal);
        if (controller.signal.aborted || sequence !== generation.current || client!.closed || connectionClient.closed) { received.close(); return undefined; }
        activityClient = received;
        setActivityState(previous => ({ owner: activityOwner, entries: previous.owner === activityOwner ? previous.entries : {}, descriptor, loading: false }));
        return received;
      };
      const connectionFailed = (reason: unknown) => {
        const transient = !client?.closed && !activityClient?.closed && (reason instanceof TypeError
          || reason instanceof IndexReadError && reason.status === 409 && reason.code === "index_series_invalid"
          || reason instanceof DOMException && ["TimeoutError", "AbortError"].includes(reason.name)
          || reason instanceof ActivityReadError && !["connection_context_mismatch", "source_withdrawn", "source_unverified", "activity_replay_mismatch", "activity_evidence_invalid"].includes(reason.code));
        if (!controller.signal.aborted && sequence === generation.current) setActivityState(previous => ({ owner: activityOwner,
          entries: transient && previous.owner === activityOwner ? previous.entries : {},
          descriptor: transient ? previous.descriptor : undefined, anchor: transient ? previous.anchor : undefined, loading: false, error: errorText(reason) }));
      };
      try {
        await connectActivity();
        if (controller.signal.aborted) return;
        if (!descriptor) setActivityState({ owner: activityOwner, entries: {}, error: "量额连接未配置" });
        else {
          const status = expected.policy.periodic ? await client.overviewStatus(controller.signal) : undefined;
          const anchor = status?.market_anchor_date ?? activityClient!.marketAnchor;
          const marketAnchors = status?.market_anchors ?? activityClient!.marketAnchors;
          const activityTargets = new Map<ActivityId, string>();
          if (!controller.signal.aborted) setActivityState(previous => ({ owner: activityOwner, entries: previous.entries, descriptor, anchor, loading: true }));
          const activityIds: ActivityId[] = [...OVERVIEW_INDICES.map(item => item.id), MARKET, LEGACY_MARKET];
          // 三年两/三市快照较大；逐项读取避免同进程校验排队耗尽单请求期限。
          for (const id of activityIds) {
            if (controller.signal.aborted || sequence !== generation.current) break;
            let bundle: ActivityBundle | undefined, error: string | undefined, keepPrevious = true;
            try {
              const gate = activityGate(descriptor!, id);
              if (gate) throw new Error(gate);
              const price = isMarket(id) ? undefined : loaded[id as OverviewIndexId]?.snapshot;
              if (!isMarket(id) && !price) throw new Error("当前价格快照未取得，无法绑定量额");
              // 首屏读已发布日期；非周期启动仍观察ready冻结的新目标，空库也要跟进。
              activityTargets.set(id, price?.snapshot_id ?? anchor);
              const marketAnchor = isMarket(id) && marketAnchors ? marketAnchors[id === MARKET ? "sse_szse" : "sse_szse_bse"] : anchor;
              if (isMarket(id) && !marketAnchor) throw new Error("尚无已发布市场数据");
              bundle = await activityClient!.load(id, price?.window.anchor_date ?? marketAnchor!, price, isMarket(id) ? undefined : loaded[id as OverviewIndexId]?.calculations, controller.signal);
              activityVersions.set(id, bundle.snapshot.activity_id);
            } catch (reason) {
              error = errorText(reason);
              keepPrevious = !activityClient?.closed && !(reason instanceof ActivityReadError && ["connection_context_mismatch", "source_withdrawn", "source_unverified", "activity_replay_mismatch", "activity_evidence_invalid"].includes(reason.code));
            }
            if (!controller.signal.aborted && sequence === generation.current) setActivityState(previous => ({ ...previous, entries: { ...previous.entries, [id]: { bundle: bundle ?? (keepPrevious ? previous.entries[id]?.bundle : undefined), error } } }));
          }
          if (!controller.signal.aborted) setActivityState(previous => ({ ...previous, loading: false }));
          if (!activityObservation.current || activityObservation.current.owner !== connectionClient) {
            activityObservation.current = { owner: connectionClient, state: createStartupPriceObservation() };
          }
          if (!expected.policy.periodic) void watchStartupActivity(activityClient!, activityTargets, activityVersions, controller.signal, async id => {
            const price = isMarket(id) ? undefined : loaded[id as OverviewIndexId]?.snapshot;
            const received = await activityClient!.load(id, price?.window.anchor_date ?? activityTargets.get(id)!, price,
              isMarket(id) ? undefined : loaded[id as OverviewIndexId]?.calculations, controller.signal);
            if (!controller.signal.aborted && sequence === generation.current) setActivityState(previous => ({ ...previous,
              entries: { ...previous.entries, [id]: { bundle: received } } }));
            return received.snapshot.activity_id;
          }, (id, error) => {
            if (!controller.signal.aborted && sequence === generation.current) {
              const invalid = activityClient!.closed || (error instanceof ActivityReadError && ["source_withdrawn", "source_unverified", "activity_replay_mismatch", "activity_evidence_invalid"].includes(error.code));
              setActivityState(previous => ({ ...previous, entries: { ...previous.entries,
                [id]: { bundle: invalid ? undefined : previous.entries[id]?.bundle, error: errorText(error) } } }));
            }
          }, message => { if (!controller.signal.aborted && sequence === generation.current) setActivityNotice(message); }, activityObservation.current.state);
        }
      } catch (reason) {
        connectionFailed(reason);
      }
      if (expected.policy.periodic && !controller.signal.aborted) {
        void watchPeriodicUpdates(client, activityClient, controller.signal, initialVersions, activityVersions,
          async id => {
            const snapshot = await client!.current(id, controller.signal);
            const calculations = await client!.calculations(snapshot, controller.signal);
            if (!controller.signal.aborted && sequence === generation.current) {
              loaded[id] = { snapshot, calculations, loading: false };
              setRows(previous => ({ ...previous, [id]: loaded[id] }));
            }
            return snapshot.snapshot_id;
          }, async (id, anchor) => {
            const price = isMarket(id) ? undefined : loaded[id as OverviewIndexId]?.snapshot;
            if (!isMarket(id) && !price) throw new Error("当前价格快照未取得，无法绑定量额");
            const received = await activityClient!.load(id, price?.window.anchor_date ?? anchor, price,
              isMarket(id) ? undefined : loaded[id as OverviewIndexId]?.calculations, controller.signal);
            if (!controller.signal.aborted && sequence === generation.current) setActivityState(previous => ({ ...previous,
              descriptor, error: undefined, loading: false, anchor: isMarket(id) ? anchor : previous.anchor, entries: { ...previous.entries, [id]: { bundle: received } } }));
            return received.snapshot.activity_id;
          }, message => { if (!controller.signal.aborted && sequence === generation.current) setStartupNotice(message); },
          (id, error) => {
            if (!controller.signal.aborted && sequence === generation.current) {
              const invalid = activityClient?.closed || (error instanceof ActivityReadError && ["source_withdrawn", "source_unverified", "activity_replay_mismatch", "activity_evidence_invalid"].includes(error.code));
              setActivityState(previous => ({ ...previous, entries: { ...previous.entries,
                [id]: { bundle: invalid ? undefined : previous.entries[id]?.bundle, error: errorText(error) } } }));
            }
          }, async () => {
            try { return await connectActivity(); }
            catch (reason) { connectionFailed(reason); throw reason; }
          });
      }
      if (!controller.signal.aborted) { setBusy(false); setPhase(client.closed ? "指数连接已失效，请重新连接。" : "读取结束 · 当前读取不采集新行情"); }
    })().catch(reason => {
      if (!controller.signal.aborted) { setActivityState({ owner: activityOwner, entries: {}, error: errorText(reason) }); setBusy(false); setPhase(errorText(reason)); }
    });
    return () => { controller.abort(); client?.close(); activityClient?.close(); };
  }, [connectionClient, connectionError, reload, refreshToken]);

  const trends = useMemo(() => Object.fromEntries(OVERVIEW_INDICES.map(item => [item.id,
    rows[item.id]?.snapshot ? trendBars(rows[item.id]!.snapshot!.bars, observation) : undefined])), [rows, observation]);
  const market = selected === "three-market";
  const marketId = LEGACY_MARKET;
  const marketLabel = "沪深北三市合计";
  const marketScope = "沪深北 A股股票";
  const row = market ? undefined : rows[selected];
  const snapshot = row?.snapshot;
  const series = row?.calculations?.[frequency];
  const quantity: ActivityState = activityState.owner === activityOwner ? activityState : { owner: activityOwner, entries: {}, loading: true };
  const activityId = market ? marketId : selected as OverviewIndexId;
  const entry = quantity.entries[activityId];
  // 价格切换与响应到达顺序不能让旧量额短暂挂到新的价格上。
  const bundle = entry?.bundle && (market || entry.bundle.snapshot.price_snapshot_id === snapshot?.snapshot_id) ? entry.bundle : undefined;
  const missingPricePeriod = !market && frequency !== "daily" && !series;
  const quantitySeries = missingPricePeriod ? undefined : bundle?.calculations.series.find(item => item.field === (market ? "amount" : activity) && item.frequency === (market ? "daily" : frequency));
  const quantityError = missingPricePeriod ? "当前周期价格计算未取得，量额副图暂无数据" : quantity.loading ? "正在读取量额…" : entry?.error ?? quantity.error ?? (!bundle ? "量额数据未取得" : undefined);
  const marketBundle = quantity.entries[marketId]?.bundle;
  const marketSeries = marketBundle?.calculations.series[0];


  const selectedActivityMA = activityMA[market ? "market" : activity];
  const activitySources = bundle ? [...new Set(bundle.snapshot.sources.map(item => sources[item.source] ?? item.source))].join(" / ") : "暂无数据";
  const receiptTimes = bundle?.snapshot.observations.at(-1)?.sources.map(item => item.completed_at).sort((a, b) => Date.parse(a) - Date.parse(b)) ?? [];
  const activityReceipt = receiptTimes.length ? (receiptTimes[0] === receiptTimes.at(-1) ? timeText(receiptTimes[0])
    : `${timeText(receiptTimes[0])} 至 ${timeText(receiptTimes.at(-1)!)}`) : "暂无数据";
  const definition = OVERVIEW_INDICES.find(item => item.id === selected);
  const snapshots = Object.values(rows).flatMap(value => value.snapshot ? [value.snapshot] : []);
  const dates = [...new Set(snapshots.map(value => value.window.end))];
  const asOf = dates.length === 1 ? `${dates[0]} 收盘` : dates.length ? "各指数截至日见列表" : "暂无数据";

  return <div className={`overview-app ${navOpen ? "m-nav-open" : ""}`} data-theme={theme}
    onKeyDown={event => { if (event.key === "Escape" && navOpen) { setNavOpen(false); navToggle.current?.focus(); } }}>
    <a href="#overview-main" className="m-skip">跳到页面内容</a>
    <aside className="m-sidebar" id="overview-navigation" aria-label="全站导航">
      <div className="m-brand"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 5l8 5 5-4 5 4 8-5-4 17-9 6-9-6zM8 13l8 10 8-10M16 23v5" /></svg><span>THE WOLF<small>个人研究工作台</small></span></div>
      <p className="m-nav-group">市场研究</p><nav aria-label="市场研究">
        <button aria-current="page" onClick={() => setNavOpen(false)}><span>↗</span>行情总览</button>
        {["大资金动向", "量价分析", "题材概念", "个股查询", "大事新闻"].map(name => <button key={name} disabled title="尚未接入正式页面"><span>◇</span>{name}</button>)}
      </nav><div className="m-nav-bottom"><span>●</span> 本地研究工作台</div>
    </aside>
    {navOpen && <button className="m-backdrop" aria-label="关闭导航" onClick={() => setNavOpen(false)} />}
    <main className="m-main" id="overview-main" tabIndex={-1}>
      <div className="m-topbar"><div className="m-breadcrumb"><button ref={navToggle} className="m-mobile-toggle" aria-expanded={navOpen} aria-controls="overview-navigation" aria-label="展开或收起导航" onClick={() => setNavOpen(value => !value)}>☰</button>市场研究<span>/</span><strong>行情总览</strong></div>
        <div className="m-top-actions"><label><input type="checkbox" checked={notes} onChange={event => setNotes(event.target.checked)} />显示数据说明</label>
          <button aria-pressed={theme === "dark"} aria-label="深色备选主题" onClick={() => setTheme(value => value === "light" ? "dark" : "light")}>{theme === "light" ? "深色模式" : "浅色模式"}</button></div></div>
      <header className="m-heading"><div><h1>行情总览</h1><p className="m-muted">数据截至 {market ? bundle?.snapshot.window.end ?? "暂无数据" : asOf} · A 股市场</p></div>
        <div className="m-update"><p>{market ? marketLabel : "所选指数"}获取时间（北京时间）<br />{market ? activityReceipt : snapshot ? timeText(snapshot.retrieval.observed_at) : "暂无数据"}</p>
          <button onClick={() => onUpdate?.(market ? "activity:" + marketId : "price:" + selected)} disabled={!onUpdate}>更新数据</button></div></header>
      {startupNotice && <p role="status" className="m-startup-status">{startupNotice}</p>}
      {activityNotice && <p role="status" className="m-startup-status">{activityNotice}</p>}
      <div className="m-connection"><p role={!busy && !phase.startsWith("读取结束") ? "alert" : "status"}>{phase}</p><div><button disabled={busy || !connectionClient} onClick={() => setReload(value => value + 1)}>重新读取</button><button onClick={reconnect}>重新连接</button></div></div>

      <section data-module="market-overview.01" aria-labelledby="overview-summary-title">
        <div className="m-section-line"><div className="m-section-label"><span>01</span><h2 id="overview-summary-title">市场概况</h2></div>
          <div className="m-window-control"><span>观察窗口</span><div className="m-segmented" role="group" aria-label="观察窗口">{[["5", "5 日"], ["20", "20 日"], ["60", "60 日"], ["1y", "1 年"]].map(([value, label]) => <button key={value} aria-pressed={observation === value} onClick={() => setObservation(value)}>{label}</button>)}</div></div></div>
        <div className="m-table-scroll" role="region" aria-label="行情指标表，窄屏可横向滚动" tabIndex={0}><table className="m-table"><caption className="m-sr-only">选择指标查看详情；观察窗口改变收盘走势与同快照区间涨跌。</caption>
          <thead><tr><th>指标</th><th>最新值</th><th>较前日</th><th>区间比较</th><th>走势</th></tr></thead>
          <tbody>{OVERVIEW_INDICES.map(item => {
            const current = rows[item.id], value = current?.snapshot, pct = value?.summary.daily_change_pct;
            const key = observation === "1y" ? "year_1" : `day_${observation}` as "day_5" | "day_20" | "day_60";
            const performance = current?.calculations?.performance[key];
            const performanceReason = performance?.reason ? RESULT_REASONS[performance.reason] : current?.calculationError ?? "计算结果未取得";
            return <tr key={item.id} className={selected === item.id ? "selected" : ""}>
              <th scope="row"><button className="m-metric-select" aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}>{item.name}<small>{item.code}</small></button></th>
              <td>{value ? <><strong className="m-metric-value">{priceText(value.summary.close, true)}</strong><small>{value.window.end}{current?.stale ? " · 上次数据" : ""}</small></> : <Missing reason={current?.loading ? "正在读取" : current?.error ?? "尚无已保存价格"} />}</td>
              <td>{pct != null ? <span className={pct.startsWith("-") ? "m-down" : pct === "0.00" ? "m-flat" : "m-up"}>{!pct.startsWith("-") && pct !== "0.00" ? "+" : ""}{pct}%</span> : <Missing reason="缺少已发布的前日比较" />}</td>
              <td>{performance?.value != null ? <span className={percentDisplay(performance.value).className}>{percentDisplay(performance.value).text}</span>
                : <Missing reason={performanceReason} />}</td>
              <td>{trends[item.id] ? <MiniTrend bars={trends[item.id]!} theme={theme} /> : <Missing reason="尚无已保存价格" />}</td>
            </tr>;
          })}{([LEGACY_MARKET] as const).map(id => {
            const data = quantity.entries[id]?.bundle;
            const graph = data?.calculations.series[0];
            const last = graph?.rows.at(-1);
            const comparison = data?.calculations.comparisons?.[observation === "1y" ? "year_1" : `day_${observation}` as "day_5" | "day_20" | "day_60"];
            const name = marketLabel;
            return <tr key={id} className={market && marketId === id ? "selected" : ""}><th scope="row"><button className="m-metric-select" aria-pressed={market && marketId === id} onClick={() => setSelected("three-market")}>{name}<small>{marketScope}</small></button></th>
              <td>{last?.total.value != null ? <><strong className="m-metric-value m-market-amount">{activityText(last.total.value, "amount")}</strong><small>亿元 · {last.end}</small></> : <Missing reason={activityReason(last?.total.reason) + (quantity.entries[id]?.error ?? quantity.error ?? "")} />}</td>
              <td>{last?.change_pct.value != null ? <span className={percentDisplay(last.change_pct.value).className}>{percentDisplay(last.change_pct.value).text}</span> : <Missing reason={activityReason(last?.change_pct.reason)} />}</td>
              <td>{comparison?.comparison.value != null ? <span className={percentDisplay(comparison.comparison.value).className}>{percentDisplay(comparison.comparison.value).text}<small>较窗口均额</small></span> : <Missing reason={activityReason(comparison?.comparison.reason)} />}</td>
              <td>{graph ? <ActivityTrend series={graph} observation={observation} theme={theme} /> : <Missing reason="缺少成交额序列" />}</td></tr>;
          })}</tbody></table></div>
        <p className="m-table-foot">点击指标查看下方详情 · 观察窗口按交易日／自然年比较 · 成交额较观察窗口均额比较，不由四指数相加</p>
        {OVERVIEW_INDICES.filter(item => rows[item.id]?.error).map(item => <p key={item.id} className="m-warning" role={rows[item.id]?.empty ? "status" : "alert"}>{item.name}：{rows[item.id]?.empty ? "暂无数据，尚未保存价格" : rows[item.id]?.error}{rows[item.id]?.snapshot ? "；保留上次成功读取的快照。" : ""}</p>)}
        {OVERVIEW_INDICES.filter(item => rows[item.id]?.calculationError).map(item => <p key={item.id} className="m-warning" role="alert">{item.name}：计算结果暂无数据；{rows[item.id]?.calculationError}。</p>)}
      </section>

      <section className="m-chart-section" data-module={market ? "market-overview.03" : "market-overview.02"} aria-labelledby="overview-detail-title">
        <header className="m-chart-heading"><div className="m-chart-title"><span>{market ? "03" : "02"}</span><h2 id="overview-detail-title">{market ? marketLabel : definition!.name}</h2><code>{market ? marketScope : definition!.code}</code></div>
          {!market && <div className="m-segmented" role="group" aria-label="K线周期">{FREQUENCIES.map(value => <button key={value} aria-pressed={frequency === value} disabled={value !== "daily" && !row?.calculations}
            title={value !== "daily" && !row?.calculations ? "暂无数据：计算结果未取得" : undefined} onClick={() => setFrequency(value)}>{FREQUENCY_LABELS[value]} K</button>)}</div>}</header>
        <div className="m-chart-controls"><div className="m-range-controls" role="group" aria-label="图表显示范围"><span>显示范围</span>{[["1", "1 月"], ["3", "3 月"], ["6", "6 月"], ["12", "1 年"], ["36", "3 年"], ["all", "全部"]].map(([value, label]) => <button key={value} disabled={market ? !marketSeries : !snapshot} aria-pressed={range.preset === value} onClick={() => setRange({ preset: value })}>{label}</button>)}</div>
          <div className="m-chart-actions">{!market && <label>副图 <select aria-label="指数K线副图" value={activity} onChange={event => setActivity(event.target.value as ActivityField)}><option value="amount">成交额</option><option value="volume">成交量 VOL</option></select></label>}<MovingAverageSettings market={market} marketLabel={marketLabel} activity={activity} frequency={frequency} series={series} selected={maPeriods}
            activitySeries={quantitySeries} activitySelected={selectedActivityMA} onActivitySelect={period => {
              const key = market ? "market" : activity;
              setActivityMA(previous => ({ ...previous, [key]: previous[key].includes(period) ? previous[key].filter(item => item !== period) : MA_PERIODS.filter(item => item === period || previous[key].includes(item)) }));
            }} onSelect={period => setMaPeriods(previous => previous.includes(period) ? previous.filter(item => item !== period) : MA_PERIODS.filter(item => item === period || previous.includes(item)))} /></div></div>
        {row?.stale && snapshot && <p className="m-warning">当前显示上次成功读取的快照；连接或读取完成前不代表最新数据。</p>}
        {!market && snapshot && (series || frequency === "daily") ? <PriceChart key={`${snapshot.snapshot_id}-${frequency}`} snapshot={snapshot} series={series} frequency={frequency} maPeriods={maPeriods} theme={theme} range={range} onRange={setRange} cursor={cursor} onCursor={setCursor} />
          : market ? null : <div className="m-empty" role="status"><strong>{row?.loading ? "正在读取…" : row?.error && !row.empty ? "价格读取失败" : "暂无数据"}</strong><p>{row?.calculationError ? `${FREQUENCY_LABELS[frequency]}K暂无数据：${row.calculationError}；可选择日K查看原始价格。` : row?.error ?? "请配置指数连接并读取已保存的价格。"}</p></div>}
        {quantitySeries ? <ActivityChart key={`${bundle!.snapshot.activity_id}-${market ? "daily" : frequency}-${activity}`} series={quantitySeries} price={market ? undefined : series} snapshot={market ? undefined : snapshot}
          maPeriods={selectedActivityMA} theme={theme} range={range} onRange={setRange} cursor={cursor} onCursor={setCursor} market={market} marketLabel={marketLabel} />
          : <div className={`m-activity-empty ${market ? "m-empty" : ""}`} role="status"><span>{market ? marketLabel + " · 亿元" : activity === "volume" ? "指数成交量 VOL · 万股" : "指数成交额 · 亿元"}</span><strong>暂无数据</strong><span>量额：{quantityError}</span></div>}
        <p className="m-muted m-activity-provenance">{market && "三市同日齐全才合计；北交所使用官方股票日报主记录，交易方式细分范围尚未完全核实。"}量额未经双源核验 · 来源：{activitySources} · 数据截至：{bundle?.snapshot.window.end ?? "暂无数据"}。
          未准入、缺日或缺市场显示“暂无数据”；更新仅按受控服务配置执行。</p>
        {notes && <aside className="m-notes"><h3>数据说明</h3><p>当前获取的历史版本，非当时可知回放。所有金融结果由可信本地服务提供；最新单日涨跌沿用发布时固化摘要，其余价格结果在读取时基于同一快照计算。</p>
          <p>价格均线按所选日／周／月K计数，周期未结束的结果会变化；不足样本明确缺失。量额合计、涨跌与均线均来自服务端，同一来源精度不混用。缺失不补零、不使用示例行情。</p>
          {snapshot && <><p>快照：{snapshot.snapshot_id}<br />观察：{snapshot.observation_id}</p><p>最新涨跌公式：{snapshot.summary.formula_version}</p>
            {row?.calculations && <p>计算版本：{row.calculations.formula_version}<br />计算输入快照：{row.calculations.snapshot_id}</p>}
            {snapshot.evidence.map(item => <p key={item.object_id}>{sources[item.source] ?? item.source} · {item.url}</p>)}</>}
          {market && <p>统计范围：{marketScope}；上交所主板A股和科创板、深交所主板A股和创业板；三市额外包含北交所股票日报。来源原值刻度分别保留，沪深分项精度0.01亿元、北交所0.01元。G1—G4按已验证范围保留。</p>}
          <ActivityDetails id={activityId} descriptor={quantity.descriptor} bundle={bundle} error={quantityError} anchor={market ? bundle?.snapshot.anchor_date ?? quantity.anchor : snapshot?.window.anchor_date} />
          <p>可见高低点直接选取当前快照已有价格及日期。均线日／周／月按各自周期计算，三年不足的长周期档位将禁用，不扩取历史。</p></aside>}
      </section>
      <footer className="m-footer"><span>数据来源：{market ? activitySources : snapshot ? snapshot.evidence.map(item => sources[item.source] ?? item.source).join(" / ") : "暂无数据"} · 本地保存</span><a href="/third-party-licenses.txt" target="_blank" rel="noreferrer">第三方许可</a><span>THE WOLF / MARKET RESEARCH</span></footer>
    </main>
  </div>;
}
