"""价格与量额用真实SQL表验证固定版本、来源绑定、CAS及事务失败保旧。"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_index_series_contract import originals, WINDOW
from test_index_series_runtime import state
from test_market_activity import synthetic, INDEX
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.activity.facts import index_manifest
from pmi.market_data.activity.model import Original
from pmi.market_data.storage.database import Database, digest
from pmi.market_data.storage.publications import Publications
from pmi.market_data.storage.originals import Originals
from pmi.market_data.storage import index_store
from pmi.market_data.storage.activity_store import Store


class SqliteMarketTests(unittest.TestCase):
    def test_price_publication_failed_candidate_and_observation_identity(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-price-', dir='/private/tmp') as directory:
            root = Path(directory)
            db = Database(root)
            db.initialize()
            with db.writer(), db.transaction() as connection:
                Publications(connection).domain('price-v2', digest('isolated-price'))
            items = originals(INDEX, WINDOW)
            with db.writer():
                first = index_store.publish(root, INDEX, WINDOW, build_manifest(INDEX, WINDOW, items), items, state(INDEX))
            changed = originals(INDEX, WINDOW, prices=('101.00', '111.00', '91.00', '106.00'))
            def fail(stage):
                if stage == 'before_commit':
                    raise RuntimeError('合成中断')
            with db.writer(), self.assertRaises(RuntimeError):
                index_store.publish(root, INDEX, WINDOW, build_manifest(INDEX, WINDOW, changed), changed, state(INDEX, 'interrupted'), fail)
            with patch.object(Originals, 'get', side_effect=AssertionError('禁止普通读取打开原件')):
                current = index_store.read_snapshot(root, INDEX)
                self.assertEqual(current['snapshot_id'], first['snapshot_id'])
                self.assertEqual(current['observation_id'], first['observation_id'])
                self.assertIsNone(index_store.committed_job_locked(root, INDEX, 'interrupted'))
                self.assertEqual(index_store.committed_job_locked(root, INDEX, first['job_id']), first)
        self.assertFalse(root.exists())

    def test_activity_keeps_fixed_price_and_receipt_sql_only(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-activity-', dir='/private/tmp') as directory:
            root = Path(directory)
            db = Database(root)
            db.initialize()
            with db.writer(), db.transaction() as connection:
                Publications(connection).domain('price-v2', digest('isolated-price'))
                Publications(connection).domain('activity', digest('isolated-activity'))
            items = synthetic()
            with db.writer():
                saved = index_store.publish(root, INDEX, WINDOW, build_manifest(INDEX, WINDOW, items), items, state(INDEX))
            price = index_store.read_snapshot(root, INDEX)
            raw = items[0]
            original = Original(raw.source, raw.content, raw.url, raw.started_at, raw.completed_at)
            manifest = index_manifest(INDEX.index_id, price, original)
            operation = {'request_id': 'synthetic', 'series_id': INDEX.index_id, 'target': saved['snapshot_id'],
                         'state': 'preparing', 'activity_id': None, 'reason': None, 'observation_id': None}
            receipt = {'series_id': INDEX.index_id, 'sources': [{'source': raw.source, 'object_id': original.object_id,
                'url': raw.url, 'started_at': raw.started_at, 'completed_at': raw.completed_at, 'published_at': None}]}
            store = Store(root)
            with store.lock(write=True):
                reference = store.publish(manifest, {original.object_id: original.content}, None, operation, receipt)
            with patch.object(Originals, 'get', side_effect=AssertionError('禁止普通读取打开原件')):
                fixed = store.fixed(reference)
                self.assertEqual(fixed, manifest)
                self.assertEqual(store.current(INDEX.index_id, saved['snapshot_id'])['activity_id'], reference)
                self.assertIsNone(store.current(INDEX.index_id, 'a' * 64))
                observed = store.observations(reference, fixed)
                self.assertEqual(observed[0]['request_id'], 'synthetic')
            with store.lock(write=True), self.assertRaises(ValueError):
                store.publish(manifest, {original.object_id: original.content}, None, {**operation, 'request_id': 'stale'}, receipt)
            self.assertEqual(store.fixed(reference), manifest)
        self.assertFalse(root.exists())
