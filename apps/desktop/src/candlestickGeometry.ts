import type { IndexBar } from "./indexTypes";

export type ChartRange = { start: number; count: number };

/** 缩放围绕选中日，范围最少10日，筛选不足10日时全部显示。 */
export function zoomRange(range: ChartRange, length: number, selected: number, factor: number): ChartRange {
  const count = Math.min(length, Math.max(Math.min(10, length), Math.round(range.count * factor)));
  return { count, start: Math.max(0, Math.min(length - count, selected - Math.floor(count / 2))) };
}

/** 按筛选边界平移，绝不生成窗口之外的柱。 */
export function panRange(range: ChartRange, length: number, direction: number): ChartRange {
  return { ...range, start: Math.max(0, Math.min(length - range.count, range.start + direction * Math.max(1, Math.floor(range.count / 2)))) };
}

/** Number仅用于坐标；实体方向按开收，原字符串留给选中日展示。 */
export function candleGeometry(bar: IndexBar, index: number, count: number, min: number, max: number) {
  const y = (value: string) => 24 + (max - Number(value)) / (max - min || 1) * 208;
  const open = y(bar.open), close = y(bar.close);
  return { x: 48 + (index + .5) * (720 / count), width: Math.max(1, Math.min(18, 720 / count * .65)),
    high: y(bar.high), low: y(bar.low), top: Math.min(open, close), height: Math.abs(close - open),
    color: Number(bar.close) > Number(bar.open) ? "#ff8a80" : Number(bar.close) < Number(bar.open) ? "#69d6b0" : "#c2cad8" };
}
