"""数据层计算投影的局部定义表；不舍入金融结果，不共享跨请求证据。"""
from __future__ import annotations

import json
import hashlib
from collections import OrderedDict
from threading import Lock
from collections.abc import Callable
from typing import TypedDict


class Definition(TypedDict):
    unit: str
    formula_version: str
    parameters: dict[str, str]


class Encoder:
    """只提取完全相同的元数据；原身份不符时拒绝，不覆盖错误引用。"""

    def __init__(self, identity: dict[str, str | None], maximum: int):
        self.identity, self.maximum = identity, maximum
        self.definitions: list[Definition] = []
        self.indices: dict[str, int] = {}

    def reference(self, reference: dict) -> None:
        if set(reference) != {*self.identity, 'start', 'end'} or any(
                reference[key] != value for key, value in self.identity.items()):
            raise ValueError('compact_input_mismatch')

    def scalar(self, scalar: dict, *, activity: bool = False) -> dict:
        keys = {'value', 'reason', 'unit', 'formula_version', 'parameters', 'input_ref'}
        if activity:
            keys |= {'complete', 'incomplete_reasons'}
        if set(scalar) != keys:
            raise ValueError('compact_scalar_mismatch')
        self.reference(scalar['input_ref'])
        definition = {key: scalar[key] for key in ('unit', 'formula_version', 'parameters')}
        key = json.dumps(definition, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        if key not in self.indices:
            if len(self.definitions) >= self.maximum:
                raise ValueError('compact_definitions_overflow')
            self.indices[key] = len(self.definitions)
            self.definitions.append(definition)
        result = {name: scalar[name] for name in ('value', 'reason')}
        result.update({name: scalar['input_ref'][name] for name in ('start', 'end')})
        result['definition'] = self.indices[key]
        if activity:
            result.update({name: scalar[name] for name in ('complete', 'incomplete_reasons')})
        return result


def compact_index(value: dict, *, overview: bool = False) -> dict:
    """保留原计算树，去掉逐单元身份重复；数值、日期、顺序和null不变。"""
    encoder = Encoder({key: value[key] for key in ('index_id', 'snapshot_id')}, 32)
    result = dict(value)
    for frequency in (() if overview else ('daily', 'weekly', 'monthly')):
        rows = []
        for bar in value[frequency]['rows']:
            encoder.reference(bar['input_ref'])
            if any(bar['input_ref'][key] != bar[key] for key in ('start', 'end')):
                raise ValueError('compact_bar_mismatch')
            row = {key: item for key, item in bar.items() if key != 'input_ref'}
            row['change_pct'] = encoder.scalar(bar['change_pct'])
            row['ma'] = [encoder.scalar(item) for item in bar['ma']]
            rows.append(row)
        result[frequency] = {**value[frequency], 'rows': rows}
    result['performance'] = {key: encoder.scalar(item) for key, item in value['performance'].items()}
    return {**result, 'definitions': encoder.definitions}


def compact_activity(value: dict) -> dict:
    """量额结果无损投影；完整性、缺口及两/三市公式版本保持原值。"""
    encoder = Encoder({key: value[key] for key in ('series_id', 'activity_id', 'price_snapshot_id')}, 64)
    series = []
    for item in value['series']:
        rows = [{**row, 'total': encoder.scalar(row['total'], activity=True),
                 'change_pct': encoder.scalar(row['change_pct'], activity=True),
                 'ma': [encoder.scalar(cell, activity=True) for cell in row['ma']]} for row in item['rows']]
        series.append({**item, 'rows': rows})
    comparisons = value['comparisons']
    if comparisons is not None:
        comparisons = {key: {**item, 'baseline': encoder.scalar(item['baseline'], activity=True),
                             'comparison': encoder.scalar(item['comparison'], activity=True)}
                       for key, item in comparisons.items()}
    return {**value, 'series': series, 'comparisons': comparisons, 'definitions': encoder.definitions}


_CACHE: OrderedDict[tuple[str, str, str, str], bytes] = OrderedDict()
_CACHE_LOCK = Lock()
_CACHE_LIMIT = 32 * 1048576
_cache_bytes = 0


def _calculated(kind: str, snapshot: dict, version: str, compute: Callable[[], dict]) -> dict:
    """仅缓存纯计算的不可变JSON，入口每次先完成原件/回执重放和权限校验。

    固定ID、公式版本、参数(kind)之外再绑定完整已验证输入摘要；根变化、撤回、
    损坏不能靠命中缓存绕过读取。上限12项/32MiB，超大结果只计算不留存；无持久化。
    返回新对象，调用者修改不能污染其他请求。
    """
    global _cache_bytes
    payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    fixed_id = snapshot.get('activity_id', snapshot.get('snapshot_id'))
    key = (kind, fixed_id, version, hashlib.sha256(payload).hexdigest())
    with _CACHE_LOCK:
        encoded = _CACHE.get(key)
        if encoded is not None:
            _CACHE.move_to_end(key)
    if encoded is None:
        encoded = json.dumps(compute(), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        if len(encoded) <= _CACHE_LIMIT:
            with _CACHE_LOCK:
                previous = _CACHE.pop(key, None)
                _cache_bytes -= len(previous) if previous is not None else 0
                _CACHE[key] = encoded
                _cache_bytes += len(encoded)
                while len(_CACHE) > 12 or _cache_bytes > _CACHE_LIMIT:
                    _, removed = _CACHE.popitem(last=False)
                    _cache_bytes -= len(removed)
    return json.loads(encoded)


def index_calculations(index_id: str, snapshot: dict, version: str, detail: str = 'full') -> dict:
    """仅供已验证只读视图调用；复用原价格公式与无损编码。"""
    from pmi.market_data.index_calculations import calculate, calculate_overview
    if detail not in ('overview', 'full'):
        raise ValueError('calculation_parameters_invalid')
    compute = calculate_overview if detail == 'overview' else calculate
    return _calculated('index:' + index_id + ':' + detail, snapshot, version,
                       lambda: compact_index(compute(index_id, snapshot, version), overview=detail == 'overview'))


def activity_calculations(snapshot: dict, version: str) -> dict:
    """仅供已验证量额视图调用；缓存不包含来源准入或提交有效性结论。"""
    from pmi.market_data.activity.calculations import calculate
    return _calculated('activity:' + snapshot['series_id'], snapshot, version, lambda: compact_activity(calculate(snapshot, version)))
