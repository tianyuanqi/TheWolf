"""旧固定ID映射到SQL行版本；快照头不再保存多年数值或成员清单。"""
from __future__ import annotations

import sqlite3
from typing import Any

from .database import StorageError, digest
from .documents import Documents
from .facts import Facts, decimal_text
from .publications import RowKey


class Snapshots:
    """这里只做已验证输入的持久化映射；准入校验与发布提交由用例负责。"""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.documents = Documents(connection)
        self.facts = Facts(connection)

    def price(self, value: dict[str, Any], *, snapshot_id: str | None = None) -> tuple[str, dict[RowKey, str]]:
        """现役v2指数的头与事实分开；源覆盖保留，日历和摘要由固定行恢复。"""
        if value.get('schema_version') != 'index-series-price-snapshot-v2':
            raise StorageError('storage_unknown_price_schema')
        instrument = value['instrument']['id']
        self.facts.instrument(instrument, 'index', exchange=value['instrument'].get('exchange'),
                              code=value['instrument'].get('code'), name=value['instrument'].get('name'))
        rows = {}
        dates = []
        for row in value['bars']:
            day = row['trade_date']
            key = ('price', instrument, day, '')
            if key in rows:
                raise StorageError('storage_duplicate_date')
            rows[key] = self.facts.price(instrument, row, unit=value['unit'], precision=value['storage_decimals'], price_type='index_points')
            dates.append(day)
        if dates != sorted(dates) or dates != value['calendar_dates']:
            raise StorageError('storage_calendar_mismatch')
        sources = []
        for source in value['evidence']:
            for source_row in source['rows']:
                normalized = tuple(decimal_text(source_row[key]) for key in ('open', 'high', 'low', 'close'))
                raw_values = tuple(decimal_text(source_row['raw_values'][key]) for key in ('open', 'high', 'low', 'close'))
                compared = tuple(decimal_text(source_row['comparison_values'][key]) for key in ('open', 'high', 'low', 'close'))
                source_value = digest(['source-price-value', instrument, source_row['trade_date'], normalized, raw_values, compared])
                args = (source_value, instrument, source_row['trade_date'], *normalized, *raw_values, *compared)
                self.connection.execute('INSERT OR IGNORE INTO source_price_value VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', args)
                if tuple(self.connection.execute('SELECT * FROM source_price_value WHERE id=?', (source_value,)).fetchone()) != args:
                    raise StorageError('storage_source_price_conflict')
                args = (source['object_id'], instrument, source_row['trade_date'], source_value, source_row['locator'])
                self.connection.execute('INSERT OR IGNORE INTO source_price_binding VALUES(?,?,?,?,?)', args)
                existing = self.connection.execute('SELECT * FROM source_price_binding WHERE object_id=? AND instrument_id=? AND trade_date=?', args[:3]).fetchone()
                if tuple(existing) != args:
                    raise StorageError('storage_source_price_conflict')
            sources.append({key: item for key, item in source.items() if key != 'rows'})
        identity = snapshot_id or digest(value)
        header = {key: item for key, item in value.items() if key not in ('bars', 'calendar_dates', 'summary', 'evidence')}
        header['evidence'] = sources
        metadata = self.documents.encode(header)
        root = self.documents.node('price_snapshot', identity, ((None, metadata),))
        self.documents.alias(identity, 'index-snapshot', root, digest(value))
        return identity, rows

    def activity(self, value: dict[str, Any], *, snapshot_id: str | None = None) -> tuple[str, dict[RowKey, str]]:
        """量额逐日、分项逐指标存表；两市/三市合计保持原系列身份。"""
        if value.get('schema_version') != 'activity-facts-v1':
            raise StorageError('storage_unknown_activity_schema')
        series = value['series_id']
        self.facts.instrument(series, 'market' if series.startswith('cn-') else 'index')
        rows, dates = {}, []
        for row in value['rows']:
            day = row['trade_date']
            key = ('activity', series, day, '')
            if key in rows:
                raise StorageError('storage_duplicate_date')
            replacements = {}
            if 'components' in row:
                fields = [(market + ':' + str(position), field) for market, parts in row['components'].items()
                          for position, field in enumerate(parts)]
            else:
                fields = [(name, row[name]) for name in ('amount', 'volume')]
            for name, field in fields:
                projection = self.facts.metric(series, day, name, field)
                replacements[id(field)] = self.documents.reference(projection)
            row_id = digest(['activity-row', series, row])
            self.documents.put(row, 'activity-row', document_id=row_id, transform=lambda item: replacements.get(id(item)))
            rows[key] = row_id
            dates.append(day)
        if dates != sorted(dates) or dates != value['calendar_dates']:
            raise StorageError('storage_calendar_mismatch')
        identity = snapshot_id or digest(value)
        header = {key: item for key, item in value.items() if key not in ('rows', 'calendar_dates')}
        metadata = self.documents.encode(header)
        root = self.documents.node('activity_snapshot', identity, ((None, metadata),))
        self.documents.alias(identity, 'activity-snapshot', root, digest(value))
        return identity, rows
