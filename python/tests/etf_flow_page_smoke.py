"""S3正式页真实服务联调：身份只取独立假配置，禁止真实网络及真实根。"""
from copy import deepcopy
import json
from pathlib import Path
import sys

from etf_flow_fixture import AT, END, stored_sample
from etf_flow_smoke import main
from pmi.market_data.etf_flow.budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.evidence import Evidence
from pmi.market_data.etf_flow.model import Configuration, Input, canonical, digest
from pmi.market_data.etf_flow.repository import Repository
from pmi.market_data.storage.etf_store import Store


def page_seed(root: Path) -> dict:
    """同一个页面不带场景开关；仅启动前在自有临时根构造不同配置/历史事实。"""
    case = sys.argv[2]
    if case not in ('single', 'four', 'expanded', 'states'): raise ValueError('unknown isolated scenario')
    for name in ('price', 'etf', 'runtime', 'cache'): (root/name).mkdir(mode=0o700)
    from sqlite_fixture import initialize
    initialize(root/'etf')
    if case == 'four':
        from market_overview_smoke import IDS, INDICES, WINDOW, varied_originals, state, build_manifest
        from pmi.market_data.storage import index_store as index_series_store
        from sqlite_fixture import initialize, price_writer as writer_lock
        for index in INDICES:
            if index.index_id not in IDS: continue
            originals = varied_originals(index)
            with writer_lock(root/'etf'):
                index_series_store.prepare_directories(root/'etf', index)
                index_series_store.publish(root/'etf', index, WINDOW, build_manifest(index, WINDOW, originals), originals, state(index))
    store = Store(root/'etf'); store.initialize(); repo = Repository(store)
    with store.writer():
        fixture = 'single' if case == 'single' else 'page-four' if case == 'four' else 'multiple'
        config, inputs, evidence, dates = stored_sample(store, fixture, 322)
        raw = deepcopy(config.raw)
        if case == 'single':
            rule = raw['rule_versions'][0]
            for key in ('confirmed_at', 'confirmation', 'k', 'min_in', 'min_out', 'direction_ratio', 'streak_days'): rule[key] = None
        if case == 'four': raw['pool_versions'] = raw['pool_versions'][:1]
        config = Configuration.parse(raw)
        members = config.pools[-1].members
        inputs = tuple(row for row in inputs if row.member_id in {m.id for m in members})
        ev = deepcopy(evidence.raw)
        ev['adjustments'] = [a for a in ev['adjustments'] if a['member_id'] in {m.id for m in members}]
        # 合成披露包含10个百分点，验证不被前端再次乘100；晚披露只能事后对照。
        proof = store.put(canonical({'synthetic_test_only': True, 'kind': 'holder-event', 'members': [m.id for m in members]}))
        ev['sources'].append({'object_id': proof, 'publisher': '虚构测试披露方', 'channel': '隔离证据', 'url': members[0].basis.url,
            'retrieved_at': AT, 'published_at': AT, 'locator': '仅测试报告 §9', 'original_unit': '份、百分数', 'precision': '合成值'})
        ev['disclosures'] = [{'id': 'test-disclosure', 'member_id': members[0].id, 'report_date': '2026-06-30',
            'published_date': '2026-11-05', 'source_id': proof, 'locator': '测试 §9', 'state': 'disclosed',
            'holders': [{'name': '虚构持有人', 'shares': '1000', 'percentage': '10', 'classification': '测试主体',
                'classification_basis': '仅隔离数据'}], 'note': '不是真实持仓'},
            {'id': 'test-not-disclosed', 'member_id': members[0].id, 'report_date': '2025-12-31',
            'published_date': '2026-03-01', 'source_id': proof, 'locator': '测试旧报告', 'state': 'not_disclosed', 'holders': [], 'note': '仅测试未披露'}]
        ev['events'] = [{'id': 'test-event', 'member_ids': [members[0].id], 'occurred_start': None, 'occurred_end': None,
            'published_date': '2026-11-05', 'source_id': proof, 'locator': '测试公告第1段',
            'description': '虚构待核事件，不代表真实买卖', 'subjects': ['虚构测试主体']}]
        evidence = Evidence.parse(ev, {m.id for m in members})
        Cache(store, None, config).bind_configuration()
        if case in ('expanded', 'states'):
            prior_raw = deepcopy(config.raw); prior_raw['pool_versions'] = prior_raw['pool_versions'][:1]
            prior_config = Configuration.parse(prior_raw)
            prior_members = {m.id for m in prior_config.pools[-1].members}
            prior_at = '2026-11-04T12:00:00+08:00'
            prior_rows = []
            for row in inputs:
                if row.member_id not in prior_members or row.date == END: continue
                item = deepcopy(row.raw)
                for field in item['fields'].values(): field['source']['retrieved_at'] = prior_at
                prior_rows.append(Input.parse(item))
            prior_ev = deepcopy(ev); prior_ev.update(confirmed_at=prior_at, version='test-prior-evidence')
            prior_ev['disclosures'] = []; prior_ev['events'] = []
            prior_ev['sources'] = [s for s in prior_ev['sources'] if s['object_id'] != proof]
            for source in prior_ev['sources']: source['retrieved_at'] = prior_at
            prior_ev['adjustments'] = [a for a in prior_ev['adjustments'] if a['member_id'] in prior_members]
            for adjustment in prior_ev['adjustments']: adjustment.update(confirmed_at=prior_at, end=dates[-2])
            before = repo.publish(prior_config, Evidence.parse(prior_ev, prior_members), tuple(prior_rows), end=dates[-2],
                selection_at=prior_at, operation_key=digest('page-prior'), expected=None, allow_daily_signal=False)
            # 保留相同历史输入引用；只追加末日和新成员，不把测试生成器后取时间倒灌旧数据。
            inputs = tuple(prior_rows) + tuple(row for row in inputs if row.date == END or row.member_id not in prior_members)
            if case == 'states':
                adjusted = []
                for row in inputs:
                    if row.member_id == members[-1].id and row.date in dates[:2]: continue
                    item = deepcopy(row.raw)
                    if row.date == END and row.member_id == members[0].id: item['fields'].pop('nav')
                    if row.date == END and row.member_id == members[2].id:
                        prior = next(p for p in inputs if p.member_id == row.member_id and p.date == dates[-2])
                        item['fields']['shares']['value'] = str(prior.value('shares'))
                    if item != row.raw:
                        corrected = store.put(canonical({'synthetic_test_only': True, 'values': item}))
                        for field in item['fields'].values(): field['source']['object_id'] = corrected
                    adjusted.append(Input.parse(item))
                inputs = tuple(adjusted)
                final_pool = deepcopy(raw['pool_versions'][-1]); final_pool.update(version='test-many-3',
                    effective_date='2026-11-05', confirmed_at=AT, change='仅配置停用一只及调整分组')
                final_pool['members'][1]['disabled_date'] = '2026-11-05'
                final_pool['members'][2]['group'] = '重新分组测试'
                raw['pool_versions'].append(final_pool); config = Configuration.parse(raw)
            repo.publish(config, evidence, inputs, end=END, selection_at=AT, operation_key=digest('page-daily'),
                expected=before, allow_daily_signal=True)
        elif case == 'four':
            from pmi.market_data.index_calculations import FORMULA_VERSION
            from pmi.market_data.activity.model import TWO_MARKET
            context = {'format': 'etf-flow-context-v1', 'rows': [{'date': END, 'reason': None,
                'indices': [{'index_id': members[0].index_id, 'snapshot_id': digest('synthetic-index'), 'formula_version': FORMULA_VERSION,
                    'date': END, 'return_1': '1.25', 'return_5': '-2.50', 'input_basis': 'posthoc_context', 'calculated_at': AT}],
                'market': {'series_id': TWO_MARKET, 'activity_id': digest('synthetic-market'), 'formula_version': 'etf-flow-context-v1',
                    'date': END, 'scope_label': '沪深', 'turnover': '12300000000', 'ratio_20': '1.25',
                    'input_basis': 'posthoc_context', 'calculated_at': AT}}]}
            repo.publish(config, evidence, inputs, end=END, selection_at=AT, operation_key=digest('page-four'), expected=None,
                allow_daily_signal=False, context=context)
        Cache(store, None, config).save_inputs(inputs)
        grant = Grant.parse({'id': 'page-no-network', 'confirmed_at': AT, 'confirmation': '本隔离场景禁止外网',
            'expires_at': '2026-11-06T12:00:00+08:00', 'members': [m.id for m in config.pools[-1].members],
            'start': dates[0], 'end': END, 'domains': ['query.sse.com.cn', 'api.fund.eastmoney.com'],
            'max_requests': 0, 'max_bytes': 0, 'response_limit': 1024, 'interval_seconds': 3, 'timeout_seconds': 1})
        Budget(store, grant).initialize()
    for name, value in (('pool', config.raw), ('evidence', evidence.raw), ('grant', grant.raw)):
        path = root/(name+'.json'); path.write_bytes(canonical(value)); path.chmod(0o600)
    (root/'page-expectations.json').write_text(json.dumps({'case': case, 'end': END, 'previous': dates[-2],
        'members': config.raw['pool_versions'][-1]['members'], 'expected_count': len(members),
        'original_recorded': case in ('expanded', 'states')}, ensure_ascii=False))
    return {'root': str(root/'etf'), 'configuration': str(root/'pool.json'), 'evidence': str(root/'evidence.json'),
        'grant': str(root/'grant.json'), 'write_enabled': True, 'refresh_revision': None}


if __name__ == '__main__': main(page_seed, 'etf_flow_page_browser.mjs')
