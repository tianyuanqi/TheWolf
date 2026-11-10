"""导出隔离真实回环HTTP响应供浏览器Client检查；不连接外部源。"""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from test_etf_flow_http import EtfHttpTests


def main():
    fixture = EtfHttpTests(methodName='test_ready_descriptor_current_update_both_views_evidence_and_replay')
    try:
        fixture.setUp()
        snapshot, parameters = fixture.publish()
        def get(path):
            result = fixture.client.get(path, headers=fixture.headers)
            fixture.assertEqual(result.status_code, 200, result.text)
            return result.json()
        path = '/api/etf-flow/snapshots/'+snapshot
        result = {'descriptor': fixture.config.public_etf_descriptor(), 'legacy': fixture.config.public_descriptor(),
            'ready': fixture.ready, 'current': get('/api/etf-flow/current'),
            'original': get(path+'?mode=original&period=60'), 'view': get(path+'?mode=current&period=60'),
            'operation': get('/api/etf-flow/operations/http-test-operation'), 'parameters': parameters}
        # 同一真实服务保存queued后模拟进程没开始执行；GET不修复，原POST明确恢复。
        params = {'expected_snapshot_id': result['current']['snapshot_id'], 'plan_id': result['current']['plan']['id']}
        with patch('pmi.market_data.etf_flow.runtime.threading.Thread.start'):
            queued = fixture.client.post('/api/etf-flow/update', headers=fixture.headers|{'X-Wolf-Request-Id':'http-recovery-test'}, json=params)
        fixture.assertEqual(queued.status_code, 202, queued.text)
        result['recovery'] = get('/api/etf-flow/operations/http-recovery-test')
        recovered = fixture.client.post('/api/etf-flow/update', headers=fixture.headers|{'X-Wolf-Request-Id':'http-recovery-test'}, json=params)
        fixture.assertEqual(recovered.status_code, 200, recovered.text)
        result['recovered'] = recovered.json()
        fixture.assertTrue(result['recovery']['recovery_required'])
        fixture.assertEqual(result['recovered']['state'], 'interrupted')
        Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        fixture.doCleanups()


if __name__ == '__main__': main()
