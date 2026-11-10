"""显式本地操作仅导入可复核原件，初始化/额度/重复导入均在新隔离根。"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from etf_flow_fixture import AT, END, configuration
from pmi.market_data.etf_flow.budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from pmi.market_data.etf_flow.cli import initialize, add_grant, import_originals
from pmi.market_data.etf_flow.model import Configuration, FlowError, canonical, digest
from pmi.market_data.etf_flow.sources import SHARES_QUERY
from pmi.market_data.storage.etf_store import Store


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='etf-cli-test-', dir='/private/tmp')
        self.root = Path(self.tmp.name); self.data = self.root/'data'; self.data.mkdir(mode=0o700)
        self.config = Configuration.parse(configuration())
        self.member = self.config.pools[0].members[0]
        self.configuration = self.save('configuration.json', self.config.raw)
        now = datetime.now(timezone.utc)
        self.grant = {'id': 'test-only-grant', 'confirmation': '只供隔离测试，无真实读取权限',
            'confirmed_at': (now-timedelta(minutes=1)).isoformat(), 'expires_at': (now+timedelta(minutes=10)).isoformat(),
            'members': [self.member.id], 'start': END, 'end': END, 'domains': ['query.sse.com.cn'],
            'max_requests': 1, 'max_bytes': 1024, 'response_limit': 1024, 'interval_seconds': 3, 'timeout_seconds': 1}
        self.grant_path = self.save('grant.json', self.grant)
        self.manifest = {'format': 'etf-flow-import-v1', 'revision': None, 'requests': [], 'evidence_originals': []}

    def save(self, name, value):
        path = self.root/name; path.write_bytes(canonical(value)); path.chmod(0o600); return path

    def tearDown(self):
        self.tmp.cleanup(); self.assertFalse(self.root.exists())

    def inputs(self):
        body = {'sqlId': SHARES_QUERY, 'result': [{'SEC_CODE': self.member.code, 'STAT_DATE': END, 'TOT_VOL': '12.34'}]}
        path = self.save('original.json', body)
        self.manifest['requests'] = [{'member_id': self.member.id, 'kind': 'shares', 'start': END, 'end': END,
            'page': 1, 'path': str(path), 'object_id': hashlib.sha256(path.read_bytes()).hexdigest(), 'retrieved_at': AT}]
        self.manifest['evidence_originals'] = [{'path': str(path), 'object_id': self.manifest['requests'][0]['object_id']}]
        return self.save('import.json', self.manifest)

    def test_initialize_is_explicit_and_reinitialization_never_resets_budget(self):
        result = initialize(self.data, self.grant_path, '仅本测试授权')
        self.assertFalse(result['published'])
        store = Store(self.data); before = Budget(store, Grant.parse(self.grant)).usage()
        with self.assertRaises(FlowError): initialize(self.data, self.grant_path, '重复')
        with self.assertRaises(FlowError): add_grant(self.data, self.grant_path, '重复')
        self.assertEqual(Budget(store, Grant.parse(self.grant)).usage(), before)
        self.assertIsNone(store.current_id())
        changed = deepcopy(self.grant); changed['id'] += '-next'
        second = self.save('next-grant.json', changed)
        add_grant(self.data, second, '测试另一份单独授权')
        self.assertEqual(Budget(store, Grant.parse(self.grant)).usage(), before)

    def test_import_reparses_reuses_and_repairs_receipt_without_duplicate_facts(self):
        initialize(self.data, self.grant_path, '仅测试')
        manifest = self.inputs()
        # 原件回执已落盘、规范输入还没保存就中断：同清单可恢复，不需要重新取数。
        with patch.object(Cache, 'save_inputs', side_effect=OSError('isolated interruption')):
            with self.assertRaises(OSError): import_originals(self.data, self.configuration, manifest, '仅测试')
        result = import_originals(self.data, self.configuration, manifest, '仅测试重放')
        self.assertEqual((result['imported_requests'], result['reused_requests']), (0, 1))
        store = Store(self.data)
        before = Cache(store, None, self.config).inputs()
        self.assertEqual(len(before), 1); self.assertEqual(before[0].value('shares'), 123400)
        import_originals(self.data, self.configuration, manifest, '仅测试再次重放')
        self.assertEqual(Cache(store, None, self.config).inputs(), before)
        self.assertIsNone(store.current_id()); self.assertEqual(Budget(store, Grant.parse(self.grant)).usage()['requests'], 0)

    def test_invalid_or_conflicting_original_and_unresolved_operation_are_rejected(self):
        initialize(self.data, self.grant_path, '仅测试'); manifest = self.inputs()
        original = deepcopy(self.manifest)
        self.manifest['requests'][0]['object_id'] = 'a'*64
        manifest = self.save('import.json', self.manifest)
        store = Store(self.data); before = {p.name for p in (self.data/'objects').iterdir()}
        with self.assertRaises(FlowError): import_originals(self.data, self.configuration, manifest, '仅测试')
        self.assertEqual(before, {p.name for p in (self.data/'objects').iterdir()})
        self.manifest = original; manifest = self.save('import.json', original)
        with store.writer():
            store.write_journal(digest({'format': 'etf-flow-operations-v1', 'scope': store.scope}),
                {'operations': [{'state': 'queued', 'lease_closed': False,
                    'operation_key': digest('synthetic-unresolved'), 'snapshot_id': None}]}, None)
        with self.assertRaises(FlowError): import_originals(self.data, self.configuration, manifest, '仅测试')
        with self.assertRaises(FlowError): add_grant(self.data, self.grant_path, '仅测试')

    def test_import_identity_is_bound_before_receipt_interruption_and_old_original_retained(self):
        initialize(self.data, self.grant_path, '仅测试'); manifest = self.inputs()
        with patch.object(Cache, 'save_inputs', side_effect=OSError('回执后中断')):
            with self.assertRaises(OSError): import_originals(self.data, self.configuration, manifest, '仅测试')
        store = Store(self.data)
        original_id = self.manifest['requests'][0]['object_id']; original = store.get(original_id)
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*') if p.is_file()}
        changed = deepcopy(self.config.raw)
        other = configuration('multiple')['pool_versions'][0]['members'][1]
        changed['pool_versions'][0]['members'][0].update(code=other['code'], name=other['name'])
        self.save('configuration.json', changed)
        # 即使仅导入披露原件，不含可重新解析的行情，也不能借此重绑已用配置。
        empty = self.save('empty-import.json', {**self.manifest, 'requests': []})
        with self.assertRaisesRegex(FlowError, 'config_history_changed'):
            import_originals(self.data, self.configuration, empty, '仅测试')
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.data.rglob('*') if p.is_file()})
        self.save('configuration.json', self.config.raw)
        import_originals(self.data, self.configuration, manifest, '仅测试恢复')
        self.assertEqual(store.get(original_id), original)
        self.assertEqual(Cache(store, None, self.config).inputs()[0].fields['shares'].source.object_id, original_id)
        self.assertIsNone(store.current_id())


if __name__ == '__main__': unittest.main()
