import type { IndexSeriesClient } from "./indexSeriesClient";
import { OVERVIEW_INDICES } from "./indexSeriesTypes";

const ACTIVE = new Set(["preparing", "fetching_csindex", "fetching_cnindex", "fetching_eastmoney", "validating", "publishing"]);
const INTERVAL_MS = 3000;
const OBSERVE_MS = 300000;

/** 同一连接重读共用限时与间隔；版本去重以每轮真正读到的快照为准。 */
export type StartupPriceObservation = { nextCheckAt: number; deadline: number };
export function createStartupPriceObservation(): StartupPriceObservation {
  return { nextCheckAt: 0, deadline: Date.now() + OBSERVE_MS };
}

/** 等待只读观察间隔；取消时同时释放计时器和监听。 */
function pause(signal: AbortSignal, delay: number): Promise<void> {
  return new Promise(resolve => {
    const done = () => { clearTimeout(timer); signal.removeEventListener("abort", done); resolve(); };
    const timer = setTimeout(done, delay);
    signal.addEventListener("abort", done, { once: true });
    if (signal.aborted) done();
  });
}

/**
 * 观察服务端已配置的启动系列，仅GET状态；不发起采集、不读取量额、不认领操作回执。
 * 以成功读取的价格快照编号去重；失败保留旧版，换实例／取消丢弃迟到结果。
 * 观察有界，结束不代表服务端任务已完成或已取消。
 */
export async function watchStartupPrices(client: IndexSeriesClient, signal: AbortSignal,
  published: () => void, notice: (message: string) => void, initialVersions: ReadonlyMap<string, string> = new Map(),
  observation = createStartupPriceObservation()): Promise<void> {
  const targets = OVERVIEW_INDICES.filter(item => client.expected.startup_indices.includes(item.id));
  if (signal.aborted || client.closed) return;
  if (!targets.length) { notice("启动自动更新未启用；当前只读取已保存价格。"); return; }
  const versions = new Map(initialVersions);
  const { deadline } = observation;
  while (!signal.aborted && !client.closed && Date.now() < deadline) {
    if (observation.nextCheckAt > Date.now()) await pause(signal, Math.min(observation.nextCheckAt, deadline) - Date.now());
    if (signal.aborted || client.closed || Date.now() >= deadline) break;
    const states = await Promise.all(targets.map(async item => {
      try { return { item, status: await client.status(item.id, signal) }; }
      catch { return { item, status: undefined }; }
    }));
    if (signal.aborted || client.closed) return;
    // 通知导致effect重建时也保留间隔，失败重读不能形成无间隔请求循环。
    observation.nextCheckAt = Date.now() + INTERVAL_MS;
    let changed = false;
    const messages = states.map(({ item, status }) => {
      if (!status) return `${item.name}：暂时无法读取状态，保留已保存数据`;
      // 只有成功发布的状态可提示刷新；这不是对任何旧请求的精确确认。
      if (status.stage === "completed" && status.snapshot_id) {
        // current固定返回首次观察，status可返回后续观察；获取记录变化不等于价格快照变化。
        const version = status.snapshot_id;
        if (versions.get(item.id) !== version) { versions.set(item.id, version); changed = true; }
      }
      const label = ACTIVE.has(status.stage) ? (status.trigger === "startup" ? "正在自动更新" : "正在更新")
        : status.stage === "failed" || status.stage === "interrupted" ? "更新未成功，保留已保存数据"
        : status.result === "source_not_ready" ? "来源未就绪，保留已保存数据"
        : status.stage === "completed" ? "已有保存结果" : "尚无更新结果";
      return `${item.name}：${label}`;
    });
    notice("启动价格自动更新已配置 · " + messages.join("；"));
    if (changed) published();
  }
  if (!signal.aborted && !client.closed) notice("价格自动跟进已暂停；已显示数据保留，可重新连接核对。此提示不代表服务端更新已停止。");
}
