"""托管入口的显式配置；只映射现有ServiceConfig，不增加金融权限。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from pmi.service_config import ServiceConfig
from pmi.market_data import ActivityOptions


def unique(pairs: list[tuple[str, object]]) -> dict:
    """拒绝配置中的重复键，避免不同解析器取得不同权限。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('配置键重复')
        result[key] = value
    return result


def location(value: str, *, directory: bool = True) -> Path:
    """校验已有规范位置及全部祖先；不创建或修复业务位置。"""
    if not isinstance(value, str):
        raise ValueError('位置必须是字符串')
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('位置必须规范且无符号链接')
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError('位置尚不存在')
    return path


def disjoint(left: Path, right: Path) -> bool:
    """按路径分量判定两个位置互不包含。"""
    return left != right and left not in right.parents and right not in left.parents


def parse(raw: str, repo: Path) -> tuple[dict, ServiceConfig, Path]:
    """冻结显式设置，返回服务配置和安全运行基目录；失败无持久副作用。"""
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('非法数值')))
    required = {'python', 'data_root', 'service_port', 'browser_port', 'runtime_base'}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - {'index', 'activity', 'periodic', 'etf_flow'}:
        raise ValueError('配置字段不完整或含未知字段')
    executable = value['python']
    if not isinstance(executable, str) or not Path(executable).is_absolute() or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise ValueError('解释器不可执行')
    root, base = location(value['data_root']), location(value['runtime_base'])
    if type(value['browser_port']) is not int or not 0 < value['browser_port'] < 65536:
        raise ValueError('浏览器端口无效')
    idx = value.get('index', dict(write_ids=[], startup_ids=[], max_attempts=0, max_bytes=0))
    if not isinstance(idx, dict) or set(idx) != {'write_ids', 'startup_ids', 'max_attempts', 'max_bytes'}:
        raise ValueError('指数配置字段无效')
    for key in ('write_ids', 'startup_ids'):
        if not isinstance(idx[key], list) or any(not isinstance(x, str) for x in idx[key]):
            raise ValueError('指数集合无效')
    for key in ('max_attempts', 'max_bytes'):
        if type(idx[key]) is not int or idx[key] < 0:
            raise ValueError('指数预算无效')
    protected = [root, repo.resolve()]
    activity = None
    act = value.get('activity')
    if act is not None:
        fields = {'root', 'write_series', 'blocked_series', 'budget_ledger', 'budget_cycle', 'max_attempts', 'max_bytes'}
        if not isinstance(act, dict) or not fields <= set(act) or set(act) - fields - {'startup_series'} or not isinstance(act['write_series'], list) or not isinstance(act['blocked_series'], list) or not isinstance(act.get('startup_series', []), list):
            raise ValueError('量额配置字段无效')
        if any(not isinstance(x, list) or len(x) != 2 or any(not isinstance(v, str) for v in x) for x in act['blocked_series']):
            raise ValueError('量额撤回配置无效')
        activity_root = location(act['root']); protected.append(activity_root)
        ledger = location(act['budget_ledger'], directory=False) if act['budget_ledger'] is not None else None
        if ledger is not None:
            protected.append(ledger.parent)
        activity = ActivityOptions(activity_root, tuple(act['write_series']), tuple(tuple(x) for x in act['blocked_series']),
                                   act['max_attempts'], act['max_bytes'], act['budget_cycle'], ledger, tuple(act.get('startup_series', [])))
    etf = None
    etf_value = value.get('etf_flow')
    if etf_value is not None:
        from pmi.market_data import EtfOptions
        fields = {'root', 'configuration', 'evidence', 'grant', 'write_enabled', 'refresh_revision'}
        if not isinstance(etf_value, dict) or set(etf_value) != fields:
            raise ValueError('ETF配置字段无效')
        etf = EtfOptions(location(etf_value['root']), location(etf_value['configuration'], directory=False),
                         location(etf_value['evidence'], directory=False),
                         location(etf_value['grant'], directory=False) if etf_value['grant'] is not None else None,
                         etf_value['write_enabled'], etf_value['refresh_revision'])
        protected += [etf.root, etf.configuration_path, etf.evidence_path]
        if etf.grant_path is not None:
            protected.append(etf.grant_path)
    if any(not disjoint(base, p) for p in protected):
        raise ValueError('运行位置与业务位置或仓库重叠')
    if base.stat().st_uid != os.getuid() or base.stat().st_mode & 0o022:
        raise ValueError('运行基目录须由当前用户独占写入')
    periodic = None
    if 'periodic' in value:
        from pmi.market_data.periodic_budget import PeriodicOptions
        policy = value['periodic']
        if not isinstance(policy, dict) or set(policy) != {'daily_requests', 'daily_bytes', 'monthly_requests', 'monthly_bytes'}:
            raise ValueError('周期配置字段无效')
        periodic = PeriodicOptions(**policy)
    config = ServiceConfig(root, value['service_port'], (f"http://127.0.0.1:{value['browser_port']}",),
                           index_write_ids=tuple(idx['write_ids']), startup_index_ids=tuple(idx['startup_ids']),
                           index_max_attempts=idx['max_attempts'], index_max_bytes=idx['max_bytes'], activity_options=activity, periodic_options=periodic, etf_options=etf)
    return value, config, base


def service_arguments(value: dict) -> list[str]:
    """把冻结值传入既有CLI，不提供shell透传或隐式额外选项。"""
    args = ['serve', '--data-root', value['data_root'], '--port', str(value['service_port']), '--origin', f"http://127.0.0.1:{value['browser_port']}"]
    idx = value.get('index', dict(write_ids=[], startup_ids=[], max_attempts=0, max_bytes=0))
    for key, flag in [('write_ids', '--index-write-id'), ('startup_ids', '--startup-index-id')]:
        for item in idx[key]: args.extend([flag, item])
    args.extend(['--index-max-attempts', str(idx['max_attempts']), '--index-max-bytes', str(idx['max_bytes'])])
    act = value.get('activity')
    if act:
        args.extend(['--activity-root', act['root'], '--activity-budget-cycle', act['budget_cycle'], '--activity-max-attempts', str(act['max_attempts']), '--activity-max-bytes', str(act['max_bytes'])])
        if act['budget_ledger'] is not None: args.extend(['--activity-budget-ledger', act['budget_ledger']])
        for item in act['write_series']: args.extend(['--activity-write-series', item])
        for item in act.get('startup_series', []): args.extend(['--activity-startup-series', item])
        for series, evidence in act['blocked_series']: args.extend(['--activity-block', f'{series}={evidence}'])
    if 'periodic' in value:
        for key, item in value['periodic'].items():
            args.extend(['--periodic-'+key.replace('_', '-'), str(item)])
    etf = value.get('etf_flow')
    if etf is not None:
        args.extend(['--etf-root', etf['root'], '--etf-configuration', etf['configuration'], '--etf-evidence', etf['evidence'],
                     '--etf-write', str(etf['write_enabled']).lower()])
        if etf['grant'] is not None:
            args.extend(['--etf-grant', etf['grant']])
        if etf['refresh_revision'] is not None:
            args.extend(['--etf-refresh-revision', etf['refresh_revision']])
    return args
