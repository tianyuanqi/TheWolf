"""指数活动归属及旧协议交接回归，仅使用独占合成目录。"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmi.market_data import ReadUnavailable
from pmi.market_data.index_activity import activity, is_active
from pmi.market_data.writer_lock import writer_lock


class IndexActivityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.index_root = self.root / "indices/csi000300"
        self.index_root.mkdir(parents=True)
        self.state_path = self.index_root / "update-status.json"
        self.state = {"stage": "preparing", "job_id": "a" * 32}
        self.state_path.write_text(json.dumps(self.state))


    def test_index_job_and_protocol_are_separate(self):
        with activity(self.index_root, "csi:000300:price", "job"):
            self.assertTrue(is_active(self.index_root, "csi:000300:price", "job"))
            self.assertFalse(is_active(self.index_root, "csi:000852:price", "job"))
            self.assertFalse(is_active(self.index_root, "csi:000300:price", "other"))
        self.assertFalse(is_active(self.index_root, "csi:000300:price", "job"))


    def test_activity_symlink_does_not_touch_target(self):
        target = self.root / "kept"
        target.write_bytes(b"keep")
        (self.index_root / ".index-v2-activity.lock").symlink_to(target)
        with self.assertRaises(ReadUnavailable):
            with activity(self.index_root, "csi:000300:price", "job"):
                self.fail("unsafe activity entered")
        self.assertFalse(is_active(self.index_root, "csi:000300:price", "job"))
        self.assertEqual(target.read_bytes(), b"keep")
