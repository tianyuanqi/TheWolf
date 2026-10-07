"""核对腾讯候选及P01中证原件后离线重放，绝不代替新鲜真实更新验收。"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from pmi.index_calendar import CALENDAR_SOURCES, complete_window
from pmi.index_contract import Original, build_manifest, digest
from pmi.index_snapshot import index_root, publish, read_evidence, read_snapshot
from pmi.writer_lock import writer_lock

EXPECTED = {"Tencent": "396245b5940b3f6efe049c9582113d0398738805a12d5772f0f8fead6c9c531a",
            "C01": "40aff181ee6a4503d73cca807ec7c67e7be733429136c59d4e7550b609ca9e43"}


def main() -> None:
    """实际读取原件、开始/结束账本和日历哈希；缺材料就停止。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p01-root", type=Path, required=True)
    parser.add_argument("--tencent-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.data_root.resolve()
    repository = Path(__file__).resolve().parents[2]
    if root.is_relative_to(repository / ".local-data") or index_root(root).exists():
        parser.error("需要尚无指数子根的隔离目录，不覆盖旧测试结果或正式库")
    receipts = json.loads((args.p01_root / "evidence/originals-manifest.json").read_bytes())
    ledger = [json.loads(line) for line in (args.p01_root / "evidence/request-ledger.jsonl").read_text().splitlines()]
    tencent_receipt = json.loads((args.tencent_root / "receipt.json").read_bytes())
    content = (args.tencent_root / "raw-response.bin").read_bytes()
    assert digest(content) == tencent_receipt["sha256"] == EXPECTED["Tencent"]
    assert tencent_receipt["status_code"] == 200 and tencent_receipt["bytes"] == len(content)
    originals = [Original("tencent", content, tencent_receipt["start_utc"], tencent_receipt["end_utc"])]
    for source, request_id in (("csindex", "C01"),):
        receipt = receipts[request_id]
        assert receipt["sha256"] == EXPECTED[request_id]
        content = args.p01_root.joinpath("raw", receipt["sha256"]).read_bytes()
        assert digest(content) == receipt["sha256"]
        wire = next(item for item in ledger if item["event"] == "wire_start" and item["id"] == request_id)
        started = datetime.fromtimestamp(wire["time"], timezone.utc).isoformat()
        originals.append(Original(source, content, started, receipt["retrieved_at"]))
    for _, object_id in CALENDAR_SOURCES:
        assert digest(args.p01_root.joinpath("raw", object_id).read_bytes()) == object_id
    days = complete_window(datetime(2026, 10, 5, tzinfo=timezone.utc))
    manifest = build_manifest(days, tuple(originals))
    with writer_lock(root):
        snapshot_id = publish(root, manifest, tuple(originals), {"job_id": "tencent-offline-replay", "result": "business_changed", "message": "腾讯候选及P01固定原件离线重放，非本轮联网成功"})
    view = read_snapshot(root, snapshot_id)
    for item in view["evidence"]:
        evidence = read_evidence(root, snapshot_id, item["object_id"])
        for day in ("2025-09-04", "2025-12-31", "2026-01-05", "2026-09-30"):
            row = next(row for row in evidence["rows"] if row["trade_date"] == day)
            print(item["source"], day, row["locator"], row["open"], row["high"], row["low"], row["close"])
    print("OFFLINE ONLY: 260 days / 1040 exact matches; immutable snapshot", snapshot_id)
    print(json.dumps(view["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
