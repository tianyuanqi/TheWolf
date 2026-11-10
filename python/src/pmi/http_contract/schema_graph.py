"""将冻结Schema装配为已有原生校验节点；不缓存响应或证据有效性。"""
from __future__ import annotations

import re
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from pydantic_core import SchemaValidator, ValidationError as CoreError, core_schema as core


class _Unsupported(ValueError):
    pass


class _Compiled:
    def __init__(self, native: SchemaValidator, original: Draft202012Validator):
        self.native, self.original = native, original

    def validate(self, instance: Any) -> None:
        try:
            self.native.validate_python(instance, strict=True)
        except CoreError:
            # 原生严格类型会拒绝JSON Schema允许的整数1.0、孤立代理码点等；
            # 失败回原引擎，不能改变原契约的接受/拒绝集合。
            self.original.validate(instance)

    def is_valid(self, instance: Any) -> bool:
        try:
            self.validate(instance)
            return True
        except ValidationError:
            return False


def validator(schemas: dict, name: str) -> _Compiled | Draft202012Validator:
    """仅编译能证明等价的有限语法，其他语法和不相斥oneOf回原引擎。

    原生节点只做JSON结构约束，不代替DTO往返、金融语义或磁盘证据重放。
    使用已有pydantic_core；生成Schema仍是唯一来源，没有另存手写规则。
    """
    original = Draft202012Validator({**schemas, '$ref': '#/$defs/' + name})
    nodes: dict[int, str] = {}
    definitions: list[dict] = []
    active: set[int] = set()

    def resolve(schema: dict | bool) -> dict | bool:
        visited = set()
        while isinstance(schema, dict) and '$ref' in schema:
            target = schema['$ref']
            if (set(schema) != {'$ref'} or not target.startswith('#/$defs/')
                    or '/' in target[8:] or '~' in target or target in visited):
                raise _Unsupported('nonlocal, compound or cyclic reference')
            visited.add(target)
            schema = schemas['$defs'][target[8:]]
        return schema

    def disjoint(choices: list) -> bool:
        # oneOf不能宽化成anyOf；只编译可从必填/禁止属性或字符串标签证明两两互斥的分支。
        if len(choices) == 1:
            return True
        branches = [resolve(s) for s in choices]
        if not branches or any(not isinstance(s, dict) or s.get('type') != 'object' for s in branches):
            return False
        def pair(left: dict, right: dict) -> bool:
            for required, closed in ((left, right), (right, left)):
                if closed.get('additionalProperties') is False and (
                        set(required.get('required', [])) - set(closed.get('properties', {}))):
                    return True
            common = set(left.get('required', [])) & set(right.get('required', []))
            for key in common:
                tags = [resolve(s.get('properties', {}).get(key, {})) for s in (left, right)]
                if any(not isinstance(t, dict) or t.get('type') != 'string' for t in tags):
                    continue
                values = [[t['const']] if 'const' in t else t.get('enum', []) for t in tags]
                if all(v and all(type(x) is str for x in v) for v in values) and set(values[0]).isdisjoint(values[1]):
                    return True
            return False
        return all(pair(left, right) for i, left in enumerate(branches) for right in branches[i+1:])

    def build(schema: dict | bool) -> dict:
        key = id(schema)
        if key in active:
            raise _Unsupported('cyclic schema')
        if key in nodes:
            return core.definition_reference_schema(nodes[key])
        node = 'schema_' + str(len(nodes))
        nodes[key] = node
        active.add(key)
        result = compile_node(schema)
        active.remove(key)
        definitions.append(core.chain_schema([result], ref=node))
        return core.definition_reference_schema(node)

    def compile_node(schema: dict | bool) -> dict:
        if schema is True:
            return core.any_schema()
        if not isinstance(schema, dict):
            raise _Unsupported('unsupported boolean/schema')
        if '$ref' in schema:
            return build(resolve(schema))
        rule = {k: v for k, v in schema.items() if k not in {'description', 'format'}}
        if not rule:
            return core.any_schema()
        if set(rule) in ({'anyOf'}, {'oneOf'}):
            choices = next(iter(rule.values()))
            if not choices or ('oneOf' in rule and not disjoint(choices)):
                raise _Unsupported('nonexclusive union')
            children = [build(s) for s in choices]
            return children[0] if len(children) == 1 else core.union_schema(children, mode='left_to_right')
        kind = rule.pop('type', None)
        allowed = {
            'string': {'pattern', 'minLength', 'maxLength'}, 'integer': {'minimum'},
            'boolean': set(), 'null': set(),
            'array': {'items', 'minItems', 'maxItems'},
            'object': {'properties', 'required', 'additionalProperties'},
        }
        if kind not in allowed or set(rule) - allowed[kind] - {'enum', 'const'}:
            raise _Unsupported('unknown type/keyword')
        if kind == 'string':
            # 编译Python正则以保留原re.search与锚点语义，不改用Rust正则。
            result = core.str_schema(strict=True, pattern=re.compile(rule['pattern']) if 'pattern' in rule else None,
                                     min_length=rule.get('minLength'), max_length=rule.get('maxLength'))
        elif kind == 'integer':
            result = core.int_schema(strict=True, ge=rule.get('minimum'))
        elif kind == 'boolean':
            result = core.bool_schema(strict=True)
        elif kind == 'null':
            result = core.none_schema()
        elif kind == 'array':
            result = core.list_schema(build(rule.get('items', True)), strict=True,
                                      min_length=rule.get('minItems'), max_length=rule.get('maxItems'))
        else:
            properties = rule.get('properties', {})
            required = set(rule.get('required', []))
            if required - set(properties):
                raise _Unsupported('undeclared required field')
            extra = rule.get('additionalProperties', True)
            fields = {k: core.typed_dict_field(build(s), required=k in required) for k, s in properties.items()}
            result = core.typed_dict_schema(fields, strict=True, extra_behavior='forbid' if extra is False else 'allow',
                                           extras_schema=build(extra) if isinstance(extra, dict) else None)
        for keyword in ('const', 'enum'):
            if keyword not in rule:
                continue
            values = [rule[keyword]] if keyword == 'const' else rule[keyword]
            types = {'string': str, 'integer': int, 'boolean': bool}
            if kind not in types or not values or any(type(v) is not types[kind] for v in values):
                raise _Unsupported('nonprimitive or mixed literal')
            # 先严格类型，避免原生literal把True当1；原JSON整数浮点由失败回退处理。
            result = core.chain_schema([result, core.literal_schema(values)])
        return result

    try:
        root = build(schemas['$defs'][name])
        return _Compiled(SchemaValidator(core.definitions_schema(root, definitions)), original)
    except (_Unsupported, KeyError, TypeError):
        return original
