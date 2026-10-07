export type IndexBar = { trade_date: string; open: string; high: string; low: string; close: string;
  evidence_refs: { object_id: string; locator: string }[] };
export type IndexView = { schema_version: string; snapshot_id: string; observation_id: string;
  instrument: { id: string; name: string; code: string }; unit: string; timezone: string; pit_grade: string;
  calendar_dates: string[]; bars: IndexBar[];
  window: { start: string; end: string; expected_count: number; actual_count: number };
  summary: { trade_date: string; close: string; daily_change_pct: string | null; reason: string | null };
  source_contract: { version: string };
  evidence: { source: string; object_id: string; url: string }[] };
export type IndexStatus = { enabled: boolean; stage: string; job_id?: string | null; result?: string | null;
  message?: string | null; last_success_at?: string | null; started_at?: string | null; snapshot_id?: string | null };
export type IndexEvidence = { snapshot_id: string; observation_id: string; source: string; object_id: string; url: string;
  rows: { trade_date: string; open: string; high: string; low: string; close: string; locator: string;
    raw_values: Record<string, string> }[];
  retrieval: { started_at: string; completed_at: string; published_at: null };
  verification: string; unused_fields: string[]; text_preview: string; preview_truncated: boolean };

const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;
const id = (value: unknown) => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const day = (value: unknown) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
const point = (value: unknown) => typeof value === "string" && /^\d+\.\d{2}$/.test(value) && Number(value) > 0;

/** 本地接口也做运行时契约核对，禁止将错误结构当作真实金融视图。 */
export function parseIndexView(value: unknown): IndexView {
  if (!object(value) || value.schema_version !== "csi300-price-snapshot-v1" || !id(value.snapshot_id)
      || !id(value.observation_id) || !object(value.instrument) || value.instrument.id !== "csi:000300:price"
      || value.instrument.code !== "000300" || value.instrument.name !== "沪深300" || value.unit !== "点"
      || value.timezone !== "Asia/Shanghai" || value.pit_grade !== "latest_only" || !object(value.window)
      || value.window.actual_count !== 260 || value.window.expected_count !== 260 || !Array.isArray(value.bars)
      || value.bars.length !== 260 || !Array.isArray(value.calendar_dates) || value.calendar_dates.length !== 260
      || !object(value.summary) || !day(value.summary.trade_date) || !point(value.summary.close)
      || !(value.summary.daily_change_pct === null || (typeof value.summary.daily_change_pct === "string"
          && /^-?\d+\.\d{2}$/.test(value.summary.daily_change_pct)))
      || !Array.isArray(value.evidence) || value.evidence.length !== 2
      || !object(value.source_contract) || !["csi300-exact-ohlc-v1", "csi300-tencent-exact-ohlc-v2"].includes(String(value.source_contract.version))
      || !value.evidence.every(item => object(item) && id(item.object_id) && typeof item.url === "string"
        && ["eastmoney", "tencent", "csindex"].includes(String(item.source)))) throw new Error("指数视图契约不符");
  const evidenceItems = value.evidence as Record<string, unknown>[];
  const primary = value.source_contract.version === "csi300-exact-ohlc-v1" ? "eastmoney" : "tencent";
  if (evidenceItems[0].source !== primary || evidenceItems[1].source !== "csindex"
      || evidenceItems[0].object_id === evidenceItems[1].object_id) throw new Error("指数双源身份不符");
  let previous = "";
  for (const [index, bar] of value.bars.entries()) {
    if (!object(bar) || !day(bar.trade_date) || String(bar.trade_date) <= previous || bar.trade_date !== value.calendar_dates[index]
        || ![bar.open, bar.high, bar.low, bar.close].every(point)
        || Number(bar.low) > Math.min(Number(bar.open), Number(bar.close))
        || Number(bar.high) < Math.max(Number(bar.open), Number(bar.close))
        || !Array.isArray(bar.evidence_refs) || bar.evidence_refs.length !== 2
        || new Set(bar.evidence_refs.map(ref => object(ref) ? ref.object_id : null)).size !== 2
        || !bar.evidence_refs.every(ref => object(ref) && evidenceItems.some(item => item.object_id === ref.object_id)
          && typeof ref.locator === "string")) throw new Error("指数日线契约不符");
    previous = String(bar.trade_date);
  }
  const bars = value.bars as IndexBar[];
  if (value.window.start !== bars[0].trade_date || value.window.end !== previous || value.summary.trade_date !== previous
      || value.summary.close !== bars.at(-1)!.close) throw new Error("指数摘要与范围不符");
  return value as unknown as IndexView;
}

/** 核对固定证据身份和逐日原值，迟到或跨快照响应不能进入面板。 */
export function parseIndexEvidence(value: unknown, view: IndexView, objectId: string): IndexEvidence {
  const member = view.evidence.find(item => item.object_id === objectId);
  if (!object(value) || value.snapshot_id !== view.snapshot_id || value.observation_id !== view.observation_id
      || !member || value.source !== member.source || value.url !== member.url
      || value.object_id !== objectId || !object(value.retrieval) || typeof value.retrieval.completed_at !== "string"
      || typeof value.retrieval.started_at !== "string" || value.retrieval.published_at !== null
      || !Array.isArray(value.rows) || value.rows.length !== view.bars.length || !value.rows.every((row, index) => object(row) && day(row.trade_date)
        && row.trade_date === view.bars[index].trade_date
        && ["open", "high", "low", "close"].every(field => row[field] === view.bars[index][field as keyof IndexBar])
        && [row.open, row.high, row.low, row.close].every(point) && typeof row.locator === "string" && object(row.raw_values)
        && ["open", "high", "low", "close"].every(field => typeof (row.raw_values as Record<string, unknown>)[field] === "string"))
      || typeof value.url !== "string" || typeof value.source !== "string" || typeof value.verification !== "string"
      || !Array.isArray(value.unused_fields) || !value.unused_fields.every(item => typeof item === "string")
      || typeof value.preview_truncated !== "boolean" || typeof value.text_preview !== "string") throw new Error("固定证据契约不符");
  return value as unknown as IndexEvidence;
}

/** 核对任务状态，未知阶段不能被推定为成功终态。 */
export function parseIndexStatus(value: unknown): IndexStatus {
  if (!object(value) || typeof value.enabled !== "boolean" || typeof value.stage !== "string"
      || !["idle", "preparing", "fetching_eastmoney", "fetching_tencent", "fetching_csindex", "validating", "publishing", "completed", "failed", "interrupted"].includes(value.stage)
      || (value.job_id != null && typeof value.job_id !== "string")
      || (value.message != null && typeof value.message !== "string")
      || (value.result != null && !["business_changed", "evidence_changed", "unchanged", "source_not_ready", "failed", "interrupted"].includes(String(value.result)))
      || (value.stage === "completed" && !["business_changed", "evidence_changed", "unchanged", "source_not_ready"].includes(String(value.result)))
      || (value.snapshot_id != null && !id(value.snapshot_id))
      || (value.last_success_at != null && typeof value.last_success_at !== "string")) throw new Error("指数任务状态契约不符");
  return value as unknown as IndexStatus;
}
