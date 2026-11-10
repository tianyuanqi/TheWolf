"""S3五项修复的实际页面/服务；通过明确更新发布已存合成修订，零出站。"""
import json
from pathlib import Path

from etf_flow_fixture import AT, END
from etf_flow_smoke import main
from etf_flow_view_fixture import revisions
from pmi.market_data.etf_flow.budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.model import canonical
from pmi.market_data.storage.etf_store import Store


def seed(root: Path):
    for name in ('price', 'etf', 'runtime', 'cache'): (root/name).mkdir(mode=0o700)
    from sqlite_fixture import initialize
    initialize(root/'etf')
    store = Store(root/'etf'); store.initialize()
    with store.writer():
        f = revisions(store, publish_correction=False)
        cache = Cache(store, None, f['config']); cache.bind_configuration(); cache.save_inputs(f['inputs'])
        grant = Grant.parse({'id': 'view-regression-zero-network', 'confirmed_at': AT, 'confirmation': '仅合成修订，禁止外网',
            'expires_at': '2026-11-06T12:00:00+08:00', 'members': [m.id for m in f['config'].pools[-1].members],
            'start': f['dates'][0], 'end': END, 'domains': ['query.sse.com.cn', 'api.fund.eastmoney.com'],
            'max_requests': 0, 'max_bytes': 0, 'response_limit': 1024, 'interval_seconds': 3, 'timeout_seconds': 1})
        Budget(store, grant).initialize()
    for name, value in [('pool', f['config'].raw), ('evidence', f['evidence'].raw), ('grant', grant.raw)]:
        path = root/(name+'.json'); path.write_bytes(canonical(value)); path.chmod(0o600)
    (root/'test-clock.json').write_text(json.dumps({'at': '2026-11-05T13:00:00+08:00'}))
    (root/'page-expectations.json').write_text(json.dumps({'members': f['config'].raw['pool_versions'][-1]['members'],
        'end': END, 'previous': f['dates'][-2], 'first_input': f['dates'][0], 'initial_end': f['dates'][-3], 'partial': f['partial'],
        'old_proof': f['original_proof'], 'new_proof': f['corrected_proof']}, ensure_ascii=False))
    return {'root': str(root/'etf'), 'configuration': str(root/'pool.json'), 'evidence': str(root/'evidence.json'),
        'grant': str(root/'grant.json'), 'write_enabled': True, 'refresh_revision': None}


if __name__ == '__main__': main(seed, 'etf_flow_view_browser.mjs')
