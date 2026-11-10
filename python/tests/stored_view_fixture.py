"""实际范围HTTP响应供浏览器校验测试；独占合成库，禁止普通读打开原件。"""
import json
from pathlib import Path
import sys
from unittest.mock import patch

from test_combined_views import CombinedViews
from pmi.market_data.activity.model import INDEX_IDS, MARKET, TWO_MARKET
from pmi.market_data.storage.originals import Originals


def generate(target: Path):
    if target.exists() or not target.is_absolute() or not str(target).startswith('/private/tmp/'):
        raise ValueError('必须为独占临时输出')
    cls = CombinedViews
    cls.setUpClass()
    try:
        test = cls()
        result = {'versions': cls.data.market_versions(), 'prices': [], 'activities': [], 'markets': []}
        with patch.object(Originals, 'get', side_effect=AssertionError('normal read opened original')):
            for sid in INDEX_IDS:
                overview = test.price_reply(sid).json()
                for frequency in ('daily', 'weekly', 'monthly'):
                    reply = test.price_reply(sid, 'range', **overview['source_coverage'], frequency=frequency, ma='5,20')
                    assert reply.status == 200, reply.body[:1000]
                    result['prices'].append({'overview': overview, 'range': reply.json()})
            from urllib.parse import urlencode
            for sid in (*INDEX_IDS, MARKET, TWO_MARKET):
                parameters = test.activity_parameters(sid)
                version = next(item['activity'] for item in result['versions']['indices' if sid in INDEX_IDS else 'markets']
                               if item.get('index_id', item.get('series_id')) == sid)
                for frequency in (('daily', 'weekly', 'monthly') if sid in INDEX_IDS else ('daily',)):
                    for field in (('amount', 'volume') if sid in INDEX_IDS else ('amount',)):
                        query = {**parameters, **version['source_coverage'], 'frequency': frequency, 'field': field, 'ma': '5,20'}
                        reply = test.get(f'/api/market-activity/{sid}/view?' + urlencode(query), activity=True)
                        assert reply.status == 200, reply.body[:1000]
                        result['activities'].append(reply.json())
                if sid in (MARKET, TWO_MARKET):
                    reply = test.get(f'/api/market-activity/{sid}/view?' + urlencode({**parameters, 'detail': 'overview'}), activity=True)
                    assert reply.status == 200, reply.body[:1000]
                    result['markets'].append(reply.json())
        cls.tearDownClass()
        target.write_text(json.dumps(result, ensure_ascii=False))
        print(json.dumps({key: len(value) for key, value in result.items() if key != 'versions'}))
    finally:
        cls.doClassCleanups()


if __name__ == '__main__':
    generate(Path(sys.argv[1]))
