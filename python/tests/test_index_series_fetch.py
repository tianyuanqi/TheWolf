"""受控传输反例：全为内存响应或无网络子进程，不请求金融来源。"""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import requests

from pmi.market_data import SnapshotError
from pmi.market_data.index_catalog import INDICES
from pmi.market_data import index_series_fetch as fetch
from pmi.market_data.index_series_contract import canonical
from pmi.market_data.index_series_store import append_record, load_json
from pmi.market_data.writer_lock import writer_lock
from test_index_series_contract import WINDOW


class Raw(io.BytesIO):
    def read(self, size=-1, decode_content=False):
        assert decode_content is False
        return super().read(size)


class Response:
    def __init__(self, content=b"synthetic", status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.raw = Raw(content)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.raw.close()


class Process:
    def __init__(self, *, stuck=False):
        self.stdin = io.BytesIO()
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.stuck = stuck
        self.waits = []
    def poll(self):
        return self.returncode
    def wait(self, timeout):
        self.waits.append(timeout)
        if self.killed or self.terminated and not self.stuck:
            self.returncode = -9 if self.killed else -15
            return self.returncode
        time.sleep(min(timeout, .01))
        raise subprocess.TimeoutExpired("synthetic", timeout)
    def terminate(self):
        self.terminated = True
    def kill(self):
        self.killed = True


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wolf-series-fetch-test-")
        self.root = Path(self.temporary.name).resolve()
        self.index = INDICES[0]
        self.stop = threading.Event()

    def tearDown(self):
        self.temporary.cleanup()

    def reserve(self, source=None, index=None, budget=None):
        index = index or self.index
        return fetch.reserve(self.root, index, source or index.sources[0], WINDOW, "job", budget or fetch.NetworkBudget(), self.stop)

    def test_fsync_reservation_survives_restart_and_budget_change_keeps_prior_charges(self):
        with writer_lock(self.root):
            first = self.reserve(budget=fetch.NetworkBudget(1, fetch.MAX_RESPONSE_BYTES))
            with self.assertRaisesRegex(SnapshotError, "network_budget_exhausted"):
                self.reserve(index=INDICES[3], budget=fetch.NetworkBudget(1, fetch.MAX_RESPONSE_BYTES))
            second = self.reserve(index=INDICES[3], budget=fetch.NetworkBudget(3, 2 * fetch.MAX_RESPONSE_BYTES))
            with self.assertRaisesRegex(SnapshotError, "network_budget_exhausted"):
                self.reserve(source="eastmoney", budget=fetch.NetworkBudget(3, 2 * fetch.MAX_RESPONSE_BYTES))
        entries = fetch._entries(self.root)
        self.assertEqual(len(entries), 2)
        self.assertNotEqual(first["index_id"], second["index_id"])
        self.assertEqual(sum(item["reserved_bytes"] for item in entries), 2 * fetch.MAX_RESPONSE_BYTES)

    def test_success_refunds_only_complete_body_failed_reserves_full(self):
        with writer_lock(self.root):
            entry = self.reserve()
            append_record(self.root / "index-v2-network-ledger.jsonl", {
                "event": "finished", "attempt_id": entry["attempt_id"], "index_id": self.index.index_id,
                "job_id": "job", "source": entry["source"], "success": True, "charged_bytes": 10, "finished_at": fetch._now()})
            self.reserve(index=INDICES[3], budget=fetch.NetworkBudget(2, fetch.MAX_RESPONSE_BYTES + 10))
        attempts, settled = fetch._totals(fetch._entries(self.root))
        self.assertEqual(sum(settled.get(key, fetch.MAX_RESPONSE_BYTES) for key in attempts), fetch.MAX_RESPONSE_BYTES + 10)

    def test_same_host_cooldown_cancel_does_not_reserve_second_request(self):
        with writer_lock(self.root):
            self.reserve()
            self.stop.set()
            with self.assertRaises(fetch.FetchInterrupted):
                self.reserve(index=INDICES[1])
        self.assertEqual(len(fetch._entries(self.root)), 1)

    def test_environment_cannot_redirect_ledger_or_expand_budget(self):
        redirected = self.root / "unapproved-ledger"
        with writer_lock(self.root), patch.dict(os.environ, {"WOLF_INDEX_BUDGET_LEDGER": str(redirected), "WOLF_INDEX_MAX_ATTEMPTS": "999999"}):
            self.reserve(budget=fetch.NetworkBudget(1, fetch.MAX_RESPONSE_BYTES))
            with self.assertRaisesRegex(SnapshotError, "network_budget_exhausted"):
                self.reserve(index=INDICES[3], budget=fetch.NetworkBudget(1, fetch.MAX_RESPONSE_BYTES))
        self.assertFalse(redirected.exists())
        self.assertEqual(len(fetch._entries(self.root)), 1)

    def test_invalid_ledger_and_symlink_fail_before_popen(self):
        path = self.root / "index-v2-network-ledger.jsonl"
        path.write_bytes(b'{"event":"attempt"}')
        with writer_lock(self.root), patch.object(fetch.subprocess, "Popen") as process, self.assertRaisesRegex(SnapshotError, "incomplete_network_ledger"):
            fetch.fetch_bounded(self.root, self.index, "csindex", WINDOW, "job", budget=fetch.NetworkBudget())
        process.assert_not_called()
        path.unlink()
        target = self.root / "target"
        target.write_text("synthetic")
        path.symlink_to(target)
        with writer_lock(self.root), self.assertRaises(ValueError):
            self.reserve()
        self.assertEqual(target.read_text(), "synthetic")

    def test_request_parameters_and_body_receipt(self):
        output = self.root / "output"
        output.mkdir()
        response = Response(b"{}", headers={"Content-Length": "2"})
        with patch.object(requests, "get", return_value=response) as request:
            fetch.fetch_once("https://www.csindex.com.cn/controlled", output)
        options = request.call_args.kwargs
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(options["timeout"], (5, 15))
        self.assertEqual(options["headers"]["Accept-Encoding"], "identity")
        self.assertNotIn("verify", options)
        self.assertNotIn("proxies", options)
        self.assertEqual((output / "original").read_bytes(), b"{}")
        self.assertEqual(load_json((output / "receipt.json").read_bytes())["bytes"], 2)

    def test_redirect_encoding_length_and_truncated_body_are_rejected(self):
        cases = [Response(status=302), Response(headers={"Content-Encoding": "gzip"}),
                 Response(headers={"Content-Length": str(fetch.MAX_RESPONSE_BYTES + 1)}),
                 Response(b"short", headers={"Content-Length": "100"}),
                 Response(headers={"Content-Length": "-1"})]
        for position, response in enumerate(cases):
            output = self.root / str(position)
            output.mkdir()
            with patch.object(requests, "get", return_value=response), self.assertRaises(SnapshotError):
                fetch.fetch_once("https://www.csindex.com.cn/controlled", output)
            self.assertFalse((output / "receipt.json").exists())

    def test_stream_hard_limit_never_accepts_unknown_full_length(self):
        for length in (None, str(fetch.MAX_RESPONSE_BYTES)):
            output = self.root / ("unknown" if length is None else "known")
            output.mkdir()
            response = Response(b"a" * fetch.MAX_RESPONSE_BYTES, headers={} if length is None else {"Content-Length": length})
            with patch.object(requests, "get", return_value=response):
                if length is None:
                    with self.assertRaisesRegex(SnapshotError, "source_body_limit"):
                        fetch.fetch_once("https://www.csindex.com.cn/controlled", output)
                else:
                    fetch.fetch_once("https://www.csindex.com.cn/controlled", output)
            self.assertEqual((output / "original").stat().st_size, fetch.MAX_RESPONSE_BYTES)

    def test_hard_deadline_terminates_kills_waits_and_charges_full(self):
        process = Process(stuck=True)
        with writer_lock(self.root), patch.object(fetch.subprocess, "Popen", return_value=process), patch.object(fetch, "DEADLINE_SECONDS", .02):
            with self.assertRaisesRegex(SnapshotError, "source_deadline_exceeded"):
                fetch.fetch_bounded(self.root, self.index, "csindex", WINDOW, "job", budget=fetch.NetworkBudget())
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertTrue(process.stdin.closed)
        self.assertEqual(fetch._entries(self.root)[-1]["charged_bytes"], fetch.MAX_RESPONSE_BYTES)
        self.assertFalse(fetch._entries(self.root)[-1]["success"])

    def test_popen_failure_charges_full_and_does_not_retry(self):
        with writer_lock(self.root), patch.object(fetch.subprocess, "Popen", side_effect=OSError("secret proxy string")) as popen:
            with self.assertRaises(OSError):
                fetch.fetch_bounded(self.root, self.index, "csindex", WINDOW, "job", budget=fetch.NetworkBudget())
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(fetch._entries(self.root)[-1]["charged_bytes"], fetch.MAX_RESPONSE_BYTES)
        self.assertNotIn("secret proxy", (self.root / "index-v2-network-ledger.jsonl").read_text())

    def test_parent_eof_reaps_real_non_network_child(self):
        process = subprocess.Popen([sys.executable, "-B", "-c",
            "import threading,time; from pmi.market_data.index_series_fetch import _watch_parent; threading.Thread(target=_watch_parent,daemon=True).start(); time.sleep(30)"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), -15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)

    def test_successful_mock_child_checks_complete_receipt_and_settles_actual(self):
        process = Process()
        process.returncode = 0
        def popen(command, **kwargs):
            output = Path(command[-1])
            (output / "original").write_bytes(b"synthetic")
            (output / "receipt.json").write_bytes(canonical({"bytes": 9, "complete": True, "completed_at": fetch._now()}))
            return process
        with writer_lock(self.root), patch.object(fetch.subprocess, "Popen", side_effect=popen):
            original = fetch.fetch_bounded(self.root, self.index, "csindex", WINDOW, "job", budget=fetch.NetworkBudget())
        self.assertEqual(original.content, b"synthetic")
        self.assertEqual(fetch._entries(self.root)[-1]["charged_bytes"], 9)
        self.assertTrue(fetch._entries(self.root)[-1]["success"])


if __name__ == "__main__":
    unittest.main()
