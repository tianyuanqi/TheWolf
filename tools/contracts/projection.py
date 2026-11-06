"""C契约的受限源解析和覆盖投影；运行证据由独立检查入口核对。"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import contract_source as legacy

FORMAT = "wolf-operations/C-target/1"
EXTENSIONS = ("x-wolf-transport", "x-wolf-operation-semantics", "x-wolf-disabled-routes")
ALLOWED = {"type", "properties", "required", "additionalProperties", "items", "enum",
           "const", "anyOf", "oneOf", "$ref", "pattern", "minItems", "maxItems",
           "description", "format", "minLength", "maxLength"}


def digest(value: object) -> str:
    """计算稳定结构摘要，原文件身份另用原字节SHA-256。"""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def pointer(spec: dict, ref: str):
    """只读取明确的本地JSON Pointer；禁止远程或未支持组件类别。"""
    if not any(ref.startswith("#/components/" + group + "/")
               for group in ("schemas", "parameters", "headers")):
        raise ValueError("不支持的引用: " + ref)
    node = spec
    try:
        for key in ref[2:].split("/"):
            node = node[key.replace("~1", "/").replace("~0", "~")]
    except (KeyError, TypeError) as error:
        raise ValueError("悬空引用: " + ref) from error
    return node


def references(spec: dict, node: object, location: str = "#", stack: tuple = ()) -> None:
    """遍历全部引用闭包，循环与引用兄弟覆盖均拒绝。"""
    if isinstance(node, dict):
        if "$ref" in node:
            if set(node) != {"$ref"}:
                raise ValueError("引用兄弟覆盖未支持: " + location)
            ref = node["$ref"]
            if ref in stack:
                raise ValueError("循环引用: " + location + " -> " + ref)
            references(spec, pointer(spec, ref), ref, stack + (ref,))
        else:
            for key, value in node.items():
                references(spec, value, location + "/" + escape(key), stack)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            references(spec, value, location + "/" + str(index), stack)


def resolve(spec: dict, node: dict, group: str, location: str) -> tuple[dict, str]:
    """按使用位置解析参数或响应头，保留声明源定位。"""
    seen = set()
    while "$ref" in node:
        ref = node["$ref"]
        if set(node) != {"$ref"} or not ref.startswith("#/components/" + group + "/"):
            raise ValueError("引用类别/兄弟错误: " + location)
        if ref in seen:
            raise ValueError("循环引用: " + location)
        seen.add(ref)
        node, location = pointer(spec, ref), ref
    return node, location


def schema_check(node: dict, location: str) -> None:
    """白名单仅增加长度断言；递归检查字段及组合，不跳过未知关键字。"""
    unknown = set(node) - ALLOWED
    if unknown:
        raise ValueError("未知Schema断言: " + location + " " + str(sorted(unknown)))
    if "$ref" in node and not node["$ref"].startswith("#/components/schemas/"):
        raise ValueError("Schema引用类别错误: " + location)
    for name, value in node.get("properties", {}).items():
        schema_check(value, location + "/properties/" + escape(name))
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            schema_check(node[key], location + "/" + key)
    for key in ("anyOf", "oneOf"):
        for index, value in enumerate(node.get(key, [])):
            schema_check(value, location + "/" + key + "/" + str(index))


def schema_locations(spec: dict) -> dict[str, dict]:
    """收集所有显式schema位置，包括扩展中的fallback结构。"""
    result = {"#/components/schemas/" + escape(k): v
              for k, v in spec["components"]["schemas"].items()}

    def walk(value: object, location: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_location = location + "/" + escape(key)
                if key == "schema":
                    result[child_location] = child
                else:
                    walk(child, child_location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, location + "/" + str(index))

    walk(spec, "#")
    return result


def load_target(path: Path) -> dict:
    """校验完整原目标，不改写源，不回退B扩展。"""
    spec = legacy.yaml.load(path.read_text(encoding="utf-8"), Loader=legacy.UniqueLoader)
    if spec["info"]["version"] not in {"1.0.0", "1.1.0", "2.0.0"} or any(k not in spec for k in EXTENSIONS):
        raise ValueError("C格式/版本/扩展缺失")
    if "x-wolf-current-transport" in spec or "x-wolf-coverage" in spec:
        raise ValueError("C目标混入B扩展")
    references(spec, spec)
    for location, schema in schema_locations(spec).items():
        schema_check(schema, location)
    # 显式位置校验须早于OAS验证，错误信息保留源Pointer。
    projection(spec, hashlib.sha256(path.read_bytes()).hexdigest())
    legacy.validate(spec)
    return spec


def projection(spec: dict, source_sha256: str) -> dict:
    """建立有效参数/头及语义覆盖登记；不声称自然语言已自动执行。"""
    boundaries: dict[str, dict] = {}
    routes = []

    def boundary(node: dict, group: str, use: str) -> dict:
        resolved, declaration = resolve(spec, node, group, use)
        schema = resolved["schema"]
        schema_check(schema, declaration + "/schema")
        location = declaration + "/schema"
        name = "Boundary_" + hashlib.sha256(location.encode()).hexdigest()[:16]
        boundaries[location] = {"validator": name, "schema": legacy.project(schema),
                                "source_pointer": location, "content_sha256": digest(schema)}
        return {"use_pointer": use, "declaration_pointer": declaration,
                "validator": name, "required": resolved.get("required", False),
                "name": resolved.get("name"), "in": resolved.get("in")}

    def parameters(items: list, location: str) -> dict:
        result = {}
        for index, node in enumerate(items):
            use = location + "/" + str(index)
            resolved, _ = resolve(spec, node, "parameters", use)
            key = (resolved["in"], resolved["name"].lower() if resolved["in"] == "header"
                   else resolved["name"])
            if key in result:
                raise ValueError("同层重复参数: " + use)
            result[key] = boundary(node, "parameters", use)
        return result

    for path, method, operation in legacy.operations(spec):
        base = "#/paths/" + escape(path)
        effective = parameters(spec["paths"][path].get("parameters", []), base + "/parameters")
        effective.update(parameters(operation.get("parameters", []), base + "/" + method + "/parameters"))
        headers = {}
        for status, response in operation["responses"].items():
            headers[status] = {}
            for name, header in response.get("headers", {}).items():
                use = base + "/" + method + "/responses/" + status + "/headers/" + escape(name)
                headers[status][name] = boundary(header, "headers", use)
        routes.append({"operation": method.upper() + " " + path,
                       "source_pointer": base + "/" + method,
                       "parameters": [effective[k] for k in sorted(effective)], "response_headers": headers})
    obligations = []
    for extension in EXTENSIONS:
        for name, value in spec[extension].items():
            obligations.append({"source_pointer": "#/" + extension + "/" + escape(name),
                "content_sha256": digest(value),
                "checker": "operation_state_cases" if extension == "x-wolf-operation-semantics"
                and name == "state_constraints" else "projection_retention_only",
                "runtime_evidence": "deferred-not-executed"})
    return {"format": FORMAT, "source_version": spec["info"]["version"],
            "source_sha256": source_sha256, "paths": legacy.project(spec["paths"]),
            "extensions": {k: copy.deepcopy(spec[k]) for k in EXTENSIONS},
            "routes": routes, "boundaries": boundaries, "obligations": obligations}


def check_coverage(spec: dict, source_sha: str, actual: dict) -> None:
    """双向核对合成覆盖投影；任何缺项/额外项/摘要或登记漂移失败。"""
    expected = projection(spec, source_sha)
    if actual != expected:
        raise ValueError("C覆盖投影/版本/来源/登记漂移")


def operation_state(value: dict) -> None:
    """只实现固定state_constraints子句的有限检查，不模拟真实关联存储。"""
    state = value["state"]
    status = value["business_status"]
    if state == "unknown":
        if status is not None or value["rejection"] is not None:
            raise ValueError("unknown不能有状态或拒绝结论")
        return
    if state == "rejected":
        if value["rejection"] is None or any(value[k] is not None for k in
                                             ("job_id", "business_status", "reused_job")):
            raise ValueError("rejected字段归属错误")
        return
    if any(value[k] is None for k in ("job_id", "business_status", "reused_job")) or value["rejection"] is not None:
        raise ValueError("非拒绝已关联状态缺字段")
    if value["job_id"] != status["job_id"]:
        raise ValueError("job不一致")
    if state in {"completed", "failed", "interrupted"} and status["stage"] != state:
        raise ValueError("终态不一致")
