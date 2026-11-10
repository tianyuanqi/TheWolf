"""本地结构/全量完整性检查；只写维护回执，绝不采集、发布或消费额度。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Callable
from uuid import uuid4

from .database import Database, StorageError, digest, now
from .documents import Documents
from .originals import Originals
from .publications import Publications

STRUCTURE_AGE = timedelta(hours=24)
FULL_AGE = timedelta(days=7)
VALIDATOR_VERSION = 'sqlite-integrity-v1'


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise StorageError('storage_invalid_check_time')
    return result


class Integrity:
    """同一单写者租约串行检查；正常页面只读取健康状态，不重验原件。"""

    def __init__(self, database: Database, clock: Callable[[], datetime] | None = None):
        self.database = database
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def status(self) -> dict:
        """返回截止时间与隔离状态；GET不补写检查记录或启动采集。"""
        with self.database.read() as connection:
            row = connection.execute('SELECT quarantined,reason,last_structure,last_full FROM integrity_health WHERE singleton=1').fetchone()
            if row is None:
                raise StorageError('storage_health_missing')
            point = self.clock()
            if point.utcoffset() is None:
                raise StorageError('storage_invalid_check_time')
            due_structure = row[2] is None or point >= _time(row[2]) + STRUCTURE_AGE or point < _time(row[2])
            due_full = row[3] is None or point >= _time(row[3]) + FULL_AGE or point < _time(row[3])
            return {'quarantined': bool(row[0]), 'reason': row[1], 'last_structure': row[2], 'last_full': row[3],
                'structure_due': due_structure, 'full_due': due_full, 'available': not row[0] and not due_structure and not due_full}

    def require_available(self) -> None:
        value = self.status()
        if value['quarantined']:
            raise StorageError('storage_quarantined')
        if not value['available']:
            raise StorageError('storage_integrity_check_due')

    def _structure(self, connection: sqlite3.Connection) -> dict[str, int]:
        if [row[0] for row in connection.execute('PRAGMA quick_check')] != ['ok']:
            raise StorageError('storage_sqlite_corrupt')
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise StorageError('storage_reference_broken')
        mismatch = connection.execute('''SELECT p.id FROM publication p JOIN document d ON d.id=p.id
            JOIN validation_receipt v ON v.id=p.validation_id WHERE d.canonical_sha256<>v.input_sha256 OR v.result<>'passed' LIMIT 1''').fetchone()
        if mismatch:
            raise StorageError('storage_validation_receipt_invalid')
        pubs = Publications(connection)
        for publication in connection.execute('SELECT id FROM publication'):
            pubs.check_lineage(publication[0])
        for head in connection.execute('SELECT * FROM current_publication'):
            publication = connection.execute('SELECT domain_id,subject,legacy_status FROM publication WHERE id=?', (head['publication_id'],)).fetchone()
            if tuple(publication) != (head['domain_id'], head['subject'], 'published'):
                raise StorageError('storage_current_binding_invalid')
            if head['observation_id'] is not None and connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?', (head['publication_id'], head['observation_id'])).fetchone() is None:
                raise StorageError('storage_current_observation_invalid')
            selected = {tuple(row[:4]): row[4] for row in connection.execute('SELECT row_kind,instrument_id,trade_date,metric,projection_id FROM current_row WHERE domain_id=? AND subject=? AND binding=?', tuple(head[:3]))}
            if selected != pubs.rows(head['publication_id']):
                raise StorageError('storage_current_rows_invalid')
        for kind, table in (('price', 'price_row'), ('metric', 'daily_metric')):
            if connection.execute(f'''SELECT 1 FROM row_provenance p LEFT JOIN {table} r ON r.id=p.row_id
                WHERE p.kind=? AND r.id IS NULL LIMIT 1''', (kind,)).fetchone():
                raise StorageError('storage_row_provenance_invalid')
            # 缺失行表达“未取得来源值”，不能为它伪造原件引用；其口径由发布重放核验。
            present = "r.value IS NOT NULL AND " if kind == 'metric' else ''
            if connection.execute(f'''SELECT 1 FROM {table} r WHERE {present}NOT EXISTS
                (SELECT 1 FROM row_provenance p WHERE p.kind=? AND p.row_id=r.id) LIMIT 1''', (kind,)).fetchone():
                raise StorageError('storage_row_provenance_missing')
        if connection.execute("SELECT 1 FROM row_provenance WHERE kind NOT IN('price','metric') LIMIT 1").fetchone():
            raise StorageError('storage_row_provenance_invalid')
        for kind, table, fact in (('price', 'price_projection', 'price_row'), ('metric', 'metric_projection', 'daily_metric')):
            metric = ' OR p.metric<>r.metric' if kind == 'metric' else ''
            if connection.execute(f'''SELECT 1 FROM {table} p JOIN {fact} r ON r.id=p.row_id
                WHERE p.instrument_id<>r.instrument_id OR p.trade_date<>r.trade_date{metric} LIMIT 1''').fetchone():
                raise StorageError('storage_projection_identity_invalid')
            metric = ' OR p.metric<>r.metric' if kind == 'metric' else " OR r.metric<>''"
            if connection.execute(f'''SELECT 1 FROM publication_row r LEFT JOIN {table} p ON p.id=r.projection_id
                WHERE r.row_kind=? AND r.projection_id IS NOT NULL AND
                (p.id IS NULL OR p.instrument_id<>r.instrument_id OR p.trade_date<>r.trade_date{metric}) LIMIT 1''', (kind,)).fetchone():
                raise StorageError('storage_publication_row_invalid')
        if connection.execute("SELECT 1 FROM publication_row WHERE row_kind NOT IN('price','metric','activity') LIMIT 1").fetchone():
            raise StorageError('storage_publication_row_invalid')
        return {table: connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in
            ('publication', 'price_row', 'daily_metric', 'original_object', 'document', 'attempt', 'operation')}

    def _full(self, connection: sqlite3.Connection, semantic_check: Callable[[sqlite3.Connection], None]) -> dict[str, int]:
        docs = Documents(connection)
        checked = {'nodes': 0, 'documents': 0, 'originals': 0, 'prices': 0, 'metrics': 0}
        for row in connection.execute('SELECT * FROM node ORDER BY id'):
            children = tuple((edge[0], edge[1]) for edge in connection.execute('SELECT e.name,n.fingerprint FROM node_edge e JOIN node n ON n.id=e.child WHERE e.parent=? ORDER BY e.position', (row['id'],)))
            if digest([row['kind'], row['atom'], children]) != row['fingerprint']:
                raise StorageError('storage_node_fingerprint_invalid')
            checked['nodes'] += 1
        for row in connection.execute('SELECT * FROM price_row ORDER BY id'):
            values = tuple(row[key] for key in ('opening', 'high', 'low', 'closing', 'volume', 'amount'))
            revision = digest([values, row['unit'], row['precision'], row['price_type']])
            if revision != row['row_version'] or digest(['price', row['instrument_id'], row['trade_date'], revision]) != row['id']:
                raise StorageError('storage_price_fingerprint_invalid')
            checked['prices'] += 1
        for row in connection.execute('SELECT * FROM daily_metric ORDER BY id'):
            revision = digest([row['value'], row['unit'], row['missing_reason']])
            if revision != row['row_version'] or digest(['metric', row['instrument_id'], row['trade_date'], row['metric'], revision]) != row['id']:
                raise StorageError('storage_metric_fingerprint_invalid')
            checked['metrics'] += 1
        # 流式批取，固定SQL输入；不把全部原件或所有文档驻留内存。
        cursor = connection.execute('SELECT id,canonical_sha256 FROM document ORDER BY id')
        while group := cursor.fetchmany(100):
            values = docs.get_many([row[0] for row in group])
            for identity, expected in group:
                if digest(values[identity]) != expected:
                    raise StorageError('storage_document_fingerprint_invalid')
                checked['documents'] += 1
        for row in connection.execute('SELECT id FROM original_object ORDER BY id'):
            Originals(self.database).get(row[0])
            checked['originals'] += 1
        semantic_check(connection)
        return checked

    def run(self, kind: str, *, semantic_check: Callable[[sqlite3.Connection], None] | None = None,
            release_quarantine: bool = False) -> dict:
        """完整成功才更新期限；异常/中断留回执，解除隔离须显式完整复核。"""
        if kind not in ('structure', 'full') or release_quarantine and kind != 'full' or kind == 'full' and semantic_check is None:
            raise StorageError('storage_integrity_request_invalid')
        identifier, started = uuid4().hex, self.clock().isoformat()
        with self.database.writer() as connection:
            with self.database.transaction():
                connection.execute("UPDATE integrity_check SET state='interrupted',finished_at=? WHERE state='running'", (started,))
                versions = [[row[0], row[1]] for row in connection.execute('SELECT id,validation_id FROM publication ORDER BY id')]
                version_set = Documents(connection).put({'validator': VALIDATOR_VERSION, 'versions': versions})
                connection.execute('INSERT INTO integrity_check VALUES(?,?,?,?,?,?,?)', (identifier, kind, started, None, 'running', version_set, None))
            details = {}
            try:
                connection.execute('BEGIN')
                details['counts'] = self._structure(connection)
                if kind == 'full':
                    details['full'] = self._full(connection, semantic_check)
                connection.rollback()
            except BaseException as error:
                connection.rollback()
                state = 'interrupted' if not isinstance(error, Exception) else 'failed'
                # 明细不写任意异常文本/路径；异常继续向受控调用者传播。
                with self.database.transaction():
                    reference = Documents(connection).put({'validator': VALIDATOR_VERSION, 'error_type': type(error).__name__})
                    connection.execute('UPDATE integrity_check SET finished_at=?,state=?,details=? WHERE id=?', (self.clock().isoformat(), state, reference, identifier))
                    if state == 'failed':
                        connection.execute("UPDATE integrity_health SET quarantined=1,reason='integrity_check_failed' WHERE singleton=1")
                raise
            completed = self.clock().isoformat()
            with self.database.transaction():
                reference = Documents(connection).put({'validator': VALIDATOR_VERSION, **details})
                connection.execute("UPDATE integrity_check SET finished_at=?,state='passed',details=? WHERE id=?", (completed, reference, identifier))
                connection.execute('UPDATE integrity_health SET last_structure=? WHERE singleton=1', (completed,))
                if kind == 'full':
                    connection.execute('UPDATE integrity_health SET last_full=? WHERE singleton=1', (completed,))
                if release_quarantine:
                    connection.execute('UPDATE integrity_health SET quarantined=0,reason=NULL WHERE singleton=1')
            return {'id': identifier, 'kind': kind, 'state': 'passed', 'completed_at': completed, **details}
