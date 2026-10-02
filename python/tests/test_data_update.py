"""以可重建合成来源验证完整窗口、时间继承、任务恢复和并发。"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from pmi import data_update as u
from pmi.sina_slice import _calendar_dates, _decode_sina, _fetch_original, main
from pmi.snapshot import DailyBar, SnapshotError, publish_snapshot, read_snapshot
from pmi.trading_calendar import complete_window
from pmi.writer_lock import writer_lock
from test_snapshot import fixture


FORECAST = b"%PDF-1.4\nsynthetic forecast"
REPORT = b"%PDF-1.4\nsynthetic full report"
FORECAST_HASH = hashlib.sha256(FORECAST).hexdigest()
REPORT_HASH = hashlib.sha256(REPORT).hexdigest()
NOW = datetime.fromisoformat("2026-10-02T20:00:00+08:00")
NEW_DAYS = complete_window(NOW)
RAW = b'var KLC_K2_sz002245="AAA=";'


def sources(days=NEW_DAYS, revised=False):
    """生成与实际来源形状一致的合成输入；数值预期独立明确。"""
    decoded = [{"date": day + "T00:00:00.000Z", "open": 10.0, "high": 11.0, "low": 9.0,
                "close": 10.6 if revised and day == "2026-09-24" else 10.5,
                "volume": 12345, "amount": 123456} for day in days]
    records = [[day, "10.00", "10.60" if revised and day == "2026-09-24" else "10.50",
                "9.00", "11.00", "0", "0", 123, "123456.00"] for day in days]
    raw = json.dumps({"code": "0", "data": {"code": "002245", "name": "蔚蓝锂芯", "picupdata": records}}).encode()
    return decoded, raw


def old_snapshot(root):
    """建立旧固定窗口及未知逐原件时间的两份公告，不读真实库。"""
    old = fixture()
    days = _calendar_dates()
    payload = replace(old, calendar_dates=days, complete_through_date=days[-1],
                      source_id="sina-finance-a-share-daily",
                      market_contract=replace(old.market_contract, source_url=u.SINA_URL,
                                              verification_source_url=u.SZSE_URL, source_symbol="sz002245",
                                              raw_volume_unit="share", raw_amount_unit="CNY"),
                      retrieved_at="2026-09-24T01:00:00+00:00",
                      bars=tuple(DailyBar(day, "10.00", "11.00", "9.00", "10.50", "12345", "123456") for day in days),
                      document=replace(old.document, published_at=None, publication_precision="unknown"),
                      pdf_bytes=FORECAST, additional_pdf_bytes=(REPORT,),
                      additional_documents=(replace(old.document, document_id="report"),))
    return publish_snapshot(root, payload)


def run_update(root, revised=False, checkpoint=None, official_override=None, raw=RAW):
    """用真实标准化与发布路径处理合成来源，仅替代网络和 KLC 解码。"""
    decoded, official = sources(revised=revised)
    state = {"job_id": "synthetic-job", "stage": "preparing", "last_success_at": None}
    with patch.object(u, "PDF_SHA256", FORECAST_HASH), patch.object(u, "FORMAL_PDF_SHA256", REPORT_HASH), \
            patch("pmi.sina_slice.MiniRacer") as decoder, writer_lock(root):
        decoder.return_value.call.return_value = decoded
        def fetch(url, *args, **kwargs):
            return raw if url == u.SINA_URL else (official_override or official)
        return u._perform_update(root, state, fetch, NOW, checkpoint)


class DataUpdateTests(unittest.TestCase):
    def test_calendar_uses_notices_excludes_today_and_refuses_unknown_year(self):
        self.assertEqual((NEW_DAYS[0], NEW_DAYS[-1], len(NEW_DAYS)), ("2026-07-08", "2026-09-30", 60))
        for clock, last_day in (("2026-09-25T23:00:00+08:00", "2026-09-24"),
                                ("2026-09-27T12:00:00+08:00", "2026-09-24"),
                                ("2026-09-28T16:00:00+08:00", "2026-09-24"),
                                ("2026-09-30T01:00:00+00:00", "2026-09-29"),
                                ("2026-10-10T20:00:00+08:00", "2026-10-09")):
            days = complete_window(datetime.fromisoformat(clock))
            self.assertEqual(days[-1], last_day)
            self.assertNotIn("2026-09-25", days)
            self.assertNotIn("2026-10-01", days)
        for clock in ("2027-01-04T12:00:00+08:00", "2026-01-04T12:00:00+08:00"):
            with self.assertRaisesRegex(SnapshotError, "calendar_uncovered"):
                complete_window(datetime.fromisoformat(clock))
        with self.assertRaises(SnapshotError):
            complete_window(datetime(2026, 10, 2))

    def test_new_window_revision_old_fixed_views_and_unknown_announcement_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old_id = old_snapshot(root); old = read_snapshot(root, old_id)
            result = run_update(root, revised=True)
            self.assertEqual((result["stage"], result["result"]), ("completed", "business_changed"))
            self.assertEqual(result["added_dates"], ["2026-09-28", "2026-09-29", "2026-09-30"])
            self.assertEqual(result["removed_dates"], ["2026-07-03", "2026-07-06", "2026-07-07"])
            self.assertEqual(result["revised_dates"], ["2026-09-24"])
            new = read_snapshot(root)
            self.assertEqual((new["open_session_count"], new["observed_count"]), (60, 60))
            self.assertEqual(new["documents"][0]["public_available_at"], old["documents"][0]["public_available_at"])
            self.assertNotIn("original_retrieved_at", new["documents"][0])
            self.assertIn("unknown", new["documents"][0]["original_retrieval_basis"])
            self.assertEqual(read_snapshot(root, old_id), old)

    def test_unchanged_new_observation_and_evidence_only_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old_snapshot(root)
            first = run_update(root); fixed = read_snapshot(root)
            second = run_update(root)
            self.assertEqual(second["result"], "unchanged")
            self.assertEqual(second["snapshot_id"], first["snapshot_id"])
            self.assertGreater(second["last_success_at"], first["last_success_at"])
            third = run_update(root, raw=RAW + b"\n// synthetic outside-window change")
            self.assertEqual(third["result"], "evidence_changed")
            self.assertNotEqual(third["snapshot_id"], second["snapshot_id"])
            self.assertEqual(third["added_dates"], [])
            self.assertEqual(read_snapshot(root, fixed["snapshot_id"]), fixed)

    def test_failed_background_check_preserves_last_success_and_saved_window(self):
        import requests
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old_snapshot(root)
            success = run_update(root)
            saved = read_snapshot(root)
            perform = u._perform_update
            def fail_fetch(*args, **kwargs):
                raise requests.ConnectionError("synthetic isolated failure")
            def isolated_worker(root, state):
                return perform(root, state, fetch=fail_fetch, now=NOW)
            with patch.object(u, "PDF_SHA256", FORECAST_HASH), patch.object(u, "FORMAL_PDF_SHA256", REPORT_HASH), \
                    patch.object(u, "_perform_update", side_effect=isolated_worker):
                job = u.start_update(root)
                for _ in range(100):
                    state = u.update_status(root)
                    if state["stage"] == "failed": break
                    time.sleep(.01)
                self.assertEqual(state["stage"], "failed")
                self.assertEqual(state["job_id"], job["job_id"])
                self.assertEqual(state["last_success_at"], success["last_success_at"])
                self.assertEqual(read_snapshot(root), saved)

    def test_sources_missing_duplicate_conflict_do_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old_id = old_snapshot(root)
            _, raw = sources(); official = json.loads(raw)
            cases = []
            missing = json.loads(raw); missing["data"]["picupdata"].pop(); cases.append(missing)
            duplicate = json.loads(raw); duplicate["data"]["picupdata"].append(duplicate["data"]["picupdata"][0]); cases.append(duplicate)
            conflict = json.loads(raw); conflict["data"]["picupdata"][0][8] = "123457"; cases.append(conflict)
            for invalid_value in (None, "NaN", "malformed"):
                malformed = json.loads(raw); malformed["data"]["picupdata"][0][8] = invalid_value; cases.append(malformed)
            for source in cases:
                result = run_update(root, official_override=json.dumps(source).encode())
                self.assertEqual(result["stage"], "failed")
                self.assertEqual(read_snapshot(root)["snapshot_id"], old_id)
            decoded, _ = sources()
            for invalid in (decoded[:-1], decoded + [decoded[0]]):
                with patch("pmi.sina_slice.MiniRacer") as decoder:
                    decoder.return_value.call.return_value = invalid
                    with self.assertRaises(SnapshotError):
                        _decode_sina(RAW, NEW_DAYS)

    def test_stale_window_empty_or_corrupt_announcements_never_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old_snapshot(root)
            current = read_snapshot(root)
            with patch.object(u, "complete_window", return_value=("2026-09-23",)):
                result = u._perform_update(root, {"job_id": "stale", "stage": "preparing"}, fetch=lambda *a, **k: self.fail("must not fetch"), now=NOW)
            self.assertIn("stale_window", result["message"])
            self.assertEqual(read_snapshot(root)["snapshot_id"], current["snapshot_id"])
            (root / "objects" / FORECAST_HASH).write_bytes(b"corrupt")
            result = u._perform_update(root, {"job_id": "bad-pdf", "stage": "preparing"}, fetch=lambda *a, **k: self.fail("must not fetch"), now=NOW)
            self.assertEqual(result["stage"], "failed")
        with tempfile.TemporaryDirectory() as directory:
            result = u._perform_update(Path(directory), {"job_id": "empty", "stage": "preparing"}, fetch=lambda *a, **k: self.fail("must not fetch"), now=NOW)
            self.assertIn("slice_empty", result["message"])

    def test_cross_process_lock_and_background_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old_snapshot(root)
            with writer_lock(root):
                with patch.object(sys, "argv", ["sina_slice", "--data-root", directory]), patch("pmi.sina_slice._fetch_original") as fetch:
                    with self.assertRaisesRegex(SnapshotError, "writer_busy"):
                        main()
                    fetch.assert_not_called()
                code = "from pathlib import Path; from pmi.writer_lock import writer_lock;\nwith writer_lock(Path(__import__('sys').argv[1])): pass"
                result = subprocess.run([sys.executable, "-c", code, directory], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"writer_busy", result.stderr)
                with self.assertRaisesRegex(SnapshotError, "writer_busy"):
                    u.start_update(root)
            entered = threading.Event(); release = threading.Event()
            def slow_worker(root, state):
                entered.set(); release.wait(3)
                state.update(stage="failed", result="synthetic", message="synthetic")
                u._save_status(root, state)
            with patch.object(u, "_perform_update", side_effect=slow_worker):
                first = u.start_update(root); self.assertTrue(entered.wait(2))
                self.assertEqual(u.start_update(root)["job_id"], first["job_id"])
                self.assertEqual(u.update_status(root)["job_id"], first["job_id"])
                release.set()
                for _ in range(50):
                    if u.update_status(root)["stage"] == "failed": break
                    time.sleep(.01)
                self.assertEqual(u.update_status(root)["stage"], "failed")

    def test_fetch_read_budget_and_decoder_failure_are_explicit(self):
        from py_mini_racer import JSEvalException
        with patch("pmi.sina_slice.MiniRacer") as decoder:
            decoder.return_value.call.side_effect = JSEvalException("synthetic malformed decoder input")
            with self.assertRaisesRegex(SnapshotError, "decode failed"):
                _decode_sina(RAW, NEW_DAYS)
            decoder.return_value.close.assert_called_once()
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def iter_content(self, chunk_size): yield b"slow"
        with patch("pmi.sina_slice.requests.get", return_value=Response()) as get, \
                patch("pmi.sina_slice.time.monotonic", side_effect=[0, 31]):
            with self.assertRaisesRegex(SnapshotError, "deadline exceeded"):
                _fetch_original(u.SINA_URL)
            self.assertEqual(get.call_count, 1)

    def test_fetch_subprocess_receipt_and_parent_exit_without_network(self):
        real_popen = subprocess.Popen
        code = "import pmi.source_fetch as s; s._fetch_original=lambda *a: b'synthetic original'; s.main()"
        def fake_source(command, **kwargs):
            return real_popen([sys.executable, "-c", code, *command[3:]], **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(u.subprocess, "Popen", side_effect=fake_source):
            root = Path(directory)
            self.assertEqual(u._fetch_bounded(u.SINA_URL, receipt_root=root), b"synthetic original")
            receipt = json.loads((root / "original-observations.jsonl").read_text())
            self.assertEqual(receipt["sha256"], hashlib.sha256(b"synthetic original").hexdigest())
            self.assertIn("completed_at", receipt)
        with tempfile.TemporaryDirectory() as directory:
            code = "import time; import pmi.source_fetch as s; s._fetch_original=lambda *a: time.sleep(60); s.main()"
            process = real_popen([sys.executable, "-c", code, "--source", "sina", "--output", directory], stdin=subprocess.PIPE)
            process.stdin.close()
            self.assertNotEqual(process.wait(timeout=5), 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_fetch_hard_deadline_terminates_and_does_not_record_receipt(self):
        process = unittest.mock.Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 45), None]
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, patch.object(u.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(SnapshotError, "45 seconds"):
                u._fetch_bounded(u.SINA_URL, receipt_root=Path(directory))
            process.terminate.assert_called_once()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_process_death_and_restart_checks_commit_without_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            for stage in ("raw_written", "objects_ready", "manifest_uncommitted", "committed"):
                root = Path(directory) / stage; old_id = old_snapshot(root)
                code = "from pathlib import Path; import sys,os; from test_data_update import run_update; run_update(Path(sys.argv[1]),checkpoint=lambda s: os._exit(17) if s==sys.argv[2] else None)"
                result = subprocess.run([sys.executable, "-c", code, str(root), stage])
                self.assertEqual(result.returncode, 17)
                state = u.update_status(root)
                if stage == "committed":
                    self.assertEqual(state["stage"], "completed")
                    self.assertNotEqual(state["snapshot_id"], old_id)
                else:
                    self.assertEqual(state["stage"], "interrupted")
                    self.assertEqual(read_snapshot(root)["snapshot_id"], old_id)
                retry = run_update(root)
                self.assertEqual(retry["stage"], "completed")
                self.assertIsNotNone(read_snapshot(root, old_id))


if __name__ == "__main__":
    unittest.main()
