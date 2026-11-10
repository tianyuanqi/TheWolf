"""对SQL固定输入重放现有来源规则；仅用于导入、发布与完整性检查。"""
from __future__ import annotations

from datetime import datetime
import hashlib
import sqlite3
from typing import Any

from .database import Database, StorageError, canonical, digest
from .documents import Documents
from .originals import Originals


class EvidenceStore:
    """给既有ETF纯验证器的SQL/原件适配器；不是产品普通读取入口。"""

    def __init__(self, database: Database, connection: sqlite3.Connection):
        self.database, self.connection = database, connection
        row = connection.execute("SELECT logical_scope FROM domain WHERE id='etf' AND initialized=1").fetchone()
        if row is None:
            raise StorageError('storage_etf_not_initialized')
        self.scope = row[0]

    def get_json(self, identifier: str) -> Any:
        return Documents(self.connection).get(identifier)

    def get_many(self, identifiers: list[str]) -> dict[str, Any]:
        return Documents(self.connection).get_many(identifiers)

    def get(self, identifier: str) -> bytes:
        return Originals(self.database).get(identifier)

    def current_id(self) -> str | None:
        row = self.connection.execute("SELECT publication_id FROM current_publication WHERE domain_id='etf' AND subject='etf-flow' AND binding=''").fetchone()
        return row[0] if row else None

    def journal(self, key: str) -> tuple[str | None, Any | None]:
        row = self.connection.execute('''SELECT j.id,j.value_document FROM journal_head h
            JOIN journal_revision j ON j.id=h.revision_id WHERE h.domain_id='etf' AND h.journal_key=?''', (key,)).fetchone()
        return (row[0], self.get_json(row[1])) if row else (None, None)


def price_receipt(index_id: str, snapshot_id: str, originals: tuple) -> dict:
    """原v2观察身份算法；迁移检查时刻不替代原来源完成时刻。"""
    from pmi.market_data.index_series_contract import utc
    sources = [{'source': item.source, 'url': item.url, 'started_at': utc(item.started_at),
        'completed_at': utc(item.completed_at), 'object_id': hashlib.sha256(item.content).hexdigest(),
        'published_at': None} for item in originals]
    return {'index_id': index_id, 'snapshot_id': snapshot_id, 'sources': sources,
        'observed_at': max((item['completed_at'] for item in sources), key=lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')))}


def check_price(database: Database, connection: sqlite3.Connection, identity: str) -> None:
    from pmi.market_data.index_catalog import get_index
    from pmi.market_data.index_series_contract import Original, rebuild_manifest
    docs = Documents(connection)
    manifest = docs.get(identity)
    index = get_index(manifest['instrument']['id'])
    observations = list(connection.execute('SELECT observation_id FROM publication_observation WHERE publication_id=?', (identity,)))
    if not observations:
        raise StorageError('storage_publication_observation_missing')
    for row in observations:
        receipt = docs.get(row[0])
        if digest(receipt) != row[0] or receipt['snapshot_id'] != identity:
            raise StorageError('storage_price_observation_invalid')
        originals = tuple(Original(item['source'], Originals(database).get(item['object_id']),
            item['started_at'], item['completed_at'], item['url']) for item in receipt['sources'])
        if price_receipt(index.index_id, identity, originals) != receipt:
            raise StorageError('storage_price_observation_invalid')
        rebuild_manifest(index, manifest, originals)


def check_activity(database: Database, connection: sqlite3.Connection, identity: str) -> None:
    from pmi.market_data.activity import two_market, three_market
    from pmi.market_data.activity.facts import index_manifest, market_from_originals
    from pmi.market_data.activity.model import Original, MARKET_IDS, TWO_MARKET, rule
    from pmi.market_data.index_history_calendar import complete_window, from_manifest_window
    docs = Documents(connection)
    manifest = docs.get(identity)
    series = manifest['series_id']
    sources = [Original(row['source'], Originals(database).get(row['object_id']), row['url'], '', '') for row in manifest['sources']]
    if series in MARKET_IDS:
        window = complete_window(datetime.fromisoformat(manifest['anchor_date'] + 'T00:00:00+08:00')) if manifest['source_policy_version'] == three_market.POLICY else from_manifest_window(manifest)
        if series == TWO_MARKET:
            rebuilt = two_market.manifest(window, sources, policy_version=manifest['source_policy_version'])
        elif manifest['source_policy_version'] == three_market.POLICY:
            rebuilt = three_market.manifest(window, sources)
        else:
            rebuilt = market_from_originals(window, sources)
    else:
        if not rule(series).admitted:
            raise StorageError('storage_activity_source_unverified')
        binding = connection.execute("SELECT bound_id FROM publication_binding WHERE publication_id=? AND role='price'", (identity,)).fetchone()
        if binding is None or binding[0] != manifest['price_snapshot_id']:
            raise StorageError('storage_activity_binding_invalid')
        price = {**docs.get(binding[0]), 'snapshot_id': binding[0]}
        rebuilt = index_manifest(series, price, sources[0], policy_version=manifest['source_policy_version'])
    if canonical(rebuilt) != canonical(manifest):
        raise StorageError('storage_activity_replay_mismatch')
    observations = list(connection.execute('SELECT observation_id FROM publication_observation WHERE publication_id=?', (identity,)))
    if not observations:
        raise StorageError('storage_publication_observation_missing')
    for row in observations:
        receipt = docs.get(row[0])
        if digest(receipt) != row[0] or receipt['series_id'] != series or receipt['activity_id'] != identity or receipt['price_snapshot_id'] != manifest['price_snapshot_id']:
            raise StorageError('storage_activity_observation_invalid')
        refs = [{key: source[key] for key in ('source', 'object_id', 'url')} for source in receipt['sources']]
        if sorted(refs, key=canonical) != sorted(manifest['sources'], key=canonical):
            raise StorageError('storage_activity_observation_invalid')
        for source in receipt['sources']:
            start, end = (datetime.fromisoformat(source[key]) for key in ('started_at', 'completed_at'))
            if source['published_at'] is not None or start.utcoffset() is None or end.utcoffset() is None or start > end:
                raise StorageError('storage_activity_observation_invalid')


def check_etf(database: Database, connection: sqlite3.Connection, identity: str) -> None:
    from pmi.market_data.etf_flow.repository import Repository, group_ids
    store = EvidenceStore(database, connection)
    repository = Repository(store)
    loaded = repository.load(identity)
    for group in group_ids(loaded.config, loaded.manifest['selection_at']):
        repository.evaluations(loaded, 'current', group)
        repository.evaluations(loaded, 'original', group)


def check_all(database: Database, connection: sqlite3.Connection) -> None:
    """当前格式重放来源；退役格式以已独立验证的固定内容/原件指纹保全。"""
    for row in connection.execute('SELECT id,domain_id,legacy_status FROM publication ORDER BY domain_id,subject,sequence'):
        if row['domain_id'] == 'price-v2':
            check_price(database, connection, row['id'])
        elif row['domain_id'] == 'activity':
            check_activity(database, connection, row['id'])
        elif row['domain_id'] == 'etf':
            check_etf(database, connection, row['id'])
        elif row['domain_id'] not in ('retired-csi', 'retired-slice', 'stock-query') or row['legacy_status'] not in ('retired', 'unaccepted'):
            raise StorageError('storage_unknown_publication_domain')
    if connection.execute("SELECT 1 FROM domain WHERE id='etf'").fetchone():
        from .etf_cache import verify_proofs
        from .journals import Journals
        journals = Journals(connection, 'etf')
        for row in connection.execute("SELECT id FROM journal_revision WHERE domain_id='etf'"):
            journals.wrapper(row[0])
        verify_proofs(database, connection)
