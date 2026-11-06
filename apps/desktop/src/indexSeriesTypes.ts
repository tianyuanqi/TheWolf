import type { components } from "../../../contracts/generated/http";
import { IndexSeriesView as validView } from "../../../contracts/generated/validators.mjs";

export const OVERVIEW_INDICES = [
  { id: "sse:000001:price", code: "000001.SH", name: "上证指数", decimals: 2, provider: "csindex" },
  { id: "szse:399001:price", code: "399001.SZ", name: "深证成指", decimals: 4, provider: "cnindex" },
  { id: "szse:399006:price", code: "399006.SZ", name: "创业板指", decimals: 4, provider: "cnindex" },
  { id: "sse:000688:price", code: "000688.SH", name: "科创50", decimals: 2, provider: "csindex" },
] as const;
export type OverviewIndexId = typeof OVERVIEW_INDICES[number]["id"];
export type SeriesSnapshot = components["schemas"]["IndexSeriesSnapshot"];
export type SeriesBar = components["schemas"]["IndexSeriesBar"];

/** 十进制价格原值的精确比较，仅用于校验与选择展示标签，不生成金融结果。 */
export function comparePrice(left: string, right: string): number {
  const scaled = (value: string) => { const [whole, fraction = ""] = value.split("."); return BigInt(whole + fraction.padEnd(4, "0")); };
  const a = scaled(left), b = scaled(right);
  return a < b ? -1 : a > b ? 1 : 0;
}

/** 日期是否合法由ISO往返验证；不在浏览器补交易日历。 */
export function validDay(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
    && new Date(value + "T00:00:00Z").toISOString().slice(0, 10) === value;
}

/** 结构之后核对指数、快照引用、精度及行归属，旧CSI包装不冒充四指数三年资料。 */
export function parseSeriesView(value: unknown, indexId: OverviewIndexId): SeriesSnapshot {
  if (!validView(value) || value.format !== "v2" || value.index_id !== indexId) throw new Error("指数视图契约或归属不符");
  const snapshot = value.snapshot;
  const definition = OVERVIEW_INDICES.find(item => item.id === indexId)!;
  const { bars, calendar_dates: dates, summary, window: range, evidence, retrieval } = snapshot;
  if (snapshot.instrument.id !== indexId || snapshot.instrument.code !== definition.code.slice(0, 6)
      || snapshot.instrument.name !== definition.name || snapshot.instrument.provider !== definition.provider
      || snapshot.storage_decimals !== definition.decimals || retrieval.index_id !== indexId
      || retrieval.snapshot_id !== snapshot.snapshot_id || bars.length !== dates.length
      || range.actual_count !== bars.length || range.expected_count !== bars.length
      || range.start !== dates[0] || range.end !== dates.at(-1)
      || range.natural_start > range.start || range.anchor_date <= range.end
      || ![range.natural_start, range.anchor_date, range.start, range.end].every(validDay)) throw new Error("指数范围、精度或快照归属不符");
  const point = new RegExp(`^[0-9]+\\.[0-9]{${definition.decimals}}$`);
  const evidenceIds = new Set(evidence.map(item => item.object_id));
  if (evidenceIds.size !== 2 || retrieval.sources.some(item => !evidenceIds.has(item.object_id))) throw new Error("指数来源引用不符");
  for (const [i, bar] of bars.entries()) {
    if (!validDay(bar.trade_date) || bar.trade_date !== dates[i] || (i > 0 && bar.trade_date <= dates[i - 1])
        || ![bar.open, bar.high, bar.low, bar.close].every(price => point.test(price) && Number.isFinite(Number(price)) && Number(price) > 0)
        || comparePrice(bar.low, bar.open) > 0 || comparePrice(bar.low, bar.close) > 0
        || comparePrice(bar.high, bar.open) < 0 || comparePrice(bar.high, bar.close) < 0
        || new Set(bar.evidence_refs.map(item => item.object_id)).size !== 2
        || bar.evidence_refs.some(item => !evidenceIds.has(item.object_id))) throw new Error("指数日线与固定日历不符");
  }
  if (summary.trade_date !== range.end || summary.close !== bars.at(-1)!.close) throw new Error("指数摘要与日线不符");
  return snapshot;
}

/** 从可见行选择既有high／low及日期；并列时保留最早一行。 */
export function visibleExtrema<T extends Pick<SeriesBar, "high" | "low" | "trade_date">>(bars: readonly T[], start: number, end: number) {
  let high = bars[start], low = bars[start];
  for (let i = start + 1; i <= end; i++) {
    if (comparePrice(bars[i].high, high.high) > 0) high = bars[i];
    if (comparePrice(bars[i].low, low.low) < 0) low = bars[i];
  }
  return { high, low };
}

/** 日历月份只用于裁剪显示范围；月末回退钳至目标月最后一天。 */
export function monthsBefore(day: string, months: number): string {
  const date = new Date(day + "T00:00:00Z");
  const target = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() - months, 1));
  const last = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  target.setUTCDate(Math.min(date.getUTCDate(), last));
  return target.toISOString().slice(0, 10);
}

/** 观察窗口仅选取已有收盘点；区间收益由固定快照计算接口提供。 */
export function trendBars(bars: SeriesBar[], window: string): SeriesBar[] {
  if (window !== "1y") return bars.slice(-Number(window) - 1);
  const boundary = monthsBefore(bars.at(-1)!.trade_date, 12);
  let index = bars.length - 1;
  while (index >= 0 && bars[index].trade_date > boundary) index--;
  return bars.slice(Math.max(index, 0));
}
