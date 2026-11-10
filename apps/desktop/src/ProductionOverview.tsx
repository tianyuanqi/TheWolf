import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "./apiClient";
import { OVERVIEW_INDICES, type OverviewIndexId } from "./indexSeriesTypes";
import { MA_PERIODS, FREQUENCIES, FREQUENCY_LABELS, RESULT_REASONS, percentDisplay, type CalculationSeries, type Frequency } from "./indexCalculationTypes";
import { ActivityChart, ActivityTrend, MiniTrend, PriceChart, type ChartWindow, type Theme } from "./OverviewCharts";
import { ActivityDetails } from "./ActivityDetails";
import { LEGACY_MARKET, activityReason, activityText, type ActivityField, type ActivitySeries } from "./activityTypes";
import { priceText } from "./overviewPriceText";
import "./overview.css";
import { useStoredOverview } from "./useStoredOverview";
const DEFAULT_MA = [5, 10, 20, 30, 250];
const sources: Record<string, string> = { csindex: "中证指数", cnindex: "国证指数", eastmoney: "东方财富", sse: "上交所", szse: "深交所", bse: "北交所", "cnindex-raw": "国证指数" };
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
export function ProductionOverview({ connectionClient, connectionError, reconnect, refreshToken = 0, onUpdate, navigate }: {
  connectionClient?: ApiClient; navigate?: (page: string) => void; refreshToken?: number; onUpdate?: (target: string) => void; connectionError?: string; reconnect: () => void;
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
  const market = selected === "three-market";
  const selectedActivityMA = activityMA[market ? "market" : activity];
  const stored = useStoredOverview({ connection: connectionClient, connectionError, refreshToken, selected, range, frequency,
    ma: maPeriods, field: activity, activityMA: selectedActivityMA });
  const { rows, busy, phase: displayPhase } = stored;
  function selectMetric(id: typeof selected) { setSelected(id); }
  const marketId = LEGACY_MARKET;
  const marketLabel = "沪深北三市合计";
  const marketScope = "沪深北 A股股票";
  const row = market ? undefined : rows[selected];
  const snapshot = row?.snapshot;
  const priceRange = stored.detail.price?.snapshot_id === snapshot?.snapshot_id ? stored.detail.price : undefined;
  const series = priceRange?.series;
  const activityId = market ? marketId : selected as OverviewIndexId;
  const bundle = stored.detail.activity && (market || stored.detail.activity.price_snapshot_id === snapshot?.snapshot_id) ? stored.detail.activity : undefined;
  const quantitySeries = bundle?.series;
  const quantityError = stored.detail.loading ? "正在读取量额…" : stored.detail.activityError ?? stored.connectionNotice;
  const marketSeries = stored.market?.series;
  const activitySources = bundle ? [...new Set(bundle.sources.map(item => sources[item.source] ?? item.source))].join(" / ") : "暂无数据";
  const receiptTimes = bundle?.sources.map(item => item.completed_at).sort((a, b) => Date.parse(a) - Date.parse(b)) ?? [];
  const activityReceipt = receiptTimes.length ? (receiptTimes[0] === receiptTimes.at(-1) ? timeText(receiptTimes[0])
    : `${timeText(receiptTimes[0])} 至 ${timeText(receiptTimes.at(-1)!)}`) : "暂无数据";
  const definition = OVERVIEW_INDICES.find(item => item.id === selected);
  const snapshots = Object.values(rows).flatMap(value => value.snapshot ? [value.snapshot] : []);
  const dates = [...new Set(snapshots.map(value => value.source_coverage.end))];
  const asOf = dates.length === 1 ? `${dates[0]} 收盘` : dates.length ? "各指数截至日见列表" : "暂无数据";

  return <div className={`overview-app ${navOpen ? "m-nav-open" : ""}`} data-theme={theme}
    onKeyDown={event => { if (event.key === "Escape" && navOpen) { setNavOpen(false); navToggle.current?.focus(); } }}>
    <a href="#overview-main" className="m-skip">跳到页面内容</a>
    <aside className="m-sidebar" id="overview-navigation" aria-label="全站导航">
      <div className="m-brand"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 5l8 5 5-4 5 4 8-5-4 17-9 6-9-6zM8 13l8 10 8-10M16 23v5" /></svg><span>THE WOLF<small>个人研究工作台</small></span></div>
      <p className="m-nav-group">市场研究</p><nav aria-label="市场研究">
        <button aria-current="page" onClick={() => setNavOpen(false)}><span>↗</span>行情总览</button>
        <button disabled={!navigate} onClick={() => navigate?.("fund-flows")}><span aria-hidden="true">◇</span>大资金动向</button>
        {["量价分析", "题材概念", "个股查询", "大事新闻"].map(name => <button key={name} disabled title="尚未接入正式页面"><span>◇</span>{name}</button>)}
      </nav><div className="m-nav-bottom"><span>●</span> 本地研究工作台</div>
    </aside>
    {navOpen && <button className="m-backdrop" aria-label="关闭导航" onClick={() => setNavOpen(false)} />}
    <main className="m-main" id="overview-main" tabIndex={-1}>
      <div className="m-topbar"><div className="m-breadcrumb"><button ref={navToggle} className="m-mobile-toggle" aria-expanded={navOpen} aria-controls="overview-navigation" aria-label="展开或收起导航" onClick={() => setNavOpen(value => !value)}>☰</button>市场研究<span>/</span><strong>行情总览</strong></div>
        <div className="m-top-actions"><label><input type="checkbox" checked={notes} onChange={event => setNotes(event.target.checked)} />显示数据说明</label>
          <button aria-pressed={theme === "dark"} aria-label="深色备选主题" onClick={() => setTheme(value => value === "light" ? "dark" : "light")}>{theme === "light" ? "深色模式" : "浅色模式"}</button></div></div>
      <header className="m-heading"><div><h1>行情总览</h1><p className="m-muted">数据截至 {market ? bundle?.source_coverage.end ?? "暂无数据" : asOf} · A 股市场</p></div>
        <div className="m-update"><p>{market ? marketLabel : "所选指数"}获取时间（北京时间）<br />{market ? activityReceipt : snapshot ? timeText(snapshot.observed_at) : "暂无数据"}</p>
          <button onClick={() => onUpdate?.(market ? "activity:" + marketId : "price:" + selected)} disabled={!onUpdate}>更新数据</button></div></header>
      {stored.connectionNotice && <p role="status" className="m-startup-status">{stored.connectionNotice}</p>}
      <div className="m-connection"><p role={!busy && !displayPhase.startsWith("读取结束") ? "alert" : "status"}>{displayPhase}</p><div><button disabled={busy || !connectionClient} onClick={stored.reload}>重新读取</button><button onClick={reconnect}>重新连接</button></div></div>

      <section data-module="market-overview.01" aria-labelledby="overview-summary-title">
        <div className="m-section-line"><div className="m-section-label"><span>01</span><h2 id="overview-summary-title">市场概况</h2></div>
          <div className="m-window-control"><span>观察窗口</span><div className="m-segmented" role="group" aria-label="观察窗口">{[["5", "5 日"], ["20", "20 日"], ["60", "60 日"], ["1y", "1 年"]].map(([value, label]) => <button key={value} aria-pressed={observation === value} onClick={() => setObservation(value)}>{label}</button>)}</div></div></div>
        <div className="m-table-scroll" role="region" aria-label="行情指标表，窄屏可横向滚动" tabIndex={0}><table className="m-table"><caption className="m-sr-only">选择指标查看详情；观察窗口改变收盘走势与同快照区间涨跌。</caption>
          <thead><tr><th>指标</th><th>最新值</th><th>较前日</th><th>区间比较</th><th>走势</th></tr></thead>
          <tbody>{OVERVIEW_INDICES.map(item => {
            const current = rows[item.id], value = current?.snapshot, pct = value?.summary.daily_change_pct;
            const key = observation === "1y" ? "year_1" : `day_${observation}` as "day_5" | "day_20" | "day_60";
            const performance = current?.performance?.[key];
            const performanceReason = performance?.reason ? RESULT_REASONS[performance.reason] : "计算结果未取得";
            return <tr key={item.id} className={selected === item.id ? "selected" : ""}>
              <th scope="row"><button className="m-metric-select" aria-pressed={selected === item.id} onClick={() => selectMetric(item.id)}>{item.name}<small>{item.code}</small></button></th>
              <td>{value ? <><strong className="m-metric-value">{priceText(value.summary.close, true)}</strong><small>{value.source_coverage.end}{current?.stale ? " · 上次数据" : ""}</small></> : <Missing reason={current?.loading ? "正在读取" : current?.error ?? "尚无已保存价格"} />}</td>
              <td>{pct != null ? <span className={pct.startsWith("-") ? "m-down" : pct === "0.00" ? "m-flat" : "m-up"}>{!pct.startsWith("-") && pct !== "0.00" ? "+" : ""}{pct}%</span> : <Missing reason="缺少已发布的前日比较" />}</td>
              <td>{performance?.value != null ? <span className={percentDisplay(performance.value).className}>{percentDisplay(performance.value).text}</span>
                : <Missing reason={performanceReason} />}</td>
              <td>{value ? <MiniTrend bars={value.bars} observation={observation} theme={theme} /> : <Missing reason="尚无已保存价格" />}</td>
            </tr>;
          })}{([LEGACY_MARKET] as const).map(id => {
            const data = stored.market;
            const graph = data?.series;
            const last = graph?.rows.at(-1);
            const comparison = data?.comparisons?.[observation === "1y" ? "year_1" : `day_${observation}` as "day_5" | "day_20" | "day_60"];
            const name = marketLabel;
            return <tr key={id} className={market && marketId === id ? "selected" : ""}><th scope="row"><button className="m-metric-select" aria-pressed={market && marketId === id} onClick={() => selectMetric("three-market")}>{name}<small>{marketScope}</small></button></th>
              <td>{last?.total.value != null ? <><strong className="m-metric-value m-market-amount">{activityText(last.total.value, "amount")}</strong><small>亿元 · {last.end}</small></> : <Missing reason={activityReason(last?.total.reason) + (stored.marketError ?? "")} />}</td>
              <td>{last?.change_pct.value != null ? <span className={percentDisplay(last.change_pct.value).className}>{percentDisplay(last.change_pct.value).text}</span> : <Missing reason={activityReason(last?.change_pct.reason)} />}</td>
              <td>{comparison?.comparison.value != null ? <span className={percentDisplay(comparison.comparison.value).className}>{percentDisplay(comparison.comparison.value).text}<small>较窗口均额</small></span> : <Missing reason={activityReason(comparison?.comparison.reason)} />}</td>
              <td>{graph ? <ActivityTrend series={graph} observation={observation} theme={theme} /> : <Missing reason="缺少成交额序列" />}</td></tr>;
          })}</tbody></table></div>
        <p className="m-table-foot">点击指标查看下方详情 · 观察窗口按交易日／自然年比较 · 成交额较观察窗口均额比较，不由四指数相加</p>
        {OVERVIEW_INDICES.filter(item => rows[item.id]?.error).map(item => <p key={item.id} className="m-warning" role={rows[item.id]?.empty ? "status" : "alert"}>{item.name}：{rows[item.id]?.empty ? "暂无数据，尚未保存价格" : rows[item.id]?.error}{rows[item.id]?.snapshot ? "；保留上次成功读取的快照。" : ""}</p>)}
      </section>

      <section className="m-chart-section" data-module={market ? "market-overview.03" : "market-overview.02"} aria-labelledby="overview-detail-title">
        <header className="m-chart-heading"><div className="m-chart-title"><span>{market ? "03" : "02"}</span><h2 id="overview-detail-title">{market ? marketLabel : definition!.name}</h2><code>{market ? marketScope : definition!.code}</code></div>
          {!market && <div className="m-segmented" role="group" aria-label="K线周期">{FREQUENCIES.map(value => <button key={value} aria-pressed={frequency === value} disabled={!snapshot}
            title={!snapshot ? "尚无已保存价格" : undefined} onClick={() => setFrequency(value)}>{FREQUENCY_LABELS[value]} K</button>)}</div>}</header>
        <div className="m-chart-controls"><div className="m-range-controls" role="group" aria-label="图表显示范围"><span>显示范围</span>{[["1", "1 月"], ["3", "3 月"], ["6", "6 月"], ["12", "1 年"], ["36", "3 年"], ["all", "全部"]].map(([value, label]) => <button key={value} disabled={market ? !marketSeries : !snapshot} aria-pressed={range.preset === value} onClick={() => setRange({ preset: value })}>{label}</button>)}</div>
          <div className="m-chart-actions">{!market && <label>副图 <select aria-label="指数K线副图" value={activity} onChange={event => setActivity(event.target.value as ActivityField)}><option value="amount">成交额</option><option value="volume">成交量 VOL</option></select></label>}<MovingAverageSettings market={market} marketLabel={marketLabel} activity={activity} frequency={frequency} series={series} selected={maPeriods}
            activitySeries={quantitySeries} activitySelected={selectedActivityMA} onActivitySelect={period => {
              const key = market ? "market" : activity;
              setActivityMA(previous => ({ ...previous, [key]: previous[key].includes(period) ? previous[key].filter(item => item !== period) : MA_PERIODS.filter(item => item === period || previous[key].includes(item)) }));
            }} onSelect={period => setMaPeriods(previous => previous.includes(period) ? previous.filter(item => item !== period) : MA_PERIODS.filter(item => item === period || previous.includes(item)))} /></div></div>
        {row?.stale && snapshot && <p className="m-warning">当前显示上次成功读取的快照；连接或读取完成前不代表最新数据。</p>}
        {!market && snapshot && priceRange && series ? <PriceChart key={`${snapshot.snapshot_id}-${frequency}`} snapshot={priceRange} series={series} frequency={frequency} maPeriods={maPeriods} theme={theme} range={range} onRange={setRange} cursor={cursor} onCursor={setCursor} />
          : market ? null : <div className="m-empty" role="status"><strong>{row?.loading ? "正在读取…" : row?.error && !row.empty ? "价格读取失败" : "暂无数据"}</strong><p>{stored.detail.priceError ?? row?.error ?? "请配置指数连接并读取已保存的价格。"}</p></div>}
        {quantitySeries ? <ActivityChart key={`${bundle!.activity_id}-${market ? "daily" : frequency}-${activity}`} series={quantitySeries} price={market ? undefined : series} sourceCoverage={bundle?.source_coverage} navigationPeriods={bundle!.navigation_periods}
          maPeriods={selectedActivityMA} theme={theme} range={range} onRange={setRange} cursor={cursor} onCursor={setCursor} market={market} marketLabel={marketLabel} />
          : <div className={`m-activity-empty ${market ? "m-empty" : ""}`} role="status"><span>{market ? marketLabel + " · 亿元" : activity === "volume" ? "指数成交量 VOL · 万股" : "指数成交额 · 亿元"}</span><strong>暂无数据</strong><span>量额：{quantityError}</span></div>}
        <p className="m-muted m-activity-provenance">{market && "三市同日齐全才合计；北交所使用官方股票日报主记录，交易方式细分范围尚未完全核实。"}量额未经双源核验 · 来源：{activitySources} · 数据截至：{bundle?.source_coverage.end ?? "暂无数据"}。
          未准入、缺日或缺市场显示“暂无数据”；更新仅按受控服务配置执行。</p>
        {notes && <aside className="m-notes"><h3>数据说明</h3><p>当前获取的历史版本，非当时可知回放。所有金融结果由可信本地服务提供；最新单日涨跌沿用发布时固化摘要，其余价格结果在读取时基于同一快照计算。</p>
          <p>价格均线按所选日／周／月K计数，周期未结束的结果会变化；不足样本明确缺失。量额合计、涨跌与均线均来自服务端，同一来源精度不混用。缺失不补零、不使用示例行情。</p>
          {snapshot && <><p>快照：{snapshot.snapshot_id}<br />观察：{snapshot.observation_id}</p><p>最新涨跌公式：{snapshot.summary.formula_version}</p>
            {priceRange && <p>计算版本：{priceRange.formula_version}<br />计算输入快照：{priceRange.snapshot_id}</p>}
            {snapshot.sources.map(item => <p key={item.object_id}>{sources[item.source] ?? item.source} · {item.url}</p>)}</>}
          {market && <p>统计范围：{marketScope}；上交所主板A股和科创板、深交所主板A股和创业板；三市额外包含北交所股票日报。来源原值刻度分别保留，沪深分项精度0.01亿元、北交所0.01元。G1—G4按已验证范围保留。</p>}
          <ActivityDetails id={activityId} descriptor={stored.descriptor} view={bundle} error={quantityError} />
          <p>可见高低点直接选取当前快照已有价格及日期。均线日／周／月按各自周期计算，三年不足的长周期档位将禁用，不扩取历史。</p></aside>}
      </section>
      <footer className="m-footer"><span>数据来源：{market ? activitySources : snapshot ? snapshot.sources.map(item => sources[item.source] ?? item.source).join(" / ") : "暂无数据"} · 本地保存</span><a href="/third-party-licenses.txt" target="_blank" rel="noreferrer">第三方许可</a><span>THE WOLF / MARKET RESEARCH</span></footer>
    </main>
  </div>;
}
