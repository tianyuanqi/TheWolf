"""独审三项反例及关联边界；全部使用独立假配置、新根与禁止联网的来源替身。"""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from etf_flow_fixture import AT, END, configuration, stored_sample
from pmi.market_data.etf_flow.budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.model import Configuration, FlowError, Input, canonical
from pmi.market_data.etf_flow.options import Options
from pmi.market_data.etf_flow.runtime import Runtime
from pmi.market_data.etf_flow.sources import QUOTE_QUERY
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.etf_flow.transport import Original


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='etf-revision-test-', dir='/private/tmp')
        self.root = Path(self.tmp.name); self.data = self.root/'data'; self.data.mkdir(mode=0o700)
        self.store = Store(self.data); self.store.initialize()
        self.now = datetime.fromisoformat(AT); self.runtimes = []; self.calls = []
        self.network = patch.object(socket.socket, 'connect', side_effect=AssertionError('隔离测试禁止联网'))
        self.network.start()
        with self.store.writer():
            self.config, self.rows, self.evidence, self.dates = stored_sample(self.store)
        self.member = self.config.pools[-1].members[0]
        self.paths = [self.root/n for n in ('config.json', 'evidence.json', 'grant.json')]
        grant = {'id': 'isolated-review-fix', 'confirmation': '仅隔离反例，无真实取数授权',
            'confirmed_at': (self.now-timedelta(minutes=1)).isoformat(), 'expires_at': (self.now+timedelta(days=1)).isoformat(),
            'members': [self.member.id], 'start': self.dates[0], 'end': END,
            'domains': ['query.sse.com.cn', 'api.fund.eastmoney.com'], 'max_requests': 8, 'max_bytes': 32768,
            'response_limit': 4096, 'interval_seconds': 3, 'timeout_seconds': 1}
        for path, value in zip(self.paths, (self.config.raw, self.evidence.raw, grant)):
            path.write_bytes(canonical(value)); path.chmod(0o600)
        with self.store.writer(): Budget(self.store, Grant.parse(grant), lambda: self.now).initialize()
        self.options = Options(self.data, *self.paths, write_enabled=True)

    def tearDown(self):
        try:
            for runtime in self.runtimes: self.assertTrue(runtime.close(5))
            self.tmp.cleanup(); self.assertFalse(self.root.exists())
        finally: self.network.stop()

    def prepare(self, missing=()):
        altered = []
        for row in self.rows:
            raw = deepcopy(row.raw)
            for on, field in missing:
                if row.date == on: raw['fields'].pop(field)
            altered.append(Input.parse(raw))
        with self.store.writer(): Cache(self.store, None, self.config).save_inputs(tuple(altered))
        return self.restart()

    def restart(self):
        runtime = Runtime(self.options, clock=lambda: self.now)
        self.runtimes.append(runtime); return runtime

    def fetch(self, runtime, bodies):
        def run(request, key):
            self.now += timedelta(seconds=4)
            self.calls.append(request)
            attempt = runtime.budget.charge(request, key)
            raw = canonical(bodies(request))
            source = runtime.budget.settle(attempt, raw, True)
            receipt = runtime.store.put_json({'object_id': source, 'request_key': request.key, 'code': None})
            return Original(request, attempt, source, raw, self.now.isoformat(), receipt)
        return patch.object(runtime.transport, 'fetch', side_effect=run)

    def run_update(self, runtime, request_id, bodies):
        plan = runtime.plan(); parameters = {'plan_id': plan.id, 'expected_snapshot_id': plan.raw['expected_snapshot_id']}
        with self.fetch(runtime, bodies):
            status, _ = runtime.start(request_id, parameters, 'isolated-instance')
            self.assertEqual(status, 202); runtime._worker.join(20)
            self.assertFalse(runtime._worker.is_alive())
        return runtime.operation(request_id, 'isolated-instance'), parameters

    @staticmethod
    def nav(items, page=1, total=None):
        return {'ErrCode': 0, 'PageIndex': page, 'PageSize': 20, 'TotalCount': len(items) if total is None else total,
                'Data': {'LSJZList': [{'FSRQ': on, 'DWJZ': '1.0000'} for on in items]}}

    def test_identity_replacement_before_first_publication_rejected_and_append_allowed(self):
        runtime = self.prepare(); cached_before = runtime.cache.inputs(); self.assertIsNone(self.store.current_id()); runtime.close()
        changed = deepcopy(self.config.raw)
        replacement = configuration('multiple')['pool_versions'][0]['members'][1]
        changed['pool_versions'][0]['members'][0].update(code=replacement['code'], name=replacement['name'])
        self.paths[0].write_bytes(canonical(changed))
        with self.assertRaisesRegex(FlowError, 'config_history_changed'):
            self.restart().plan()
        appended = deepcopy(self.config.raw); new = deepcopy(appended['pool_versions'][-1])
        new.update(version='test-pool-appended', effective_date='2026-11-05', confirmed_at=AT)
        added = deepcopy(replacement); added['enabled_date'] = '2026-11-05'; new['members'].append(added)
        appended['pool_versions'].append(new); self.paths[0].write_bytes(canonical(appended))
        latest = self.restart(); self.assertEqual(len(latest.plan().raw['members']), 2)
        self.assertEqual([r.hash for r in latest.cache.inputs()], [r.hash for r in cached_before])
        self.assertIsNone(self.store.current_id())

    def test_empty_nav_rechecked_only_by_new_explicit_request_after_restart(self):
        runtime = self.prepare(((END, 'nav'),))
        first, parameters = self.run_update(runtime, 'first', lambda r: self.nav([]))
        self.assertEqual(first['state'], 'completed'); old = first['snapshot_id']; old_bytes = self.store.get(old)
        runtime.close(); runtime = self.restart()
        with patch.object(runtime.transport, 'fetch', side_effect=AssertionError('GET和原请求重放不准出站')):
            runtime.current('isolated-instance')
            status, replay = runtime.start('first', parameters, 'isolated-instance')
            self.assertEqual(status, 200); self.assertEqual(replay['snapshot_id'], old)
        self.assertEqual(len(runtime.plan().network), 1)
        second, _ = self.run_update(runtime, 'explicit-next', lambda r: self.nav([END]))
        self.assertEqual(second['state'], 'completed'); self.assertEqual(len(self.calls), 2)
        result = runtime.repository.load(second['snapshot_id'])
        self.assertEqual(result.calculator.metrics(self.member.id, END)['amount'], '40.0000')
        self.assertEqual(runtime.budget.usage()['requests'], 2)
        self.assertEqual(self.store.get(old), old_bytes)
        self.assertIsNone(runtime.repository.load(old).calculator.metrics(self.member.id, END)['nav'])

    def test_optional_empty_quote_keeps_core_admission_and_amount(self):
        runtime = self.prepare(tuple((END, f) for f in ('close', 'turnover', 'volume')))
        result, _ = self.run_update(runtime, 'quote-empty', lambda r: {'sqlId': QUOTE_QUERY, 'result': []})
        self.assertEqual(result['state'], 'completed')
        loaded = runtime.repository.load(result['snapshot_id'])
        metric = loaded.calculator.metrics(self.member.id, END)
        self.assertEqual(metric['amount'], '40'); self.assertIsNone(metric['close']); self.assertIsNone(metric['turnover'])
        self.assertEqual(len(loaded.calculator.admissions), 1)
        self.assertEqual(len(runtime.plan().network), 1, '下一次明确更新仍可检查缺行情')

    def test_partial_nav_pages_can_fill_missing_edges_without_rewriting_old_snapshot(self):
        from urllib.parse import parse_qs, urlsplit
        dates = self.dates[-22:]; runtime = self.prepare(tuple((d, 'nav') for d in dates))
        def response(request, complete):
            page = int(parse_qs(urlsplit(request.url).query)['pageIndex'][0])
            available = list(reversed(dates if complete else dates[1:-1]))
            return self.nav(available[(page-1)*20:page*20], page, len(available))
        first, _ = self.run_update(runtime, 'partial', lambda r: response(r, False))
        self.assertEqual(first['state'], 'completed'); old = self.store.get(first['snapshot_id'])
        self.assertEqual(len(runtime.plan().network), 2)
        second, _ = self.run_update(runtime, 'fill-edges', lambda r: response(r, True))
        self.assertEqual(second['state'], 'completed'); self.assertEqual(len(self.calls), 4)
        latest = runtime.repository.load(second['snapshot_id'])
        self.assertTrue(all(latest.calculator.metrics(self.member.id, d)['nav'] is not None for d in dates))
        self.assertEqual(self.store.get(first['snapshot_id']), old)

    def test_optional_quote_rejections_still_fail_and_keep_existing_snapshot(self):
        runtime = self.prepare(tuple((END, f) for f in ('close', 'turnover', 'volume')))
        first, _ = self.run_update(runtime, 'empty-valid', lambda r: {'sqlId': QUOTE_QUERY, 'result': []})
        self.assertEqual(first['state'], 'completed'); previous = first['snapshot_id']
        valid = {'SEC_CODE': self.member.code, 'TX_DATE': END.replace('-', ''), 'DATE_TYPE': 'D',
                 'CLOSE_PRICE': '1.010', 'TRADE_AMT': '0.05', 'TRADE_VOL': '0.04'}
        other = configuration('multiple')['pool_versions'][0]['members'][1]
        bodies = [
            {'sqlId': QUOTE_QUERY, 'result': [], 'actionErrors': ['拒绝']},
            {'sqlId': QUOTE_QUERY, 'result': None},
            {'sqlId': QUOTE_QUERY, 'result': [{**valid, 'SEC_CODE': other['code']}]},
            {'sqlId': QUOTE_QUERY, 'result': [{**valid, 'TX_DATE': self.dates[-2].replace('-', '')}]},
            {'sqlId': QUOTE_QUERY, 'result': [{**valid, 'TRADE_AMT': '0.001'}]},
        ]
        for i, body in enumerate(bodies):
            result, _ = self.run_update(runtime, 'bad-quote-'+str(i), lambda r, body=body: body)
            self.assertEqual(result['state'], 'failed'); self.assertEqual(self.store.current_id(), previous)
        self.assertEqual(len(self.calls), 6, '每个明确新请求只有一次；失败不自动重试')

    def test_failure_before_publication_keeps_bound_cache_identity(self):
        from pmi.market_data.etf_flow.sources import SHARES_QUERY
        runtime = self.prepare(((END, 'shares'), (END, 'close')))
        def response(request):
            if request.kind == 'shares':
                return {'sqlId': SHARES_QUERY, 'result': [{'SEC_CODE': self.member.code, 'STAT_DATE': END, 'TOT_VOL': '2.00'}]}
            raise FlowError('etf_http_rejected')
        failed, _ = self.run_update(runtime, 'fails-after-shares', response)
        self.assertEqual(failed['state'], 'failed'); self.assertEqual(failed['reason'], 'etf_http_rejected')
        self.assertIsNone(self.store.current_id())
        last = next(row for row in runtime.cache.inputs() if row.date == END)
        original = self.store.get(last.fields['shares'].source.object_id)
        self.assertIn(self.member.code.encode(), original)
        changed = deepcopy(self.config.raw); changed['pool_versions'][0]['members'][0]['name'] += '替换版本'
        runtime.close(); self.paths[0].write_bytes(canonical(changed))
        with self.assertRaisesRegex(FlowError, 'config_history_changed'): self.restart().plan()
        self.assertEqual(self.store.get(last.fields['shares'].source.object_id), original)

    def test_cross_page_duplicate_failure_can_be_rechecked_after_restart(self):
        import hashlib
        from urllib.parse import parse_qs, urlsplit
        dates = self.dates[-21:]; descending = list(reversed(dates))
        runtime = self.prepare(tuple((d, 'nav') for d in dates))
        def response(request, broken):
            page = int(parse_qs(urlsplit(request.url).query)['pageIndex'][0])
            values = descending[:20] if page == 1 else [descending[19] if broken else descending[20]]
            return self.nav(values, page, 21)
        failed, parameters = self.run_update(runtime, 'bad-pages', lambda r: response(r, True))
        self.assertEqual((failed['state'], failed['reason']), ('failed', 'etf_source_count_mismatch'))
        originals = {row['object_id']: runtime.store.get(row['object_id']) for r in self.calls if (row := runtime.cache.response(r))}
        runtime.close(); runtime = self.restart()
        def hashes(): return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*') if p.is_file()}
        before = hashes()
        with patch.object(runtime.transport, 'fetch', side_effect=AssertionError('GET和同请求重放不准出站')):
            runtime.current('isolated-instance')
            status, replay = runtime.start('bad-pages', parameters, 'isolated-instance')
            self.assertEqual(status, 200); self.assertEqual(replay['state'], 'failed')
        self.assertEqual(hashes(), before)
        self.assertEqual(len(runtime.plan().network), 2)
        completed, _ = self.run_update(runtime, 'corrected-pages', lambda r: response(r, False))
        self.assertEqual(completed['state'], 'completed'); self.assertEqual(len(self.calls), 4)
        self.assertEqual(runtime.budget.usage()['requests'], 4)
        latest = runtime.repository.load(completed['snapshot_id'])
        self.assertTrue(all(latest.calculator.metrics(self.member.id, d)['nav'] == '1.0000' for d in dates))
        self.assertEqual({key: runtime.store.get(key) for key in originals}, originals)
        self.assertEqual(runtime.operation('bad-pages', 'isolated-instance')['state'], 'failed')

    def unbound_import_rejections(self, *, response_only):
        """精确构造旧格式状态而不创建绑定；空、仅证据及正常导入都不能认领。"""
        import hashlib
        from dataclasses import asdict
        from pmi.market_data.etf_flow.cli import import_originals
        from pmi.market_data.etf_flow.sources import SHARES_QUERY, request_for
        cache = Cache(self.store, None, self.config)
        request = request_for(self.member, 'shares', END, END)
        raw = canonical({'sqlId': SHARES_QUERY, 'result': [{'SEC_CODE': self.member.code, 'STAT_DATE': END, 'TOT_VOL': '2.00'}]})
        with self.store.writer():
            source = self.store.put(raw)
            if response_only:
                receipt = self.store.put_json({'object_id': source, 'request_key': request.key, 'code': None})
                self.store.write_journal(cache.response_key(request), {'request': asdict(request), 'object_id': source,
                    'retrieved_at': AT, 'receipt_id': receipt}, None)
            else:
                self.store.write_journal(cache.inputs_key, {'input_refs': [self.store.put_json(row.raw) for row in self.rows]}, None)
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*') if p.is_file()}
        other = configuration('multiple')['pool_versions'][0]['members'][1]
        changed = deepcopy(self.config.raw); changed['pool_versions'][0]['members'][0].update(code=other['code'], name=other['name'])
        self.paths[0].write_bytes(canonical(changed))
        new_raw = canonical({'sqlId': SHARES_QUERY, 'result': [{'SEC_CODE': other['code'], 'STAT_DATE': END, 'TOT_VOL': '3.00'}]})
        original_path = self.root/'new-original.json'; original_path.write_bytes(new_raw); original_path.chmod(0o600)
        source_id = hashlib.sha256(new_raw).hexdigest()
        cases = [([], []), ([], [{'path': str(original_path), 'object_id': source_id}]),
                 ([{'member_id': self.member.id, 'kind': 'shares', 'start': END, 'end': END, 'page': 1,
                    'path': str(original_path), 'object_id': source_id, 'retrieved_at': AT}], [])]
        for requests, evidence in cases:
            with self.subTest(response_only=response_only, requests=len(requests), evidence=len(evidence)):
                manifest = self.root/'import.json'; manifest.write_bytes(canonical({'format': 'etf-flow-import-v1', 'revision': None,
                    'requests': requests, 'evidence_originals': evidence})); manifest.chmod(0o600)
                with self.assertRaisesRegex(FlowError, 'cache_configuration_missing'):
                    import_originals(self.data, self.paths[0], manifest, '仅隔离测试，不授权迁移')
                self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*') if p.is_file()})
                self.assertIsNone(self.store.journal(cache.configuration_key)[0])
        self.assertEqual(self.store.get(source), raw)
        with self.assertRaisesRegex(FlowError, 'cache_configuration_missing'): self.restart().plan()

    def test_unbound_input_cache_cannot_be_claimed_by_any_import(self):
        self.unbound_import_rejections(response_only=False)

    def test_unbound_response_cache_cannot_be_claimed_by_any_import(self):
        self.unbound_import_rejections(response_only=True)

    def test_complete_nav_group_reused_after_input_cache_interruption(self):
        from urllib.parse import parse_qs, urlsplit
        dates = self.dates[-21:]; descending = list(reversed(dates))
        runtime = self.prepare(tuple((d, 'nav') for d in dates))
        def response(request):
            page = int(parse_qs(urlsplit(request.url).query)['pageIndex'][0])
            return self.nav(descending[(page-1)*20:page*20], page, 21)
        with patch.object(runtime.cache, 'save_inputs', side_effect=OSError('原件完整但输入缓存保存中断')):
            failed, _ = self.run_update(runtime, 'complete-pages', response)
        self.assertEqual(failed['state'], 'failed'); self.assertIsNone(self.store.current_id())
        runtime.close(); runtime = self.restart(); plan = runtime.plan()
        self.assertEqual(len(plan.requests), 2); self.assertEqual(plan.network, ())
        restored, _ = self.run_update(runtime, 'explicit-reuse', lambda r: self.fail('完整已核验页不应重复出站'))
        self.assertEqual(restored['state'], 'completed'); self.assertEqual(len(self.calls), 2)
        self.assertEqual(runtime.budget.usage()['requests'], 2)


if __name__ == '__main__': unittest.main()
