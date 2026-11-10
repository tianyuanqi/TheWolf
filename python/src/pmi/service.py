"""独立浏览器服务入口；显式配置，启动不初始化样本或自动更新。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pmi.service_config import ServiceConfig


def main() -> None:
    """输出公开连接描述，或按同一冻结配置启动单进程服务。"""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("describe-config", "describe-index-config", "describe-activity-config", "describe-etf-config", "serve"))
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--origin", required=True, action="append")
    parser.add_argument("--index-write-id", action="append", default=[])
    parser.add_argument("--startup-index-id", action="append", default=[])
    parser.add_argument("--index-max-attempts", type=int, default=16)
    parser.add_argument("--index-max-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--activity-root", type=Path)
    parser.add_argument("--activity-write-series", action="append", default=[])
    parser.add_argument("--activity-startup-series", action="append", default=[])
    parser.add_argument("--activity-block", action="append", default=[], help="series_id=evidence_sha256，撤回后整系列隔离")
    parser.add_argument("--activity-budget-ledger", type=Path)
    parser.add_argument("--activity-budget-cycle", default="activity-budget-v1")
    parser.add_argument("--activity-max-attempts", type=int, default=0)
    parser.add_argument("--activity-max-bytes", type=int, default=0)
    parser.add_argument("--etf-root", type=Path)
    parser.add_argument("--etf-configuration", type=Path)
    parser.add_argument("--etf-evidence", type=Path)
    parser.add_argument("--etf-grant", type=Path)
    parser.add_argument("--etf-write", choices=("false", "true"), default="false")
    parser.add_argument("--etf-refresh-revision")
    for key in ('daily-requests', 'daily-bytes', 'monthly-requests', 'monthly-bytes'):
        parser.add_argument('--periodic-'+key, type=int)
    parser.add_argument("--managed-run-id")
    parser.add_argument("--managed-control-fd", type=int)
    parser.add_argument("--managed-watch-fd", type=int)
    args = parser.parse_args()
    managed = (args.managed_run_id, args.managed_control_fd, args.managed_watch_fd)
    if any(x is not None for x in managed) and (any(x is None for x in managed) or args.action != "serve"):
        parser.error("托管参数必须完整且仅用于serve")
    try:
        from pmi.market_data import ActivityOptions as Options
        activity = Options(args.activity_root, tuple(args.activity_write_series), tuple(tuple(x.split("=")) for x in args.activity_block),
                           args.activity_max_attempts, args.activity_max_bytes, args.activity_budget_cycle,
                           args.activity_budget_ledger, tuple(args.activity_startup_series)) if args.activity_root else None
        if activity is None and (args.activity_startup_series or args.activity_write_series or args.activity_block or args.activity_budget_ledger or args.activity_max_attempts or args.activity_max_bytes):
            raise ValueError("量额选项须显式量额根")
        from pmi.market_data.periodic_budget import PeriodicOptions
        limits = {key: getattr(args, 'periodic_'+key) for key in ('daily_requests', 'daily_bytes', 'monthly_requests', 'monthly_bytes')}
        periodic = None
        if any(item is not None for item in limits.values()):
            if any(item is None for item in limits.values()):
                raise ValueError('周期额度四项必须完整指定')
            periodic = PeriodicOptions(**limits)
        etf = None
        if any((args.etf_root, args.etf_configuration, args.etf_evidence, args.etf_grant, args.etf_refresh_revision)) or args.etf_write == "true":
            if any(x is None for x in (args.etf_root, args.etf_configuration, args.etf_evidence)):
                raise ValueError("ETF根、观察池配置和证据配置必须完整指定")
            from pmi.market_data import EtfOptions
            etf = EtfOptions(args.etf_root, args.etf_configuration, args.etf_evidence, args.etf_grant,
                             args.etf_write == "true", args.etf_refresh_revision)
        config = ServiceConfig(args.data_root, args.port, tuple(args.origin),
                               index_write_ids=tuple(args.index_write_id), startup_index_ids=tuple(args.startup_index_id),
                               index_max_attempts=args.index_max_attempts, index_max_bytes=args.index_max_bytes, activity_options=activity, periodic_options=periodic, etf_options=etf)
    except ValueError as error:
        parser.error(str(error))
    if args.action in {"describe-config", "describe-index-config", "describe-activity-config", "describe-etf-config"}:
        descriptor = config.public_descriptor() if args.action == "describe-config" else config.public_index_descriptor()
        if args.action == "describe-activity-config":
            descriptor = config.public_activity_descriptor()
        if args.action == "describe-etf-config":
            descriptor = config.public_etf_descriptor()
        print(json.dumps(descriptor, ensure_ascii=False, sort_keys=True))
        return
    from pmi.api import create_app
    if args.managed_run_id:
        from pmi.managed_service import serve
        serve(create_app(config), config, *managed)
        return
    import uvicorn
    uvicorn.run(create_app(config), host="127.0.0.1", port=config.port, workers=1,
                reload=False, proxy_headers=False, server_header=False, access_log=False)


if __name__ == "__main__":
    main()
