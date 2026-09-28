import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from pmi.snapshot import (DailyBar, DocumentEvidence, MarketContract, SliceInput, SnapshotError,
                          publish_snapshot, read_pdf, read_snapshot)


def fixture() -> SliceInput:
    """构造跨测试模块复用的合成切片，不读取真实行情或公告。"""
    return SliceInput(
        instrument_code="002245", instrument_name="测试证券", exchange="SZSE",
        source_id="synthetic-test-only", source_version="fixture-v1",
        source_policy_version="synthetic-policy-v1", batch_id="synthetic-batch-1",
        market_contract=MarketContract(
            source_url="https://example.invalid/fixture-market",
            raw_publisher="synthetic publisher", transport_id="synthetic transport",
            source_symbol="synthetic.002245", trading_scope="synthetic SZSE shares",
            price_resolution="synthetic cent", volume_resolution="synthetic share",
            amount_resolution="synthetic yuan",
            verification_source_url="https://example.invalid/verification",
            currency="CNY", adjustment="none", raw_price_unit="CNY/share",
            raw_volume_unit="synthetic shares", raw_amount_unit="synthetic CNY",
            normalization_version="synthetic-v1"),
        retrieved_at="2026-09-23T09:00:00+08:00",
        complete_through_date="2026-09-22", completion_basis="synthetic fixture",
        calendar_dates=("2026-09-21", "2026-09-22"),
        bars=(DailyBar("2026-09-21", "10.00", "11.00", "9.50", "10.50",
                       "1200", "12500.00"),),
        document=DocumentEvidence("fixture-001", "测试公告", "测试主体",
                                  "https://example.invalid/fixture.pdf", "2026-09-22",
                                  "date", 1, "仅供合成测试"),
        raw_response=b'{"fixture":true}',
        verification_response=b'{"verified":"synthetic"}',
        pdf_bytes=b"%PDF-1.4\nfixture",
    )


class SnapshotTests(unittest.TestCase):
    def test_old_batch_retry_does_not_rewind_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture()
            old_id = publish_snapshot(root, original)
            revised = replace(original, batch_id="synthetic-batch-2",
                              retrieved_at="2026-09-24T09:00:00+08:00",
                              bars=(replace(original.bars[0], close_cny="10.60"),))
            new_id = publish_snapshot(root, revised)
            self.assertEqual(publish_snapshot(root, original), old_id)
            self.assertEqual(read_snapshot(root)["snapshot_id"], new_id)
            self.assertEqual(read_snapshot(root, old_id)["bars"][0]["close_cny"], "10.50")
            self.assertEqual(read_snapshot(root, new_id)["bars"][0]["close_cny"], "10.60")
            self.assertEqual(publish_snapshot(root, revised), new_id)
            self.assertEqual(read_snapshot(root)["snapshot_id"], new_id)
            third = replace(revised, batch_id="synthetic-batch-3",
                            retrieved_at="2026-09-25T09:00:00+08:00",
                            bars=(replace(original.bars[0], close_cny="10.70"),))
            third_id = publish_snapshot(root, third)
            self.assertEqual(read_snapshot(root)["snapshot_id"], third_id)
            backfilled = replace(original, batch_id="synthetic-backfill",
                                 retrieved_at="2026-09-22T09:00:00+08:00",
                                 bars=(replace(original.bars[0], close_cny="10.80"),))
            backfill_id = publish_snapshot(root, backfilled)
            self.assertEqual(read_snapshot(root)["snapshot_id"], third_id)
            self.assertEqual(read_snapshot(root, backfill_id)["bars"][0]["close_cny"], "10.80")

    def test_mapped_manifest_must_match_snapshot_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = fixture()
            old_id = publish_snapshot(root, original)
            revised = replace(original, batch_id="synthetic-batch-2",
                              bars=(replace(original.bars[0], close_cny="10.60"),))
            new_id = publish_snapshot(root, revised)
            with sqlite3.connect(root / "slice.sqlite") as connection:
                connection.execute("UPDATE snapshots SET manifest_object_id=? WHERE snapshot_id=?",
                                   (new_id, old_id))
            with self.assertRaisesRegex(SnapshotError, "identity|manifest"):
                read_snapshot(root, old_id)
            self.assertEqual(read_snapshot(root, new_id)["snapshot_id"], new_id)

    def test_partial_window_then_fill_preserves_fixed_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            partial_id = publish_snapshot(root, fixture())
            partial = read_snapshot(root, partial_id)
            self.assertEqual(partial["unknown_missing_dates"], ["2026-09-22"])
            second_bar = replace(fixture().bars[0], trade_date="2026-09-22",
                                 open_cny="10.60", high_cny="11.20",
                                 low_cny="10.20", close_cny="10.80")
            filled = replace(fixture(), batch_id="synthetic-batch-filled",
                             bars=fixture().bars + (second_bar,),
                             raw_response=b'{"fixture":"two days"}')
            full_id = publish_snapshot(root, filled)
            current = read_snapshot(root)
            self.assertNotEqual(partial_id, full_id)
            self.assertEqual(current["observed_count"], 2)
            self.assertEqual(current["unknown_missing_dates"], [])
            self.assertEqual(len({row["trade_date"] for row in current["bars"]}), 2)
            self.assertEqual(read_snapshot(root, partial_id), partial)
            self.assertEqual(full_id, publish_snapshot(root, filled))

    def test_second_document_adds_version_without_changing_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_id = publish_snapshot(root, fixture())
            old = read_snapshot(root, old_id)
            report_pdf = b"%PDF-1.4\nsecond synthetic report"
            report = replace(fixture().document,
                             document_id="fixture-report-002",
                             title="测试正式报告", published_at="2026-09-23",
                             physical_page=2)
            expanded = replace(fixture(), batch_id="synthetic-batch-with-report",
                               additional_documents=(report,),
                               additional_pdf_bytes=(report_pdf,))
            new_id = publish_snapshot(root, expanded)
            current = read_snapshot(root)
            self.assertNotEqual(new_id, old_id)
            self.assertEqual(len(current["documents"]), 2)
            self.assertEqual(read_pdf(root, new_id,
                                      current["documents"][1]["pdf_object_id"]), report_pdf)
            self.assertEqual(read_snapshot(root, old_id), old)
            with self.assertRaises(SnapshotError):
                read_pdf(root, old_id, current["documents"][1]["pdf_object_id"])
            (root / "objects" / current["documents"][1]["pdf_object_id"]).write_bytes(
                b"corrupt report")
            with self.assertRaisesRegex(SnapshotError, "hash mismatch"):
                read_snapshot(root, new_id)
            self.assertEqual(read_snapshot(root, old_id), old)

    def test_source_switch_keeps_old_snapshot_and_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_id = publish_snapshot(root, fixture())
            old = read_snapshot(root, old_id)
            replacement = replace(
                fixture(), source_id="second-synthetic-source",
                source_version="fixture-v2",
                source_policy_version="synthetic-policy-v2",
                batch_id="synthetic-batch-2",
                market_contract=replace(
                    fixture().market_contract,
                    raw_publisher="second synthetic publisher",
                    transport_id="second synthetic transport"),
                raw_response=b'{"second_fixture":true}',
            )
            new_id = publish_snapshot(root, replacement)
            self.assertNotEqual(old_id, new_id)
            self.assertEqual(read_snapshot(root)["snapshot_id"], new_id)
            self.assertEqual(read_snapshot(root, old_id), old)
            self.assertEqual(read_pdf(root, old_id, old["pdf_object_id"]),
                             fixture().pdf_bytes)
            self.assertEqual(read_snapshot(root, new_id)["batch_id"],
                             "synthetic-batch-2")

    def test_publish_repeat_revision_and_fixed_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = publish_snapshot(root, fixture())
            self.assertEqual(first, publish_snapshot(root, fixture()))
            old = read_snapshot(root, first)
            self.assertEqual(old["unknown_missing_dates"], ["2026-09-22"])
            self.assertEqual(old["pit_grade"], "latest_only")
            self.assertEqual(old["document_public_available_at"],
                             "2026-09-22T16:00:00+00:00")
            self.assertEqual(read_pdf(root, first, old["pdf_object_id"]),
                             fixture().pdf_bytes)
            revision = replace(fixture(), bars=(replace(fixture().bars[0],
                                                       close_cny="10.60"),))
            second = publish_snapshot(root, revision)
            self.assertNotEqual(first, second)
            self.assertEqual(read_snapshot(root)["bars"][0]["close_cny"], "10.60")
            self.assertEqual(read_snapshot(root, first)["bars"][0]["close_cny"], "10.50")
            with self.assertRaises(SnapshotError):
                read_pdf(root, first, read_snapshot(root, second)["pdf_object_id"] + "x")

    def test_invalid_input_never_replaces_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = publish_snapshot(root, fixture())
            invalid = replace(fixture(), bars=(replace(fixture().bars[0],
                                                      low_cny="11.50"),))
            with self.assertRaisesRegex(SnapshotError, "OHLC"):
                publish_snapshot(root, invalid)
            with self.assertRaisesRegex(SnapshotError, "decimal"):
                publish_snapshot(root, replace(fixture(), bars=(replace(
                    fixture().bars[0], amount_cny="NaN"),)))
            with self.assertRaisesRegex(SnapshotError, "complete-through"):
                publish_snapshot(root, replace(fixture(), complete_through_date="2026-09-21"))
            self.assertEqual(read_snapshot(root)["snapshot_id"], first)

    def test_missing_and_corrupt_objects_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_id = publish_snapshot(root, fixture())
            object_id = read_snapshot(root)["pdf_object_id"]
            (root / "objects" / object_id).write_bytes(b"corrupt")
            with self.assertRaisesRegex(SnapshotError, "hash mismatch"):
                read_snapshot(root, snapshot_id)

    def test_corrupt_verification_original_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_id = publish_snapshot(root, fixture())
            object_id = read_snapshot(root)["verification_object_id"]
            (root / "objects" / object_id).write_bytes(b"corrupt comparison")
            with self.assertRaisesRegex(SnapshotError, "hash mismatch"):
                read_snapshot(root, snapshot_id)

    def test_symlinked_object_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, \
                tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / "objects").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(SnapshotError, "symlink"):
                publish_snapshot(root, fixture())

    def test_no_snapshot_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(read_snapshot(Path(directory)))

    def test_process_death_at_publish_boundaries(self):
        helper = """
import os, sys
from dataclasses import replace
from pathlib import Path
from pmi.snapshot import publish_snapshot
from test_snapshot import fixture
payload = replace(fixture(), bars=(replace(fixture().bars[0], close_cny="10.60"),))
def die_at_stage(stage):
    if stage == sys.argv[2]:
        os._exit(17)
publish_snapshot(Path(sys.argv[1]), payload, checkpoint=die_at_stage)
"""
        for stage in ("raw_written", "objects_ready", "manifest_uncommitted",
                      "committed"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                old_id = publish_snapshot(root, fixture())
                environment = os.environ.copy()
                environment["PYTHONPATH"] = os.pathsep.join(
                    [str(Path(__file__).resolve().parents[1] / "src"),
                     str(Path(__file__).resolve().parent)])
                result = subprocess.run([sys.executable, "-c", helper, directory, stage],
                                        env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 17, result.stderr)
                current = read_snapshot(root)
                expected = "10.60" if stage == "committed" else "10.50"
                self.assertEqual(current["bars"][0]["close_cny"], expected)
                self.assertEqual(read_snapshot(root, old_id)["bars"][0]["close_cny"],
                                 "10.50")
                revision = replace(fixture(), bars=(replace(fixture().bars[0],
                                                           close_cny="10.60"),))
                new_id = publish_snapshot(root, revision)
                self.assertEqual(read_snapshot(root)["snapshot_id"], new_id)
                self.assertEqual(new_id, publish_snapshot(root, revision))

    def test_write_failure_and_isolated_restore(self):
        with tempfile.TemporaryDirectory() as directory, \
                tempfile.TemporaryDirectory() as restored_directory:
            root = Path(directory)
            snapshot_id = publish_snapshot(root, fixture())

            def no_space(stage: str) -> None:
                if stage == "raw_written":
                    raise OSError("simulated disk full")

            revision = replace(fixture(), raw_response=b'{"fixture":"revised"}')
            with self.assertRaisesRegex(OSError, "disk full"):
                publish_snapshot(root, revision, checkpoint=no_space)
            self.assertEqual(read_snapshot(root)["snapshot_id"], snapshot_id)

            restored = Path(restored_directory) / "restored-slice"
            shutil.copytree(root, restored)
            record = read_snapshot(restored, snapshot_id)
            self.assertEqual(record["bars"], read_snapshot(root, snapshot_id)["bars"])
            self.assertEqual(read_pdf(restored, snapshot_id, record["pdf_object_id"]),
                             fixture().pdf_bytes)


if __name__ == "__main__":
    unittest.main()
