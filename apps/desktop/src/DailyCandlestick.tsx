import { useMemo, useState } from "react";
import type { IndexBar } from "./indexTypes";
import { candleGeometry, panRange, zoomRange } from "./candlestickGeometry";

/** 固定快照日K线；预期日期保留缺口，选择和范围控制具有键盘等效入口。 */
export function DailyCandlestick({ bars, expectedDates, onSelect, onEvidence }: {
  bars: IndexBar[]; expectedDates: string[]; onSelect: (day: string) => void; onEvidence: (day: string) => void;
}) {
  const [startDate, setStartDate] = useState(expectedDates[0]);
  const [endDate, setEndDate] = useState(expectedDates.at(-1)!);
  const [filter, setFilter] = useState({ start: expectedDates[0], end: expectedDates.at(-1)! });
  const filtered = useMemo(() => expectedDates.filter(day => day >= filter.start && day <= filter.end), [expectedDates, filter]);
  const [range, setRange] = useState({ start: Math.max(0, expectedDates.length - 60), count: Math.min(60, expectedDates.length) });
  const [selected, setSelected] = useState(expectedDates.at(-1)!);
  const [error, setError] = useState<string>();
  const byDay = new Map(bars.map(bar => [bar.trade_date, bar]));
  const visible = filtered.slice(range.start, range.start + range.count);
  const values = visible.flatMap(day => { const bar = byDay.get(day); return bar ? [Number(bar.high), Number(bar.low)] : []; });
  const max = Math.max(...values), min = Math.min(...values);
  const chosen = byDay.get(selected);
  function select(day: string) { setSelected(day); onSelect(day); }
  function apply(start: string, end: string, recent = false) {
    const validDate = (day: string) => /^\d{4}-\d{2}-\d{2}$/.test(day) && !Number.isNaN(Date.parse(day))
      && new Date(day).toISOString().slice(0, 10) === day;
    if (!validDate(start) || !validDate(end) || start > end) { setError("日期范围无效，请输入有序的起止日期。"); return; }
    const next = expectedDates.filter(day => day >= start && day <= end);
    setFilter({ start, end }); setError(undefined);
    setRange({ start: recent ? Math.max(0, next.length - 60) : 0, count: recent ? Math.min(60, next.length) : next.length });
    if (next.length) select(next.at(-1)!);
    else onSelect("");
  }
  function zoom(factor: number) { setRange(zoomRange(range, filtered.length, Math.max(0, filtered.indexOf(selected)), factor)); }
  function pan(direction: number) {
    const next = panRange(range, filtered.length, direction); setRange(next);
    if (next.count) select(filtered[direction < 0 ? next.start : next.start + next.count - 1]);
  }
  function keyboard(key: string): boolean {
    const current = visible.indexOf(selected);
    const next = key === "Home" ? 0 : key === "End" ? visible.length - 1
      : key === "ArrowLeft" ? Math.max(0, current - 1) : key === "ArrowRight" ? Math.min(visible.length - 1, current + 1) : -1;
    if (next < 0 || !visible.length) return false;
    select(visible[next]); return true;
  }
  const gap = visible.filter(day => !byDay.has(day));
  return <section className="card chart-card" aria-label="沪深300日K线">
    <h2>日K线</h2>
    <form className="chart-actions" onSubmit={event => { event.preventDefault(); apply(startDate, endDate); }}>
      <label>起始日期<input type="date" value={startDate} onChange={event => setStartDate(event.target.value)} /></label>
      <label>结束日期<input type="date" value={endDate} onChange={event => setEndDate(event.target.value)} /></label>
      <button type="submit">应用</button>
    </form>
    <div className="chart-actions">
      <button onClick={() => { setStartDate(expectedDates[0]); setEndDate(expectedDates.at(-1)!); apply(expectedDates[0], expectedDates.at(-1)!, true); }}>最近60日</button>
      <button onClick={() => { setStartDate(expectedDates[0]); setEndDate(expectedDates.at(-1)!); apply(expectedDates[0], expectedDates.at(-1)!); }}>全部260日</button>
      <button disabled={!visible.length} onClick={() => zoom(1.5)}>缩小</button>
      <button disabled={!visible.length} onClick={() => zoom(1 / 1.5)}>放大</button>
      <button disabled={!visible.length || range.start === 0} onClick={() => pan(-1)}>向左平移</button>
      <button disabled={!visible.length || range.start + range.count >= filtered.length} onClick={() => pan(1)}>向右平移</button>
    </div>
    {error && <p role="alert" className="warning">{error} 保留上次有效视图。</p>}
    <p className="note">当前可见：{visible.length ? `${visible[0]} 至 ${visible.at(-1)} · ${visible.length}日` : "空范围，无交集"} · 单位：点</p>
    {gap.length > 0 && <p className="warning">缺失交易日：{gap.join("、")}，保留空位。</p>}
    {values.length > 0 && <p className="note">图内最高 {max.toFixed(2)} · 最低 {min.toFixed(2)} 点</p>}
    {visible.length > 0 && values.length > 0 && <svg viewBox="0 0 800 280" tabIndex={0} role="group" aria-label="日K线，左右键选日，Home和End到可见首尾，Tab离开"
      onKeyDown={event => { if (keyboard(event.key)) event.preventDefault(); }}>
      <line x1="48" x2="776" y1="238" y2="238" stroke="#263a5d" />
      {visible.map((day, index) => {
        const bar = byDay.get(day); if (!bar) return null;
        const geometry = candleGeometry(bar, index, visible.length, min, max);
        return <g key={day} onMouseEnter={() => select(day)} onClick={() => select(day)}>
          <title>{`${day} 开${bar.open} 高${bar.high} 低${bar.low} 收${bar.close} 点`}</title>
          <rect x={geometry.x - 360 / visible.length} y="18" width={720 / visible.length} height="222" fill={selected === day ? "#263a5d" : "transparent"} />
          <line x1={geometry.x} x2={geometry.x} y1={geometry.high} y2={geometry.low} stroke={geometry.color} />
          {geometry.height === 0 ? <line x1={geometry.x - geometry.width / 2} x2={geometry.x + geometry.width / 2} y1={geometry.top} y2={geometry.top} stroke={geometry.color} strokeWidth="2" />
            : <rect x={geometry.x - geometry.width / 2} y={geometry.top} width={geometry.width} height={Math.max(.5, geometry.height)} fill={geometry.color} />}
        </g>;
      })}
    </svg>}
    {chosen && visible.includes(selected) && <div className="selected-day">
      <p aria-live="polite">选中 {selected} · 开 {chosen.open} · 高 {chosen.high} · 低 {chosen.low} · 收 {chosen.close} 点</p>
      <button onClick={() => onEvidence(selected)}>查看该日依据</button>
    </div>}
    <p className="note">红：收高于开；绿：收低于开；平盘：横线。摘要涨跌幅按前交易日收盘计算。</p>
  </section>;
}
