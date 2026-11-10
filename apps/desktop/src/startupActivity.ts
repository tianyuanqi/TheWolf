import type { ActivityClient } from "./activityClient";
import type { ActivityId } from "./activityTypes";
import { createStartupPriceObservation, type StartupPriceObservation } from "./startupPrices";

/** 同实例有界GET观察；固定目标不从新响应学习，成功加载后才推进去重版本。 */
export async function watchStartupActivity(client: ActivityClient, targets: ReadonlyMap<ActivityId, string>,
  initial: ReadonlyMap<ActivityId, string>, signal: AbortSignal,
  load: (id: ActivityId) => Promise<string>, failed: (id: ActivityId, error: unknown) => void,
  notice: (value: string) => void, state: StartupPriceObservation = createStartupPriceObservation(),
  demanded: (id: ActivityId) => boolean = () => true): Promise<void> {
  const active = [...targets].filter(([id]) => client.expected.startup_series.includes(id));
  if (!active.length || signal.aborted || client.closed) return;
  const versions = new Map(initial);
  const expired = () => Date.now() >= state.deadline;
  while (!signal.aborted && !client.closed && Date.now() < state.deadline) {
    if (state.nextCheckAt > Date.now()) {
      await new Promise<void>(resolve => {
        const done = () => { clearTimeout(timer); signal.removeEventListener("abort", done); resolve(); };
        const timer = setTimeout(done, Math.max(0, Math.min(state.nextCheckAt, state.deadline) - Date.now()));
        signal.addEventListener("abort", done, { once: true });
        if (signal.aborted) done();
      });
    }
    if (signal.aborted || client.closed || Date.now() >= state.deadline) break;
    state.nextCheckAt = Date.now() + 3000;
    notice("正在跟进服务端量额启动结果；页面只读，不发起采集。");
    for (const [id, target] of active) {
      if (expired()) break;
      if (!demanded(id)) continue;
      try {
        const next = await client.currentVersion(id, target, signal);
        // 当前请求可以跨过截止点返回，但不得再启动固定读取或下一系列GET。
        if (signal.aborted || client.closed) return;
        if (expired()) break;
        if (next && versions.get(id) !== next) {
          const received = await load(id);
          if (signal.aborted || client.closed) return;
          if (expired()) break;
          versions.set(id, received);
        }
      } catch (error) {
        if (!signal.aborted) failed(id, error);
      }
    }
    // 网络耗时不形成连续请求；effect重建也沿用原间隔和总限时。
    state.nextCheckAt = Date.now() + 3000;
  }
  if (!signal.aborted && !client.closed) notice("量额自动跟进已暂停；服务可能仍在执行，完成后可重新读取。数据日期以图中标注为准。");
}
