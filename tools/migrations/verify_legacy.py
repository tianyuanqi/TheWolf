"""固定旧代码验证恢复副本；输出全版本逻辑指纹，不启动服务或采集。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

from identity_mapping import IdentityMapping
from read_boundary import BoundaryError, ReadBoundary, fingerprint, readonly_database, verify_copies


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate(roots, mapping):
    from pmi.market_data import index_series_store, index_snapshot, snapshot, periodic_budget
    from pmi.market_data.index_catalog import INDICES
    from pmi.market_data.activity.runtime import Runtime as Activity
    from pmi.market_data.activity.model import Options as ActivityOptions
    from pmi.market_data.etf_flow.store import Store
    from pmi.market_data.etf_flow.repository import Repository, group_ids
    from pmi.market_data.etf_flow.runtime import Runtime
    from pmi.market_data.etf_flow.options import Options, Settings
    from pmi.market_data.etf_flow.budget import Budget, Grant
    from pmi.market_data.etf_flow.model import Input
    from pmi.market_data.stock_query.store import load as stock_load

    result = {'versions': [], 'heads': [], 'quotas': [], 'operations': [], 'observations': []}
    prices = {}
    parent = roots['data'] / 'slice-002245-sina'

    def remember(kind, identifier, raw, projected, rows, subject):
        if hashlib.sha256(raw).hexdigest() != identifier:
            raise BoundaryError('legacy_id_mismatch')
        result['versions'].append({'kind': kind, 'id': identifier, 'subject': subject,
            'bytes_sha256': identifier, 'canonical_sha256': digest(json.loads(raw)),
            'projection_sha256': digest(projected), 'rows': rows})

    for file in sorted((parent / 'indices').glob('*/index-v2.sqlite')):
        index = next(item for item in INDICES if item.relative_dir == str(file.parent.relative_to(parent)))
        with readonly_database(file) as connection:
            ids = [row[0] for row in connection.execute('SELECT id FROM snapshots ORDER BY rowid')]
            for identifier in ids:
                value = index_series_store.read_snapshot(parent, index, identifier, connection=connection)
                prices[index.index_id, identifier] = value
                remember('price-v2', identifier, (file.parent / 'objects' / identifier).read_bytes(), value, len(value['bars']), index.index_id)
            current = index_series_store.read_snapshot(parent, index, connection=connection)
            result['heads'].append({'domain': 'price-v2', 'subject': index.index_id,
                'value': dict(connection.execute('SELECT * FROM current_snapshot').fetchone()),
                'projection_sha256': digest(current)})
            for row in connection.execute('SELECT * FROM observations ORDER BY id'):
                manifest = json.loads((file.parent / 'objects' / row['snapshot_id']).read_bytes())
                receipt = index_series_store._read_receipt(connection, file.parent, index, row['snapshot_id'], row['id'], manifest)
                result['observations'].append({'domain': 'price-v2', 'subject': index.index_id, 'id': row['id'], 'sha256': digest(receipt)})
            for row in connection.execute('SELECT * FROM committed_jobs ORDER BY job_id'):
                state = index_series_store._committed_job(parent, index, row['job_id'], connection)
                result['operations'].append({'domain': 'price-v2', 'id': row['job_id'], 'sha256': digest(state)})

    oldfile = parent / 'indices/csi000300/index.sqlite'
    with readonly_database(oldfile) as connection:
        for row in connection.execute('SELECT id FROM snapshots ORDER BY rowid'):
            identifier = row[0]
            value = index_snapshot.read_snapshot(parent, identifier, connection=connection)
            remember('csi-price-v1', identifier, (oldfile.parent / 'objects' / identifier).read_bytes(), value, len(value['bars']), 'csi000300')
        current = index_snapshot.read_snapshot(parent, connection=connection)
        result['heads'].append({'domain': 'csi-price-v1', 'projection_sha256': digest(current)})

    with readonly_database(parent / 'slice.sqlite') as connection:
        for row in connection.execute('SELECT snapshot_id FROM snapshots ORDER BY rowid'):
            identifier = row[0]
            value = snapshot.read_snapshot(parent, identifier, connection=connection)
            remember('slice-price-v1', identifier, (parent / 'objects' / identifier).read_bytes(), value, len(value['bars']), '002245.SZ')
        current = snapshot.read_snapshot(parent, connection=connection)
        result['heads'].append({'domain': 'slice-price-v1', 'projection_sha256': digest(current)})
        for row in connection.execute('SELECT * FROM snapshot_observations ORDER BY rowid'):
            result['observations'].append({'domain': 'slice-price-v1', 'sha256': digest(dict(row))})

    class VerifiedPrices:
        def check_location(self):
            pass

        def read_daily(self, series, target):
            value = prices.get((series, target))
            return None if value is None else {'format': 'v2', 'snapshot': value}

    activity_root = roots['data'] / 'market-activity'
    runtime = Activity(VerifiedPrices(), ActivityOptions(activity_root))
    for file in sorted((activity_root / 'snapshots').glob('*.json')):
        raw = file.read_bytes()
        manifest = json.loads(raw)
        value = runtime._fixed(manifest['series_id'], file.stem)
        remember('activity-v1', file.stem, raw, value, len(value['rows']), manifest['series_id'])
        result['observations'].extend({'domain': 'activity-v1', 'id': item['observation_id'], 'sha256': digest(item)} for item in value['observations'])
    for directory in ('index', 'market'):
        for file in sorted((activity_root / directory).rglob('*.json')):
            pointer = json.loads(file.read_bytes())
            manifest = runtime._fixed(pointer['series_id'], pointer['activity_id'])
            target = manifest['price_snapshot_id'] or manifest['anchor_date']
            value = runtime._current_value(pointer['series_id'], target, pointer, manifest)
            result['heads'].append({'domain': 'activity-v1', 'path': str(file.relative_to(activity_root)), 'sha256': digest(value)})
    for file in sorted((activity_root / 'operations').glob('*.json')):
        operation = json.loads(file.read_bytes())
        runtime._validate_completed(operation)
        result['operations'].append({'domain': 'activity-v1', 'id': operation['request_id'], 'sha256': digest(operation)})

    config = json.loads((roots['data'] / 'daily/market-overview.json').read_bytes())
    periodic = periodic_budget.Budget(parent, activity_root, periodic_budget.PeriodicOptions(**config['periodic']))
    ledger = periodic.read()
    result['quotas'].append({'domain': 'periodic', 'scope': periodic.scope, 'sha256': digest(ledger),
        'attempts': len(ledger['attempts']), 'batches': len(ledger['batches']), 'days': ledger['days'], 'months': ledger['months']})
    etf_config = config['etf_flow']
    options = Options(mapping.physical(etf_config['root']), mapping.physical(etf_config['configuration']),
        mapping.physical(etf_config['evidence']), mapping.physical(etf_config['grant']) if etf_config['grant'] else None,
        etf_config['write_enabled'], etf_config['refresh_revision'])
    settings = Settings(options)
    etf = Runtime(options)
    store = etf.store
    repository = Repository(store)
    identifier = store.current_id()
    visited = set()
    while identifier is not None:
        if identifier in visited:
            raise BoundaryError('legacy_publication_cycle')
        visited.add(identifier)
        loaded = repository.load(identifier)
        evaluations = {mode: {str(group): repository.evaluations(loaded, mode, group) for group in group_ids(loaded.config, loaded.manifest['selection_at'])}
                       for mode in ('current', 'original')}
        projection = {'manifest': loaded.manifest, 'inputs': [x.raw for x in loaded.inputs], 'evaluations': evaluations}
        remember('etf-flow-v1', identifier, store.get(identifier), projection, len(loaded.inputs), 'etf-flow')
        identifier = loaded.manifest['parent']
    result['heads'].append({'domain': 'etf-flow-v1', 'id': store.current_id(), 'scope': store.scope,
        'settings_identity': settings.id, 'writable_identity': settings.identity(True)})
    for file in sorted((roots['etf'] / 'settings').glob('grant*.json')):
        grant = Grant.parse(json.loads(file.read_bytes()))
        budget = Budget(store, grant)
        reference, value = budget.read()
        result['quotas'].append({'domain': 'etf-flow-v1', 'id': grant.id, 'scope': store.scope,
            'reference': reference, 'sha256': digest(value), 'usage': budget.usage()})
    for operation in etf._records()[1]:
        # _records 使用记录本身的完整历史config_id验证计划与操作，不用新目录配置覆盖。
        if operation['state'] == 'completed':
            found = store.published_operation(operation['operation_key'])
            if found is None or found[0] != operation['snapshot_id']:
                raise BoundaryError('legacy_etf_commit_mismatch')
            repository.load(found[0])
        result['operations'].append({'domain': 'etf-flow-v1', 'id': operation['operation_key'],
            'config_id': operation['config_id'], 'plan_id': operation['plan_id'], 'sha256': digest(operation)})
    inputs = etf.cache.inputs()
    result['etf_cache'] = {'rows': len(inputs), 'sha256': digest([x.raw for x in inputs])}
    object_count, journal_count, input_count = 0, 0, 0
    for file in sorted((store.root / 'objects').iterdir()):
        raw = store.get(file.name)
        object_count += 1
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(value, dict) and set(value) == {'member_id', 'date', 'fields', 'revision_reason'}:
            Input.parse(value)
            input_count += 1
    for file in sorted((store.root / 'journals').iterdir()):
        store.journal(file.name)
        journal_count += 1
    result['etf_objects'] = {'objects': object_count, 'current_journals': journal_count, 'inputs': input_count}
    etf.close()

    for release in sorted(roots['stock'].glob('acceptance-*')):
        identifier, bundle = stock_load(release)
        raw = (release / 'stock-query/snapshots' / (identifier + '.json')).read_bytes()
        remember('stock-query-v1', identifier, raw, bundle, sum(len(stock['prices']) for stock in bundle['stocks']), 'stock-query')
    if len(result['versions']) != 56 or len({row['id'] for row in result['versions']}) != 56:
        raise BoundaryError('legacy_version_count_changed')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--copies', type=Path, required=True)
    parser.add_argument('--legacy-code', type=Path, required=True)
    parser.add_argument('--code-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or fingerprint(args.manifest) != args.manifest_sha256:
        raise BoundaryError('validation_input_mismatch')
    manifest = json.loads(args.manifest.read_bytes())
    roots = {key: args.copies / key for key in manifest['roots']}
    code_manifest = json.loads(args.code_manifest.read_bytes())
    for relative, item in code_manifest['files'].items():
        expected = item['sha256'] if isinstance(item, dict) else item
        if fingerprint(args.legacy_code / relative) != expected:
            raise BoundaryError('legacy_code_changed')
    sys.path.insert(0, str(args.legacy_code / 'python/src'))
    mapping = IdentityMapping({str(roots[key]): row['original_root'] for key, row in manifest['roots'].items()})
    # 提前加载标准库的时区/编码缓存；边界内仍禁止任何网络。
    datetime.now(timezone.utc).isoformat()
    dependencies = [Path(sys.base_prefix), Path(sys.prefix), Path(__file__).resolve().parent,
        args.legacy_code, Path('/usr/share/zoneinfo'), Path('/var/db/timezone/zoneinfo'), Path('/private/var/db/timezone/zoneinfo'),
        Path('/System/Library/CoreServices/SystemVersion.plist')]
    boundary = ReadBoundary(copies=list(roots.values()), originals=[Path(x['original_root']) for x in manifest['roots'].values()],
        code=dependencies, output=args.output)
    boundary.install()
    started = time.perf_counter()
    report = {'manifest_sha256': args.manifest_sha256, 'passed': False}
    try:
        report['copies_before'] = verify_copies(manifest, {key: str(root) for key, root in roots.items()})
        with mapping.installed():
            report['validation'] = validate(roots, mapping)
        report['copies_after'] = verify_copies(manifest, {key: str(root) for key, root in roots.items()})
        report['passed'] = not boundary.denied
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    report.update(seconds=time.perf_counter() - started, opened=sorted(boundary.opened), denied=boundary.denied)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'passed': report['passed'], 'versions': len(report.get('validation', {}).get('versions', [])),
                      'denied': len(boundary.denied), 'seconds': report['seconds'], 'error': report.get('error', {}).get('message')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
