import unittest
import json
import hashlib
import sqlite3
import tempfile
import sys
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pmi.sina_slice import (FORMAL_PDF_URL, PDF_URL, SINA_URL, SZSE_URL,
                            _calendar_dates, _daily_bars, _fetch_original, main)
from pmi.snapshot import DailyBar, SnapshotError, read_snapshot


class SinaSliceTests(unittest.TestCase):
    def test_cli_reobserves_old_content_without_rewinding_on_retry(self):
        """经真实适配器批次规则与 CLI 导入验证内容恢复和旧观察重试。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_root = root / "data"
            originals = [root / name for name in
                         ("sina.raw", "official.raw", "forecast.pdf", "report.pdf")]
            originals[1].write_bytes(b"synthetic official")
            originals[2].write_bytes(b"%PDF-1.4\nforecast")
            originals[3].write_bytes(b"%PDF-1.4\nreport")
            forecast_hash = hashlib.sha256(originals[2].read_bytes()).hexdigest()
            report_hash = hashlib.sha256(originals[3].read_bytes()).hexdigest()
            day = _calendar_dates()[0]

            def bars_for_raw(raw, _official):
                close = "10.50" if raw == b"source A" else "10.60"
                return (DailyBar(day, "10.00", "11.00", "9.00", close,
                                 "100", "1050.00"),)

            def run_replay(raw, retrieved_at):
                originals[0].write_bytes(raw)
                argv = ["sina_slice", "--data-root", str(data_root),
                        "--sina-raw", str(originals[0]),
                        "--official-raw", str(originals[1]),
                        "--pdf", str(originals[2]),
                        "--formal-pdf", str(originals[3]),
                        "--retrieved-at", retrieved_at]
                with patch.object(sys, "argv", argv), redirect_stdout(StringIO()) as output:
                    main()
                return json.loads(output.getvalue())["snapshot_id"]

            def run_live(raw, retrieved_at):
                """模拟四份来源响应，保留真实 CLI 获取与逐原件日志路径。"""
                contents = {SINA_URL: raw, SZSE_URL: originals[1].read_bytes(),
                            PDF_URL: originals[2].read_bytes(),
                            FORMAL_PDF_URL: originals[3].read_bytes()}

                class Response:
                    status_code = 200

                    def __init__(self, content):
                        self.content = content

                    def __enter__(self):
                        return self

                    def __exit__(self, *_):
                        return False

                    def iter_content(self, chunk_size):
                        yield self.content

                argv = ["sina_slice", "--data-root", str(data_root)]
                with patch.object(sys, "argv", argv), \
                        patch("pmi.sina_slice.requests.get",
                              side_effect=lambda url, **_: Response(contents[url])), \
                        patch("pmi.sina_slice.datetime") as clock, \
                        redirect_stdout(StringIO()) as output:
                    clock.now.return_value = datetime.fromisoformat(retrieved_at)
                    main()
                return json.loads(output.getvalue())["snapshot_id"]

            with patch("pmi.sina_slice.PDF_SHA256", forecast_hash), \
                    patch("pmi.sina_slice.FORMAL_PDF_SHA256", report_hash), \
                    patch("pmi.sina_slice._decode_sina", side_effect=lambda raw: raw), \
                    patch("pmi.sina_slice._official_rows",
                          return_value=("合成公司", {})), \
                    patch("pmi.sina_slice._daily_bars", side_effect=bars_for_raw):
                t1 = "2026-09-25T01:00:00+00:00"
                t2 = "2026-09-26T01:00:00+00:00"
                t3 = "2026-09-27T01:00:00+00:00"
                a_id = run_live(b"source A", t1)
                b_id = run_live(b"source B", t2)
                self.assertEqual(run_replay(b"source A", t1), a_id)
                self.assertEqual(read_snapshot(data_root)["snapshot_id"], b_id)
                self.assertEqual(run_live(b"source A", t3), a_id)
                self.assertEqual(read_snapshot(data_root)["snapshot_id"], a_id)
                self.assertEqual(run_replay(b"source B", t2), b_id)
                self.assertEqual(read_snapshot(data_root)["snapshot_id"], a_id)
                self.assertEqual(run_replay(b"source A", t3), a_id)
                fixed_a = read_snapshot(data_root, a_id)
                self.assertEqual(fixed_a["bars"][0]["close_cny"], "10.50")
                self.assertEqual(fixed_a["first_seen_at"], t1)
                self.assertEqual(read_snapshot(data_root, b_id)["bars"][0]["close_cny"],
                                 "10.60")
                self.assertEqual(read_snapshot(data_root, a_id)["batch_id"],
                                 fixed_a["batch_id"])
                with sqlite3.connect(data_root / "slice.sqlite") as connection:
                    self.assertEqual(connection.execute(
                        "SELECT COUNT(*) FROM snapshots").fetchone()[0], 2)
                    observations = connection.execute(
                        "SELECT snapshot_id, observed_at FROM snapshot_observations "
                        "ORDER BY observed_at").fetchall()
                    self.assertEqual(observations, [(a_id, t1), (b_id, t2),
                                                    (a_id, t3)])
                    current_observation = connection.execute(
                        "SELECT o.snapshot_id, o.observed_at FROM current_observation c "
                        "JOIN snapshot_observations o ON o.observation_id=c.observation_id"
                    ).fetchone()
                    self.assertEqual(current_observation, (a_id, t3))
                receipts = (data_root / "original-observations.jsonl").read_text().splitlines()
                self.assertEqual(len(receipts), 12)

    def test_each_completed_download_records_own_observation(self):
        class Response:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def iter_content(self, chunk_size):
                yield b"synthetic-source-bytes"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("pmi.sina_slice.requests.get", return_value=Response()):
                self.assertEqual(_fetch_original(SINA_URL, receipt_root=root),
                                 b"synthetic-source-bytes")
            records = [json.loads(line) for line in
                       (root / "original-observations.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["source_url"], SINA_URL)
            self.assertEqual(records[0]["sha256"],
                             hashlib.sha256(b"synthetic-source-bytes").hexdigest())
            self.assertIn("completed_at", records[0])

    def test_download_rejects_other_hosts_redirects_and_oversize(self):
        with self.assertRaisesRegex(SnapshotError, "unapproved"):
            _fetch_original("http://127.0.0.1/private")

        class Response:
            status_code = 302

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def iter_content(self, chunk_size):
                yield b"a" * 1_000_001

        response = Response()
        with patch("pmi.sina_slice.requests.get", return_value=response) as get:
            with self.assertRaisesRegex(SnapshotError, "HTTP status 302"):
                _fetch_original(SINA_URL)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
            response.status_code = 200
            with self.assertRaisesRegex(SnapshotError, "exceeds one megabyte"):
                _fetch_original(SINA_URL)

    def test_share_and_yuan_values_match_official_hand_resolution(self):
        dates = _calendar_dates()
        sina = {day: {"open": 10.00, "high": 11.00, "low": 9.00,
                      "close": 10.50, "volume": 12345, "amount": 123456}
                for day in dates}
        official = {day: [day, "10.00", "10.50", "9.00", "11.00",
                          "0", "0", 123, "123456.00"] for day in dates}

        bars = _daily_bars(sina, official)
        self.assertEqual(len(bars), 60)
        self.assertEqual(bars[0].volume_shares, "12345")
        self.assertEqual(bars[0].amount_cny, "123456")
        self.assertEqual(bars[0].open_cny, "10.00")

        wrong_amount = deepcopy(official)
        wrong_amount[dates[0]][8] = "123457.00"
        with self.assertRaisesRegex(SnapshotError, "amount differs"):
            _daily_bars(sina, wrong_amount)

        wrong_volume = deepcopy(sina)
        wrong_volume[dates[0]]["volume"] = 12351
        with self.assertRaisesRegex(SnapshotError, "volume differs"):
            _daily_bars(wrong_volume, official)

        wrong_price = deepcopy(sina)
        wrong_price[dates[0]]["open"] = 10.001
        with self.assertRaisesRegex(SnapshotError, "cent resolution"):
            _daily_bars(wrong_price, official)


if __name__ == "__main__":
    unittest.main()
