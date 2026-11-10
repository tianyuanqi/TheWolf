"""小型运行状态的SQL指针；历史元数据仍不可变，不使用旁路JSON文件。"""
from __future__ import annotations

import sqlite3
from typing import Any

from .database import StorageError
from .documents import Documents


def read(connection: sqlite3.Connection, domain: str, key: str) -> Any | None:
    row = connection.execute('SELECT revision FROM state WHERE domain_id=? AND key=?', (domain, key)).fetchone()
    return Documents(connection).get(row[0]) if row else None


def write(connection: sqlite3.Connection, domain: str, key: str, value: Any, *, immutable: bool = False) -> str:
    """外层事务保护；内容寻址历史可复用，禁止以immutable标记覆盖不同内容。"""
    docs = Documents(connection)
    reference = docs.put(value)
    prior = connection.execute('SELECT revision FROM state WHERE domain_id=? AND key=?', (domain, key)).fetchone()
    if immutable and prior is not None and prior[0] != reference:
        raise StorageError('storage_immutable_state_conflict')
    connection.execute('''INSERT INTO state VALUES(?,?,?) ON CONFLICT(domain_id,key)
        DO UPDATE SET revision=excluded.revision''', (domain, key, reference))
    return reference
