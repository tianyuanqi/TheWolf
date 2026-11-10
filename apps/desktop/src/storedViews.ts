import type { components } from "../../../contracts/generated/http";
import { MarketVersions as validVersions, StoredPriceOverview as validPriceOverview, StoredPriceRange as validPriceRange,
  StoredActivityRange as validActivityRange, StoredMarketOverview as validMarketOverview } from "../../../contracts/generated/validators.mjs";
import { CALCULATION_VERSION, MA_PERIODS, checkStoredPerformance, type Frequency } from "./indexCalculationTypes";
import { activityFormula, isMarket, type ActivityField, type ActivityId, type ActivityScalar } from "./activityTypes";
import { validDay, monthsBefore, comparePrice, OVERVIEW_INDICES, type OverviewIndexId } from "./indexSeriesTypes";
import type { ChartWindow } from "./OverviewCharts";
import type { IndexSeriesClient } from "./indexSeriesClient";
import type { ActivityClient } from "./activityClient";

export type Versions = components["schemas"]["MarketVersions"];
export type Version = components["schemas"]["StoredVersion"];
export type PriceOverview = components["schemas"]["StoredPriceOverview"];
export type PriceRange = components["schemas"]["StoredPriceRange"];
export type ActivityRange = components["schemas"]["StoredActivityRange"];
export type MarketOverview = components["schemas"]["StoredMarketOverview"];
export type DateRange = components["schemas"]["StoredDateRange"];
type SelectedRange = PriceRange | ActivityRange;
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>`${JSON.stringify(key)}:${stable(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

export function requestedRange(coverage: DateRange, range: ChartWindow): DateRange {
  const end = range.preset === "custom" ? range.end! : coverage.end;
  const start = range.preset === "custom" ? range.start! : range.preset === "all" ? coverage.start
    : [coverage.start, monthsBefore(end, Number(range.preset))].sort().at(-1)!;
  if (!validDay(start) || !validDay(end) || start > end || start < coverage.start || end > coverage.end) throw new Error("请选择已保存范围内的日期");
  return { start, end };
}

function coverage(value: { source_coverage: DateRange; requested_range: DateRange; returned_range: DateRange | null; calculation_input_range: DateRange | null }, expected: DateRange) {
  const source = value.source_coverage, input = value.calculation_input_range, returned = value.returned_range;
  for (const range of [source, value.requested_range, input, returned]) if (range && (!validDay(range.start) || !validDay(range.end) || range.start > range.end)) throw new Error("日期范围无效");
  if (stable(value.requested_range) !== stable(expected) || expected.start < source.start || expected.end > source.end
      || Boolean(input) !== Boolean(returned) || input && returned && (input.start < source.start || input.end > source.end || returned.start < input.start || returned.end > input.end)) throw new Error("返回覆盖或计算输入与请求不符");
}

function selected(value: SelectedRange, request: DateRange, frequency: Frequency, periods: number[]) {
  coverage(value, request);
  const wanted = [...periods].sort((a, b) => a - b);
  if (value.frequency !== frequency || value.series.frequency !== frequency || stable(value.ma_periods) !== stable(wanted)
      || new Set(periods).size !== periods.length || periods.some(period => !MA_PERIODS.includes(period as typeof MA_PERIODS[number]))) throw new Error("周期或均线集合不符");
  const rows = value.series.rows, returned = value.returned_range, input = value.calculation_input_range;
  const navigation = value.navigation_periods;
  if (!navigation.length || navigation[0].start !== value.source_coverage.start || navigation.at(-1)!.end !== value.source_coverage.end
      || navigation.some((period, i) => !validDay(period.start) || !validDay(period.end) || period.start > period.end
        || i > 0 && navigation[i - 1].end >= period.start || frequency === "daily" && period.start !== period.end)
      || rows.some(row => !navigation.some(period => period.start === row.start && period.end === row.end))) throw new Error("日期导航与固定范围不符");
  const price = "index_id" in value ? value as PriceRange : undefined;
  const activity = "series_id" in value ? value as ActivityRange : undefined;
  if (Boolean(rows.length) !== Boolean(returned) || returned && (rows[0].start !== returned.start || rows.at(-1)!.end !== returned.end)) throw new Error("实际返回日期不符");
  const abilities = value.series.ma_availability;
  if (stable(abilities.map(item => item.period)) !== stable(MA_PERIODS) || abilities.some(item => !Number.isSafeInteger(item.sample_count) || item.sample_count < 0 || item.required_count !== item.period)) throw new Error("均线能力无效");
  for (const [i, row] of rows.entries()) {
    if (!input || !validDay(row.start) || !validDay(row.end) || row.start > row.end || row.start < input.start || row.end > input.end
        || !validDay(row.period_start) || !validDay(row.period_end) || row.period_start > row.start || row.period_end < row.end
        || row.period_start > request.end || row.period_end < request.start || i > 0 && (rows[i - 1].end >= row.start || rows[i - 1].period_end >= row.period_start)
        || !Number.isSafeInteger(row.sample_count) || row.sample_count < 1 || frequency === "daily" && (row.sample_count !== 1 || row.start !== row.end)) throw new Error("周期边界或样本数无效");
    if (stable(row.ma.map(item => Number(item.parameters.period))) !== stable(wanted)) throw new Error("均线返回集合不符");
    const cells = [row.change_pct, ...row.ma, ...("total" in row ? [row.total] : [])];
    for (const [position, cell] of cells.entries()) {
      const ref = cell.input_ref;
      const isChange = position === 0, isTotal = position > row.ma.length;
      const formula = price ? isChange ? frequency === "daily" ? "adjacent-expected-close-pct-half-up-v1" : "period-close-pct-half-up-v1"
        : "close-sma-half-up-4-v1" : value.formula_version;
      const period = isChange || isTotal ? "1" : String(wanted[position - 1]);
      const unit = isChange ? "%" : price ? "点" : activity?.field === "volume" ? "股" : "元";
      if (cell.formula_version !== formula || cell.parameters.frequency !== frequency || cell.parameters.period !== period || cell.unit !== unit || ref.end !== row.end
          || ref.start !== null && (ref.start < input.start || ref.start > ref.end)
          || (cell.value === null ? !cell.reason : cell.reason !== null || ref.start === null || !Number.isFinite(Number(cell.value))
            || !(price ? isChange ? /^-?\d+\.\d{2}$/ : /^\d+\.\d{4}$/ : /^-?\d+(?:\.\d+)?$/).test(cell.value)
            || !isChange && cell.value.startsWith("-"))
          || ("index_id" in ref ? !price || ref.index_id !== price.index_id || ref.snapshot_id !== price.snapshot_id
            : !activity || ref.series_id !== activity.series_id || ref.activity_id !== activity.activity_id || ref.price_snapshot_id !== activity.price_snapshot_id)) throw new Error("计算引用不属于固定输入");
      if ("operation" in cell.parameters && (!activity || cell.parameters.field !== activity.field
          || cell.parameters.operation !== (isChange ? "change_pct" : isTotal ? "sum" : "ma"))) throw new Error("量额计算参数无效");
      if (price && cell.value === null && (cell.reason !== (isChange ? "missing_previous_close" : "insufficient_samples") || ref.start !== null)) throw new Error("价格缺失原因无效");
      if ("complete" in cell && (cell.complete !== (cell.incomplete_reasons.length === 0) || new Set(cell.incomplete_reasons).size !== cell.incomplete_reasons.length)) throw new Error("量额完整性标记无效");
    }
    if ("open" in row && (!price || row.formula_version !== (frequency === "daily" ? "raw-daily-price-v1" : "calendar-ohlc-v1")
        || row.input_ref.index_id !== price.index_id || row.input_ref.snapshot_id !== price.snapshot_id || row.input_ref.start !== row.start || row.input_ref.end !== row.end
        || row.complete !== (row.incomplete_reasons.length === 0) || new Set(row.incomplete_reasons).size !== row.incomplete_reasons.length
        || ![row.open,row.high,row.low,row.close].every(item => new RegExp(`^\\d+\\.\\d{${price.storage_decimals}}$`).test(item) && Number(item) > 0 && Number.isFinite(Number(item)))
        || comparePrice(row.high, row.open) < 0 || comparePrice(row.high, row.close) < 0 || comparePrice(row.low, row.open) > 0 || comparePrice(row.low, row.close) > 0)) throw new Error("K线原值或周期标记无效");
  }
}

function activityContext(value: ActivityRange | MarketOverview, id: ActivityId) {
  if (value.formula_version !== activityFormula(id) || !validDay(value.anchor_date) || value.anchor_date <= value.source_coverage.end
      || !value.source_scope || value.source_revision_relation !== "unknown" || new Set(value.sources.map(source => source.object_id)).size !== value.sources.length
      || (isMarket(id) ? value.binding !== null || value.price_snapshot_id !== null : !value.binding || !value.price_snapshot_id)) throw new Error("量额来源或固定配对说明无效");
  if (value.binding && ((value.binding.price_object_id === value.binding.activity_object_id) !== (value.binding.relation === "same_source_object"))) throw new Error("量额来源配对关系无效");
}

function marketComparisons(value: MarketOverview) {
  if (!value.comparisons || !value.series.rows.length) throw new Error("市场比较缺失");
  const dates = new Set(value.series.rows.map(row => row.end));
  const last = value.series.rows.at(-1)!.end, prior = value.series.rows.at(-2)?.end ?? last;
  function scalar(item: ActivityScalar, key: string, operation: string, end: string) {
    const ref = item.input_ref;
    if (item.formula_version !== value.formula_version || ref.series_id !== value.series_id || ref.activity_id !== value.activity_id || ref.price_snapshot_id !== null
        || ref.end !== end || ref.start !== null && (!validDay(ref.start) || ref.start > end || ref.start < value.source_coverage.start)
        || item.parameters.field !== "amount" || item.parameters.frequency !== "daily" || item.parameters.operation !== operation || item.parameters.period !== key
        || item.unit !== (operation === "window_mean_pct" ? "%" : "元") || item.complete !== (item.incomplete_reasons.length === 0)
        || new Set(item.incomplete_reasons).size !== item.incomplete_reasons.length
        || (item.value === null ? !item.reason : item.reason !== null || ref.start === null || !/^-?\d+(?:\.\d+)?$/.test(item.value)
          || !Number.isFinite(Number(item.value)) || operation === "baseline_mean" && item.value.startsWith("-"))) throw new Error("市场比较引用、单位或参数无效");
    if (ref.start && value.returned_range && ref.start >= value.returned_range.start && !dates.has(ref.start)) throw new Error("市场比较日期不属于返回交易日");
  }
  for (const [key, comparison] of Object.entries(value.comparisons)) {
    if (!Number.isSafeInteger(comparison.sample_count) || comparison.sample_count < 0) throw new Error("市场比较样本数无效");
    scalar(comparison.baseline, key, "baseline_mean", prior);
    scalar(comparison.comparison, key, "window_mean_pct", last);
  }
}

/** 两个已核验连接共用32项范围缓存；实例/配置/版本/观察/绑定/参数均进入键。 */
export class StoredViews {
  private cache = new Map<string, unknown>();
  private pending = new Map<string, { controller: AbortController; promise: Promise<unknown> }>();
  private storeId?: string;
  constructor(readonly price: IndexSeriesClient, readonly activity?: ActivityClient) {}
  clear() {
    this.cache.clear();
    for (const entry of this.pending.values()) entry.controller.abort();
    this.pending.clear();
  }
  private async memo<T>(domain: string, query: Record<string, string>, signal: AbortSignal, read: (signal: AbortSignal) => Promise<T>): Promise<T> {
    if (this.price.closed || this.activity?.closed) { this.clear(); throw new Error("连接已失效，请重新连接"); }
    const key = stable([this.price.expected.config_id, this.price.instance, this.activity?.expected.config_id, this.storeId, domain, query, "unadjusted"]);
    const cancelled = () => new DOMException("读取已取消", "AbortError");
    if (signal.aborted) throw cancelled();
    if (this.cache.has(key)) {
      const value = this.cache.get(key); this.cache.delete(key); this.cache.set(key, value);
      return structuredClone(value) as T;
    }
    // 已发出的固定范围读取可供快速切回复用；取消只结束该调用者，连接关闭仍取消网络。
    let entry = this.pending.get(key);
    if (!entry) {
      const controller = new AbortController();
      const promise = Promise.resolve().then(() => read(controller.signal)).then(value => {
        if (controller.signal.aborted || this.price.closed || this.activity?.closed) throw cancelled();
        this.cache.set(key, structuredClone(value));
        while (this.cache.size > 32) this.cache.delete(this.cache.keys().next().value!);
        return value;
      }).finally(() => { if (this.pending.get(key)?.controller === controller) this.pending.delete(key); });
      entry = { controller, promise }; this.pending.set(key, entry);
      while (this.pending.size > 32) {
        const oldest = this.pending.keys().next().value!;
        this.pending.get(oldest)!.controller.abort(); this.pending.delete(oldest);
      }
    }
    let abort: () => void = () => {};
    try {
      const value = await Promise.race([entry.promise, new Promise<never>((_, reject) => {
        abort = () => reject(cancelled()); signal.addEventListener("abort", abort, { once: true });
        if (signal.aborted) abort();
      })]);
      if (signal.aborted || this.price.closed || this.activity?.closed) throw cancelled();
      return structuredClone(value) as T;
    } finally { signal.removeEventListener("abort", abort); }
  }
  async versions(signal: AbortSignal): Promise<Versions> {
    const value = await this.price.storedVersions(signal);
    const ids = [...OVERVIEW_INDICES.map(item => item.id), "csi:000300:price", "csi:000852:price"];
    if (!validVersions(value) || value.indices.length !== 6 || ![0, 2].includes(value.markets.length)
        || value.indices.some(item => !ids.includes(item.index_id)) || value.markets.some(item => !isMarket(item.series_id))
        || new Set(value.indices.map(x => x.index_id)).size !== value.indices.length
        || new Set(value.markets.map(x => x.series_id)).size !== value.markets.length) throw new Error("当前版本列表无效");
    for (const item of [...value.indices.flatMap(x => [x.price, x.activity]), ...value.markets.map(x => x.activity), value.etf])
      if (item && (!validDay(item.source_coverage.start) || !validDay(item.source_coverage.end) || item.source_coverage.start > item.source_coverage.end)) throw new Error("发布覆盖无效");
    for (const item of value.indices) {
      if (item.price && (item.price.binding !== "" || !item.price.first_observation_id || !item.price.observation_id)
          || item.activity && (!item.price || item.activity.binding !== item.price.publication_id || !item.activity.observation_id)) throw new Error("版本观察或量额绑定无效");
    }
    if (value.markets.some(item => item.activity && (!validDay(item.activity.binding) || !item.activity.observation_id))) throw new Error("市场绑定无效");
    if (this.storeId !== value.store_id) this.clear();
    this.storeId = value.store_id;
    return value;
  }
  private priceQuery(version: Version) {
    if (!version.first_observation_id) throw new Error("价格观察缺失");
    return { snapshot_id: version.publication_id, observation_id: version.first_observation_id, formula_version: CALCULATION_VERSION };
  }
  async overview(id: OverviewIndexId, version: Version, signal: AbortSignal): Promise<PriceOverview> {
    const query = { ...this.priceQuery(version), detail: "overview" };
    return this.memo("price:" + id, query, signal, async requestSignal => {
      const value = await this.price.storedView(id, query, requestSignal);
      if (!validPriceOverview(value) || value.index_id !== id || value.snapshot_id !== version.publication_id || value.observation_id !== version.first_observation_id
          || stable(value.source_coverage) !== stable(version.source_coverage) || value.instrument.id !== id || !value.bars.length
          || value.summary.trade_date !== value.source_coverage.end || value.summary.close !== value.bars.at(-1)!.close) throw new Error("价格概况归属无效");
      const definition = OVERVIEW_INDICES.find(item => item.id === id)!;
      if (value.instrument.name !== definition.name || value.instrument.code !== definition.code.slice(0, 6) || value.instrument.provider !== definition.provider
          || value.storage_decimals !== definition.decimals || !validDay(value.anchor_date) || value.anchor_date <= value.source_coverage.end
          || new Set(value.sources.map(source => source.object_id)).size !== 2 || value.sources.length !== 2
          || stable(value.sources.map(source => source.source).sort()) !== stable([definition.provider, "eastmoney"].sort())
          || value.verification.primary_source !== definition.provider || value.verification.mode !== (definition.decimals === 2 ? "exact" : "rounding_aware")
          || value.verification.comparison_rounding !== (definition.decimals === 2 ? null : "ROUND_HALF_UP")) throw new Error("指数身份、来源或精度不符");
      coverage(value, { start: [value.source_coverage.start, monthsBefore(value.source_coverage.end, 12)].sort().at(-1)!, end: value.source_coverage.end });
      if (!value.returned_range || value.returned_range.start !== value.bars[0].trade_date || value.returned_range.end !== value.bars.at(-1)!.trade_date) throw new Error("概况范围无效");
      const point = new RegExp(`^\\d+\\.\\d{${definition.decimals}}$`);
      for (const [i, row] of value.bars.entries()) if (!validDay(row.trade_date) || i > 0 && value.bars[i - 1].trade_date >= row.trade_date
          || ![row.open, row.high, row.low, row.close].every(item => point.test(item) && Number.isFinite(Number(item)) && Number(item) > 0)
          || comparePrice(row.high, row.open) < 0 || comparePrice(row.high, row.close) < 0 || comparePrice(row.low, row.open) > 0 || comparePrice(row.low, row.close) > 0) throw new Error("概况日期或价格原值无效");
      checkStoredPerformance(value);
      return value;
    });
  }
  async priceRange(id: OverviewIndexId, version: Version, range: DateRange, frequency: Frequency, periods: number[], signal: AbortSignal): Promise<PriceRange> {
    const query = { ...this.priceQuery(version), ...range, detail: "range", frequency, ma: [...periods].sort((a,b)=>a-b).join(",") || "none" };
    return this.memo("price:" + id, query, signal, async requestSignal => {
      const value = await this.price.storedView(id, query, requestSignal);
      if (!validPriceRange(value) || value.index_id !== id || value.snapshot_id !== version.publication_id || value.observation_id !== version.first_observation_id
          || stable(value.source_coverage) !== stable(version.source_coverage)) throw new Error("价格范围归属无效");
      selected(value, range, frequency, periods); return value;
    });
  }
  private activityQuery(id: ActivityId, version: Version) {
    if (!this.activity || !version.observation_id) throw new Error("量额连接或观察缺失");
    return { activity_id: version.publication_id, observation_id: version.observation_id, formula_version: activityFormula(id),
      ...((id === "cn-a-turnover" || id === "cn-a-turnover-sse-szse") ? { anchor_date: version.binding } : { price_snapshot_id: version.binding }) } as Record<string,string>;
  }
  async marketOverview(id: ActivityId, version: Version, signal: AbortSignal): Promise<MarketOverview> {
    const query = { ...this.activityQuery(id, version), detail: "overview" };
    return this.memo("activity:" + id, query, signal, async requestSignal => {
      const value = await this.activity!.storedView(id, query, requestSignal);
      if (!validMarketOverview(value) || value.series_id !== id || value.activity_id !== version.publication_id || value.observation_id !== version.observation_id
          || value.anchor_date !== version.binding || value.price_snapshot_id !== null || stable(value.source_coverage) !== stable(version.source_coverage)) throw new Error("市场概况归属无效");
      activityContext(value, id);
      selected({ ...value, frequency: "daily", ma_periods: [], field: "amount" },
        { start: [value.source_coverage.start, monthsBefore(value.source_coverage.end, 12)].sort().at(-1)!, end: value.source_coverage.end }, "daily", []);
      marketComparisons(value);
      return value;
    });
  }
  async activityRange(id: ActivityId, version: Version, range: DateRange, field: ActivityField, frequency: Frequency, periods: number[], signal: AbortSignal): Promise<ActivityRange> {
    const query = { ...this.activityQuery(id, version), ...range, detail: "range", field, frequency, ma: [...periods].sort((a,b)=>a-b).join(",") || "none" };
    return this.memo("activity:" + id, query, signal, async requestSignal => {
      const value = await this.activity!.storedView(id, query, requestSignal);
      if (!validActivityRange(value) || value.series_id !== id || value.activity_id !== version.publication_id || value.observation_id !== version.observation_id
          || (value.price_snapshot_id ?? value.anchor_date) !== version.binding || value.field !== field || stable(value.source_coverage) !== stable(version.source_coverage)) throw new Error("量额范围或价格绑定不符");
      activityContext(value, id);
      selected(value, range, frequency, periods); return value;
    });
  }
}
