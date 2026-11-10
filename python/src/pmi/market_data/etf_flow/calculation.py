"""固定输入下的ETF金额、准入及可解释规则；纯计算，不读写文件或网络。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from typing import Any, Mapping, TypedDict

from .calendar import preceding_window, trading_dates
from .model import (Adjustment, Configuration, FlowError, FORMULA_VERSION, Input, Member, PoolVersion,
                    RuleVersion, SHANGHAI, adjustment_for, day, digest, exact, identifier, instant, integer, number, object_id)


class Metrics(TypedDict):
    date: str
    shares: str | None
    comparable_previous: str | None
    delta: str | None
    change_rate: str | None
    amount: str | None
    nav: str | None
    close: str | None
    turnover: str | None
    volume: str | None
    net_assets: str | None
    premium: str | None
    turnover_ratio: str | None
    adjustment: bool
    reason: str | None


class Condition(TypedDict):
    state: str
    reason: str | None
    incoming: bool | None
    outgoing: bool | None
    mean: str | None
    standard_deviation: str | None
    upper: str | None
    lower: str | None
    positive_count: int | None
    negative_count: int | None
    denominator: int | None
    positive_ratio: str | None
    negative_ratio: str | None
    threshold: str | None


class Exclusion(TypedDict):
    member_id: str
    reason: str


class Evaluation(TypedDict):
    result_id: str
    date: str
    state: str
    amount: str | None
    partial: bool
    active_count: int
    ready_count: int
    valid_count: int
    valid_ids: list[str]
    exclusions: list[Exclusion]
    c1: Condition
    c2: Condition
    pool_version: str
    rule_version: str
    input_version: str
    calculated_at: str
    selection_at: str
    group_id: str | None
    mode: str


@dataclass(frozen=True)
class Admission:
    member_id: str
    first_qualified_at: str
    checked_at: str
    start: str
    end: str
    required_days: int
    input_version: str
    input_refs: tuple[str, ...]
    adjustment_refs: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Any) -> Admission:
        """准入证据也有版本与原输入引用；不能靠一个布尔值倒写成熟状态。"""
        v = exact(raw, set(cls.__dataclass_fields__))
        if (instant(v["first_qualified_at"]) > instant(v["checked_at"]) or day(v["start"]) > day(v["end"])
                or not isinstance(v["input_refs"], list) or not isinstance(v["adjustment_refs"], list)):
            raise FlowError("etf_invalid_admission", 422)
        required = integer(v["required_days"], 321)
        if len(v["input_refs"]) != required or len(set(v["input_refs"])) != required or not v["adjustment_refs"]:
            raise FlowError("etf_invalid_admission", 422)
        return cls(identifier(v["member_id"]), v["first_qualified_at"], v["checked_at"], v["start"], v["end"],
                   required, object_id(v["input_version"]), tuple(object_id(x) for x in v["input_refs"]),
                   tuple(object_id(x) for x in v["adjustment_refs"]))

    @property
    def hash(self) -> str:
        return digest(asdict(self))


def empty_condition(reason: str, state: str = "insufficient") -> Condition:
    return {"state": state, "reason": reason, "incoming": None, "outgoing": None, "mean": None,
            "standard_deviation": None, "upper": None, "lower": None, "positive_count": None,
            "negative_count": None, "denominator": None, "positive_ratio": None, "negative_ratio": None,
            "threshold": None}


class Calculator:
    """一份输入/事件/准入版本对应一个实例；时点由调用者固定，不读当前时钟。"""

    def __init__(self, configuration: Configuration, inputs: tuple[Input, ...], adjustments: tuple[Adjustment, ...],
                 admissions: tuple[Admission, ...], *, selection_at: str, end: str):
        self.config, self.selection_at, self.end = configuration, selection_at, day(end)
        if self.end > instant(selection_at).astimezone(SHANGHAI).date().isoformat():
            raise FlowError("etf_future_evaluation", 422)
        self.pool, self.rule = configuration.selected(selection_at)
        known_ids = {m.id for p in configuration.pools for m in p.members}
        if any(v.member_id not in known_ids for v in inputs) or any(a.member_id not in known_ids for a in adjustments):
            raise FlowError("etf_unknown_member", 422)
        self.inputs: dict[tuple[str, str], Input] = {}
        for value in inputs:
            key = value.member_id, value.date
            if key in self.inputs:
                raise FlowError("etf_duplicate_date", 422)
            if any(instant(f.source.retrieved_at) > instant(selection_at) for f in value.fields.values()):
                raise FlowError("etf_input_not_yet_known", 422)
            self.inputs[key] = value
        self.adjustments = adjustments
        self.admissions = admissions
        start = min((x.date for x in inputs), default=self.end)
        self.calendar = trading_dates(start, max([self.end, *(x.date for x in inputs)]))
        if any(x.date not in self.calendar for x in inputs):
            raise FlowError("etf_non_trading_input", 422)
        self.positions = {d: i for i, d in enumerate(self.calendar)}
        self.input_version = digest(sorted(x.hash for x in inputs))
        self._metrics: dict[tuple[str, str], Metrics] = {}
        self._window_only = False

    @classmethod
    def from_window(cls, configuration: Configuration, inputs: tuple[Input, ...], adjustments: tuple[Adjustment, ...],
                    admissions: tuple[Admission, ...], *, selection_at: str, end: str,
                    input_version: str, bounds: tuple[str, str] | None) -> Calculator:
        """只供已发布SQL版本的页面明细；完整输入身份/日历来自固定目录。"""
        value = cls(configuration, inputs, adjustments, admissions, selection_at=selection_at, end=end)
        start, last = bounds if bounds is not None else (end, end)
        value.calendar = trading_dates(day(start), max(day(last), end))
        value.positions = {d: i for i, d in enumerate(value.calendar)}
        value.input_version = object_id(input_version)
        value._window_only = True
        return value

    def metrics(self, member_id: str, on: str) -> Metrics:
        """前一交易日必须在固定输入中；未知折算/净值不会产生正式金额。"""
        key = member_id, on
        if key in self._metrics:
            return self._metrics[key]
        if on not in self.positions or on > self.end:
            raise FlowError("etf_invalid_evaluation_date", 422)
        row = self.inputs.get(key)
        position = self.positions[on]
        previous = self.inputs.get((member_id, self.calendar[position - 1])) if position else None
        values = {field: row.value(field) if row else None for field in ("shares", "nav", "close", "turnover", "volume")}
        shares, nav, close, turnover = (values[x] for x in ("shares", "nav", "close", "turnover"))
        adjustment = adjustment_for(self.adjustments, member_id, on, self.selection_at)
        comparable = delta = change = amount = assets = premium = ratio = None
        reason: str | None = None
        with localcontext() as context:
            context.prec = 180
            if shares is None:
                reason = "shares_missing"
            elif previous is None or previous.value("shares") is None:
                reason = "previous_day_missing"
            elif adjustment is None:
                reason = "adjustment_unverified"
            else:
                comparable = previous.value("shares") * adjustment.factor + adjustment.tail
                if comparable < 0:
                    reason = "invalid_comparable_shares"
                    comparable = None
                else:
                    delta = shares - comparable
                    change = delta / comparable if comparable > 0 else None
                    if nav is None:
                        reason = "waiting_nav"
                    else:
                        amount = delta * nav
            if shares is not None and nav is not None:
                assets = shares * nav
            if nav is not None and close is not None:
                premium = close / nav - 1
            if turnover is not None and assets is not None and assets > 0:
                ratio = turnover / assets
        result: Metrics = {"date": on, **{k: number(v) for k, v in values.items()},
                           "comparable_previous": number(comparable), "delta": number(delta), "change_rate": number(change),
                           "amount": number(amount), "net_assets": number(assets), "premium": number(premium),
                           "turnover_ratio": number(ratio), "adjustment": bool(adjustment and adjustment.kind == "adjustment"),
                           "reason": reason}
        self._metrics[key] = result
        return result

    def admission(self, member: str, rule: RuleVersion | None = None, at: str | None = None) -> Admission | None:
        """成熟成员保留已取得的准备事实；当前缺数不改写为从未达标。"""
        required, point = (rule or self.rule).required_days, instant(at or self.selection_at)
        eligible = [a for a in self.admissions if a.member_id == member and a.required_days >= required
                    and instant(a.checked_at) <= point and instant(a.first_qualified_at) <= point]
        return eligible[0] if eligible else None

    def qualify(self) -> tuple[Admission, ...]:
        """新准入须覆盖目标末日的连续准备窗；首次达标时间取实际核验时刻。"""
        if self._window_only:
            raise FlowError('etf_incomplete_calculation_inputs')
        window = preceding_window(self.end, self.rule.required_days)
        result = list(self.admissions)
        for member in self.pool.members:
            if self.admission(member.id) is not None:
                continue
            rows = [self.inputs.get((member.id, d)) for d in window]
            complete = all(row is not None and row.value("shares") is not None and row.value("nav") is not None for row in rows)
            if complete:
                complete = all(adjustment_for(self.adjustments, member.id, d, self.selection_at) is not None for d in window[1:])
            if complete:
                first = next((a.first_qualified_at for a in self.admissions if a.member_id == member.id), self.selection_at)
                adjustment_ids = sorted({digest(adjustment_document(adjustment_for(self.adjustments, member.id, d, self.selection_at))) for d in window[1:]})
                result.append(Admission(member.id, first, self.selection_at, window[0], window[-1], self.rule.required_days,
                                        digest(sorted(row.hash for row in rows)), tuple(row.hash for row in rows), tuple(adjustment_ids)))
        return tuple(result)

    def _original_configuration(self, on: str) -> tuple[PoolVersion, RuleVersion]:
        """发布原记录时按评估日生效范围选择版本，不让次日配置提前参与。"""
        point = instant(self.selection_at)
        pools = [p for p in self.config.pools if p.effective_date <= on and instant(p.confirmed_at) <= point]
        rules = [r for r in self.config.rules if r.effective_date <= on]
        if not pools or not rules:
            raise FlowError("etf_config_not_effective", 409)
        return pools[-1], rules[-1]

    def evaluate(self, on: str, group_id: str | None = None, *, original: bool = False) -> Evaluation:
        """计算只使用评估日及以前数值；原信号仅由显式发布调用，GET不能补造。"""
        if self._window_only:
            raise FlowError('etf_incomplete_calculation_inputs')
        if on not in self.positions or on > self.end:
            raise FlowError("etf_invalid_evaluation_date", 422)
        pool, rule = self._original_configuration(on) if original else (self.pool, self.rule)
        active_day = on if original else instant(self.selection_at).astimezone(SHANGHAI).date().isoformat()
        admission_at = min(instant(self.selection_at), instant(on + "T23:59:59.999999+08:00")).isoformat() if original else self.selection_at
        members = [m for m in pool.members if group_id is None or m.group_id == group_id]
        exclusions: list[Exclusion] = []
        active: list[Member] = []
        ready: list[Member] = []
        valid: list[Member] = []
        position = self.positions[on]
        baseline_days = self.calendar[max(0, position - rule.window):position]
        for member in members:
            reason = None
            if not member.active(active_day):
                reason = "disabled" if member.disabled_date is not None and member.disabled_date <= active_day else "not_enabled"
            else:
                active.append(member)
                if self.admission(member.id, rule, admission_at) is None:
                    reason = "history_insufficient"
                else:
                    ready.append(member)
                    current = self.metrics(member.id, on)
                    if current["amount"] is None:
                        reason = current["reason"] or "amount_missing"
                    elif len(baseline_days) != rule.window or any(self.metrics(member.id, d)["amount"] is None for d in baseline_days):
                        reason = "baseline_insufficient"
                    else:
                        valid.append(member)
            if reason is not None:
                exclusions.append({"member_id": member.id, "reason": reason})
        partial = len(valid) < len(ready)
        amounts = [Decimal(self.metrics(m.id, on)["amount"]) for m in valid]
        with localcontext() as context:
            context.prec = 180
            total = sum(amounts, Decimal(0)) if amounts else None
            c1 = self._c1(valid, baseline_days, total, rule, partial)
            c2 = self._c2(valid, on, rule, partial)
        if not valid or partial or c1["state"] == "insufficient" or c2["state"] == "insufficient":
            state = "insufficient"
        elif c1["state"] == "parameters_pending" or c2["state"] == "parameters_pending":
            state = "parameters_pending"
        elif c1["incoming"] and c2["incoming"]:
            state = "abnormal_subscription"
        elif c1["outgoing"] and c2["outgoing"]:
            state = "abnormal_redemption"
        else:
            state = "not_triggered"
        identity = {"formula": FORMULA_VERSION, "input": self.input_version, "adjustments": digest([adjustment_document(x) for x in self.adjustments]),
                    "selection_at": self.selection_at, "pool": pool.hash, "rule": rule.hash, "on": on, "group": group_id,
                    "members": sorted((m.id, self.admission(m.id, rule, admission_at).hash) for m in ready), "original": original}
        return {"result_id": digest(identity), "date": on, "state": state, "amount": number(total), "partial": partial,
                "active_count": len(active), "ready_count": len(ready), "valid_count": len(valid),
                "valid_ids": sorted(m.id for m in valid), "exclusions": exclusions, "c1": c1, "c2": c2,
                "pool_version": pool.version, "rule_version": rule.version, "input_version": self.input_version,
                "calculated_at": self.selection_at, "selection_at": self.selection_at, "group_id": group_id,
                "mode": "original" if original else "current"}

    def _c1(self, members: list[Member], baseline: tuple[str, ...], total: Decimal | None,
            rule: RuleVersion, partial: bool) -> Condition:
        """固定同一名单的此前w日样本标准差；零波动、缺覆盖与未确认分开。"""
        if not members or total is None or len(baseline) != rule.window:
            return empty_condition("baseline_insufficient")
        values = [sum((Decimal(self.metrics(m.id, d)["amount"]) for m in members), Decimal(0)) for d in baseline]
        mean = sum(values, Decimal(0)) / rule.window
        deviation = (sum(((x - mean) ** 2 for x in values), Decimal(0)) / (rule.window - 1)).sqrt()
        condition = empty_condition("parameters_pending", "parameters_pending")
        condition.update(mean=number(mean), standard_deviation=number(deviation))
        if partial:
            condition.update(state="insufficient", reason="partial_coverage")
        elif deviation == 0:
            condition.update(state="insufficient", reason="zero_variance")
        elif rule.confirmed(self.selection_at) and all(x is not None for x in (rule.k, rule.min_in, rule.min_out)):
            upper = max(mean + rule.k * deviation, rule.min_in)
            lower = min(mean - rule.k * deviation, -rule.min_out)
            condition.update(state="evaluated", reason=None, incoming=total >= upper, outgoing=total <= lower,
                             upper=number(upper), lower=number(lower))
        return condition

    def _c2(self, members: list[Member], on: str, rule: RuleVersion, partial: bool) -> Condition:
        """零仅进分母；0/1有效成员不输出比例，也不以未触发替代不足。"""
        if len(members) < 2:
            return empty_condition("fewer_than_two_valid_members")
        positive = sum(Decimal(self.metrics(m.id, on)["delta"]) > 0 for m in members)
        negative = sum(Decimal(self.metrics(m.id, on)["delta"]) < 0 for m in members)
        incoming, outgoing = Decimal(positive) / len(members), Decimal(negative) / len(members)
        result = empty_condition("parameters_pending", "parameters_pending")
        result.update(positive_count=positive, negative_count=negative, denominator=len(members),
                      positive_ratio=number(incoming), negative_ratio=number(outgoing), threshold=number(rule.direction_ratio))
        if partial:
            result.update(state="insufficient", reason="partial_coverage")
        elif rule.confirmed(self.selection_at) and rule.direction_ratio is not None:
            result.update(state="evaluated", reason=None, incoming=incoming >= rule.direction_ratio, outgoing=outgoing >= rule.direction_ratio)
        return result

    def member_cumulative(self, member_id: str, on: str, count: int) -> str | None:
        """只按逐日F求和；任何应有交易日缺失即返回缺失。"""
        position = self.positions.get(on, -1)
        if position < count - 1:
            return None
        values = [self.metrics(member_id, d)["amount"] for d in self.calendar[position - count + 1:position + 1]]
        if any(x is None for x in values):
            return None
        with localcontext() as context:
            context.prec = 180
            return number(sum((Decimal(x) for x in values), Decimal(0)))


def cumulative(evaluations: list[Evaluation], count: int) -> str | None:
    """完整观察池累计不能由部分小计或缺失结果拼凑。"""
    selected = evaluations[-count:]
    if len(selected) != count or any(x["amount"] is None or x["partial"] for x in selected):
        return None
    with localcontext() as context:
        context.prec = 180
        return number(sum((Decimal(x["amount"]) for x in selected), Decimal(0)))


def adjustment_document(value: Adjustment) -> dict[str, Any]:
    """调整原词法规范化用于不可变寻址，Decimal不交给JSON隐式转换。"""
    return {**asdict(value), "factor": number(value.factor), "tail": number(value.tail), "source_ids": list(value.source_ids)}


def streak(evaluations: list[Evaluation], rule: RuleVersion, at: str) -> dict[str, Any]:
    """连续描述也需确认N；零、缺口或名单/池变更都会中断。"""
    if not rule.confirmed(at) or rule.streak_days is None:
        return {"state": "parameters_pending", "direction": None, "days": None, "amount": None}
    rows = evaluations[-rule.streak_days:]
    if len(rows) != rule.streak_days or any(x["amount"] is None or x["partial"] for x in rows):
        return {"state": "insufficient", "direction": None, "days": None, "amount": None}
    amounts = [Decimal(x["amount"]) for x in rows]
    same = all((x["pool_version"], x["valid_ids"]) == (rows[-1]["pool_version"], rows[-1]["valid_ids"]) for x in rows)
    direction = "subscription" if all(v > 0 for v in amounts) else "redemption" if all(v < 0 for v in amounts) else None
    if not same or direction is None:
        return {"state": "not_met", "direction": None, "days": 0, "amount": None}
    return {"state": "met", "direction": direction, "days": rule.streak_days, "amount": cumulative(rows, rule.streak_days)}
