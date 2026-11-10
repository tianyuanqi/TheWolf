"""ETF用例编排：有限异步更新、原请求优先重放、显式跨账本恢复。"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import threading
from typing import Any, Callable

from pmi.market_data.periodic_budget import Budget as PeriodicBudget, BudgetError
from .budget import Budget, Request
from .cache import merge
from pmi.market_data.storage.etf_cache import Cache
from .calendar import preceding_window
from .model import Configuration, FlowError, Input, SHANGHAI, day, digest, exact, identifier, instant, object_id
from .options import Options, Settings
from .repository import Repository
from .sources import Parsed, parse, plan as source_plan, verify_nav_pages
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.storage.database import CommitUncertain
from .transport import Transport

TERMINAL = frozenset({"completed", "failed", "interrupted"})
OP_FIELDS = {"request_id", "config_id", "instance_id", "operation_key", "plan_id", "plan_ref", "expected_snapshot_id",
             "state", "reason", "snapshot_id", "created_at", "updated_at", "coordinator_target", "batch_id",
             "coordinator_scope", "lease_closed", "recovered_from_instance"}


@dataclass(frozen=True)
class Plan:
    id: str
    raw: dict[str, Any]
    requests: tuple[Request, ...]
    network: tuple[Request, ...]
    inputs: tuple[Input, ...]


class Runtime:
    def __init__(self, options: Options, *, clock: Callable[[], datetime] | None = None,
                 periodic: PeriodicBudget | None = None, guard: Callable[[], None] | None = None,
                 connection_id: str | None = None,
                 context_provider: Callable[[Configuration, str, str], dict[str, Any]] | None = None):
        self.settings = Settings(options)
        self.connection_id = object_id(connection_id) if connection_id is not None else None
        self.settings.id = self._config_id(options.write_enabled)
        self.store = Store(options.root)
        self.repository = Repository(self.store, verify_reads=False)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.budget = Budget(self.store, self.settings.grant, self.clock) if self.settings.grant else None
        self.periodic, self.guard = periodic, guard
        self.context_provider = context_provider
        self.cache = Cache(self.store, options.refresh_revision, self.settings.config)
        self.stop = threading.Event()
        self.transport = Transport(self.budget, self.stop) if self.budget else None
        self.registry = digest({"format": "etf-flow-operations-v1", "scope": self.store.scope})
        self._mutex = threading.RLock()
        self._worker: threading.Thread | None = None
        self._active_key: str | None = None
        self._uncertain: dict[str, dict[str, Any]] = {}

    def _config_id(self, write_enabled: bool) -> str:
        identity = self.settings.identity(write_enabled)
        return digest({"settings": identity, "connection": self.connection_id}) if self.connection_id is not None else identity

    def check(self, *, write: bool = False) -> None:
        self.settings.check()
        self.store.check()
        if write:
            if not self.settings.options.write_enabled or self.budget is None:
                raise FlowError("etf_update_disabled", 403)
            if self.guard:
                self.guard()
            if self.stop.is_set():
                raise FlowError("etf_update_interrupted")

    def now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            raise FlowError("etf_clock_invalid")
        return value.isoformat()

    def plan(self) -> Plan:
        """可信配置和已有输入冻结整批计划；生成计划本身不扣额、不建账。"""
        self.check()
        now = self.now()
        today = instant(now).astimezone(SHANGHAI).date()
        end = preceding_window((today - timedelta(days=1)).isoformat(), 1)[-1]
        pool, rule = self.settings.config.selected(now)
        start = preceding_window(end, rule.required_days)[0]
        current = self.store.current_id()
        old = self.repository.load(current) if current else None
        if old and not self.settings.config.extends(old.config):
            raise FlowError("etf_config_history_changed")
        rows = merge(old.inputs if old else (), self.cache.inputs(), "合并已发布输入与已验证缓存")
        members = tuple(m for m in pool.members if m.active(today.isoformat()))
        lookup = {(x.member_id, x.date): x for x in rows}
        requests = tuple(r for member in members for r in source_plan(member, start, end, lookup,
                                  refresh=self.settings.options.refresh_revision is not None))
        cached = self.cache.reusable_responses(requests)
        network = tuple(r for r in requests if cached[r.key] is None)
        raw = {"format": "etf-flow-plan-v1", "config_id": self.settings.id, "expected_snapshot_id": current,
               "end": end, "start": start, "server_day": today.isoformat(), "pool_hash": pool.hash, "rule_hash": rule.hash,
               "members": [m.id for m in members], "requests": [asdict(r) for r in requests],
               "cached": {key: row["object_id"] for key, row in cached.items() if row is not None},
               "grant_hash": self.settings.grant.hash if self.settings.grant else None,
               "input_refs": sorted(digest(x.raw) for x in rows)}
        return Plan(digest(raw), raw, requests, network, rows)

    def _records(self) -> tuple[str | None, list[dict[str, Any]]]:
        reference, value = self.store.journal(self.registry)
        if reference is None:
            return None, list(self._uncertain.values())
        value = exact(value, {"operations"})
        if not isinstance(value["operations"], list):
            raise FlowError("etf_invalid_operation")
        records = [exact(row, OP_FIELDS) for row in value["operations"]]
        keys = set()
        for row in records:
            identifier(row["request_id"])
            identifier(row["instance_id"])
            object_id(row["config_id"])
            object_id(row["plan_id"])
            instant(row["created_at"])
            if instant(row["updated_at"]) < instant(row["created_at"]):
                raise FlowError("etf_invalid_operation")
            expected = row["expected_snapshot_id"]
            if expected is not None:
                object_id(expected)
            identity = self._identity(row["request_id"], row["config_id"], row["plan_id"], expected)
            if (row["operation_key"] != identity or row["coordinator_target"] != self._target(identity)
                    or row["state"] not in TERMINAL | {"queued", "running"} or type(row["lease_closed"]) is not bool
                    or (row["config_id"], row["request_id"]) in keys):
                raise FlowError("etf_invalid_operation")
            keys.add((row["config_id"], row["request_id"]))
            plan = self.store.get_json(object_id(row["plan_ref"]))
            if digest(plan) != row["plan_id"] or plan.get("config_id") != row["config_id"] or plan.get("expected_snapshot_id") != expected:
                raise FlowError("etf_invalid_operation")
            if row["state"] == "completed":
                object_id(row["snapshot_id"])
            elif row["snapshot_id"] is not None:
                raise FlowError("etf_invalid_operation")
        identities = {row['operation_key'] for row in records}
        return reference, [self._uncertain.get(row['operation_key'], row) for row in records] + [
            row for key, row in list(self._uncertain.items()) if key not in identities]

    def _identity(self, request_id: str, config_id: str, plan_id: str, expected: str | None) -> str:
        return digest({"scope": self.store.scope, "config_id": config_id, "request_id": request_id,
                       "plan_id": plan_id, "expected_snapshot_id": expected})

    def _target(self, operation_key: str) -> str:
        return "etf-flow:" + self.store.scope + ":" + operation_key

    def _save(self, record: dict[str, Any]) -> None:
        """单个registry指针原子保存占位及回执；不存在未入索引的queued空窗。"""
        reference, records = self._records()
        others = [r for r in records if (r["config_id"], r["request_id"]) != (record["config_id"], record["request_id"])]
        self.store.write_journal(self.registry, {"operations": [*others, record]}, reference)

    def _find(self, request_id: str, *, historical_read: bool = False) -> dict[str, Any] | None:
        identifier(request_id)
        permitted = {self.settings.id}
        if not self.settings.options.write_enabled:
            permitted.add(self._config_id(True))
        # 迁移保留原config_id；只读查询可查同一已验证scope的旧记录，写入/恢复仍严格匹配当前授权。
        records = [row for row in self._records()[1] if row["request_id"] == request_id
                   and (historical_read or row["config_id"] in permitted)]
        if len(records) > 1:
            raise FlowError("etf_operation_conflict")
        return records[0] if records else None

    def _commit(self, record: dict[str, Any], *, historical_read: bool = False) -> str | None:
        found = self.store.published_operation(record["operation_key"])
        if found is None:
            if record["state"] == "completed":
                raise FlowError("etf_publication_unverifiable")
            return None
        snapshot, manifest = found
        loaded = self.repository.load(snapshot)
        plan = self.store.get_json(record["plan_ref"])
        if (manifest["parent"] != record["expected_snapshot_id"] or manifest["end"] != plan["end"]
                or manifest['pool_hash'] != plan['pool_hash'] or manifest['rule_hash'] != plan['rule_hash']
                or not historical_read and (loaded.config.hash != self.settings.config.hash
                    or loaded.evidence.hash != self.settings.evidence.hash)
                or (record["snapshot_id"] is not None and record["snapshot_id"] != snapshot)):
            raise FlowError("etf_publication_unverifiable")
        return snapshot

    def _response(self, record: dict[str, Any], instance: str) -> dict[str, Any]:
        active = self._active_key == record["operation_key"] and self._worker is not None and self._worker.is_alive()
        recovery = (record["state"] not in TERMINAL or not record["lease_closed"]) and not active
        return {k: v for k, v in record.items() if k not in {"plan_ref", "coordinator_target", "coordinator_scope"}} | {
            "serving_instance_id": identifier(instance), "serving_config_id": self.settings.id, "recovery_required": recovery}

    def operation(self, request_id: str, instance: str) -> dict[str, Any]:
        """GET只展示原实例归属和恢复需求，不解除占位或补写回执。"""
        self.check()
        with self._mutex:
            record = self._find(request_id, historical_read=True)
            if record is None:
                raise FlowError("etf_operation_not_found", 404)
            if record["state"] == "completed":
                self._commit(record, historical_read=True)
            return self._response(record, instance)

    def start(self, request_id: str, parameters: dict[str, Any], instance: str) -> tuple[int, dict[str, Any]]:
        """权限守卫后先重放原请求；新请求才检查计划/CAS/额度及其他未决。"""
        self.check(write=True)
        identifier(request_id)
        identifier(instance)
        parameters = exact(parameters, {"expected_snapshot_id", "plan_id"})
        object_id(parameters["plan_id"])
        if parameters["expected_snapshot_id"] is not None:
            object_id(parameters["expected_snapshot_id"])
        with self._mutex:
            prior = self._find(request_id)
            if prior is not None:
                if any(prior[k] != parameters[k] for k in parameters):
                    raise FlowError("etf_operation_conflict")
                if self._active_key == prior["operation_key"] and self._worker is not None and self._worker.is_alive():
                    return 202, self._response(prior, instance)
                if prior["state"] in TERMINAL and prior["lease_closed"]:
                    if prior["state"] == "completed":
                        self._commit(prior)
                    return 200, self._response(prior, instance)
                with self.store.writer():
                    return 200, self._response(self._recover(prior, instance), instance)
            with self.store.writer():
                # 锁内复核，拒绝另一服务已写入的请求或未决；不盲目接管它。
                if self._find(request_id) is not None:
                    raise FlowError("etf_busy")
                if any(r["state"] not in TERMINAL or not r["lease_closed"] for r in self._records()[1]):
                    raise FlowError("etf_unresolved_operation")
                planned = self.plan()
                if planned.id != parameters["plan_id"] or planned.raw["expected_snapshot_id"] != parameters["expected_snapshot_id"]:
                    raise FlowError("etf_plan_changed")
                self.budget.preflight(planned.network)
                self.cache.bind_configuration()
                now = self.now()
                for row in planned.inputs:
                    self.store.put_json(row.raw)
                key = self._identity(request_id, self.settings.id, planned.id, parameters["expected_snapshot_id"])
                record = {"request_id": request_id, "config_id": self.settings.id, "instance_id": instance,
                    "operation_key": key, "plan_id": planned.id, "plan_ref": self.store.put_json(planned.raw),
                    "expected_snapshot_id": parameters["expected_snapshot_id"], "state": "queued", "reason": None,
                    "snapshot_id": None, "created_at": now, "updated_at": now, "coordinator_target": self._target(key),
                    "coordinator_scope": self.periodic.scope if self.periodic else None, "batch_id": None,
                    "lease_closed": False, "recovered_from_instance": None}
                try:
                    self._save(record)
                except CommitUncertain:
                    self._preserve_uncertain(record)
                    raise
            self._active_key = key
            self._worker = threading.Thread(target=self._run, args=(record, planned), name="etf-flow-update", daemon=True)
            self._worker.start()
            return 202, self._response(record, instance)

    def _recover(self, record: dict[str, Any], instance: str) -> dict[str, Any]:
        try:
            return self._recover_confirmed(record, instance)
        except CommitUncertain:
            self._preserve_uncertain(record)
            raise

    def _preserve_uncertain(self, record: dict[str, Any]) -> None:
        """只写未决回执，绝不据可见发布推断本次请求成功。"""
        unresolved = {**record, 'state': 'running', 'snapshot_id': None,
                      'reason': 'etf_commit_uncertain', 'lease_closed': False, 'updated_at': self.now()}
        self._uncertain[record['operation_key']] = unresolved
        try:
            with self.store.writer():
                self._save(unresolved)
        except Exception:
            # 介质仍不可写时，本实例继续拒绝成功/新请求；不以重读掩盖故障。
            pass

    def _recover_confirmed(self, record: dict[str, Any], instance: str) -> dict[str, Any]:
        """ETF锁→旧账本锁；先核实提交/落本地终态，再结束唯一零请求外部租约。"""
        if (self.periodic.scope if self.periodic else None) != record["coordinator_scope"]:
            raise FlowError("etf_coordinator_changed")
        manager = self.periodic.recover_etf_zero(record["coordinator_target"], record["batch_id"]) if self.periodic else nullcontext(None)
        with manager as lease:
            self.transport.recover(record["operation_key"])
            snapshot = self._commit(record)
            if record["state"] not in TERMINAL or snapshot is not None:
                record = {**record, "state": "completed" if snapshot else "interrupted", "snapshot_id": snapshot,
                          "reason": None if snapshot else "etf_update_interrupted"}
            record = {**record, "updated_at": self.now(), "recovered_from_instance": record["instance_id"]}
            self._save(record)
            if lease is not None:
                lease.finish(None if snapshot else "etf_update_interrupted")
            record = {**record, "lease_closed": True, "updated_at": self.now()}
            self._save(record)
            self._uncertain.pop(record['operation_key'], None)
            return record

    def _check_plan_boundary(self, planned: Plan) -> None:
        self.check(write=True)
        now = self.now()
        pool, rule = self.settings.config.selected(now)
        today = instant(now).astimezone(SHANGHAI).date().isoformat()
        if (today != planned.raw["server_day"] or pool.hash != planned.raw["pool_hash"] or rule.hash != planned.raw["rule_hash"]
                or [m.id for m in pool.members if m.active(today)] != planned.raw["members"]
                or self.store.current_id() != planned.raw["expected_snapshot_id"]):
            raise FlowError("etf_plan_changed")

    def _execute(self, record: dict[str, Any], planned: Plan) -> str:
        """逐请求落原件与已核验缓存，所有来源/页面核验通过后一次发布。"""
        pool, _ = self.settings.config.selected(self.now())
        members = {m.id: m for m in pool.members}
        rows = planned.inputs
        nav_groups: dict[tuple[str, str, str], list[Parsed]] = {}
        for request in planned.requests:
            self._check_plan_boundary(planned)
            # 只复用受理时已经整组核验的原件；不能在本批逐页替换中途重新判定复用。
            expected_cached = planned.raw["cached"].get(request.key)
            if expected_cached is None:
                original = self.transport.fetch(request, record["operation_key"])
                parsed = parse(members[request.member_id], request, original.raw, original.object_id, original.retrieved_at)
                self.cache.save_response(original, replace=True)
            else:
                cached = self.cache.response(request)
                if cached is None or cached["object_id"] != expected_cached:
                    raise FlowError("etf_plan_changed")
                parsed = parse(members[request.member_id], request, self.store.get(cached["object_id"]),
                               cached["object_id"], cached["retrieved_at"])
            if request.kind == "nav":
                nav_groups.setdefault((request.member_id, request.start, request.end), []).append(parsed)
            else:
                self.cache.save_inputs(parsed.rows)
                rows = merge(rows, parsed.rows, "明确检查更新：" + (self.settings.options.refresh_revision or "补齐缺项"))
        for (_, start, end), pages in nav_groups.items():
            # 计划按日历上限预留；源总数较少时多余空页可验证后舍弃，不伪造缺日。
            needed = max(1, ((pages[0].total or 0) + 19) // 20)
            if any(p.total != pages[0].total or p.rows for p in pages[needed:]):
                raise FlowError("etf_source_page_mismatch")
            verify_nav_pages(tuple(pages[:needed]), start, end)
            incoming = tuple(row for page in pages for row in page.rows)
            self.cache.save_inputs(incoming)
            rows = merge(rows, incoming, "明确检查更新：单位净值核验")
        self._check_plan_boundary(planned)
        selected_at = self.now()
        context = self.context_provider(self.settings.config, planned.raw["end"], selected_at) if self.context_provider else None
        self._check_plan_boundary(planned)
        return self.repository.publish(self.settings.config, self.settings.evidence, rows, end=planned.raw["end"],
            selection_at=selected_at, operation_key=record["operation_key"], expected=record["expected_snapshot_id"],
            allow_daily_signal=True, context=context)

    def _run(self, record: dict[str, Any], planned: Plan) -> None:
        """worker持根锁直至本地回执及外部租约结束；未决失败留给显式恢复。"""
        lease = None
        try:
            with self.store.writer():
                try:
                    self._check_plan_boundary(planned)
                    if self.periodic:
                        lease = self.periodic.begin([], target=record["coordinator_target"], automatic=False)
                        record = {**record, "batch_id": lease.row["id"]}
                    record = {**record, "state": "running", "updated_at": self.now()}
                    self._save(record)
                    snapshot = self._execute(record, planned)
                    record = {**record, "state": "completed", "snapshot_id": snapshot, "reason": None, "updated_at": self.now()}
                except CommitUncertain:
                    # 随后能读到发布不证明这次提交已获确认；只由显式原请求恢复收口。
                    raise
                except Exception as error:
                    # 发布可能已成功但回执写失败；先沿current链确认，不以异常冒充回滚。
                    snapshot = self._commit(record)
                    code = error.code if isinstance(error, (FlowError, BudgetError)) else "etf_update_failed"
                    record = {**record, "state": "completed" if snapshot else "interrupted" if code == "etf_update_interrupted" else "failed",
                              "snapshot_id": snapshot, "reason": None if snapshot else code, "updated_at": self.now()}
                self._save(record)
                if lease:
                    lease.finish(None if record["state"] == "completed" else "etf_update_failed")
                elif self.periodic:
                    # begin可能已落外部占位后才抛错；没有Lease返回不等于没有占位。
                    with self.periodic.recover_etf_zero(record["coordinator_target"], record["batch_id"]) as orphan:
                        if orphan:
                            orphan.finish(None if record["state"] == "completed" else "etf_update_failed")
                record = {**record, "lease_closed": True, "updated_at": self.now()}
                self._save(record)
        except CommitUncertain:
            if lease is not None and not lease.closed:
                try:
                    lease.finish('periodic_unresolved_batch')
                except Exception:
                    pass
            self._preserve_uncertain(record)
        except Exception:
            # 不明写入/回执保留queued/running及外部占位；GET只报告recovery_required。
            if lease is not None and not lease.closed:
                try:
                    lease.finish("periodic_unresolved_batch")
                except Exception:
                    pass

    def close(self, timeout: float = 3) -> bool:
        """只停止本runtime的worker和网络子进程，不取消其他业务。"""
        self.stop.set()
        worker = self._worker
        if worker and worker.ident is not None:
            worker.join(timeout)
        return worker is None or not worker.is_alive()

    def current(self, instance: str) -> dict[str, Any]:
        """只读当前发布、待发布配置和固定计划摘要；不初始化额度或恢复任务。"""
        self.check()
        now = self.now()
        current = self.store.current_id()
        loaded = self.repository.load(current) if current else None
        pool, rule = self.settings.config.selected(now)
        planned = self.plan()
        reason = None
        usage = None
        if not self.settings.options.write_enabled:
            reason = "etf_update_disabled"
        elif not self.store.initialized:
            reason = "etf_not_initialized"
        else:
            try:
                usage = self.budget.usage()
                self.budget.preflight(planned.network)
            except FlowError as error:
                reason = error.code
        records = self._records()[1]
        unresolved = [r for r in records if r["state"] not in TERMINAL or not r["lease_closed"]]
        current_records = [r for r in records if r["config_id"] == self.settings.id]
        if unresolved:
            reason = "etf_unresolved_operation"
        return {"snapshot_id": current, "selection_at": loaded.manifest["selection_at"] if loaded else None,
                "end": loaded.manifest["end"] if loaded else None, "server_day": instant(now).astimezone(SHANGHAI).date().isoformat(),
                "configuration_pending": self.repository.configuration_pending(loaded, self.settings.config, now) if loaded else True,
                "configuration_reason": "configuration_not_published" if loaded is None else
                    "configuration_changed" if self.repository.configuration_pending(loaded, self.settings.config, now) else None,
                "members": [asdict(m) for m in pool.members], "pool_version": pool.version, "rule_version": rule.version,
                "initialized": self.store.initialized, "write_enabled": self.settings.options.write_enabled,
                "blocked_reason": reason, "usage": usage,
                "plan": {"id": planned.id, "start": planned.raw["start"], "end": planned.raw["end"],
                         "member_ids": planned.raw["members"], "request_count": len(planned.network),
                         "cached_request_count": len(planned.requests) - len(planned.network),
                         "reserved_bytes": len(planned.network) * self.settings.grant.response_limit if self.settings.grant else None},
                "operation": self._response(current_records[-1], instance) if current_records else None,
                "unresolved": [{"request_id": r["request_id"], "config_id": r["config_id"], "instance_id": r["instance_id"]}
                               for r in unresolved]}

    def view(self, snapshot: str, *, mode: str, period: int, end: str | None = None, group: str | None = None) -> dict[str, Any]:
        from .view import build
        self.check()
        return build(self.repository, snapshot, mode=mode, period=period, end=end, group=group,
                     server_day=instant(self.now()).astimezone(SHANGHAI).date().isoformat())

    def evidence(self, snapshot: str, source: str) -> dict[str, Any]:
        self.check()
        return self.repository.evidence(snapshot, source)
