"""单库基础的隔离反例：精度、独立修订、不可变历史与无副作用读取。"""
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.documents import Documents
from pmi.market_data.storage.facts import Facts
from pmi.market_data.storage.originals import Originals
from etf_flow_fixture import sample


class SQLiteStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='wolf-sqlite-unit-', dir='/private/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = Database(self.root)
        self.database.initialize()

    def price(self, **changes):
        value = {'trade_date': '2026-10-20', 'open': '123.4500', 'high': '124.0000',
                 'low': '120.0000', 'close': '123.4600', 'evidence_refs': [{'locator': 'fake:1'}]}
        value.update(changes)
        return value

    def put_price(self, connection, value):
        facts = Facts(connection)
        facts.instrument('synthetic:index', 'index')
        return facts.price('synthetic:index', value, unit='点', precision=4, price_type='index_points')

    def test_observation_change_reuses_prices_and_one_correction_adds_one(self):
        first = self.price()
        observation = self.price(evidence_refs=[{'locator': 'fake:2'}])
        changed = self.price(close='123.4700')
        with self.database.writer(), self.database.transaction() as connection:
            a = self.put_price(connection, first)
            self.assertEqual(a, self.put_price(connection, deepcopy(first)))
            b = self.put_price(connection, observation)
            self.assertNotEqual(a, b)
            self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 1)
            c = self.put_price(connection, changed)
            self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 2)
            docs = Documents(connection)
            self.assertEqual(docs.get(a), first)
            self.assertEqual(docs.get(b), observation)
            self.assertEqual(docs.get(c), changed)
            self.assertEqual(connection.execute('SELECT typeof(closing) FROM price_row LIMIT 1').fetchone()[0], 'text')

    def test_etf_one_metric_revision_leaves_other_four_versions(self):
        original = sample(count=1)[1][0].raw
        correction = deepcopy(original)
        correction['fields']['nav']['value'] = '1.000000000000000001'
        with self.database.writer(), self.database.transaction() as connection:
            facts = Facts(connection)
            first = facts.input(original)
            second = facts.input(correction)
            self.assertEqual(facts.input(correction), second)
            counts = dict(connection.execute('SELECT metric,count(*) FROM daily_metric GROUP BY metric'))
            self.assertEqual(counts, {'shares': 1, 'nav': 2, 'close': 1, 'turnover': 1, 'volume': 1})
            self.assertEqual(Documents(connection).get(first), original)
            self.assertEqual(Documents(connection).get(second), correction)

    def test_invalid_precision_float_and_ohlc_roll_back(self):
        for changes in ({'close': '123.47001'}, {'close': 123.47}, {'close': '125.0000'}):
            with self.assertRaises(StorageError), self.database.writer(), self.database.transaction() as connection:
                self.put_price(connection, self.price(**changes))
        with self.database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT count(*) FROM instrument').fetchone()[0], 0)

    def test_batch_read_exceeds_sqlite_compound_select_limit(self):
        from datetime import date, timedelta
        with self.database.writer(), self.database.transaction() as connection:
            references = []
            expected = {}
            for offset in range(727):
                row = self.price(trade_date=(date(2023, 1, 1) + timedelta(days=offset)).isoformat())
                reference = self.put_price(connection, row)
                references.append(reference)
                expected[reference] = row
            self.assertEqual(Documents(connection).get_many(references), expected)

    def test_facts_and_documents_cannot_be_overwritten(self):
        with self.database.writer(), self.database.transaction() as connection:
            reference = self.put_price(connection, self.price())
        with self.database.writer(), self.database.transaction() as connection:
            for sql in ('DELETE FROM price_row', "UPDATE price_row SET closing='0'", 'DELETE FROM document'):
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable_history'):
                    connection.execute(sql)
            self.assertEqual(Documents(connection).get(reference), self.price())

    def test_original_dedup_and_corruption_rejected_without_repair(self):
        store = Originals(self.database)
        raw = b'only synthetic original\n'
        with self.database.writer():
            reference = store.put(raw)
            self.assertEqual(store.put(raw), reference)
        self.assertEqual(store.get(reference), raw)
        path = self.root / 'objects' / reference
        path.write_bytes(b'broken synthetic original')
        with self.assertRaisesRegex(StorageError, 'storage_original_corrupt'):
            store.get(reference)
        self.assertEqual(path.read_bytes(), b'broken synthetic original')

    def test_original_link_retry_syncs_destination_before_registration(self):
        import pmi.market_data.storage.originals as module
        store = Originals(self.database)
        raw = b'synthetic interrupted original directory sync\n'
        identity = hashlib.sha256(raw).hexdigest()
        target = self.root / 'objects' / identity
        actual = module.fsync_directory

        def interrupted(path):
            if path == self.root / 'objects':
                raise OSError('synthetic directory sync failure')
            actual(path)

        with self.database.writer(), patch.object(module, 'fsync_directory', interrupted):
            for _ in range(2):
                # 首次和重试的目标目录同步都失败时，均不得登记SQL引用或丢掉自有临时链接。
                with self.assertRaisesRegex(OSError, 'synthetic directory sync failure'):
                    store.put(raw)
                self.assertEqual(target.stat().st_nlink, 2)
                with self.database.read() as connection:
                    self.assertEqual(connection.execute('SELECT count(*) FROM original_object').fetchone()[0], 0)

        events = []
        def synchronized(path):
            actual(path)
            events.append(path.name)
        def statement(sql):
            if sql.startswith('INSERT OR IGNORE INTO original_object'):
                events.append('sql-registration')

        with self.database.writer() as connection, patch.object(module, 'fsync_directory', synchronized):
            connection.set_trace_callback(statement)
            try:
                self.assertEqual(store.put(raw), identity)
            finally:
                connection.set_trace_callback(None)
        self.assertLess(events.index('objects'), events.index('incoming'))
        self.assertLess(events.index('incoming'), events.index('sql-registration'))
        self.assertEqual(target.stat().st_nlink, 1)
        self.assertEqual(list((self.root / 'incoming').iterdir()), [])
        self.assertEqual(store.get(identity), raw)

    def test_read_query_only_and_missing_database_do_not_create_files(self):
        before = {str(p.relative_to(self.root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                  for p in self.root.rglob('*') if p.is_file()}
        with self.database.read() as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO domain VALUES('x','x',1,NULL)")
        after = {str(p.relative_to(self.root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        with TemporaryDirectory(prefix='wolf-sqlite-empty-', dir='/private/tmp') as directory:
            root = Path(directory)
            with self.assertRaises(StorageError), Database(root).read():
                pass
            self.assertEqual(list(root.iterdir()), [])

    def test_outer_failure_rolls_back_inner_success(self):
        with self.assertRaisesRegex(RuntimeError, 'interrupt'), self.database.writer(), self.database.transaction():
            with self.database.transaction() as connection:
                self.put_price(connection, self.price())
            raise RuntimeError('interrupt')
        with self.database.read() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 0)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_publication_delta_old_versions_cas_and_failed_publish(self):
        from pmi.market_data.storage.database import digest
        from pmi.market_data.storage.publications import Publications, ValidationProof
        with self.database.writer(), self.database.transaction() as connection:
            publications = Publications(connection)
            publications.domain('test', 'isolated-test-scope')
            first_row = self.put_price(connection, self.price())
            first = Documents(connection).put({'test': 'first'}, 'test-publication')
            proof = ValidationProof('synthetic-test', digest({'test': 'first'}), '2026-11-01T00:00:00+00:00', {'synthetic': True})
            key = ('price', 'synthetic:index', '2026-10-20', '')
            publications.add(first, domain='test', subject='synthetic:index', rows={key: first_row}, proof=proof)
            publications.select(first, domain='test', subject='synthetic:index', expected=None)
            second_row = self.put_price(connection, self.price(close='123.4700'))
            second = Documents(connection).put({'test': 'second'}, 'test-publication')
            proof = ValidationProof('synthetic-test', digest({'test': 'second'}), '2026-11-02T00:00:00+00:00', {'synthetic': True})
            publications.add(second, domain='test', subject='synthetic:index', rows={key: second_row}, proof=proof, base=first)
            publications.select(second, domain='test', subject='synthetic:index', expected=first)
            self.assertEqual(publications.rows(first), {key: first_row})
            self.assertEqual(publications.rows(second), {key: second_row})
            self.assertEqual(connection.execute('SELECT count(*) FROM publication_row WHERE publication_id=?', (second,)).fetchone()[0], 1)
            with self.assertRaisesRegex(StorageError, 'storage_publication_changed'):
                publications.select(first, domain='test', subject='synthetic:index', expected=first)
            self.assertEqual(publications.head('test', 'synthetic:index')[0], second)
        with self.assertRaisesRegex(RuntimeError, 'publication interrupt'), self.database.writer(), self.database.transaction() as connection:
            publications = Publications(connection)
            publications.select(first, domain='test', subject='synthetic:index', expected=second)
            raise RuntimeError('publication interrupt')
        with self.database.read() as connection:
            self.assertEqual(Publications(connection).head('test', 'synthetic:index')[0], second)
            self.assertEqual(connection.execute('SELECT projection_id FROM current_row').fetchone()[0], second_row)

    def test_snapshot_head_has_no_history_values_and_restores_exact_evidence(self):
        from decimal import Decimal
        from pmi.market_data.index_series_contract import summarize
        from pmi.market_data.storage.database import digest
        from pmi.market_data.storage.publications import Publications, ValidationProof
        from pmi.market_data.storage.snapshots import Snapshots
        bars = [self.price(), self.price(trade_date='2026-10-21')]
        with self.database.writer(), self.database.transaction() as connection:
            sources = []
            for n in range(2):
                object_id = Originals(self.database).put(('synthetic codec source ' + str(n)).encode())
                source_rows = []
                for i, bar in enumerate(bars):
                    fields = {key: bar[key] for key in ('open', 'high', 'low', 'close')}
                    source_rows.append({'trade_date': bar['trade_date'], **fields, 'locator': 'fake:' + str(i),
                                        'raw_values': fields, 'comparison_values': {key: format(Decimal(v), '.2f') for key,v in fields.items()}})
                sources.append({'source': 'fake' + str(n), 'object_id': object_id, 'url': 'https://example.invalid/synthetic', 'rows': source_rows})
            for i, bar in enumerate(bars):
                bar['evidence_refs'] = [{'source': source['source'], 'object_id': source['object_id'], 'locator': 'fake:' + str(i)} for source in sources]
            manifest = {'schema_version': 'index-series-price-snapshot-v2', 'instrument': {'id': 'synthetic:index'},
                        'unit': '点', 'storage_decimals': 4, 'window': {'start': '2026-10-20', 'end': '2026-10-21'},
                        'calendar_dates': ['2026-10-20', '2026-10-21'], 'bars': bars, 'summary': summarize(bars), 'evidence': sources}
            identifier, rows = Snapshots(connection).price(manifest)
            publications = Publications(connection)
            publications.domain('test', 'synthetic')
            proof = ValidationProof('synthetic-codec-test', digest(manifest), '2026-11-01T00:00:00+00:00', {'synthetic': True})
            publications.add(identifier, domain='test', subject='synthetic:index', rows=rows, proof=proof)
            self.assertEqual(Documents(connection).get(identifier), manifest)
            root = Documents(connection).reference(identifier).node_id
            header = connection.execute('SELECT child FROM node_edge WHERE parent=?', (root,)).fetchone()[0]
            metadata = Documents(connection).decode(header)
            self.assertNotIn('bars', metadata)
            self.assertNotIn('calendar_dates', metadata)
            self.assertNotIn('summary', metadata)
            self.assertTrue(all('rows' not in source for source in metadata['evidence']))
            self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT count(*) FROM source_price_value').fetchone()[0], 2)
            self.assertFalse(connection.execute('PRAGMA foreign_key_check').fetchall())

    def test_corrupt_publication_cycle_is_bounded_and_rejected(self):
        from pmi.market_data.storage.database import digest
        from pmi.market_data.storage.publications import Publications, ValidationProof
        with self.database.writer(), self.database.transaction() as connection:
            pubs = Publications(connection)
            pubs.domain('test', 'synthetic-cycle')
            ids = []
            for revision in range(2):
                value = {'synthetic': revision}
                identity = Documents(connection).put(value)
                pubs.add(identity, domain='test', subject='synthetic', rows={}, base=ids[-1] if ids else None,
                    proof=ValidationProof('test', digest(value), '2026-11-08T00:00:00Z', {}))
                ids.append(identity)
            # 仅自有假库注入绕过不可变触发器的底层损坏，模拟文件损坏而非合法写入。
            connection.execute('DROP TRIGGER immutable_publication_update')
            connection.execute('UPDATE publication SET base_publication=? WHERE id=?', (ids[1], ids[0]))
        with self.database.read() as connection:
            connection.set_progress_handler(lambda: 1, 10000)
            with self.assertRaisesRegex(StorageError, 'lineage_invalid'):
                Publications(connection).rows(ids[1])


if __name__ == '__main__':
    unittest.main()
