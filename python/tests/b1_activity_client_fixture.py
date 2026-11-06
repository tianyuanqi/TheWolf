"""输出真实ASGI量额操作夹具；来源准入仅在测试进程替换，不补G1—G4。"""
import json,sys
from pathlib import Path
from unittest.mock import patch
from test_market_activity import ActivityTests, admitted, SID


def main(output:Path):
    case=ActivityTests();case.setUp()
    try:
        price=case.price_fixture()
        with admitted():
            a=case.client(write_series=(SID,));descriptor=a.config.public_activity_descriptor();price_descriptor=a.config.public_index_descriptor()
            ready_a=a.request('/api/market-activity/session').json()
            missing=a.request(f'/api/market-activity/{SID}?price_snapshot_id='+price['snapshot_id'])
            operation_a=a.update(price['snapshot_id']).json()
            b=case.client(write_series=(SID,));ready_b=b.request('/api/market-activity/session').json()
            recovery=b.request('/api/market-activity/operations/activity-test?series_id='+SID)
            with patch.object(b.config.market_data._activity_runtime,'_obtain',side_effect=AssertionError('恢复不得取数')):
                operation_b=b.update(price['snapshot_id']).json()
            c=case.client(write_series=(SID,));ready_c=c.request('/api/market-activity/session').json()
            with patch.object(c.config.market_data._activity_runtime,'_obtain',side_effect=AssertionError('恢复不得取数')):
                operation_c=c.update(price['snapshot_id']).json()
            output.write_text(json.dumps(dict(descriptor=descriptor,price_descriptor=price_descriptor,ready_a=ready_a,ready_b=ready_b,ready_c=ready_c,
                operation_a=operation_a,operation_b=operation_b,operation_c=operation_c,recovery=recovery.json(),recovery_status=recovery.status,
                missing=missing.json(),missing_status=missing.status,parameters=dict(price_snapshot_id=price['snapshot_id'],expected_activity_id=None)),indent=2))
    finally:case.doCleanups()

if __name__=='__main__':main(Path(sys.argv[1]))
