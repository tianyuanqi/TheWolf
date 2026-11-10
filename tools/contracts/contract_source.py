"""唯一契约的受限源解析及稳定投影公共函数。"""
from __future__ import annotations
import json
from pathlib import Path
import yaml
from openapi_spec_validator import validate

# OAS3.1的全部操作键；元数据不计作操作，不支持的方法也不能静默过滤。
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def operations(spec):
    """遍历全部合法HTTP操作键，供源支持检查和实现对照共用。"""
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


class UniqueLoader(yaml.SafeLoader):
    """禁止重复键，避免后出现的结构静默覆盖已审字段。"""


def mapping(loader, node, deep=False):
    """解析唯一映射，不接受YAML合并键。"""
    result = {}
    for key_node, value_node in node.value:
        if key_node.value == "<<":
            raise ValueError("契约不允许YAML合并键")
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"重复键: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def local_refs(value):
    """拒绝远程引用及不能机械投影的引用位置，不联网解析结构。"""
    if isinstance(value, dict):
        if "$ref" in value and not value["$ref"].startswith("#/components/schemas/"):
            raise ValueError(f"只允许本地schema引用: {value['$ref']}")
        for item in value.values():
            local_refs(item)
    elif isinstance(value, list):
        for item in value:
            local_refs(item)


def load_current_spec(path: Path) -> dict:
    """读取并校验整个OpenAPI文档；检查不支持的schema断言。"""
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    local_refs(value)
    validate(value)
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum",
               "const", "anyOf", "oneOf", "$ref", "pattern", "minItems", "maxItems",
               "description", "format"}

    def schema(node):
        unknown = set(node) - allowed
        if unknown:
            raise ValueError(f"未经试点的schema关键字: {sorted(unknown)}")
        for child in node.get("properties", {}).values():
            schema(child)
        for keyword in ("items", "additionalProperties"):
            if isinstance(node.get(keyword), dict):
                schema(node[keyword])
        for keyword in ("anyOf", "oneOf"):
            for child in node.get(keyword, []):
                schema(child)

    for node in value["components"]["schemas"].values():
        schema(node)
    for path, item in value["paths"].items():
        for parameter in item.get("parameters", []):
            schema(parameter["schema"])
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            try:
                for parameter in operation.get("parameters", []):
                    schema(parameter["schema"])
                for media in operation.get("requestBody", {}).get("content", {}).values():
                    schema(media["schema"])
                for response in operation["responses"].values():
                    for media in response.get("content", {}).values():
                        schema(media["schema"])
                    for header in response.get("headers", {}).values():
                        schema(header["schema"])
            except ValueError as error:
                raise ValueError(f"{method.upper()} {path}: {error}") from error
    return value


def project(value):
    """仅转换本地引用位置，字段及断言不作人工二次定义。"""
    if isinstance(value, dict):
        return {key: (item.replace("#/components/schemas/", "#/$defs/") if key == "$ref"
                      else project(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [project(item) for item in value]
    return value


def save(path: Path, value) -> None:
    """保存稳定JSON，不混入运行时间或机器路径。"""
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def load_spec(path: Path) -> dict:
    """按显式协议版本选择解析，未知版本或缺失C扩展不能降级。"""
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    version = value.get("info", {}).get("version")
    if version in {"1.0.0", "1.1.0", "2.0.0", "3.0.0"}:
        from projection import load_target
        return load_target(path)
    if version != "0.1.4" or "x-wolf-transport" in value:
        raise ValueError("不支持的契约版本或混合格式")
    return load_current_spec(path)
