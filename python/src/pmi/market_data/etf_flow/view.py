"""正式页面的固定快照投影；原记录空缺保持空缺，单只事后资料明确另标。"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, localcontext
from typing import Any

from .calendar import preceding_window
from .calculation import Calculator, Metrics, cumulative, streak
from .evidence import Evidence
from .context import select as select_context
from .model import Configuration, FlowError, FORMULA_VERSION, SHANGHAI, adjustment_for, day, digest, instant, number
from .repository import Loaded, Repository

PERIODS = (20, 60, 120, 260)


def _metrics(calc: Calculator, member: str, on: str) -> Metrics:
    if on in calc.positions and on <= calc.end:
        return calc.metrics(member, on)
    return {"date": on, "shares": None, "comparable_previous": None, "delta": None, "change_rate": None,
            "amount": None, "nav": None, "close": None, "turnover": None, "volume": None,
            "net_assets": None, "premium": None, "turnover_ratio": None, "adjustment": False, "reason": "input_missing"}


def _original_material(repository: Repository, loaded: Loaded, end: str, period: int,
                       group: str | None) -> tuple[Calculator, Evidence, str] | None:
    """所选原记录的单只数据和事件也必须回到原版本，不能拼入最新修订。"""
    for ref in loaded.manifest["signal_refs"]:
        record = repository._signal(ref)
        if record["date"] != end:
            continue
        config = Configuration.parse(repository.store.get_json(record["configuration_ref"]))
        evidence = Evidence.parse(repository.store.get_json(record["evidence_ref"]), {m.id for p in config.pools for m in p.members})
        calc = repository.window_calculator(config, evidence, record['admission_refs'], record['dataset_ref'],
            selection_at=record['recorded_at'], end=end, view_end=end, period=period, group=group, original=True)
        return calc, evidence, record['context_ref']
    return None


def build(repository: Repository, snapshot: str, *, mode: str, period: int, end: str | None,
          group: str | None, server_day: str) -> dict[str, Any]:
    """只读计算与已存档案；不补信号、不改选择时刻、不依赖当前网络。"""
    if mode not in {"current", "original"} or type(period) is not int or period not in PERIODS:
        raise FlowError("etf_invalid_view", 422)
    loaded = repository.load(snapshot, verify=False, window=(end, period, group, mode))
    end = day(end) if end is not None else loaded.manifest["end"]
    if end > loaded.manifest["end"] or preceding_window(end, 1)[-1] != end:
        raise FlowError("etf_invalid_evaluation_date", 422)
    dates = preceding_window(end, period)
    original = _original_material(repository, loaded, end, period, group) if mode == "original" else None
    calc, evidence, context_ref = original or (loaded.calculator, loaded.evidence, loaded.manifest["context_ref"])
    if original:
        pool, rule = calc._original_configuration(end)
    else:
        pool, rule = calc.pool, calc.rule
    groups = [{"id": digest(name), "name": name, "member_ids": [m.id for m in pool.members if m.group == name]}
              for name in sorted({m.group for m in pool.members})]
    if group is not None and group not in {g["id"] for g in groups}:
        raise FlowError("etf_group_not_found", 422)
    members = [m for m in pool.members if group is None or m.group_id == group]
    material_mode = "recorded_inputs" if original else "posthoc_inputs"
    evaluations = repository.evaluations(loaded, mode, group)
    # 用固定快照绑定公开结果ID；原存储对象和实际金融结果不改写。
    evaluations = {on: {**row, "result_id": digest({"snapshot_id": snapshot, "result_id": row["result_id"]})}
                   for on, row in evaluations.items() if on <= end}
    evaluation = evaluations.get(end)
    # 截止日是所选固定档案中最近一次完整金额，不承诺此前连续无缺口。
    complete_amount_through = max((on for on, row in evaluations.items()
                                  if row["amount"] is not None and not row["partial"]), default=None)
    if mode == "original" and original is None:
        complete_amount_through = None
    series, running = [], Decimal(0)
    with localcontext() as context:
        context.prec = 180
        for on in dates:
            row = evaluations.get(on)
            if row is None or row["amount"] is None or row["partial"]:
                running = None
            elif running is not None:
                running += Decimal(row["amount"])
            series.append({"date": on, "state": row["state"] if row else "unrecorded" if mode == "original" else "insufficient",
                           "evaluation": row, "cumulative": number(running)})
    # 累计/连续条件必须包含每个实际交易日，不能把稀疏历史记录压成连续N条。
    complete_tail = []
    for on in preceding_window(end, max(20, rule.streak_days or 2)):
        row = evaluations.get(on)
        if row is None:
            complete_tail = []
        else:
            complete_tail.append(row)
    member_rows, source_map = [], {}
    adjustment_sources: set[str] = set()
    active_day = end if original else instant(calc.selection_at).astimezone(SHANGHAI).date().isoformat()
    admission_at = min(instant(calc.selection_at), instant(end + "T23:59:59.999999+08:00")).isoformat() if original else calc.selection_at
    exclusions = {x["member_id"]: x["reason"] for x in evaluation["exclusions"]} if evaluation else {}
    for member in members:
        admission = calc.admission(member.id, rule, admission_at)
        reason = exclusions.get(member.id)
        if reason is None and not member.active(active_day):
            reason = "disabled" if member.disabled_date and member.disabled_date <= active_day else "not_enabled"
        if reason is None and admission is None:
            reason = "history_insufficient"
        metrics = _metrics(calc, member.id, end)
        reason = reason or metrics["reason"]
        member_series = []
        for on in dates:
            raw = calc.inputs.get((member.id, on))
            references = sorted({f.source.object_id for f in raw.fields.values()}) if raw else []
            # 只公开实际metrics路径采用的依据；窗口早于输入的fallback点不能凭证据补造。
            adjustment = adjustment_for(calc.adjustments, member.id, on, calc.selection_at) if on in calc.positions and on <= calc.end else None
            detail = None
            if adjustment is not None:
                detail = {"kind": adjustment.kind, "start": adjustment.start, "end": adjustment.end,
                          "factor": number(adjustment.factor), "tail": number(adjustment.tail),
                          "confirmed_at": adjustment.confirmed_at, "confirmation": adjustment.confirmation,
                          "source_ids": list(adjustment.source_ids)}
                adjustment_sources.update(adjustment.source_ids)
            member_series.append({"metrics": _metrics(calc, member.id, on), "source_ids": references,
                                  "adjustment_detail": detail})
            if on == end and raw:
                for field in raw.fields.values():
                    source_map[digest(asdict(field.source))] = asdict(field.source)
        admission_public = None if admission is None else {k: v for k, v in asdict(admission).items()
                                                          if k not in {"input_refs", "adjustment_refs"}} | {"id": admission.hash}
        member_rows.append({**asdict(member), "group_id": member.group_id, "active": member.active(active_day),
            "admission": admission_public, "reason": reason, "metrics": metrics,
            "amount_5": calc.member_cumulative(member.id, end, 5) if end in calc.positions else None,
            "amount_20": calc.member_cumulative(member.id, end, 20) if end in calc.positions else None,
            "series": member_series, "input_basis": material_mode, "input_version": calc.input_version,
            "input_selected_at": calc.selection_at})
    public = evidence.public(end, include_later=mode == "current")
    allowed_ids = {m.id for m in members}
    disclosures = [d for d in public["disclosures"] if d["member_id"] in allowed_ids]
    events = [e for e in public["events"] if not e["member_ids"] or allowed_ids.intersection(e["member_ids"])]
    referenced = {d["source_id"] for d in disclosures} | {e["source_id"] for e in events} | adjustment_sources
    for source in evidence.sources:
        if source.object_id in referenced:
            source_map[digest(asdict(source))] = asdict(source)
    rule_public = next(r for r in calc.config.raw["rule_versions"] if r["version"] == rule.version)
    return {"schema_version": "etf-flow-view-v2", "snapshot_id": snapshot, "formula_version": FORMULA_VERSION,
        "mode": mode, "end": end, "period": period, "group_id": group,
        "selection_at": calc.selection_at, "selected_member_ids": evaluation["valid_ids"] if evaluation else [],
        "pool_version": pool.version, "rule_version": rule.version, "input_version": calc.input_version,
        "calculated_at": evaluation["calculated_at"] if evaluation else None, "server_day": day(server_day),
        "groups": groups, "members": member_rows,
        "summary": {"evaluation": evaluation, "amount_5": cumulative(complete_tail, 5),
                    "amount_20": cumulative(complete_tail, 20), "streak": streak(complete_tail, rule, calc.selection_at)},
        "series": series, "history": [evaluations[on] for on in dates if on in evaluations],
        "disclosures": disclosures, "events": events, "sources": list(source_map.values()),
        "rule": rule_public, "pool": {"version": pool.version, "hash": pool.hash, "effective_date": pool.effective_date,
                                     "confirmed_at": pool.confirmed_at, "change": pool.change},
        "context": select_context(repository.store.get_json(context_ref), end, {m.index_id for m in members if m.index_id}),
        "data_status": {"state": evaluation["state"] if evaluation else "unrecorded" if mode == "original" else "insufficient",
                        "input_basis": material_mode, "evidence_version": evidence.version,
                        "history_first": dates[0], "history_last": dates[-1],
                        "complete_amount_through": complete_amount_through,
                        "original_recorded": original is not None, "parameters_confirmed": rule.confirmed(calc.selection_at)
                            and all(x is not None for x in (rule.k, rule.min_in, rule.min_out, rule.direction_ratio, rule.streak_days)),
                        "required_days": rule.required_days}}
