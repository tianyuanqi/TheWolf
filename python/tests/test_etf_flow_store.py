"""隔离文件系统检查发布、失败保旧、旧引用、预算与未决恢复基础。"""
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import patch

from etf_flow_fixture import configuration, stored_sample, AT, END
from pmi.market_data.etf_flow.budget import Budget, Grant, Request
from pmi.market_data.etf_flow.model import FlowError, canonical, digest
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.storage import StorageError
from pmi.market_data.etf_flow.repository import Repository


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="etf-store-test-", dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.store = Store(self.root)

    def tearDown(self):
        self.temporary.cleanup()
        self.assertFalse(self.root.exists(), "本次自有假数据根必须实际清理")

    def test_reads_do_not_initialize_or_create_locks(self):
        before = list(self.root.iterdir())
        self.assertIsNone(self.store.current_id())
        self.assertFalse(self.store.initialized)
        self.assertEqual(before, list(self.root.iterdir()))

    def test_fixed_objects_cas_and_published_parent_chain(self):
        self.store.initialize()
        operation = digest("isolated-operation")
        with self.store.writer():
            incomplete = self.store.put_json({"format": "etf-flow-snapshot-v1", "parent": None, "operation_key": operation})
            with self.assertRaisesRegex(FlowError, 'invalid_fields'):
                self.store.publish(incomplete, None)
            config, inputs, evidence, _ = stored_sample(self.store)
            repo = Repository(self.store)
            with patch.object(self.store, 'publish'):
                original = repo.publish(config, evidence, inputs, end=END, selection_at=AT, operation_key=operation, expected=None)
            self.assertIsNone(self.store.published_operation(operation))  # 写对象不等于发布。
            self.store.publish(original, None)
            old_bytes = self.store.get(original)
            with patch.object(self.store, 'publish'):
                next_id = repo.publish(config, evidence, inputs, end=END, selection_at=AT, operation_key=digest('next'), expected=original)
            with self.assertRaises(FlowError):
                self.store.publish(next_id, None)
            self.assertEqual(self.store.current_id(), original)
            self.store.publish(next_id, original)
        self.assertEqual(self.store.published_operation(operation)[0], original)
        self.assertEqual(self.store.get(original), old_bytes)
        self.assertEqual(Store(self.root).current_id(), next_id)

    def test_state_history_keeps_old_reference_and_rejects_stale_write(self):
        self.store.initialize()
        key = digest("state")
        with self.store.writer():
            first = self.store.write_journal(key, {"state": "queued"}, None)
            old = self.store.get(first)
            second = self.store.write_journal(key, {"state": "completed"}, first)
            with self.assertRaises(FlowError):
                self.store.write_journal(key, {"state": "failed"}, first)
        self.assertEqual(self.store.get(first), old)
        self.assertEqual(self.store.journal(key), (second, {"state": "completed"}))
        self.assertEqual(self.store.get_json(second)["previous"], first)

    def test_exclusive_writer_and_corrupt_or_linked_object_rejected(self):
        self.store.initialize()
        other = Store(self.root)
        result = []
        def independent_writer():
            try:
                with other.writer():
                    result.append('unexpected_writer')
            except FlowError as error:
                result.append(error.code)
        with self.store.writer():
            worker = threading.Thread(target=independent_writer)
            worker.start(); worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, ['etf_busy'])
            source = self.store.put(b"isolated original")
        path = self.root / "objects" / source
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(StorageError, 'original_corrupt'):
            self.store.get(source)
        path.unlink()  # 仅隔离故障对象；不在产品提供删除接口。
        path.symlink_to(self.root / "facts.sqlite")
        with self.assertRaises(ValueError):
            self.store.get(source)

    def test_partial_initialization_not_silently_repaired(self):
        (self.root / "objects").mkdir()
        before = list(self.root.iterdir())
        with self.assertRaises(FlowError):
            self.store.current_id()
        self.assertEqual(before, list(self.root.iterdir()))

    def budget(self, count=2):
        member = configuration()["pool_versions"][0]["members"][0]
        self.now = datetime.fromisoformat("2026-11-05T12:00:00+08:00")
        grant = Grant.parse({"id": "isolated-grant", "confirmed_at": "2026-11-05T11:00:00+08:00",
            "confirmation": "仅隔离测试", "expires_at": "2026-11-06T12:00:00+08:00", "members": [member["id"]],
            "start": "2026-11-03", "end": "2026-11-04", "domains": ["www.sse.com.cn"],
            "max_requests": count, "max_bytes": count * 100, "response_limit": 100, "interval_seconds": 3, "timeout_seconds": 30})
        budget = Budget(self.store, grant, clock=lambda: self.now)
        request = Request("shares", member["id"], "2026-11-04", "2026-11-04", member["basis"]["url"])
        return budget, request

    def test_budget_persistent_charge_failure_no_refund_restart_no_reset(self):
        self.store.initialize()
        budget, request = self.budget(count=1)
        with self.store.writer():
            budget.initialize()
            budget.preflight((request,))
            attempt = budget.charge(request, digest("operation"))
            source = budget.settle(attempt, b"failed response", False)
        self.assertEqual(budget.usage()["requests"], 1)
        self.assertEqual(budget.usage()["reserved_bytes"], 100)
        self.assertEqual(self.store.get(source), b"failed response")
        restarted = Budget(Store(self.root), budget.grant, clock=lambda: self.now)
        with self.assertRaises(FlowError):
            restarted.preflight((request,))
        restarted.preflight(())  # 余额耗尽仍允许无出站核验/配置发布。
        with self.store.writer(), self.assertRaises(FlowError):
            budget.initialize()

    def test_unsettled_attempt_recovery_keeps_unknown_and_delay_after_end(self):
        self.store.initialize()
        budget, request = self.budget()
        operation = digest("operation")
        with self.store.writer():
            budget.initialize()
            budget.charge(request, operation)
            with self.assertRaises(FlowError):
                budget.preflight((request,))
            self.now += timedelta(seconds=30)
            budget.close_unknown(operation)
            with self.assertRaises(FlowError):
                budget.charge(request, digest("second"))
            self.now += timedelta(seconds=3)
            attempt = budget.charge(request, digest("second"))
            budget.settle(attempt, b"ok", True)
        self.assertEqual(budget.usage()["unknown_attempts"], 1)
        self.assertEqual(budget.usage()["requests"], 2)
        self.assertEqual(budget.usage()["reserved_bytes"], 200)

    def test_bad_scope_expiry_oversize_and_clock_regression(self):
        self.store.initialize()
        budget, request = self.budget()
        with self.store.writer():
            budget.initialize()
            with self.assertRaises(FlowError):
                budget.preflight((Request(request.kind, request.member_id, "2026-11-02", request.end, request.url),))
            with self.assertRaises(FlowError):
                budget.preflight((Request(request.kind, request.member_id, request.start, request.end, "https://example.com/"),))
            attempt = budget.charge(request, digest("operation"))
            with self.assertRaises(FlowError):
                budget.settle(attempt, b"x" * 101, True)
            budget.settle(attempt, b"x", False)
            self.now -= timedelta(seconds=1)
            with self.assertRaises(FlowError):
                budget.preflight((request,))
            self.now += timedelta(days=2)
            with self.assertRaises(FlowError):
                budget.preflight((request,))


if __name__ == "__main__":
    unittest.main()
