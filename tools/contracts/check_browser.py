"""C启写阶段的有限结构/装配检查；真实HTTP、浏览器与自然语言语义另行取证。"""
from pathlib import Path
import copy
import hashlib
import json
import tempfile

from generate import ROOT, load_spec, operations
from projection import check_coverage, operation_state


def main():
    """核对同源投影和真实装配路由，并拒绝声明/摘要漂移。"""
    from pmi.api import create_app
    from pmi.http_contract import verify_resources
    from pmi.service_config import ServiceConfig
    spec = load_spec(ROOT / 'contracts/openapi.yaml')
    if spec['info']['version'] != '3.0.0': raise ValueError('仅适用SQLite 3.0.0读取契约')
    digest = hashlib.sha256((ROOT / 'contracts/openapi.yaml').read_bytes()).hexdigest()
    projection = json.loads((ROOT / 'contracts/generated/operations.json').read_text())
    check_coverage(spec, digest, projection); verify_resources()
    for key in ('routes', 'boundaries', 'obligations'):
        broken = copy.deepcopy(projection)
        if isinstance(broken[key], list): broken[key].pop()
        else: broken[key].pop(next(iter(broken[key])))
        try: check_coverage(spec, digest, broken)
        except ValueError: pass
        else: raise AssertionError('缺项投影未被拒绝: ' + key)
    with tempfile.TemporaryDirectory(prefix='c-contract-') as directory:
        root = Path(directory).resolve()
        from pmi.market_data.storage import Database
        from pmi.market_data.storage.publications import Publications
        from pmi.market_data.storage.database import digest as content_digest
        database = Database(root)
        database.initialize()
        with database.writer(), database.transaction() as connection:
            Publications(connection).domain('price-v2', content_digest('synthetic-contract'))
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        app = create_app(ServiceConfig(root, 18080, ('http://127.0.0.1:18081',)))
        expected = {method.upper() + ' ' + path for path, method, _ in operations(spec)}
        actual = {method + ' ' + route.path for route in app.routes for method in route.methods}
        assert actual == expected, {'missing': sorted(expected - actual), 'extra': sorted(actual - expected)}
        assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}, '装配改变SQLite库或创建旁路文件'
    unknown = {'state': 'unknown', 'job_id': None, 'business_status': None, 'reused_job': None, 'rejection': None}
    operation_state(unknown)
    try: operation_state({**unknown, 'business_status': {'stage': 'completed'}})
    except ValueError: pass
    else: raise AssertionError('unknown错误归属未拒绝')
    print(json.dumps({'contract_sha256': digest, 'routes': sorted(actual), 'projection_drift_negatives': 3,
                      'runtime_resources': 'matched', 'startup_mutated_data_files': 0,
                      'limits': ['不是实际回环HTTP/浏览器证据', '自然语言扩展保留不等于自动执行', '结构检查不代替更新执行证据；关联持久和原生延期']}, ensure_ascii=False))


if __name__ == '__main__': main()
