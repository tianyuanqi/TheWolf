import { activityReason, activityPolicyKeys, type ActivityDescriptor, type ActivityId } from "./activityTypes";
import type { ActivityRange } from "./storedViews";

/** 来源与固定引用只作文本展示；明示所选范围，不把裁剪结果说成完整发布。 */
export function ActivityDetails({ id, descriptor, view, error }: {
  id: ActivityId; descriptor?: ActivityDescriptor; view?: ActivityRange; error?: string;
}) {
  const rules = descriptor?.policy.sources.filter(rule => activityPolicyKeys(id).includes(rule.series)) ?? [];
  return <div className="m-activity-details">
    <p>量额：{error ? `暂无数据 · ${error}` : view ? "已保存固定版本" : "暂无数据"} · 未经双源核验</p>
    {rules.map(rule => <p key={rule.series}>{rule.series} · 来源 {rule.source} · 范围 {rule.scope}<br />
      金额原始单位 {rule.amount_unit}、精度 {rule.amount_quantum} {rule.amount_unit}；成交量 {rule.volume_unit ?? "不提供"}。
      {rule.admitted ? "已准入" : `未准入：${rule.gaps.join("、") || "证据不足"}`}</p>)}
    <p>量额按官方单源提供，未经双源核验；价格仍按双源标准。交易方式范围等未核实事项继续保留，未准入／撤回不出数，缺日、缺市场不补零。全市场仅成交额，不由四指数相加。</p>
    {view && <>
      <p>量额版本：{view.activity_id}<br />价格版本：{view.price_snapshot_id ?? "不适用（独立全市场序列）"}<br />
        计算公式：{view.formula_version}<br />完整发布覆盖：{view.source_coverage.start} 至 {view.source_coverage.end}<br />
        本次显示请求：{view.requested_range.start} 至 {view.requested_range.end}</p>
      <p>来源覆盖：{view.source_scope}<br />来源修订一致性未知。当前取得历史版本，非当时可知回放。</p>
      {view.binding && <p>价格与量额配对：{view.binding.relation === "same_source_object" ? "来自同一原件" : "来自不同原件，已核对可用价格原值一致"}<br />
        价格原件：{view.binding.price_object_id}<br />量额原件：{view.binding.activity_object_id}</p>}
      {view.sources.map(source => <p key={source.object_id}>{source.source} · {source.url}<br />原件引用：{source.object_id}<br />获取时间：{source.completed_at}</p>)}
      <p>观察：{view.observation_id}</p>
      <p>所选范围缺失周期：{view.series.rows.filter(row => row.total.value === null).map(row => `${row.start} 至 ${row.end}（${activityReason(row.total.reason)}）`).join("；") || "无"}</p>
    </>}
  </div>;
}
