import type { components } from "../../../contracts/generated/http";
import type { IndexSeriesClient } from "./indexSeriesClient";
import type { ActivityClient } from "./activityClient";
import { OVERVIEW_INDICES, type OverviewIndexId } from "./indexSeriesTypes";
import { MARKET, LEGACY_MARKET, isMarket, type ActivityId } from "./activityTypes";

type Status = components["schemas"]["OverviewUpdateStatus"];
type Policy = components["schemas"]["OverviewPeriodicPolicy"];
const MIB = 1048576;
const reasons: Record<string, string> = {
  periodic_daily_exhausted: "当天额度不足，未启动新批次", periodic_monthly_exhausted: "本月额度不足，未启动新批次",
  periodic_batch_too_large: "整批补更超过单日额度，须另行批准临时额度，未开始取数",
  periodic_unresolved_batch: "上次更新中断，存在未决请求，暂停新取数", periodic_clock_regressed: "服务时钟回退，暂停取数",
  periodic_update_failed: "本批部分更新未成功，保留已保存数据", periodic_plan_unavailable: "无法安全制定更新计划，暂停取数",
  calendar_uncovered: "交易日历尚未覆盖当前年份，暂停取数", periodic_ledger_invalid: "预算账本无法核验，暂停取数",
};

/** 数字是预算计额，独立于实际响应体大小；不在页面计算金融结果。 */
export function periodicNotice(value: Status, policy: Policy): string {
  const usage = (row: Status["daily"], requests: number, bytes: number) => `${row.requests}/${requests}次，${(row.bytes / MIB).toFixed(3)}/${bytes / MIB}MiB；剩余${Math.max(0, requests-row.requests-value.reserved.requests)}次／${(Math.max(0, bytes-row.bytes-value.reserved.bytes)/MIB).toFixed(3)}MiB`;
  const at = (stamp: string) => new Date(stamp).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
  return `每天北京时间07:00检查 · ${value.state === "running" ? "正在更新" : value.reason ? reasons[value.reason] ?? "更新已暂停，保留已保存数据" : "等候下一次检查"}。`
    + ` 今日${usage(value.daily, policy.daily_requests, policy.daily_bytes)}；本月${usage(value.monthly, policy.monthly_requests, policy.monthly_bytes)}。`
    + (value.reserved.requests ? ` 本批待出站预留${value.reserved.requests}次／${(value.reserved.bytes / MIB).toFixed(3)}MiB。` : "")
    + (value.warning ? " 额度使用已达80%，请留意余量。" : "")
    + (value.resume_at ? ` 预计额度恢复：${at(value.resume_at)}；整批仍须装入可用额度。` : "")
    + ` 下次定时检查：${at(value.next_check_at)}。`;
}

/** 隐藏时暂停观察，回到前台立即核对；取消会清理监听和定时器。 */
function pause(signal: AbortSignal, delay: number): Promise<void> {
  return new Promise(resolve => {
    const done = () => { clearTimeout(timer); signal.removeEventListener("abort", done); document.removeEventListener("visibilitychange", visible); resolve(); };
    const visible = () => { if (!document.hidden) done(); };
    const timer = setTimeout(done, delay);
    signal.addEventListener("abort", done, { once: true });
    document.addEventListener("visibilitychange", visible);
    if (signal.aborted) done();
  });
}

/** 单条串行GET观察链，无五分钟终止；只在完整读取成功后推进版本，迟到旧状态不倒退。 */
export async function watchPeriodicUpdates(price: IndexSeriesClient, activity: ActivityClient | undefined,
  signal: AbortSignal, prices: Map<string, string>, quantities: Map<ActivityId, string>,
  loadPrice: (id: OverviewIndexId) => Promise<string>,
  loadActivity: (id: ActivityId, anchor: string) => Promise<string>,
  notice: (message: string) => void, failed: (id: ActivityId, error: unknown) => void,
  connectActivity?: () => Promise<ActivityClient | undefined>): Promise<void> {
  const policy = price.expected.policy.periodic;
  if (!policy) return;
  let revision = -1, serverDay = "", nextDelay = 0, mayConnect = false;
  while (!signal.aborted && !price.closed) {
    if (nextDelay) await pause(signal, nextDelay);
    if (signal.aborted || price.closed) break;
    nextDelay = 30000;
    if (document.hidden) continue;
    try {
      const state = await price.overviewStatus(signal);
      if (signal.aborted || price.closed) break;
      if (state.revision < revision || state.server_day < serverDay) continue;
      revision = state.revision; serverDay = state.server_day;
      nextDelay = state.state === "running" ? 3000 : 30000;
      notice(periodicNotice(state, policy));
      for (const item of OVERVIEW_INDICES) {
        try {
          const status = await price.status(item.id, signal);
          if (signal.aborted || price.closed) return;
          if (status.stage === "completed" && status.snapshot_id && status.snapshot_id !== prices.get(item.id)) {
            const version = await loadPrice(item.id);
            if (signal.aborted || price.closed) return;
            prices.set(item.id, version);
          }
        } catch (error) { if (!signal.aborted) failed(item.id, error); }
      }
      // 首轮失败后至少经过一次观察间隔；已关闭的身份失配客户端不自动重建。
      if (!activity && connectActivity && mayConnect) {
        try { activity = await connectActivity(); }
        catch (error) { if (!signal.aborted) failed(MARKET, error); }
        if (signal.aborted || price.closed) return;
      }
      mayConnect = true;
      if (activity && !activity.closed) {
        for (const id of [...OVERVIEW_INDICES.map(item => item.id), MARKET, LEGACY_MARKET] as ActivityId[]) {
          const target = isMarket(id) ? (state.market_anchors ? state.market_anchors[id === MARKET ? "sse_szse" : "sse_szse_bse"] : state.market_anchor_date) : prices.get(id);
          if (!target) continue;
          try {
            const version = await activity.currentVersion(id, target, signal);
            if (signal.aborted || price.closed || activity.closed) return;
            if (version && version !== quantities.get(id)) {
              const loaded = await loadActivity(id, isMarket(id) ? target : state.market_anchor_date);
              if (signal.aborted || price.closed || activity.closed) return;
              quantities.set(id, loaded);
            }
          } catch (error) { if (!signal.aborted) failed(id, error); }
        }
      }
    } catch (error) {
      if (!signal.aborted && error instanceof Error && error.message.startsWith("服务时钟")) notice(error.message);
      else if (!signal.aborted) notice("暂时无法核对自动更新状态，保留已保存数据；恢复连接后继续只读核对。");
    }
  }
}
