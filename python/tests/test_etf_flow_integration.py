"""干净基线迁入边界：缺省ETF关闭、旧接口拒绝且不生成金融文件。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from http_test_support import ReadClient, disk
from sqlite_fixture import initialize


class IntegrationTests(unittest.TestCase):
    def test_disabled_etf_preserves_overview_and_never_initializes(self):
        with tempfile.TemporaryDirectory(prefix='etf-integration-', dir='/private/tmp') as folder:
            root = Path(folder); initialize(root)
            client = ReadClient(root)
            self.addCleanup(client.config.market_data.close_updates)
            before = disk(root)
            main = client.request('/api/session/ready')
            self.assertEqual(main.status, 200)
            self.assertEqual(main.json()['contract_version'], '3.0.0')
            self.assertEqual(main.json()['identity_format'], 'wolf-config-v2')
            ready = client.request('/api/etf-flow/session')
            self.assertEqual(ready.status, 404)
            self.assertEqual(ready.json()['detail']['code'], 'etf_disabled')
            headers = {'X-Wolf-Expected-Config': client.config.etf_config_id}
            current = client.request('/api/etf-flow/current', headers=headers)
            self.assertEqual(current.status, 404)
            update = client.request('/api/etf-flow/update', 'POST', headers=headers | {'Content-Type': 'application/json'},
                                    body=json.dumps({'plan_id': 'a' * 64, 'expected_snapshot_id': None}).encode())
            self.assertEqual(update.status, 403)
            self.assertEqual(update.json()['detail']['code'], 'update_disabled')
            catalog = client.request('/api/index-series/catalog', headers={'X-Wolf-Expected-Config': client.config.index_config_id})
            self.assertEqual(catalog.status, 200)
            for route in ('/api/slice', '/api/slice/update', '/api/indices/000300', '/api/indices/000300/update',
                          '/api/stock-query/session', '/api/operations/retired-request'):
                for method in ('GET', 'POST', 'OPTIONS'):
                    with self.subTest(route=route, method=method):
                        response = client.request(route, method)
                        self.assertEqual(response.status, 404)
            self.assertEqual(disk(root), before)
            self.assertTrue((root/"facts.sqlite").is_file())

    def test_retired_cli_options_stay_rejected(self):
        with tempfile.TemporaryDirectory(prefix='etf-cli-boundary-', dir='/private/tmp') as folder:
            for flag, value in (('--slice-write', 'false'), ('--index-write', 'false'),
                                ('--index-write', 'sse:000001:price')):
                response = subprocess.run([sys.executable, '-B', '-m', 'pmi.service', 'describe-config',
                    '--data-root', folder, '--port', '18080', '--origin', 'http://127.0.0.1:18081', flag, value],
                    text=True, capture_output=True, timeout=10)
                self.assertNotEqual(response.returncode, 0)
                self.assertIn('unrecognized arguments', response.stderr)
                self.assertEqual(response.stdout, '')
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
