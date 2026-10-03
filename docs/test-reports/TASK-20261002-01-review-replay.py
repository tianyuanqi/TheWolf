"""独立审查保存原件的离线重放；仅在自动清理的隔离副本执行真实标准化和发布。"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from pmi.data_update import classify_change, prepare_update
from pmi.snapshot import publish_snapshot, read_pdf, read_snapshot
from pmi.trading_calendar import complete_window


def main() -> None:
    """校验真实原件哈希、新窗口、公告时间与旧固定视图；不联网、不操作原真实库。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--backup-root', type=Path, required=True)
    args = parser.parse_args()
    sina = (args.evidence_root / 'sina.raw').read_bytes()
    official = (args.evidence_root / 'szse.raw').read_bytes()
    assert hashlib.sha256(sina).hexdigest() == '86f526512fc2a5431c1e4e769685cb74b524179e2bd720b6b4c8e0f40497336f'
    assert hashlib.sha256(official).hexdigest() == '411657407ed6eb1c0c06678e25dcbdc6f028a770207f362e9ca721db6ebeef17'
    days = complete_window(datetime.fromisoformat('2026-10-02T20:00:00+08:00'))
    with tempfile.TemporaryDirectory(prefix='thewolf-review-replay-') as directory:
        root = Path(directory) / 'isolated'
        shutil.copytree(args.backup_root, root)
        previous = read_snapshot(root)
        with sqlite3.connect(root / 'slice.sqlite') as connection:
            ids = [row[0] for row in connection.execute('SELECT snapshot_id FROM snapshots')]
        old = {key: read_snapshot(root, key) for key in ids}
        payload = prepare_update(root, previous, sina, official, '2026-10-02T12:34:03.173103+00:00', days)
        result = classify_change(previous, payload)
        new_id = publish_snapshot(root, payload)
        current = read_snapshot(root)
        assert new_id == 'c6768b6b93692cac9a9e09425ec8cb67cd562da36acd90f8ca2bcc250f138201'
        assert current['snapshot_id'] == new_id and current['observed_count'] == current['open_session_count'] == 60
        assert all(read_snapshot(root, key) == value for key, value in old.items())
        assert [item['public_available_at'] for item in current['documents']] == [item['public_available_at'] for item in previous['documents']]
        for item in current['documents']:
            assert hashlib.sha256(read_pdf(root, new_id, item['pdf_object_id'])).hexdigest() == item['pdf_object_id']
            assert item.get('original_retrieved_at') is None
        again = prepare_update(root, current, sina, official, '2026-10-02T12:35:03.173103+00:00', days)
        assert classify_change(current, again) == 'unchanged'
        assert publish_snapshot(root, again) == new_id
        with sqlite3.connect(root / 'slice.sqlite') as connection:
            assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        print(json.dumps({'real_saved_originals': 'PASS', 'network_requests': 0, 'snapshot_id': new_id,
                          'result': result, 'start': days[0], 'end': days[-1], 'count': len(days),
                          'old_fixed_views_preserved': len(ids), 'pdfs': 2, 'announcement_times_preserved': True,
                          'repeat': 'unchanged'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
