"""统一库的轻量版本与范围用例；调用者负责配置准入及完整性健康门禁。"""
from __future__ import annotations

from calendar import monthrange
from datetime import date

from pmi.market_data.index_catalog import INDICES
from pmi.market_data.index_series_contract import summarize
from pmi.market_data.activity.model import MARKET, MARKET_IDS, TWO_MARKET
from pmi.market_data import range_calculations
from .database import Database, StorageError, identifier
from .documents import Documents
from .publications import Publications
from .ranges import Ranges, plan


def one_year(day: str) -> str:
    current = date.fromisoformat(day)
    return current.replace(year=current.year - 1, day=min(current.day, monthrange(current.year - 1, current.month)[1])).isoformat()


def selected_sources(rows: list[dict], sources: list[dict]) -> list[dict]:
    """仅返回本次计算输入实际引用的来源说明；原件仍须显式证据请求。"""
    references = set()
    def visit(value):
        if isinstance(value, dict):
            if value.get('object_id'):
                references.add(value['object_id'])
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(rows)
    return [source for source in sources if source['object_id'] in references]


def activity_context(header: dict) -> dict:
    binding = header['binding']
    return {'source_scope': header['source_scope'], 'source_revision_relation': header['source_revision_relation'],
            'binding': {key: value for key, value in binding.items() if key != 'rows'} if binding else None}


class Views:
    def __init__(self, database: Database):
        self.database = database

    def _descriptor(self, connection, domain: str, subject: str, binding: str = '') -> dict | None:
        row = connection.execute('''SELECT c.publication_id,c.observation_id,p.coverage_start,p.coverage_end
            FROM current_publication c JOIN publication p ON p.id=c.publication_id
            WHERE c.domain_id=? AND c.subject=? AND c.binding=? AND p.legacy_status='published' ''', (domain, subject, binding)).fetchone()
        if row is None:
            return None
        if row[1] is not None and connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?',
                                                   (row[0], row[1])).fetchone() is None:
            raise StorageError('storage_observation_not_member')
        first = connection.execute('SELECT observation_id FROM publication_observation WHERE publication_id=? AND first_observation=1', (row[0],)).fetchone()
        return {'publication_id': row[0], 'observation_id': row[1], 'first_observation_id': first[0] if first else None,
                'source_coverage': {'start': row[2], 'end': row[3]}, 'binding': binding}

    def versions(self, before: str, *, activity: bool, etf: bool, blocked: tuple[str, ...] = ()) -> dict:
        """单事务读取当前ID及绑定；不装配日线、原件、计划、额度或计算。"""
        if date.fromisoformat(before).isoformat() != before:
            raise StorageError('range_parameters_invalid')
        with self.database.read() as connection:
            identity = connection.execute('SELECT store_id FROM store_identity WHERE singleton=1').fetchone()[0]
            indices = []
            for index in INDICES:
                price = self._descriptor(connection, 'price-v2', index.index_id)
                quantity = (self._descriptor(connection, 'activity', index.index_id, price['publication_id'])
                            if activity and price and index.index_id not in blocked else None)
                indices.append({'index_id': index.index_id, 'price': price, 'activity': quantity})
            markets = []
            if activity:
                for series in sorted(MARKET_IDS):
                    if series in blocked:
                        markets.append({'series_id': series, 'activity': None})
                        continue
                    if series == MARKET:
                        row = connection.execute('''SELECT c.binding FROM current_publication c JOIN publication p ON p.id=c.publication_id
                            WHERE c.domain_id='activity' AND c.subject=? ORDER BY p.sequence DESC LIMIT 1''', (series,)).fetchone()
                        anchor = row[0] if row and row[0] <= before else None
                    else:
                        anchor = connection.execute("SELECT max(binding) FROM current_publication WHERE domain_id='activity' AND subject=? AND binding<=?", (series, before)).fetchone()[0]
                    markets.append({'series_id': series, 'activity': self._descriptor(connection, 'activity', series, anchor) if anchor else None})
            return {'store_id': identity, 'indices': indices, 'markets': markets,
                    'etf': self._descriptor(connection, 'etf', 'etf-flow') if etf else None}

    def _observation(self, connection, publication: str, observed: str) -> dict:
        if connection.execute('SELECT 1 FROM publication_observation WHERE publication_id=? AND observation_id=?',
                              (identifier(publication), identifier(observed))).fetchone() is None:
            raise StorageError('storage_observation_not_member')
        receipt = Documents(connection).get(observed)
        if receipt.get('snapshot_id', receipt.get('activity_id')) != publication:
            raise StorageError('storage_observation_not_member')
        return receipt

    def price_range(self, index: str, publication: str, observed: str, start: str, end: str,
                    frequency: str, periods: tuple[int, ...], version: str) -> dict:
        with self.database.read() as connection:
            reader = Ranges(connection)
            header = reader.header(publication, 'price-v2', index)
            receipt = self._observation(connection, publication, observed)
            dates = reader.dates(publication, 'price', index)
            selection = plan(dates, start, end, frequency, periods)
            bars = reader.rows(publication, 'price', index, selection)
            snapshot = {**header, 'snapshot_id': publication, 'bars': bars}
            series = range_calculations.price_series(snapshot, dates, selection.visible_periods, frequency, periods, version)
            return {'index_id': index, 'snapshot_id': publication, 'observation_id': observed,
                'source_coverage': {'start': dates[0], 'end': dates[-1]}, 'requested_range': selection.requested,
                'returned_range': selection.returned, 'calculation_input_range': selection.calculation,
                'frequency': frequency, 'ma_periods': sorted(periods), 'formula_version': version,
                'calendar_version': header['calendar_version'], 'anchor_date': header['window']['anchor_date'],
                'pit_grade': 'latest_only', 'unit': header['unit'], 'storage_decimals': header['storage_decimals'],
                'series': series, 'sources': receipt['sources'], 'verification': header['verification'],
                'navigation_periods': [{'start': group[0], 'end': group[-1]} for group in range_calculations.groups(dates, frequency)]}

    def price_overview(self, index: str, publication: str, observed: str, version: str) -> dict:
        """一年走势加基准边界，现算原5/20/60日/一年比较；不返回三年输入。"""
        with self.database.read() as connection:
            reader = Ranges(connection)
            header = reader.header(publication, 'price-v2', index)
            receipt = self._observation(connection, publication, observed)
            dates = reader.dates(publication, 'price', index)
            start = max(dates[0], one_year(dates[-1]))
            selection = plan(dates, start, dates[-1], 'daily', ())
            bars = reader.rows(publication, 'price', index, selection)
            snapshot = {**header, 'snapshot_id': publication, 'bars': bars}
            calculation = range_calculations.price_overview(snapshot, dates, version)
            return {'index_id': index, 'snapshot_id': publication, 'observation_id': observed,
                'instrument': header['instrument'], 'source_policy_version': header['source_policy_version'],
                'source_coverage': {'start': dates[0], 'end': dates[-1]}, 'requested_range': selection.requested,
                'returned_range': selection.calculation, 'calculation_input_range': selection.calculation,
                'calendar_version': header['calendar_version'], 'anchor_date': header['window']['anchor_date'],
                'pit_grade': 'latest_only', 'unit': header['unit'], 'storage_decimals': header['storage_decimals'],
                'summary': summarize(bars), 'bars': [{key: bar[key] for key in ('trade_date', 'open', 'high', 'low', 'close')} for bar in bars],
                'performance': calculation['performance'], 'formula_version': version,
                'sources': receipt['sources'], 'observed_at': receipt['observed_at'], 'verification': header['verification']}

    def activity_range(self, series: str, publication: str, observed: str, binding: str, start: str, end: str,
                       field: str, frequency: str, periods: tuple[int, ...], version: str) -> dict:
        with self.database.read() as connection:
            reader = Ranges(connection)
            header = reader.header(publication, 'activity', series)
            if (header['price_snapshot_id'] or header['anchor_date']) != binding:
                raise StorageError('storage_activity_binding_invalid')
            receipt = self._observation(connection, publication, observed)
            dates = reader.dates(publication, 'activity', series)
            selection = plan(dates, start, end, frequency, periods)
            rows = reader.rows(publication, 'activity', series, selection)
            snapshot = {**header, 'activity_id': publication, 'rows': rows}
            presence = reader.activity_presence(publication, series, field)
            result = range_calculations.activity_series(snapshot, dates, presence, selection.visible_periods,
                                                       field, frequency, periods, version)
            return {'series_id': series, 'activity_id': publication, 'observation_id': observed,
                'price_snapshot_id': header['price_snapshot_id'], 'anchor_date': header['anchor_date'],
                'source_coverage': {'start': dates[0], 'end': dates[-1]}, 'requested_range': selection.requested,
                'returned_range': selection.returned, 'calculation_input_range': selection.calculation,
                'field': field, 'frequency': frequency, 'ma_periods': sorted(periods), 'formula_version': version,
                'calendar_version': header['calendar_version'], 'pit_grade': 'latest_only',
                'navigation_periods': [{'start': group[0], 'end': group[-1]} for group in range_calculations.groups(dates, frequency)],
                'series': result, 'sources': selected_sources(rows, receipt['sources']), 'source_policy_version': header['source_policy_version'], **activity_context(header)}

    def market_overview(self, series: str, publication: str, observed: str, anchor: str, version: str) -> dict:
        from pmi.market_data.activity.calculations import formula_for
        if series not in MARKET_IDS or version != formula_for(series):
            raise StorageError('range_parameters_invalid')
        with self.database.read() as connection:
            reader = Ranges(connection)
            header = reader.header(publication, 'activity', series)
            if header['price_snapshot_id'] is not None or header['anchor_date'] != anchor:
                raise StorageError('storage_activity_binding_invalid')
            receipt = self._observation(connection, publication, observed)
            dates = reader.dates(publication, 'activity', series)
            selection = plan(dates, max(dates[0], one_year(dates[-1])), dates[-1], 'daily', ())
            rows = reader.rows(publication, 'activity', series, selection)
            snapshot = {**header, 'activity_id': publication, 'rows': rows}
            presence = reader.activity_presence(publication, series, 'amount')
            trend = range_calculations.activity_series(snapshot, dates, presence, selection.visible_periods,
                                                       'amount', 'daily', (), version)
            return {'series_id': series, 'activity_id': publication, 'observation_id': observed,
                'price_snapshot_id': None, 'anchor_date': anchor, 'formula_version': version, 'pit_grade': 'latest_only',
                'source_coverage': {'start': dates[0], 'end': dates[-1]}, 'calculation_input_range': selection.calculation,
                'requested_range': selection.requested, 'returned_range': selection.returned,
                'calendar_version': header['calendar_version'], 'source_policy_version': header['source_policy_version'],
                'navigation_periods': [{'start': day, 'end': day} for day in dates],
                'sources': selected_sources(rows, receipt['sources']), 'series': trend, 'comparisons': range_calculations.market_comparison(snapshot), **activity_context(header)}
