"""每次获取与事实行的证据关系，保留未知发布时间，不补造金融时间。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from .database import StorageError, digest
from .documents import Documents


def observation(connection: sqlite3.Connection, domain: str, receipt: str, source: dict[str, Any]) -> str:
    """获取来源必须有身份和带时区的获取时间；字段原样保存在元数据中。"""
    retrieved = source.get('completed_at') or source.get('retrieved_at')
    publisher = source.get('source') or source.get('publisher')
    if not publisher or not retrieved:
        raise StorageError('storage_observation_incomplete')
    try:
        end = datetime.fromisoformat(retrieved)
        if end.utcoffset() is None:
            raise ValueError()
        if source.get('started_at'):
            start = datetime.fromisoformat(source['started_at'])
            if start.utcoffset() is None or start > end:
                raise ValueError()
        if source.get('published_at') and datetime.fromisoformat(source['published_at']).utcoffset() is None:
            raise ValueError()
    except (TypeError, ValueError) as error:
        raise StorageError('storage_observation_time_invalid') from error
    identity = digest([domain, receipt, source])
    metadata = Documents(connection).put(source)
    args = (identity, domain, publisher, source['object_id'], source.get('published_at'),
            source.get('started_at'), retrieved, source.get('locator'), metadata)
    connection.execute('INSERT OR IGNORE INTO source_observation VALUES(?,?,?,?,?,?,?,?,?)', args)
    if tuple(connection.execute('SELECT * FROM source_observation WHERE id=?', (identity,)).fetchone()) != args:
        raise StorageError('storage_observation_collision')
    return identity


def provenance(connection: sqlite3.Connection, kind: str, projection: str,
               observations: dict[str, list[str]], refs: list[dict[str, Any]]) -> None:
    """逐事实关联其实际来源；缺失观察不允许静默丢弃证据。"""
    if kind not in ('price', 'metric'):
        raise StorageError('storage_invalid_provenance_kind')
    table = 'price_projection' if kind == 'price' else 'metric_projection'
    row = connection.execute('SELECT row_id FROM ' + table + ' WHERE id=?', (projection,)).fetchone()
    if row is None:
        raise StorageError('storage_missing_projection')
    for ref in refs:
        found = observations.get(ref['object_id'])
        if not found:
            raise StorageError('storage_missing_observation')
        for observed in found:
            connection.execute('INSERT OR IGNORE INTO row_provenance VALUES(?,?,?,?)',
                               (kind, row[0], observed, ref.get('locator') or 'source-document'))
