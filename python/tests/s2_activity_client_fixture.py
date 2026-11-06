"""生成实际ASGI读取的客户端夹具；旧三市仅沿用P3的隔离重放替身。"""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from market_activity_display_smoke import fixtures, publish
from test_market_activity import Client, admitted
from test_index_series_contract import WINDOW
from test_two_market import market_original
from pmi.market_data.activity import calculations, runtime, two_market
from pmi.market_data.activity.model import INDEX_IDS, MARKET, TWO_MARKET, canonical


def main(output: Path):
    with tempfile.TemporaryDirectory(prefix='wolf-s2-client-') as temporary, admitted():
        root=Path(temporary).resolve();fixtures(root)
        client=Client(root/'price',root/'activity')
        rt=client.config.market_data._activity_runtime
        originals=[market_original(m,d,empty=m=='szse' and d==WINDOW.dates[-4]) for d in WINDOW.dates for m in ('sse','szse')]
        publish(rt.store,two_market.manifest(WINDOW,originals),{o.object_id:o.content for o in originals},'s2-two-client')
        result={'descriptor':client.config.public_activity_descriptor(),'price_descriptor':client.config.public_index_descriptor(),
                'ready':client.request('/api/market-activity/session').json(),'bundles':{}}
        try:
            with patch.object(runtime,'market_from_originals',side_effect=lambda window, originals:json.loads((root/'market-test-replay.json').read_bytes())):
                for sid in (*INDEX_IDS,MARKET,TWO_MARKET):
                    price=client.config.market_data.read_daily(sid)['snapshot'] if sid in INDEX_IDS else None
                    key='price_snapshot_id='+price['snapshot_id'] if price else 'anchor_date='+WINDOW.anchor_date
                    base='/api/market-activity/'+sid
                    current=client.request(base+'?'+key);assert current.status==200,current.body
                    aid=current.json()['activity_id']
                    snapshot=client.request(base+'/snapshots/'+aid);assert snapshot.status==200,snapshot.body
                    computed=client.request(base+'/snapshots/'+aid+'/calculations?formula_version='+calculations.formula_for(sid));assert computed.status==200,computed.body
                    result['bundles'][sid]={'price':price,'current':current.json(),'snapshot':snapshot.json(),'calculations':computed.json()}
            output.write_bytes(canonical(result))
        finally:client.app.state.updates.close()


if __name__=='__main__':main(Path(sys.argv[1]))
