"""托管/独立启动入口ETF配置往返，默认禁用且旧公开身份不变。"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from pmi.managed_config import parse, service_arguments
from pmi.market_data.etf_flow.model import FlowError
import test_etf_flow_runtime as fixture

REPO = Path(__file__).resolve().parents[2]


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.RuntimeTests(methodName='test_read_does_not_repair_queued_and_explicit_replay_recovers_before_begin')
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        root = self.fixture.root
        for name in ('host', 'run'): (root/name).mkdir(mode=0o700)
        self.value = {'python': sys.executable, 'data_root': str(self.fixture.data), 'runtime_base': str(root/'run'),
            'service_port': 18080, 'browser_port': 18081}
        self.etf = {'root': str(self.fixture.data), 'configuration': str(self.fixture.paths[0]),
            'evidence': str(self.fixture.paths[1]), 'grant': str(self.fixture.paths[2]), 'write_enabled': False, 'refresh_revision': None}

    def test_optional_etf_keeps_old_descriptors_and_cli_roundtrip_identical(self):
        _, old, _ = parse(json.dumps(self.value), REPO)
        raw, config, _ = parse(json.dumps(self.value | {'etf_flow': self.etf}), REPO)
        self.addCleanup(config.market_data.close_updates); self.addCleanup(old.market_data.close_updates)
        self.assertEqual(old.public_descriptor(), config.public_descriptor())
        self.assertEqual(old.public_index_descriptor(), config.public_index_descriptor())
        args = service_arguments(raw); args[0] = 'describe-etf-config'
        response = subprocess.run([sys.executable, '-B', '-m', 'pmi.service', *args], capture_output=True, text=True, timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout), config.public_etf_descriptor())
        self.assertEqual(list((self.fixture.root/'host').iterdir()), [])
        self.assertEqual(list((self.fixture.root/'run').iterdir()), [])
        self.assertFalse(config.public_etf_descriptor()['write_enabled'])

    def test_invalid_overlap_missing_grant_and_frozen_file_change_rejected(self):
        for change in ({'root': str(self.fixture.root/'host')}, {'root': str(REPO)},
                       {'write_enabled': True, 'grant': None}, {'write_enabled': 'false'}, {'unknown': True}):
            with self.subTest(change=change), self.assertRaises((ValueError, FlowError)):
                parse(json.dumps(self.value | {'etf_flow': self.etf | change}), REPO)
        _, config, _ = parse(json.dumps(self.value | {'etf_flow': self.etf}), REPO)
        self.addCleanup(config.market_data.close_updates)
        self.fixture.paths[0].write_text('{}')  # 仅隔离文件；已有实例须拒绝原身份继续读取。
        with self.assertRaises(FlowError): config.market_data.etf_flow('current', 'isolated-instance')


if __name__ == '__main__': unittest.main()
