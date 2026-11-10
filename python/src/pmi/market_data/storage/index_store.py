"""指数固定版本的SQL读写；原件只在验证、更新及证据用例读取。"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable

from pmi.market_data import SnapshotError
from pmi.market_data.index_catalog import IndexDefinition, get_index
from pmi.market_data.index_history_calendar import FrozenWindow
from pmi.market_data.index_series_contract import Original, SeriesManifest, build_manifest, canonical, digest, parse_evidence
from .database import Database, StorageError, now
from .documents import Documents
from .observations import observation, provenance
from .originals import Originals
from .publications import Publications, ValidationProof
from .snapshots import Snapshots
from .index_status import (ACTIVE, TERMINAL, UpdateState, SeriesSnapshot, PublicationUncertain,
                           validate_id, load_json, idle_state, _validate_state, _validate_job_state, _instant, _receipt)
from . import state as states


def index_root(parent: Path, index: IndexDefinition) -> Path:
    """已登记指数共享一个物理库，领域身份只进入SQL键。"""
    if get_index(index.index_id) != index:
        raise SnapshotError('unknown_index_definition')
    Database(parent).check()
    return parent


def prepare_directories(parent: Path, index: IndexDefinition) -> Path:
    """更新不再创建指数子库；显式初始化/迁入完成后才能启写。"""
    database = Database(index_root(parent, index))
    with database.read() as connection:
        if connection.execute("SELECT 1 FROM domain WHERE id='price-v2' AND initialized=1").fetchone() is None:
            raise SnapshotError('price_store_not_initialized')
    return parent


def reject_sidecars(parent: Path, index: IndexDefinition) -> None:
    with Database(index_root(parent, index)).read():
        pass


def recover_locked(parent: Path, index: IndexDefinition, *, guard: Callable[[], None] | None = None) -> None:
    """SQLite事务保证原子性；遇到待恢复旁路文件拒绝，不自动修复或替换库。"""
    if guard:
        guard()
    reject_sidecars(parent, index)


def write_object(root: Path, content: bytes) -> str:
    database = Database(root)
    with database.transaction():
        return Originals(database).put(content)


def record_original(parent: Path, index: IndexDefinition, value: dict) -> None:
    """即使随后的金融校验失败，也保留已获取原件的完整观察时间。"""
    if value['index_id'] != index.index_id:
        raise SnapshotError('observation_identity_mismatch')
    database = Database(parent)
    with database.transaction() as connection:
        observation(connection, 'price-v2', value['job_id'], value)


def network_entries(parent: Path) -> list[dict]:
    with Database(parent).read() as connection:
        return states.read(connection, 'price-v2', 'legacy:slice-002245-sina/index-v2-network-ledger.jsonl') or []


def record_network(parent: Path, value: dict) -> None:
    """累计网络额度仅追加记录，不通过重启或迁移重置。"""
    database = Database(parent)
    with database.transaction() as connection:
        key = 'legacy:slice-002245-sina/index-v2-network-ledger.jsonl'
        entries = states.read(connection, 'price-v2', key) or []
        entries.append(value)
        from pmi.market_data.index_series_fetch import _totals
        _totals(entries)
        states.write(connection, 'price-v2', key, entries)


def _snapshot(connection: sqlite3.Connection, index: IndexDefinition, snapshot_id: str | None) -> dict | None:
    publications = Publications(connection)
    if snapshot_id is None:
        current = publications.head('price-v2', index.index_id)
        if current is None:
            return None
        snapshot_id = current[0]
        if connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?',
                              (snapshot_id, current[1])).fetchone() is None:
            raise SnapshotError('observation_membership_mismatch')
    validate_id(snapshot_id)
    row = connection.execute("SELECT 1 FROM publication WHERE id=? AND domain_id='price-v2' AND subject=? AND legacy_status='published'",
                             (snapshot_id, index.index_id)).fetchone()
    if row is None:
        return None
    observed = connection.execute('SELECT observation_id FROM publication_observation WHERE publication_id=? AND first_observation=1', (snapshot_id,)).fetchone()
    if observed is None:
        raise SnapshotError('observation_membership_mismatch')
    docs = Documents(connection)
    manifest, receipt = docs.get(snapshot_id), docs.get(observed[0])
    if receipt.get('index_id') != index.index_id or receipt.get('snapshot_id') != snapshot_id:
        raise SnapshotError('observation_identity_mismatch')
    return {**manifest, 'snapshot_id': snapshot_id, 'observation_id': observed[0], 'retrieval': receipt}


def read_snapshot(parent: Path, index: IndexDefinition, snapshot_id: str | None = None, *, connection: sqlite3.Connection | None = None) -> SeriesSnapshot | None:
    """只查询已验证的固定行；不读旧快照，不逐原件重放校验。"""
    database = Database(index_root(parent, index))
    if not database.exists:
        return None
    with nullcontext(connection) if connection is not None else database.read() as active:
        return _snapshot(active, index, snapshot_id)


def read_snapshot_locked(parent: Path, index: IndexDefinition, snapshot_id: str | None = None) -> dict | None:
    return read_snapshot(parent, index, snapshot_id)


def latest_success_at_locked(parent: Path, index: IndexDefinition) -> str | None:
    with Database(parent).read() as connection:
        current = Publications(connection).head('price-v2', index.index_id)
        return Documents(connection).get(current[1])['observed_at'] if current else None


def raw_status(parent: Path, index: IndexDefinition) -> UpdateState:
    database = Database(parent)
    if not database.exists:
        return idle_state(index)
    with database.read() as connection:
        value = states.read(connection, 'price-v2', 'legacy:slice-002245-sina/' + index.relative_dir + '/update-v2-status.json')
        if value is None:
            return idle_state(index)
        _validate_state(value, index)
        return value


def save_status(parent: Path, index: IndexDefinition, state: dict) -> None:
    _validate_state(state, index)
    with Database(parent).transaction() as connection:
        states.write(connection, 'price-v2', 'legacy:slice-002245-sina/' + index.relative_dir + '/update-v2-status.json', state)


def read_status(parent: Path, index: IndexDefinition) -> dict:
    """SQL提交证明优先；未提交运行态还须精确活动锁，不自动恢复状态。"""
    from pmi.market_data.index_activity import is_active
    with Database(parent).read():
        value = raw_status(parent, index)
        committed = committed_job_locked(parent, index, value.get('job_id'))
        if committed:
            return committed
        if value['stage'] in ACTIVE:
            if is_active(parent, index.index_id, value['job_id']):
                return value
            return {**value, 'stage': 'interrupted', 'result': 'interrupted', 'message': '任务已中断，旧快照保留'}
        if value['stage'] == 'completed' and value['result'] != 'source_not_ready':
            raise SnapshotError('completed_job_proof_missing')
        return value


def committed_job_locked(parent: Path, index: IndexDefinition, job_id: str | None) -> dict | None:
    if not job_id:
        return None
    with Database(parent).read() as connection:
        row = connection.execute("SELECT revision,publication_id FROM operation WHERE domain_id='price-v2' AND request_id=? AND state='completed'", (job_id,)).fetchone()
        if row is None:
            return None
        docs = Documents(connection)
        state = docs.get(row[0])
        member = connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?', (row[1], state['observation_id'])).fetchone()
        if member is None:
            raise SnapshotError('observation_membership_mismatch')
        _validate_job_state(state, index, job_id, row[1], docs.get(state['observation_id']))
        return state


def publish(parent: Path, index: IndexDefinition, window: FrozenWindow, manifest: SeriesManifest,
            originals: tuple[Original, ...], state: UpdateState, checkpoint: Callable[[str], None] | None = None) -> UpdateState:
    """原规则验证后单事务追加变化行、观察与提交任务；旧版本不复制或覆盖。"""
    _validate_state(state, index)
    if build_manifest(index, window, originals) != manifest or state['target_start'] != window.start or state['target_end'] != window.end:
        raise SnapshotError('publish_identity_mismatch')
    snapshot_id = digest(canonical(manifest))
    previous = committed_job_locked(parent, index, state['job_id'])
    if previous:
        if previous['snapshot_id'] != snapshot_id:
            raise SnapshotError('job_content_conflict')
        return previous
    database = Database(parent)
    for original in originals:
        with database.transaction():
            Originals(database).put(original.content)
    if checkpoint:
        checkpoint('objects_written')
    receipt = _receipt(index, snapshot_id, originals)
    observation_id = digest(canonical(receipt))
    completed = {**state, 'stage': 'completed', 'snapshot_id': snapshot_id, 'observation_id': observation_id,
                 'finished_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'last_success_at': receipt['observed_at']}
    _validate_job_state(completed, index, state['job_id'], snapshot_id, receipt)
    with database.transaction() as connection:
        if checkpoint:
            checkpoint('candidate_started')
        publications, docs = Publications(connection), Documents(connection)
        current = publications.head('price-v2', index.index_id)
        _, rows = Snapshots(connection).price(manifest)
        proof = ValidationProof('index-publish-sql-v1', snapshot_id, now(), {'observation': observation_id})
        publications.add(snapshot_id, domain='price-v2', subject=index.index_id, rows=rows, proof=proof,
            base=current[0] if current else None, coverage_start=manifest['calendar_dates'][0], coverage_end=manifest['calendar_dates'][-1])
        docs.put(receipt)
        first = connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=?', (snapshot_id,)).fetchone() is None
        publications.observe(snapshot_id, observation_id, first=first)
        source_ids = {}
        for source in receipt['sources']:
            source_ids.setdefault(source['object_id'], []).append(observation(connection, 'price-v2', observation_id, source))
        for bar in manifest['bars']:
            provenance(connection, 'price', rows['price', index.index_id, bar['trade_date'], ''], source_ids, bar['evidence_refs'])
        old = docs.get(current[0]) if current else None
        old_receipt = docs.get(current[1]) if current else None
        if current is None or (window.end >= old['window']['end'] and window.anchor_date >= old['window']['anchor_date']
                               and _instant(receipt['observed_at']) >= _instant(old_receipt['observed_at'])):
            publications.select(snapshot_id, domain='price-v2', subject=index.index_id, observation=observation_id,
                                expected=current[0] if current else None)
        connection.execute('INSERT INTO operation VALUES(?,?,?,?,?)', ('price-v2', state['job_id'], docs.put(completed), 'completed', snapshot_id))
        if checkpoint:
            checkpoint('before_commit')
    if checkpoint:
        checkpoint('after_commit')
    return completed


def read_original(parent: Path, index: IndexDefinition, snapshot_id: str, object_id: str) -> Original:
    """验证固定版本来源成员后，只读取所请求的一个原件。"""
    snapshot = read_snapshot(parent, index, snapshot_id)
    if snapshot is None:
        raise SnapshotError('index_evidence_not_found')
    validate_id(object_id)
    receipt = next((item for item in snapshot['retrieval']['sources'] if item['object_id'] == object_id), None)
    if receipt is None:
        raise SnapshotError('index_evidence_not_member')
    return Original(receipt['source'], Originals(Database(parent)).get(object_id), receipt['started_at'], receipt['completed_at'], receipt['url'])


def read_evidence(parent: Path, index: IndexDefinition, snapshot_id: str, object_id: str, *, connection: sqlite3.Connection | None = None) -> dict:
    snapshot = read_snapshot(parent, index, snapshot_id, connection=connection)
    if snapshot is None:
        raise SnapshotError('index_evidence_not_found')
    original = read_original(parent, index, snapshot_id, object_id)
    manifest = {key: value for key, value in snapshot.items() if key not in {'snapshot_id', 'observation_id', 'retrieval'}}
    evidence = parse_evidence(index, manifest, original)
    receipt = next(item for item in snapshot['retrieval']['sources'] if item['object_id'] == object_id)
    return {'snapshot_id': snapshot_id, 'observation_id': snapshot['observation_id'], **evidence,
            'retrieval': receipt, 'verification': snapshot['verification'],
            'text_preview': original.content[:4096].decode('utf-8', errors='replace'), 'preview_truncated': len(original.content) > 4096}
