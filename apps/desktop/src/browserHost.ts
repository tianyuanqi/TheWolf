import { parseDescriptor } from "./apiClient";
import type { ConnectionDescriptor } from "./apiClient";
import { parseActivityDescriptor } from "./activityClient";
import type { IndexDescriptor } from "./indexSeriesClient";
import { parseIndexDescriptor } from "./indexSeriesClient";

/** 只从受控HTML宿主读取冻结配置，不接受URL参数/localStorage连接覆盖。 */
export async function connectionDescriptor(signal: AbortSignal): Promise<ConnectionDescriptor> {
  const response = await fetch("/__wolf/config", { cache: "no-store", credentials: "omit", redirect: "error", signal });
  if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("本机页面尚未配置独立服务");
  const descriptor = parseDescriptor(await response.json());
  if (signal.aborted) throw new DOMException("连接已取消", "AbortError");
  // A fresh root entry may bind only to the validated host. Never rebind an existing fragment.
  if (descriptor.connection_mode === "managed" && location.pathname === "/" && !location.search && !location.hash) {
    const entry = new URLSearchParams({ "wolf-run": descriptor.run_id!, "wolf-instance": descriptor.expected_instance_id!, page: "overview" });
    history.replaceState(null, "", "#" + entry);
  }
  const fragment = new URLSearchParams(location.hash.slice(1));
  const run = fragment.getAll("wolf-run"), instance = fragment.getAll("wolf-instance");
  if (descriptor.connection_mode === "managed" ? run.length !== 1 || instance.length !== 1
      || run[0] !== descriptor.run_id || instance[0] !== descriptor.expected_instance_id : run.length > 0 || instance.length > 0) {
    throw new Error("托管运行身份不符，请从本次日常入口打开；原操作记录仍可复制");
  }
  return descriptor;
}

/** v2可选入口缺失只影响新总览；仍以宿主描述作为期望而非API响应。 */
export async function indexConnectionDescriptor(connection: ConnectionDescriptor, signal: AbortSignal) {
  const response = await fetch("/__wolf/index-config", { cache: "no-store", credentials: "omit", redirect: "error", signal });
  if (response.status === 404) return undefined;
  if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("指数连接配置不可用");
  return parseIndexDescriptor(await response.json(), connection);
}

/** B描述与价格预期同源；可选配置缺失仅影响量额。 */
export async function activityConnectionDescriptor(price: IndexDescriptor, signal: AbortSignal) {
  const response = await fetch("/__wolf/activity-config", { cache: "no-store", credentials: "omit", redirect: "error", signal });
  if (response.status === 404) return undefined;
  if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json")) throw new Error("量额连接配置不可用");
  return parseActivityDescriptor(await response.json(), price);
}
