import { useEffect, useRef, useState, type ReactNode } from 'react';
import { init, use } from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, AxisPointerComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { Theme } from './OverviewCharts';
import { placeEtfMarkers } from './etfFlowMarkers';

use([BarChart, LineChart, GridComponent, AxisPointerComponent, CanvasRenderer]);
export type EtfChartPoint = { date: string; bar: string | null; line: string | null; readout: ReactNode };
export type EtfChartMarker = { id: string; date: string; label: string; description?: string; detail: ReactNode };
const NO_MARKERS: EtfChartMarker[] = [];

/** 仅把服务端的元/份换成亿用于坐标显示；不计算金额、累计或跨日差值。 */
export function EtfFlowChart({ points, theme, label, barLabel, lineLabel, markers = NO_MARKERS }: {
  points: EtfChartPoint[]; theme: Theme; label: string; barLabel: string; lineLabel: string;
  markers?: EtfChartMarker[];
}) {
  const host = useRef<HTMLDivElement>(null);
  const [cursor, setCursor] = useState(points.length - 1);
  const cursorRef = useRef(cursor); cursorRef.current = cursor;
  const [markerId, setMarkerId] = useState<string>();
  const located = placeEtfMarkers(points.map(point => point.date), markers);
  const selectedMarker = located.find(item => item.marker.id === markerId);
  useEffect(() => setMarkerId(undefined), [points, markers]);
  useEffect(() => {
    setCursor(points.length - 1);
    const dark = theme === 'dark';
    const color = { text: dark ? '#a5b2c2' : '#626c7b', grid: dark ? '#2d3948' : '#e3e7ed',
      line: dark ? '#5aa9e6' : '#3a4f8c', up: dark ? '#f0625a' : '#c43d4a', down: dark ? '#34c38f' : '#16784a' };
    const chart = init(host.current!, undefined, { renderer: 'canvas' });
    chart.setOption({ animation: false, grid: { top: 24, left: 52, right: 52, bottom: 30 },
      axisPointer: { show: true, triggerTooltip: false, type: 'line', label: { show: false } },
      xAxis: { type: 'category', data: points.map(p => p.date), axisTick: { show: false },
        axisLine: { lineStyle: { color: color.grid } }, axisLabel: { color: color.text, hideOverlap: true } },
      yAxis: [barLabel, lineLabel].map((name, i) => ({ type: 'value', name, scale: i === 1,
        nameTextStyle: { color: color.text, fontSize: 10 }, axisLabel: { color: color.text },
        splitLine: { show: i === 0, lineStyle: { color: color.grid, type: 'dashed' } } })),
      series: [{ type: 'bar', barMaxWidth: 12, data: points.map(p => ({ value: p.bar === null ? null : Number(p.bar) / 1e8,
        itemStyle: { color: p.bar !== null && Number(p.bar) < 0 ? color.down : color.up } })) },
      { type: 'line', yAxisIndex: 1, connectNulls: false, showSymbol: false,
        lineStyle: { width: 1.6, color: color.line }, data: points.map(p => p.line === null ? null : Number(p.line) / 1e8) }] });
    chart.on('updateAxisPointer', (event: unknown) => {
      const index = (event as { axesInfo?: { value?: unknown }[] }).axesInfo?.[0]?.value;
      if (typeof index === 'number' && Number.isInteger(index) && index >= 0 && index < points.length) setCursor(index);
    });
    const resize = new ResizeObserver(() => chart.resize()); resize.observe(host.current!);
    return () => { resize.disconnect(); chart.dispose(); };
  }, [points, theme, barLabel, lineLabel]);
  const selected = points[Math.min(cursor, points.length - 1)];
  return <><div className="etf-chart-frame"><div ref={host} className="etf-chart" role="region" tabIndex={0}
    aria-label={`${label}。左右键逐日查看，Home和End跳到首尾。`} onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? points.length - 1
        : cursorRef.current + (event.key === 'ArrowLeft' ? -1 : 1);
      setCursor(Math.max(0, Math.min(points.length - 1, next)));
    }} />{located.length > 0 && <svg className="etf-chart-marker-lines" aria-hidden="true">
      {located.map(({ marker, position }) => <g key={marker.id}>
        <line x1={`${position * 100}%`} x2={`${position * 100}%`} y1="8" y2="100%" />
        <circle cx={`${position * 100}%`} cy="5" r="3" />
      </g>)}
    </svg>}</div>
    {located.length > 0 && <div className="etf-chart-marker-list" role="group" aria-label={`${label}图上标记`}>
      <span>虚线圆点：{label}中的日期标记。选择查看依据；非交易日置于相邻交易日之间。</span>
      {located.map(({ marker, nonTrading }) => <button key={marker.id} aria-pressed={markerId === marker.id}
        title={marker.description} aria-label={`${marker.date} · ${marker.label}${nonTrading ? '（非交易日）' : ''}${marker.description ? '：' + marker.description : ''}`}
        onClick={() => setMarkerId(marker.id)}>{marker.date} · {marker.label}{nonTrading ? '（非交易日）' : ''}</button>)}
    </div>}
    {selectedMarker && <div className="etf-marker-detail" role="region" aria-label="图上标记依据" aria-live="polite">
      <strong>{selectedMarker.marker.date} · {selectedMarker.marker.label}{selectedMarker.nonTrading ? '（非交易日，不对应交易数据点）' : ''}</strong>
      {selectedMarker.marker.detail}
    </div>}
    <div className="etf-readout" aria-live="off">{selected ? <><time>{selected.date}</time>{selected.readout}</> : '暂无数据'}</div></>;
}
