"""用指定旧版存储源码创建合成旧库，验证更新、失败、恢复与观察顺序。"""

import argparse
import importlib.util
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import fields, replace
from pathlib import Path

from pmi.snapshot import SnapshotError, publish_snapshot, read_snapshot
from test_data_update import old_snapshot, run_update


def main() -> None:
    """完全在临时根验证旧代码生成的 A/B 同刻库；只读旧源码，不用真实原件。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-snapshot", required=True, type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("legacy_snapshot", args.legacy_snapshot)
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy
    spec.loader.exec_module(legacy)
    with tempfile.TemporaryDirectory(prefix="thewolf-legacy-update-") as directory:
        base = Path(directory)
        # 通过合成建库入口取输入，不复制当前版清单字段到旧版证据。
        captured = []
        from unittest.mock import patch
        with patch("test_data_update.publish_snapshot", side_effect=lambda root, payload: captured.append(payload)):
            old_snapshot(base / "unused")
        payload = captured[0]
        old_document = lambda doc: legacy.DocumentEvidence(**{field.name: getattr(doc, field.name) for field in fields(legacy.DocumentEvidence)})
        old_payload = legacy.SliceInput(**{**payload.__dict__, "document": old_document(payload.document),
                                          "additional_documents": tuple(old_document(doc) for doc in payload.additional_documents)})
        for stage in ("objects_ready", "manifest_uncommitted", "committed"):
            root = base / stage
            a_id = legacy.publish_snapshot(root, old_payload)
            b_payload = replace(old_payload, raw_response=b"synthetic same-time B")
            b_id = legacy.publish_snapshot(root, b_payload)
            fixed = {key: read_snapshot(root, key) for key in (a_id, b_id)}
            backup = base / (stage + "-backup")
            shutil.copytree(root, backup)
            def interrupt(current):
                if current == stage:
                    raise SnapshotError("synthetic update interruption")
            result = run_update(root, checkpoint=interrupt)
            if stage != "committed":
                assert result["stage"] == "failed"
                assert read_snapshot(root)["snapshot_id"] == b_id
            else:
                assert result["stage"] == "completed"
            for key, value in fixed.items():
                assert read_snapshot(root, key) == value
            assert read_snapshot(backup)["snapshot_id"] == b_id
            assert run_update(root)["stage"] == "completed"
            # 单独恢复一致性备份后，旧 A 的同刻重试不能倒退原 B；较晚新 A 仍合法。
            recovered = base / (stage + "-restored")
            shutil.copytree(backup, recovered)
            publish_snapshot(recovered, payload)
            assert read_snapshot(recovered)["snapshot_id"] == b_id
            publish_snapshot(recovered, replace(payload, retrieved_at="2026-09-25T01:00:00+00:00"))
            assert read_snapshot(recovered)["snapshot_id"] == a_id
            with sqlite3.connect(root / "slice.sqlite") as connection:
                assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    print("legacy code A/B same-time, update interruptions, immutable fixed views, backup restore, later A observation: PASS")


if __name__ == "__main__":
    main()
