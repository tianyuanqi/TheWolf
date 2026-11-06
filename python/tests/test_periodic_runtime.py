"""周期协调与调度的隔离验证；只用合成价格、来源替身与可控时钟。"""
from datetime import datetime
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from pmi.market_data import MarketData, ActivityOptions, SnapshotError
from pmi.market_data.periodic_budget import PeriodicOptions, BudgetError, initialize, MIB, INDEX_IDS
from pmi.market_data.index_history_calendar import SHANGHAI, complete_window
from pmi.periodic_scheduler import Scheduler
from test_periodic_budget import Clock


class SchedulerTests(unittest.TestCase):
    def test_start_seven_sleep_and_stop(self):
        clock = Clock('2026-10-29T06:00:00'); stop = threading.Event(); calls = []
        scheduler = Scheduler(lambda: calls.append(clock()), stop, clock)
        self.assertTrue(scheduler.tick()); self.assertFalse(scheduler.tick())
        clock.set('2026-10-29T07:00:00'); self.assertTrue(scheduler.tick()); self.assertFalse(scheduler.tick())
        clock.set('2026-11-15T10:00:00'); self.assertTrue(scheduler.tick()); self.assertEqual(len(calls), 3)
        clock.set('2026-10-29T10:00:00'); self.assertFalse(scheduler.tick())
        stop.set(); clock.set('2026-12-01T10:00:00'); self.assertFalse(scheduler.tick())

    def test_busy_manual_entry_defers_without_losing_daily_check(self):
        results = iter((False, True))
        scheduler = Scheduler(lambda: next(results), threading.Event(), Clock())
        self.assertFalse(scheduler.tick())
        self.assertTrue(scheduler.tick())
        self.assertFalse(scheduler.tick())

    def test_concurrent_ticks_only_one(self):
        entered = threading.Event(); release = threading.Event(); calls = []
        def check(): calls.append(1); entered.set(); release.wait(2)
        scheduler = Scheduler(check, threading.Event(), Clock())
        worker = threading.Thread(target=scheduler.tick); worker.start()
        try:
            self.assertTrue(entered.wait(1)); self.assertFalse(scheduler.tick())
        finally: release.set(); worker.join(2)
        self.assertEqual(calls, [1])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wolf-periodic-runtime-', dir='/private/tmp')
        self.root = Path(self.temp.name); self.price = self.root/'price'; self.act = self.root/'activity'
        self.price.mkdir(); self.act.mkdir(); initialize(self.price, self.act)
        self.data = MarketData(self.price, {x: True for x in INDEX_IDS}, activity_options=ActivityOptions(self.act), periodic_options=PeriodicOptions())
        self.clock = Clock(); self.data._periodic.budget.clock = self.clock
    def tearDown(self):
        self.assertTrue(self.data.close_updates()); self.temp.cleanup()

    def test_unknown_year_no_fetch_and_get_no_writes(self):
        self.clock.set('2027-01-02T07:00:00')
        before = (self.price/'overview-periodic-ledger.json').read_bytes()
        with patch('pmi.market_data.index_series_fetch.fetch_bounded', side_effect=AssertionError('network forbidden')):
            self.data.periodic_check(INDEX_IDS, 'c', 'i')
        self.assertEqual(self.data.periodic_status()['reason'], 'calendar_uncovered')
        self.assertEqual(before, (self.price/'overview-periodic-ledger.json').read_bytes())

    def test_covered_holiday_zero_requests_and_restart_dedupe(self):
        calls = []
        dates = complete_window(self.clock()).dates
        def read(_, code, snapshot_id=None): return {'format': 'v2', 'snapshot': {'calendar_dates': dates}}
        with patch.object(MarketData, 'read_daily', read), patch.object(MarketData, '_update', side_effect=AssertionError('no update')):
            self.data.periodic_check(INDEX_IDS, 'c', 'i'); self.data.periodic_check(INDEX_IDS, 'c', 'i')
        ledger = self.data._periodic.budget.read()
        self.assertEqual(ledger['attempts'], []); self.assertEqual(len(ledger['batches']), 1)
        other = MarketData(self.price, {x:True for x in INDEX_IDS}, activity_options=ActivityOptions(self.act), periodic_options=PeriodicOptions())
        other._periodic.budget.clock = self.clock
        with patch.object(MarketData, 'read_daily', read): other.periodic_check(INDEX_IDS, 'c', 'new-instance')
        self.assertEqual(len(other._periodic.budget.read()['batches']), 1)
        self.assertTrue(other.close_updates())

    def test_manual_and_automatic_cannot_bypass_same_lease(self):
        lease = self.data._periodic.budget.begin([('reserved', MIB)], target='test', automatic=False)
        try:
            with self.assertRaisesRegex(BudgetError, 'periodic_busy'): self.data.update(INDEX_IDS[0])
            with self.assertRaisesRegex(SnapshotError, 'periodic_lease_required'): self.data._update(INDEX_IDS[0])
            self.data.periodic_check(INDEX_IDS, 'c', 'i')
            self.assertEqual(self.data._periodic.budget.read()['attempts'], [])
        finally: lease.finish()

    def test_real_manual_writer_defers_daily_check_until_released(self):
        entered, release = threading.Event(), threading.Event()
        def fetch(*args, **kwargs):
            entered.set()
            if not release.wait(5): raise AssertionError('release missing')
            raise SnapshotError('source_fetch_failed')
        calls = []
        def check():
            result = self.data.periodic_check((INDEX_IDS[0],), 'c', 'i')
            calls.append(result)
            return result
        scheduler = Scheduler(check, threading.Event(), self.clock)
        try:
            with patch('pmi.market_data.index_series_update.fetch_bounded', fetch):
                self.data.update(INDEX_IDS[0]); self.assertTrue(entered.wait(2))
                self.assertFalse(scheduler.tick()); self.assertIsNone(scheduler.checked_day)
                release.set(); self.assertTrue(self.data.wait_updates(5))
                for worker in self.data._periodic._watchers: worker.join(3)
                self.assertTrue(scheduler.tick()); self.assertFalse(scheduler.tick())
                self.assertEqual(calls, [False, True])
                batches = self.data._periodic.budget.read()['batches']
                self.assertEqual(len(batches), 2)
                self.assertTrue(batches[1]['target'].startswith('overview:'))
        finally:
            release.set()

    def test_unsafe_read_is_not_retried_as_lock_contention(self):
        from pmi.market_data import ReadUnavailable
        scheduler = Scheduler(lambda: self.data.periodic_check(INDEX_IDS, 'c', 'i'), threading.Event(), self.clock)
        with patch.object(MarketData, 'read_daily', side_effect=ReadUnavailable('unsafe database')):
            self.assertTrue(scheduler.tick()); self.assertFalse(scheduler.tick())
        self.assertEqual(self.data.periodic_status()['reason'], 'periodic_plan_unavailable')
        self.assertEqual(self.data._periodic.budget.read()['attempts'], [])

    def test_manual_market_cannot_fetch_old_window(self):
        from pmi.market_data.activity.model import TWO_MARKET
        data = MarketData(self.price, {}, activity_options=ActivityOptions(self.act, write_series=(TWO_MARKET,)), periodic_options=PeriodicOptions())
        data._periodic.budget.clock = self.clock
        try:
            with self.assertRaisesRegex(ValueError, 'invalid_activity_parameters'):
                data.activity('start', TWO_MARKET, 'old-window', {'anchor_date':'2026-10-29','expected_activity_id':None},'c','i')
            self.assertEqual(data._periodic.budget.read()['attempts'], [])
        finally:
            self.assertTrue(data.close_updates())

    def test_activity_plan_failure_does_not_block_price(self):
        from pmi.market_data.activity.model import ActivityError
        data = MarketData(self.price, {x:True for x in INDEX_IDS}, activity_options=ActivityOptions(
            self.act, write_series=(INDEX_IDS[0],), startup_series=(INDEX_IDS[0],)), periodic_options=PeriodicOptions())
        data._periodic.budget.clock = self.clock
        calls = []
        def updated(_, code, **kwargs):
            calls.append(code)
            return {'stage':'completed','result':'business_changed'}
        try:
            with patch.object(MarketData,'read_daily',return_value=None), patch.object(MarketData,'_update',updated), patch.object(MarketData,'status',return_value={'stage':'completed','result':'business_changed'}), patch.object(data._activity_runtime,'guard',side_effect=ActivityError('source_withdrawn')):
                data.periodic_check(INDEX_IDS,'c','i')
                self.assertEqual(calls,list(INDEX_IDS))
                self.assertEqual(data.periodic_status()['reason'],'periodic_update_failed')
        finally:
            self.assertTrue(data.close_updates())

    def test_scope_cannot_enable_legacy_or_extra_market(self):
        with self.assertRaises(ValueError):
            MarketData(self.price, {'002245':True}, activity_options=ActivityOptions(self.act), periodic_options=PeriodicOptions())
        with self.assertRaises(ValueError):
            MarketData(self.price, {}, activity_options=ActivityOptions(self.act, write_series=('unknown-market',)), periodic_options=PeriodicOptions())

    def test_missing_ledger_constructor_never_creates(self):
        (self.price/'overview-periodic-ledger.json').unlink()
        with self.assertRaises(FileNotFoundError):
            MarketData(self.price, {}, activity_options=ActivityOptions(self.act), periodic_options=PeriodicOptions())
        self.assertFalse((self.price/'overview-periodic-ledger.json').exists())


class FullBatchTests(unittest.TestCase):
    def test_normal_twelve_requests_failure_keeps_old_and_next_day(self):
        from periodic_fixture import seed, transport
        from pmi.market_data.activity.model import TWO_MARKET
        with tempfile.TemporaryDirectory(prefix='wolf-periodic-chain-',dir='/private/tmp') as folder:
            root=Path(folder);seed(root)
            data=MarketData(root/'data',{x:True for x in INDEX_IDS},activity_options=ActivityOptions(root/'activity',write_series=(*INDEX_IDS,TWO_MARKET),startup_series=(*INDEX_IDS,TWO_MARKET)),periodic_options=PeriodicOptions())
            clock=Clock('2026-10-30T07:00:00');data._periodic.budget.clock=clock
            try:
                with transport(data):data.periodic_check(INDEX_IDS,'config','instance')
                status=data.periodic_status()
                self.assertEqual(status['reason'],None,status)
                self.assertEqual(status['daily'],{'requests':12,'bytes':10*MIB+2*65536})
                self.assertEqual(status['market_anchor_date'],'2026-10-30')
                for sid in INDEX_IDS:self.assertEqual(data.read_daily(sid)['snapshot']['window']['end'],'2026-10-29')
                with transport(data):data.periodic_check(INDEX_IDS,'config','new-instance')
                self.assertEqual(data.periodic_status()['daily']['requests'],12)
                old=data.read_daily(INDEX_IDS[0])['snapshot']['snapshot_id']
                clock.set('2026-10-31T07:00:00')
                with transport(data,lambda:{'fail_ids':[INDEX_IDS[0]]}):data.periodic_check(INDEX_IDS,'config','instance')
                self.assertEqual(data.read_daily(INDEX_IDS[0])['snapshot']['snapshot_id'],old)
                self.assertEqual(data.periodic_status()['reason'],'periodic_update_failed')
                self.assertEqual(data.periodic_status()['daily']['requests'],11)
                self.assertEqual(data.periodic_status()['monthly']['requests'],23)
                before=data._periodic.budget.path.read_bytes()
                clock.set('2027-01-02T07:00:00')
                with transport(data):data.periodic_check(INDEX_IDS,'config','instance')
                self.assertEqual(data.periodic_status()['reason'],'calendar_uncovered')
                self.assertEqual(data._periodic.budget.path.read_bytes(),before)
                self.assertEqual(data.read_daily(INDEX_IDS[0])['snapshot']['snapshot_id'],old)
            finally:self.assertTrue(data.close_updates())


class HttpBoundaryTests(unittest.TestCase):
    def test_actual_dispatch_identity_get_no_writes_and_shared_manual_budget(self):
        from pmi.api import create_app
        from pmi.service_config import ServiceConfig
        from http_test_support import ReadClient, disk
        from pmi.market_data.activity.model import TWO_MARKET
        with tempfile.TemporaryDirectory(prefix='wolf-periodic-http-',dir='/private/tmp') as folder:
            root=Path(folder); price=root/'data';act=root/'activity';price.mkdir();act.mkdir();initialize(price,act)
            config=ServiceConfig(price,18080,('http://127.0.0.1:18081',),index_write_ids=(INDEX_IDS[0],),activity_options=ActivityOptions(act,write_series=(TWO_MARKET,)),periodic_options=PeriodicOptions())
            client=ReadClient.__new__(ReadClient);client.config=config;client.app=create_app(config)
            client.headers={'host':config.authority,'origin':config.allowed_origins[0],'x-wolf-client':'1','x-wolf-expected-instance':client.app.state.boundary.instance,'x-wolf-expected-config':config.index_config_id}
            try:
                before=disk(root)
                reply=client.request('/api/overview-update/status');self.assertEqual(reply.status,200,reply.body)
                self.assertEqual(disk(root),before)
                with patch.object(MarketData,'periodic_status',side_effect=AssertionError('identity before read')):
                    reply=client.request('/api/overview-update/status',headers={'x-wolf-expected-config':'a'*64});self.assertEqual(reply.status,409)
                lease=config.market_data._periodic.budget.begin([('pending',MIB)],target='test',automatic=False)
                try:
                    headers={'content-type':'application/json','x-wolf-request-id':'blocked-price'}
                    reply=client.request('/api/index-series/'+INDEX_IDS[0]+'/update','POST',headers=headers,body=b'{}');self.assertEqual(reply.status,409,reply.body)
                    parameters={'anchor_date':config.market_data._periodic.budget.day(),'expected_activity_id':None}
                    reply=client.request('/api/market-activity/'+TWO_MARKET+'/update','POST',headers={**headers,'x-wolf-expected-config':config.activity_config_id,'x-wolf-request-id':'blocked-market'},body=json.dumps(parameters).encode());self.assertEqual(reply.status,409,reply.body)
                    self.assertEqual(config.market_data._periodic.budget.read()['attempts'],[])
                finally:lease.finish()
                with self.assertRaises(ValueError):MarketData(price,{INDEX_IDS[0]:True},activity_options=ActivityOptions(act))
            finally:self.assertTrue(client.app.state.updates.close())


class ActivityLockTests(unittest.TestCase):
    def test_periodic_writer_waits_for_reader_and_can_cancel(self):
        from pmi.market_data.activity.store import Store
        from pmi.market_data.activity.model import ActivityError
        with tempfile.TemporaryDirectory(prefix='wolf-periodic-lock-', dir='/private/tmp') as name:
            store=Store(Path(name)); cancel=threading.Event(); entered=threading.Event(); attempted=threading.Event(); failures=[]
            with store.lock(write=True): pass
            def writer():
                attempted.set()
                try:
                    with store.lock(write=True,cancel=cancel):entered.set()
                except ActivityError as error:failures.append(error.code)
            with store.lock(write=False):
                worker=threading.Thread(target=writer);worker.start();self.assertTrue(attempted.wait(1))
                worker.join(.1);self.assertFalse(entered.is_set())
            worker.join(2);self.assertTrue(entered.is_set());self.assertEqual(failures,[])
            entered.clear();attempted.clear()
            with store.lock(write=False):
                worker=threading.Thread(target=writer);worker.start();self.assertTrue(attempted.wait(1));cancel.set();worker.join(2)
            self.assertFalse(worker.is_alive());self.assertFalse(entered.is_set());self.assertEqual(failures,['activity_cancelled'])
