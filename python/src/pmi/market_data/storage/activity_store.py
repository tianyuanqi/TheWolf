"""量额SQL适配器：独立指标事实、价格绑定、观察和操作同事务发布。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import hashlib
from pathlib import Path
import re
import time
from threading import Event
from typing import Iterator

from pmi.market_data.activity.model import ActivityError, MARKET, MARKET_IDS, TWO_MARKET, SERIES, canonical, digest, identifier, load
from .database import Database, StorageError, now
from .documents import Documents
from .facts import Facts
from .observations import observation as add_observation, provenance
from .originals import Originals
from .publications import Publications, ValidationProof
from .snapshots import Snapshots
from .tasks import task_writer
from . import state


class Store:
    def __init__(self, root: Path):
        self.root, self.database = root, Database(root)

    def check(self) -> None:
        self.database.check()

    @property
    def scope(self) -> str:
        with self.database.read() as connection:
            row = connection.execute("SELECT logical_scope FROM domain WHERE id='activity'").fetchone()
            if row is None:
                raise ActivityError('activity_not_initialized')
            return row[0]

    @contextmanager
    def lock(self, *, write: bool, cancel: Event | None = None) -> Iterator[None]:
        """读不加文件锁；写持统一租约，取消只中断等待，不重发出站请求。"""
        if not write:
            with self.database.read():
                yield
            return
        deadline = time.monotonic() + 30
        while True:
            lease = task_writer(self.root)
            try:
                lease.__enter__()
                break
            except StorageError as error:
                if str(error) != 'storage_writer_busy' or cancel is None or time.monotonic() >= deadline:
                    raise ActivityError('activity_busy' if str(error) == 'storage_writer_busy' else 'activity_storage_unavailable') from error
                if cancel.wait(.05):
                    raise ActivityError('activity_cancelled') from error
        try:
            yield
        finally:
            lease.__exit__(None, None, None)

    @staticmethod
    def location(series: str, target: str) -> tuple[str, ...]:
        """保留应用层逻辑键，绝不将其拼成文件系统路径。"""
        if series not in SERIES:
            raise ActivityError('unknown_activity_series', 422)
        if series in MARKET_IDS:
            try:
                if date.fromisoformat(target).isoformat() != target:
                    raise ValueError()
            except (ValueError, TypeError) as error:
                raise ActivityError('invalid_activity_parameters', 422) from error
        else:
            identifier(target)
        return ('head', series, target)

    def json(self, *parts: str) -> dict | None:
        with self.database.read() as connection:
            if len(parts) == 3 and parts[0] == 'head':
                return self._head(connection, parts[1], parts[2])
            if len(parts) != 2 or parts[0] not in ('operations', 'observation-refs', 'observations') or '/' in parts[1]:
                raise ActivityError('activity_key_invalid')
            return state.read(connection, 'activity', '/'.join(parts))

    def write(self, parts: tuple[str, ...], content: bytes, *, immutable: bool = False) -> None:
        """只接收明确运行状态，金融快照及原件只能走验证发布入口。"""
        if len(parts) != 2 or parts[0] != 'operations' or re.fullmatch(r'[a-zA-Z0-9_-]{1,80}\.json', parts[1]) is None:
            raise ActivityError('activity_key_invalid')
        value = load(content)
        if value['request_id'] + '.json' != parts[1]:
            raise ActivityError('activity_operation_mismatch')
        with self.database.transaction() as connection:
            reference = state.write(connection, 'activity', '/'.join(parts), value, immutable=immutable)
            connection.execute('''INSERT INTO operation VALUES(?,?,?,?,?) ON CONFLICT(domain_id,request_id)
                DO UPDATE SET revision=excluded.revision,state=excluded.state,publication_id=excluded.publication_id''',
                ('activity', value['request_id'], reference, value['state'], value['activity_id']))

    def operations(self) -> list[dict]:
        with self.database.read() as connection:
            refs = [row[0] for row in connection.execute("SELECT revision FROM operation WHERE domain_id='activity' ORDER BY request_id")]
            values = Documents(connection).get_many(refs)
            return [values[ref] for ref in refs]

    def _head(self, connection, series: str, target: str) -> dict | None:
        self.location(series, target)
        if series == MARKET:
            row = connection.execute('''SELECT c.metadata FROM current_publication c JOIN publication p ON p.id=c.publication_id
                WHERE c.domain_id='activity' AND c.subject=? ORDER BY p.sequence DESC LIMIT 1''', (series,)).fetchone()
        else:
            row = connection.execute("SELECT metadata FROM current_publication WHERE domain_id='activity' AND subject=? AND binding=?", (series, target)).fetchone()
        return Documents(connection).get(row[0]) if row else None

    def current(self, series: str, target: str) -> dict | None:
        with self.database.read() as connection:
            value = self._head(connection, series, target)
            if value and (value['series_id'] != series or value['target'] != target):
                if series == MARKET and value['series_id'] == series:
                    return None
                raise ActivityError('activity_identity_mismatch')
            return value

    def latest_anchor(self, series: str, before: str) -> str | None:
        with self.database.read() as connection:
            if series == MARKET:
                pointer = self._head(connection, series, before)
                return pointer['target'] if pointer and pointer['target'] <= before else None
            row = connection.execute("SELECT max(binding) FROM current_publication WHERE domain_id='activity' AND subject=? AND binding<=?", (series, before)).fetchone()
            return row[0]

    def fixed(self, activity_id: str) -> dict | None:
        with self.database.read() as connection:
            row = connection.execute("SELECT 1 FROM publication WHERE id=? AND domain_id='activity' AND legacy_status='published'", (identifier(activity_id),)).fetchone()
            return Documents(connection).get(activity_id) if row else None

    def observations(self, activity_id: str, manifest: dict, *, originals: dict[str, bytes] | None = None) -> list[dict]:
        """SQL成员和已提交操作证明归属；普通读不逐原件复验。"""
        if originals is not None:
            if (set(originals) != {source['object_id'] for source in manifest['sources']}
                    or any(hashlib.sha256(raw).hexdigest() != reference for reference, raw in originals.items())):
                raise ActivityError('activity_evidence_invalid')
        with self.database.read() as connection:
            index = state.read(connection, 'activity', 'observation-refs/' + identifier(activity_id) + '.json')
            binding = {'series_id': manifest['series_id'], 'activity_id': activity_id, 'price_snapshot_id': manifest['price_snapshot_id']}
            if index is None or set(index) != {*binding, 'entries'} or any(index[k] != v for k, v in binding.items()):
                raise ActivityError('activity_observation_invalid')
            result = []
            for entry in index['entries']:
                member = connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?', (activity_id, entry['observation_id'])).fetchone()
                operation = connection.execute("SELECT revision FROM operation WHERE domain_id='activity' AND request_id=? AND publication_id=? AND state='completed'", (entry['request_id'], activity_id)).fetchone()
                if not member or not operation:
                    raise ActivityError('activity_observation_invalid')
                committed = Documents(connection).get(operation[0])
                if committed['observation_id'] != entry['observation_id']:
                    raise ActivityError('activity_observation_invalid')
                receipt = Documents(connection).get(entry['observation_id'])
                if (not isinstance(receipt, dict) or set(receipt) != {*binding, 'sources'}
                        or any(receipt[k] != v for k, v in binding.items())):
                    raise ActivityError('activity_observation_invalid')
                result.append({**receipt, **entry})
            return result

    def original(self, object_id: str) -> bytes:
        return Originals(self.database).get(identifier(object_id), limit=4 * 1024 * 1024)

    def originals(self, object_ids: list[str]) -> dict[str, bytes]:
        return {ref: self.original(ref) for ref in object_ids}

    def publish(self, manifest: dict, originals: dict[str, bytes], expected: str | None, operation: dict, observation: dict) -> str:
        """防降级、来源重放、观察时点检查在同一候选事务完成后发布。"""
        from .validation import check_activity
        series = manifest['series_id']
        target = manifest['price_snapshot_id'] or manifest['anchor_date']
        with self.database.transaction() as connection:
            pointer = self._head(connection, series, target)
            if (pointer['activity_id'] if pointer else None) != expected:
                raise ActivityError('activity_cas_conflict')
            if pointer:
                previous = {row['trade_date']: row for row in self.fixed(pointer['activity_id'])['rows']}
                for row in manifest['rows']:
                    if row['trade_date'] not in previous:
                        continue
                    pairs = [(previous[row['trade_date']][k], row[k]) for k in ('volume', 'amount')] if series not in MARKET_IDS else [
                        (x, next((v for v in row['components'][k] if v['locator'] == x['locator']), {'value': None}))
                        for k in (('sse', 'szse') if series == TWO_MARKET else ('sse', 'szse', 'bse')) for x in previous[row['trade_date']]['components'][k]]
                    if any(before['value'] is not None and after['value'] is None for before, after in pairs):
                        raise ActivityError('activity_degradation_rejected')
            if set(originals) != {source['object_id'] for source in manifest['sources']}:
                raise ActivityError('activity_evidence_invalid')
            for reference, raw in originals.items():
                if hashlib.sha256(raw).hexdigest() != identifier(reference) or Originals(self.database).put(raw) != reference:
                    raise ActivityError('activity_evidence_invalid')
            identity, rows = Snapshots(connection).activity(manifest)
            receipt = {**observation, 'activity_id': identity, 'price_snapshot_id': manifest['price_snapshot_id']}
            binding = {'series_id': series, 'activity_id': identity, 'price_snapshot_id': manifest['price_snapshot_id']}
            if set(receipt) != {*binding, 'sources'} or any(receipt[k] != v for k, v in binding.items()):
                raise ActivityError('activity_observation_invalid')
            if any(set(source) != {'source', 'object_id', 'url', 'started_at', 'completed_at', 'published_at'} for source in receipt['sources']):
                raise ActivityError('activity_observation_invalid')
            docs, publications = Documents(connection), Publications(connection)
            receipt_id = docs.put(receipt)
            proof = ValidationProof('activity-publish-sql-v1', digest(manifest), now(), {'observation': receipt_id})
            dates = manifest['calendar_dates']
            publications.add(identity, domain='activity', subject=series, rows=rows, proof=proof,
                base=expected, coverage_start=dates[0], coverage_end=dates[-1],
                bindings={'price': manifest['price_snapshot_id']} if manifest['price_snapshot_id'] else {})
            first = connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=?', (identity,)).fetchone() is None
            publications.observe(identity, receipt_id, first=first)
            check_activity(self.database, connection, identity)
            sources = {}
            for source in receipt['sources']:
                sources.setdefault(source['object_id'], []).append(add_observation(connection, 'activity', receipt_id, source))
            for row in manifest['rows']:
                fields = [(market + ':' + str(i), value) for market, values in row['components'].items() for i, value in enumerate(values)] if 'components' in row else [(name, row[name]) for name in ('amount', 'volume')]
                for name, field in fields:
                    ref = Facts(connection).metric(series, row['trade_date'], name, field)
                    if field.get('object_id'):
                        provenance(connection, 'metric', ref, sources, [field])
            key = 'observation-refs/' + identity + '.json'
            index = state.read(connection, 'activity', key) or {**binding, 'entries': []}
            if any(entry['request_id'] == operation['request_id'] for entry in index['entries']):
                raise ActivityError('activity_operation_mismatch')
            index['entries'].append({'request_id': operation['request_id'], 'observation_id': receipt_id})
            state.write(connection, 'activity', key, index)
            committed = {**operation, 'state': 'completed', 'activity_id': identity, 'reason': None, 'observation_id': receipt_id}
            self.write(('operations', operation['request_id'] + '.json'), canonical(committed))
            pointer = {'series_id': series, 'target': target, 'activity_id': identity, 'operation': committed, 'observation_id': receipt_id}
            head = publications.head('activity', series, target)
            publications.select(identity, domain='activity', subject=series, binding=target, observation=receipt_id,
                                metadata=docs.put(pointer), expected=head[0] if head else None)
            return identity
