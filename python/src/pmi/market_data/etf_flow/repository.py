"""ETF版本发布与纯读投影：原信号、事后重算和首次准备证据分别保留。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import Any

from .calendar import preceding_window, trading_dates
from .calculation import Admission, Calculator, Evaluation, adjustment_document, cumulative, streak
from .evidence import Evidence
from .context import empty as empty_context, validate as validate_context
from .model import (Adjustment, Configuration, FlowError, FORMULA_VERSION, Input, SHANGHAI, Source,
                    adjustment_for, canonical, day, digest, exact, instant, number, object_id)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pmi.market_data.storage.etf_store import Store

SNAPSHOT_FIELDS = {"format", "scope", "parent", "operation_key", "configuration_ref", "evidence_ref", "dataset_ref",
                   "admission_refs", "signal_refs", "archive_ref", "context_ref", "selection_at", "end", "pool_hash", "rule_hash", "formula_version"}
SIGNAL_FIELDS = {"format", "date", "recorded_at", "configuration_ref", "evidence_ref", "dataset_ref", "admission_refs", "context_ref", "evaluations"}


@dataclass(frozen=True)
class Loaded:
    id: str
    manifest: dict[str, Any]
    config: Configuration
    evidence: Evidence
    inputs: tuple[Input, ...]
    admissions: tuple[Admission, ...]
    calculator: Calculator


def group_ids(config: Configuration, at: str) -> list[str | None]:
    pool, _ = config.selected(at)
    return [None, *sorted({m.group_id for m in pool.members})]


class Repository:
    """只在显式发布用例追加对象；读视图不更新计算时间或原信号。"""

    def __init__(self, store: Store, *, verify_reads: bool = True):
        self.store = store
        self.verify_reads = verify_reads

    def _dataset(self, reference: str) -> tuple[Input, ...]:
        value = self._dataset_identity(reference)
        refs = value['input_refs']
        values = self.store.get_many(refs)
        return tuple(Input.parse(values[ref]) for ref in refs)

    def _dataset_identity(self, reference: str) -> dict[str, Any]:
        value = exact(self.store.get_json(reference), {"format", "input_refs", "input_version"})
        if value["format"] != "etf-flow-dataset-v1" or not isinstance(value["input_refs"], list):
            raise FlowError("etf_invalid_dataset")
        refs = value["input_refs"]
        if len(set(refs)) != len(refs) or digest(sorted(refs)) != value["input_version"]:
            raise FlowError("etf_invalid_dataset")
        for ref in refs:
            object_id(ref)
        return value

    def window_calculator(self, config: Configuration, evidence: Evidence, admission_refs: list[str],
                          dataset: str, *, selection_at: str, end: str, view_end: str, period: int,
                          group: str | None, original: bool = False, read_inputs: bool = True) -> Calculator:
        """调用者先验证所属发布；准备凭据读SQL，窗口计算不再重放准备原件。"""
        identity = self._dataset_identity(dataset)
        admissions = tuple(Admission.parse(self.store.get_json(ref)) for ref in admission_refs)
        metadata = Calculator(config, (), evidence.adjustments, admissions, selection_at=selection_at, end=end)
        pool, _ = metadata._original_configuration(view_end) if original else (metadata.pool, metadata.rule)
        members = {m.id for m in pool.members if group is None or m.group_id == group} if read_inputs else set()
        start = preceding_window(view_end, max(period, 20) + 1)[0]
        refs, bounds = self.store.input_window(identity['input_refs'], start, view_end, members)
        values = self.store.get_many(refs)
        inputs = tuple(Input.parse(values[ref]) for ref in refs)
        return Calculator.from_window(config, inputs, evidence.adjustments, admissions,
            selection_at=selection_at, end=end, input_version=identity['input_version'], bounds=bounds)

    def _admission(self, reference: str) -> Admission:
        """回读原准备窗的实际输入和调整，防止损坏布尔标记冒充321日齐备。"""
        proof = Admission.parse(self.store.get_json(reference))
        values = self.store.get_many(list(proof.input_refs))
        rows = tuple(Input.parse(values[ref]) for ref in proof.input_refs)
        dates = preceding_window(proof.end, proof.required_days)
        if (tuple(x.date for x in rows) != dates or dates[0] != proof.start
                or any(x.member_id != proof.member_id or x.value("shares") is None or x.value("nav") is None for x in rows)
                or digest(sorted(proof.input_refs)) != proof.input_version
                or any(instant(f.source.retrieved_at) > instant(proof.checked_at) for x in rows for f in x.fields.values())):
            raise FlowError("etf_invalid_admission")
        adjustments = tuple(Adjustment.parse(self.store.get_json(ref)) for ref in proof.adjustment_refs)
        if any(adjustment_for(adjustments, proof.member_id, on, proof.checked_at) is None for on in dates[1:]):
            raise FlowError("etf_invalid_admission")
        for source in {f.source.object_id for row in rows for f in row.fields.values()} | {s for a in adjustments for s in a.source_ids}:
            self.store.get(source)
        return proof

    def load(self, identifier: str, *, verify: bool | None = None,
             window: tuple[str | None, int, str | None, str] | None = None) -> Loaded:
        """装配固定SQL版本；发布/维护verify重放来源，普通读取依赖已验证凭据。"""
        verify = self.verify_reads if verify is None else verify
        if window is not None and verify:
            raise FlowError('etf_incomplete_calculation_inputs')
        if not verify:
            self.store.require_published(identifier)
        manifest = exact(self.store.get_json(object_id(identifier)), SNAPSHOT_FIELDS)
        if (manifest["format"] != "etf-flow-snapshot-v1" or manifest["scope"] != self.store.scope
                or manifest["formula_version"] != FORMULA_VERSION
                or not isinstance(manifest["admission_refs"], list) or not isinstance(manifest["signal_refs"], list)):
            raise FlowError("etf_invalid_snapshot")
        if manifest["parent"] is not None:
            object_id(manifest["parent"])
        object_id(manifest["operation_key"])
        config = Configuration.parse(self.store.get_json(manifest["configuration_ref"]))
        members = {m.id for p in config.pools for m in p.members}
        evidence = Evidence.parse(self.store.get_json(manifest["evidence_ref"]), members)
        if instant(evidence.confirmed_at) > instant(manifest["selection_at"]):
            raise FlowError("etf_future_evidence")
        if window is None:
            inputs = self._dataset(manifest["dataset_ref"])
            admissions = tuple(self._admission(ref) if verify else Admission.parse(self.store.get_json(ref))
                               for ref in manifest["admission_refs"])
            calc = Calculator(config, inputs, evidence.adjustments, admissions, selection_at=manifest["selection_at"], end=manifest["end"])
        else:
            requested_end, period, group, mode = window
            view_end = day(requested_end) if requested_end is not None else manifest['end']
            if view_end > manifest['end'] or preceding_window(view_end, 1)[-1] != view_end:
                raise FlowError('etf_invalid_evaluation_date', 422)
            recorded = mode == 'original' and any(self._signal(ref)['date'] == view_end for ref in manifest['signal_refs'])
            calc = self.window_calculator(config, evidence, manifest['admission_refs'], manifest['dataset_ref'],
                selection_at=manifest['selection_at'], end=manifest['end'], view_end=view_end,
                period=period, group=group, read_inputs=not recorded)
            inputs, admissions = tuple(calc.inputs.values()), calc.admissions
        if calc.pool.hash != manifest["pool_hash"] or calc.rule.hash != manifest["rule_hash"]:
            raise FlowError("etf_snapshot_config_mismatch")
        source_ids = {s.object_id for s in evidence.sources} | {f.source.object_id for x in inputs for f in x.fields.values()}
        if verify:
            for ref in source_ids:
                self.store.get(ref)
        validate_context(self.store.get_json(manifest["context_ref"]))
        return Loaded(identifier, manifest, config, evidence, inputs, admissions, calc)

    def _signal(self, reference: str) -> dict[str, Any]:
        record = exact(self.store.get_json(reference), SIGNAL_FIELDS)
        if record["format"] != "etf-flow-signal-v1" or not isinstance(record["evaluations"], list):
            raise FlowError("etf_invalid_signal")
        day(record["date"])
        instant(record["recorded_at"])
        for evaluation in record["evaluations"]:
            if (evaluation.get("date") != record["date"] or evaluation.get("mode") != "original"
                    or evaluation.get("calculated_at") != record["recorded_at"]):
                raise FlowError("etf_invalid_signal")
        return record

    def publish(self, config: Configuration, evidence: Evidence, inputs: tuple[Input, ...], *,
                end: str, selection_at: str, operation_key: str, expected: str | None,
                allow_daily_signal: bool = False, context: dict[str, Any] | None = None) -> str:
        """原子发布新输入/配置与独立重算档案；首次补历史永不补造原信号。"""
        self.store._require_writer()
        if self.store.current_id() != expected:
            raise FlowError("etf_snapshot_changed")
        old = self.load(expected) if expected else None
        if old is not None and not config.extends(old.config):
            raise FlowError("etf_config_history_changed")
        if old is not None and (end < old.manifest["end"] or instant(selection_at) < instant(old.manifest["selection_at"])):
            raise FlowError("etf_time_regressed")
        pool, rule = config.selected(selection_at)
        if instant(evidence.confirmed_at) > instant(selection_at):
            raise FlowError("etf_future_evidence")
        if old is not None:
            incoming = {(x.member_id, x.date) for x in inputs}
            if not {(x.member_id, x.date) for x in old.inputs} <= incoming:
                raise FlowError("etf_input_history_removed")
            if evidence.version == old.evidence.version and evidence.hash != old.evidence.hash:
                raise FlowError("etf_evidence_history_changed")
        calc = Calculator(config, inputs, evidence.adjustments, old.admissions if old else (), selection_at=selection_at, end=end)
        source_ids = {s.object_id for s in evidence.sources} | {f.source.object_id for x in inputs for f in x.fields.values()}
        for ref in source_ids:
            self.store.get(ref)
        input_refs = [self.store.put_json(x.raw) for x in inputs]
        configuration_ref = self.store.put_json(config.raw)
        evidence_ref = self.store.put_json(evidence.raw)
        dataset_ref = self.store.put_json({"format": "etf-flow-dataset-v1", "input_refs": input_refs, "input_version": calc.input_version})
        for adjustment in evidence.adjustments:
            self.store.put_json(adjustment_document(adjustment))
        admissions = calc.qualify()
        admission_refs = [self.store.put_json(asdict(a)) for a in admissions]
        calc = Calculator(config, inputs, evidence.adjustments, admissions, selection_at=selection_at, end=end)
        dates = tuple(d for d in calc.calendar if d <= end)[-260:]
        archive = {"format": "etf-flow-recalculation-v1", "selection_at": selection_at, "pool_hash": pool.hash,
                   "rule_hash": rule.hash, "input_version": calc.input_version,
                   "evaluations": [calc.evaluate(on, group) for group in group_ids(config, selection_at) for on in dates]}
        archive_ref = self.store.put_json(archive)
        context_ref = self.store.put_json(validate_context(context if context is not None else empty_context()))
        signal_refs = list(old.manifest["signal_refs"]) if old else []
        server_day = instant(selection_at).astimezone(SHANGHAI).date()
        latest_complete = preceding_window((server_day - timedelta(days=1)).isoformat(), 1)[-1]
        # 仅记录本次最新日度观察；旧截止日、首次初始化和中间缺失日不补造。
        if allow_daily_signal and old is not None and end > old.manifest["end"] and end == latest_complete:
            existing_dates = {self._signal(ref)["date"] for ref in signal_refs}
            if end not in existing_dates:
                original_pool, _ = calc._original_configuration(end)
                groups = [None, *sorted({m.group_id for m in original_pool.members})]
                evaluations = [calc.evaluate(end, group, original=True) for group in groups]
                signal = {"format": "etf-flow-signal-v1", "date": end, "recorded_at": selection_at,
                          "configuration_ref": configuration_ref, "evidence_ref": evidence_ref, "dataset_ref": dataset_ref,
                          "admission_refs": admission_refs, "context_ref": context_ref, "evaluations": evaluations}
                signal_refs.append(self.store.put_json(signal))
        manifest = {"format": "etf-flow-snapshot-v1", "scope": self.store.scope, "parent": expected,
                    "operation_key": object_id(operation_key), "configuration_ref": configuration_ref, "evidence_ref": evidence_ref,
                    "dataset_ref": dataset_ref, "admission_refs": admission_refs, "signal_refs": signal_refs,
                    "archive_ref": archive_ref, "context_ref": context_ref, "selection_at": selection_at, "end": end,
                    "pool_hash": pool.hash, "rule_hash": rule.hash, "formula_version": FORMULA_VERSION}
        snapshot = self.store.put_json(manifest)
        self.load(snapshot, verify=True)
        self.store.publish(snapshot, expected)
        return snapshot

    def configuration_pending(self, loaded: Loaded, config: Configuration, now: str) -> bool:
        """到期未发布只标明待发布；不改变固定快照的名单或重算身份。"""
        pool, rule = config.selected(now)
        frozen_day = instant(loaded.manifest["selection_at"]).astimezone(SHANGHAI).date().isoformat()
        live_day = instant(now).astimezone(SHANGHAI).date().isoformat()
        frozen_members = sorted(m.id for m in loaded.calculator.pool.members if m.active(frozen_day))
        live_members = sorted(m.id for m in pool.members if m.active(live_day))
        return (config.hash != loaded.config.hash or pool.hash != loaded.manifest["pool_hash"]
                or rule.hash != loaded.manifest["rule_hash"] or frozen_members != live_members)

    def evaluations(self, loaded: Loaded, mode: str, group: str | None) -> dict[str, Evaluation]:
        """读取独立档案；原记录不存在就缺失，不调用当前计算填补它。"""
        if mode == "current":
            archive = exact(self.store.get_json(loaded.manifest["archive_ref"]),
                            {"format", "selection_at", "pool_hash", "rule_hash", "input_version", "evaluations"})
            if (archive["format"] != "etf-flow-recalculation-v1" or archive["selection_at"] != loaded.manifest["selection_at"]
                    or archive["pool_hash"] != loaded.manifest["pool_hash"] or archive["rule_hash"] != loaded.manifest["rule_hash"]
                    or archive["input_version"] != loaded.calculator.input_version):
                raise FlowError("etf_invalid_recalculation")
            values = archive["evaluations"]
        elif mode == "original":
            values = [value for ref in loaded.manifest["signal_refs"] for value in self._signal(ref)["evaluations"]]
        else:
            raise FlowError("etf_invalid_mode", 422)
        rows = [v for v in values if v["group_id"] == group]
        if len({r["date"] for r in rows}) != len(rows):
            raise FlowError("etf_duplicate_signal")
        return {row["date"]: row for row in rows}

    def sources(self, loaded: Loaded) -> dict[str, list[Source]]:
        """仅导出此快照及其原信号实际引用的来源，不开放任意对象读取。"""
        source_map: dict[str, list[Source]] = {}

        def add(source: Source) -> None:
            existing = source_map.setdefault(source.object_id, [])
            if source not in existing:
                existing.append(source)

        datasets = [loaded.inputs]
        evidence = [loaded.evidence]
        for ref in loaded.manifest["signal_refs"]:
            record = self._signal(ref)
            datasets.append(self._dataset(record["dataset_ref"]))
            config = Configuration.parse(self.store.get_json(record["configuration_ref"]))
            evidence.append(Evidence.parse(self.store.get_json(record["evidence_ref"]), {m.id for p in config.pools for m in p.members}))
        for rows in datasets:
            for row in rows:
                for field in row.fields.values():
                    add(field.source)
        for bundle in evidence:
            for source in bundle.sources:
                add(source)
        return source_map

    def evidence(self, snapshot: str, source_id: str) -> dict[str, Any]:
        loaded = self.load(snapshot)
        sources = self.sources(loaded).get(object_id(source_id))
        if sources is None:
            raise FlowError("etf_evidence_not_found", 404)
        raw = self.store.get(source_id)
        return {"snapshot_id": snapshot, "object_id": source_id, "bytes": len(raw),
                "references": [asdict(s) for s in sources]}
