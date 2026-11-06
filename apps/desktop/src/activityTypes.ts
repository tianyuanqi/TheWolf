import type { components } from "../../../contracts/generated/http";
import { MarketActivityCalculations as validCalculations, MarketActivitySnapshot as validSnapshot } from "../../../contracts/generated/validators.mjs";
import { MA_PERIODS, FREQUENCIES, type Frequency } from "./indexCalculationTypes";
import { validDay, type SeriesSnapshot } from "./indexSeriesTypes";

export type ActivityDescriptor = components["schemas"]["MarketActivityDescriptor"];
export type ActivityId = components["schemas"]["MarketActivitySeriesId"];
export type ActivitySnapshot = components["schemas"]["MarketActivitySnapshot"];
export type ActivityCalculations = components["schemas"]["MarketActivityCalculations"];
export type ActivitySeries = ActivityCalculations["series"][number];
export type ActivityScalar = components["schemas"]["MarketActivityScalar"];
export type ActivityField = ActivitySeries["field"];
export type ActivityBundle = { snapshot: ActivitySnapshot; calculations: ActivityCalculations };
export const ACTIVITY_FORMULA = "market-activity-calculations-v1";
export const LEGACY_MARKET = "cn-a-turnover";
export const MARKET = "cn-a-turnover-sse-szse";
export const isMarket = (id: string) => id === MARKET || id === LEGACY_MARKET;
export const activityFormula = (id: string) => id === MARKET ? "market-activity-calculations-sse-szse-v1" : ACTIVITY_FORMULA;
export const activityPolicyKeys = (id: ActivityId) => id === MARKET ? ["sse-a-json", "szse-a-json"] : id === LEGACY_MARKET ? ["sse-a-json", "szse-a-json", "bse-a-json"] : [id];
const decimal = /^-?\d+(?:\.\d+)?$/;
const messages: Record<string, string> = {
  source_unverified: "来源尚未准入，G1—G4证据缺口保留", source_withdrawn: "官方错误值已撤回，本系列隔离",
  activity_not_found: "尚无与本次查询匹配的已保存量额", activity_disabled: "量额连接未配置",
  source_missing: "来源缺日或缺少该值", missing_source_value: "来源缺少该值", missing_date: "缺少该交易日", missing_market: "缺少市场数据",
  missing_window_value: "窗口内存在缺失值", insufficient_samples: "有效样本不足", zero_baseline: "比较基准为零",
  calendar_unknown: "周期日历未覆盖", window_start_truncated: "历史窗口起点截断", period_in_progress: "周期尚未结束",
};
export const activityReason = (reason?: string | null) => reason ? messages[reason] ?? reason : "量额数据未取得";
export const activityUnit = (field: ActivityField) => field === "volume" ? "万股" : "亿元";

/** 只移动十进制小数点；文字舍入与图形坐标共用原单位转换，不修改输入。 */
function activityDecimal(value: string, field: ActivityField): string {
  if (!decimal.test(value)) throw new Error("量额显示值无效");
  const shift = field === "volume" ? 4 : 8;
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const digits = whole.padStart(shift + 1, "0");
  const tail = (digits.slice(-shift) + fraction).replace(/0+$/, "");
  return (negative ? "-" : "") + digits.slice(0, -shift) + (tail ? "." + tail : "");
}

/** 金额文字按亿元四舍五入为整数；VOL保留原显示精度，缺失不补零。 */
export function activityText(value: string | null, field: ActivityField): string {
  if (value === null) return "暂无数据";
  const converted = activityDecimal(value, field);
  const negative = converted.startsWith("-");
  const [whole, fraction = ""] = (negative ? converted.slice(1) : converted).split(".");
  if (field === "amount") {
    const rounded = BigInt(whole) + (fraction[0] >= "5" ? 1n : 0n);
    return (negative && rounded !== 0n ? "-" : "") + rounded.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  return (negative ? "-" : "") + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction ? "." + fraction : "");
}

/** 图形坐标沿用未舍入的单位换算值；不得把文字整数反写为绘图或金融输入。 */
export function activityPlotValue(value: string | null, field: ActivityField): number | null {
  return value === null ? null : Number(activityDecimal(value, field));
}

/** 客户端只收紧展示门禁；真正准入与撤回仍由可信服务执行。 */
export function activityGate(config: ActivityDescriptor, id: ActivityId): string | undefined {
  if (!config.series.includes(id)) return "量额系列未配置";
  if (config.blocked_series.some(item => item.series_id === id)) return activityReason("source_withdrawn");
  const ids = activityPolicyKeys(id);
  const rules = ids.map(key => config.policy.sources.filter(item => item.series === key));
  if (rules.some(items => items.length !== 1 || !items[0].admitted)) return activityReason("source_unverified");
}

/** 校验固定配对、日历与原始单位；不重算任何量额、均线或比较值。 */
export function parseActivitySnapshot(value: unknown, id: ActivityId, aid: string, anchor: string, price?: SeriesSnapshot): ActivitySnapshot {
  if (!validSnapshot(value) || value.series_id !== id || value.activity_id !== aid || value.price_snapshot_id !== (price?.snapshot_id ?? null)
      || value.anchor_date !== anchor || !value.calendar_dates.length || value.calendar_dates.length > 1100
      || value.rows.length !== value.calendar_dates.length || value.window.start !== value.calendar_dates[0]
      || value.window.end !== value.calendar_dates.at(-1)
      || (isMarket(id) ? !("market_calendars" in value) || value.binding !== null : "market_calendars" in value || !price || !value.binding)
      || (price && (JSON.stringify(value.calendar_dates) !== JSON.stringify(price.calendar_dates) || value.calendar_version !== price.calendar_version))) {
    throw new Error("量额快照与价格配对、查询日期或日历不符");
  }
  const objects = new Set(value.sources.map(item => item.object_id));
  for (const [i, row] of value.rows.entries()) {
    if (row.trade_date !== value.calendar_dates[i] || !validDay(row.trade_date) || (i > 0 && row.trade_date <= value.calendar_dates[i - 1])) throw new Error("量额日期不符");
    const fields: [components["schemas"]["MarketActivityFact"], string][] = "components" in row
      ? Object.values(row.components).flatMap(parts => parts.map(part => [part, "元"] as [typeof part, string]))
      : [[row.amount, "元"], [row.volume, "股"]];
    if (!fields.length || ("components" in row && Object.values(row.components).some(parts => !parts.length))) throw new Error("全市场缺少显式分量");
    for (const [fact, unit] of fields) {
      if (fact.unit !== unit || (fact.value === null ? !fact.reason : fact.reason !== null || !/^\d+(?:\.\d+)?$/.test(fact.value)
          || !Number.isFinite(Number(fact.value)) || !fact.object_id || !objects.has(fact.object_id))) throw new Error("量额原值、缺失或原件引用无效");
    }
  }
  if (!value.observations.length || value.observations.some(o => o.series_id !== id || o.activity_id !== aid || o.price_snapshot_id !== (price?.snapshot_id ?? null))) throw new Error("量额观察归属无效");
  return value;
}

/** 核对固定来源精度，不允许单序列悄悄混入别的单位、刻度或来源。 */
export function checkActivityPolicy(snapshot: ActivitySnapshot, config: ActivityDescriptor): void {
  function check(fact: components["schemas"]["MarketActivityFact"], key: string, field: ActivityField) {
    const policyKey = (snapshot.series_id === MARKET || snapshot.source_policy_version === "activity-source-policy-sse-szse-bse-v1") ? key + "-a-json" : key;
    const rule = config.policy.sources.find(item => item.series === policyKey);
    if (!rule || fact.raw_unit !== (field === "volume" ? rule.volume_unit : rule.amount_unit)
        || fact.source_quantum !== (field === "volume" ? "1" : rule.amount_quantum)
        || (fact.object_id && snapshot.sources.find(source => source.object_id === fact.object_id)?.source !== rule.source)) throw new Error("量额来源、单位或精度与冻结策略不符");
  }
  for (const row of snapshot.rows) {
    if ("components" in row) for (const [market, parts] of Object.entries(row.components)) parts.forEach(part => check(part, market, "amount"));
    else { check(row.amount, snapshot.series_id, "amount"); check(row.volume, snapshot.series_id, "volume"); }
  }
}

/** 各结果必须引用同一固定输入，核对公式参数、缺失和周期归属；不复制服务端公式。 */
export function parseActivityCalculations(value: unknown, snapshot: ActivitySnapshot, priceSeries?: { [key in Frequency]: { rows: { start: string; end: string }[] } }): ActivityCalculations {
  if (!validCalculations(value) || value.series_id !== snapshot.series_id || value.activity_id !== snapshot.activity_id
      || value.price_snapshot_id !== snapshot.price_snapshot_id || value.formula_version !== activityFormula(snapshot.series_id)) throw new Error("量额计算快照归属无效");
  const market = isMarket(snapshot.series_id);
  const expected = market ? ["amount:daily"] : ["volume", "amount"].flatMap(field => FREQUENCIES.map(frequency => `${field}:${frequency}`));
  if (value.series.length !== expected.length || new Set(value.series.map(s => `${s.field}:${s.frequency}`)).size !== expected.length
      || value.series.some(s => !expected.includes(`${s.field}:${s.frequency}`)) || (market ? !value.comparisons : value.comparisons !== null)) throw new Error("量额计算系列不符");
  const dates = new Set(snapshot.calendar_dates);
  function scalar(item: ActivityScalar, field: ActivityField, frequency: Frequency, operation: string, period: string, end: string) {
    const ref = item.input_ref;
    if (item.formula_version !== activityFormula(snapshot.series_id) || ref.series_id !== snapshot.series_id || ref.activity_id !== snapshot.activity_id
        || ref.price_snapshot_id !== snapshot.price_snapshot_id || ref.end !== end || !dates.has(end)
        || (ref.start !== null && (!dates.has(ref.start) || ref.start > end))
        || item.parameters.field !== field || item.parameters.frequency !== frequency || item.parameters.operation !== operation || item.parameters.period !== period
        || item.unit !== (operation.endsWith("pct") ? "%" : field === "volume" ? "股" : "元")
        || item.complete !== (item.incomplete_reasons.length === 0)
        || (item.value === null ? !item.reason : item.reason !== null || !decimal.test(item.value) || (!operation.endsWith("pct") && item.value.startsWith("-")) || !Number.isFinite(Number(item.value)))) {
      throw new Error("量额计算引用、公式参数、单位或缺失标记不符");
    }
  }
  for (const series of value.series) {
    if (!series.rows.length || series.rows[0].start !== snapshot.window.start || series.rows.at(-1)!.end !== snapshot.window.end
        || series.ma_availability.length !== MA_PERIODS.length) throw new Error("量额计算覆盖不符");
    if (series.frequency === "daily" && series.rows.length !== snapshot.rows.length) throw new Error("量额日序列缺行");
    const priceRows = priceSeries?.[series.frequency].rows;
    if (priceRows && (priceRows.length !== series.rows.length || priceRows.some((r, i) => r.start !== series.rows[i].start || r.end !== series.rows[i].end))) throw new Error("价格与量额周期不一致");
    for (const [i, row] of series.rows.entries()) {
      if (!dates.has(row.start) || !dates.has(row.end) || row.start > row.end || !validDay(row.period_start) || !validDay(row.period_end)
          || row.period_start > row.start || row.period_end < row.end || (i > 0 && row.start <= series.rows[i - 1].end)
          || (series.frequency === "daily" && (row.start !== snapshot.calendar_dates[i] || row.end !== row.start)) || row.ma.length !== MA_PERIODS.length) throw new Error("量额周期日期无效");
      const inputs = snapshot.rows.filter(input => input.trade_date >= row.start && input.trade_date <= row.end);
      const missing = inputs.some(input => "components" in input ? Object.values(input.components).some(parts => parts.some(part => part.value === null)) : input[series.field].value === null);
      if (missing && row.total.value !== null) throw new Error("缺日或缺市场不得显示有效合计");
      scalar(row.total, series.field, series.frequency, "sum", "1", row.end);
      scalar(row.change_pct, series.field, series.frequency, "change_pct", "1", row.end);
      row.ma.forEach((item, n) => scalar(item, series.field, series.frequency, "ma", String(MA_PERIODS[n]), row.end));
    }
    series.ma_availability.forEach((ability, i) => {
      if (ability.period !== MA_PERIODS[i] || ability.required_count !== ability.period || ability.sample_count > ability.period
          || ability.available !== (series.rows.at(-1)!.ma[i].value !== null) || ability.reason !== series.rows.at(-1)!.ma[i].reason) throw new Error("量额均线能力不符");
    });
  }
  if (value.comparisons) for (const [key, comparison] of Object.entries(value.comparisons)) {
    scalar(comparison.baseline, "amount", "daily", "baseline_mean", key, snapshot.calendar_dates.at(-2) ?? snapshot.window.end);
    scalar(comparison.comparison, "amount", "daily", "window_mean_pct", key, snapshot.window.end);
  }
  return value;
}
