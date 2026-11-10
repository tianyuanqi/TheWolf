"""恢复验证器只在自有假数据上证明映射和读边界，绝不接触真实源。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[2] / 'tools/migrations'
sys.path.insert(0, str(TOOLS))
from identity_mapping import IdentityMapping
from read_boundary import BoundaryError, ReadBoundary, readonly_database


def worker(root: Path):
    # 固定离线验证器原字节；迁移后产品不得恢复旧读取实现。
    import importlib
    import importlib.util
    import pmi.market_data
    frozen = TOOLS / 'legacy_validation'
    manifest = json.loads((frozen / 'manifest.json').read_bytes())
    for label, module_name in [('etf_store', 'pmi.market_data.etf_flow.store'),
                              ('etf_options', 'pmi.market_data.etf_flow.options'),
                              ('periodic_budget', 'pmi.market_data.periodic_budget')]:
        path = frozen / (label + '.py')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['files'][path.name]['sha256']
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        package, name = module_name.rsplit('.', 1)
        setattr(importlib.import_module(package), name, module)
    from etf_flow_fixture import stored_sample
    from pmi.market_data.etf_flow.budget import Budget, Grant
    from pmi.market_data.etf_flow.store import Store
    from pmi.market_data.etf_flow.options import Options, Settings
    from pmi.market_data.etf_flow.model import canonical, FlowError
    from pmi.market_data import periodic_budget
    source = root / 'original'
    source.mkdir(mode=0o700)
    for name in ('etf', 'price', 'activity'):
        (source / name).mkdir(mode=0o700)
    store = Store(source / 'etf')
    store.initialize()
    with store.writer():
        config, inputs, evidence, dates = stored_sample(store)
    grant = Grant.parse({'id': 'restore-only-test', 'confirmed_at': '2026-11-05T11:00:00+08:00',
        'confirmation': '假数据只验证恢复，禁止真实取数', 'expires_at': '2026-11-06T12:00:00+08:00',
        'members': [inputs[0].member_id], 'start': dates[0], 'end': dates[-1],
        'domains': ['www.sse.com.cn'], 'max_requests': 1, 'max_bytes': 100,
        'response_limit': 100, 'interval_seconds': 3, 'timeout_seconds': 1})
    for name, value in (('config', config.raw), ('evidence', evidence.raw), ('grant', grant.raw)):
        file = source / (name + '.json')
        file.write_bytes(canonical(value))
        file.chmod(0o600)
    with store.writer():
        Budget(store, grant).initialize()
    periodic_budget.initialize(source / 'price', source / 'activity')
    old_settings = Settings(Options(source / 'etf', source / 'config.json', source / 'evidence.json', source / 'grant.json'))
    old_write_identity = old_settings.identity(True)
    old_scope = periodic_budget.scope_id(source / 'price', source / 'activity')
    with sqlite3.connect(source / 'read.sqlite') as connection:
        connection.execute('CREATE TABLE example(value TEXT)')
        connection.execute('INSERT INTO example VALUES (?)', ('synthetic',))
    copy = root / 'restored'
    bad_scope, bad_quota = root / 'bad-scope', root / 'bad-quota'
    for target in (copy, bad_scope, bad_quota):
        shutil.copytree(source, target)
    (bad_scope / 'etf/initialized.json').write_bytes(canonical({'format': 'etf-flow-store-v1', 'scope': '0' * 64}))
    file = bad_quota / 'price' / periodic_budget.LEDGER
    value = json.loads(file.read_bytes())
    value['days']['2026-11-05'] = {'requests': 1, 'bytes': 100}
    file.write_bytes(canonical(value))
    output = root / 'report.json'
    boundary = ReadBoundary(copies=[copy, bad_scope, bad_quota], originals=[source],
        code=[Path(sys.base_prefix), Path(sys.prefix), Path(__file__).resolve().parents[2]], output=output)
    boundary.install()
    tests = []

    def rejects(name, action, errors=(BoundaryError,)):
        try:
            action()
        except errors:
            tests.append(name)
            return
        raise AssertionError(name + ' unexpectedly passed')

    rejects('unmapped_etf_rejected', lambda: Store(copy / 'etf').initialized, (FlowError,))
    rejects('unmapped_periodic_rejected', lambda: periodic_budget.Budget(copy / 'price', copy / 'activity', periodic_budget.PeriodicOptions()), (periodic_budget.BudgetError,))
    mapping = IdentityMapping({str(copy): str(source)})
    with mapping.installed():
        assert Store(copy / 'etf').initialized
        settings = Settings(Options(copy / 'etf', copy / 'config.json', copy / 'evidence.json', copy / 'grant.json'))
        assert settings.id == old_settings.id
        assert settings.identity(True) == old_write_identity
        assert periodic_budget.Budget(copy / 'price', copy / 'activity', periodic_budget.PeriodicOptions()).scope == old_scope
        assert Budget(Store(copy / 'etf'), grant).read()[1]['attempts'] == []
        tests.append('mapped_all_three_identities_preserved')
    with IdentityMapping({str(copy): str(source) + '-wrong'}).installed():
        rejects('wrong_mapping_rejected', lambda: Store(copy / 'etf').initialized, (FlowError,))
    with IdentityMapping({str(bad_scope): str(source)}).installed():
        rejects('tampered_scope_rejected', lambda: Store(bad_scope / 'etf').initialized, (FlowError,))
    with IdentityMapping({str(bad_quota): str(source)}).installed():
        rejects('tampered_quota_rejected', lambda: periodic_budget.Budget(bad_quota / 'price', bad_quota / 'activity', periodic_budget.PeriodicOptions()), (periodic_budget.BudgetError,))
    rejects('original_file_read_rejected', lambda: (source / 'config.json').read_bytes())
    rejects('original_stat_rejected', lambda: (source / 'config.json').stat())
    rejects('original_list_rejected', lambda: list(source.iterdir()))
    rejects('copy_write_rejected', lambda: (copy / 'config.json').write_bytes(b'invalid'))
    directory = os.open(copy, os.O_RDONLY | os.O_DIRECTORY)
    try:
        descriptor = os.open('config.json', os.O_RDONLY, dir_fd=directory)
        os.close(descriptor)
        tests.append('relative_descriptor_read_supported')
        rejects('relative_original_read_rejected', lambda: os.open('../original/config.json', os.O_RDONLY, dir_fd=directory))
    finally:
        os.close(directory)
    rejects('sqlite_original_rejected', lambda: sqlite3.connect((source / 'read.sqlite').as_uri() + '?mode=ro', uri=True))
    rejects('sqlite_writable_rejected', lambda: sqlite3.connect(copy / 'read.sqlite'))
    with readonly_database(copy / 'read.sqlite') as connection:
        assert connection.execute('SELECT value FROM example').fetchone()[0] == 'synthetic'
        rejects('sqlite_mutation_rejected', lambda: connection.execute("DELETE FROM example"), (sqlite3.DatabaseError,))
    rejects('network_rejected', lambda: socket.getaddrinfo('example.invalid', 443))
    rejects('subprocess_rejected', lambda: subprocess.run([sys.executable, '-c', 'pass']))
    with output.open('x') as stream:
        json.dump({'passed': True, 'checks': tests, 'denied': boundary.denied}, stream)
    return 0


class LegacyRestoreTests(unittest.TestCase):
    def test_identity_mapping_and_boundaries_in_isolated_process(self):
        with tempfile.TemporaryDirectory(prefix='wolf-restore-boundary-', dir='/private/tmp') as temporary:
            root = Path(temporary)
            result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root)],
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / 'report.json').read_bytes())
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['checks']), 17)
            self.assertGreaterEqual(len(report['denied']), 9)
            self.assertEqual((root / 'original/config.json').read_bytes(), (root / 'restored/config.json').read_bytes())
            self.assertEqual((root / 'original/read.sqlite').read_bytes(), (root / 'restored/read.sqlite').read_bytes())
        self.assertFalse(root.exists())


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        raise SystemExit(worker(Path(sys.argv[2])))
    unittest.main()
