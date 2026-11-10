"""A价格计算的确定性、历史兼容及实际应用边界；只用隔离合成数据。"""
from copy import deepcopy
from datetime import datetime, date, timezone
from decimal import localcontext, Inexact
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmi.market_data import MarketData, SnapshotError
from pmi.market_data.index_catalog import INDICES
from pmi.market_data.index_calculations import (calculate, FORMULA_VERSION, PERIODS, INDEX_IDS,
                                               _series, _performance)
from pmi.market_data.index_history_calendar import complete_window, period_calendar, CALENDAR_VERSION
from pmi.market_data.price_formulas import change_pct_v1, close_sma_v1
from pmi.market_data.index_series_contract import summarize, build_manifest
from pmi.market_data.storage import index_store as store
from sqlite_fixture import price_writer as writer_lock, initialize as initialize_sqlite
from pmi.http_contract import response_value
from test_index_series_http_contract import synthetic_view
from test_index_series_contract import originals, WINDOW
from test_index_series_runtime import state
from http_test_support import ReadClient, disk

# 从实施前冻结源码独立构建的六个合成manifest摘要，不从本轮实现倒算。
GOLDEN = ['d80e94ed2801b00bc2dd1a5cbf4919e54574441ae2acb0dc75f2a38862cb57a5',
          '54b3f0261652c8ff8c99744b4cec0d8cecc77ea81068aa2ad04e87fe8901268f',
          '5782fd653e89402b83ef1c1962c01a69ddc7061055360ae48def746e4b071715',
          '0afdc9083b0afcb1025ec5c8865c8a55f0b2068d02e1f014ec774b47067b25d9',
          '2591794d720ca13e057eb5955b3f441d9cef9dcbb7e18dfe7cf69c8fb77c61d0',
          'f137a93d11a911564b0720a4aefd9a18baf33161167b0573b65afe0663975588']


def price(day, close):
    return {'trade_date':day, 'open':close, 'high':close, 'low':close, 'close':close, 'evidence_refs':[]}


def small(rows):
    """纯函数边界用的人工小样本；不发布为三年生产快照。"""
    return {'snapshot_id':'a'*64, 'bars':rows, 'calendar_version':CALENDAR_VERSION}


class FormulaTests(unittest.TestCase):
    def test_rounding_negative_zero_and_context(self):
        for current, previous, expected in [('1.00005','1','0.01'),('0.99995','1','-0.01'),
                                             ('0.999999','1','0.00'),('2','1','100.00')]:
            self.assertEqual(change_pct_v1(current, previous),expected)
        self.assertEqual(close_sma_v1(['1.0000','1.0001']),'1.0001')
        with localcontext() as context:
            context.prec=3; context.traps[Inexact]=True
            self.assertEqual(change_pct_v1('1','3'),'-66.67')
            self.assertEqual(close_sma_v1(['1','2','2']),'1.6667')
        for value in ['NaN','Infinity','0','-1',1.1]:
            with self.subTest(value=value),self.assertRaises(SnapshotError):change_pct_v1('1',value)

    def test_shared_formula_and_old_manifest_identity_all_six(self):
        for index,golden in zip(INDICES,GOLDEN):
            self.assertEqual(synthetic_view(index)['snapshot']['snapshot_id'],golden)
        with patch('pmi.market_data.index_series_contract.change_pct_v1',wraps=change_pct_v1) as formula:
            rows=[price('2026-01-05','100.00'),price('2026-01-06','100.01')]
            self.assertEqual(summarize(rows)['daily_change_pct'],'0.01');formula.assert_called_once()
        for close in ['100.00','100.01','99.99']:
            rows=[price('2026-01-05','100.00'),price('2026-01-06',close)]
            result=_series(INDICES[1].index_id,small(rows),'daily')
            # 输出字符串直接逐位断言，不先转float或重新舍入。
            self.assertEqual(result['rows'][-1]['change_pct']['value'],summarize(rows)['daily_change_pct'])

    def test_window_counts_and_n_plus_one(self):
        rows=[price(f'2026-01-{day:02d}',str(day)+'.00') for day in [5,6,7,8,9,12]]
        self.assertIsNone(_performance('test',small(rows[:5]))['day_5']['value'])
        self.assertEqual(_performance('test',small(rows))['day_5']['value'],'140.00')
        self.assertEqual(_performance('test',small(rows))['day_5']['input_ref']['start'],'2026-01-05')
        self.assertEqual(_performance('test',small(rows))['year_1']['reason'],'missing_year_baseline')
        series=_series('test',small(rows),'daily')
        self.assertEqual(series['rows'][4]['ma'][0]['value'],'7.0000')
        self.assertIsNone(series['rows'][3]['ma'][0]['value'])

    def test_natural_year_leap_day_and_holiday_fallback(self):
        rows=[price('2023-02-27','80.00'),price('2023-02-28','100.00'),price('2024-02-29','110.00')]
        value=_performance('test',small(rows))['year_1']
        self.assertEqual((value['value'],value['input_ref']['start']),('10.00','2023-02-28'))
        rows=[price('2023-10-27','50.00'),price('2023-10-30','200.00'),price('2024-10-28','100.00')]
        self.assertEqual(_performance('test',small(rows))['year_1']['value'],'100.00')

    def test_truncated_and_unfinished_week_month_preserve_close(self):
        rows=[price('2026-01-08','10.00'),price('2026-01-09','20.00'),price('2026-01-12','30.00')]
        series=_series('test',small(rows),'weekly');a,b=series['rows']
        self.assertEqual((a['open'],a['high'],a['low'],a['close']),('10.00','20.00','10.00','20.00'))
        self.assertIn('window_start_truncated',a['incomplete_reasons'])
        self.assertIn('period_in_progress',b['incomplete_reasons'])
        self.assertEqual(b['change_pct']['value'],'50.00')
        self.assertIsNone(a['change_pct']['value'])
        self.assertEqual((a['period_start'],a['period_end']),('2026-01-05','2026-01-11'))
        # 首段截断但期末收盘有效；第五周MA包含首段和未完成末段。
        rows += [price('2026-01-16','40.00'),price('2026-01-23','60.00'),price('2026-01-30','80.00'),price('2026-02-02','100.00')]
        self.assertEqual(_series('test',small(rows),'weekly')['rows'][-1]['ma'][0]['value'],'60.0000')
        self.assertIsNone(period_calendar(date(2026,12,28),date(2027,1,3),CALENDAR_VERSION))
        unknown=_series('test',small([price('2026-12-31','10.00')]),'weekly')['rows'][0]
        self.assertFalse(unknown['complete']);self.assertEqual(unknown['incomplete_reasons'],['calendar_unknown'])
        rows=[price('2026-01-30','20.00'),price('2026-02-02','30.00')]
        monthly=_series('test',small(rows),'monthly')['rows']
        self.assertEqual(monthly[1]['change_pct']['value'],'50.00')
        self.assertEqual(monthly[0]['period_end'],'2026-01-31')

    def test_full_fixed_snapshot_replay_capabilities_and_invalid_inputs(self):
        for index in [i for i in INDICES if i.index_id in INDEX_IDS]:
            snapshot=synthetic_view(index)['snapshot'];before=deepcopy(snapshot)
            result=calculate(index.index_id,snapshot,FORMULA_VERSION)
            self.assertEqual(snapshot,before)
            self.assertEqual(result['daily']['rows'][-1]['change_pct']['value'],snapshot['summary']['daily_change_pct'])
            self.assertEqual(result,calculate(index.index_id,snapshot,FORMULA_VERSION))
            self.assertEqual(response_value('IndexSeriesCalculations',result),result)
            for frequency,available in [('daily',PERIODS),('weekly',PERIODS[:6]),('monthly',PERIODS[:4])]:
                self.assertEqual(tuple(x['period'] for x in result[frequency]['ma_availability'] if x['available']),available)
                for row in result[frequency]['rows']:
                    self.assertEqual(row['input_ref']['snapshot_id'],snapshot['snapshot_id'])
                    for value in [row['change_pct'],*row['ma']]:
                        self.assertEqual(value['input_ref']['snapshot_id'],snapshot['snapshot_id'])
                        self.assertEqual(value['reason'] is None,value['value'] is not None)
        index=INDICES[1];snapshot=synthetic_view(index)['snapshot']
        for mutate in [lambda v:v['summary'].update(daily_change_pct='1.23'),
                       lambda v:v['bars'][0].update(close='NaN'),lambda v:v['calendar_dates'].pop()]:
            bad=deepcopy(snapshot);mutate(bad)
            with self.assertRaises(SnapshotError):calculate(index.index_id,bad,FORMULA_VERSION)
        with self.assertRaises(SnapshotError):calculate(index.index_id,snapshot,'future')


class ApplicationTests(unittest.TestCase):
    def test_fixed_http_readonly_rejection_and_current_independence(self):
        with tempfile.TemporaryDirectory(prefix='thewolf-a-unit-') as folder:
            root=Path(folder).resolve(); initialize_sqlite(root);index=INDICES[1];items=originals(index,WINDOW)
            with writer_lock(root):
                store.prepare_directories(root,index)
                store.publish(root,index,WINDOW,build_manifest(index,WINDOW,items),items,state(index))
            data=MarketData(root,{});view=data.read_daily(index.index_id);sid=view['snapshot']['snapshot_id']
            client=ReadClient(root);client.headers['x-wolf-expected-config']=client.config.index_config_id
            base=f'/api/index-series/{index.index_id}/snapshots/{sid}/calculations'
            before=disk(root)
            with patch('socket.socket.connect',side_effect=AssertionError('network forbidden')):
                response=client.request(base+'?formula_version='+FORMULA_VERSION)
                self.assertEqual(response.status,200,response.body[:1000]);expected=response.json()
                self.assertEqual(response.headers['x-wolf-config'],client.config.index_config_id)
                for suffix in ['', '?formula_version=unknown','?formula_version='+FORMULA_VERSION+'&extra=1',
                               '?formula_version='+FORMULA_VERSION+'&formula_version='+FORMULA_VERSION]:
                    self.assertEqual(client.request(base+suffix).status,422)
                self.assertEqual(client.request(base+'?formula_version='+FORMULA_VERSION,headers={'x-wolf-expected-config':'0'*64}).status,409)
                self.assertEqual(client.request(base.replace(sid,'a'*64)+'?formula_version='+FORMULA_VERSION).status,404)
                self.assertEqual(client.request(base.replace(index.index_id,INDICES[0].index_id)+'?formula_version='+FORMULA_VERSION).status,422)
            self.assertEqual(disk(root),before)
            from market_overview_smoke import varied_originals
            items=varied_originals(index)
            with writer_lock(root):store.publish(root,index,WINDOW,build_manifest(index,WINDOW,items),items,state(index,"revised"))
            self.assertNotEqual(data.read_daily(index.index_id)['snapshot']['snapshot_id'],sid)
            self.assertEqual(data.read_index_calculations(index.index_id,sid,FORMULA_VERSION),expected)
        self.assertFalse(root.exists())

    def test_empty_root_no_creation(self):
        with tempfile.TemporaryDirectory(prefix='thewolf-a-empty-') as folder:
            root=Path(folder).resolve(); initialize_sqlite(root);before=disk(root);data=MarketData(root,{})
            self.assertIsNone(data.read_index_calculations(INDICES[1].index_id,'a'*64,FORMULA_VERSION))
            self.assertEqual(disk(root),before)
        self.assertFalse(root.exists())


if __name__=='__main__':unittest.main()
