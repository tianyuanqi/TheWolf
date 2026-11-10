"""独立假配置的连续原记录、独立折算证据及迟到净值；只写调用者隔离Store。"""
from copy import deepcopy
from decimal import Decimal

from etf_flow_fixture import stored_sample
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.evidence import Evidence
from pmi.market_data.etf_flow.model import Configuration, Input, digest, canonical
from pmi.market_data.etf_flow.repository import Repository


def revisions(store, *, publish_correction=True, nav_scale=Decimal(1)):
    """四只两组：原折算10元、修订20元；末日缺NAV80元小计，补后100元完整。"""
    config, inputs, evidence, dates = stored_sample(store, 'page-four', 324)
    raw = deepcopy(config.raw); raw['pool_versions'] = raw['pool_versions'][:1]
    config = Configuration.parse(raw); members = config.pools[-1].members
    Cache(store, None, config).bind_configuration()
    ids = {m.id for m in members}; inputs = tuple(x for x in inputs if x.member_id in ids)
    split_day, last = dates[-2:]
    previous = next(x.value('shares') for x in inputs if x.member_id == members[0].id and x.date == dates[-3])

    def material(at, version, factor, tail, split_amount, missing_nav):
        proof = store.put(canonical({'synthetic_test_only': True, 'kind': 'split', 'version': version,
                                'factor': factor, 'tail': tail, 'date': split_day}))
        documents = []
        for row in inputs:
            if row.date > at[:10]: continue
            doc = deepcopy(row.raw)
            if row.member_id == members[0].id and row.date in (split_day, last):
                doc['fields']['shares']['value'] = str(previous * Decimal(factor) + Decimal(tail) + split_amount
                                                      + (20 if row.date == last else 0))
                if row.date == last and missing_nav: doc['fields'].pop('nav')
            if row.member_id == members[-1].id and row.date == last:
                prior = next(x for x in inputs if x.member_id == row.member_id and x.date == split_day)
                doc['fields']['shares']['value'] = str(prior.value('shares'))
            if 'nav' in doc['fields']:
                doc['fields']['nav']['value'] = str(Decimal(doc['fields']['nav']['value']) * nav_scale)
            for field in doc['fields'].values(): field['source']['retrieved_at'] = at
            documents.append(doc)
        raw_id = store.put(canonical({'synthetic_test_only': True, 'rows': documents}))
        rows = []
        for doc in documents:
            for field in doc['fields'].values(): field['source']['object_id'] = raw_id
            rows.append(Input.parse(doc))
        ev = deepcopy(evidence.raw); ev.update(version=version, confirmed_at=at)
        ev['adjustments'] = [a for a in ev['adjustments'] if a['member_id'] in ids]
        for a in ev['adjustments']: a['confirmed_at'] = at
        for s in ev['sources']: s['retrieved_at'] = at
        ev['sources'].append({'object_id': proof, 'publisher': '虚构独立折算公告', 'channel': '隔离测试',
            'url': members[0].basis.url, 'retrieved_at': at, 'published_at': None,
            'locator': '测试折算公告倍率和尾差段：' + version, 'original_unit': '倍率、份', 'precision': '合成精确值'})
        ev['adjustments'].append({'member_id': members[0].id, 'kind': 'adjustment', 'start': split_day, 'end': split_day,
            'factor': factor, 'tail': tail, 'source_ids': [proof], 'confirmed_at': at, 'confirmation': '测试倍率及尾差均有专属原件'})
        ev['events'] = [{'id': f'fixture-event-{n}', 'member_ids': [members[0].id], 'occurred_start': None, 'occurred_end': None,
            'published_date': dates[-3], 'source_id': proof, 'locator': f'同一公告第{n}段',
            'description': f'仅隔离事件{n}', 'subjects': ['虚构主体']} for n in (1, 2)]
        return tuple(rows), Evidence.parse(ev, ids), proof

    repo = Repository(store)
    first_at = dates[-2] + 'T12:00:00+08:00'
    first_rows, first_ev, _ = material(first_at, 'view-initial', '2', '0.5', 10, True)
    first_rows = tuple(x for x in first_rows if x.date <= dates[-3])
    # 初始依据不能包含确认时点之后的单日事件；普通区间保留允许覆盖的输入日。
    ev = deepcopy(first_ev.raw); ev['adjustments'] = [a for a in ev['adjustments'] if a['kind'] == 'normal']
    first_ev = Evidence.parse(ev, ids)
    initial = repo.publish(config, first_ev, first_rows, end=dates[-3], selection_at=first_at,
        operation_key=digest('view-initial'), expected=None, allow_daily_signal=False)
    old_rows, old_ev, old_proof = material(dates[-1] + 'T12:00:00+08:00', 'view-original', '2', '0.5', 10, True)
    prior_rows = first_rows + tuple(x for x in old_rows if x.date == split_day)
    prior = repo.publish(config, old_ev, prior_rows, end=split_day, selection_at=dates[-1] + 'T12:00:00+08:00',
        operation_key=digest('view-original'), expected=initial, allow_daily_signal=True)
    at = '2026-11-05T12:00:00+08:00'
    rows, ev, _ = material(at, 'view-partial', '2', '0.5', 10, True)
    partial_inputs = prior_rows + tuple(x for x in rows if x.date == last)
    partial = repo.publish(config, ev, partial_inputs, end=last, selection_at=at,
        operation_key=digest('view-partial'), expected=prior, allow_daily_signal=True)
    corrected_at = '2026-11-05T13:00:00+08:00'
    corrected, corrected_ev, new_proof = material(corrected_at, 'view-corrected', '3', '0.75', 20, False)
    corrected_inputs = first_rows + tuple(x for x in corrected if x.date in (split_day, last))
    final = repo.publish(config, corrected_ev, corrected_inputs, end=last, selection_at=corrected_at,
        operation_key=digest('view-corrected'), expected=partial, allow_daily_signal=True) if publish_correction else None
    return {'config': config, 'inputs': corrected_inputs, 'evidence': corrected_ev, 'dates': dates,
            'initial': initial, 'prior': prior, 'partial': partial, 'final': final,
            'original_proof': old_proof, 'corrected_proof': new_proof}
