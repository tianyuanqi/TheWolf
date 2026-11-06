"""S2官方单源：已存研究原件离线核验与隔离生产门控，不访问日常库。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmi.market_data import index_series_store as price_store
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.writer_lock import writer_lock
from pmi.market_data.activity import facts, model, sources
from pmi.market_data.activity.model import ActivityError, Original
from test_market_activity import Client, INDEX, SID, synthetic
from test_index_series_contract import WINDOW
from test_index_series_runtime import state
from http_test_support import disk


class SingleOfficialSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wolf-s2-admission-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.price, self.activity = self.base/'price', self.base/'activity'
        self.price.mkdir(); self.activity.mkdir()
        self.items = synthetic()
        with writer_lock(self.price):
            price_store.prepare_directories(self.price, INDEX)
            price_store.publish(self.price, INDEX, WINDOW, build_manifest(INDEX, WINDOW, self.items), self.items, state(INDEX))
        self.snapshot = price_store.read_snapshot(self.price, INDEX)
        original = self.items[0]
        self.original = Original(original.source, original.content, original.url, original.started_at, original.completed_at)

    def test_sse_admitted_without_test_policy_override_and_zero_network(self):
        client = Client(self.price, self.activity, write_series=(SID,))
        self.addCleanup(client.app.state.updates.close)
        before = disk(self.price)
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('禁止外网')) as network:
            result = client.update(self.snapshot['snapshot_id'])
            self.assertEqual(result.status, 200, result.body)
            self.assertEqual(result.json()['state'], 'completed', result.body)
            fixed = client.request(f"/api/market-activity/{SID}/snapshots/{result.json()['activity_id']}")
            self.assertEqual(fixed.status, 200, fixed.body)
            self.assertEqual(fixed.json()['rows'][-1]['amount']['value'], '123000000.00')
            self.assertEqual(fixed.json()['source_policy_version'], 'activity-source-policy-v2')
            self.assertEqual(fixed.json()['binding']['relation'], 'same_source_object')
            network.assert_not_called()
        self.assertEqual(before, disk(self.price))

    def test_old_policy_replays_null_and_unknown_version_is_rejected(self):
        old = facts.index_manifest(SID, self.snapshot, self.original, policy_version='activity-source-policy-v1')
        self.assertTrue(all(row['amount']['value'] is None and row['amount']['reason']=='source_unverified' for row in old['rows']))
        new = facts.index_manifest(SID, self.snapshot, self.original)
        self.assertNotEqual(model.digest(old), model.digest(new))
        self.assertEqual(old, facts.index_manifest(SID, self.snapshot, self.original, policy_version=old['source_policy_version']))
        with self.assertRaisesRegex(ActivityError, 'source_policy_version_unknown'):
            facts.index_manifest(SID, self.snapshot, self.original, policy_version='invented-version')

    def test_single_source_does_not_relax_pairing_precision_or_missing(self):
        raw = json.loads(self.original.content)
        raw['data'][0]['tradingValue'] = None
        raw['data'][-1]['tradingVol'] = '0'
        def candidate(body):
            return Original('csindex', model.canonical(body), self.original.url, '', '')
        manifest = facts.index_manifest(SID, self.snapshot, candidate(raw))
        self.assertIsNone(manifest['rows'][0]['amount']['value'])
        self.assertEqual(manifest['rows'][-1]['volume']['value'], '0')
        mismatch = deepcopy(raw); mismatch['data'][-1]['close'] = '99999'
        with self.assertRaisesRegex(ActivityError, 'price_values_mismatch'):
            facts.index_manifest(SID, self.snapshot, candidate(mismatch))
        precision = deepcopy(raw); precision['data'][-1]['tradingValue'] = '1.234'
        with self.assertRaisesRegex(ActivityError, 'source_precision_mismatch'):
            facts.index_manifest(SID, self.snapshot, candidate(precision))

    def test_official_exponent_is_exact_and_bounded(self):
        self.assertEqual(model.source_number('4.43564144E10', integer=True), 44356414400)
        for raw in ('NaN', '-1E2', '1E100', '1E25', '1E-13', True, 1.23):
            with self.assertRaises(ActivityError):
                model.source_number(raw)
        with self.assertRaises(ActivityError):
            model.source_number('1.23E-1', integer=True)
        with self.assertRaises(ActivityError):
            model.number('1E2')

    def test_synthetic_official_identity_units_and_precision(self):
        raw=model.load(self.original.content,source=True)
        raw['data']=[{**raw['data'][0],'tradeDate':'20261027','tradingValue':'12.34','tradingVol':'1234'}]
        content=model.canonical(raw)
        item=Original('csindex',content,sources.url(SID,['2026-10-27']),'','')
        row = sources.parse_index(SID,item,['2026-10-27'])[0]
        amount = facts.fact(SID,'amount',row['amount'],item,row['locator'])
        volume = facts.fact(SID,'volume',row['volume'],item,row['locator'])
        self.assertEqual((amount['raw_value'],amount['value'],amount['raw_unit'],amount['source_quantum']),('12.34','1234000000.00','亿元','0.01'))
        self.assertEqual(volume['value'],'1234')
