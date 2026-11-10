"""合并只读契约与旧路径逐项等价；完整隔离原件，不接触真实根或外网。"""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from http_test_support import ReadClient, disk
from overview_performance import seed_complete, configuration
from pmi.api import create_app
from urllib.parse import urlencode
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.integrity import Integrity
from pmi.market_data.storage.validation import check_all
from pmi.market_data.storage.originals import Originals
from pmi.market_data.compact_view import compact_index, compact_activity
from pmi.market_data.activity.calculations import formula_for
from pmi.market_data.activity.model import INDEX_IDS, MARKET, TWO_MARKET, ActivityError
from pmi.market_data.index_calculations import FORMULA_VERSION


def expand(value, identity_keys):
    """测试端按契约独立递归还原；不调用产品编码器倒算预期数值。"""
    identity = {key: value[key] for key in identity_keys}
    definitions = value['definitions']
    def walk(item):
        if isinstance(item, list):
            return [walk(child) for child in item]
        if not isinstance(item, dict):
            return item
        if 'definition' in item:
            return {**definitions[item['definition']], **{k: v for k, v in item.items() if k not in ('definition', 'start', 'end')},
                    'input_ref': {**identity, 'start': item['start'], 'end': item['end']}}
        result = {k: walk(v) for k, v in item.items() if k != 'definitions'}
        if 'open' in item and 'ma' in item:
            result['input_ref'] = {**identity, 'start': item['start'], 'end': item['end']}
        return result
    return walk(value)


class CombinedViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='wolf-combined-view-', dir='/private/tmp')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        seed_complete(cls.root)
        cls.before = {name: disk(cls.root/name) for name in ('data', 'activity')}
        cls.client = ReadClient.__new__(ReadClient)
        cls.client.config = configuration(cls.root, 18080, 18081)
        cls.client.app = create_app(cls.client.config)
        cls.addClassCleanup(cls.client.app.state.updates.close)
        cls.client.headers = {'host': cls.client.config.authority, 'origin': cls.client.config.allowed_origins[0],
                              'x-wolf-client': '1', 'x-wolf-expected-instance': cls.client.app.state.boundary.instance}
        cls.data = cls.client.config.market_data
        cls.fixtures = []
        cls.overviews = []


    @classmethod
    def tearDownClass(cls):
        assert cls.before == {name: disk(cls.root/name) for name in ('data', 'activity')}
        if os.environ.get('WOLF_COMBINED_FIXTURE'):
            target = Path(os.environ['WOLF_COMBINED_FIXTURE'])
            if not target.is_absolute() or not str(target).startswith('/private/tmp/wolf-overview-perf-'):
                raise ValueError('夹具输出必须为本轮独占临时路径')
            target.write_text(json.dumps(cls.fixtures, ensure_ascii=False))
        if os.environ.get('WOLF_OVERVIEW_FIXTURE'):
            target = Path(os.environ['WOLF_OVERVIEW_FIXTURE'])
            if not target.is_absolute() or not str(target).startswith('/private/tmp/wolf-overview-perf-'):
                raise ValueError('夹具输出必须为本轮独占临时路径')
            target.write_text(json.dumps(cls.overviews, ensure_ascii=False))


    def get(self, path, *, activity=False, **kwargs):
        return self.client.request(path, headers={'x-wolf-expected-config': self.client.config.activity_config_id
                                   if activity else self.client.config.index_config_id, **kwargs})


    def test_view_dto_integer_fast_path_retains_normalization_and_rejection(self):
        from pmi import http_contract
        value = self.price_reply(INDEX_IDS[0]).json()
        before = deepcopy(value)
        with patch.object(http_contract, '_integer_values', wraps=http_contract._integer_values) as normalize:
            self.assertEqual(http_contract.response_value('StoredPriceOverview', value), before)
            self.assertEqual(normalize.call_count, 0)
        self.assertEqual(value, before)
        # 原Schema的JSON整数允许5.0；严格DTO失败后沿用原规范化，不放宽布尔。
        value['storage_decimals'] = 2.0
        result = http_contract.response_value('StoredPriceOverview', value)
        self.assertIs(type(result['storage_decimals']), int)
        self.assertEqual(result, before)
        for bad in (True, 2.5, '2'):
            value['storage_decimals'] = bad
            with self.assertRaises(http_contract.ContractResponseError):
                http_contract.response_value('StoredPriceOverview', value)


    def test_observation_reuse_requires_exact_members_and_hashes(self):
        sid = INDEX_IDS[0];price = self.data.read_daily(sid)['snapshot'];runtime = self.data._activity_runtime
        current = runtime.current(sid, price['snapshot_id'])
        manifest = runtime.store.fixed(current['activity_id'])
        originals = {source['object_id']: runtime.store.original(source['object_id']) for source in manifest['sources']}
        expected = runtime.store.observations(current['activity_id'], manifest)
        with runtime.store.lock(write=False):
            self.assertEqual(runtime.store.observations(current['activity_id'], manifest, originals=originals), expected)
            for invalid in ({}, {**originals, '0'*64: b'other'}, {key: b'corrupted' for key in originals}):
                with self.assertRaises(ActivityError):runtime.store.observations(current['activity_id'], manifest, originals=invalid)


    def test_encoder_rejects_identity_before_removing_repetition(self):
        sid=INDEX_IDS[0]; snapshot=self.data.read_daily(sid)['snapshot']
        value=self.data.read_index_calculations(sid,snapshot['snapshot_id'],FORMULA_VERSION)
        for ref in (value['daily']['rows'][0]['input_ref'], value['performance']['day_5']['input_ref']):
            original=ref['snapshot_id'];ref['snapshot_id']='0'*64
            with self.assertRaises(ValueError):compact_index(value)
            ref['snapshot_id']=original
        current=self.data.activity('current',sid,snapshot['snapshot_id'])
        activity=self.data.activity('calculations',sid,current['activity_id'],formula_for(sid))
        activity['series'][0]['rows'][0]['total']['input_ref']['activity_id']='0'*64
        with self.assertRaises(ValueError):compact_activity(activity)


    def test_overview_keeps_input_and_exact_summary_validation_without_period_calculation(self):
        from pmi.market_data.index_calculations import calculate_overview
        from pmi.market_data import SnapshotError
        sid = INDEX_IDS[0];snapshot = self.data.read_daily(sid)['snapshot']
        with patch('pmi.market_data.index_calculations._series', side_effect=AssertionError('overview must not compute hidden periods')):
            expected = calculate_overview(sid, snapshot, FORMULA_VERSION)
        for mutate in (lambda x: x['summary'].update(daily_change_pct=x['summary']['daily_change_pct']+'0'),
                       lambda x: x['bars'][0].update(low='999999999.00'),
                       lambda x: x['calendar_dates'].pop()):
            bad = deepcopy(snapshot);mutate(bad)
            with self.assertRaises(SnapshotError):calculate_overview(sid, bad, FORMULA_VERSION)
        self.assertEqual(expected, calculate_overview(sid, snapshot, FORMULA_VERSION))


    def test_overview_cache_does_not_satisfy_full(self):
        from collections import OrderedDict
        import pmi.market_data.compact_view as compact
        sid = INDEX_IDS[0]
        with patch.object(compact, '_CACHE', OrderedDict()), patch.object(compact, '_cache_bytes', 0):
            overview = self.data.read_index_view(sid, FORMULA_VERSION, 'overview')
            self.assertNotIn('daily', overview['calculations'])
            with patch('pmi.market_data.index_calculations.calculate', side_effect=RuntimeError('full calculation required')):
                with self.assertRaisesRegex(RuntimeError, 'full calculation required'):
                    self.data.read_index_view(sid, FORMULA_VERSION, 'full')


    def price_parameters(self, sid, detail='overview', **more):
        current = next(item['price'] for item in self.data.market_versions()['indices'] if item['index_id']==sid)
        return {'detail':detail, 'snapshot_id':current['publication_id'], 'observation_id':current['observation_id'],
                'formula_version':FORMULA_VERSION, **more}

    def price_reply(self, sid, detail='overview', **more):
        return self.get(f'/api/index-series/{sid}/view?'+urlencode(self.price_parameters(sid,detail,**more)))

    def activity_parameters(self, sid, detail='range', **more):
        versions=self.data.market_versions()
        current=next(item['activity'] for item in versions['indices' if sid in INDEX_IDS else 'markets']
                     if item.get('index_id',item.get('series_id'))==sid)
        key='price_snapshot_id' if sid in INDEX_IDS else 'anchor_date'
        return {'detail':detail,'activity_id':current['publication_id'],'observation_id':current['observation_id'],
                key:current['binding'],'formula_version':formula_for(sid),**more}

    def test_all_price_ranges_equal_full_financial_calculation_without_originals(self):
        for sid in INDEX_IDS:
            snapshot=self.data.read_daily(sid)['snapshot']
            expected=self.data.read_index_calculations(sid,snapshot['snapshot_id'],FORMULA_VERSION)
            with patch.object(Originals,'get',side_effect=AssertionError('normal reads must be SQL only')):
                for frequency in ('daily','weekly','monthly'):
                    reply=self.price_reply(sid,'range',start=snapshot['calendar_dates'][0],end=snapshot['calendar_dates'][-1],frequency=frequency,ma='5,20')
                    self.assertEqual(reply.status,200,reply.body[:1000])
                    actual=reply.json()['series']
                    wanted={**expected[frequency], 'rows':[{**row,'ma':[x for x in row['ma'] if x['parameters']['period'] in ('5','20')]} for row in expected[frequency]['rows']]}
                    self.assertEqual(actual,wanted)

    def test_all_activity_ranges_equal_full_and_keep_binding(self):
        for sid in (*INDEX_IDS,TWO_MARKET,MARKET):
            parameters=self.activity_parameters(sid)
            snapshot=self.data.activity('fixed',sid,parameters['activity_id'])
            old=self.data.activity('calculations',sid,parameters['activity_id'],formula_for(sid))
            for frequency in (('daily','weekly','monthly') if sid in INDEX_IDS else ('daily',)):
                for field in (('amount','volume') if sid in INDEX_IDS else ('amount',)):
                    query={**parameters,'start':snapshot['calendar_dates'][0],'end':snapshot['calendar_dates'][-1],
                           'frequency':frequency,'field':field,'ma':'5,20'}
                    with patch.object(Originals,'get',side_effect=AssertionError('no original reads')):
                        reply=self.get(f'/api/market-activity/{sid}/view?'+urlencode(query),activity=True)
                    self.assertEqual(reply.status,200,reply.body[:1000])
                    expected=next(x for x in old['series'] if x['frequency']==frequency and x['field']==field)
                    expected={**expected,'rows':[{**row,'ma':[x for x in row['ma'] if x['parameters']['period'] in ('5','20')]} for row in expected['rows']]}
                    self.assertEqual(reply.json()['series'],expected)
                    self.assertEqual(reply.json()['price_snapshot_id'],snapshot['price_snapshot_id'])

    def test_overview_matches_full_performance_and_returns_bounded_bars(self):
        for sid in INDEX_IDS:
            snapshot=self.data.read_daily(sid)['snapshot']
            expected=self.data.read_index_calculations(sid,snapshot['snapshot_id'],FORMULA_VERSION)
            reply=self.price_reply(sid)
            self.assertEqual(reply.status,200,reply.body[:1000]);value=reply.json()
            self.assertEqual(value['performance'],expected['performance'])
            self.assertEqual(value['summary'],snapshot['summary'])
            self.assertLess(len(value['bars']),len(snapshot['bars']))
            self.assertEqual(value['bars'],[{key:bar[key] for key in ('trade_date','open','high','low','close')}
                for bar in snapshot['bars'] if value['returned_range']['start']<=bar['trade_date']<=value['returned_range']['end']])
            self.assertNotIn('evidence',value);self.assertNotIn('snapshot',value)

    def test_boundary_rejects_before_value_calculation(self):
        sid=INDEX_IDS[0];valid=self.price_parameters(sid)
        with patch.object(type(self.data),'price_view',side_effect=AssertionError('reject before use case')):
            for query in ('','formula_version=unknown','formula_version='+FORMULA_VERSION+'&extra=1',urlencode({**valid,'extra':'1'})):
                self.assertEqual(self.get(f'/api/index-series/{sid}/view?'+query).status,422)
            self.assertEqual(self.get(f'/api/index-series/{sid}/view?'+urlencode(valid),**{'x-wolf-expected-config':'0'*64}).status,409)
            self.assertEqual(self.get(f'/api/index-series/{sid}/view?'+urlencode(valid),origin='https://example.invalid').status,403)

    def test_cache_keys_cover_range_ma_and_health_not_mutable_return_values(self):
        sid=INDEX_IDS[0];first=self.price_reply(sid).json();changed=self.price_reply(sid).json()
        changed['performance']['day_5']['value']='999.00'
        with patch.object(self.data._storage_views,'price_overview',side_effect=AssertionError('same fixed version should reuse')):
            self.assertEqual(self.price_reply(sid).json(),first)
        path=f'/api/index-series/{sid}/view?'+urlencode(self.price_parameters(sid))
        with patch.object(self.data._maintenance,'require_available',side_effect=StorageError('storage_quarantined')):
            reply=self.get(path);self.assertEqual(reply.status,409)
            self.assertEqual(reply.json()['detail']['code'],'storage_quarantined')
        snapshot=self.data.read_daily(sid)['snapshot'];start,end=snapshot['calendar_dates'][-30],snapshot['calendar_dates'][-1]
        one=self.price_reply(sid,'range',start=start,end=end,frequency='daily',ma='5').json()
        two=self.price_reply(sid,'range',start=start,end=end,frequency='daily',ma='20').json()
        self.assertEqual(one['ma_periods'],[5]);self.assertEqual(two['ma_periods'],[20]);self.assertNotEqual(one['series'],two['series'])

    def test_periodic_integrity_failure_blocks_cached_values_until_explicit_full_release(self):
        sid=INDEX_IDS[0];view=self.price_reply(sid).json();database=Database(self.root/'data')
        stored=database.path.read_bytes();database_info=database.path.stat();query=f'/api/index-series/{sid}/view?'+urlencode(self.price_parameters(sid));object_id=view['sources'][0]['object_id'];path=database.root/'objects'/object_id
        raw,info=path.read_bytes(),path.stat()
        try:
            path.write_bytes(bytes([raw[0]^1])+raw[1:]);os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
            # 已批准校验前移：普通读取不读原件；维护发现后立即持续隔离所有缓存。
            with self.assertRaises(StorageError):Integrity(database).run('full',semantic_check=lambda c:check_all(database,c))
            self.assertEqual(self.get(query).status,409)
            path.write_bytes(raw);os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
            self.assertEqual(self.get(query).status,409)
            Integrity(database).run('full',semantic_check=lambda c:check_all(database,c),release_quarantine=True)
            self.assertEqual(self.price_reply(sid).json(),view)
        finally:
            path.write_bytes(raw);os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
            database.path.write_bytes(stored);os.utime(database.path,ns=(database_info.st_atime_ns,database_info.st_mtime_ns));self.data._range_cache.clear()


if __name__=='__main__':unittest.main()
