"""真实数据库结构上的隔离ETF发布、只读装配、独立字段修订及额度持久性。"""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from etf_flow_fixture import AT, END, stored_sample
from pmi.market_data.etf_flow.model import Input, digest
from pmi.market_data.etf_flow.repository import Repository
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.storage.journals import Journals
from pmi.market_data.storage.originals import Originals


class SqliteEtfTests(unittest.TestCase):
    def test_nav_group_proof_is_sql_only_and_one_changed_page_invalidates_it(self):
        from etf_flow_fixture import configuration
        from pmi.market_data.etf_flow.calendar import preceding_window
        from pmi.market_data.etf_flow.model import Configuration, canonical
        from pmi.market_data.etf_flow.sources import request_for
        from pmi.market_data.etf_flow.transport import Original
        from pmi.market_data.storage.etf_cache import Cache, verify_proofs
        with tempfile.TemporaryDirectory(prefix='wolf-sql-cache-', dir='/private/tmp') as directory:
            root = Path(directory)
            store = Store(root)
            store.initialize()
            config = Configuration.parse(configuration())
            member = config.pools[-1].members[0]
            dates = preceding_window(END, 21)
            requests = tuple(request_for(member, 'nav', dates[0], dates[-1], page=page) for page in (1, 2))
            cache = Cache(store, None, config)
            def save(page, days, replace=False):
                request = requests[page - 1]
                raw = canonical({'ErrCode': 0, 'PageIndex': page, 'PageSize': 20, 'TotalCount': 21,
                    'Data': {'LSJZList': [{'FSRQ': day, 'DWJZ': '1.0000'} for day in days]}})
                source = store.put(raw)
                receipt = store.put_json({'object_id': source, 'request_key': request.key, 'code': None})
                cache.save_response(Original(request, 'test', source, raw, AT, receipt), replace=replace)
            descending = list(reversed(dates))
            with store.writer():
                save(1, descending[:20])
                self.assertTrue(all(value is None for value in cache.reusable_responses(requests).values()))
                save(2, descending[20:])
            with patch.object(Originals, 'get', side_effect=AssertionError('普通计划不得读原件')):
                self.assertTrue(all(value is not None for value in cache.reusable_responses(requests).values()))
            with store.writer():
                save(2, descending[:1], replace=True)
            with patch.object(Originals, 'get', side_effect=AssertionError('普通计划不得读原件')):
                self.assertTrue(all(value is None for value in cache.reusable_responses(requests).values()))
            with store.database.read() as connection:
                verify_proofs(store.database, connection)
            with store.database.writer(), store.database.transaction() as connection:
                connection.execute("DELETE FROM state WHERE domain_id='etf' AND key LIKE 'response-proof:%'")
            from pmi.market_data.storage import StorageError
            with store.database.read() as connection, self.assertRaisesRegex(StorageError, 'cache_proof_missing'):
                verify_proofs(store.database, connection)
        self.assertFalse(root.exists())

    def test_full_publication_and_sql_only_fixed_reads(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-etf-', dir='/private/tmp') as directory:
            root = Path(directory)
            store = Store(root)
            store.initialize()
            repository = Repository(store)
            with store.writer():
                config, inputs, evidence, dates = stored_sample(store)
                first = repository.publish(config, evidence, inputs, end=END, selection_at=AT,
                                           operation_key=digest('first'), expected=None)
            with store.database.read() as connection:
                before = connection.execute('SELECT count(*) FROM daily_metric').fetchone()[0]
            changed = deepcopy(inputs[-1].raw)
            changed['fields']['nav']['value'] = '2.0000'
            changed['revision_reason'] = '隔离修订'
            with store.writer():
                second = repository.publish(config, evidence, inputs[:-1] + (Input.parse(changed),), end=END,
                    selection_at=AT, operation_key=digest('second'), expected=first)
            with store.database.read() as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM daily_metric').fetchone()[0], before + 1)
                self.assertEqual(connection.execute('SELECT count(*) FROM publication_row WHERE publication_id=?', (second,)).fetchone()[0], 1)
            with patch.object(Originals, 'get', side_effect=AssertionError('普通读取不许读原件')):
                old = repository.load(first, verify=False)
                new = repository.load(second, verify=False)
                self.assertEqual(str(old.inputs[-1].value('nav')), '1')
                self.assertEqual(str(new.inputs[-1].value('nav')), '2.0000')
                self.assertEqual(len(new.admissions[0].input_refs), 321)
                self.assertEqual(repository.evaluations(old, 'current', None)[END]['amount'], '40')
            self.assertEqual(Store(root).scope, store.scope)
        self.assertFalse(root.exists())

    def test_journal_old_ids_and_stale_cas(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-journal-', dir='/private/tmp') as directory:
            root = Path(directory)
            store = Store(root)
            store.initialize()
            key = digest('quota')
            with store.writer():
                first = store.write_journal(key, {'used': 1}, None)
                second = store.write_journal(key, {'used': 2}, first)
                with self.assertRaises(ValueError):
                    store.write_journal(key, {'used': 0}, first)
            self.assertEqual(store.get_json(first), {'previous': None, 'value': {'used': 1}})
            self.assertEqual(store.get_json(second)['previous'], first)
            self.assertEqual(Store(root).journal(key), (second, {'used': 2}))
        self.assertFalse(root.exists())
