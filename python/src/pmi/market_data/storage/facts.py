"""价格及独立日指标的精确行版本；观察改变不复制未变数值。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
import sqlite3
from typing import Any

from .database import StorageError, canonical, digest
from .documents import Documents

_DECIMAL = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z')
_FIELDS = ('open', 'high', 'low', 'close', 'volume', 'amount')


def decimal_text(value: Any, *, nullable: bool = False) -> str | None:
    """只收有限十进制字符串，不舍入、不转换为REAL；缺失保持NULL。"""
    if value is None and nullable:
        return None
    if type(value) is not str or len(value) > 100 or _DECIMAL.fullmatch(value) is None or not Decimal(value).is_finite():
        raise StorageError('storage_invalid_decimal')
    return value


def trade_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (ValueError, TypeError) as error:
        raise StorageError('storage_invalid_date') from error
    return value


class Facts:
    """所有变更由外层单写者事务保护；每个旧行投影指向独立事实和元数据。"""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.documents = Documents(connection)

    def instrument(self, identity: str, kind: str, *, exchange: str | None = None,
                   code: str | None = None, name: str | None = None) -> None:
        if not isinstance(identity, str) or not identity or kind not in ('index', 'stock', 'etf', 'market'):
            raise StorageError('storage_invalid_instrument')
        self.connection.execute('INSERT OR IGNORE INTO instrument VALUES(?,?,?,?,?)', (identity, kind, exchange, code, name))
        row = self.connection.execute('SELECT kind FROM instrument WHERE id=?', (identity,)).fetchone()
        if row[0] != kind:
            raise StorageError('storage_instrument_conflict')

    def source_price(self, instrument: str, object_id: str, row: dict[str, Any]) -> str:
        """核验来源的原精度与比较口径各列保存，不混入价格事实计数。"""
        fields = ('open', 'high', 'low', 'close')
        day = trade_date(row['trade_date'])
        normalized = tuple(decimal_text(row[key]) for key in fields)
        raw = tuple(decimal_text(row['raw_values'][key]) for key in fields)
        compared = tuple(decimal_text(row.get('comparison_values', row)[key]) for key in fields)
        value_id = digest(['source-price-value', instrument, day, normalized, raw, compared])
        args = (value_id, instrument, day, *normalized, *raw, *compared)
        self.connection.execute('INSERT OR IGNORE INTO source_price_value VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', args)
        if tuple(self.connection.execute('SELECT * FROM source_price_value WHERE id=?', (value_id,)).fetchone()) != args:
            raise StorageError('storage_source_price_conflict')
        args = (object_id, instrument, day, value_id, row['locator'])
        self.connection.execute('INSERT OR IGNORE INTO source_price_binding VALUES(?,?,?,?,?)', args)
        if tuple(self.connection.execute('SELECT * FROM source_price_binding WHERE object_id=? AND instrument_id=? AND trade_date=?', args[:3]).fetchone()) != args:
            raise StorageError('storage_source_price_conflict')
        identity = digest(['source-price-projection', instrument, row])
        metadata = self.documents.encode({key: item for key, item in row.items() if key not in {*fields, 'raw_values', 'comparison_values'}})
        node = self.documents.node('source_price', identity, ((None, metadata),))
        self.documents.alias(identity, 'source-price-row', node, digest(row))
        self.connection.execute('INSERT OR IGNORE INTO source_price_projection VALUES(?,?,?,?)',
                                (identity, value_id, metadata, int('comparison_values' in row)))
        return identity

    def price(self, instrument: str, row: dict[str, Any], *, unit: str, precision: int,
              price_type: str, fields: dict[str, str] | None = None, date_field: str = 'trade_date') -> str:
        """保存OHLC/量额事实；来源定位等元数据独立，合法来源修订不重复数值行。"""
        mapping = fields or {name: name for name in _FIELDS if name in row}
        if (set(mapping) - set(_FIELDS) or not {'open', 'high', 'low', 'close'} <= set(mapping)
                or len(set(mapping.values())) != len(mapping) or not isinstance(unit, str) or not unit
                or type(precision) is not int or not 0 <= precision <= 30):
            raise StorageError('storage_invalid_price_layout')
        day = trade_date(row[date_field])
        values = tuple(decimal_text(row[mapping[key]]) if key in mapping else None for key in _FIELDS)
        opening, high, low, closing = (Decimal(value) for value in values[:4])
        if not 0 < low <= min(opening, closing) <= max(opening, closing) <= high:
            raise StorageError('storage_invalid_ohlc')
        if any(len(value.partition('.')[2]) > precision for value in values[:4]):
            raise StorageError('storage_price_precision_mismatch')
        revision = digest([values, unit, precision, price_type])
        row_id = digest(['price', instrument, day, revision])
        args = (row_id, instrument, day, revision, *values, unit, precision, price_type)
        self.connection.execute('INSERT OR IGNORE INTO price_row VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', args)
        actual = self.connection.execute('SELECT * FROM price_row WHERE id=?', (row_id,)).fetchone()
        if tuple(actual) != args:
            raise StorageError('storage_fact_collision')
        metadata = {key: value for key, value in row.items() if key not in mapping.values()}
        metadata_node = self.documents.encode(metadata)
        projection = digest(['price-projection', instrument, row, unit, precision, price_type])
        node = self.documents.node('price', projection, ((None, metadata_node),))
        self.documents.alias(projection, 'price-row', node, digest(row))
        layout = canonical({output: _FIELDS.index(key) for key, output in mapping.items()}).decode()
        self.connection.execute('INSERT OR IGNORE INTO price_projection VALUES(?,?,?,?,?,?)',
                                (projection, instrument, day, row_id, metadata_node, layout))
        return projection

    def metric(self, instrument: str, day: str, metric: str, field: dict[str, Any], *,
               unit: str | None = None, missing_reason: str | None = None) -> str:
        """一项指标一个事实版本；缺项不填零，来源与其独立投影保持绑定。"""
        trade_date(day)
        value = decimal_text(field.get('value'), nullable=True)
        unit = field.get('unit') if unit is None else unit
        reason = (field.get('reason') or missing_reason) if value is None else None
        if not isinstance(unit, str) or not unit or (value is None and (not isinstance(reason, str) or not reason)):
            raise StorageError('storage_invalid_metric')
        revision = digest([value, unit, reason])
        row_id = digest(['metric', instrument, day, metric, revision])
        args = (row_id, instrument, day, metric, revision, value, unit, reason)
        self.connection.execute('INSERT OR IGNORE INTO daily_metric VALUES(?,?,?,?,?,?,?,?)', args)
        if tuple(self.connection.execute('SELECT * FROM daily_metric WHERE id=?', (row_id,)).fetchone()) != args:
            raise StorageError('storage_fact_collision')
        metadata = self.documents.encode({key: item for key, item in field.items() if key != 'value'})
        projection = digest(['metric-projection', instrument, day, metric, field])
        node = self.documents.node('metric', projection, ((None, metadata),))
        self.documents.alias(projection, 'metric-field', node, digest(field))
        self.connection.execute('INSERT OR IGNORE INTO metric_projection VALUES(?,?,?,?,?,?)',
                                (projection, instrument, day, metric, row_id, metadata))
        return projection

    def input(self, value: dict[str, Any]) -> str:
        """ETF旧输入组合只引用指标及其来源投影，保留原Input内容ID。"""
        from pmi.market_data.etf_flow.model import Input
        parsed = Input.parse(value)
        self.instrument(parsed.member_id, 'etf')
        replacements = {}
        field_refs = {}
        for name, field in value['fields'].items():
            reference = self.metric(parsed.member_id, parsed.date, name, field)
            field_refs[name] = reference
            replacements[id(field)] = self.documents.reference(reference)
        identifier = self.documents.put(value, 'etf-input', transform=lambda item: replacements.get(id(item)))
        self.connection.execute('INSERT OR IGNORE INTO input_assembly VALUES(?,?,?,?)',
                                (identifier, parsed.member_id, parsed.date, value['revision_reason']))
        self.connection.executemany('INSERT OR IGNORE INTO input_field VALUES(?,?,?)',
                                    [(identifier, name, reference) for name, reference in field_refs.items()])
        return identifier

    def adjustment(self, value: dict[str, Any]) -> str:
        """调整因子是独立事实，原始价格及日指标不随复权重写。"""
        from pmi.market_data.etf_flow.model import Adjustment
        parsed = Adjustment.parse(value)
        self.instrument(parsed.member_id, 'etf')
        factor, tail = decimal_text(value['factor']), decimal_text(value['tail'])
        identity = digest(value)
        metadata = self.documents.encode({key: item for key, item in value.items() if key not in ('factor', 'tail')})
        node = self.documents.node('adjustment', identity, ((None, metadata),))
        self.documents.alias(identity, 'adjustment', node, identity)
        args = (identity, parsed.member_id, parsed.kind, parsed.start, parsed.end, factor, tail, parsed.confirmed_at, metadata)
        self.connection.execute('INSERT OR IGNORE INTO adjustment VALUES(?,?,?,?,?,?,?,?,?)', args)
        if tuple(self.connection.execute('SELECT * FROM adjustment WHERE id=?', (identity,)).fetchone()) != args:
            raise StorageError('storage_adjustment_conflict')
        return identity
