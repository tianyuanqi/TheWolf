"""一次性导入已核验的旧副本；不搜默认根、不联网、不切换运行配置。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
from zoneinfo import ZoneInfo

from read_boundary import BoundaryError, fingerprint, readonly_database, verify_copies

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python/src'))
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.database import canonical, digest, now
from pmi.market_data.storage.documents import Documents
from pmi.market_data.storage.facts import Facts
from pmi.market_data.storage.originals import Originals
from pmi.market_data.storage.publications import Publications, ValidationProof
from pmi.market_data.storage.snapshots import Snapshots

VALIDATOR = 'legacy-frozen-readers-20261108-v1'


class Importer:
    def __init__(self, database, copies, manifest, manifest_sha, validation, validation_sha, migration_id):
        self.database, self.copies, self.manifest = database, copies, manifest
        self.manifest_sha, self.validation_sha, self.migration_id = manifest_sha, validation_sha, migration_id
        if not validation.get('passed') or validation.get('denied') or validation.get('manifest_sha256') != manifest_sha:
            raise StorageError('migration_validation_required')
        self.verified = {row['id']: row for row in validation['validation']['versions']}
        self.validation = validation['validation']
        self.at = now()
        self.mapped = {}
        self.originals = Originals(database)
        self.projections = {}
        self.results = []
        self.c = None

    def source(self, root, relative):
        if root not in self.manifest['roots'] or relative not in self.manifest['roots'][root]['files']:
            raise StorageError('migration_unlisted_source')
        path = self.copies / root / relative
        raw = path.read_bytes()
        item = self.manifest['roots'][root]['files'][relative]
        if len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise StorageError('migration_source_changed')
        return raw

    def json(self, root, relative):
        def pairs(items):
            value = dict(items)
            if len(value) != len(items):
                raise StorageError('migration_duplicate_json_key')
            return value
        return json.loads(self.source(root, relative), object_pairs_hook=pairs)

    def mapped_file(self, root, relative, target, reason):
        self.mapped[root, relative] = ('mapped', target, reason)

    def raw(self, root, relative):
        value = self.source(root, relative)
        media = 'application/pdf' if value.startswith(b'%PDF-') else 'application/octet-stream'
        reference = self.originals.put(value, media)
        self.mapped_file(root, relative, reference, '原件按内容SHA去重，来源归属另存')
        return reference

    def document(self, value, *, old_id=None):
        return Documents(self.c).put(value, document_id=old_id)

    def metadata_file(self, root, relative):
        reference = self.document(self.json(root, relative))
        self.mapped_file(root, relative, reference, '元数据/运行身份按原字段保留')
        return reference

    def state(self, domain, key, value):
        reference = self.document(value)
        self.c.execute('INSERT INTO state VALUES(?,?,?) ON CONFLICT(domain_id,key) DO UPDATE SET revision=excluded.revision', (domain, key, reference))
        return reference

    def publication(self, identity, domain, subject, rows, manifest, *, status='published', bindings=None):
        expected = self.verified.get(identity)
        if expected is None or expected['canonical_sha256'] != digest(manifest):
            raise StorageError('migration_unverified_publication')
        pub = Publications(self.c)
        old = self.c.execute('SELECT id FROM publication WHERE domain_id=? AND subject=? ORDER BY sequence DESC LIMIT 1', (domain, subject)).fetchone()
        dates = sorted({key[2] for key in rows})
        proof = ValidationProof(VALIDATOR, digest(manifest), self.at, {'source_manifest': self.manifest_sha,
            'validation_report': self.validation_sha, 'old_id': identity, 'projection_sha256': expected['projection_sha256']})
        pub.add(identity, domain=domain, subject=subject, rows=rows, proof=proof, base=old[0] if old else None,
                coverage_start=dates[0] if dates else None, coverage_end=dates[-1] if dates else None,
                status=status, bindings=bindings)
        self.c.execute('INSERT OR IGNORE INTO legacy_id_map VALUES(?,?,?,?,?)', (domain, identity, expected['kind'], identity, status))

    def compare(self, identity, projected):
        actual = digest(projected)
        if actual != self.verified[identity]['projection_sha256']:
            raise StorageError('migration_projection_mismatch:' + identity)
        self.results.append({'id': identity, 'kind': self.verified[identity]['kind'],
            'rows': self.verified[identity]['rows'], 'projection_sha256': actual, 'passed': True})

    def observation(self, domain, receipt_id, source):
        object_id = source['object_id']
        reference = digest([domain, receipt_id, source])
        metadata = self.document(source)
        published = source.get('published_at')
        started = source.get('started_at')
        retrieved = source.get('completed_at') or source.get('retrieved_at')
        if not retrieved:
            raise StorageError('migration_missing_retrieval_time')
        publisher = source.get('source') or source.get('publisher')
        if not publisher:
            raise StorageError('migration_missing_source_identity')
        args = (reference, domain, publisher, object_id, published, started, retrieved, source.get('locator'), metadata)
        self.c.execute('INSERT OR IGNORE INTO source_observation VALUES(?,?,?,?,?,?,?,?,?)', args)
        return reference

    def provenance(self, kind, projection, observations, refs):
        table = 'price_projection' if kind == 'price' else 'metric_projection'
        row = self.c.execute('SELECT row_id FROM ' + table + ' WHERE id=?', (projection,)).fetchone()
        if row is None:
            raise StorageError('migration_missing_projection')
        for ref in refs:
            for observation in observations.get(ref['object_id'], []):
                self.c.execute('INSERT OR IGNORE INTO row_provenance VALUES(?,?,?,?)',
                    (kind, row[0], observation, ref.get('locator') or 'source-document'))

    def originals_for_price(self):
        manifests = {row['id'] for row in self.verified.values() if row['kind'] in ('price-v2', 'csi-price-v1', 'slice-price-v1')}
        for relative in self.manifest['roots']['data']['files']:
            if relative.startswith('slice-002245-sina/') and '/objects/' in relative:
                name = Path(relative).name
                if name not in manifests:
                    self.raw('data', relative)

    def prices(self):
        from pmi.market_data.index_catalog import INDICES
        prefix = 'slice-002245-sina/'
        for index in INDICES:
            domain = 'price-v2'
            directory = prefix + index.relative_dir + '/'
            with readonly_database(self.copies / 'data' / (directory + 'index-v2.sqlite')) as old:
                saved = list(old.execute('SELECT * FROM snapshots ORDER BY rowid'))
                for row in saved:
                    identity = row['id']
                    manifest = self.json('data', directory + 'objects/' + identity)
                    _, rows = Snapshots(self.c).price(manifest, snapshot_id=identity)
                    self.publication(identity, domain, index.index_id, rows, manifest)
                    self.state(domain, 'publication:' + identity, dict(row))
                    observation_ids = {}
                    for observed in old.execute('SELECT * FROM observations WHERE snapshot_id=? ORDER BY rowid', (identity,)):
                        receipt = json.loads(observed['receipt'])
                        self.document(receipt, old_id=observed['id'])
                        Publications(self.c).observe(identity, observed['id'], first=observed['id'] == row['first_observation'])
                        for source in receipt['sources']:
                            oid = self.observation(domain, observed['id'], source)
                            observation_ids.setdefault(source['object_id'], []).append(oid)
                    for bar in manifest['bars']:
                        self.provenance('price', rows['price', index.index_id, bar['trade_date'], ''], observation_ids, bar['evidence_refs'])
                    self.mapped_file('data', directory + 'objects/' + identity, identity, '固定旧ID映射到价格行版本与来源')
                    loaded = Documents(self.c).get(identity)
                    self.compare(identity, {**loaded, 'snapshot_id': identity, 'observation_id': row['first_observation'],
                        'retrieval': Documents(self.c).get(row['first_observation'])})
                current = old.execute('SELECT * FROM current_snapshot').fetchone()
                if current:
                    head = Publications(self.c).head(domain, index.index_id)
                    Publications(self.c).select(current['snapshot_id'], domain=domain, subject=index.index_id,
                        observation=current['observation_id'], expected=head[0] if head else None)
                for job in old.execute('SELECT * FROM committed_jobs'):
                    value = json.loads(job['state'])
                    reference = self.document(value)
                    self.c.execute('INSERT OR REPLACE INTO operation VALUES(?,?,?,?,?)',
                        (domain, job['job_id'], reference, value['stage'], job['snapshot_id']))
                self.mapped_file('data', directory + 'index-v2.sqlite', digest([dict(x) for x in saved]), '原库版本/观察/提交任务/当前指针逐表映射')

    def retired_prices(self):
        facts, docs = Facts(self.c), Documents(self.c)
        for kind, relative, id_column, domain in (
            ('csi-price-v1', 'slice-002245-sina/indices/csi000300/', 'id', 'retired-csi'),
            ('slice-price-v1', 'slice-002245-sina/', 'snapshot_id', 'retired-slice')):
            file = relative + ('index.sqlite' if kind == 'csi-price-v1' else 'slice.sqlite')
            with readonly_database(self.copies / 'data' / file) as old:
                saved = list(old.execute('SELECT * FROM snapshots ORDER BY rowid'))
                for row in saved:
                    identity = row[id_column]
                    manifest = self.json('data', relative + 'objects/' + identity)
                    instrument = 'csi:000300:price' if kind == 'csi-price-v1' else manifest['instrument_code'] + '.SZ'
                    facts.instrument(instrument, 'index' if kind == 'csi-price-v1' else 'stock')
                    rows, replacements = {}, {}
                    for bar in manifest['bars']:
                        fields = None if kind == 'csi-price-v1' else {'open': 'open_cny', 'high': 'high_cny', 'low': 'low_cny',
                            'close': 'close_cny', 'volume': 'volume_shares', 'amount': 'amount_cny'}
                        reference = facts.price(instrument, bar, unit='点' if kind == 'csi-price-v1' else 'CNY', precision=2,
                            price_type='index_points' if kind == 'csi-price-v1' else 'unadjusted', fields=fields)
                        rows['price', instrument, bar['trade_date'], ''] = reference
                        replacements[id(bar)] = docs.reference(reference)
                    for source in manifest.get('evidence', []):
                        for value in source['rows']:
                            reference = facts.source_price(instrument, source['object_id'], value)
                            replacements[id(value)] = docs.reference(reference)
                    docs.put(manifest, document_id=identity, transform=lambda value: replacements.get(id(value)))
                    self.publication(identity, domain, instrument, rows, manifest, status='retired')
                    self.state(domain, 'publication:' + identity, dict(row))
                    if kind == 'csi-price-v1':
                        receipt = json.loads(old.execute('SELECT receipt FROM observations WHERE id=?', (row['first_observation'],)).fetchone()[0])
                        self.document(receipt, old_id=row['first_observation'])
                        Publications(self.c).observe(identity, row['first_observation'], first=True)
                        observed_sources = {}
                        for source in receipt['sources']:
                            source = {**source, 'url': next(item['url'] for item in manifest['evidence'] if item['object_id'] == source['object_id'])}
                            observed_sources.setdefault(source['object_id'], []).append(self.observation(domain, row['first_observation'], source))
                        for bar in manifest['bars']:
                            self.provenance('price', rows['price', instrument, bar['trade_date'], ''], observed_sources, bar['evidence_refs'])
                        projection = {**docs.get(identity), 'snapshot_id': identity, 'observation_id': row['first_observation'], 'retrieval': receipt}
                    else:
                        observed_sources = []
                        for observed_row in old.execute('SELECT * FROM snapshot_observations WHERE snapshot_id=? ORDER BY rowid', (identity,)):
                            observed_doc = dict(observed_row)
                            observed_ref = self.document(observed_doc)
                            self.c.execute('INSERT OR IGNORE INTO legacy_id_map VALUES(?,?,?,?,?)',
                                (domain, observed_row['observation_id'], 'observation', observed_ref, 'retired'))
                            Publications(self.c).observe(identity, observed_ref, first=not observed_sources)
                            source = {'source': manifest['source_id'], 'object_id': manifest['raw_object_id'],
                                'url': manifest['market_contract']['source_url'], 'published_at': None,
                                'retrieved_at': observed_row['observed_at'], 'time_basis': observed_row['time_basis'],
                                'legacy_observation_id': observed_row['observation_id']}
                            observed_sources.append(self.observation(domain, observed_ref, source))
                        if not observed_sources:
                            raise StorageError('migration_legacy_observation_missing')
                        for key, reference in rows.items():
                            self.provenance('price', reference, {source['object_id']: observed_sources},
                                [{'object_id': source['object_id'], 'locator': 'legacy-manifest:' + identity + ':bars:' + key[2]}])
                        projection = slice_projection(docs.get(identity), dict(row))
                    self.compare(identity, projection)
                    self.mapped_file('data', relative + 'objects/' + identity, identity, '退役固定版本保留，不启用页面或读取路由')
                for table in [r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]:
                    self.state(domain, 'legacy-table:' + table, [dict(x) for x in old.execute('SELECT * FROM "' + table + '"')])
                self.mapped_file('data', file, digest([dict(x) for x in saved]), '退役库关系原样映射为SQL历史元数据')

    def activity(self):
        prefix, domain = 'market-activity/', 'activity'
        for relative in self.manifest['roots']['data']['files']:
            if relative.startswith(prefix + 'objects/'):
                self.raw('data', relative)
        files = sorted(p for p in self.manifest['roots']['data']['files'] if p.startswith(prefix + 'snapshots/'))
        # 与源观察时点一致的顺序；不按hash字典顺序推断金融最新版本。
        files.sort(key=lambda path: (self.json('data', path)['calendar_dates'][-1], path))
        for relative in files:
            identity = Path(relative).stem
            manifest = self.json('data', relative)
            series = manifest['series_id']
            _, rows = Snapshots(self.c).activity(manifest, snapshot_id=identity)
            bindings = {'price': manifest['price_snapshot_id']} if manifest['price_snapshot_id'] else {}
            self.publication(identity, domain, series, rows, manifest, bindings=bindings)
            entries = self.json('data', prefix + 'observation-refs/' + identity + '.json')['entries']
            observations = []
            source_observations = {}
            for entry in entries:
                operation = self.json('data', prefix + 'operations/' + entry['request_id'] + '.json')
                if operation['state'] != 'completed':
                    raise StorageError('migration_activity_uncommitted')
                receipt = self.json('data', prefix + 'observations/' + entry['observation_id'] + '.json')
                self.document(receipt, old_id=entry['observation_id'])
                Publications(self.c).observe(identity, entry['observation_id'], first=not observations)
                observations.append({**receipt, **entry})
                for source in receipt['sources']:
                    oid = self.observation(domain, entry['observation_id'], source)
                    source_observations.setdefault(source['object_id'], []).append(oid)
            for key, projection in rows.items():
                row = Documents(self.c).get(projection)
                fields = [(market + ':' + str(position), value) for market, values in row['components'].items() for position, value in enumerate(values)] if 'components' in row else [(name, row[name]) for name in ('amount', 'volume')]
                for name, field in fields:
                    target = Facts(self.c).metric(series, key[2], name, field)
                    if field.get('object_id'):
                        self.provenance('metric', target, source_observations, [field])
            self.mapped_file('data', relative, identity, '量额各行/分项独立保存，固定价格或anchor绑定不变')
            self.compare(identity, {**Documents(self.c).get(identity), 'activity_id': identity, 'observations': observations})
        for relative in self.manifest['roots']['data']['files']:
            if not relative.startswith(prefix) or relative in {p for r, p in self.mapped if r == 'data'}:
                continue
            if '/index/' in relative or '/market/' in relative:
                pointer = self.json('data', relative)
                reference = self.metadata_file('data', relative)
                manifest = Documents(self.c).get(pointer['activity_id'])
                subject = pointer['series_id']
                binding = manifest['price_snapshot_id'] or manifest['anchor_date']
                head = Publications(self.c).head(domain, subject, binding)
                Publications(self.c).select(pointer['activity_id'], domain=domain, subject=subject, binding=binding,
                    observation=pointer['observation_id'], metadata=reference, expected=head[0] if head else None)
            elif relative.endswith('.json'):
                reference = self.metadata_file('data', relative)
                if '/operations/' in relative:
                    op = Documents(self.c).get(reference)
                    self.c.execute('INSERT OR REPLACE INTO operation VALUES(?,?,?,?,?)',
                        (domain, op['request_id'], reference, op['state'], op['activity_id']))
                self.state(domain, str(Path(relative).relative_to(prefix)), Documents(self.c).get(reference))

    def stock(self):
        domain = 'stock-query'
        releases = sorted({path.split('/')[0] for path in self.manifest['roots']['stock']['files'] if path.startswith('acceptance-')})
        for release in releases:
            prefix = release + '/stock-query/'
            for relative in self.manifest['roots']['stock']['files']:
                if relative.startswith(prefix + 'objects/'):
                    self.raw('stock', relative)
            identity = self.json('stock', prefix + 'current.json')['snapshot_id']
            path = prefix + 'snapshots/' + identity + '.json'
            value = self.json('stock', path)
            facts, docs = Facts(self.c), Documents(self.c)
            rows, replacements = {}, {}
            for stock in value['stocks']:
                facts.instrument(stock['id'], 'stock', name=stock['name'])
                source = next(source for source in value['sources'] if source['id'] == stock['price_source_id'])
                source_id = self.observation(domain, identity, {**source, 'object_id': source['id']})
                for price in stock['prices']:
                    reference = facts.price(stock['id'], price, unit=stock['currency'], precision=2,
                        price_type='unadjusted', date_field='date')
                    rows['price', stock['id'], price['date'], ''] = reference
                    replacements[id(price)] = docs.reference(reference)
                    self.provenance('price', reference, {source['id']: [source_id]},
                        [{'object_id': source['id'], 'locator': source['locator'] + ':' + price['date']}])
            docs.put(value, document_id=identity, transform=lambda item: replacements.get(id(item)))
            self.publication(identity, domain, 'stock-query', rows, value, status='unaccepted')
            self.compare(identity, docs.get(identity))
            self.mapped_file('stock', path, identity, '未验收固定资料保留；不恢复页面/API')
            self.state(domain, release + ':head', self.json('stock', prefix + 'current.json'))
            self.metadata_file('stock', prefix + 'current.json')
            self.metadata_file('stock', prefix + 'import-receipt.json')

    def etf(self):
        domain, prefix = 'etf', 'store/'
        docs, facts = Documents(self.c), Facts(self.c)
        objects, archived = {}, {}
        for relative in self.manifest['roots']['etf']['files']:
            if not relative.startswith(prefix + 'objects/'):
                continue
            raw = self.source('etf', relative)
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                value = None
            is_raw = value is None or isinstance(value, dict) and ('pageHelp' in value or 'Data' in value)
            if is_raw:
                self.raw('etf', relative)
            elif isinstance(value, dict) and set(value) == {'previous', 'value'}:
                archived[Path(relative).name] = value
                self.archive('etf', relative, 'cumulative-journal-history')
            elif isinstance(value, dict):
                objects[Path(relative).name] = (relative, value)
            else:
                raise StorageError('migration_unknown_etf_object')
        # 金融值先落独立表；其余文档只引用这些行，不保留数值JSON副本。
        pending = []
        for identity, (relative, value) in objects.items():
            if set(value) == {'member_id', 'date', 'fields', 'revision_reason'}:
                reference = facts.input(value)
                for metric, field in value['fields'].items():
                    source_id = self.observation(domain, identity, field['source'])
                    projection = self.c.execute('SELECT field_document FROM input_field WHERE input_id=? AND metric=?', (reference, metric)).fetchone()[0]
                    self.provenance('metric', projection, {field['source']['object_id']: [source_id]}, [field['source']])
            elif set(value) == {'member_id', 'kind', 'start', 'end', 'factor', 'tail', 'source_ids', 'confirmed_at', 'confirmation'}:
                reference = facts.adjustment(value)
            else:
                pending.append((identity, relative, value))
                continue
            if reference != identity:
                raise StorageError('migration_etf_content_id_changed')
            self.mapped_file('etf', relative, identity, 'ETF输入/调整拆为独立行，保留原内容ID')
        for identity, relative, value in pending:
            replacements = {}
            if value.get('format') == 'etf-flow-evidence-v1':
                for adjustment in value['adjustments']:
                    reference = facts.adjustment(adjustment)
                    replacements[id(adjustment)] = docs.reference(reference)
                for kind in ('events', 'disclosures'):
                    for event in value[kind]:
                        reference = docs.put(event)
                        self.c.execute('INSERT OR IGNORE INTO event VALUES(?,?,?,?,?)',
                            (reference, kind, event['id'], event['source_id'], event.get('published_date')))
            docs.put(value, document_id=identity, transform=lambda item: replacements.get(id(item)))
            self.mapped_file('etf', relative, identity, 'ETF版本/配置/准备证明/历史档案元数据保留')
        for identity, (relative, value) in objects.items():
            if docs.get(identity) != value:
                raise StorageError('migration_etf_object_mismatch')
        pointer = self.json('etf', prefix + 'current.json')
        current = pointer['object_id']
        publications = []
        identity = current
        while identity is not None:
            value = docs.get(identity)
            publications.append((identity, value))
            identity = value['parent']
        for identity, value in reversed(publications):
            dataset = docs.get(value['dataset_ref'])
            rows = {}
            inputs = []
            for reference in dataset['input_refs']:
                item = docs.get(reference)
                inputs.append(item)
                for metric, projection in self.c.execute('SELECT metric,field_document FROM input_field WHERE input_id=?', (reference,)):
                    rows['metric', item['member_id'], item['date'], metric] = projection
            self.publication(identity, domain, 'etf-flow', rows, value)
            archive = docs.get(value['archive_ref'])
            evaluations = {'current': {}, 'original': {}}
            groups = {str(row['group_id']) for row in archive['evaluations']}
            for group in groups:
                evaluations['current'][group] = {row['date']: row for row in archive['evaluations'] if str(row['group_id']) == group}
                signals = [row for ref in value['signal_refs'] for row in docs.get(ref)['evaluations'] if str(row['group_id']) == group]
                evaluations['original'][group] = {row['date']: row for row in signals}
            self.compare(identity, {'manifest': docs.get(identity), 'inputs': inputs, 'evaluations': evaluations})
        head = Publications(self.c).head(domain, 'etf-flow')
        Publications(self.c).select(current, domain=domain, subject='etf-flow', expected=head[0] if head else None)
        for relative in sorted(self.manifest['roots']['etf']['files']):
            if not relative.startswith(prefix + 'journals/'):
                continue
            key = Path(relative).name
            identity = self.json('etf', relative)['object_id']
            wrapper = archived.get(identity)
            if wrapper is None:
                raise StorageError('migration_journal_missing')
            value = wrapper['value']
            reference = docs.put(value)
            # 技术差量链从导入点开始；原previous另存SQL，旧当前账本ID仍可精确解析。
            self.c.execute('INSERT OR IGNORE INTO journal_revision VALUES(?,?,?,?,?)', (identity, domain, key, None, reference))
            self.state(domain, 'journal-legacy-previous:' + identity, wrapper['previous'])
            self.c.execute('INSERT OR REPLACE INTO journal_head VALUES(?,?,?)', (domain, key, identity))
            self.mapped_file('etf', relative, identity, '当前账本/缓存索引转SQL，历史累计版本只保全')
            if isinstance(value, dict) and value.get('format') == 'etf-flow-budget-v1':
                grant_id = value['grant']['id']
                self.c.execute('INSERT OR REPLACE INTO budget_scope VALUES(?,?,?,?)', (domain, key, grant_id, key))
                for attempt in value['attempts']:
                    self.c.execute('INSERT OR REPLACE INTO attempt VALUES(?,?,?,?)', (domain, key, attempt['id'], docs.put(attempt)))
            if isinstance(value, dict) and set(value) == {'operations'}:
                for op in value['operations']:
                    self.c.execute('INSERT OR REPLACE INTO operation VALUES(?,?,?,?,?)',
                        (domain, op['operation_key'], docs.put(op), op['state'], op['snapshot_id']))
        self.metadata_file('etf', prefix + 'current.json')
        self.metadata_file('etf', prefix + 'initialized.json')
        from pmi.market_data.storage.etf_cache import import_proofs
        import_proofs(self.database, self.c)

    def archive(self, root, relative, category):
        item = self.manifest['roots'][root]['files'][relative]
        identity = item['sha256']
        location = root + '/' + relative
        self.c.execute('INSERT OR IGNORE INTO historical_archive VALUES(?,?,?,?,?)',
            (identity, category, item['size'], self.manifest_sha, location))
        self.mapped[root, relative] = ('preserved-unpublished', identity, category)

    def other_objects(self):
        # 显式列举盘点中的材料目录；不把未知对象静默升级或忽略。
        preserved = {'data': {'backups', 'daily', 'releases', 'runtime-capsules', 'task-20261002-01-r02',
            'task-20261002-01-u1', 'task-20261002-01-r01', 'task-20261003-01', 'task-rollbacks'},
            'etf': {'initialization-20261106', 'research-20261105-s1', 'research-20261106-s4a', 'settings'},
            'stock': {'research-20261106-s1', 'research-20261106-s2'}}
        for root, source in self.manifest['roots'].items():
            for relative, item in source['files'].items():
                if (root, relative) in self.mapped:
                    continue
                if Path(relative).name == '.DS_Store' or (root == 'data' and relative == 'metadata.sqlite'):
                    self.mapped[root, relative] = ('excluded', None, '非业务目录元文件或已明确development fixture，原件仍保全')
                elif relative.split('/')[0] in preserved[root] or (root == 'etf' and relative.startswith('store/incoming/')):
                    self.archive(root, relative, 'offline-retained-material')
                elif root == 'data' and relative.startswith('slice-002245-sina/'):
                    if relative.endswith('.jsonl'):
                        records = [json.loads(line) for line in self.source(root, relative).splitlines() if line.strip()]
                        reference = self.state('price-v2', 'legacy:' + relative, records)
                        self.mapped_file(root, relative, reference, '网络累计/原件获取观察按记录保留，不重置额度')
                    elif relative.endswith('.json'):
                        reference = self.metadata_file(root, relative)
                        value = Documents(self.c).get(reference)
                        if Path(relative).name == 'overview-periodic-ledger.json':
                            self.state('periodic', 'ledger', value)
                            self.c.execute('INSERT OR REPLACE INTO budget_scope VALUES(?,?,?,?)', ('periodic', value['scope_id'], None, 'ledger'))
                            for attempt in value['attempts']:
                                self.c.execute('INSERT OR REPLACE INTO attempt VALUES(?,?,?,?)', ('periodic', value['scope_id'], attempt['id'], self.document(attempt)))
                        else:
                            self.state('price-v2', 'legacy:' + relative, value)
                    elif Path(relative).name.endswith('.lock'):
                        self.archive(root, relative, 'retired-lock-identity')
                    else:
                        raise StorageError('migration_unknown_price_file:' + relative)
                elif root == 'data' and relative == 'market-activity-budget/ledger.json':
                    value = self.json(root, relative)
                    reference = self.state('activity', 'network-budget', value)
                    self.mapped_file(root, relative, reference, '量额请求额度原值保留')
                elif Path(relative).name.endswith('.lock'):
                    self.archive(root, relative, 'retired-lock-identity')
                else:
                    raise StorageError('migration_unclassified_source:' + root + '/' + relative)
        for (root, relative), (disposition, target, reason) in self.mapped.items():
            self.c.execute('INSERT OR IGNORE INTO migration_object VALUES(?,?,?,?,?,?,?)',
                (self.migration_id, root, relative, self.manifest['roots'][root]['files'][relative]['sha256'], disposition, target, reason))

    def reconcile_ledgers(self):
        """额度和已保存操作按原规范指纹核对，不以总条数相等替代字段相等。"""
        docs = Documents(self.c)
        for expected in self.validation.get('quotas', []):
            if expected['domain'] == 'periodic':
                row = self.c.execute("SELECT revision FROM state WHERE domain_id='periodic' AND key='ledger'").fetchone()
            else:
                row = self.c.execute("SELECT value_document FROM journal_revision WHERE domain_id='etf' AND id=?", (expected['reference'],)).fetchone()
            if row is None or digest(docs.get(row[0])) != expected['sha256']:
                raise StorageError('migration_quota_fingerprint_mismatch')
        domains = {'price-v2': 'price-v2', 'activity-v1': 'activity', 'etf-flow-v1': 'etf'}
        for expected in self.validation.get('operations', []):
            row = self.c.execute('SELECT revision FROM operation WHERE domain_id=? AND request_id=?',
                (domains[expected['domain']], expected['id'])).fetchone()
            if row is None or digest(docs.get(row[0])) != expected['sha256']:
                raise StorageError('migration_operation_fingerprint_mismatch')

    def run(self):
        if not self.database.exists:
            self.database.initialize()
        # 独立提交迁移身份；后续业务事务失败仍可证明此候选根属于本批次。
        with self.database.writer(), self.database.transaction() as connection:
            existing = connection.execute('SELECT source_manifest_sha256,state FROM migration WHERE id=?', (self.migration_id,)).fetchone()
            if existing:
                if existing[0] != self.manifest_sha:
                    raise StorageError('migration_identity_conflict')
                if existing[1] == 'verified':
                    for identity in self.verified:
                        docs = Documents(connection)
                        expected = self.verified[identity]['canonical_sha256']
                        if digest(docs.get(identity)) != expected:
                            raise StorageError('migration_verified_content_changed')
                    if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                        raise StorageError('migration_foreign_key_failure')
                    return {'already_imported': True, 'migration_id': self.migration_id}
            else:
                if connection.execute('SELECT 1 FROM migration').fetchone() is not None:
                    raise StorageError('migration_identity_conflict')
                connection.execute('INSERT INTO migration VALUES(?,?,?, ?,NULL)', (self.migration_id, self.manifest_sha, 'preparing', self.at))
        with self.database.writer(), self.database.transaction() as connection:
            self.c = connection
            for domain, logical in [('price-v2', 'legacy-price'), ('activity', 'legacy-activity'), ('retired-csi', 'legacy-retired-csi'),
                ('retired-slice', 'legacy-retired-slice'), ('stock-query', 'legacy-stock-query'), ('etf', 'legacy-etf'), ('periodic', 'legacy-periodic')]:
                root_key = 'etf' if domain == 'etf' else 'stock' if domain == 'stock-query' else 'data'
                root = self.manifest['roots'][root_key].get('original_root')
                suffix = 'store' if domain == 'etf' else 'market-activity' if domain == 'activity' else '' if domain == 'stock-query' else 'slice-002245-sina'
                legacy_root = str(Path(root) / suffix) if root else None
                if domain == 'etf':
                    logical = self.json('etf', 'store/initialized.json')['scope']
                elif domain == 'periodic':
                    logical = self.json('data', 'slice-002245-sina/overview-periodic-ledger.json')['scope_id']
                elif domain == 'activity' and legacy_root:
                    logical = digest({'format': 'wolf-activity-scope-v1', 'root': legacy_root})
                elif domain == 'price-v2' and legacy_root:
                    logical = digest({'identity_format': 'wolf-data-scope-v2', 'data_root': legacy_root, 'mapping': {'index_series': 'indices'}})
                Publications(connection).domain(domain, logical, legacy_root=legacy_root)
            for label, action in [('originals', self.originals_for_price), ('prices', self.prices),
                ('retired-prices', self.retired_prices), ('activity', self.activity), ('stock', self.stock),
                ('etf', self.etf), ('metadata-and-inventory', self.other_objects)]:
                print(json.dumps({'phase': label, 'state': 'starting'}), flush=True)
                action()
                print(json.dumps({'phase': label, 'state': 'staged', 'versions_checked': len(self.results)}), flush=True)
            self.reconcile_ledgers()
            if {row['id'] for row in self.results} != set(self.verified):
                raise StorageError('migration_version_set_mismatch')
            if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise StorageError('migration_foreign_key_failure')
            count = connection.execute('SELECT count(*) FROM migration_object WHERE migration_id=?', (self.migration_id,)).fetchone()[0]
            if count != sum(len(item['files']) for item in self.manifest['roots'].values()):
                raise StorageError('migration_object_count_mismatch')
            counts = {table: connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in
                ('publication', 'price_row', 'daily_metric', 'source_price_value', 'source_observation', 'row_provenance',
                 'original_object', 'document', 'node', 'current_publication', 'operation', 'budget_scope', 'attempt', 'historical_archive', 'migration_object')}
            connection.execute("UPDATE migration SET state='verified',verified_at=? WHERE id=?", (now(), self.migration_id))
            return {'already_imported': False, 'migration_id': self.migration_id, 'counts': counts, 'versions': self.results}


def slice_projection(manifest, metadata):
    def available(document):
        if document.get('inherited_public_available_at'):
            return datetime.fromisoformat(document['inherited_public_available_at']).astimezone(timezone.utc).isoformat()
        if document['publication_precision'] == 'date':
            value = datetime.combine(date.fromisoformat(document['published_at']) + timedelta(days=1), datetime.min.time(), ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
        elif document['published_at']:
            value = datetime.fromisoformat(document['published_at']).astimezone(timezone.utc)
        else:
            value = datetime.fromisoformat(metadata['first_seen_at'])
        return value.isoformat()
    documents = manifest.get('documents') or [{**manifest['document'], 'pdf_object_id': metadata['pdf_object_id']}]
    documents = [{**item, 'public_available_at': available(item)} for item in documents]
    return {**manifest, 'documents': documents, 'snapshot_id': metadata['snapshot_id'],
        'first_seen_at': metadata['first_seen_at'], 'recorded_at': metadata['recorded_at'],
        'document_public_available_at': documents[0]['public_available_at'], 'observed_count': len(manifest['bars']),
        'open_session_count': len(manifest['calendar_dates']),
        'unknown_missing_dates': sorted(set(manifest['calendar_dates']) - {row['trade_date'] for row in manifest['bars']})}


def main():
    parser = argparse.ArgumentParser()
    for option in ('manifest', 'copies', 'validation', 'target', 'output'):
        parser.add_argument('--' + option, type=Path, required=True)
    for option in ('manifest-sha256', 'validation-sha256', 'migration-id'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.is_absolute() or args.output.resolve() != args.output or fingerprint(args.manifest) != args.manifest_sha256 or fingerprint(args.validation) != args.validation_sha256:
        raise StorageError('migration_frozen_input_mismatch')
    manifest = json.loads(args.manifest.read_bytes())
    validation = json.loads(args.validation.read_bytes())
    if args.target.resolve() != args.target:
        raise StorageError('migration_requires_canonical_target')
    roots = {key: str(args.copies / key) for key in manifest['roots']}
    if any(args.output == root or root in args.output.parents for root in
           (args.copies, args.target, *(Path(x['original_root']) for x in manifest['roots'].values()))):
        raise StorageError('migration_report_must_be_outside_data')
    for item in [args.copies, *(Path(x['original_root']) for x in manifest['roots'].values())]:
        if args.target == item or item in args.target.parents or args.target in item.parents:
            raise StorageError('migration_target_overlap')
    verify_copies(manifest, roots)
    if args.target.exists() and any(args.target.iterdir()):
        with Database(args.target).read() as connection:
            owned = connection.execute('SELECT source_manifest_sha256 FROM migration WHERE id=?', (args.migration_id,)).fetchone()
            if owned is None or owned[0] != args.manifest_sha256:
                raise StorageError('migration_requires_new_or_owned_target')
    elif not args.target.exists():
        args.target.mkdir(mode=0o700)
    started = time.perf_counter()
    result = Importer(Database(args.target), args.copies, manifest, args.manifest_sha256, validation,
                      args.validation_sha256, args.migration_id).run()
    verify_copies(manifest, roots)
    result.update(seconds=time.perf_counter() - started, source_manifest_sha256=args.manifest_sha256,
                  validation_sha256=args.validation_sha256, target=str(args.target))
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if key not in ('versions', 'target')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
