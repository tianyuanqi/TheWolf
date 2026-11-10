"""一次性导入的故障、重复执行和输入冻结；只使用独占假数据根。"""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/migrations'))
from import_legacy import Importer
from backup_sqlite import backup
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.database import canonical
from pmi.market_data.storage.documents import Documents
from pmi.market_data.storage.facts import Facts
from pmi.market_data.storage.originals import Originals


class SyntheticImporter(Importer):
    fail = False

    def originals_for_price(self):
        self.originals.put(b'synthetic import original')

    def prices(self):
        facts = Facts(self.c)
        facts.instrument('synthetic-import', 'stock')
        facts.price('synthetic-import', {'trade_date': '2026-11-01', 'open': '1.00', 'high': '1.20',
            'low': '0.90', 'close': '1.10'}, unit='CNY', precision=2, price_type='unadjusted')
        if self.fail:
            raise RuntimeError('synthetic interruption before publication')

    def retired_prices(self):
        pass

    def activity(self):
        pass

    def stock(self):
        pass

    def etf(self):
        pass

    def other_objects(self):
        for root, item in self.manifest['roots'].items():
            for relative in item['files']:
                self.metadata_file(root, relative)
        super().other_objects()


class ImportTests(unittest.TestCase):
    def test_backup_restore_checks_all_columns_and_preserves_source(self):
        with TemporaryDirectory(prefix='wolf-backup-test-', dir='/private/tmp') as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir(mode=0o700)
            db = Database(source)
            db.initialize()
            with db.writer(), db.transaction() as connection:
                original = Originals(db).put(b'synthetic backup source')
                reference = Documents(connection).put({'original_id': original, 'state': 'synthetic', 'unknown': None})
            before = {str(file.relative_to(source)): (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns) for file in source.rglob('*') if file.is_file()}
            first = backup(source, root / 'backup')
            second = backup(root / 'backup', root / 'restored')
            self.assertTrue(first['passed'] and second['passed'])
            self.assertEqual(first['tables'], second['tables'])
            self.assertEqual(first['original_manifest_sha256'], second['original_manifest_sha256'])
            with Database(root / 'restored').read() as connection:
                self.assertEqual(Documents(connection).get(reference)['unknown'], None)
            self.assertEqual(Originals(Database(root / 'restored')).get(original), b'synthetic backup source')
            after = {str(file.relative_to(source)): (hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns) for file in source.rglob('*') if file.is_file()}
            self.assertEqual(before, after)
            with self.assertRaisesRegex(StorageError, 'new_disjoint_target'):
                backup(source, source / 'nested')
        self.assertFalse(root.exists())

    def test_interrupted_import_rolls_back_and_same_batch_resumes_without_duplicates(self):
        with TemporaryDirectory(prefix='wolf-import-test-', dir='/private/tmp') as temporary:
            root = Path(temporary)
            copies, target = root / 'copies', root / 'target'
            target.mkdir(mode=0o700)
            manifest = {'roots': {}}
            for key, relative, value in [('data', 'slice-002245-sina/overview-periodic-ledger.json', {'scope_id': 'synthetic-periodic'}),
                ('etf', 'store/initialized.json', {'scope': 'synthetic-etf'})]:
                file = copies / key / relative
                file.parent.mkdir(parents=True)
                raw = canonical(value)
                file.write_bytes(raw)
                manifest['roots'][key] = {'files': {relative: {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}}
            manifest['roots']['stock'] = {'files': {}}
            source_sha = hashlib.sha256(canonical(manifest)).hexdigest()
            validation = {'passed': True, 'denied': [], 'manifest_sha256': source_sha, 'validation': {'versions': []}}

            def importer():
                return SyntheticImporter(Database(target), copies, manifest, source_sha, validation, 'a' * 64, 'synthetic-batch')

            first = importer()
            first.fail = True
            with self.assertRaisesRegex(RuntimeError, 'synthetic interruption'), redirect_stdout(io.StringIO()):
                first.run()
            with Database(target).read() as connection:
                self.assertEqual(connection.execute('SELECT state FROM migration').fetchone()[0], 'preparing')
                self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT count(*) FROM original_object').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT count(*) FROM current_publication').fetchone()[0], 0)
            original_paths = list((target / 'objects').iterdir())
            self.assertEqual(len(original_paths), 1)
            with redirect_stdout(io.StringIO()):
                result = importer().run()
            self.assertEqual(result['counts']['price_row'], 1)
            self.assertEqual(result['counts']['original_object'], 1)
            self.assertEqual(list((target / 'objects').iterdir()), original_paths)
            before = {str(file.relative_to(target)): hashlib.sha256(file.read_bytes()).hexdigest() for file in target.rglob('*') if file.is_file()}
            with redirect_stdout(io.StringIO()):
                self.assertTrue(importer().run()['already_imported'])
            after = {str(file.relative_to(target)): hashlib.sha256(file.read_bytes()).hexdigest() for file in target.rglob('*') if file.is_file()}
            self.assertEqual(before, after)
            source = copies / 'etf/store/initialized.json'
            source.write_bytes(b'{"scope":"tampered"}')
            with self.assertRaisesRegex(StorageError, 'migration_source_changed'):
                importer().json('etf', 'store/initialized.json')
        self.assertFalse(root.exists())

    def test_source_price_and_adjustment_keep_exact_decimals_in_separate_rows(self):
        with TemporaryDirectory(prefix='wolf-independent-facts-', dir='/private/tmp') as temporary:
            db = Database(Path(temporary))
            db.initialize()
            with db.writer(), db.transaction() as connection:
                facts = Facts(connection)
                facts.instrument('synthetic:source', 'index')
                source = Originals(db).put(b'synthetic price source')
                row = {'trade_date': '2026-11-01', 'open': '1.20', 'high': '1.30', 'low': '1.00', 'close': '1.25',
                    'raw_values': {'open': '1.2000', 'high': '1.3000', 'low': '1.0000', 'close': '1.2500'}, 'locator': '$.fake[0]'}
                reference = facts.source_price('synthetic:source', source, row)
                self.assertEqual(Documents(connection).get(reference), row)
                self.assertEqual(connection.execute('SELECT count(*) FROM price_row').fetchone()[0], 0)
                adjustment = {'member_id': 'synthetic-etf', 'kind': 'normal', 'start': '2026-01-01', 'end': '2026-11-01',
                    'factor': '1', 'tail': '0', 'source_ids': [source], 'confirmed_at': '2026-11-02T00:00:00+00:00', 'confirmation': '仅假数据'}
                reference = facts.adjustment(adjustment)
                self.assertEqual(Documents(connection).get(reference), adjustment)
                self.assertEqual(connection.execute('SELECT typeof(factor),factor FROM adjustment').fetchone()[:], ('text', '1'))


if __name__ == '__main__':
    unittest.main()
