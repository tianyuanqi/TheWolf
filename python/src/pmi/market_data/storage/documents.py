"""元数据的内容寻址关系图；行情值引用事实表，不保存数值JSON快照。"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any, Callable

from .database import StorageError, digest, identifier


@dataclass(frozen=True)
class Reference:
    """仅受信适配器可生成的已保存节点引用，不接受外部JSON伪造。"""
    node_id: int


class Documents:
    """调用者提供同一读/写事务；不可变图按节点复用，数组分块复用。"""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _node_hash(self, node_id: int) -> str:
        if type(node_id) is not int or node_id <= 0:
            raise StorageError('storage_invalid_node_reference')
        # 不跨保存点缓存内部rowid；回滚后SQLite可能将同一整数分配给另一节点。
        row = self.connection.execute('SELECT fingerprint FROM node WHERE id=?', (node_id,)).fetchone()
        if row is None:
            raise StorageError('storage_missing_node')
        return row[0]

    def node(self, kind: str, atom: str | None = None,
             children: tuple[tuple[str | None, int], ...] = ()) -> int:
        # 内部引用用整数缩小索引；内容身份仍由孩子指纹计算，与插入顺序无关。
        fingerprint = digest([kind, atom, tuple((key, self._node_hash(child)) for key, child in children)])
        cursor = self.connection.execute('INSERT OR IGNORE INTO node(fingerprint,kind,atom) VALUES(?,?,?)', (fingerprint, kind, atom))
        row = self.connection.execute('SELECT id,kind,atom FROM node WHERE fingerprint=?', (fingerprint,)).fetchone()
        value = row[0]
        if tuple(row[1:]) != (kind, atom):
            raise StorageError('storage_node_collision')
        if cursor.rowcount:
            self.connection.executemany('INSERT INTO node_edge VALUES(?,?,?,?)',
                                        [(value, i, key, child) for i, (key, child) in enumerate(children)])
        return value

    def encode(self, value: Any, transform: Callable[[Any], Reference | None] | None = None, depth: int = 0) -> int:
        """数值事实由适配器替换为专用行引用；元数据不接受二进制浮点。"""
        if depth > 128:
            raise StorageError('storage_document_too_deep')
        replacement = transform(value) if transform else None
        if replacement is not None:
            self._node_hash(replacement.node_id)
            return replacement.node_id
        if value is None:
            return self.node('null')
        if type(value) is bool:
            return self.node('bool', '1' if value else '0')
        if type(value) is int:
            return self.node('int', str(value))
        if type(value) is str:
            return self.node('str', value)
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise StorageError('storage_invalid_document')
            return self.node('dict', children=tuple((key, self.encode(value[key], transform, depth + 1)) for key in sorted(value)))
        if type(value) in (list, tuple):
            chunks = []
            for start in range(0, len(value), 64):
                children = tuple((None, self.encode(item, transform, depth + 1)) for item in value[start:start + 64])
                chunks.append((None, self.node('chunk', children=children)))
            return self.node('list', str(len(value)), tuple(chunks))
        raise StorageError('storage_invalid_document_type')

    def alias(self, document_id: str, kind: str, root: int, canonical_sha: str) -> str:
        """保留旧固定ID，规范内容摘要另外记录；同ID不同内容绝不覆盖。"""
        identifier(document_id)
        self.connection.execute('INSERT OR IGNORE INTO document VALUES(?,?,?,?)', (document_id, kind, root, canonical_sha))
        actual = self.connection.execute('SELECT kind,root,canonical_sha256 FROM document WHERE id=?', (document_id,)).fetchone()
        if tuple(actual) != (kind, root, canonical_sha):
            raise StorageError('storage_document_collision')
        return document_id

    def put(self, value: Any, kind: str = 'metadata', *, document_id: str | None = None,
            transform: Callable[[Any], Reference | None] | None = None) -> str:
        content_hash = digest(value)
        root = self.encode(value, transform)
        return self.alias(document_id or content_hash, kind, root, content_hash)

    def reference(self, document_id: str) -> Reference:
        row = self.connection.execute('SELECT root FROM document WHERE id=?', (identifier(document_id),)).fetchone()
        if row is None:
            raise StorageError('storage_document_not_found')
        return Reference(row[0])

    def get(self, document_id: str) -> Any:
        return self.decode(self.reference(document_id).node_id)

    def get_many(self, document_ids: list[str]) -> dict[str, Any]:
        """批量解码已固定对象；只做SQL行装配，不从旧文件重放。"""
        result = {}
        # 递归CTE的VALUES分支受SQLite compound-select上限约束；低于默认500。
        for offset in range(0, len(document_ids), 400):
            group = document_ids[offset:offset + 400]
            for item in group:
                identifier(item)
            marks = ','.join('?' for _ in group)
            roots = dict(self.connection.execute(f'SELECT id,root FROM document WHERE id IN({marks})', group))
            if set(roots) != set(group):
                raise StorageError('storage_document_not_found')
            decoded = self._decode_roots(list(roots.values()))
            result.update({key: decoded[node] for key, node in roots.items()})
        return result

    def decode(self, root: int) -> Any:
        return self._decode_roots([root])[root]

    def _read_graph(self, roots: list[int]) -> tuple[dict, dict]:
        """共享子图只遍历一次，同次查询取得节点及有序边；不装配事实数值。"""
        values = ','.join('(?)' for _ in roots)
        query = '''WITH RECURSIVE reach(id) AS (VALUES''' + values + ''' UNION SELECT e.child FROM node_edge e JOIN reach r ON e.parent=r.id)
                   SELECT n.id,n.kind,n.atom,e.position,e.name,e.child FROM reach r
                   CROSS JOIN node n ON n.id=r.id LEFT JOIN node_edge e ON e.parent=n.id
                   ORDER BY n.id,e.position'''
        nodes, edges = {}, {}
        for key, kind, atom, position, name, child in self.connection.execute(query, roots):
            nodes[key] = (kind, atom)
            if position is not None:
                edges.setdefault(key, []).append((name, child))
        if not set(roots) <= nodes.keys() or len(nodes) > 1_000_000:
            raise StorageError('storage_invalid_document')
        return nodes, edges

    def _decode_roots(self, roots: list[int]) -> dict[int, Any]:
        """一次取出可达元数据；事实引用批量查询，避免逐文件或逐节点I/O。"""
        nodes, edges = self._read_graph(roots)
        prices, metrics = {}, {}
        for kind, table, target in [('price', 'price_projection', prices), ('metric', 'metric_projection', metrics)]:
            refs = [atom for node_kind, atom in nodes.values() if node_kind == kind]
            for offset in range(0, len(refs), 800):
                group = refs[offset:offset + 800]
                marks = ','.join('?' for _ in group)
                if kind == 'price':
                    sql = f'''SELECT p.id,p.field_layout,r.opening,r.high,r.low,r.closing,r.volume,r.amount
                              FROM {table} p JOIN price_row r ON p.row_id=r.id WHERE p.id IN({marks})'''
                else:
                    sql = f'''SELECT p.id,r.value FROM {table} p JOIN daily_metric r ON p.row_id=r.id WHERE p.id IN({marks})'''
                target.update({row[0]: tuple(row[1:]) for row in self.connection.execute(sql, group)})
        adjustments = {}
        refs = [atom for node_kind, atom in nodes.values() if node_kind == 'adjustment']
        for offset in range(0, len(refs), 800):
            group = refs[offset:offset + 800]
            marks = ','.join('?' for _ in group)
            adjustments.update({row[0]: tuple(row[1:]) for row in self.connection.execute(
                f'SELECT id,factor,tail FROM adjustment WHERE id IN({marks})', group)})
        source_prices = {}
        refs = [atom for node_kind, atom in nodes.values() if node_kind == 'source_price']
        for offset in range(0, len(refs), 800):
            group = refs[offset:offset + 800]
            marks = ','.join('?' for _ in group)
            source_prices.update({row[0]: tuple(row[1:]) for row in self.connection.execute(
                f'''SELECT p.id,p.comparison,v.opening,v.high,v.low,v.closing,
                    v.raw_open,v.raw_high,v.raw_low,v.raw_close,
                    v.comparison_open,v.comparison_high,v.comparison_low,v.comparison_close
                    FROM source_price_projection p JOIN source_price_value v ON p.value_id=v.id WHERE p.id IN({marks})''', group)})
        cache: dict[int, Any] = {}
        visiting: set[int] = set()

        def unpack(key: int, depth: int = 0) -> Any:
            if key in cache:
                return cache[key]
            if key in visiting or depth > 128 or key not in nodes:
                raise StorageError('storage_invalid_document_graph')
            visiting.add(key)
            kind, atom = nodes[key]
            children = edges.get(key, [])
            if kind == 'null':
                value = None
            elif kind == 'bool':
                if atom not in ('0', '1'):
                    raise StorageError('storage_invalid_scalar')
                value = atom == '1'
            elif kind == 'int':
                value = int(atom)
            elif kind == 'str':
                value = atom
            elif kind == 'dict':
                value = {name: unpack(child, depth + 1) for name, child in children}
            elif kind in ('list', 'chunk'):
                parts = [unpack(child, depth + 1) for _, child in children]
                value = [item for chunk in parts for item in chunk] if kind == 'list' else parts
                if kind == 'list' and len(value) != int(atom):
                    raise StorageError('storage_invalid_list')
            elif kind in ('price', 'metric', 'adjustment', 'source_price'):
                if len(children) != 1:
                    raise StorageError('storage_invalid_fact_reference')
                value = dict(unpack(children[0][1], depth + 1))
                if kind == 'price':
                    if atom not in prices:
                        raise StorageError('storage_missing_fact')
                    layout, *fields = prices[atom]
                    for output_key, position in json.loads(layout).items():
                        value[output_key] = fields[position]
                elif kind == 'metric':
                    if atom not in metrics:
                        raise StorageError('storage_missing_fact')
                    value['value'] = metrics[atom][0]
                elif kind == 'adjustment':
                    if atom not in adjustments:
                        raise StorageError('storage_missing_adjustment')
                    value['factor'], value['tail'] = adjustments[atom]
                else:
                    if atom not in source_prices:
                        raise StorageError('storage_missing_source_price')
                    compared, *numbers = source_prices[atom]
                    names = ('open', 'high', 'low', 'close')
                    value.update(zip(names, numbers[:4]))
                    value['raw_values'] = dict(zip(names, numbers[4:8]))
                    if compared:
                        value['comparison_values'] = dict(zip(names, numbers[8:12]))
            elif kind in ('price_snapshot', 'activity_snapshot'):
                if len(children) != 1:
                    raise StorageError('storage_invalid_snapshot_reference')
                from .publications import Publications
                value = dict(unpack(children[0][1], depth + 1))
                row_kind = 'price' if kind == 'price_snapshot' else 'activity'
                selected = Publications(self.connection).rows(atom, kind=row_kind)
                references = [selected[key] for key in sorted(selected, key=lambda item: (item[2], item[1], item[3]))]
                items = self.get_many(references)
                rows = [items[reference] for reference in references]
                value['bars' if kind == 'price_snapshot' else 'rows'] = rows
                value['calendar_dates'] = [row['trade_date'] for row in rows]
                if kind == 'price_snapshot':
                    from pmi.market_data.index_series_contract import summarize
                    value['summary'] = summarize(rows)
                    sources = []
                    for source in value['evidence']:
                        evidence_rows = []
                        query = """SELECT b.trade_date,b.locator,v.opening,v.high,v.low,v.closing,
                                   v.raw_open,v.raw_high,v.raw_low,v.raw_close,
                                   v.comparison_open,v.comparison_high,v.comparison_low,v.comparison_close
                                   FROM source_price_binding b JOIN source_price_value v ON b.value_id=v.id
                                   WHERE b.object_id=? AND b.instrument_id=? AND b.trade_date BETWEEN ? AND ?
                                   ORDER BY b.trade_date"""
                        for item in self.connection.execute(query, (source['object_id'], value['instrument']['id'],
                                                                    value['window']['start'], value['window']['end'])):
                            fields = ('open', 'high', 'low', 'close')
                            evidence_rows.append({'trade_date': item[0], 'locator': item[1], **dict(zip(fields, item[2:6])),
                                                  'raw_values': dict(zip(fields, item[6:10])),
                                                  'comparison_values': dict(zip(fields, item[10:14]))})
                        sources.append({**source, 'rows': evidence_rows})
                    value['evidence'] = sources
            else:
                raise StorageError('storage_invalid_node_kind')
            visiting.remove(key)
            cache[key] = value
            return value

        def detached(value: Any) -> Any:
            # SQL节点去重不等于应用对象别名。尤其空days/months/attempts
            # 可能共用节点；修改其中一个不得污染另一个（deepcopy会保留别名）。
            if isinstance(value, dict):
                return {key: detached(item) for key, item in value.items()}
            if isinstance(value, list):
                return [detached(item) for item in value]
            return value

        return {root: detached(unpack(root)) for root in roots}
