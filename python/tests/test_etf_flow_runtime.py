"""真实存储/协调器调用链隔离测试；故障点只作用于本测试根，不使用真实金融数据。"""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from etf_flow_fixture import AT, END, stored_sample
from pmi.market_data.etf_flow.budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.model import FlowError, Input, canonical, digest
from pmi.market_data.etf_flow.options import Options
from pmi.market_data.etf_flow.runtime import Runtime
from pmi.market_data.etf_flow.sources import SHARES_QUERY
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.etf_flow.transport import Original
from pmi.market_data.periodic_budget import Budget as PeriodicBudget, BudgetError, Lease, PeriodicOptions, initialize


class Crash(BaseException):
    """模拟进程在明确持久化边界停止；不会被业务Exception分支改写成正常失败。"""


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="etf-runtime-test-", dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.data = self.root / "etf"
        self.data.mkdir(mode=0o700)
        from sqlite_fixture import initialize as initialize_sqlite
        initialize_sqlite(self.data)
        self.store = Store(self.data)
        self.store.initialize()
        self.now = datetime.fromisoformat(AT)
        with self.store.writer():
            self.config, self.inputs, self.evidence, self.dates = stored_sample(self.store, getattr(self, 'sample_name', 'single'))
            Cache(self.store, None, self.config).save_inputs(self.inputs)
        self.paths = [self.root / name for name in ("config.json", "evidence.json", "grant.json")]
        member = self.config.pools[-1].members[0]
        self.grant_raw = {"id": "isolated-runtime", "confirmation": "仅隔离测试，不准真实取数",
            "confirmed_at": (self.now - timedelta(minutes=1)).isoformat(), "expires_at": (self.now + timedelta(days=1)).isoformat(),
            "members": [member.id], "start": self.dates[0], "end": END,
            "domains": ["query.sse.com.cn", "api.fund.eastmoney.com"], "max_requests": 1, "max_bytes": 2048,
            "response_limit": 2048, "interval_seconds": 3, "timeout_seconds": 1}
        for path, value in zip(self.paths, (self.config.raw, self.evidence.raw, self.grant_raw)):
            path.write_bytes(canonical(value))
            path.chmod(0o600)
        self.options = Options(self.data, *self.paths, write_enabled=True)
        with self.store.writer():
            Budget(self.store, Grant.parse(self.grant_raw), lambda: self.now).initialize()
        self.price = self.activity = self.data
        initialize(self.price, self.activity)
        self.periodic = PeriodicBudget(self.price, self.activity, PeriodicOptions(), lambda: self.now)
        self.runtimes = []
        self.runtime = self.new_runtime()

    def new_runtime(self):
        value = Runtime(self.options, clock=lambda: self.now, periodic=self.periodic)
        self.runtimes.append(value)
        return value

    def release_crashed_lease(self):
        # 模拟操作系统退出自动关闭fd；绝不调用finish去改写崩溃当时的账本。
        if self.periodic.active:
            lease = self.periodic.active
            lease.task.close()
            lease.closed = True
            self.periodic.active = None

    def tearDown(self):
        for runtime in self.runtimes:
            self.assertTrue(runtime.close(5), "测试worker必须退出")
        self.release_crashed_lease()
        self.tmp.cleanup()
        self.assertFalse(self.root.exists())

    def parameters(self, runtime=None):
        plan = (runtime or self.runtime).plan()
        return {"plan_id": plan.id, "expected_snapshot_id": plan.raw["expected_snapshot_id"]}

    def queued(self, request="operation-1"):
        parameters = self.parameters()
        with patch.object(threading.Thread, "start", return_value=None):
            status, _ = self.runtime.start(request, parameters, "instance-1")
        self.assertEqual(status, 202)
        return parameters, self.runtime._find(request), self.runtime.plan()

    def run_to_crash(self, record, plan, context):
        try:
            with context, self.assertRaises(Crash):
                self.runtime._run(record, plan)
        finally:
            self.release_crashed_lease()

    def assert_old_business_available(self):
        lease = self.periodic.begin([("isolated-price-request", 65536)], target="price:isolated", automatic=False)
        attempt = lease.charge("isolated-price-request", 65536)
        lease.settle(attempt, 7, True)
        lease.finish()
        lease = self.periodic.begin([("isolated-activity-request", 65536)], target="activity:isolated", automatic=False)
        attempt = lease.charge("isolated-activity-request", 65536)
        lease.settle(attempt, 9, True)
        lease.finish()
        self.assertEqual(self.periodic.status()["daily"], {"requests": 2, "bytes": 131072})

    def test_actual_worker_zero_network_publication_and_idempotent_replay_after_restart(self):
        parameters = self.parameters()
        self.assertEqual(self.runtime.plan().network, ())
        with patch.object(self.runtime.transport, "fetch", side_effect=AssertionError("无缺项不准出站")):
            status, accepted = self.runtime.start("operation-1", parameters, "instance-1")
            self.assertEqual(status, 202)
            self.runtime._worker.join(10)
        result = self.runtime.operation("operation-1", "instance-1")
        self.assertEqual(result["state"], "completed")
        self.assertFalse(result["recovery_required"])
        self.assertNotEqual(self.runtime.plan().id, parameters["plan_id"])
        self.now += timedelta(days=2)  # 旧授权已过期、当前缺日计划变化，原请求仍重放。
        restarted = self.new_runtime()
        status, replay = restarted.start("operation-1", parameters, "instance-2")
        self.assertEqual(status, 200)
        self.assertEqual(replay["snapshot_id"], result["snapshot_id"])
        self.assertEqual(replay["instance_id"], "instance-1")
        self.assertEqual(replay["serving_instance_id"], "instance-2")
        self.assertEqual(restarted.budget.usage()["requests"], 0)
        self.assertEqual(self.periodic.status()["daily"]["requests"], 0)
        with self.assertRaisesRegex(FlowError, "operation_conflict"):
            restarted.start("operation-1", {**parameters, "plan_id": digest("different")}, "instance-2")

    def test_commit_uncertainty_at_publication_and_receipts_requires_explicit_recovery(self):
        from pmi.market_data.storage import database
        from pmi.market_data.storage.documents import Documents
        commit = database._commit
        for stage in ('publication-before', 'publication-after', 'receipt-after', 'close-after'):
            with self.subTest(stage=stage):
                parameters, record, plan = self.queued(stage)
                old = self.store.current_id()
                fired = []
                def fault(connection):
                    current = connection.execute("SELECT publication_id FROM current_publication WHERE domain_id='etf'").fetchone()
                    op = connection.execute("SELECT revision FROM operation WHERE domain_id='etf' AND request_id=?", (record['operation_key'],)).fetchone()
                    status = Documents(connection).get(op[0]) if op else None
                    target = (bool(current) and current[0] != old if stage.startswith('publication') else
                              bool(status) and status['state'] == 'completed' and status['lease_closed'] == (stage == 'close-after'))
                    if not fired and target:
                        fired.append(True)
                        if stage != 'publication-before': commit(connection)
                        raise OSError('synthetic commit uncertainty')
                    commit(connection)
                with patch.object(database, '_commit', fault), patch.object(self.runtime.transport, 'fetch', side_effect=AssertionError('禁止出站')):
                    self.runtime._run(record, plan)
                self.assertEqual(fired, [True])
                snapshot = self.store.current_id()
                self.assertEqual(snapshot == old, stage == 'publication-before')
                state = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*') if p.is_file()}
                before = state()
                restarted = self.new_runtime()
                for runtime in (self.runtime, restarted):
                    result = runtime.operation(stage, 'instance-2')
                    self.assertEqual(result['state'], 'running')
                    self.assertEqual(result['reason'], 'etf_commit_uncertain')
                    self.assertTrue(result['recovery_required'])
                    self.assertEqual(result['operation_key'], record['operation_key'])
                    self.assertEqual(result['instance_id'], 'instance-1')
                self.assertEqual(before, state())
                with patch.object(restarted.transport, 'fetch', side_effect=AssertionError('恢复不得取数')):
                    _, result = restarted.start(stage, parameters, 'instance-2')
                self.assertEqual(result['state'], 'interrupted' if stage == 'publication-before' else 'completed')
                self.assertFalse(result['recovery_required'])
                self.assertEqual(self.store.current_id(), snapshot)
                self.assertEqual(restarted.budget.usage()['requests'], 0)
                self.assertEqual(self.periodic.status()['daily']['requests'], 0)
                self.runtime = restarted

    def test_read_does_not_repair_queued_and_explicit_replay_recovers_before_begin(self):
        parameters, record, _ = self.queued()
        files = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob("*") if p.is_file()}
        result = self.runtime.operation("operation-1", "instance-2")
        self.assertTrue(result["recovery_required"])
        self.assertEqual(files, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob("*") if p.is_file()})
        with self.assertRaisesRegex(FlowError, "unresolved"):
            self.runtime.start("new-id", parameters, "instance-2")
        status, recovered = self.new_runtime().start("operation-1", parameters, "instance-2")
        self.assertEqual(status, 200)
        self.assertEqual(recovered["state"], "interrupted")
        self.assertFalse(recovered["recovery_required"])
        self.assertEqual(self.periodic.read()["batches"], [])
        self.assert_old_business_available()

    def test_recovery_commit_uncertainty_and_plain_receipt_failure_keep_original_identity(self):
        from pmi.market_data.storage import database
        from pmi.market_data.storage.documents import Documents
        parameters, record, plan = self.queued('receipt-failure')
        save, failed = self.runtime._save, []
        def receipt(value):
            if value['state'] == 'completed' and not failed:
                failed.append(True)
                raise OSError('synthetic receipt failure outside commit')
            save(value)
        with patch.object(self.runtime, '_save', receipt), patch.object(self.runtime.transport, 'fetch', side_effect=AssertionError('禁止出站')):
            self.runtime._run(record, plan)
        self.assertEqual(failed, [True])
        snapshot = self.store.current_id()
        self.assertIsNotNone(snapshot)
        self.assertTrue(self.runtime.operation('receipt-failure', 'instance-2')['recovery_required'])
        commit, fired = database._commit, []
        def uncertain(connection):
            row = connection.execute("SELECT revision FROM operation WHERE domain_id='etf' AND request_id=?", (record['operation_key'],)).fetchone()
            value = Documents(connection).get(row[0]) if row else {}
            commit(connection)
            if value.get('lease_closed') and not fired:
                fired.append(True)
                raise OSError('synthetic uncertainty during explicit recovery')
        with patch.object(database, '_commit', uncertain), self.assertRaises(database.CommitUncertain):
            self.runtime.start('receipt-failure', parameters, 'instance-2')
        self.assertEqual(fired, [True])
        value = self.runtime.operation('receipt-failure', 'instance-2')
        self.assertEqual(value['state'], 'running'); self.assertTrue(value['recovery_required'])
        restarted = self.new_runtime()
        self.assertTrue(restarted.operation('receipt-failure', 'instance-3')['recovery_required'])
        with patch.object(restarted.transport, 'fetch', side_effect=AssertionError('恢复不得出站')):
            _, value = restarted.start('receipt-failure', parameters, 'instance-3')
        self.assertEqual(value['state'], 'completed'); self.assertFalse(value['recovery_required'])
        self.assertEqual(value['instance_id'], 'instance-1'); self.assertEqual(value['snapshot_id'], snapshot)
        self.assertEqual(restarted.budget.usage()['requests'], 0)
        self.assertEqual(len(self.periodic.read()['batches']), 1)

    def test_crash_after_external_begin_before_batch_id_save(self):
        parameters, record, plan = self.queued()
        original_save = self.runtime._save
        def fail(value):
            if value["state"] == "running":
                raise Crash()
            original_save(value)
        self.run_to_crash(record, plan, patch.object(self.runtime, "_save", side_effect=fail))
        self.assertIsNone(self.runtime._find("operation-1")["batch_id"])
        self.assertEqual(self.periodic.status()["active"]["target"], record["coordinator_target"])
        _, result = self.new_runtime().start("operation-1", parameters, "instance-2")
        self.assertEqual(result["state"], "interrupted")
        self.assertIsNone(self.periodic.status()["active"])
        self.assert_old_business_available()

    def test_commit_before_receipt_preserved_and_replayed_even_when_cas_changes(self):
        parameters, record, plan = self.queued()
        save = self.runtime._save
        def fail(value):
            if value["state"] == "completed":
                raise Crash()
            save(value)
        self.run_to_crash(record, plan, patch.object(self.runtime, "_save", side_effect=fail))
        snapshot = self.store.current_id()
        self.assertIsNotNone(snapshot)
        self.assertEqual(self.runtime._find("operation-1")["state"], "running")
        _, result = self.new_runtime().start("operation-1", parameters, "instance-2")
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["snapshot_id"], snapshot)
        self.assertEqual(self.store.current_id(), snapshot)
        self.assertIsNone(self.periodic.status()["active"])

    def test_terminal_before_external_finish_and_recovery_can_itself_be_interrupted(self):
        parameters, record, plan = self.queued()
        self.run_to_crash(record, plan, patch.object(Lease, "finish", side_effect=Crash()))
        self.assertEqual(self.runtime._find("operation-1")["state"], "completed")
        snapshot = self.store.current_id()
        restarted = self.new_runtime()
        try:
            with patch.object(Lease, "finish", side_effect=Crash()), self.assertRaises(Crash):
                restarted.start("operation-1", parameters, "instance-2")
        finally:
            self.release_crashed_lease()
        status, result = restarted.start("operation-1", parameters, "instance-2")
        self.assertEqual(status, 200)
        self.assertEqual(result["snapshot_id"], snapshot)
        self.assertEqual(len(self.periodic.read()["batches"]), 1)
        self.assertIsNone(self.periodic.status()["active"])

    def test_external_finish_before_final_local_receipt_can_replay(self):
        parameters, record, plan = self.queued()
        save = self.runtime._save
        def fail(value):
            if value["lease_closed"]:
                raise Crash()
            save(value)
        self.run_to_crash(record, plan, patch.object(self.runtime, "_save", side_effect=fail))
        self.assertIsNone(self.periodic.status()["active"])
        self.assertFalse(self.runtime._find("operation-1")["lease_closed"])
        _, result = self.new_runtime().start("operation-1", parameters, "instance-2")
        self.assertEqual(result["state"], "completed")
        self.assertFalse(result["recovery_required"])
        self.assertEqual(self.periodic.read()["days"], {})

    def test_other_business_unresolved_or_live_lease_never_released(self):
        parameters, _, _ = self.queued()
        lease = self.periodic.begin([("other", 65536)], target="activity:other", automatic=False)
        before = self.periodic.path.read_bytes()
        with self.assertRaisesRegex(FlowError, "etf_busy"):
            self.runtime.start("operation-1", parameters, "instance-2")
        self.assertEqual(self.periodic.path.read_bytes(), before)
        self.release_crashed_lease()
        with self.assertRaisesRegex(BudgetError, "unresolved"):
            self.runtime.start("operation-1", parameters, "instance-2")
        self.assertEqual(self.periodic.path.read_bytes(), before)

    def test_nonzero_or_mismatched_external_lease_cannot_be_recovered(self):
        _, record, _ = self.queued()
        lease = self.periodic.begin([("other", 65536)], target=record["coordinator_target"], automatic=False)
        lease.charge("other", 65536)
        self.release_crashed_lease()
        before = self.periodic.path.read_bytes()
        with self.assertRaisesRegex(BudgetError, "not_zero"):
            with self.periodic.recover_etf_zero(record["coordinator_target"], None):
                self.fail("不得恢复带真实出站占额的批次")
        with self.assertRaisesRegex(BudgetError, "target_invalid"):
            with self.periodic.recover_etf_zero(record["coordinator_target"], "f" * 32):
                pass
        self.assertEqual(before, self.periodic.path.read_bytes())

    def test_publication_failure_preserves_current_and_budget_then_new_check_reuses_verified_cache(self):
        # 缺末日份额；其他已核验输入全部缓存，源失败不发布半批。
        with self.store.writer():
            cache = self.runtime.cache
            ref, _ = self.store.journal(cache.inputs_key)
            shortened = []
            for row in self.inputs:
                raw = deepcopy(row.raw)
                if row.date == END:
                    raw["fields"].pop("shares")
                shortened.append(Input.parse(raw))
            self.store.write_journal(cache.inputs_key, {"input_refs": [self.store.put_json(x.raw) for x in shortened]}, ref)
        parameters = self.parameters()
        self.assertEqual(len(self.runtime.plan().network), 1)
        calls = []
        def fetch(request, key):
            calls.append(request)
            attempt = self.runtime.budget.charge(request, key)
            member = self.config.pools[-1].members[0]
            raw = canonical({"sqlId": SHARES_QUERY, "result": [{"SEC_CODE": member.code, "STAT_DATE": END, "TOT_VOL": "2.00"}]})
            source = self.runtime.budget.settle(attempt, raw, True)
            receipt = self.runtime.store.put_json({"object_id": source, "request_key": request.key, "code": None})
            return Original(request, attempt, source, raw, AT, receipt)
        with patch.object(self.runtime.transport, "fetch", side_effect=fetch), patch.object(self.runtime.repository, "publish", side_effect=FlowError("etf_test_publication_failure")):
            self.runtime.start("operation-1", parameters, "instance-1")
            self.runtime._worker.join(10)
        self.assertEqual(self.runtime.operation("operation-1", "instance-1")["state"], "failed")
        self.assertEqual(self.runtime.operation("operation-1", "instance-1")["reason"], "etf_test_publication_failure")
        self.assertIsNone(self.store.current_id())
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.runtime.budget.usage()["requests"], 1)
        status, _ = self.runtime.start("operation-1", parameters, "instance-2")
        self.assertEqual(status, 200)  # 额度已用尽仍回放原失败，不取数。
        new_parameters = self.parameters()
        self.assertEqual(self.runtime.plan().network, ())
        with patch.object(self.runtime.transport, "fetch", side_effect=AssertionError("必须复用缓存")):
            self.runtime.start("operation-2", new_parameters, "instance-1")
            self.runtime._worker.join(10)
        self.assertEqual(self.runtime.operation("operation-2", "instance-1")["state"], "completed")
        self.assertEqual(self.runtime.budget.usage()["requests"], 1)

    def test_read_only_and_changed_config_guard_precede_replay(self):
        parameters, _, _ = self.queued()
        self.paths[0].write_bytes(self.paths[0].read_bytes() + b"\n")
        with self.assertRaisesRegex(FlowError, "configuration_changed"):
            self.runtime.start("operation-1", parameters, "instance-2")
        self.paths[0].write_bytes(canonical(self.config.raw))
        readonly = Runtime(Options(self.data, *self.paths, write_enabled=False), clock=lambda: self.now)
        self.runtimes.append(readonly)
        with self.assertRaisesRegex(FlowError, "update_disabled"):
            readonly.start("operation-1", parameters, "instance-2")

    def test_old_operation_read_keeps_identity_but_cannot_replay_under_new_connection(self):
        parameters = self.parameters()
        with patch.object(self.runtime.transport, 'fetch', side_effect=AssertionError('no network')):
            self.runtime.start('old-operation', parameters, 'old-instance')
            self.runtime._worker.join(10)
        original = self.runtime.operation('old-operation', 'old-instance')
        self.assertEqual(original['state'], 'completed')
        fresh = Runtime(self.options, clock=lambda: self.now, connection_id='a' * 64)
        self.runtimes.append(fresh)
        before = {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                  for p in self.data.rglob('*') if p.is_file()}
        found = fresh.operation('old-operation', 'new-instance')
        self.assertEqual(found['config_id'], original['config_id'])
        self.assertEqual(found['instance_id'], 'old-instance')
        self.assertEqual(found['snapshot_id'], original['snapshot_id'])
        self.assertEqual(found['serving_config_id'], fresh.settings.id)
        self.assertNotEqual(found['serving_config_id'], found['config_id'])
        with patch.object(fresh.transport, 'fetch', side_effect=AssertionError('old plan cannot fetch')):
            with self.assertRaisesRegex(FlowError, 'plan_changed'):
                fresh.start('old-operation', parameters, 'new-instance')
        self.assertEqual(before, {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                                 for p in self.data.rglob('*') if p.is_file()})

    def test_begin_failure_after_persistent_reservation_does_not_leave_invisible_blocker(self):
        parameters, record, plan = self.queued()
        begin = self.periodic.begin
        def begin_then_fail(*args, **kwargs):
            lease = begin(*args, **kwargs)
            self.release_crashed_lease()
            raise OSError("isolated failure after begin")
        with patch.object(self.periodic, "begin", side_effect=begin_then_fail):
            self.runtime._run(record, plan)
        result = self.runtime.operation("operation-1", "instance-1")
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["recovery_required"])
        self.assertIsNone(self.periodic.status()["active"])
        self.assert_old_business_available()
