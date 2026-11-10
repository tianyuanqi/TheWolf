"""周期预算隔离反例：可控时钟、跨周期、整批拒绝和异常退出。"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pmi.market_data.periodic_budget import Budget, BudgetError, PeriodicOptions, MIB, initialize
from pmi.market_data.index_history_calendar import SHANGHAI
from pmi.market_data.storage.database import Database
from pmi.market_data.storage import state as states


class Clock:
    def __init__(self, value='2026-10-30T07:00:00'):
        self.value = datetime.fromisoformat(value).replace(tzinfo=SHANGHAI)
    def __call__(self): return self.value
    def set(self, value): self.value = datetime.fromisoformat(value).replace(tzinfo=SHANGHAI)


class PeriodicBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wolf-periodic-unit-')
        self.root = Path(self.temp.name).resolve()
        self.price = self.root/'store'; self.activity = self.price
        self.price.mkdir(); Database(self.price).initialize(); initialize(self.price, self.activity)
        self.clock = Clock()
        self.options = PeriodicOptions()
        self.budget = Budget(self.price, self.activity, self.options, self.clock)

    def tearDown(self):
        if self.budget.active: self.budget.active.finish('test_cleanup')
        self.temp.cleanup()

    def test_whole_batch_rejected_without_charge(self):
        before = self.budget.path.read_bytes()
        with self.assertRaisesRegex(BudgetError, 'daily_exhausted'):
            self.budget.begin([('x',65536)]*81,target='x',automatic=True)
        self.assertEqual(self.budget.path.read_bytes(),before)

    def test_day_and_month_both_gate_requests_and_bytes(self):
        options = PeriodicOptions(daily_requests=2,daily_bytes=2*MIB,monthly_requests=3,monthly_bytes=3*MIB)
        budget = Budget(self.price,self.activity,options,self.clock)
        lease = budget.begin([('a',MIB),('b',MIB)],target='day1',automatic=False)
        lease.charge('a',MIB);lease.charge('b',MIB);lease.finish()
        with self.assertRaisesRegex(BudgetError,'daily_exhausted'):budget.begin([('x',MIB)],target='d',automatic=False)
        self.clock.set('2026-10-31T07:00:00')
        with self.assertRaisesRegex(BudgetError,'monthly_exhausted'):budget.begin([('x',MIB),('y',MIB)],target='d',automatic=False)
        lease=budget.begin([('x',MIB)],target='d',automatic=False);lease.charge('x',MIB);lease.finish()
        self.assertEqual(budget.status()['monthly'],{'requests':3,'bytes':3*MIB})

    def test_cross_day_does_not_double_charge_month(self):
        lease=self.budget.begin([('a',MIB),('b',65536)],target='same',automatic=True)
        first=lease.charge('a',MIB);lease.settle(first,123,True)
        self.clock.set('2026-10-31T00:00:01');lease.charge('b',65536);lease.finish()
        data=self.budget.read()
        self.assertEqual(data['days']['2026-10-30'],{'requests':1,'bytes':MIB})
        self.assertEqual(data['days']['2026-10-31'],{'requests':1,'bytes':65536})
        self.assertEqual(data['months']['2026-10'],{'requests':2,'bytes':MIB+65536})
        self.assertEqual(data['attempts'][0]['actual_bytes'],123)

    def test_cross_month_preserves_both_periods(self):
        self.clock.set('2026-10-31T23:59:59')
        lease=self.budget.begin([('a',MIB),('b',MIB)],target='same',automatic=True)
        lease.charge('a',MIB);self.clock.set('2026-11-01T00:00:01');lease.charge('b',MIB);lease.finish()
        self.assertEqual(self.budget.read()['months'],{'2026-10':{'requests':1,'bytes':MIB},'2026-11':{'requests':1,'bytes':MIB}})

    def test_failed_request_not_refunded_but_unsent_plan_released(self):
        lease=self.budget.begin([('a',MIB),('b',MIB)],target='x',automatic=True)
        key=lease.charge('a',MIB);lease.settle(key,10,False);lease.finish('network_failure')
        self.assertEqual(self.budget.status()['daily'],{'requests':1,'bytes':MIB})
        self.assertEqual(self.budget.read()['batches'][0]['remaining'],[])
        with self.assertRaisesRegex(BudgetError,'already_attempted'):self.budget.begin([('a',MIB)],target='x',automatic=True)
        # 实例重建不能绕过同一目标自动失败抑制。
        new=Budget(self.price,self.activity,self.options,self.clock)
        with self.assertRaisesRegex(BudgetError,'already_attempted'):new.begin([('a',MIB)],target='x',automatic=True)
        self.clock.set('2026-10-31T07:00:00');lease=new.begin([('a',MIB)],target='x',automatic=True);lease.finish('not_sent')

    def test_cross_instance_busy(self):
        lease=self.budget.begin([('a',MIB)],target='x',automatic=False)
        other=Budget(self.price,self.activity,self.options,self.clock)
        with self.assertRaisesRegex(BudgetError,'busy'):other.begin([('a',MIB)],target='x',automatic=False)
        lease.finish()

    def test_crash_unknown_is_charged_and_blocks_restart(self):
        script='''from pathlib import Path
from pmi.market_data.periodic_budget import Budget,PeriodicOptions,MIB
b=Budget(Path(__import__('sys').argv[1]),Path(__import__('sys').argv[2]),PeriodicOptions())
l=b.begin([('a',MIB),('b',MIB)],target='unknown',automatic=True)
l.charge('a',MIB)
__import__('os')._exit(0)
'''
        subprocess.run([sys.executable,'-B','-c',script,str(self.price),str(self.activity)],check=True)
        # 退出释放操作系统锁，但持久running和已扣请求不被当成未运行。
        budget=Budget(self.price,self.activity,self.options)
        self.assertEqual(sum(x['requests'] for x in budget.read()['days'].values()),1)
        with self.assertRaisesRegex(BudgetError,'unresolved'):budget.begin([],target='other',automatic=False)

    def test_unknown_completion_keeps_pending_reservation(self):
        lease=self.budget.begin([('a',MIB),('b',MIB)],target='unknown-publication',automatic=True)
        lease.charge('a',MIB)
        lease.finish('periodic_unresolved_batch')
        self.assertIsNone(self.budget.active)
        self.assertEqual(self.budget.status()['active']['remaining'], [['b',MIB]])
        with self.assertRaisesRegex(BudgetError,'unresolved'):
            self.budget.begin([],target='manual-new-id',automatic=False)

    def test_read_does_not_initialize_or_write_cycle(self):
        before=self.budget.path.read_bytes();self.clock.set('2026-11-01T07:00:00')
        self.assertEqual(self.budget.status()['monthly'],{'requests':0,'bytes':0})
        self.assertEqual(before,self.budget.path.read_bytes())
        self.budget.path.unlink()
        with self.assertRaises((FileNotFoundError,BudgetError)):self.budget.status()
        self.assertFalse(self.budget.path.exists())

    def test_regressed_clock_cannot_reopen_period(self):
        lease=self.budget.begin([],target='a',automatic=True);lease.finish()
        self.clock.set('2026-09-30T07:00:00')
        with self.assertRaisesRegex(BudgetError,'clock_regressed'):self.budget.status()
        with self.assertRaisesRegex(BudgetError,'clock_regressed'):self.budget.begin([],target='b',automatic=False)

    def test_unplanned_request_refused(self):
        lease=self.budget.begin([('a',MIB)],target='x',automatic=False)
        before=self.budget.path.read_bytes()
        with self.assertRaisesRegex(BudgetError,'unplanned'):lease.charge('b',MIB)
        self.assertEqual(before,self.budget.path.read_bytes());lease.finish()

    def test_warning_at_eighty_percent(self):
        options=PeriodicOptions(daily_requests=5,daily_bytes=10*MIB,monthly_requests=50,monthly_bytes=100*MIB)
        budget=Budget(self.price,self.activity,options,self.clock)
        lease=budget.begin([('a',65536)]*4,target='x',automatic=False)
        for _ in range(4):lease.charge('a',65536)
        lease.finish();self.assertTrue(budget.status()['warning'])

    def test_ledger_tamper_rejected_not_repaired(self):
        data=self.budget.read();data['days']={'2026-10-30':{'requests':0,'bytes':0}}
        with self.budget.database.writer(), self.budget.database.transaction() as connection:
            states.write(connection, 'periodic', 'ledger', data)
        before=self.budget.path.read_bytes()
        with self.assertRaisesRegex(BudgetError,'ledger_invalid'):self.budget.status()
        self.assertEqual(before,self.budget.path.read_bytes())

    def test_each_limit_independently_and_latest_resume_constraint(self):
        cases = [
            (PeriodicOptions(1, 4*MIB, 10, 10*MIB), 'daily'),
            (PeriodicOptions(10, MIB, 20, 10*MIB), 'daily'),
        ]
        for options, code in cases:
            budget = Budget(self.price, self.activity, options, self.clock)
            with self.assertRaisesRegex(BudgetError, code):
                budget.begin([('a', MIB), ('b', MIB)], target='too-large', automatic=False)
        # 月次数与月字节分别耗尽，日余额尚足；两者不靠同一个阈值同时触发。
        lease = self.budget.begin([('a',MIB)]*2, target='seed', automatic=False)
        lease.charge('a',MIB); lease.charge('a',MIB); lease.finish()
        self.clock.set('2026-10-31T07:00:00')
        for options in (PeriodicOptions(2,4*MIB,2,10*MIB), PeriodicOptions(10,MIB,20,2*MIB)):
            budget = Budget(self.price,self.activity,options,self.clock)
            with self.assertRaisesRegex(BudgetError,'monthly'):
                budget.begin([('b',65536)],target='monthly',automatic=False)
        self.clock.set('2026-11-01T07:00:00')
        lease = budget.begin([('b',65536)], target='next-month',automatic=False)
        lease.charge('b',65536); lease.finish()
        self.assertEqual(budget.status()['monthly']['requests'],1)
        self.assertEqual(budget.read()['months']['2026-10']['requests'],2)

    def test_cross_period_remaining_batch_rejected_before_next_outbound(self):
        lease=self.budget.begin([('a',MIB),('b',MIB)],target='cross',automatic=False)
        lease.charge('a',MIB)
        self.clock.set('2026-10-31T07:00:00')
        # 模拟同月已经达到获批月额的可信较低策略；不能借换日忘记本月消耗。
        self.budget.options=PeriodicOptions(1,MIB,1,MIB)
        with self.assertRaisesRegex(BudgetError,'monthly'):lease.charge('b',MIB)
        self.assertEqual(len(self.budget.read()['attempts']),1)
        lease.finish('periodic_monthly_exhausted')

if __name__=='__main__':unittest.main()
