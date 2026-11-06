import type { components } from "../../../contracts/generated/http";
import { IndexSeriesDescriptor as validDescriptor, IndexSeriesReady as validReady,
  OverviewUpdateStatus as validOverviewStatus, IndexSeriesUpdateStatus as validStatus, IndexSeriesAcceptedOperation as validAccepted, IndexSeriesOperationResult as validOperation,
  IndexSeriesCalculationError as validCalculationError, IndexSeriesError as validError, BusinessError as validBoundaryError } from "../../../contracts/generated/validators.mjs";
import generation from "../../../contracts/generated/manifest.json";
import type { ConnectionDescriptor } from "./apiClient";
import { OVERVIEW_INDICES, parseSeriesView, type OverviewIndexId, type SeriesSnapshot } from "./indexSeriesTypes";
import { CALCULATION_VERSION, parseCalculations } from "./indexCalculationTypes";

import type { Identity } from "./operationSession";

export type IndexDescriptor = components["schemas"]["IndexSeriesDescriptor"];

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
    .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const item of Object.values(value)) freeze(item);
    Object.freeze(value);
  }
  return value;
}

function checkSets(value: Pick<IndexDescriptor, "write_indices" | "startup_indices" | "policy">): void {
  for (const list of [value.write_indices, value.startup_indices, value.policy.source_policy_versions]) {
    if (new Set(list).size !== list.length || stable(list) !== stable([...list].sort())) throw new Error("指数配置集合无效");
  }
  if (!value.startup_indices.every(id => value.write_indices.includes(id))
      || value.policy.network.max_attempts < 0 || value.policy.network.max_bytes < 0) throw new Error("指数配置策略无效");
}

/** 受控宿主预期独立于ready；新旧协议只共享端点和资料范围，不混用配置摘要。 */
export function parseIndexDescriptor(value: unknown, legacy?: ConnectionDescriptor): IndexDescriptor {
  if (!validDescriptor(value) || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(value.endpoint)
      || Number(new URL(value.endpoint).port) > 65535 || value.contract_sha256 !== generation.source_sha256
      || (legacy && (value.endpoint !== legacy.endpoint || value.data_scope_id !== legacy.data_scope_id))) {
    throw new Error("指数连接配置与页面或原连接不匹配");
  }
  checkSets(value);
  const policy = value.policy.periodic;
  if (policy && (![policy.daily_requests, policy.daily_bytes, policy.monthly_requests, policy.monthly_bytes].every(n => Number.isSafeInteger(n) && n > 0)
      || policy.daily_requests > 80 || policy.daily_bytes > 33554432 || policy.monthly_requests > 500 || policy.monthly_bytes > 536870912
      || policy.daily_requests > policy.monthly_requests || policy.daily_bytes > policy.monthly_bytes)) throw new Error("周期额度超出批准策略");
  return freeze(structuredClone(value));
}

export class IndexReadError extends Error {
  constructor(message: string, readonly code: string, readonly status: number) { super(message); }
}

/** v2受控Client：读取与明确写入分离，不透传URL或从响应学习配置。 */
export class IndexSeriesClient {
  private readonly lifetime = new AbortController();
  private constructor(readonly expected: IndexDescriptor, readonly instance: string) {}

  /** 固定预期握手并与已连接的旧协议实例对照；跨根、跨配置、重定向均拒绝。 */
  static async connect(expected: IndexDescriptor, legacyInstance: string, signal: AbortSignal): Promise<IndexSeriesClient> {
    const response = await fetch(expected.endpoint + "/api/index-series/session", {
      credentials: "omit", redirect: "error", cache: "no-store", headers: { "X-Wolf-Client": "1" },
      signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]),
    });
    if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("指数服务未就绪");
    const value: unknown = await response.json();
    if (signal.aborted) throw new DOMException("连接已取消", "AbortError");
    if (!validReady(value)) throw new Error("指数连接协议不匹配");
    checkSets(value);
  const policy = value.policy.periodic;
  if (policy && (![policy.daily_requests, policy.daily_bytes, policy.monthly_requests, policy.monthly_bytes].every(n => Number.isSafeInteger(n) && n > 0)
      || policy.daily_requests > 80 || policy.daily_bytes > 33554432 || policy.monthly_requests > 500 || policy.monthly_bytes > 536870912
      || policy.daily_requests > policy.monthly_requests || policy.daily_bytes > policy.monthly_bytes)) throw new Error("周期额度超出批准策略");
    const { endpoint: _endpoint, ...identity } = expected;
    const { instance_id, status: _status, ...actual } = value;
    if (stable(actual) !== stable(identity) || instance_id !== legacyInstance
        || response.headers.get("X-Wolf-Instance") !== instance_id
        || response.headers.get("X-Wolf-Config") !== expected.config_id) throw new Error("指数服务实例或冻结配置不匹配，请重新连接");
    return new IndexSeriesClient(expected, instance_id);
  }

  /** 获取当前完整快照后，列表、迷你走势与详情共用该对象；交互不会重新读取current。 */
  async current(indexId: OverviewIndexId, signal: AbortSignal) {
    if (!OVERVIEW_INDICES.some(item => item.id === indexId)) throw new Error("未登记的总览指数");
    return parseSeriesView(await this.read("/api/index-series/" + encodeURIComponent(indexId), signal, 8000), indexId);
  }

  /** 只读已取得快照的指定公式版本；不随current变化重试，不从响应接受地址。 */
  async calculations(snapshot: SeriesSnapshot, signal: AbortSignal) {
    if (!OVERVIEW_INDICES.some(item => item.id === snapshot.instrument.id) || !/^[a-f0-9]{64}$/.test(snapshot.snapshot_id)) {
      throw new Error("未登记的指数或快照");
    }
    const path = "/api/index-series/" + encodeURIComponent(snapshot.instrument.id) + "/snapshots/"
      + snapshot.snapshot_id + "/calculations?formula_version=" + CALCULATION_VERSION;
    return parseCalculations(await this.read(path, signal, 30000, true), snapshot);
  }

  /** 同实例只读调度状态；动态日期不能授予新权限或改变受控配置。 */
  async overviewStatus(signal: AbortSignal) {
    if (!this.expected.policy.periodic) throw new Error("周期更新未配置");
    const value = await this.read("/api/overview-update/status", signal, 8000);
    if (!validOverviewStatus(value) || value.market_anchor_date > value.server_day
        || ![value.daily, value.monthly, value.reserved].every(row => [row.requests, row.bytes].every(n => Number.isSafeInteger(n) && n >= 0))
        || !Number.isSafeInteger(value.revision) || value.revision < 0) throw new Error("周期更新状态无效");
    return value;
  }

  /** 当前业务状态不能替代原请求的精确关联结果。 */
  async status(id: OverviewIndexId, signal: AbortSignal) {
    const value = await this.read(`/api/index-series/${encodeURIComponent(id)}/update`, signal, 8000);
    if (!validStatus(value) || value.index_id !== id) throw new Error("指数更新状态归属无效");
    return value;
  }

  /** 明确的一次POST，无自动重试；结果不确定时仅查询原身份。 */
  async startUpdate(identity: Identity, signal: AbortSignal) {
    const id = identity.index_id as OverviewIndexId;
    if (identity.operation !== "index.series.update" || identity.instance_id !== this.instance || identity.config_id !== this.expected.config_id
        || !this.expected.write_indices.includes(id) || !OVERVIEW_INDICES.some(x => x.id === id)) throw new Error("指数更新未获受控许可");
    const value = await this.read(`/api/index-series/${encodeURIComponent(id)}/update`, signal, 8000, false, identity.request_id);
    if (!validAccepted(value)) throw new Error("指数受理响应无效，结果待确认");
    return this.parseOperation(value, identity);
  }

  /** GET始终携带旧完整身份；新业务状态不能认领旧请求。 */
  async operation(identity: Identity, signal: AbortSignal) {
    if (identity.operation !== "index.series.update" || !OVERVIEW_INDICES.some(x => x.id === identity.index_id)) throw new Error("指数查询目标无效");
    const query = new URLSearchParams({ instance_id: identity.instance_id, config_id: identity.config_id, operation: identity.operation, index_id: identity.index_id! });
    return this.parseOperation(await this.read(`/api/index-series/operations/${encodeURIComponent(identity.request_id)}?${query}`, signal, 8000), identity);
  }

  private parseOperation(value: unknown, identity: Identity) {
    if (!validOperation(value)) throw new Error("指数关联响应契约无效");
    for (const key of ["instance_id", "config_id", "request_id", "operation", "index_id"] as const) if (value[key] !== identity[key]) throw new Error("指数关联身份不符");
    const status = value.business_status;
    if (value.state === "unknown") {
      if (status !== null || value.job_id !== null || value.rejection !== null || value.reused_job !== null) throw new Error("未知结果包含结论");
    } else if (value.state === "rejected") {
      if (!value.rejection || status !== null || value.job_id !== null || value.reused_job !== null) throw new Error("拒绝结果无效");
    } else {
      if (!status || status.index_id !== identity.index_id || !value.job_id || status.job_id !== value.job_id || value.reused_job === null || value.rejection !== null) throw new Error("指数job归属无效");
      if (["completed", "failed", "interrupted"].includes(value.state)) {
        const results = value.state === "completed" ? ["business_changed", "evidence_changed", "unchanged", "source_not_ready"] : [value.state];
        if (status.stage !== value.state || !results.includes(String(status.result))) throw new Error("指数终态矛盾");
      } else if (["idle", "completed", "failed", "interrupted"].includes(status.stage)) throw new Error("活动任务矛盾");
    }
    return value;
  }

  private async read(path: string, signal: AbortSignal, timeout: number, calculation = false, requestId?: string): Promise<unknown> {
    if (signal.aborted || this.closed) throw new DOMException("读取已取消", "AbortError");
    const response = await fetch(this.expected.endpoint + path, {
      method: requestId ? "POST" : undefined, body: requestId ? "{}" : undefined,
      credentials: "omit", redirect: "error", cache: "no-store",
      headers: { "X-Wolf-Client": "1", "X-Wolf-Expected-Instance": this.instance, "X-Wolf-Expected-Config": this.expected.config_id, ...(requestId ? { "Content-Type": "application/json", "X-Wolf-Request-Id": requestId } : {}) },
      signal: AbortSignal.any([signal, this.lifetime.signal, AbortSignal.timeout(timeout)]),
    });
    if (response.headers.get("X-Wolf-Instance") !== this.instance || response.headers.get("X-Wolf-Config") !== this.expected.config_id) {
      this.close(); throw new Error("响应不属于当前指数连接，请重新连接");
    }
    if (!response.headers.get("content-type")?.startsWith("application/json")) throw new Error("指数响应媒体类型不匹配");
    const value: unknown = await response.json();
    if (signal.aborted || this.closed) throw new DOMException("读取已取消", "AbortError");
    if (!response.ok) {
      const detail = validBoundaryError(value) ? value.detail : calculation && validCalculationError(value) ? value.detail
        : !calculation && validError(value) ? value.detail : undefined;
      if (!detail) throw new Error("指数错误响应契约不符");
      const { code, message } = detail;
      if (code === "connection_context_mismatch") this.close();
      throw new IndexReadError(message, code, response.status);
    }
    return value;
  }

  get closed(): boolean { return this.lifetime.signal.aborted; }
  /** 取消本连接未完成读取，不触碰后端进程或业务数据。 */
  close(): void { this.lifetime.abort(); }
}
