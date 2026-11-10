"""对实际合成HTTP响应比较原Schema引擎与复用节点；只读显式测试夹具。"""
from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
from pmi.http_contract.schema_graph import validator


def main(path: Path, overview: Path | None = None) -> None:
    for item in (path, overview):
        if item is not None and (not item.is_absolute() or not str(item).startswith('/private/tmp/wolf-overview-perf-')):
            raise ValueError('仅接受本任务自有合成测试夹具')
    fixtures = json.loads(path.read_text())
    assert len(fixtures) == 10
    if overview:
        values = json.loads(overview.read_text()); assert len(values) == 4
        fixtures.extend({'kind': 'overview', 'combined': item['combined']} for item in values)
    schemas = json.loads(files('pmi.http_contract').joinpath('schemas.json').read_text())
    count = 0
    for fixture in fixtures:
        name = {'price': 'IndexSeriesCombinedView', 'activity': 'MarketActivityCombinedView', 'overview': 'IndexSeriesOverviewView'}[fixture['kind']]
        fast = validator(schemas, name)
        slow = Draft202012Validator({**schemas, '$ref': '#/$defs/' + name})
        value = fixture['combined']
        assert fast.is_valid(value) and slow.is_valid(value)
        count += 1
        for mutate in (
            lambda v: v.update(extra=True),
            lambda v: v.pop('calculations'),
            lambda v: v['calculations'].update(definitions=[]),
            lambda v: v['calculations'].update(formula_version='unknown'),
        ):
            broken = deepcopy(value);mutate(broken)
            assert not fast.is_valid(broken) and not slow.is_valid(broken)
            count += 1
    print(f'{count}项实际响应及Schema反例与原Draft202012一致；金融语义反例另由前端/领域检查。')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
