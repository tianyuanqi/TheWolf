"""ETF使用统一SQLite及原件池；普通对象与账本读取只查询SQL。"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
from typing import Any, Iterator

from pmi.market_data.read_only import read_bytes
from pmi.market_data.etf_flow.model import FlowError, canonical, digest, object_id
from .database import CommitUncertain, Database, StorageError, fsync_directory, location as storage_location, now
from .documents import Documents
from .facts import Facts
from .journals import Journals
from .observations import observation, provenance
from .originals import Originals
from .publications import Publications, ValidationProof
from .tasks import task_writer

MAX_OBJECT_BYTES = 64 * 1024 * 1024


def location(path: Path, *, directory: bool = True) -> Path:
    """沿用ETF公开位置错误；统一数据根由数据库冻结并再次检查。"""
    try:
        storage_location(path, directory=directory)
    except (StorageError, OSError) as error:
        raise FlowError('etf_unsafe_location', 422) from error
    return path


class Store:
    """所有领域共享同一写租约；每次账本扣额在出站之前独立提交。"""

    def __init__(self, root: Path):
        self.root = location(root)
        self.database = Database(root)

    def check(self) -> None:
        self.database.check()

    @property
    def scope(self) -> str:
        if self.database.exists:
            with self.database.read() as connection:
                row = connection.execute("SELECT logical_scope FROM domain WHERE id='etf'").fetchone()
                if row:
                    return row[0]
        return digest({'format': 'etf-flow-root-v1', 'root': str(self.root)})

    @property
    def initialized(self) -> bool:
        self.check()
        if not self.database.exists:
            if any(self.root.iterdir()):
                raise FlowError('etf_incomplete_initialization')
            return False
        with self.database.read() as connection:
            row = connection.execute("SELECT initialized FROM domain WHERE id='etf'").fetchone()
            return row is not None and row[0] == 1

    def initialize(self) -> None:
        """只供显式初始化；已有数据库可增加空领域，不能重置已有额度/身份。"""
        scope = self.scope
        if self.initialized:
            raise FlowError('etf_already_initialized')
        if not self.database.exists:
            self.database.initialize()
        with self.database.writer(), self.database.transaction() as connection:
            Publications(connection).domain('etf', scope)

    @contextmanager
    def writer(self) -> Iterator[None]:
        if not self.initialized:
            raise FlowError('etf_not_initialized')
        try:
            with task_writer(self.root):
                yield
        except CommitUncertain:
            raise
        except StorageError as error:
            codes = {'storage_writer_busy': 'etf_busy', 'storage_journal_changed': 'etf_journal_changed',
                     'storage_publication_changed': 'etf_snapshot_changed'}
            raise FlowError(codes.get(str(error), 'etf_storage_unavailable')) from error

    def _require_writer(self) -> None:
        self.check()
        if not self.database.is_writer:
            raise FlowError('etf_writer_required', 403)

    def inherited_lock(self) -> int:
        self._require_writer()
        return self.database.inherited_lock()

    def spool(self, attempt: str, suffix: str) -> Path:
        """显式取数的未提交响应只留incoming；普通页面不访问此目录。"""
        if not isinstance(attempt, str) or re.fullmatch('[a-f0-9]{32}', attempt) is None or suffix not in {'raw', 'receipt'}:
            raise FlowError('etf_invalid_receipt')
        self.check()
        return location(self.root / 'incoming') / (attempt + '.' + suffix)

    def create_spool(self, attempt: str, suffix: str) -> int:
        self._require_writer()
        path = self.spool(attempt, suffix)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.fsync(descriptor)
            fsync_directory(path.parent)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def read_spool(self, attempt: str, suffix: str, limit: int) -> bytes | None:
        path = self.spool(attempt, suffix)
        if not path.exists():
            return None
        location(path, directory=False)
        if path.stat().st_size > limit:
            raise FlowError('etf_object_too_large')
        content = read_bytes(path, limit + 1)
        if len(content) > limit:
            raise FlowError('etf_object_too_large')
        self.check()
        return content

    def put(self, raw: bytes) -> str:
        """原件按字节指纹只存一份；结构化事实须经put_json逐字段落表。"""
        self._require_writer()
        with self.database.transaction():
            return Originals(self.database).put(raw)

    def put_json(self, value: Any) -> str:
        """ETF价格/净值等独立行，元数据内容图复用未变节点。"""
        self._require_writer()
        with self.database.transaction() as connection:
            docs, facts = Documents(connection), Facts(connection)
            if isinstance(value, dict) and set(value) == {'member_id', 'date', 'fields', 'revision_reason'}:
                identity = facts.input(value)
                for metric, field in value['fields'].items():
                    source = field['source']
                    observed = observation(connection, 'etf', identity, source)
                    projection = connection.execute('SELECT field_document FROM input_field WHERE input_id=? AND metric=?', (identity, metric)).fetchone()[0]
                    provenance(connection, 'metric', projection, {source['object_id']: [observed]}, [source])
                return identity
            if isinstance(value, dict) and set(value) == {'member_id', 'kind', 'start', 'end', 'factor', 'tail', 'source_ids', 'confirmed_at', 'confirmation'}:
                return facts.adjustment(value)
            replacements = {}
            if isinstance(value, dict) and value.get('format') == 'etf-flow-evidence-v1':
                for adjustment in value['adjustments']:
                    replacements[id(adjustment)] = docs.reference(facts.adjustment(adjustment))
                for kind in ('events', 'disclosures'):
                    for event in value[kind]:
                        reference = docs.put(event)
                        connection.execute('INSERT OR IGNORE INTO event VALUES(?,?,?,?,?)',
                            (reference, kind, event['id'], event['source_id'], event.get('published_date')))
            return docs.put(value, transform=lambda item: replacements.get(id(item)))

    def get(self, identifier: str) -> bytes:
        """仅显式证据/写入验证读取原件；结构化旧引用从SQL规范序列化。"""
        with self.database.read() as connection:
            raw = connection.execute('SELECT 1 FROM original_object WHERE id=?', (object_id(identifier),)).fetchone()
        return Originals(self.database).get(identifier) if raw else canonical(self.get_json(identifier))

    def get_json(self, identifier: str) -> Any:
        with self.database.read() as connection:
            if connection.execute('SELECT 1 FROM journal_revision WHERE id=? AND domain_id=?', (object_id(identifier), 'etf')).fetchone():
                return Journals(connection, 'etf').wrapper(identifier)
            return Documents(connection).get(identifier)

    def get_many(self, identifiers: list[str]) -> dict[str, Any]:
        with self.database.read() as connection:
            return Documents(connection).get_many(identifiers)

    def input_window(self, references: list[str], start: str, end: str,
                     members: set[str]) -> tuple[list[str], tuple[str, str] | None]:
        """全版本仅查身份/日期目录；数值对象只解码指定成员和必要日期。"""
        selected, dates = set(), []
        with self.database.read() as connection:
            for offset in range(0, len(references), 800):
                group = references[offset:offset + 800]
                marks = ','.join('?' for _ in group)
                rows = connection.execute(f'SELECT id,instrument_id,trade_date FROM input_assembly WHERE id IN({marks})', group).fetchall()
                if {row[0] for row in rows} != set(group):
                    raise FlowError('etf_invalid_dataset')
                dates.extend(row[2] for row in rows)
                selected.update(ref for ref, member, on in rows if member in members and start <= on <= end)
        # 保留原dataset顺序，完整日历的起止不随窗口或分组变化。
        return [ref for ref in references if ref in selected], (min(dates), max(dates)) if dates else None

    def require_published(self, identity: str) -> None:
        """快速装配只能读取已发布且有成功校验凭据的固定版本。"""
        with self.database.read() as connection:
            row = connection.execute("""SELECT 1 FROM publication p JOIN validation_receipt v ON v.id=p.validation_id
                JOIN document d ON d.id=p.id WHERE p.id=? AND p.domain_id='etf' AND p.subject='etf-flow'
                AND p.legacy_status='published' AND v.result='passed' AND v.input_sha256=d.canonical_sha256""", (object_id(identity),)).fetchone()
            if row is None:
                raise FlowError('etf_publication_unverifiable')

    def current_id(self) -> str | None:
        if not self.initialized:
            return None
        with self.database.read() as connection:
            row = Publications(connection).head('etf', 'etf-flow')
            return row[0] if row else None

    def publish(self, identifier: str, expected: str | None) -> None:
        """验证候选全部来源与准备证明后，同事务提交新版本、成员差量和CAS。"""
        from pmi.market_data.etf_flow.repository import Repository
        self._require_writer()
        with self.database.transaction() as connection:
            repository = Repository(self)
            loaded = repository.load(identifier, verify=True)
            if loaded.manifest['parent'] != expected or self.current_id() != expected:
                raise FlowError('etf_snapshot_changed')
            rows = {}
            for item in loaded.inputs:
                for metric, projection in connection.execute('SELECT metric,field_document FROM input_field WHERE input_id=?', (item.hash,)):
                    rows['metric', item.member_id, item.date, metric] = projection
            dates = sorted({key[2] for key in rows})
            proof = ValidationProof('etf-publish-sql-v1', digest(loaded.manifest), now(),
                                    {'input_version': loaded.calculator.input_version, 'admissions': loaded.manifest['admission_refs']})
            publications = Publications(connection)
            publications.add(identifier, domain='etf', subject='etf-flow', rows=rows, proof=proof, base=expected,
                             coverage_start=dates[0] if dates else None, coverage_end=dates[-1] if dates else None)
            publications.select(identifier, domain='etf', subject='etf-flow', expected=expected)

    def journal(self, key: str) -> tuple[str | None, Any | None]:
        if not self.initialized:
            return None, None
        with self.database.read() as connection:
            return Journals(connection, 'etf').read(key)

    def journal_keys(self) -> list[str]:
        with self.database.read() as connection:
            return Journals(connection, 'etf').keys()

    def write_journal(self, key: str, value: Any, expected: str | None) -> str:
        self._require_writer()
        with self.database.transaction() as connection:
            try:
                return Journals(connection, 'etf').write(key, value, expected)
            except StorageError as error:
                if str(error) == 'storage_journal_changed':
                    raise FlowError('etf_journal_changed') from error
                raise

    def published_operation(self, operation_key: str) -> tuple[str, dict[str, Any]] | None:
        identifier = self.current_id()
        visited: set[str] = set()
        while identifier is not None:
            if identifier in visited:
                raise FlowError('etf_snapshot_cycle')
            visited.add(identifier)
            value = self.get_json(identifier)
            if value.get('operation_key') == object_id(operation_key):
                return identifier, value
            identifier = value['parent']
        return None
