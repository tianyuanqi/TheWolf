"""用真实存储生成同快照不同观察的隔离案例，供前端effect回归使用。"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile

from pmi.market_data import index_series_store as store
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.writer_lock import writer_lock
from test_index_series_contract import WINDOW, originals
from test_index_series_runtime import state


def cases() -> dict:
    """只创建自有合成根；每个价格版本发布两次，返回真实current/status标识。"""
    index = get_index('sse:000001:price')
    result = {}
    with tempfile.TemporaryDirectory(prefix='wolf-startup-observation-', dir='/private/tmp') as value:
        root = Path(value).resolve()
        with writer_lock(root):
            store.prepare_directories(root, index)
        for name, prices, hour in [('old', ('100.01','110.02','90.00','105.12'), 1),
                                   ('new', ('200.01','210.02','190.00','205.12'), 3)]:
            for number in range(2):
                items = tuple(replace(item, started_at=f'2026-10-28T0{hour+number}:00:00Z',
                                      completed_at=f'2026-10-28T0{hour+number}:00:01Z')
                              for item in originals(index, WINDOW, prices=prices))
                pending = {**state(index, f'{name}-{number}'), 'result': 'unchanged' if number else 'business_changed'}
                with writer_lock(root):
                    store.save_status(root, index, pending)
                    store.publish(root, index, WINDOW, build_manifest(index, WINDOW, items), items, pending)
            current = store.read_snapshot(root, index)
            status = store.read_status(root, index)
            assert current['snapshot_id'] == status['snapshot_id']
            assert current['observation_id'] != status['observation_id']
            result[name] = {'current': {key: current[key] for key in ('snapshot_id','observation_id','window')},
                            'status': status}
    assert not root.exists()
    assert result['old']['current']['snapshot_id'] != result['new']['current']['snapshot_id']
    return result


if __name__ == '__main__':
    def guard(event, _args):
        if event == 'socket.connect':
            raise RuntimeError('fixture cannot access network')
    sys.addaudithook(guard)
    print(json.dumps(cases()))
