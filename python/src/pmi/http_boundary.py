"""目标协议全入口守卫；在任何业务I/O前处理来源、方法、输入和绑定。"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
import re
from urllib.parse import parse_qsl

from fastapi import Request
from jsonschema import Draft202012Validator

from pmi.service_config import ServiceConfig

INDEX_SERIES_OPERATIONS = frozenset({"marketVersions", "storageStatus", "overviewUpdateStatus", "indexSeriesReady", "indexSeriesCatalog", "currentIndexSeries",
    "fixedIndexSeries", "indexSeriesView", "indexSeriesCalculations", "indexSeriesEvidence", "indexSeriesRange", "indexSeriesStatus",
    "startIndexSeries", "indexSeriesOperationResult"})


ACTIVITY_OPERATIONS = frozenset({"marketActivityReady", "currentMarketActivity", "fixedMarketActivity",
    "marketActivityView", "marketActivityCalculations", "marketActivityEvidence", "startMarketActivity", "marketActivityOperation"})


ETF_OPERATIONS = frozenset({"etfFlowReady", "currentEtfFlow", "etfFlowView", "etfFlowEvidence", "startEtfFlow", "etfFlowOperation"})

@dataclass
class Rejected(Exception):
    """可公开的稳定边界拒绝，不携带内部路径或原始载荷。"""

    status: int
    code: str
    message: str
    allow: str | None = None


class Boundary:
    """消费同源运行资源，将自然语言约定落实到明确检查函数。"""

    def __init__(self, config: ServiceConfig, instance: str):
        self.config = config
        self.instance = instance
        self.spec = json.loads(files("pmi.http_contract").joinpath("openapi.resource").read_text())
        self.schemas = json.loads(files("pmi.http_contract").joinpath("schemas.json").read_text())
        self.projection = json.loads(files("pmi.http_contract").joinpath("operations.json").read_text())
        self.routes = []
        for path, item in self.spec["paths"].items():
            pattern = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", path)
            self.routes.append((re.compile("^" + pattern + "$"), path, item))
        transport = self.spec["x-wolf-transport"]
        self.single_headers = {name.lower() for name in transport["single_headers"]} | {
            "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "sec-fetch-user"}
        self.allowed_headers = {name.lower() for name in transport["cors"]["allowed_headers"]}

    def valid(self, component: str, value: object) -> bool:
        """以生成Schema验证公开标识，不另维护同一正则或长度。"""
        return Draft202012Validator({**self.schemas, "$ref": "#/$defs/" + component}).is_valid(value)

    def configuration_id(self, operation: str) -> str:
        """由可信路由选择新特性摘要；不让客户端选择权限配置。"""
        if operation in ETF_OPERATIONS:
            return self.config.etf_config_id
        if operation in ACTIVITY_OPERATIONS:
            return self.config.activity_config_id
        return self.config.index_config_id if operation in INDEX_SERIES_OPERATIONS else self.config.config_id

    def response(self, operation: str, status: int, value: object) -> None:
        """使用源指针对应的生成校验器验证内联响应，而非宽化为通用错误。"""
        for path, item in self.spec["paths"].items():
            for method in ("get", "post"):
                if item.get(method, {}).get("operationId") != operation:
                    continue
                schema = self.projection["paths"][path][method]["responses"][str(status)]["content"]["application/json"]["schema"]
                if operation in {"indexSeriesView", "marketActivityView"}:
                    from pmi.http_contract import validate_combined_schema
                    if validate_combined_schema(schema, value):
                        return
                Draft202012Validator({**self.schemas, **schema}).validate(value)
                return
        raise ValueError("未知响应操作")

    def headers(self, request: Request) -> dict[str, str]:
        """保留原始重复项的检查先于字符串合并。"""
        result: dict[str, str] = {}
        for raw_name, raw_value in request.scope["headers"]:
            name = raw_name.decode("latin-1").lower()
            if name == "forwarded" or name.startswith("x-forwarded-"):
                raise Rejected(400, "invalid_headers", "不接受转发来源覆盖")
            if name not in self.single_headers:
                continue
            value = raw_value.decode("latin-1")
            if name in result or not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise Rejected(400, "invalid_headers", "请求头重复或编码无效")
            if name != "access-control-request-headers" and "," in value:
                raise Rejected(400, "invalid_headers", "单值请求头不能合并多个值")
            result[name] = value
        if result.get("host") != self.config.authority:
            raise Rejected(403, "bad_host", "请求主机不受信任")
        return result

    def route(self, path: str) -> tuple[str, dict, dict[str, str]]:
        """精确匹配活动路径；禁用框架路由和斜杠变体不重定向。"""
        for pattern, template, item in self.routes:
            match = pattern.fullmatch(path)
            if match:
                return template, item, match.groupdict()
        raise Rejected(404, "route_not_found", "接口不存在")

    def origin(self, headers: dict[str, str], *, preflight: bool = False) -> None:
        """浏览器来源必须精确匹配；缺Origin仅供有标记的非浏览器读取。"""
        origin = headers.get("origin")
        if (origin is not None and origin not in self.config.allowed_origins) or (preflight and origin is None):
            raise Rejected(403, "bad_origin", "请求来源不受信任")
        if preflight:
            return
        site, mode, dest = (headers.get(k) for k in ("sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"))
        if (site not in {None, "none", "same-origin", "same-site", "cross-site"}
                or mode not in {None, "cors", "same-origin", "no-cors"}
                or dest not in {None, "empty", ""}
                or "sec-fetch-user" in headers
                or (origin is None and site in {"same-site", "cross-site"})):
            raise Rejected(403, "bad_fetch_metadata", "导航或不可信浏览器上下文不能访问API")

    def parameters(self, item: dict, method: str) -> list[dict]:
        """从同一契约读取有效参数，不从客户端选择Schema。"""
        values = {}
        for parameter in [*item.get("parameters", []), *item[method].get("parameters", [])]:
            if "$ref" in parameter:
                parameter = self.spec["components"]["parameters"][parameter["$ref"].rsplit("/", 1)[1]]
            values[parameter["in"], parameter["name"].lower()] = parameter
        return list(values.values())

    def preflight(self, request: Request, headers: dict[str, str]) -> tuple[str, str]:
        """仅校验广告的方法及请求头集合，不比较绑定值或访问业务。"""
        self.origin(headers, preflight=True)
        _, item, _ = self.route(request.url.path)
        advertised = headers.get("access-control-request-method")
        advertised_headers = headers.get("access-control-request-headers")
        if not advertised or not advertised_headers:
            raise Rejected(400, "invalid_preflight", "预检元数据缺失或无效")
        allow = ", ".join(k.upper() for k in item if k in {"get", "post", "options"})
        if advertised not in {"GET", "POST"} or advertised.lower() not in item:
            raise Rejected(405, "method_not_allowed", "预检方法不受支持", allow)
        # 浏览器预检携带实际GET的查询串；仅检查已声明字段与重复项，
        # 原实例/配置等值仍由实际GET校验，不在预检中比较或访问业务。
        query_items = parse_qsl(request.scope.get("query_string", b"").decode("ascii", errors="replace"), keep_blank_values=True)
        query_names = [name for name, _ in query_items]
        allowed_query = {p["name"] for p in self.parameters(item, advertised.lower()) if p["in"] == "query"}
        if len(set(query_names)) != len(query_names) or not set(query_names) <= allowed_query:
            raise Rejected(400, "invalid_preflight", "预检查询字段重复或未受支持")
        names = [name.strip().lower() for name in advertised_headers.split(",")]
        required = {p["name"].lower() for p in self.parameters(item, advertised.lower()) if p["in"] == "header" and p.get("required")}
        if advertised == "POST":
            required.add("content-type")
        if not all(names) or len(set(names)) != len(names) or not required <= set(names) or not set(names) <= self.allowed_headers:
            raise Rejected(400, "invalid_preflight", "预检请求头集合无效")
        return advertised, ", ".join(sorted(set(names)))

    async def actual(self, request: Request, headers: dict[str, str]) -> tuple[str, dict[str, str], dict[str, str], bool]:
        """按已审顺序拒绝非法输入/禁写，再绑定业务读取实例。"""
        self.origin(headers)
        if headers.get("x-wolf-client") != "1":
            raise Rejected(403, "client_marker_required", "缺少客户端协议标记")
        _, item, paths = self.route(request.url.path)
        method = request.method.lower()
        if method not in item or method not in {"get", "post"}:
            allow = ", ".join(k.upper() for k in item if k in {"get", "post", "options"})
            raise Rejected(405, "method_not_allowed", "请求方法不受支持", allow)
        operation = item[method]["operationId"]
        parameters = self.parameters(item, method)
        query_items = parse_qsl(request.scope.get("query_string", b"").decode("ascii", errors="replace"), keep_blank_values=True)
        query = dict(query_items)
        query_spec = {p["name"]: p for p in parameters if p["in"] == "query"}
        required = {name for name, parameter in query_spec.items() if parameter.get("required")}
        if len(query) != len(query_items) or not required <= set(query) or not set(query) <= set(query_spec):
            raise Rejected(422, "invalid_request", "查询字段缺失、重复或未受支持")
        for parameter in parameters:
            if parameter["in"] not in {"path", "query"}:
                continue
            value = (paths if parameter["in"] == "path" else query).get(parameter["name"])
            if value is None and not parameter.get("required"):
                continue
            schema = json.loads(json.dumps(parameter["schema"]).replace("#/components/schemas/", "#/$defs/"))
            if not Draft202012Validator({**self.schemas, **schema}).is_valid(value):
                raise Rejected(422, "invalid_request", "请求标识无效")
        if method == "post" and operation == "startMarketActivity":
            await self.activity_body(request, headers, paths)
        elif method == "post" and operation == "startEtfFlow":
            await self.etf_body(request, headers, paths)
        elif method == "post":
            if headers.get("origin") is None:
                raise Rejected(403, "bad_origin", "写请求必须提供许可来源")
            media = headers.get("content-type", "").lower().replace(" ", "")
            if media not in {"application/json", "application/json;charset=utf-8"}:
                raise Rejected(415, "unsupported_media_type", "需要JSON媒体类型")
            # 更新体只能是空对象；限制读取量，拒绝任意大正文占用内存。
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 4096:
                    raise Rejected(422, "invalid_request", "更新体只能是空对象")
            try:
                value = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                raise Rejected(422, "invalid_request", "JSON正文无效") from None
            if value != {} or not isinstance(value, dict):
                raise Rejected(422, "invalid_request", "更新不接受自选参数")
            if not self.valid("RequestId", headers.get("x-wolf-request-id")):
                raise Rejected(422, "invalid_request", "请求关联标识缺失或无效")
            if operation != "startIndexSeries" or paths["index_id"] not in self.config.index_write_ids:
                raise Rejected(403, "index_update_disabled", "此操作未启用更新")
            paths["request_id"] = headers["x-wolf-request-id"]
        bound = operation not in {"health", "sessionReady", "indexSeriesReady", "marketActivityReady", "etfFlowReady"}
        if bound:
            instance, config = headers.get("x-wolf-expected-instance"), headers.get("x-wolf-expected-config")
            if instance is None or config is None:
                raise Rejected(400, "connection_context_required", "缺少连接上下文")
            if not self.valid("PublicInstanceId", instance) or not self.valid("PublicDigest", config):
                raise Rejected(400, "connection_context_invalid", "连接上下文无效")
            if instance != self.instance or config != self.configuration_id(operation):
                raise Rejected(409, "connection_context_mismatch", "服务实例或配置已变化，请重新连接")
        return operation, paths, query, bound


    async def activity_body(self, request: Request, headers: dict, paths: dict) -> None:
        """只为B接纳有界参数正文；旧空对象POST规则保持原样。"""
        from pmi.market_data import ACTIVITY_MARKET as MARKET
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("重复JSON键")
                result[key] = value
            return result
        if headers.get("origin") is None:
            raise Rejected(403, "bad_origin", "写请求必须提供许可来源")
        if headers.get("content-type", "").replace(" ", "").lower() not in {"application/json", "application/json;charset=utf-8"}:
            raise Rejected(415, "unsupported_media_type", "需要JSON媒体类型")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise Rejected(422, "invalid_request", "量额正文超限")
        try:
            value = json.loads(body, object_pairs_hook=unique)
        except (ValueError, UnicodeDecodeError):
            raise Rejected(422, "invalid_request", "量额正文无效") from None
        if not self.valid("MarketActivityUpdateBody", value) or not self.valid("RequestId", headers.get("x-wolf-request-id")):
            raise Rejected(422, "invalid_request", "量额参数或请求标识无效")
        target = "anchor_date" if paths["series_id"] in (MARKET, "cn-a-turnover-sse-szse") else "price_snapshot_id"
        if set(value) != {target, "expected_activity_id"}:
            raise Rejected(422, "invalid_request", "量额目标类型不匹配")
        options = self.config.activity_options
        if options is None or paths["series_id"] not in options.write_series:
            raise Rejected(403, "index_update_disabled", "量额操作未启写")
        paths["request_id"] = headers["x-wolf-request-id"]
        paths["activity_body"] = value

    async def etf_body(self, request: Request, headers: dict, paths: dict) -> None:
        """ETF只接受受控计划hash及CAS；不接受浏览器传成员、日期、来源或额度。"""
        from pmi.market_data import decode_etf_request as decode, etf_request_id as identifier
        if headers.get("origin") is None:
            raise Rejected(403, "bad_origin", "写请求必须提供许可来源")
        if headers.get("content-type", "").replace(" ", "").lower() not in {"application/json", "application/json;charset=utf-8"}:
            raise Rejected(415, "unsupported_media_type", "需要JSON媒体类型")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise Rejected(422, "invalid_request", "ETF更新正文超限")
        try:
            value = decode(body)
            request_id = identifier(headers.get("x-wolf-request-id"))
        except ValueError:
            raise Rejected(422, "invalid_request", "ETF正文或请求标识无效") from None
        if not self.valid("EtfUpdateBody", value):
            raise Rejected(422, "invalid_request", "ETF更新参数无效")
        if self.config.etf_options is None or not self.config.etf_options.write_enabled:
            raise Rejected(403, "update_disabled", "ETF操作未启写")
        paths["request_id"] = request_id
        paths["etf_body"] = value
