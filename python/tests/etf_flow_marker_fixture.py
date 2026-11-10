"""仅合成的页面验收输入：明显不同的单只累计、旧缺失、折算和多种事件日期。"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

from etf_flow_view_fixture import revisions
from pmi.market_data.etf_flow.evidence import Evidence
from pmi.market_data.etf_flow.model import canonical, digest
from pmi.market_data.etf_flow.repository import Repository
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.etf_flow.view import build


def seed(root: Path) -> dict:
    """仅写调用者自有空根；ETF运行配置只读、无grant，无真实网络或金融身份。"""
    for name in ('price', 'etf', 'runtime', 'cache'):
        (root / name).mkdir(mode=0o700)
    store = Store(root / 'etf')
    store.initialize()
    with store.writer():
        fixture = revisions(store, nav_scale=Decimal('100000000'))
        config, dates = fixture['config'], fixture['dates']
        members = config.pools[-1].members
        at = '2026-11-06T12:00:00+08:00'
        raw = deepcopy(fixture['evidence'].raw)
        raw.update(version='isolated-marker-cases', confirmed_at=at)
        source = store.put_json({'synthetic_test_only': True, 'note': '事件与非交易日的显示测试，无真实金融资料'})
        source_unknown = store.put_json({'synthetic_test_only': True, 'note': '仅测试公开日未知'})
        for identity, retrieved in ((source, at), (source_unknown, dates[-3] + 'T12:00:00+08:00')):
            raw['sources'].append({'object_id': identity, 'publisher': '虚构标记测试资料', 'channel': '隔离测试',
                'url': members[0].basis.url, 'retrieved_at': retrieved, 'published_at': None,
                'locator': '合成标记日期及说明', 'original_unit': '日期', 'precision': '合成值'})
        cases = [
            ('later', members[0].id, dates[-2], '2026-11-06', source, '后来公开的发生日，当前回看须标事后对照'),
            ('weekend', members[0].id, None, '2026-10-31', source, '周末公告，仅标原公告日，不造交易点'),
            ('outside', members[0].id, dates[0], dates[0], source, '窗口外历史事件，不贴到窗口首日'),
            ('other', members[1].id, dates[-3], dates[-3], source, '另一成员专属事件，不串入首只'),
            ('unknown', members[0].id, None, None, source_unknown, '公开日未知，标已知时间，不称公告日'),
        ]
        for identity, member, occurred, published, proof, description in cases:
            raw['events'].append({'id': 'marker-' + identity, 'member_ids': [member], 'occurred_start': occurred,
                'occurred_end': occurred, 'published_date': published, 'source_id': proof,
                'locator': '合成场景 ' + identity, 'description': description, 'subjects': ['虚构测试主体']})
        evidence = Evidence.parse(raw, {member.id for member in members})
        repository = Repository(store)
        snapshot = repository.publish(config, evidence, fixture['inputs'], end=dates[-1], selection_at=at,
            operation_key=digest('marker-cases'), expected=fixture['final'], allow_daily_signal=False)
        expectations = {mode: build(repository, snapshot, mode=mode, period=60, end=dates[-1], group=None,
                                   server_day=at[:10]) for mode in ('current', 'original')}
    for name, value in (('pool', config.raw), ('evidence', evidence.raw), ('expectations', expectations)):
        path = root / (name + '.json')
        path.write_bytes(canonical(value))
        path.chmod(0o600)
    (root / 'test-clock.json').write_text(json.dumps({'at': at}))
    return {'root': str(root / 'etf'), 'configuration': str(root / 'pool.json'),
            'evidence': str(root / 'evidence.json'), 'grant': None, 'write_enabled': False, 'refresh_revision': None}
