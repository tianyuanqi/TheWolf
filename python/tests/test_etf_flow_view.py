"""S3独审反例的服务投影回归；不改已有计算/发布规则。"""
from copy import deepcopy
from pathlib import Path
import hashlib
import tempfile
import unittest

from etf_flow_fixture import AT, END, stored_sample
from etf_flow_view_fixture import revisions
from pmi.market_data.etf_flow.evidence import Evidence
from pmi.market_data.etf_flow.model import Input, digest, canonical
from pmi.market_data.etf_flow.repository import Repository
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.etf_flow.view import build


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='etf-view-test-', dir='/private/tmp')
        self.root = Path(self.temporary.name); self.store = Store(self.root); self.store.initialize()
        self.repo = Repository(self.store)

    def tearDown(self):
        self.temporary.cleanup(); self.assertFalse(self.root.exists())

    def view(self, snapshot, mode='current', end=None, group=None, period=60):
        return build(self.repo, snapshot, mode=mode, period=period, end=end, group=group, server_day='2026-11-06')

    def test_old_adjustment_and_original_record_survive_correction(self):
        with self.store.writer(): fixture = revisions(self.store)
        on = fixture['dates'][-2]
        old = self.view(fixture['final'], 'original', on)
        new = self.view(fixture['final'], 'current', on)
        self.assertEqual(old['members'][0]['metrics']['amount'], '10.0')
        self.assertEqual(new['members'][0]['metrics']['amount'], '20.00')
        for view, factor, tail, proof in [(old, '2', '0.5', fixture['original_proof']),
                                        (new, '3', '0.75', fixture['corrected_proof'])]:
            detail = view['members'][0]['series'][-1]['adjustment_detail']
            self.assertEqual((detail['factor'], detail['tail'], detail['source_ids']), (factor, tail, [proof]))
            self.assertIn(proof, [s['object_id'] for s in view['sources']])
            self.assertEqual(self.repo.evidence(view['snapshot_id'], proof)['object_id'], proof)
        self.assertNotIn(fixture['corrected_proof'], [s['object_id'] for s in old['sources']])
        self.assertEqual({e['locator'] for e in old['events']}, {'同一公告第1段', '同一公告第2段'})

    def test_complete_day_modes_groups_windows_and_late_nav(self):
        with self.store.writer(): f = revisions(self.store)
        prior, end = f['dates'][-2:]
        for period in (20, 60, 120, 260):
            before = self.view(f['partial'], period=period)
            after = self.view(f['final'], period=period)
            self.assertEqual(before['data_status']['complete_amount_through'], prior)
            self.assertEqual(after['data_status']['complete_amount_through'], end)
            self.assertEqual(before['summary']['evaluation']['amount'], '80')
            self.assertEqual(after['summary']['evaluation']['amount'], '100.00')
        groups = f['config'].pools[-1].members
        complete_group = next(m.group_id for m in groups if m.group_id != groups[0].group_id)
        self.assertEqual(self.view(f['partial'], group=complete_group)['data_status']['complete_amount_through'], end)
        self.assertEqual(self.view(f['partial'], group=groups[0].group_id)['data_status']['complete_amount_through'], prior)
        self.assertEqual(self.view(f['final'], 'original')['data_status']['complete_amount_through'], prior)
        self.assertIsNone(self.view(f['initial'], 'original')['data_status']['complete_amount_through'])
        self.assertIsNone(self.view(f['final'], 'original', f['dates'][-3])['data_status']['complete_amount_through'])
        self.assertEqual(self.view(f['partial'])['data_status']['complete_amount_through'], prior)

    def test_unknown_adjustment_and_fallback_do_not_claim_a_basis(self):
        with self.store.writer():
            config, inputs, evidence, dates = stored_sample(self.store, count=10)
            ev = deepcopy(evidence.raw); ev['adjustments'] = []
            evidence = Evidence.parse(ev, {m.id for m in config.pools[-1].members})
            snap = self.repo.publish(config, evidence, inputs, end=END, selection_at=AT,
                operation_key=digest('view-unknown'), expected=None)
        view = self.view(snap)
        self.assertIsNone(view['data_status']['complete_amount_through'])
        self.assertTrue(all(p['adjustment_detail'] is None for p in view['members'][0]['series']))
        self.assertEqual(view['members'][0]['metrics']['reason'], 'adjustment_unverified')
        # 存在覆盖窗口的已确认证据，输入前的fallback点仍未知。
        with self.store.writer():
            _, _, normal, _ = stored_sample(self.store, count=10)
            doc = deepcopy(normal.raw); doc['version'] = 'normal-with-earlier-coverage'
            doc['adjustments'][0]['start'] = view['series'][0]['date']
            normal = Evidence.parse(doc, {m.id for m in config.pools[-1].members})
            snap = self.repo.publish(config, normal, inputs, end=END, selection_at=AT,
                operation_key=digest('view-fallback'), expected=snap)
        points = self.view(snap)['members'][0]['series']
        self.assertEqual(points[0]['metrics']['reason'], 'input_missing'); self.assertIsNone(points[0]['adjustment_detail'])
        self.assertEqual(points[-1]['adjustment_detail']['kind'], 'normal')

    def test_true_zero_and_one_member_c2_do_not_erase_complete_amount(self):
        with self.store.writer():
            config, inputs, ev, dates = stored_sample(self.store)
            raw = deepcopy(inputs[-1].raw); raw['fields']['shares']['value'] = str(inputs[-2].value('shares'))
            proof = self.store.put(canonical({'synthetic_test_only': True, 'zero': raw}))
            for field in raw['fields'].values(): field['source']['object_id'] = proof
            snap = self.repo.publish(config, ev, inputs[:-1] + (Input.parse(raw),), end=END, selection_at=AT,
                operation_key=digest('view-zero'), expected=None)
        view = self.view(snap); row = view['summary']['evaluation']
        self.assertEqual(row['amount'], '0'); self.assertEqual(row['valid_count'], 1)
        self.assertIsNone(row['c2']['positive_ratio']); self.assertIsNone(row['c2']['positive_count'])
        self.assertEqual(view['data_status']['complete_amount_through'], END)

    def test_all_view_and_evidence_reads_leave_fixed_store_unchanged(self):
        with self.store.writer(): f = revisions(self.store)
        state = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        before = state()
        for snapshot in (f['initial'], f['partial'], f['final']):
            for mode in ('original', 'current'):
                view = self.view(snapshot, mode)
                # 一次证据读取已覆盖同一只读路径，不为相同原件的五种字段定位重复载入整个库。
                self.repo.evidence(snapshot, view['sources'][0]['object_id'])
        self.assertEqual(before, state())
