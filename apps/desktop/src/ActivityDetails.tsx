import { activityReason, MARKET, activityPolicyKeys, type ActivityBundle, type ActivityDescriptor, type ActivityId } from "./activityTypes";

/** 原始来源、精度与固定输入只作文本展示，不打开任意来源URL或执行原件内容。 */
export function ActivityDetails({ id, descriptor, bundle, error, anchor }: {
  id: ActivityId; descriptor?: ActivityDescriptor; bundle?: ActivityBundle; error?: string; anchor?: string;
}) {
  const rules = descriptor?.policy.sources.filter(rule => activityPolicyKeys(id).includes(rule.series)) ?? [];
  const snapshot = bundle?.snapshot;
  return <div className="m-activity-details">
    <p>量额：{error ? `暂无数据 · ${error}` : snapshot ? "已保存固定快照" : "暂无数据"}{anchor && ` · 查询锚点 ${anchor}`} · 未经双源核验</p>
    {rules.map(rule => <p key={rule.series}>{rule.series} · 来源 {rule.source} · 范围 {rule.scope}<br />
      金额原始单位 {rule.amount_unit}、精度 {rule.amount_quantum} {rule.amount_unit}；成交量 {rule.volume_unit ?? "不提供"}。
      {rule.admitted ? "已准入" : `未准入：${rule.gaps.join("、") || "证据不足"}`}</p>)}
    <p>量额按官方单源提供，未经双源核验；价格仍按双源标准。交易方式范围等未核实事项继续保留，未准入／撤回不出数，缺日、缺市场不补零。全市场仅成交额，不由四指数相加。</p>
    {snapshot && <>
      <p>量额快照：{snapshot.activity_id}<br />价格快照：{snapshot.price_snapshot_id ?? "不适用（独立全市场序列）"}<br />
        计算公式：{bundle.calculations.formula_version}<br />量额范围：{snapshot.source_scope}；{snapshot.window.start} 至 {snapshot.window.end}</p>
      <p>来源修订一致性未知；{snapshot.binding?.relation === "same_source_object" ? "双方使用同一原件" : snapshot.binding ? "不同原件的可得OHLC原值已精确比较" : "全市场独立来源"}。当前取得历史版本，非当时可知回放。</p>
      {snapshot.sources.map(source => <p key={source.object_id}>{source.source} · {source.url}<br />原件引用：{source.object_id}</p>)}
      {snapshot.observations.map(observation => <p key={observation.observation_id}>观察 {observation.observation_id}：{observation.sources.map(source => `${source.source} ${source.completed_at}`).join("；")}</p>)}
      {"market_calendars" in snapshot && <p>缺失市场／日期：{snapshot.rows.flatMap(row => "components" in row
        ? Object.entries(row.components).flatMap(([market, parts]) => parts.some(part => part.value === null) ? [`${row.trade_date} ${market}（${activityReason(parts.find(part => part.value === null)?.reason)}）`] : []) : []).join("；") || "无"}</p>}
    </>}
  </div>;
}
