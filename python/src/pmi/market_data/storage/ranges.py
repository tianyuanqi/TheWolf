"""固定发布的SQL范围选择；源覆盖、显示范围和计算预热范围分别表达。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import sqlite3

from pmi.market_data.index_calculations import _bounds, PERIODS
from .database import StorageError, identifier
from .documents import Documents
from .publications import Publications


@dataclass(frozen=True)
class RangePlan:
    requested: dict[str, str]
    returned: dict[str, str] | None
    calculation: dict[str, str] | None
    dates: tuple[str, ...]
    visible_periods: tuple[str, ...]


def validate_request(start: str, end: str, frequency: str, periods: tuple[int, ...]) -> None:
    """与库中是否有数据无关的范围语法先验证，错误请求不触碰业务表。"""
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if (first.isoformat() != start or last.isoformat() != end or first > last or (last - first).days >= 1100
                or frequency not in ('daily', 'weekly', 'monthly') or len(set(periods)) != len(periods)
                or any(type(period) is not int or period not in PERIODS for period in periods)):
            raise ValueError()
    except (ValueError, TypeError) as error:
        raise StorageError('range_parameters_invalid') from error


def plan(dates: tuple[str, ...], start: str, end: str, frequency: str, periods: tuple[int, ...]) -> RangePlan:
    """非交易日取交集；周月保留完整已存周期，向前取实际所需预热周期。"""
    validate_request(start, end, frequency, periods)
    if not dates or start < dates[0] or end > dates[-1]:
        raise StorageError('coverage_insufficient')
    groups: list[list[str]] = []
    for day in dates:
        if not groups or _bounds(groups[-1][0], frequency) != _bounds(day, frequency):
            groups.append([])
        groups[-1].append(day)
    visible = [i for i, group in enumerate(groups) if any(start <= day <= end for day in group)]
    requested = {'start': start, 'end': end}
    if not visible:
        return RangePlan(requested, None, None, (), ())
    # 显示区间与周期相交，但整个区间不含任何交易日时明确为空。
    left, right = visible[0], visible[-1]
    warmup = max(1, max(periods, default=1) - 1)
    needed = groups[max(0, left - warmup):right + 1]
    selected = tuple(day for group in needed for day in group)
    return RangePlan(requested, {'start': groups[left][0], 'end': groups[right][-1]},
                     {'start': selected[0], 'end': selected[-1]}, selected,
                     tuple(_bounds(groups[i][0], frequency)[0].isoformat() for i in visible))


class Ranges:
    """调用者持同一只读事务；固定ID必须同时匹配领域、系列及成功发布。"""

    def __init__(self, connection: sqlite3.Connection):
        self.connection, self.documents = connection, Documents(connection)
        self.publications = Publications(connection)

    def header(self, publication: str, domain: str, subject: str) -> dict:
        row = self.connection.execute('''SELECT n.kind,e.child FROM publication p JOIN document d ON d.id=p.id
            JOIN validation_receipt v ON v.id=p.validation_id JOIN node n ON n.id=d.root
            JOIN node_edge e ON e.parent=n.id AND e.position=0
            WHERE p.id=? AND p.domain_id=? AND p.subject=? AND p.legacy_status='published'
              AND v.result='passed' AND v.input_sha256=d.canonical_sha256''', (identifier(publication), domain, subject)).fetchone()
        expected = {'price-v2': 'price_snapshot', 'activity': 'activity_snapshot'}.get(domain)
        if row is None or row[0] != expected:
            raise StorageError('storage_publication_not_found')
        return self.documents.decode(row[1])

    def dates(self, publication: str, kind: str, instrument: str) -> tuple[str, ...]:
        """只读取键日期供日历/预热选择，不装配多年数值或证据。"""
        rows = self.publications.selected_rows(publication, kind=kind, instrument=instrument)
        return tuple(key[2] for key in rows)

    def rows(self, publication: str, kind: str, instrument: str, selection: RangePlan) -> list[dict]:
        if selection.calculation is None:
            return []
        rows = self.publications.selected_rows(publication, kind=kind, instrument=instrument,
            start=selection.calculation['start'], end=selection.calculation['end'])
        values = self.documents.get_many(list(rows.values()))
        result = [values[reference] for reference in rows.values()]
        if tuple(row['trade_date'] for row in result) != selection.dates:
            raise StorageError('storage_range_calendar_mismatch')
        return result

    def activity_presence(self, publication: str, series: str, field: str) -> dict[str, bool]:
        """只查询各日指标的缺失标记供能力说明，不取未请求区间的数值。"""
        from pmi.market_data.activity.model import MARKET_IDS
        if field not in ('amount', 'volume') or series in MARKET_IDS and field != 'amount':
            raise StorageError('range_parameters_invalid')
        rows = self.publications.selected_rows(publication, kind='activity', instrument=series)
        references = list(rows.values())
        found: dict[str, list[tuple[str, bool]]] = {}
        for offset in range(0, len(references), 400):
            group = references[offset:offset + 400]
            marks = ','.join('?' for _ in group)
            roots = dict(self.connection.execute('SELECT id,root FROM document WHERE id IN('+marks+')', group))
            if set(roots) != set(group):
                raise StorageError('storage_document_not_found')
            nodes, edges = self.documents._read_graph(list(roots.values()))
            # 不带document_id重走共享的来源/元数据子树；只物化指标缺失标记。
            metrics = list({atom for kind, atom in nodes.values() if kind == 'metric'})
            presence = {}
            for start in range(0, len(metrics), 800):
                selected = metrics[start:start + 800]
                marks = ','.join('?' for _ in selected)
                presence.update({key: (metric, bool(present)) for key, metric, present in self.connection.execute(
                    'SELECT p.id,p.metric,m.value IS NOT NULL FROM metric_projection p JOIN daily_metric m ON m.id=p.row_id WHERE p.id IN('+marks+')', selected)})
            if set(presence) != set(metrics):
                raise StorageError('storage_range_metric_missing')
            memo, visiting = {}, set()
            def descendants(key: int, depth: int = 0) -> frozenset[str]:
                if key in memo:
                    return memo[key]
                if key in visiting or key not in nodes or depth > 128:
                    raise StorageError('storage_invalid_document_graph')
                visiting.add(key)
                kind, atom = nodes[key]
                result = {atom} if kind == 'metric' else set()
                # 指标节点下的元数据也照常遍历，不能为加速漏掉嵌套引用。
                for _, child in edges.get(key, ()):
                    result.update(descendants(child, depth + 1))
                visiting.remove(key)
                memo[key] = frozenset(result)
                return memo[key]
            for reference, root in roots.items():
                found[reference] = [presence[key] for key in descendants(root)]
        result = {}
        for key, reference in rows.items():
            fields = found.get(reference, [])
            selected = fields if series in MARKET_IDS else [item for item in fields if item[0] == field]
            if not selected:
                raise StorageError('storage_range_metric_missing')
            result[key[2]] = all(item[1] for item in selected)
        return result
