"""背景只读用例的时间、范围与固定保存；使用独立合成数据。"""
from copy import deepcopy
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from etf_flow_fixture import AT, END, configuration
from pmi.market_data.etf_flow.calendar import preceding_window
from pmi.market_data.etf_flow.context import capture, select, validate
from pmi.market_data.etf_flow.model import Configuration, FlowError
from pmi.market_data.index_calculations import INDEX_IDS
from pmi.market_data.activity.model import TWO_MARKET
import test_etf_flow_repository as repository_fixture


class ContextTests(unittest.TestCase):
    def test_actual_existing_price_store_and_calculation_are_read_only(self):
        from pmi.market_data import MarketData
        from pmi.market_data.index_catalog import INDICES
        from pmi.market_data.index_series_contract import build_manifest
        from pmi.market_data.storage import index_store as index_series_store
        from sqlite_fixture import price_writer as writer_lock, initialize as initialize_sqlite
        from test_index_series_contract import originals, WINDOW
        from test_index_series_runtime import state
        with tempfile.TemporaryDirectory(prefix='etf-context-test-', dir='/private/tmp') as folder:
            root=Path(folder); initialize_sqlite(root); index=next(x for x in INDICES if x.index_id in INDEX_IDS)
            raw=configuration();raw['pool_versions'][0]['members'][0]['index_id']=index.index_id
            items=originals(index,WINDOW)
            with writer_lock(root):
                index_series_store.prepare_directories(root,index)
                index_series_store.publish(root,index,WINDOW,build_manifest(index,WINDOW,items),items,state(index))
            data=MarketData(root,{})
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            end=data.read_daily(index.index_id)['snapshot']['window']['end']
            with patch('socket.socket.connect',side_effect=AssertionError('不得取数')):
                background=capture(data,Configuration.parse(raw),end,AT)
            selected=select(background,end,{index.index_id})
            self.assertEqual(selected['indices'][0]['snapshot_id'],data.read_daily(index.index_id)['snapshot']['snapshot_id'])
            self.assertEqual(selected['indices'][0]['return_1'],'0.00')
            self.assertEqual(selected['indices'][0]['return_5'],'0.00')
            self.assertEqual(selected['reason'],'context_partial')
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertTrue(data.close_updates())
        self.assertFalse(root.exists())

    def test_previous_twenty_excludes_today_and_market_scope_is_explicit(self):
        raw = configuration(); index = sorted(INDEX_IDS)[0]
        raw['pool_versions'][0]['members'][0]['index_id'] = index
        config = Configuration.parse(raw)
        dates = preceding_window(END, 21)
        class Parent:
            activity_scope_id = 'a'*64
            activity_market_anchors = {'sse_szse': END, 'sse_szse_bse': None}
            def read_daily(self, identity):
                self.identity = identity
                return {'format': 'v2', 'snapshot': {'snapshot_id': 'b'*64}}
            def read_index_calculations(self, identity, snapshot, formula):
                return {'daily': {'rows': [{'end': on, 'close': '200' if on == END else '100',
                    'change_pct': {'value': '100.00' if on == END else '0.00'}} for on in dates]}}
            def activity(self, action, series, *args):
                if series != TWO_MARKET: raise AssertionError('不得暗换范围')
                if action == 'current': return {'activity_id': 'c'*64}
                if action != 'calculations': raise AssertionError('不得调用写入')
                return {'series': [{'field': 'amount', 'frequency': 'daily', 'rows': [
                    {'end': on, 'total': {'value': '200' if on == END else '100'}} for on in dates]}]}
        parent = Parent()
        frozen = capture(parent, config, END, AT)
        result = select(frozen, END, {index})
        self.assertEqual(parent.identity, index)
        self.assertEqual(result['indices'][0]['return_5'], '100.00')
        self.assertEqual(result['market']['ratio_20'], '2')
        self.assertEqual(result['market']['scope_label'], '沪深')
        self.assertEqual(result['market']['input_basis'], 'posthoc_context')
        self.assertIsNone(select(frozen, dates[-2], {index})['market']['ratio_20'])
        self.assertEqual(select(frozen, '2026-11-05', {index})['indices'], [])
        self.assertEqual(select(frozen, END, set())['indices'], [])
        bad = deepcopy(frozen); bad['rows'][-1]['market']['scope_label'] = '沪深北'
        with self.assertRaises(FlowError): validate(bad)

    def test_missing_background_does_not_block_and_snapshot_reopens_frozen_context(self):
        from pmi.market_data import ReadUnavailable
        class Unavailable:
            activity_scope_id = 'a'*64
            @property
            def activity_market_anchors(self): raise ReadUnavailable('isolated background unavailable')
        missing = capture(Unavailable(), Configuration.parse(configuration()), END, AT)
        self.assertEqual(select(missing, END, set()), {'indices': [], 'market': None, 'reason': 'context_not_available'})
        fixture = repository_fixture.RepositoryTests(methodName='test_initial_history_not_original_signal_and_read_does_not_mutate')
        fixture.setUp(); self.addCleanup(fixture.tearDown)
        context = {'format': 'etf-flow-context-v1', 'rows': [{'date': END, 'indices': [], 'market': {
            'series_id': TWO_MARKET, 'activity_id': 'a'*64, 'formula_version': 'etf-flow-context-v1',
            'date': END, 'scope_label': '沪深', 'turnover': '200', 'ratio_20': '2',
            'input_basis': 'posthoc_context', 'calculated_at': AT}, 'reason': None}]}
        with fixture.store.writer():
            snapshot = fixture.repo.publish(fixture.config, fixture.evidence, fixture.inputs, end=END,
                selection_at=AT, operation_key='c'*64, expected=None, context=context)
        from pmi.market_data.etf_flow.view import build
        before = build(fixture.repo, snapshot, mode='current', period=60, end=None, group=None, server_day='2026-11-05')
        self.assertEqual(before['summary']['evaluation']['amount'], '40')
        self.assertEqual(before['context']['market']['turnover'], '200')
        fixture.publish('next-without-background')
        after = build(fixture.repo, snapshot, mode='current', period=60, end=None, group=None, server_day='2026-11-05')
        self.assertEqual(before, after)


if __name__ == '__main__': unittest.main()
