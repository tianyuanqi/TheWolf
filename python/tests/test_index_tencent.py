"""腾讯换源反例与旧契约只读兼容，所有输入均为明确合成原件。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pmi.index_contract import (CONTRACT, LEGACY_CONTRACT, Original, SourceNotReady,
                                build_manifest, canonical, digest, parse_source)
from pmi.index_snapshot import index_root, publish, read_evidence, read_snapshot
from pmi.index_update import fetch_bounded
from pmi.snapshot import SnapshotError
from pmi.writer_lock import writer_lock
from test_index import DAYS, mutated, originals, state


def legacy_originals():
    """仅为兼容测试生成旧东财格式，生产采集不使用此路径。"""
    items = originals()
    raw = {"rc": 0, "data": {"code": "000300", "market": 1, "name": "沪深300", "decimal": 2,
        "klines": [f"{day},100.00,105.00,110.00,90.00,0,0,0" for day in DAYS]}}
    return (Original("eastmoney", canonical(raw), items[0].started_at, items[0].completed_at), items[1])


class TencentContractTests(unittest.TestCase):
    def test_json_envelope_and_original_locator(self):
        items = originals()
        earlier = ["2025-09-03", "100.00", "105.00", "110.00", "90.00"]
        items = mutated(items, 0, lambda raw: raw["data"]["sh000300"]["day"].insert(0, earlier))
        for prefix, suffix in ((b"", b""), (b"kline_dayqfq=", b";\n")):
            with self.subTest(prefix=prefix):
                content = prefix + items[0].content + suffix
                manifest = build_manifest(DAYS, (Original("tencent", content, items[0].started_at, items[0].completed_at), items[1]))
                evidence = manifest["evidence"][0]
                self.assertEqual(len(manifest["bars"]), 260)
                self.assertEqual(evidence["object_id"], digest(content))
                self.assertEqual(evidence["rows"][0]["locator"], "$.data.sh000300.day[1]")
                self.assertEqual(manifest["bars"][0]["evidence_refs"][0]["locator"], "$.data.sh000300.day[1]")
                self.assertEqual(manifest["source_contract"], CONTRACT)

    def test_no_script_execution_duplicate_fields_or_branch_fallback(self):
        raw = originals()[0].content
        for content in (b"other=" + raw, b"kline_dayqfq=" + raw + b";alert(1)",
                        b"kline_dayqfq=(" + raw + b")", raw.replace(b'"code":0', b'"code":0,"code":0')):
            with self.subTest(content=content[:40]), self.assertRaises(SnapshotError):
                parse_source("tencent", content)
        mutations = [lambda raw: raw.update(code=True), lambda raw: raw.update(code="0"),
            lambda raw: raw["data"]["sh000300"].update(qfqday=[]),
            lambda raw: raw["data"]["sh000300"].update(hfqday=[]),
            lambda raw: raw["data"]["sh000300"].pop("day"),
            lambda raw: raw["data"]["sh000300"]["qt"].update(sh000300=["1", "沪深300", "H00300"]),
            lambda raw: raw["data"]["sh000300"]["day"][0].__setitem__(1, 100),
            lambda raw: raw["data"]["sh000300"]["day"][0].__setitem__(1, "100.001")]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(SnapshotError):
                build_manifest(DAYS, mutated(originals(), 0, mutation))

    def test_date_validation_precedes_trimming(self):
        early = ["2025-09-03", "100.00", "105.00", "110.00", "90.00"]
        for rows in ([early, early], [early, ["2025-09-02", *early[1:]]], [["2025-02-30", *early[1:]]]):
            with self.subTest(rows=rows), self.assertRaises(SnapshotError):
                build_manifest(DAYS, mutated(originals(), 0, lambda raw: raw["data"]["sh000300"]["day"].__setitem__(slice(0, 0), rows)))
        with self.assertRaisesRegex(SnapshotError, "晚于冻结"):
            build_manifest(DAYS, mutated(originals(), 0, lambda raw: raw["data"]["sh000300"]["day"].append(["2026-10-01", *early[1:]])))
        with self.assertRaisesRegex(SnapshotError, "内部缺日"):
            build_manifest(DAYS, mutated(originals(), 0, lambda raw: raw["data"]["sh000300"]["day"].insert(2, ["2025-09-06", *early[1:]])))
        with self.assertRaises(SourceNotReady):
            build_manifest(DAYS, mutated(originals(), 0, lambda raw: raw["data"]["sh000300"]["day"].__delitem__(slice(-2, None))))
        conflict = mutated(originals(), 1, lambda raw: raw["data"][0].update(close="104.99"))
        with self.assertRaisesRegex(SnapshotError, "双源不一致"):
            build_manifest(DAYS, mutated(conflict, 0, lambda raw: raw["data"]["sh000300"]["day"].pop()))

    def test_legacy_read_preserved_after_new_publication(self):
        with tempfile.TemporaryDirectory(prefix="thewolf-tencent-compat-") as directory:
            root = Path(directory).resolve()
            items = legacy_originals()
            old_manifest = build_manifest(DAYS, items, contract_version=LEGACY_CONTRACT["version"])
            # 仅模拟旧版本曾经发布的磁盘夹具；解除替身后所有读取和新发布走生产路径。
            with writer_lock(root), patch("pmi.index_snapshot.build_manifest", return_value=old_manifest):
                old_id = publish(root, old_manifest, items, state("old-fixture"))
            old_view = read_snapshot(root, old_id)
            old_evidence = [read_evidence(root, old_id, item["object_id"]) for item in old_view["evidence"]]
            old_objects = {path.name: path.read_bytes() for path in (index_root(root) / "objects").iterdir()}
            with writer_lock(root), self.assertRaises(SnapshotError):
                publish(root, old_manifest, items, state("forbidden-legacy-publication"))
            new = originals(stamp="2026-10-06T01:00:00Z")
            with writer_lock(root):
                new_id = publish(root, build_manifest(DAYS, new), new, state("new-tencent"))
            self.assertNotEqual(new_id, old_id)
            self.assertEqual(read_snapshot(root)["snapshot_id"], new_id)
            self.assertEqual(read_snapshot(root, old_id), old_view)
            self.assertEqual([read_evidence(root, old_id, item["object_id"]) for item in old_view["evidence"]], old_evidence)
            for object_id, content in old_objects.items():
                self.assertEqual((index_root(root) / "objects" / object_id).read_bytes(), content)
            with self.assertRaisesRegex(SnapshotError, "未知指数来源契约"):
                build_manifest(DAYS, new, contract_version="unknown-v3")

    def test_legacy_fetch_rejected_before_budget_or_process(self):
        with tempfile.TemporaryDirectory(prefix="thewolf-source-whitelist-") as directory:
            root = Path(directory).resolve()
            with patch("pmi.index_update._record_attempt") as record, patch("pmi.index_update.subprocess.Popen") as spawn:
                with self.assertRaises(SnapshotError):
                    fetch_bounded(root, "eastmoney", DAYS, "forbidden")
                record.assert_not_called()
                spawn.assert_not_called()
