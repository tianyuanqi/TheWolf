"""不可变发布与行选择差量；当前索引只保存键和引用。"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any

from .database import StorageError, digest, identifier
from .documents import Documents

RowKey = tuple[str, str, str, str]  # 类型、标的、交易日、指标


@dataclass(frozen=True)
class ValidationProof:
    """内部验证器完成来源/金融/时间检查后的凭据，不能从HTTP参数构造。"""
    validator: str
    input_sha256: str
    checked_at: str
    details: dict[str, Any]


class Publications:
    """调用者持同一单写事务；技术差量父链不替代原对象的金融父版本字段。"""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.documents = Documents(connection)

    def domain(self, name: str, scope: str, *, legacy_root: str | None = None) -> None:
        if not name or not scope:
            raise StorageError('storage_invalid_domain')
        self.connection.execute('INSERT OR IGNORE INTO domain VALUES(?,?,1,?)', (name, scope, legacy_root))
        value = self.connection.execute('SELECT logical_scope,initialized,legacy_root FROM domain WHERE id=?', (name,)).fetchone()
        if tuple(value) != (scope, 1, legacy_root):
            raise StorageError('storage_scope_conflict')

    def receipt(self, proof: ValidationProof) -> str:
        if not proof.validator or not proof.checked_at:
            raise StorageError('storage_validation_required')
        identifier(proof.input_sha256)
        details = self.documents.put(proof.details, 'validation-details')
        reference = digest([proof.validator, proof.input_sha256, proof.checked_at, details])
        self.connection.execute('INSERT OR IGNORE INTO validation_receipt VALUES(?,?,?,?,?,?)',
                                (reference, proof.validator, proof.input_sha256, proof.checked_at, 'passed', details))
        return reference

    def rows(self, publication_id: str, *, start: str | None = None, end: str | None = None,
             kind: str | None = None, instrument: str | None = None) -> dict[RowKey, str]:
        """固定发布向祖先寻找最近的键变更；NULL是窗口移除，不是数值零。"""
        identifier(publication_id)
        if self.connection.execute('SELECT 1 FROM publication WHERE id=?', (publication_id,)).fetchone() is None:
            raise StorageError('storage_publication_not_found')
        self.check_lineage(publication_id)
        predicates, parameters = [], [publication_id]
        for column, operator, value in [('trade_date', '>=', start), ('trade_date', '<=', end), ('row_kind', '=', kind), ('instrument_id', '=', instrument)]:
            if value is not None:
                predicates.append('r.' + column + operator + '?')
                parameters.append(value)
        where = ('WHERE ' + ' AND '.join(predicates)) if predicates else ''
        query = '''WITH RECURSIVE lineage(id,depth) AS (
                     VALUES(?,0) UNION ALL
                     SELECT p.base_publication,l.depth+1 FROM publication p JOIN lineage l ON p.id=l.id
                     WHERE p.base_publication IS NOT NULL), ranked AS (
                     SELECT r.row_kind,r.instrument_id,r.trade_date,r.metric,r.projection_id,
                     row_number() OVER(PARTITION BY r.row_kind,r.instrument_id,r.trade_date,r.metric ORDER BY l.depth) AS choice
                     FROM publication_row r JOIN lineage l ON r.publication_id=l.id ''' + where + ''')
                   SELECT row_kind,instrument_id,trade_date,metric,projection_id FROM ranked
                   WHERE choice=1 AND projection_id IS NOT NULL ORDER BY instrument_id,trade_date,metric'''
        return {tuple(row[:4]): row[4] for row in self.connection.execute(query, parameters)}

    def check_lineage(self, publication_id: str) -> None:
        """UNION按ID去重保证坏链有限；父版本须属于同一领域/标的且严格更早。"""
        invalid = self.connection.execute('''WITH RECURSIVE lineage(id) AS (
            VALUES(?) UNION SELECT p.base_publication FROM publication p JOIN lineage l ON p.id=l.id
            WHERE p.base_publication IS NOT NULL)
            SELECT 1 FROM lineage l LEFT JOIN publication p ON p.id=l.id
            LEFT JOIN publication b ON b.id=p.base_publication
            WHERE p.id IS NULL OR (p.base_publication IS NOT NULL AND
                (b.id IS NULL OR b.domain_id<>p.domain_id OR b.subject<>p.subject OR b.sequence>=p.sequence)) LIMIT 1''',
            (identifier(publication_id),)).fetchone()
        if invalid:
            raise StorageError('storage_publication_lineage_invalid')

    def selected_rows(self, publication_id: str, *, start: str | None = None, end: str | None = None,
                      kind: str | None = None, instrument: str | None = None) -> dict[RowKey, str]:
        """固定ID恰为当前时使用物化键索引；历史ID仍按差量链解析，不换版本。"""
        identifier(publication_id)
        head = self.connection.execute('SELECT domain_id,subject,binding FROM current_publication WHERE publication_id=? LIMIT 1', (publication_id,)).fetchone()
        if head is None:
            return self.rows(publication_id, start=start, end=end, kind=kind, instrument=instrument)
        where, params = ['domain_id=?', 'subject=?', 'binding=?'], list(head)
        for column, operator, value in [('trade_date', '>=', start), ('trade_date', '<=', end), ('row_kind', '=', kind), ('instrument_id', '=', instrument)]:
            if value is not None:
                where.append(column + operator + '?')
                params.append(value)
        query = 'SELECT row_kind,instrument_id,trade_date,metric,projection_id FROM current_row WHERE ' + ' AND '.join(where) + ' ORDER BY instrument_id,trade_date,metric'
        return {tuple(row[:4]): row[4] for row in self.connection.execute(query, params)}

    def add(self, document_id: str, *, domain: str, subject: str, rows: dict[RowKey, str],
            proof: ValidationProof, base: str | None = None, coverage_start: str | None = None,
            coverage_end: str | None = None, status: str = 'published',
            bindings: dict[str, str] | None = None) -> str:
        """差量保存固定成员，保留旧版本；同ID重复仅在完全一致时复用。"""
        identifier(document_id)
        document = self.connection.execute('SELECT canonical_sha256 FROM document WHERE id=?', (document_id,)).fetchone()
        if document is None or document[0] != proof.input_sha256:
            raise StorageError('storage_validation_input_mismatch')
        existing = self.connection.execute('SELECT domain_id,subject,coverage_start,coverage_end,legacy_status FROM publication WHERE id=?', (document_id,)).fetchone()
        if existing is not None:
            if (tuple(existing) != (domain, subject, coverage_start, coverage_end, status)
                    or self.rows(document_id) != rows
                    or dict(self.connection.execute('SELECT role,bound_id FROM publication_binding WHERE publication_id=?', (document_id,))) != (bindings or {})):
                raise StorageError('storage_publication_collision')
            return document_id
        previous = {}
        if base is not None:
            old = self.connection.execute('SELECT domain_id,subject FROM publication WHERE id=?', (identifier(base),)).fetchone()
            if old is None or tuple(old) != (domain, subject):
                raise StorageError('storage_publication_base_mismatch')
            previous = self.rows(base)
        receipt = self.receipt(proof)
        sequence = self.connection.execute('SELECT coalesce(max(sequence),-1)+1 FROM publication WHERE domain_id=? AND subject=?', (domain, subject)).fetchone()[0]
        self.connection.execute('INSERT INTO publication VALUES(?,?,?,?,?,?,?,?,?)',
                                (document_id, domain, subject, sequence, base, coverage_start, coverage_end, status, receipt))
        changes = [(document_id, *key, rows.get(key)) for key in sorted(previous.keys() | rows.keys())
                   if previous.get(key) != rows.get(key)]
        self.connection.executemany('INSERT INTO publication_row VALUES(?,?,?,?,?,?)', changes)
        self.connection.executemany('INSERT INTO publication_binding VALUES(?,?,?)',
                                    [(document_id, role, bound) for role, bound in (bindings or {}).items()])
        return document_id

    def head(self, domain: str, subject: str, binding: str = '') -> sqlite3.Row | None:
        return self.connection.execute('SELECT publication_id,observation_id,metadata FROM current_publication WHERE domain_id=? AND subject=? AND binding=?', (domain, subject, binding)).fetchone()

    def select(self, publication_id: str, *, domain: str, subject: str, binding: str = '',
               observation: str | None = None, metadata: str | None = None,
               expected: str | None) -> None:
        """CAS与当前键索引在同一事务提交；不会把未发布或退役资料变成当前。"""
        saved = self.connection.execute('SELECT domain_id,subject,legacy_status FROM publication WHERE id=?', (identifier(publication_id),)).fetchone()
        if saved is None or tuple(saved[:2]) != (domain, subject) or saved[2] != 'published':
            raise StorageError('storage_publication_not_eligible')
        current = self.head(domain, subject, binding)
        if (current[0] if current else None) != expected:
            raise StorageError('storage_publication_changed')
        if observation is not None and self.connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?', (publication_id, observation)).fetchone() is None:
            raise StorageError('storage_observation_not_member')
        wanted = self.rows(publication_id)
        before = {tuple(row[:4]): row[4] for row in self.connection.execute('SELECT row_kind,instrument_id,trade_date,metric,projection_id FROM current_row WHERE domain_id=? AND subject=? AND binding=?', (domain, subject, binding))}
        for key in before.keys() - wanted.keys():
            self.connection.execute('DELETE FROM current_row WHERE domain_id=? AND subject=? AND binding=? AND row_kind=? AND instrument_id=? AND trade_date=? AND metric=?', (domain, subject, binding, *key))
        for key, value in wanted.items():
            if before.get(key) != value:
                self.connection.execute('INSERT INTO current_row VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(domain_id,subject,binding,row_kind,instrument_id,trade_date,metric) DO UPDATE SET projection_id=excluded.projection_id',
                                        (domain, subject, binding, *key, value))
        self.connection.execute('INSERT INTO current_publication VALUES(?,?,?,?,?,?) ON CONFLICT(domain_id,subject,binding) DO UPDATE SET publication_id=excluded.publication_id,observation_id=excluded.observation_id,metadata=excluded.metadata',
                                (domain, subject, binding, publication_id, observation, metadata))

    def observe(self, publication_id: str, observation_id: str, *, first: bool = False) -> None:
        """获取观察独立于数值版本，旧固定版本的首次观察不会被新获取覆盖。"""
        if first:
            existing = self.connection.execute('SELECT observation_id FROM publication_observation WHERE publication_id=? AND first_observation=1', (publication_id,)).fetchone()
            if existing and existing[0] != observation_id:
                raise StorageError('storage_first_observation_conflict')
        self.connection.execute('INSERT OR IGNORE INTO publication_observation VALUES(?,?,?)', (publication_id, observation_id, int(first)))
