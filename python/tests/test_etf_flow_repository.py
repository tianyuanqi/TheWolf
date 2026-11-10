"""固定版本、准入引用、首次补历史、迟到修订和披露时间的持久化反例。"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from etf_flow_fixture import AT, END, configuration, stored_sample
from pmi.market_data.etf_flow.evidence import Evidence
from pmi.market_data.etf_flow.model import Configuration, FlowError, Input, canonical, digest
from pmi.market_data.etf_flow.repository import Repository
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.etf_flow.view import build


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="etf-repository-test-", dir="/private/tmp")
        self.root = Path(self.temporary.name)
        self.store = Store(self.root)
        self.store.initialize()
        self.repo = Repository(self.store)
        with self.store.writer():
            self.config, self.inputs, self.evidence, self.dates = stored_sample(self.store)

    def tearDown(self):
        self.temporary.cleanup()
        self.assertFalse(self.root.exists())

    def publish(self, key, inputs=None, evidence=None, config=None, at=AT, end=END, daily=False):
        with self.store.writer():
            return self.repo.publish(config or self.config, evidence or self.evidence, inputs or self.inputs,
                end=end, selection_at=at, operation_key=digest(key), expected=self.store.current_id(), allow_daily_signal=daily)

    def test_initial_history_not_original_signal_and_read_does_not_mutate(self):
        snapshot = self.publish("initial", daily=True)
        loaded = self.repo.load(snapshot)
        self.assertEqual(len(loaded.admissions), 1)
        self.assertEqual(loaded.admissions[0].first_qualified_at, AT)
        self.assertEqual(len(loaded.admissions[0].input_refs), 321)
        self.assertEqual(self.repo.evaluations(loaded, "original", None), {})
        self.assertEqual(len(self.repo.evaluations(loaded, "current", None)), 260)
        self.assertEqual(loaded.calculator.evaluate(END, original=True)["valid_count"], 0)  # 不倒写昨日已准入。
        before = {str(p.relative_to(self.root)): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        other = Repository(Store(self.root))
        current = other.evaluations(other.load(snapshot), "current", None)
        after = {str(p.relative_to(self.root)): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(current[END]["amount"], "40")

    def test_future_configuration_pending_without_clock_dependent_old_result(self):
        raw = deepcopy(self.config.raw)
        future = deepcopy(raw["pool_versions"][-1])
        future.update(version="test-future", effective_date="2026-11-06", confirmed_at=AT, change="配置预定停用")
        future["members"][0]["disabled_date"] = "2026-11-06"
        raw["pool_versions"].append(future)
        config = Configuration.parse(raw)
        snapshot = self.publish("before-effective", config=config)
        loaded = self.repo.load(snapshot)
        values = self.repo.evaluations(loaded, "current", None)
        next_at = "2026-11-06T12:00:00+08:00"
        self.assertFalse(self.repo.configuration_pending(loaded, config, AT))
        self.assertTrue(self.repo.configuration_pending(loaded, config, next_at))
        self.assertEqual(values, self.repo.evaluations(self.repo.load(snapshot), "current", None))
        after = self.publish("configuration-only", config=config, at=next_at)
        result = self.repo.evaluations(self.repo.load(after), "current", None)[END]
        self.assertEqual(result["active_count"], 0)
        self.assertNotEqual(result["result_id"], values[END]["result_id"])
        self.assertEqual(self.repo.evaluations(self.repo.load(snapshot), "current", None), values)

    def next_day(self, nav="1", at="2026-11-06T12:00:00+08:00"):
        raw = deepcopy(self.inputs[-1].raw)
        raw.update(date="2026-11-05", revision_reason="隔离新增或修订")
        source = self.store.put(canonical({"test": "next-day", "nav": nav, "at": at}))
        for field in raw["fields"].values():
            field["date"] = raw["date"]
            field["source"].update(object_id=source, retrieved_at=at)
        raw["fields"]["shares"]["value"] = str(self.inputs[-1].value("shares") + 50)
        raw["fields"]["nav"]["value"] = nav
        evidence = deepcopy(self.evidence.raw)
        evidence.update(version="test-evidence-2", confirmed_at=at)
        evidence["adjustments"][0]["end"] = raw["date"]
        return Input.parse(raw), Evidence.parse(evidence, {m.id for m in self.config.pools[-1].members})

    def test_daily_record_preserved_after_late_correction_and_old_evidence_readable(self):
        first = self.publish("first")
        with self.store.writer():
            new, evidence = self.next_day()
        second = self.publish("daily", self.inputs + (new,), evidence, at="2026-11-06T12:00:00+08:00", end=new.date, daily=True)
        old_record = self.repo.evaluations(self.repo.load(second), "original", None)
        self.assertEqual(list(old_record), [new.date])
        self.assertEqual(old_record[new.date]["amount"], "50")
        with self.store.writer():
            correction, _ = self.next_day(nav="2", at="2026-11-06T13:00:00+08:00")
        third = self.publish("correction", self.inputs + (correction,), evidence, at="2026-11-06T13:00:00+08:00", end=new.date, daily=True)
        self.assertEqual(self.repo.evaluations(self.repo.load(third), "original", None), old_record)
        self.assertEqual(self.repo.evaluations(self.repo.load(third), "current", None)[new.date]["amount"], "100")
        original_view = build(self.repo, third, mode="original", period=60, end=new.date, group=None, server_day="2026-11-06")
        current_view = build(self.repo, third, mode="current", period=60, end=new.date, group=None, server_day="2026-11-06")
        self.assertEqual(original_view["members"][0]["metrics"]["amount"], "50")
        self.assertEqual(current_view["members"][0]["metrics"]["amount"], "100")
        self.assertEqual(original_view["members"][0]["input_basis"], "recorded_inputs")
        source = new.fields["nav"].source.object_id
        self.assertEqual(self.repo.evidence(third, source)["object_id"], source)
        self.assertEqual(self.repo.evaluations(self.repo.load(first), "original", None), {})
        self.assertEqual(self.store.published_operation(digest("daily"))[0], second)

    def test_old_config_or_data_cannot_be_removed_and_unreferenced_object_hidden(self):
        first = self.publish("first")
        raw = deepcopy(self.config.raw)
        raw["pool_versions"][0]["members"][0]["name"] += "修改"
        with self.assertRaises(FlowError):
            self.publish("rewrite", config=Configuration.parse(raw))
        with self.assertRaises(FlowError):
            self.publish("remove", inputs=self.inputs[1:])
        self.assertEqual(self.store.current_id(), first)
        with self.store.writer():
            unreferenced = self.store.put(b"unreferenced test original")
        with self.assertRaises(FlowError):
            self.repo.evidence(first, unreferenced)

    def test_disclosures_public_date_not_report_date_and_unknown_event_date(self):
        member = self.config.pools[-1].members[0]
        raw = deepcopy(self.evidence.raw)
        raw["disclosures"] = [{"id": "test-report", "member_id": member.id, "report_date": "2026-06-30",
            "published_date": "2026-08-29", "source_id": raw["sources"][0]["object_id"], "locator": "虚构测试页",
            "state": "not_disclosed", "holders": [], "note": "未披露并非零持仓"}]
        raw["events"] = [{"id": "test-event", "member_ids": [member.id], "occurred_start": None, "occurred_end": None,
            "published_date": "2026-08-29", "source_id": raw["sources"][0]["object_id"], "locator": "虚构公告",
            "description": "仅测试，实际发生日未知", "subjects": []}]
        evidence = Evidence.parse(raw, {member.id})
        self.assertEqual(evidence.public("2026-07-01")["disclosures"], [])
        later = evidence.public("2026-07-01", include_later=True)
        self.assertEqual(later["disclosures"][0]["knowledge"], "later_comparison")
        visible = evidence.public("2026-08-29")
        self.assertEqual(visible["disclosures"][0]["holders"], [])
        self.assertEqual(visible["events"][0]["marker_kind"], "announcement")
        self.assertEqual(visible["events"][0]["marker_date"], "2026-08-29")


if __name__ == "__main__":
    unittest.main()
