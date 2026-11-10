"""账本在SQL中追加不可变版本，当前指针与额度明细原子提交。"""
from __future__ import annotations

import sqlite3
from typing import Any

from .database import StorageError, digest, identifier
from .documents import Documents


class Journals:
    """技术父链从迁入点开始，原账本previous另存SQL以保留旧内容身份。"""

    def __init__(self, connection: sqlite3.Connection, domain: str):
        self.connection, self.domain = connection, domain
        self.documents = Documents(connection)

    def read(self, key: str) -> tuple[str | None, Any | None]:
        row = self.connection.execute('''SELECT r.id,r.value_document FROM journal_head h
            JOIN journal_revision r ON r.id=h.revision_id WHERE h.domain_id=? AND h.journal_key=?''',
            (self.domain, identifier(key))).fetchone()
        return (row[0], self.documents.get(row[1])) if row else (None, None)

    def wrapper(self, revision: str) -> dict[str, Any]:
        row = self.connection.execute('SELECT previous,value_document FROM journal_revision WHERE domain_id=? AND id=?',
                                      (self.domain, identifier(revision))).fetchone()
        if row is None:
            raise StorageError('storage_document_not_found')
        legacy = self.connection.execute('SELECT revision FROM state WHERE domain_id=? AND key=?',
                                         (self.domain, 'journal-legacy-previous:' + revision)).fetchone()
        previous = self.documents.get(legacy[0]) if legacy else row[0]
        value = {'previous': previous, 'value': self.documents.get(row[1])}
        if digest(value) != revision:
            raise StorageError('storage_journal_identity_mismatch')
        return value

    def write(self, key: str, value: Any, expected: str | None) -> str:
        """调用者持写事务；CAS失败不改变指针，完整旧版本始终可解析。"""
        key = identifier(key)
        if self.read(key)[0] != expected:
            raise StorageError('storage_journal_changed')
        reference = self.documents.put(value)
        revision = digest({'previous': expected, 'value': value})
        self.connection.execute('INSERT OR IGNORE INTO journal_revision VALUES(?,?,?,?,?)',
                                (revision, self.domain, key, expected, reference))
        actual = self.connection.execute('SELECT domain_id,journal_key,previous,value_document FROM journal_revision WHERE id=?', (revision,)).fetchone()
        if tuple(actual) != (self.domain, key, expected, reference):
            raise StorageError('storage_journal_collision')
        self.connection.execute('''INSERT INTO journal_head VALUES(?,?,?) ON CONFLICT(domain_id,journal_key)
            DO UPDATE SET revision_id=excluded.revision_id''', (self.domain, key, revision))
        self._indexes(key, value)
        return revision

    def _indexes(self, key: str, value: Any) -> None:
        if not isinstance(value, dict):
            return
        if self.domain == 'etf' and value.get('format') == 'etf-flow-budget-v1':
            self.connection.execute('''INSERT INTO budget_scope VALUES(?,?,?,?) ON CONFLICT(domain_id,scope_id)
                DO UPDATE SET grant_id=excluded.grant_id,journal_key=excluded.journal_key''',
                (self.domain, key, value['grant']['id'], key))
            for attempt in value['attempts']:
                reference = self.documents.put(attempt)
                self.connection.execute('''INSERT INTO attempt VALUES(?,?,?,?) ON CONFLICT(domain_id,scope_id,attempt_id)
                    DO UPDATE SET revision=excluded.revision''', (self.domain, key, attempt['id'], reference))
        if self.domain == 'etf' and set(value) == {'operations'}:
            for op in value['operations']:
                reference = self.documents.put(op)
                self.connection.execute('''INSERT INTO operation VALUES(?,?,?,?,?) ON CONFLICT(domain_id,request_id)
                    DO UPDATE SET revision=excluded.revision,state=excluded.state,publication_id=excluded.publication_id''',
                    (self.domain, op['operation_key'], reference, op['state'], op['snapshot_id']))

    def keys(self) -> list[str]:
        return [row[0] for row in self.connection.execute('SELECT journal_key FROM journal_head WHERE domain_id=? ORDER BY journal_key', (self.domain,))]
