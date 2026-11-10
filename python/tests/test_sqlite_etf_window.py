"""已发布ETF版本：范围数值装配、原信号身份和完整核验边界。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from etf_flow_fixture import AT, END, stored_sample
from etf_flow_view_fixture import revisions
from pmi.market_data.etf_flow.calculation import Admission, Calculator
from pmi.market_data.etf_flow.model import digest
from pmi.market_data.etf_flow.repository import Repository
from pmi.market_data.etf_flow.view import build
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.storage.originals import Originals


class WindowTests(unittest.TestCase):
    def compare(self, store, snapshot, ends, periods):
        repo = Repository(store, verify_reads=False)
        full_load = repo.load

        def whole(*args, **kwargs):
            kwargs.pop('window', None)
            return full_load(*args, **kwargs)

        def full_calculator(config, evidence, admissions, dataset, **kwargs):
            return Calculator(config, repo._dataset(dataset), evidence.adjustments,
                tuple(Admission.parse(store.get_json(ref)) for ref in admissions),
                selection_at=kwargs['selection_at'], end=kwargs['end'])

        loaded = full_load(snapshot)
        groups = [None, *sorted({m.group_id for m in loaded.calculator.pool.members})]
        get_many = store.get_many
        for mode in ('current', 'original'):
            for end in ends:
                for period in periods:
                    for group in groups:
                        parameters = dict(mode=mode, period=period, end=end, group=group, server_day='2026-11-06')
                        with patch.object(repo, 'load', whole), patch.object(repo, 'window_calculator', full_calculator):
                            expected = build(repo, snapshot, **parameters)
                        materialized = []
                        def limited(refs):
                            values = get_many(refs)
                            materialized.extend(value for value in values.values() if isinstance(value, dict)
                                and set(value) == {'member_id', 'date', 'fields', 'revision_reason'})
                            return values
                        with patch.object(store, 'get_many', limited), patch.object(Originals, 'get', side_effect=AssertionError('普通页面禁止原件')):
                            actual = build(repo, snapshot, **parameters)
                        self.assertEqual(expected, actual, (mode, end, period, group))
                        members = {member['id'] for member in actual['members']}
                        self.assertLessEqual(len(materialized), (period + 1) * len(members))
                        self.assertTrue(all(row['member_id'] in members and row['date'] <= actual['end'] for row in materialized))
                        self.assertEqual(actual['input_version'], expected['input_version'])
        return repo

    def test_long_history_and_groups_bound_numeric_rows_without_changing_results(self):
        with tempfile.TemporaryDirectory(prefix='wolf-etf-window-', dir='/private/tmp') as directory:
            root = Path(directory); store = Store(root); store.initialize(); repo = Repository(store)
            with store.writer():
                config, inputs, evidence, dates = stored_sample(store, 'multiple', 700)
                snapshot = repo.publish(config, evidence, inputs, end=END, selection_at=AT,
                    operation_key=digest('window-long-multiple'), expected=None)
            self.assertGreater(len(inputs), 2000)
            self.compare(store, snapshot, [None, dates[-100]], [20, 60, 120, 260])
        self.assertFalse(root.exists())

    def test_saved_original_signals_are_sql_only_but_evidence_and_verification_read_originals(self):
        with tempfile.TemporaryDirectory(prefix='wolf-etf-original-', dir='/private/tmp') as directory:
            root = Path(directory); store = Store(root); store.initialize()
            with store.writer(): fixture = revisions(store)
            repo = self.compare(store, fixture['final'], [fixture['dates'][-2]], [20, 260])
            raw_reads = []
            original_get = Originals.get
            def observe(instance, identity):
                raw_reads.append(identity)
                return original_get(instance, identity)
            with patch.object(Originals, 'get', observe):
                repo.evidence(fixture['final'], fixture['original_proof'])
            self.assertEqual(raw_reads, [fixture['original_proof']])
            with patch.object(Originals, 'get', side_effect=AssertionError('完整核验仍应读原件')):
                with self.assertRaisesRegex(AssertionError, '完整核验'):
                    repo.load(fixture['final'], verify=True)
        self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
