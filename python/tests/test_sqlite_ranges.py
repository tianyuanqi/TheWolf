"""范围查询与旧完整输入现算逐字段比较，覆盖预热、周月边界和缺值。"""
from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_market_activity import synthetic, INDEX
from test_index_series_runtime import state
from test_index_series_contract import WINDOW
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data import index_calculations, range_calculations
from pmi.market_data.activity import calculations
from pmi.market_data.activity.facts import index_manifest
from pmi.market_data.activity.model import Original
from pmi.market_data.storage.database import Database, StorageError, digest
from pmi.market_data.storage.originals import Originals
from pmi.market_data.storage.publications import Publications
from pmi.market_data.storage.ranges import Ranges, plan
from pmi.market_data.storage.activity_store import Store
from pmi.market_data.storage import index_store
from pmi.market_data.storage.integrity import Integrity
from pmi.market_data.storage.validation import check_all


class SqliteRangeTests(unittest.TestCase):
    def test_presence_keeps_shared_metadata_missing_values_and_chunk_boundaries(self):
        from pmi.market_data.storage.documents import Documents
        from pmi.market_data.storage.facts import Facts
        from pmi.market_data.storage.publications import ValidationProof
        with tempfile.TemporaryDirectory(prefix='wolf-presence-graph-', dir='/private/tmp') as directory:
            database = Database(Path(directory)); database.initialize()
            expected = {'amount': {}, 'volume': {}}
            with database.writer(), database.transaction() as connection:
                docs, facts, pubs = Documents(connection), Facts(connection), Publications(connection)
                pubs.domain('activity', 'synthetic-presence')
                facts.instrument(INDEX.index_id, 'index')
                shared = {'source': 'synthetic-only', 'metadata': [{'label': str(n), 'value': 'metadata'} for n in range(30)]}
                selected = {}
                for number in range(450):
                    day = (date(2024, 1, 1) + timedelta(days=number)).isoformat()
                    fields = {}
                    references = {}
                    for field, modulus, unit in [('amount', 3, '元'), ('volume', 5, '股')]:
                        value = None if number % modulus == 0 else '0.00'
                        fields[field] = {'value': value, 'unit': unit, 'source': shared}
                        if value is None: fields[field]['reason'] = 'synthetic-missing'
                        projected = facts.metric(INDEX.index_id, day, field, fields[field])
                        references[id(fields[field])] = docs.reference(projected)
                        expected[field][day] = value is not None
                    row = {'trade_date': day, **fields, 'metadata': shared}
                    document = docs.put(row, transform=lambda value: references.get(id(value)))
                    selected[('activity', INDEX.index_id, day, '')] = document
                manifest = {'synthetic_only': True, 'days': 450}
                publication = docs.put(manifest)
                pubs.add(publication, domain='activity', subject=INDEX.index_id, rows=selected,
                         proof=ValidationProof('synthetic-presence', digest(manifest), '2026-11-08T00:00:00+08:00', {'synthetic_only': True}))
            with patch.object(Originals, 'get', side_effect=AssertionError('presence must use SQL only')), database.read() as connection:
                reader = Ranges(connection)
                for field in expected:
                    self.assertEqual(reader.activity_presence(publication, INDEX.index_id, field), expected[field])
                values = reader.documents.get_many(list(selected.values()))
                for key, reference in selected.items():
                    for field in expected:
                        self.assertEqual(values[reference][field]['value'] is not None, expected[field][key[2]])
                first, second = list(values.values())[:2]
                first['metadata']['metadata'][0]['value'] = 'changed-in-memory'
                self.assertEqual(second['metadata']['metadata'][0]['value'], 'metadata')
            with database.writer(), database.transaction() as connection:
                docs = Documents(connection)
                bad = docs.node('dict', 'synthetic-cycle')
                connection.execute('INSERT INTO node_edge VALUES(?,?,?,?)', (bad, 0, 'cycle', bad))
                broken = docs.alias(digest('synthetic-cycle-document'), 'metadata', bad, digest('synthetic-cycle-content'))
            with database.read() as connection:
                reader = Ranges(connection)
                with self.assertRaisesRegex(StorageError, 'storage_invalid_document_graph'):
                    reader.documents.get(broken)
                with patch.object(reader.publications, 'selected_rows', return_value={('activity', INDEX.index_id, '2024-01-01', ''): broken}):
                    with self.assertRaisesRegex(StorageError, 'storage_invalid_document_graph'):
                        reader.activity_presence(publication, INDEX.index_id, 'amount')

    def test_range_matches_full_calculations_without_original_reads(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-range-', dir='/private/tmp') as directory:
            root = Path(directory)
            database = Database(root)
            database.initialize()
            with database.writer(), database.transaction() as connection:
                Publications(connection).domain('price-v2', digest('price'))
                Publications(connection).domain('activity', digest('activity'))
            items = list(synthetic())
            content = json.loads(items[0].content)
            content['data'][0]['tradingValue'] = None
            items[0] = replace(items[0], content=json.dumps(content).encode())
            items = tuple(items)
            with database.writer():
                price_id = index_store.publish(root, INDEX, WINDOW, build_manifest(INDEX, WINDOW, items), items, state(INDEX))['snapshot_id']
            full_price = index_store.read_snapshot(root, INDEX, price_id)
            raw = items[0]
            original = Original(raw.source, raw.content, raw.url, raw.started_at, raw.completed_at)
            manifest = index_manifest(INDEX.index_id, full_price, original)
            receipt = {'series_id': INDEX.index_id, 'sources': [{'source': raw.source, 'object_id': original.object_id,
                'url': raw.url, 'started_at': raw.started_at, 'completed_at': raw.completed_at, 'published_at': None}]}
            operation = {'request_id': 'range', 'series_id': INDEX.index_id, 'target': price_id, 'state': 'preparing',
                         'activity_id': None, 'reason': None, 'observation_id': None}
            store = Store(root)
            with store.lock(write=True):
                activity_id = store.publish(manifest, {original.object_id: original.content}, None, operation, receipt)
            full_activity = {**manifest, 'activity_id': activity_id}
            checked = Integrity(database).run('full', semantic_check=lambda connection: check_all(database, connection))
            self.assertEqual(checked['state'], 'passed')
            expected_price = index_calculations.calculate(INDEX.index_id, full_price, index_calculations.FORMULA_VERSION)
            expected_activity = calculations.calculate(full_activity, calculations.FORMULA)
            dates = tuple(full_price['calendar_dates'])
            intervals = [(dates[0], dates[0]), (dates[300], dates[309]), (dates[-40], dates[-10]), (dates[-20], dates[-1])]
            with patch.object(Originals, 'get', side_effect=AssertionError('范围读取不许打开原件')), database.read() as connection:
                reader = Ranges(connection)
                header = reader.header(price_id, 'price-v2', INDEX.index_id)
                activity_header = reader.header(activity_id, 'activity', INDEX.index_id)
                self.assertNotIn('bars', header)
                self.assertNotIn('rows', activity_header)
                self.assertEqual(reader.dates(price_id, 'price', INDEX.index_id), dates)
                presence = reader.activity_presence(activity_id, INDEX.index_id, 'amount')
                self.assertFalse(all(presence.values()))
                for frequency in ('daily', 'weekly', 'monthly'):
                    for selected in ((5,), (250, 5), ()):
                        for start, end in intervals:
                            selection = plan(dates, start, end, frequency, selected)
                            bars = reader.rows(price_id, 'price', INDEX.index_id, selection)
                            snapshot = {**header, 'snapshot_id': price_id, 'bars': bars}
                            actual = range_calculations.price_series(snapshot, dates, selection.visible_periods, frequency,
                                selected, index_calculations.FORMULA_VERSION)
                            expected = expected_price[frequency]
                            wanted = [{**row, 'ma': [value for value in row['ma'] if int(value['parameters']['period']) in selected]}
                                      for row in expected['rows'] if row['period_start'] in selection.visible_periods]
                            self.assertEqual(actual, {**expected, 'rows': wanted}, (frequency, selected, start, end))
                            rows = reader.rows(activity_id, 'activity', INDEX.index_id, selection)
                            snapshot = {**activity_header, 'activity_id': activity_id, 'rows': rows}
                            actual = range_calculations.activity_series(snapshot, dates, presence, selection.visible_periods,
                                'amount', frequency, selected, calculations.FORMULA)
                            expected = next(value for value in expected_activity['series'] if value['field'] == 'amount' and value['frequency'] == frequency)
                            wanted = [{**row, 'ma': [value for value in row['ma'] if int(value['parameters']['period']) in selected]}
                                      for row in expected['rows'] if row['period_start'] in selection.visible_periods]
                            self.assertEqual(actual, {**expected, 'rows': wanted}, (frequency, selected, start, end))
            weekend = next((date.fromisoformat(day) + timedelta(days=1)).isoformat() for day in dates if date.fromisoformat(day).weekday() == 4)
            self.assertIsNone(plan(dates, weekend, weekend, 'weekly', (5,)).returned)
            with self.assertRaisesRegex(StorageError, 'coverage_insufficient'):
                plan(dates, (date.fromisoformat(dates[0]) - timedelta(days=1)).isoformat(), dates[0], 'daily', ())
            with self.assertRaisesRegex(StorageError, 'range_parameters_invalid'):
                plan(dates, '2020-01-01', dates[0], 'daily', ())
        self.assertFalse(root.exists())
