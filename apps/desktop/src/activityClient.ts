/** B连接协议；仅提供受控身份与读取能力，供P3只读展示，不计算金融结果。 */
import type { components } from "../../../contracts/generated/http";
import { MarketActivityDescriptor as validDescriptor, MarketActivityReady as validReady,
  MarketActivitySnapshot as validSnapshot, MarketActivityCurrent as validCurrent, MarketActivityError as validError,
  MarketActivityOperation as validOperation, BusinessError as validBoundaryError,
  MarketActivityCalculations as validCalculations, MarketActivityEvidence as validEvidence } from "../../../contracts/generated/validators.mjs";
import generation from "../../../contracts/generated/manifest.json";
import type { IndexDescriptor } from "./indexSeriesClient";

import { isMarket, activityFormula, activityGate, activityReason, type ActivityId } from "./activityTypes";
import { validDay } from "./indexSeriesTypes";


import type { Identity } from "./operationSession";
import { identityKey } from "./operationSession";

type Descriptor = components["schemas"]["MarketActivityDescriptor"];
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${JSON.stringify(k)}:${stable(v)}`).join(",")}}`;
  return JSON.stringify(value);
}
function freeze<T>(value: T): T {
  if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}

/** 预期来自受控宿主；不得以ready响应或页面参数生成预期。 */
export function parseActivityDescriptor(value: unknown, price: IndexDescriptor): Descriptor {
  if (!validDescriptor(value) || value.contract_sha256 !== generation.source_sha256
      || value.endpoint !== price.endpoint || value.data_scope_id !== price.data_scope_id
      || value.price_index_config_id !== price.config_id || value.policy.network.max_attempts < 0
      || value.policy.network.max_bytes < 0
      || new Set(value.startup_series).size !== value.startup_series.length
      || !value.startup_series.every(id => value.write_series.includes(id))
      || new Set(value.series).size !== value.series.length
      || new Set(value.write_series).size !== value.write_series.length
      || !value.write_series.every(s => value.series.includes(s))) throw new Error("量额连接预期不匹配");
  return freeze(structuredClone(value));
}

export class ActivityReadError extends Error {
  constructor(readonly code: string) { super(activityReason(code)); }
}

export class ActivityClient {
  private readonly lifetime = new AbortController();
  private readonly recovery = new Set<string>();
  get closed(): boolean { return this.lifetime.signal.aborted; }
  close(): void { this.lifetime.abort(); }

  private async request(path: string, signal: AbortSignal, identity?: Identity): Promise<unknown> {
    const response = await fetch(this.expected.endpoint + path, {
      method: identity ? "POST" : undefined, body: identity ? JSON.stringify(identity.parameters) : undefined,
      credentials: "omit", redirect: "error", cache: "no-store",
      signal: AbortSignal.any([signal, this.lifetime.signal, AbortSignal.timeout(30000)]),
      headers: { "X-Wolf-Client": "1", "X-Wolf-Expected-Instance": this.instance, "X-Wolf-Expected-Config": this.expected.config_id, ...(identity ? { "Content-Type": "application/json", "X-Wolf-Request-Id": identity.request_id } : {}) },
    });
    if (response.headers.get("X-Wolf-Instance") !== this.instance || response.headers.get("X-Wolf-Config") !== this.expected.config_id) {
      this.close(); throw new Error("量额连接身份改变，请重新连接");
    }
    if (!response.headers.get("content-type")?.startsWith("application/json")) throw new Error("量额响应媒体无效");
    const value: unknown = await response.json();
    if (signal.aborted || this.lifetime.signal.aborted) throw new DOMException("读取已取消", "AbortError");
    if (!response.ok) {
      if (!validError(value) && !validBoundaryError(value)) throw new Error("量额错误响应契约不符");
      if (value.detail.code === "connection_context_mismatch") this.close();
      throw new ActivityReadError(value.detail.code);
    }
    return value;
  }

  /** 启动观察只查询固定目标，缺失返回undefined，不获取完整快照或触发更新。 */
  async currentVersion(id: ActivityId, target: string, signal: AbortSignal): Promise<string | undefined> {
    const gate = activityGate(this.expected, id);
    if (gate) throw new Error(gate);
    const key = isMarket(id) ? "anchor_date" : "price_snapshot_id";
    try {
      const value = await this.request(`/api/market-activity/${encodeURIComponent(id)}?${key}=${encodeURIComponent(target)}`, signal);
      if (!validCurrent(value) || value.series_id !== id || (isMarket(id) ? value.anchor_date : value.price_snapshot_id) !== target) throw new Error("量额目标不符");
      return value.activity_id;
    } catch (error) {
      if (error instanceof ActivityReadError && error.code === "activity_not_found") return undefined;
      throw error;
    }
  }

  /** 仅取得CAS前提；缺失可明确使用null，其他拒绝不能当作空。 */
  async updateParameters(id: ActivityId, target: string, signal: AbortSignal) {
    const key = isMarket(id) ? "anchor_date" : "price_snapshot_id";
    let expected: string | null = null;
    try {
      const value = await this.request(`/api/market-activity/${encodeURIComponent(id)}?${key}=${encodeURIComponent(target)}`, signal);
      if (!validCurrent(value) || value.series_id !== id || (isMarket(id) ? value.anchor_date : value.price_snapshot_id) !== target) throw new Error("量额目标不符");
      expected = value.activity_id;
    } catch (error) { if (!(error instanceof ActivityReadError) || error.code !== "activity_not_found") throw error; }
    return isMarket(id) ? { anchor_date: target, expected_activity_id: expected } : { price_snapshot_id: target, expected_activity_id: expected };
  }

  private async operationResult(value: unknown, identity: Identity, recovering = false) {
    if (!validOperation(value) || value.request_id !== identity.request_id || value.config_id !== identity.config_id || value.series_id !== identity.series_id
        || value.target !== (identity.parameters && ("price_snapshot_id" in identity.parameters ? identity.parameters.price_snapshot_id : identity.parameters.anchor_date))) throw new Error("量额操作目标不符");
    const input = stable({ series: identity.series_id, parameters: identity.parameters });
    const signature = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input)))].map(x => x.toString(16).padStart(2, "0")).join("");
    if (value.signature !== signature || (recovering ? value.instance_id !== this.instance || value.recovered_from_instance !== identity.instance_id : value.instance_id !== identity.instance_id)) throw new Error("量额操作身份不符，仍待确认");
    return value;
  }

  /** 明确更新或明确恢复；恢复许可只由本连接实际GET错误建立，不能从导入文本授予。 */
  async startUpdate(identity: Identity, signal: AbortSignal, recovering = false) {
    const id = identity.series_id as ActivityId;
    if (identity.operation !== "market.activity.update" || identity.config_id !== this.expected.config_id || !this.expected.write_series.includes(id)
        || activityGate(this.expected, id) || !identity.parameters || (recovering ? !this.recovery.has(identityKey(identity)) : identity.instance_id !== this.instance)) throw new Error("量额更新或恢复未获许可");
    this.recovery.delete(identityKey(identity));
    return this.operationResult(await this.request(`/api/market-activity/${encodeURIComponent(id)}/update`, signal, identity), identity, recovering);
  }

  /** 未确认归属时只保留未知；GET不能恢复持久记录。 */
  async operation(identity: Identity, signal: AbortSignal) {
    if (identity.operation !== "market.activity.update" || identity.config_id !== this.expected.config_id || !this.expected.series.includes(identity.series_id as ActivityId)) throw new Error("量额原配置不匹配，无法核对");
    try {
      const value = await this.request(`/api/market-activity/operations/${encodeURIComponent(identity.request_id)}?series_id=${encodeURIComponent(identity.series_id!)}`, signal);
      return await this.operationResult(value, identity, identity.instance_id !== this.instance);
    } catch (error) {
      if (error instanceof ActivityReadError && error.code === "activity_recovery_required") this.recovery.add(identityKey(identity));
      throw error;
    }
  }

  async storedView(id: ActivityId, query: Record<string, string>, signal: AbortSignal): Promise<unknown> {
    const gate = activityGate(this.expected, id);
    if (gate) throw new Error(gate);
    return this.request(`/api/market-activity/${encodeURIComponent(id)}/view?${new URLSearchParams(query)}`, signal);
  }

  private constructor(readonly expected: Descriptor, readonly instance: string, readonly marketAnchor: string, readonly marketAnchors?: components["schemas"]["MarketActivityAnchors"]) {}

  /** 新身份独立握手，同时核对价格连接实例；不降级使用旧摘要。 */
  static async connect(expected: Descriptor, priceInstance: string, signal: AbortSignal): Promise<ActivityClient> {
    const response = await fetch(expected.endpoint + "/api/market-activity/session", {
      credentials: "omit", redirect: "error", cache: "no-store", headers: { "X-Wolf-Client": "1" }, signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]),
    });
    if (response.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json") throw new Error("量额响应媒体无效");
    const value: unknown = await response.json();
    if (signal.aborted) throw new DOMException("连接已取消", "AbortError");
    if (!response.ok || !validReady(value)) throw new Error("量额服务不可用");
    const { endpoint: _endpoint, ...identity } = expected;
    const { status: _status, instance_id, market_anchor_date, market_anchors, ...actual } = value;
    if (!validDay(market_anchor_date) || stable(actual) !== stable(identity) || instance_id !== priceInstance
        || response.headers.get("X-Wolf-Config") !== expected.config_id
        || response.headers.get("X-Wolf-Instance") !== instance_id) throw new Error("量额服务身份已改变");
    return new ActivityClient(expected, instance_id, market_anchor_date, market_anchors);
  }

  /** 有界固定读取，拒绝跨系列/快照返回；不提供任意URL与隐式重连。 */
  async read(series: Descriptor["series"][number], activityId: string, priceSnapshotId: string | null, kind: "fixed" | "calculations" | "evidence",
             signal: AbortSignal, objectId?: string) {
    if (!this.expected.series.includes(series) || !/^[a-f0-9]{64}$/.test(activityId)
        || (isMarket(series) ? priceSnapshotId !== null : !priceSnapshotId || !/^[a-f0-9]{64}$/.test(priceSnapshotId))
        || (kind === "evidence" && (!objectId || !/^[a-f0-9]{64}$/.test(objectId)))) throw new Error("量额固定引用无效");
    const suffix = kind === "fixed" ? "" : kind === "calculations" ? `/calculations?formula_version=${activityFormula(series)}` : `/evidence/${objectId}`;
    const value = await this.request(`/api/market-activity/${encodeURIComponent(series)}/snapshots/${activityId}${suffix}`, signal);
    const valid = kind === "fixed" ? validSnapshot : kind === "calculations" ? validCalculations : validEvidence;
    if (signal.aborted || !valid(value) || value.series_id !== series || value.activity_id !== activityId || value.price_snapshot_id !== priceSnapshotId
        || (kind === "evidence" && "object_id" in value && value.object_id !== objectId)) throw new Error("量额响应归属无效");
    if ("observations" in value && value.observations.some(observation => observation.series_id !== series
        || observation.activity_id !== activityId || observation.price_snapshot_id !== priceSnapshotId
        || (kind === "evidence" && !observation.sources.some(source => source.object_id === objectId)))) throw new Error("量额观察归属无效");
    return value;
  }
}
