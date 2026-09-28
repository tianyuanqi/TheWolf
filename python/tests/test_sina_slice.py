import unittest
import json
import hashlib
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from pmi.sina_slice import SINA_URL, _calendar_dates, _daily_bars, _fetch_original
from pmi.snapshot import SnapshotError


class SinaSliceTests(unittest.TestCase):
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
