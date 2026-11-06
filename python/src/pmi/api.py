"""独立浏览器HTTP装配；全部入口先执行目标协议边界，不初始化业务数据。"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from pmi.http_boundary import Boundary, Rejected, INDEX_SERIES_OPERATIONS, ACTIVITY_OPERATIONS
from pmi.http_contract import response_value, verify_resources
from pmi.market_data import ReadUnavailable, SnapshotError
from pmi.service_config import ServiceConfig
from pmi.update_service import UpdateService

_LOGGER = logging.getLogger(__name__)
def _dispatch(boundary: Boundary, operation: str, paths: dict, query: dict, updates: UpdateService) -> Response:
    response = _dispatch_value(boundary, operation, paths, query, updates)
    if response.media_type == "application/json":
        boundary.response(operation, response.status_code, json.loads(response.body))
    return response


def _dispatch_value(boundary: Boundary, operation: str, paths: dict, query: dict, updates: UpdateService) -> Response:
    if operation in ACTIVITY_OPERATIONS:
        return _dispatch_activity(boundary, operation, paths, query)
    if operation in INDEX_SERIES_OPERATIONS:
        return _dispatch_series(boundary, operation, paths, query, updates)
    if operation == "health":
        return JSONResponse(response_value("Health", {"status": "ok", "service": "thewolf-local-service", "storage": "sqlite"}))
    if operation == "sessionReady":
        descriptor = boundary.config.public_descriptor()
        descriptor.pop("endpoint")
        return JSONResponse(response_value("Ready", {"status": "ready", "instance_id": boundary.instance, **descriptor}))
    raise ValueError("未知业务操作")


def _series_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(response_value("IndexSeriesError", {"detail": {"code": code, "message": message}}), status_code=status)


def _dispatch_series(boundary: Boundary, operation: str, paths: dict, query: dict,
                     updates: UpdateService) -> Response:
    """新特性只经公共数据门面访问；旧协议视图与新快照显式区分。"""
    if operation == "indexSeriesReady":
        descriptor = boundary.config.public_index_descriptor()
        descriptor.pop("endpoint")
        return JSONResponse(response_value("IndexSeriesReady", {"status": "ready", "instance_id": boundary.instance, **descriptor}))
    if operation == "indexSeriesOperationResult":
        return JSONResponse(response_value("IndexSeriesOperationResult", updates.lookup({**query, "request_id": paths["request_id"]})))
    if operation == "startIndexSeries":
        status, value = updates.start_series(paths["index_id"], paths["request_id"])
        if value is None:
            return Response("Internal Server Error", status_code=500, media_type="text/plain")
        return JSONResponse(response_value("IndexSeriesAcceptedOperation" if status == 202 else "IndexSeriesError", value), status_code=status)
    try:
        boundary.config.check_location()
        data = boundary.config.market_data
        if operation == "overviewUpdateStatus":
            component, value = "OverviewUpdateStatus", data.periodic_status()
        elif operation == "indexSeriesCatalog":
            component, value = "IndexSeriesCatalog", data.index_catalog(query.get("query"))
        elif operation == "indexSeriesStatus":
            component, value = "IndexSeriesUpdateStatus", updates.series_status(paths["index_id"])
        elif operation == "indexSeriesEvidence":
            component, value = "IndexSeriesEvidenceView", data.read_evidence(paths["index_id"], paths["snapshot_id"], paths["object_id"])
        elif operation == "indexSeriesCalculations":
            component, value = "IndexSeriesCalculations", data.read_index_calculations(
                paths["index_id"], paths["snapshot_id"], query["formula_version"])
        elif operation == "indexSeriesRange":
            component, value = "IndexSeriesRange", data.read_index_range(paths["index_id"], **query)
        else:
            component, value = "IndexSeriesView", data.read_daily(paths["index_id"], paths.get("snapshot_id", query.get("snapshot_id")))
        boundary.config.check_location()
    except (ReadUnavailable, SnapshotError, OSError, ValueError, KeyError, TypeError) as error:
        prefix = str(error).split(":", 1)[0] if isinstance(error, SnapshotError) else ""
        if operation == "overviewUpdateStatus":
            message = "服务时钟回退，暂停取数；已有数据继续可读" if prefix == "periodic_clock_regressed" else "自动更新账本或状态暂时无法核验；保留已保存数据，不自动恢复账本"
            return _series_error(409, "index_series_invalid", message)
        if prefix == "calculation_parameters_invalid":
            return JSONResponse(response_value("IndexSeriesCalculationError", {"detail": {
                "code": prefix, "message": "计算参数或指数未准入"}}), status_code=422)
        if prefix == "index_range_invalid":
            return _series_error(422, prefix, "日期范围或字段未准入")
        if prefix == "coverage_insufficient":
            return _series_error(409, prefix, "所选固定快照不能覆盖请求范围")
        if prefix in {"index_evidence_not_found", "index_series_evidence_not_found"}:
            return _series_error(404, "index_series_evidence_not_found", "固定证据不存在或不属于此指数快照")
        return _series_error(409, "index_series_invalid", "本地资料缺失、正在写入或不能安全核验")
    if value is None:
        fixed = "snapshot_id" in paths or "snapshot_id" in query
        return _series_error(404, "index_series_snapshot_not_found" if fixed else "index_series_empty", "尚无对应的已保存资料")
    return JSONResponse(response_value(component, value))


def _dispatch_activity(boundary: Boundary, operation: str, paths: dict, query: dict) -> Response:
    """B业务只调用行情门面；来源未准入或撤回返回明确错误，绝不伪造快照。"""
    from datetime import date
    from pmi.market_data import ActivityError, ACTIVITY_MARKET as MARKET
    try:
        data = boundary.config.market_data
        if operation == "marketActivityReady":
            descriptor = boundary.config.public_activity_descriptor()
            descriptor.pop("endpoint")
            component, value = "MarketActivityReady", {**descriptor, "status": "ready", "instance_id": boundary.instance, "market_anchor_date": data.activity_anchor_date, "market_anchors": data.activity_market_anchors}
        elif operation == "marketActivityOperation":
            component, value = "MarketActivityOperation", data.activity("lookup", query["series_id"], paths["request_id"], boundary.config.activity_config_id, boundary.instance)
        elif operation == "startMarketActivity":
            component, value = "MarketActivityOperation", data.activity("start", paths["series_id"], paths["request_id"], paths["activity_body"], boundary.config.activity_config_id, boundary.instance)
        elif operation == "currentMarketActivity":
            key = "anchor_date" if paths["series_id"] in (MARKET, "cn-a-turnover-sse-szse") else "price_snapshot_id"
            if set(query) != {key}:
                raise ActivityError("invalid_activity_parameters", 422)
            if key == "anchor_date":
                try:
                    date.fromisoformat(query[key])
                except ValueError as error:
                    raise ActivityError("invalid_activity_parameters", 422) from error
            component, value = "MarketActivityCurrent", data.activity("current", paths["series_id"], query[key])
        else:
            components = {"fixedMarketActivity": ("fixed", "MarketActivitySnapshot"),
                          "marketActivityCalculations": ("calculations", "MarketActivityCalculations"),
                          "marketActivityEvidence": ("evidence", "MarketActivityEvidence")}
            action, component = components[operation]
            args = [paths["series_id"], paths["activity_id"]]
            if action == "calculations":
                args.append(query["formula_version"])
            if action == "evidence":
                args.append(paths["object_id"])
            value = data.activity(action, *args)
        if value is None:
            raise ActivityError("activity_not_found", 404)
        return JSONResponse(response_value(component, value))
    except ActivityError as error:
        return JSONResponse(response_value("MarketActivityError", {"detail": {"code": error.code, "message": "量额资料不可用；请核对来源准入、固定引用或更新状态"}}), status_code=error.status)
    except (ReadUnavailable, SnapshotError, OSError, ValueError, KeyError, TypeError):
        return JSONResponse(response_value("MarketActivityError", {"detail": {"code": "activity_invalid", "message": "量额资料不能安全重放；只读入口不会恢复"}}), status_code=409)


def create_app(config: ServiceConfig) -> FastAPI:
    """从显式配置装配一个实例；没有环境默认根或隐式样本，启写仍须显式请求。"""
    verify_resources()
    app = FastAPI(title="TheWolf Local Service", docs_url=None, redoc_url=None, openapi_url=None,
                  redirect_slashes=False)
    boundary = Boundary(config, str(uuid.uuid4()))
    app.state.config = config
    app.state.boundary = boundary
    updates = UpdateService(boundary)
    app.state.updates = updates
    app.add_event_handler("startup", updates.start_startup)

    async def close_index_workers() -> None:
        if not await run_in_threadpool(updates.close):
            raise RuntimeError("指数worker未在关闭期限内退出")

    app.add_event_handler("shutdown", close_index_workers)

    async def endpoint(request: Request) -> Response:
        operation, paths, query = request.state.invocation
        return await run_in_threadpool(_dispatch, boundary, operation, paths, query, updates)

    for path, item in boundary.spec["paths"].items():
        for method in ("get", "post", "options"):
            if method in item:
                app.add_api_route(path, endpoint, methods=[method.upper()], name=item[method]["operationId"])

    @app.middleware("http")
    async def guard(request: Request, call_next) -> Response:
        # 中间件覆盖框架404/405/异常；任何拒绝均在业务入口之前完成。
        bound = False
        ready = False
        operation = None
        try:
            headers = boundary.headers(request)
            if request.method == "OPTIONS":
                method, names = boundary.preflight(request, headers)
                response = Response(status_code=204, headers={
                    "Access-Control-Allow-Methods": method, "Access-Control-Allow-Headers": names,
                    "Access-Control-Max-Age": "0", "Vary": "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"})
            else:
                operation, paths, query, bound = await boundary.actual(request, headers)
                ready = operation in {"sessionReady", "indexSeriesReady", "marketActivityReady"}
                request.state.invocation = (operation, paths, query)
                response = await call_next(request)
        except Rejected as error:
            value = {"detail": {"code": error.code, "message": error.message}}
            response = JSONResponse(response_value("BoundaryError" + str(error.status), value), status_code=error.status)
            if error.allow:
                response.headers["Allow"] = error.allow
        except Exception as error:
            # 边界不返回原异常/路径；异常类型保留供本机诊断，不能伪装成功。
            _LOGGER.error("本地API内部失败：%s", type(error).__name__)
            response = Response("Internal Server Error", status_code=500, media_type="text/plain")
            bound = ready = False
        if request.method != "OPTIONS":
            response.headers["Cache-Control"] = "no-store"
        if bound or ready:
            response.headers["X-Wolf-Instance"] = boundary.instance
            response.headers["X-Wolf-Config"] = boundary.configuration_id(operation)
        origins = [v.decode("latin-1") for k, v in request.scope["headers"] if k.lower() == b"origin"]
        if len(origins) == 1 and origins[0] in config.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origins[0]
            response.headers["Access-Control-Expose-Headers"] = "X-Wolf-Instance, X-Wolf-Config"
        if request.method != "OPTIONS" or "Vary" not in response.headers:
            response.headers["Vary"] = "Origin"
        if request.method == "HEAD":
            response = Response(status_code=response.status_code, headers=dict(response.headers))
        return response

    return app
