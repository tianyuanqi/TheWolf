"""唯一OpenAPI派生的产品HTTP边界；不承担金融或存储语义。"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import logging
import math
from typing import Any

from jsonschema import Draft202012Validator, ValidationError as SchemaError
from pydantic import ValidationError

from . import models

logger = logging.getLogger(__name__)
_COMBINED_COMPONENTS = frozenset({'StoredPriceView', 'StoredPriceOverview', 'StoredPriceRange', 'StoredActivityView', 'StoredActivityRange', 'StoredMarketOverview', 'IndexSeriesCombinedView', 'IndexSeriesOverviewView',
                                 'IndexSeriesViewResponse', 'MarketActivityCombinedView'})


class ContractResponseError(ValueError):
    """内部响应不符合契约；公开错误不包含原响应、机器路径或凭据。"""


def verify_resources() -> None:
    """装配时核对安装包内派生资源，拒绝部分复制或混用契约版本。"""
    root = files(__package__)
    manifest = json.loads(root.joinpath("generation.json").read_text(encoding="utf-8"))
    for name, source in (("models.py", "http_dto.py"), ("schemas.json", "schemas.json"),
                         ("openapi.resource", "openapi.resource"), ("operations.json", "operations.json")):
        actual = hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest()
        if actual != manifest["outputs"][source]:
            raise ContractResponseError("安装包契约资源不一致")
    if manifest["source_version"] != "3.0.0" or manifest["source_sha256"] != manifest["outputs"]["openapi.resource"]:
        raise ContractResponseError("安装包契约版本不匹配")


def _integer_values(value: Any) -> Any:
    """只规范化Schema已接受的JSON整数值，不转换Decimal字符串或布尔值。"""
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _integer_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_integer_values(item) for item in value]
    return value


def _same_value(left: Any, right: Any) -> bool:
    """逐字段比较JSON值；数值写法可等值，布尔不能冒充整数。"""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_value(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_value(a, b) for a, b in zip(left, right))
    return left == right


@lru_cache(maxsize=32)
def _validator(name: str):
    """从安装包资源构建同源组件校验器，不访问仓库或工具目录。"""
    schema = json.loads(files(__package__).joinpath("schemas.json").read_text(encoding="utf-8"))
    if name not in schema["$defs"]:
        raise ContractResponseError("未登记的HTTP响应组件")
    if name in _COMBINED_COMPONENTS:
        from .schema_graph import validator
        return validator(schema, name)
    return Draft202012Validator({**schema, "$ref": "#/$defs/" + name})


def validate_combined_schema(schema: dict, value: Any) -> bool:
    """仅对精确同源组件复用规则图；路由内联/组合Schema仍由原边界完整验证。"""
    for name in _COMBINED_COMPONENTS:
        if schema == {"$ref": "#/$defs/" + name}:
            _validator(name).validate(value)
            return True
    return False


def response_value(name: str, value: Any) -> Any:
    """无损核对HTTP JSON边界，保留缺省、null、原值和全部证据字段。

    Args:
        name: 服务端固定的生成组件名，不能来自客户端模块/路径参数。
        value: 已由用例或原框架适配得到的JSON值，不修改调用者输入。
    Returns:
        生成DTO的JSON值；不补齐未提供字段，不承诺数字原始字面编码。
    Raises:
        ContractResponseError: Schema或严格DTO拒绝，或往返发生字段/值变化。
    """
    try:
        # 裸DTO会宽化可选非null字段；必须先校验原输入，再规范化整数值。
        _validator(name).validate(value)
        model = getattr(models, name)
        if name in _COMBINED_COMPONENTS:
            try:
                # 正常JSON整数直接严格检查；只有原Schema接受的1.0等写法
                # 才需要原规范化遍历。失败仍走原DTO，接受集合不变。
                result = model.model_validate(value, strict=True)
            except ValidationError:
                result = model.model_validate(_integer_values(value), strict=True)
        else:
            result = model.model_validate(_integer_values(value), strict=True)
        output = result.model_dump(mode="json", exclude_unset=True)
        if not _same_value(output, value):
            raise ContractResponseError("HTTP响应往返发生字段或值变化")
        return output
    except (SchemaError, ValidationError, ContractResponseError):
        logger.error("HTTP响应契约校验失败：%s", name)
        raise ContractResponseError("HTTP响应不符合当前契约") from None
