import type { components } from "../../../contracts/generated/http";
import { Ready as validReady } from "../../../contracts/generated/validators.mjs";
import generation from "../../../contracts/generated/manifest.json";

type Ready = components["schemas"]["Ready"];
export type ConnectionDescriptor = Omit<Ready, "instance_id" | "status"> & { endpoint: string; connection_mode?: "managed"; run_id?: string; expected_instance_id?: string };

/** 校验宿主提供的公开预期；从未使用ready反向构造预期。 */
export function parseDescriptor(value: unknown): ConnectionDescriptor {
  if (!value || typeof value !== "object") throw new Error("本机连接配置缺失");
  const { endpoint, connection_mode, run_id, expected_instance_id, ...expected } = value as Record<string, unknown>;
  const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
  if ([connection_mode, run_id, expected_instance_id].some(x => x !== undefined)
      && (connection_mode !== "managed" || typeof run_id !== "string" || !uuid.test(run_id)
      || typeof expected_instance_id !== "string" || !uuid.test(expected_instance_id))) throw new Error("托管身份必须完整");
  if (typeof endpoint !== "string" || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(endpoint)
      || Number(new URL(endpoint).port) > 65535
      || !validReady({ ...expected, status: "ready", instance_id: "00000000-0000-4000-8000-000000000000" })
      || expected.contract_sha256 !== generation.source_sha256) throw new Error("本机连接配置与此页面版本不匹配");
  const descriptor = value as ConnectionDescriptor;
  return Object.freeze({ ...descriptor });
}

/** 总览共用的连接握手；不包含业务更新或旧切片接口。 */
export class ApiClient {
  private readonly lifetime = new AbortController();

  private constructor(readonly expected: ConnectionDescriptor, readonly instance: string) {}

  /** 在固定端点核对协议、范围、配置及公开实例，禁止重定向或端口发现。 */
  static async connect(expected: ConnectionDescriptor, signal: AbortSignal): Promise<ApiClient> {
    const response = await fetch(expected.endpoint + "/api/session/ready", {
      headers: { "X-Wolf-Client": "1" }, credentials: "omit", redirect: "error", cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(8000)]),
    });
    if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("本地服务未就绪");
    const value: unknown = await response.json();
    if (signal.aborted) throw new DOMException("连接已取消", "AbortError");
    if (!validReady(value)) throw new Error("服务连接协议不匹配");
    for (const key of ["service_id", "service_version", "contract_version", "contract_sha256", "identity_format", "data_scope_id", "config_id"] as const) {
      if (value[key] !== expected[key]) throw new Error("服务配置或资料目录不匹配，请检查启动配置");
    }
    if ((expected.connection_mode === "managed" && value.instance_id !== expected.expected_instance_id)
        || response.headers.get("X-Wolf-Instance") !== value.instance_id
        || response.headers.get("X-Wolf-Config") !== expected.config_id) throw new Error("服务实例响应不匹配");
    return new ApiClient(expected, value.instance_id);
  }

  /** 连接失效后只能重新握手，不复活旧Client。 */
  get closed(): boolean { return this.lifetime.signal.aborted; }

  /** 断开本连接代次；业务读取由各特性Client取消。 */
  close(): void { this.lifetime.abort(); }
}
