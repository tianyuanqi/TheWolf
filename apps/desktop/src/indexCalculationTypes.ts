import type { components } from "../../../contracts/generated/http";
import { IndexSeriesCalculations as validCalculations } from "../../../contracts/generated/validators.mjs";
import { comparePrice, validDay, type SeriesSnapshot } from "./indexSeriesTypes";

export type Calculations = components["schemas"]["IndexSeriesCalculations"];
export type CalculationSeries = Calculations["daily"];
export type CalculationScalar = components["schemas"]["IndexSeriesCalculationScalar"];
export type Frequency = CalculationSeries["frequency"];
export const CALCULATION_VERSION = "index-price-calculations-v1";
export const MA_PERIODS = [5, 10, 20, 30, 60, 120, 180, 250] as const;
export const FREQUENCIES: Frequency[] = ["daily", "weekly", "monthly"];
export const FREQUENCY_LABELS: Record<Frequency, string> = { daily: "日", weekly: "周", monthly: "月" };
export const RESULT_REASONS = {
  insufficient_samples: "有效样本不足", missing_previous_close: "缺少有效前周期收盘", missing_year_baseline: "缺少自然1年前基准",
};
export const INCOMPLETE_REASONS = {
  window_start_truncated: "历史窗口起点截断", period_in_progress: "周期尚未结束", calendar_unknown: "周期日历未覆盖",
};

/** 验证既有结果的结构、归属、参数及原值；不重算收益、均线或周月聚合。 */
export function parseCalculations(value: unknown, snapshot: SeriesSnapshot): Calculations {
  if (!validCalculations(value) || value.snapshot_id !== snapshot.snapshot_id
      || value.index_id !== snapshot.instrument.id || value.anchor_date !== snapshot.window.anchor_date
      || value.calendar_version !== snapshot.calendar_version) throw new Error("计算结果与当前价格快照不符");
  const dates = new Set(snapshot.calendar_dates);
  const point = new RegExp(`^[0-9]+\\.[0-9]{${snapshot.storage_decimals}}$`);
  function checkRef(ref: CalculationScalar["input_ref"], end: string) {
    if (ref.index_id !== snapshot.instrument.id || ref.snapshot_id !== snapshot.snapshot_id || ref.end !== end
        || !dates.has(ref.end) || (ref.start !== null && (!dates.has(ref.start) || ref.start > end))) {
      throw new Error("计算输入引用不属于所选快照或日期");
    }
  }
  function checkScalar(item: CalculationScalar, frequency: Frequency, period: string,
    formula: CalculationScalar["formula_version"], end: string, unit: "%" | "点", reason: CalculationScalar["reason"]) {
    checkRef(item.input_ref, end);
    if (item.parameters.frequency !== frequency || item.parameters.period !== period || item.formula_version !== formula
        || item.unit !== unit || (item.value === null ? item.reason !== reason || item.input_ref.start !== null
          : item.reason !== null || item.input_ref.start === null || !Number.isFinite(Number(item.value))
            || !(unit === "%" ? /^-?\d+\.\d{2}$/ : /^\d+\.\d{4}$/).test(item.value))) {
      throw new Error("计算结果的公式、参数、单位或缺失原因不符");
    }
  }
  for (const frequency of FREQUENCIES) {
    const series = value[frequency];
    if (series.frequency !== frequency || !series.rows.length || series.ma_availability.length !== MA_PERIODS.length
        || series.rows[0].start !== snapshot.window.start || series.rows.at(-1)!.end !== snapshot.window.end
        || (frequency === "daily" && series.rows.length !== snapshot.bars.length)) throw new Error("计算周期或覆盖范围不符");
    for (const [i, availability] of series.ma_availability.entries()) {
      if (availability.period !== MA_PERIODS[i] || availability.required_count !== availability.period
          || availability.sample_count > series.rows.length || availability.sample_count !== series.ma_availability[0].sample_count
          || availability.available !== (availability.sample_count >= availability.required_count)
          || availability.reason !== (availability.available ? null : "insufficient_samples")) throw new Error("均线可用性说明不一致");
    }
    for (const [i, row] of series.rows.entries()) {
      checkRef(row.input_ref, row.end);
      if (row.input_ref.start !== row.start || !dates.has(row.start)
          || !validDay(row.period_start) || !validDay(row.period_end) || row.period_start > row.start || row.period_end < row.end
          || (i > 0 && (row.start <= series.rows[i - 1].end || row.period_start <= series.rows[i - 1].period_end))
          || row.complete !== (row.incomplete_reasons.length === 0)
          || new Set(row.incomplete_reasons).size !== row.incomplete_reasons.length
          || row.formula_version !== (frequency === "daily" ? "raw-daily-price-v1" : "calendar-ohlc-v1")
          || ![row.open, row.high, row.low, row.close].every(price => point.test(price) && Number.isFinite(Number(price)) && Number(price) > 0)
          || comparePrice(row.low, row.open) > 0 || comparePrice(row.low, row.close) > 0
          || comparePrice(row.high, row.open) < 0 || comparePrice(row.high, row.close) < 0
          || row.ma.length !== MA_PERIODS.length) throw new Error("计算K线的原值或周期标记不符");
      if (frequency === "daily") {
        const raw = snapshot.bars[i];
        if (row.start !== raw.trade_date || row.end !== raw.trade_date || row.period_start !== row.start || row.period_end !== row.end
            || row.sample_count !== 1 || (["open", "high", "low", "close"] as const).some(key => row[key] !== raw[key])) {
          throw new Error("计算日线与原始价格不一致");
        }
      }
      checkScalar(row.change_pct, frequency, "1", frequency === "daily" ? "adjacent-expected-close-pct-half-up-v1"
        : "period-close-pct-half-up-v1", row.end, "%", "missing_previous_close");
      row.ma.forEach((item, j) => checkScalar(item, frequency, String(MA_PERIODS[j]), "close-sma-half-up-4-v1", row.end, "点", "insufficient_samples"));
    }
  }
  if (value.daily.rows.at(-1)!.change_pct.value !== snapshot.summary.daily_change_pct) throw new Error("最新涨跌与同快照摘要不一致");
  for (const [key, period] of [["day_5", "5"], ["day_20", "20"], ["day_60", "60"], ["year_1", "1y"]] as const) {
    checkScalar(value.performance[key], "daily", period, period === "1y" ? "natural-year-close-pct-v1" : "trading-window-close-pct-v1",
      snapshot.window.end, "%", period === "1y" ? "missing_year_baseline" : "insufficient_samples");
  }
  return value;
}

/** 图表仅投影服务端原值；无计算输出时仍可展示已取得的原始日K。 */
export type ChartBar = Pick<SeriesSnapshot["bars"][number], "trade_date" | "open" | "high" | "low" | "close"> & {
  start: string; calculation?: CalculationSeries["rows"][number];
};
export function chartBars(snapshot: SeriesSnapshot, series?: CalculationSeries): ChartBar[] {
  return series ? series.rows.map(row => ({ trade_date: row.end, start: row.start,
    open: row.open, high: row.high, low: row.low, close: row.close, calculation: row }))
    : snapshot.bars.map(row => ({ ...row, start: row.trade_date }));
}

/** 百分比的正号与着色只依赖服务端十进制文本，不重新计算或舍入。 */
export function percentDisplay(value: string) {
  const zero = /^-?0\.0+$/.test(value);
  return { text: `${!zero && !value.startsWith("-") ? "+" : ""}${value}%`,
    className: zero ? "m-flat" : value.startsWith("-") ? "m-down" : "m-up" };
}
