import { useEffect, useMemo, useRef, useState } from "react";
import { init, use, type EChartsType } from "echarts/core";
import { CandlestickChart, LineChart, BarChart } from "echarts/charts";
import { GridComponent, AxisPointerComponent, DataZoomComponent, MarkPointComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { FREQUENCY_LABELS, MA_PERIODS, INCOMPLETE_REASONS, RESULT_REASONS, percentDisplay, type ChartBar, type CalculationSeries, type Frequency } from "./indexCalculationTypes";
import { monthsBefore, validDay, visibleExtrema, comparePrice, trendBars, type SeriesBar } from "./indexSeriesTypes";

import { activityText, activityPlotValue, activityUnit, activityReason, type ActivitySeries, type ActivityField } from "./activityTypes";

import type { PriceRange, DateRange } from "./storedViews";
import { priceText } from "./overviewPriceText";

// 只注册本批实际使用的本地绘图模块，不接收外部option、图片或HTML提示。
use([CandlestickChart, LineChart, BarChart, GridComponent, AxisPointerComponent, DataZoomComponent, MarkPointComponent, CanvasRenderer]);
export type Theme = "light" | "dark";
export type ChartWindow = { preset: string; start?: string; end?: string };
const colors = {
  light: { text: "#626c7b", line: "#e3e7ed", accent: "#3a4f8c", up: "#c43d4a", down: "#16784a", flat: "#6b7380", surface: "#fff" },
  dark: { text: "#a5b2c2", line: "#2d3948", accent: "#5aa9e6", up: "#f0625a", down: "#34c38f", flat: "#9aa3b0", surface: "#161c24" },
};

/** 原始收盘点的微型折线；不在浏览器生成区间收益。 */
export function MiniTrend({ bars: rawBars, observation, theme }: { bars: Pick<SeriesBar, "trade_date" | "close">[]; observation: string; theme: Theme }) {
  const bars = useMemo(() => trendBars(rawBars, observation), [rawBars, observation]);
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const chart = init(host.current!, undefined, { renderer: "canvas" });
    chart.setOption({ animation: false, grid: { top: 3, bottom: 3, left: 2, right: 2 },
      xAxis: { type: "category", show: false, data: bars.map(bar => bar.trade_date) },
      yAxis: { type: "value", show: false, scale: true },
      series: [{ type: "line", data: bars.map(bar => Number(bar.close)), showSymbol: false, silent: true,
        lineStyle: { color: colors[theme].accent, width: 1.4 } }] });
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(host.current!);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [bars, theme]);
  return <div className="m-spark" ref={host} role="img" aria-label={`原始收盘走势：${bars[0].trade_date}至${bars.at(-1)!.trade_date}`} />;
}

function bounds(bars: { start: string; trade_date: string }[], range: ChartWindow): [number, number] {
  const endDay = range.preset === "custom" ? range.end! : bars.at(-1)!.trade_date;
  const startDay = range.preset === "custom" ? range.start!
    : range.preset === "all" ? bars[0].start : monthsBefore(endDay, Number(range.preset));
  const first = bars.findIndex(bar => bar.trade_date >= startDay);
  let end = bars.length - 1;
  while (end > 0 && bars[end].start > endDay) end--;
  return [Math.max(0, Math.min(first < 0 ? end : first, end)), end];
}

function marks(bars: ChartBar[], start: number, end: number) {
  const { high, low } = visibleExtrema(bars, start, end);
  const align = (bar: ChartBar) => {
    const position = bars.indexOf(bar);
    return position <= start + (end - start) * .15 ? "left" : position >= end - (end - start) * .15 ? "right" : "center";
  };
  return { symbol: "circle", symbolSize: 4, animation: false, data: [
    { coord: [high.trade_date, Number(high.high)], label: { formatter: `最高 ${priceText(high.high)}`, position: "top", align: align(high) }, name: high.trade_date },
    { coord: [low.trade_date, Number(low.low)], label: { formatter: `最低 ${priceText(low.low)}`, position: "bottom", align: align(low) }, name: low.trade_date },
  ] };
}

/** 固定快照与周期的服务端结果；滑动条使用完整日期导航，数值仅包含当前范围与所选均线。 */
function PriceChartContent({ snapshot, series, frequency, maPeriods, theme, range, onRange, cursor, onCursor }: {
  snapshot: PriceRange; series: CalculationSeries; frequency: Frequency; maPeriods: number[]; theme: Theme; range: ChartWindow; onRange: (value: ChartWindow) => void; cursor?: string; onCursor: (value: string) => void;
}) {
  const bars: ChartBar[] = useMemo(() => series.rows.map(row => ({ trade_date: row.end, start: row.start,
    open: row.open, high: row.high, low: row.low, close: row.close, calculation: row })), [series]);
  const navigation = useMemo(() => snapshot.navigation_periods.map(period => ({ start: period.start, trade_date: period.end })), [snapshot.navigation_periods]);
  const byDate = useMemo(() => new Map(bars.map(bar => [bar.trade_date, bar])), [bars]);
  const periodLabel = FREQUENCY_LABELS[frequency];
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsType | undefined>(undefined);
  const callback = useRef(onRange); callback.current = onRange;
  const cursorCallback = useRef(onCursor); cursorCallback.current = onCursor;
  const rangeRef = useRef(range); rangeRef.current = range;
  const suppress = useRef(false);
  const zoomTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancelZoom = () => { if (zoomTimer.current !== undefined) clearTimeout(zoomTimer.current); zoomTimer.current = undefined; };
  const [visible, setVisible] = useState<[number, number]>(() => bounds(bars, range));
  const visibleRef = useRef(visible); visibleRef.current = visible;
  const [selected, setSelected] = useState(bars.length - 1);
  const selectedRef = useRef(selected); selectedRef.current = selected;
  const [startDate, setStartDate] = useState(bars[visible[0]].start);
  const [endDate, setEndDate] = useState(bars[visible[1]].trade_date);
  const [error, setError] = useState<string>();

  useEffect(() => {
    const c = colors[theme];
    const chart = init(host.current!, undefined, { renderer: "canvas" }); chartRef.current = chart;
    const [start, end] = bounds(navigation, rangeRef.current);
    const [visibleStart, visibleEnd] = bounds(bars, rangeRef.current);
    chart.setOption({ animation: false, backgroundColor: c.surface,
      grid: { top: 30, bottom: 65, left: 12, right: 84 },
      xAxis: { type: "category", data: navigation.map(bar => bar.trade_date), boundaryGap: true,
        axisLine: { lineStyle: { color: c.line } }, axisLabel: { color: c.text, hideOverlap: true, alignMinLabel: "left", alignMaxLabel: "right" }, axisTick: { show: false } },
      yAxis: { type: "value", position: "right", scale: true, minInterval: 0.01, axisLabel: { color: c.text, formatter: (value: number) => value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }, splitLine: { lineStyle: { color: c.line, type: "dashed" } } },
      // 读数由React显示；直接使用十字指针，避免隐藏富文本tooltip仍定位空内容。
      axisPointer: { show: true, triggerTooltip: false, type: "line", label: { show: false } },
      dataZoom: [{ type: "inside", startValue: start, endValue: end, filterMode: "filter", minValueSpan: 0, throttle: 0 },
        { type: "slider", startValue: start, endValue: end, filterMode: "filter", throttle: 0, bottom: 4, height: 22,
          showDetail: false, showDataShadow: false, borderColor: c.line, fillerColor: theme === "dark" ? "#35536e66" : "#c8d1e466" }],
      series: [{ id: "price", type: "candlestick", barMaxWidth: 12,
        data: navigation.map(period => { const bar = byDate.get(period.trade_date); return bar
          ? { value: [bar.open, bar.close, bar.low, bar.high].map(Number),
              ...(bar.close === bar.open ? { itemStyle: { color: c.flat, borderColor: c.flat, color0: c.flat, borderColor0: c.flat } } : {}) }
          : { value: [null, null, null, null] }; }),
        itemStyle: { color: c.up, color0: c.down, borderColor: c.up, borderColor0: c.down },
        markPoint: { ...marks(bars, visibleStart, visibleEnd), itemStyle: { color: c.text }, label: { color: c.text, fontSize: 11 } } }],
    });
    chart.on("datazoom", () => {
      if (suppress.current) return;
      const zoom = (chart.getOption() as { dataZoom?: { startValue?: number; endValue?: number }[] }).dataZoom?.[0];
      if (!Number.isFinite(zoom?.startValue) || !Number.isFinite(zoom?.endValue)) return;
      const first = Math.max(0, Math.min(navigation.length - 1, Math.round(zoom!.startValue!)));
      const last = Math.max(first, Math.min(navigation.length - 1, Math.round(zoom!.endValue!)));
      cancelZoom();
      zoomTimer.current = setTimeout(() => callback.current({ preset: "custom", start: navigation[first].start, end: navigation[last].trade_date }), 120);
    });
    chart.on("updateAxisPointer", (event: unknown) => {
      const value = (event as { axesInfo?: { axisDim?: string; value?: unknown }[] }).axesInfo?.find(axis => axis.axisDim === "x")?.value;
      const index = bars.findIndex(bar => bar.trade_date === (typeof value === "number" ? navigation[value]?.trade_date : value));
      if (Number.isInteger(index) && index >= visibleRef.current[0] && index <= visibleRef.current[1]) { setSelected(index); cursorCallback.current(bars[index].trade_date); }
    });
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(host.current!);
    return () => { cancelZoom(); observer.disconnect(); chart.dispose(); chartRef.current = undefined; };
  }, [bars, navigation, byDate, theme]);

  useEffect(() => {
    const [start, end] = bounds(bars, range);
    setVisible([start, end]); setStartDate(bars[start].start); setEndDate(bars[end].trade_date); setError(undefined);
    const next = Math.max(start, Math.min(end, selectedRef.current));
    setSelected(next); cursorCallback.current(bars[next].trade_date);
    suppress.current = true;
    const [axisStart, axisEnd] = bounds(navigation, range);
    chartRef.current?.dispatchAction({ type: "dataZoom", startValue: axisStart, endValue: axisEnd });
    chartRef.current?.setOption({ series: [{ id: "price", markPoint: marks(bars, start, end) }] });
    suppress.current = false;
  }, [bars, navigation, range, theme]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const style = getComputedStyle(host.current!);
    // 保留每档稳定ID，取消勾选用空序列清除；不重建图表或改变可见区间。
    suppress.current = true;
    chart.setOption({ series: MA_PERIODS.map(period => ({ id: `ma-${period}`, name: `MA${period}`, type: "line",
      data: maPeriods.includes(period) ? navigation.map(point => {
        const value = byDate.get(point.trade_date)?.calculation?.ma.find(item => item.parameters.period === String(period))?.value;
        return value == null ? null : Number(value);
      }) : [], showSymbol: false, connectNulls: false, silent: true,
      lineStyle: { width: 1.2, color: style.getPropertyValue(`--ma${period}`).trim() } })) });
    suppress.current = false;
  }, [bars, navigation, byDate, maPeriods, theme]);

  useEffect(() => {
    const index = bars.findIndex(bar => bar.trade_date === cursor);
    if (index >= visible[0] && index <= visible[1]) setSelected(index);
  }, [cursor, bars, visible]);

  function applyDates() {
    cancelZoom();
    if (!validDay(startDate) || !validDay(endDate) || startDate > endDate || startDate < snapshot.source_coverage.start
        || endDate > snapshot.source_coverage.end) {
      setError("请选择已保存范围内的有效起止日期。"); return;
    }
    onRange({ preset: "custom", start: startDate, end: endDate });
  }
  const bar = bars[selected];
  const extrema = visibleExtrema(bars, visible[0], visible[1]);
  const pct = bar.calculation ? bar.calculation.change_pct.value
    : null;
  const missingReason = bar.calculation?.change_pct.reason;
  const incomplete = bar.calculation?.incomplete_reasons ?? [];
  const incompleteCount = bars.slice(visible[0], visible[1] + 1).filter(item => item.calculation && !item.calculation.complete).length;
  return <>
    <div className="m-readout" id="overview-readout" aria-live="polite"><strong>{bar.trade_date}</strong>
      <span>开 <b>{priceText(bar.open)}</b></span><span>高 <b>{priceText(bar.high)}</b></span><span>低 <b>{priceText(bar.low)}</b></span><span>收 <b>{priceText(bar.close)}</b></span>
      <span title={missingReason ? RESULT_REASONS[missingReason] : undefined}>涨跌 {pct === null ? "暂无数据" : <b className={percentDisplay(pct).className}>{percentDisplay(pct).text}</b>}</span><span className="m-muted">单位：点</span></div>
    {frequency !== "daily" && bar.calculation && <p className="m-period-readout">{periodLabel}K：{bar.calculation.period_start} 至 {bar.calculation.period_end} · 已有交易日 {bar.start} 至 {bar.trade_date}
      {incomplete.length > 0 && <strong className="m-incomplete">未完整：{incomplete.map(reason => INCOMPLETE_REASONS[reason]).join("、")}</strong>}</p>}
    <div className="m-ma-readout" aria-label={`价格${periodLabel}均线读数`}>{maPeriods.map(period => {
      const result = bar.calculation?.ma.find(item => item.parameters.period === String(period));
      const reason = result?.reason ? RESULT_REASONS[result.reason] : "计算结果未取得";
      return <span key={period} style={{ color: `var(--ma${period})` }}>MA{period} <b>{priceText(result?.value)}</b>{result?.value == null && <small>（{reason}）</small>}</span>;
    })}</div>
    <div ref={host} className="m-price-chart" tabIndex={0} role="region" aria-label={`${periodLabel}K图表`} aria-describedby="overview-readout overview-chart-help"
      onKeyDown={event => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? visible[0] : event.key === "End" ? visible[1]
          : Math.max(visible[0], Math.min(visible[1], selected + (event.key === "ArrowRight" ? 1 : -1)));
        setSelected(next); onCursor(bars[next].trade_date); chartRef.current?.dispatchAction({ type: "updateAxisPointer", seriesIndex: 0, dataIndex: navigation.findIndex(point => point.trade_date === bars[next].trade_date) });
      }} />
    <div className="m-extrema" aria-label="可见区间高低点">可见最高 {priceText(extrema.high.high)}（{extrema.high.trade_date}）
      <span>可见最低 {priceText(extrema.low.low)}（{extrema.low.trade_date}）</span></div>
    <div className="m-chart-bottom"><p id="overview-chart-help">滚轮缩放 · 拖动底部选区 · ← → 逐根查看 · Home / End 首尾</p>
      <div className="m-date-range"><label>区间 <input type="date" aria-label="显示区间开始日期" value={startDate} min={snapshot.source_coverage.start} max={snapshot.source_coverage.end} onChange={event => { cancelZoom(); setStartDate(event.target.value); }} /></label>
        <span>—</span><input type="date" aria-label="显示区间结束日期" value={endDate} min={snapshot.source_coverage.start} max={snapshot.source_coverage.end} onChange={event => { cancelZoom(); setEndDate(event.target.value); }} />
        <button onClick={applyDates}>应用</button></div></div>
    {error && <p className="m-warning" role="alert">{error}</p>}
    <p className="m-muted">已保存 {snapshot.source_coverage.start} 至 {snapshot.source_coverage.end} · 本次返回 {bars.length} 根{periodLabel}K。{series ? "涨跌与均线由同一快照计算结果提供。" : "历史涨跌与均线暂无数据。"}{frequency !== "daily" && ` 范围包含相交的整根${periodLabel}K；日期标签为末交易日，可见${incompleteCount}根未完整周期。`}</p>
  </>;
}


const plotActivity = activityPlotValue;

/** 全市场迷你走势裁剪同一已取得日序列；缺失处断开，不压缩交易日。 */
export function ActivityTrend({ series, observation, theme }: { series: ActivitySeries; observation: string; theme: Theme }) {
  const host = useRef<HTMLDivElement>(null);
  const rows = useMemo(() => {
    if (observation !== "1y") return series.rows.slice(-Number(observation) - 1);
    const cutoff = monthsBefore(series.rows.at(-1)!.end, 12);
    let first = 0;
    for (let i = 0; i < series.rows.length && series.rows[i].end <= cutoff; i++) first = i;
    return series.rows.slice(first);
  }, [series, observation]);
  useEffect(() => {
    if (!host.current) return;
    const chart = init(host.current!, undefined, { renderer: "canvas" });
    chart.setOption({ animation: false, grid: { top: 3, bottom: 3, left: 2, right: 2 }, xAxis: { type: "category", show: false, data: rows.map(row => row.end) },
      yAxis: { type: "value", show: false, scale: true }, series: [{ type: "line", connectNulls: false, showSymbol: false, silent: true,
        data: rows.map(row => plotActivity(row.total.value, "amount")), lineStyle: { color: colors[theme].accent, width: 1.4 } }] });
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(host.current!);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [rows, theme]);
  if (rows.every(row => row.total.value === null)) return <span className="m-missing" title="可见观察窗口没有有效成交额">暂无数据</span>;
  return <div ref={host} className="m-spark" role="img" aria-label={`市场成交额走势：${rows[0].end}至${rows.at(-1)!.end}；缺失处断开`} />;
}

/** 量额副图及全市场日图：仅绘制服务端结果，与K线共享可见日期及游标。 */
function ActivityChartContent({ series, price, sourceCoverage, navigationPeriods, maPeriods, theme, range, onRange, cursor, onCursor, market, marketLabel = "沪深北三市合计" }: {
  series: ActivitySeries; price?: CalculationSeries; sourceCoverage?: DateRange; navigationPeriods: DateRange[]; maPeriods: number[]; theme: Theme; range: ChartWindow;
  onRange: (value: ChartWindow) => void; cursor?: string; onCursor: (value: string) => void; market: boolean; marketLabel?: string;
}) {
  const rows = series.rows;
  const bars = useMemo(() => rows.map(row => ({ start: row.start, trade_date: row.end })), [rows]);
  const navigation = useMemo(() => navigationPeriods.map(period => ({ start: period.start, trade_date: period.end })), [navigationPeriods]);
  const rowByDate = useMemo(() => new Map(rows.map(row => [row.end, row])), [rows]);
  const [first, last] = bounds(bars, range);
  const cursorIndex = rows.findIndex(row => row.end === cursor);
  const selected = cursorIndex >= first && cursorIndex <= last ? cursorIndex : last;
  const row = rows[selected];
  const host = useRef<HTMLDivElement>(null), chartRef = useRef<EChartsType | undefined>(undefined);
  const callbacks = useRef({ onRange, onCursor }); callbacks.current = { onRange, onCursor };
  const windowRef = useRef({ first, last }); windowRef.current = { first, last };
  const suppress = useRef(false);
  const zoomTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancelZoom = () => { if (zoomTimer.current !== undefined) clearTimeout(zoomTimer.current); zoomTimer.current = undefined; };
  const rangeRef = useRef(range); rangeRef.current = range;
  const [startDate, setStartDate] = useState(bars[first].start), [endDate, setEndDate] = useState(bars[last].trade_date);
  const [error, setError] = useState<string>();
  useEffect(() => {
    const c = colors[theme];
    const chart = init(host.current!, undefined, { renderer: "canvas" }); chartRef.current = chart;
    const [start, end] = bounds(navigation, rangeRef.current);
    const priceRows = price?.rows;
    const byDate = new Map(priceRows?.map(bar => [bar.end, bar]));
    chart.setOption({ animation: false, backgroundColor: c.surface, grid: { top: 20, bottom: 55, left: 12, right: 68 },
      xAxis: { type: "category", data: navigation.map(item => item.trade_date), axisLabel: { color: c.text, hideOverlap: true }, axisLine: { lineStyle: { color: c.line } } },
      yAxis: { type: "value", position: "right", ...(series.field === "amount" ? { minInterval: 1 } : {}), axisLabel: { color: c.text,
        ...(series.field === "amount" ? { formatter: (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 0 }) } : {}) },
        splitLine: { lineStyle: { color: c.line, type: "dashed" } } },
      axisPointer: { show: true, triggerTooltip: false, type: "line", label: { show: false } },
      dataZoom: [{ type: "inside", startValue: start, endValue: end, minValueSpan: 0, throttle: 0 },
        { type: "slider", startValue: start, endValue: end, bottom: 4, height: 20, showDetail: false, showDataShadow: false }],
      series: [{ id: "activity", type: "bar", barMaxWidth: 12, data: navigation.map(point => {
        const item = rowByDate.get(point.trade_date);
        if (!item) return { value: null };
        const bar = byDate.get(item.end);
        const color = bar ? comparePrice(bar.close, bar.open) > 0 ? c.up : comparePrice(bar.close, bar.open) < 0 ? c.down : c.flat : c.flat;
        return { value: plotActivity(item.total.value, series.field), itemStyle: { color } };
      }) }],
    });
    chart.on("datazoom", () => {
      if (suppress.current) return;
      const zoom = (chart.getOption() as { dataZoom?: { startValue?: number; endValue?: number }[] }).dataZoom?.[0];
      if (!Number.isFinite(zoom?.startValue) || !Number.isFinite(zoom?.endValue)) return;
      const start = Math.max(0, Math.min(navigation.length - 1, Math.round(zoom!.startValue!)));
      const end = Math.max(start, Math.min(navigation.length - 1, Math.round(zoom!.endValue!)));
      cancelZoom();
      zoomTimer.current = setTimeout(() => callbacks.current.onRange({ preset: "custom", start: navigation[start].start, end: navigation[end].trade_date }), 120);
    });
    chart.on("updateAxisPointer", (event: unknown) => {
      const value = (event as { axesInfo?: { axisDim?: string; value?: unknown }[] }).axesInfo?.find(axis => axis.axisDim === "x")?.value;
      const index = rows.findIndex(item => item.end === (typeof value === "number" ? navigation[value]?.trade_date : value));
      if (Number.isInteger(index) && index >= windowRef.current.first && index <= windowRef.current.last) callbacks.current.onCursor(rows[index].end);
    });
    const observer = new ResizeObserver(() => chart.resize()); observer.observe(host.current!);
    return () => { cancelZoom(); observer.disconnect(); chart.dispose(); chartRef.current = undefined; };
  }, [rows, bars, navigation, rowByDate, series.field, price, theme]);
  useEffect(() => {
    suppress.current = true;
    const [axisStart, axisEnd] = bounds(navigation, rangeRef.current);
    chartRef.current?.dispatchAction({ type: "dataZoom", startValue: axisStart, endValue: axisEnd });
    const style = getComputedStyle(host.current!);
    chartRef.current?.setOption({ series: MA_PERIODS.map(period => ({ id: `activity-ma-${period}`, type: "line", showSymbol: false, silent: true, connectNulls: false,
      data: maPeriods.includes(period) ? navigation.map(point => { const item = rowByDate.get(point.trade_date); return item ? plotActivity(item.ma.find(value => value.parameters.period === String(period))!.value, series.field) : null; }) : [],
      lineStyle: { color: style.getPropertyValue(`--ma${period}`).trim(), width: 1.2 } })) });
    suppress.current = false;
    setStartDate(bars[first].start); setEndDate(bars[last].trade_date); setError(undefined);
  }, [first, last, bars, rows, navigation, rowByDate, maPeriods, series.field, theme, price]);
  const label = market ? marketLabel : series.field === "volume" ? "指数成交量 VOL" : "指数成交额";
  return <div className="m-activity-panel">
    <div className="m-readout" aria-live="polite" aria-label="量额读数"><strong>{row.end}</strong><span>{label} · {FREQUENCY_LABELS[series.frequency]}频</span>
      <b>{activityText(row.total.value, series.field)}</b><span>{activityUnit(series.field)}</span>
      {row.total.value === null && <span>{activityReason(row.total.reason)}</span>}
      {!row.total.complete && <strong className="m-incomplete">未完整：{row.total.incomplete_reasons.map(activityReason).join("、")}</strong>}
    </div>
    <div className="m-ma-readout" aria-label="量额均线读数">{maPeriods.map(period => {
      const scalar = row.ma.find(item => item.parameters.period === String(period))!;
      return <span key={period} style={{ color: `var(--ma${period})` }}>MA{period} <b>{activityText(scalar.value, series.field)}</b>{scalar.value === null && <small>（{activityReason(scalar.reason)}）</small>}{!scalar.complete && <small>（未完整）</small>}</span>;
    })}</div>
    <div ref={host} className={`m-activity-chart ${market ? "m-market-chart" : ""}`} role="region" tabIndex={0} aria-label={`${label}图表`} onKeyDown={event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? first : event.key === "End" ? last : Math.max(first, Math.min(last, selected + (event.key === "ArrowRight" ? 1 : -1)));
      onCursor(rows[next].end);
      chartRef.current?.dispatchAction({ type: "updateAxisPointer", seriesIndex: 0, dataIndex: navigation.findIndex(point => point.trade_date === rows[next].end) });
    }} />
    {market && <div className="m-chart-bottom"><span>← → 逐日查看 · 滚轮缩放 · 拖动底部选区</span><div className="m-date-range">
      <input type="date" aria-label="成交额显示开始日期" value={startDate} onChange={event => { cancelZoom(); setStartDate(event.target.value); }} />—
      <input type="date" aria-label="成交额显示结束日期" value={endDate} onChange={event => { cancelZoom(); setEndDate(event.target.value); }} />
      <button onClick={() => {
        cancelZoom();
        if (!validDay(startDate) || !validDay(endDate) || startDate > endDate || startDate < (sourceCoverage?.start ?? rows[0].start) || endDate > (sourceCoverage?.end ?? rows.at(-1)!.end)) { setError("请选择已保存范围内的有效日期。"); return; }
        onRange({ preset: "custom", start: startDate, end: endDate });
      }}>应用</button></div></div>}
    {error && <p role="alert">{error}</p>}
    <p className="m-muted">{market ? `${marketLabel}独立日频合计；中性色柱不表示行情涨跌。` : "柱色跟随同周期价格开收，不表示量额自身增减。"}单位：{activityUnit(series.field)}；缺失不补零，曲线断开。本次返回{rows[0].start}至{rows.at(-1)!.end}。</p>
  </div>;
}


function EmptyRange({ coverage, range, onRange }: { coverage: DateRange; range: ChartWindow; onRange: (value: ChartWindow) => void }) {
  const [start, setStart] = useState(range.start ?? coverage.start), [end, setEnd] = useState(range.end ?? coverage.end);
  const [error, setError] = useState<string>();
  return <div className="m-empty" role="status"><p>所选范围内没有已保存的交易日。</p>
    <div className="m-date-range"><input type="date" aria-label="显示区间开始日期" value={start} min={coverage.start} max={coverage.end} onChange={event => setStart(event.target.value)} />
      <input type="date" aria-label="显示区间结束日期" value={end} min={coverage.start} max={coverage.end} onChange={event => setEnd(event.target.value)} />
      <button onClick={() => { if (!validDay(start) || !validDay(end) || start > end || start < coverage.start || end > coverage.end) { setError("请选择已保存范围内的有效日期"); return; }
        onRange({ preset: "custom", start, end }); }}>应用</button></div>{error && <p role="alert">{error}</p>}</div>;
}

export function PriceChart(props: Parameters<typeof PriceChartContent>[0]) {
  return props.series.rows.length ? <PriceChartContent {...props} /> : <EmptyRange coverage={props.snapshot.source_coverage} range={props.range} onRange={props.onRange} />;
}

export function ActivityChart(props: Parameters<typeof ActivityChartContent>[0]) {
  return props.series.rows.length ? <ActivityChartContent {...props} /> : props.sourceCoverage
    ? <EmptyRange coverage={props.sourceCoverage} range={props.range} onRange={props.onRange} /> : <p role="status">所选范围没有交易日。</p>;
}
