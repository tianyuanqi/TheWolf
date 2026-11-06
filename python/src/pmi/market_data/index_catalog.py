"""首批六个价格指数的固定身份注册表；仅用于指数业务域。"""

import re
from dataclasses import dataclass

from pmi.market_data import SnapshotError

CATALOG_VERSION = "index-catalog-v1"
EXACT_POLICY = "index-csindex-eastmoney-exact-v1"
ROUNDING_POLICY = "index-cnindex-eastmoney-rounding-aware-v1"
ROUNDING_LIMIT = "这是核验规则，不是存储口径，官方四位原值保持。不能发现官方原值与东财两位发布值之间小于0.005点的差异，不能独立核验第三、四位。不同隐藏原值即使差异很小，跨舍入边界也可能被发现；同一舍入区间内误差不可区分，不采用绝对差容差。"
LIMITATIONS = ("价格指数日线，latest_only，不代表历史时点当时可见版本。", "成交额与估值尚未准入。", "交易日历仅覆盖 2023—2026 年，未知年份拒绝更新。")


@dataclass(frozen=True)
class IndexDefinition:
    """不可变的指数身份、原始精度及来源策略。"""

    index_id: str
    code: str
    name: str
    full_name: str | None
    provider: str
    relative_dir: str
    sources: tuple[str, str]
    source_policy_version: str
    storage_decimals: int
    aliases: tuple[str, ...]
    english_name: str
    english_full_name: str | None
    eastmoney_market: int


# 名称来自已保存的官方响应；双代码来自官方方法论。后缀为本项目输入语法。
INDICES = (
    IndexDefinition("csi:000300:price", "000300", "沪深300", "沪深300指数", "csindex", "indices/csi000300", ("csindex", "eastmoney"), EXACT_POLICY, 2,
                    ("000300", "399300", "000300.SH", "399300.SZ", "沪深300", "沪深300指数", "CSI 300", "CSI 300 Index"), "CSI 300", "CSI 300 Index", 1),
    IndexDefinition("sse:000001:price", "000001", "上证指数", "上证综合指数", "csindex", "indices/sse000001", ("csindex", "eastmoney"), EXACT_POLICY, 2,
                    ("000001", "000001.SH", "上证指数", "上证综合指数", "SSE Index", "SSE Composite Index"), "SSE Index", "SSE Composite Index", 1),
    IndexDefinition("csi:000852:price", "000852", "中证1000", "中证1000指数", "csindex", "indices/csi000852", ("csindex", "eastmoney"), EXACT_POLICY, 2,
                    ("000852", "399852", "000852.SH", "399852.SZ", "中证1000", "中证1000指数", "CSI 1000", "CSI 1000 Index"), "CSI 1000", "CSI 1000 Index", 1),
    IndexDefinition("szse:399001:price", "399001", "深证成指", None, "cnindex", "indices/szse399001", ("cnindex", "eastmoney"), ROUNDING_POLICY, 4,
                    ("399001", "399001.SZ", "深证成指", "深证成份指数", "Shenzhen Index"), "Shenzhen Index", None, 0),
    IndexDefinition("szse:399006:price", "399006", "创业板指", None, "cnindex", "indices/szse399006", ("cnindex", "eastmoney"), ROUNDING_POLICY, 4,
                    ("399006", "399006.SZ", "创业板指", "创业板指数P", "ChiNext"), "ChiNext", None, 0),
    IndexDefinition("sse:000688:price", "000688", "科创50", "上证科创板50成份指数", "csindex", "indices/sse000688", ("csindex", "eastmoney"), EXACT_POLICY, 2,
                    ("000688", "000688.SH", "科创50", "上证科创板50成份指数", "STAR 50", "SSE Science and Technology Innovation Board 50 Index"), "STAR 50", "SSE Science and Technology Innovation Board 50 Index", 1),
)


def get_index(index_id: str) -> IndexDefinition:
    """返回注册的 canonical 身份；拒绝其他输入。"""
    for index in INDICES:
        if index_id == index.index_id:
            return index
    raise SnapshotError("unknown_index")


def _query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 160:
        raise SnapshotError("unknown_index")
    value = query.strip()
    return value[:7] + value[7:].upper() if re.fullmatch(r"[0-9]{6}\.[A-Za-z]{2}", value) else value


def resolve_index(query: str) -> IndexDefinition:
    """仅解析精确注册别名，未知或不唯一时拒绝。

    Args:
        query: 指数业务域中的 canonical、代码、名称或项目市场后缀语法。

    Returns:
        唯一的不可变指数定义。
    """
    value = _query(query)
    matches = [index for index in INDICES if value == index.index_id or value in index.aliases]
    if len(matches) != 1:
        raise SnapshotError("ambiguous_index" if matches else "unknown_index")
    return matches[0]


def search_indices(query: str | None = None) -> list[IndexDefinition]:
    """返回有限注册表候选；未知代码不按片段猜测。"""
    if query is None or isinstance(query, str) and not query.strip():
        return list(INDICES)
    value = _query(query)
    exact = [index for index in INDICES if value == index.index_id or value in index.aliases]
    if exact:
        return exact
    if not any("\u4e00" <= character <= "\u9fff" for character in value):
        return []
    return [index for index in INDICES if any(value in alias for alias in index.aliases)]


def public_index(index: IndexDefinition, writable: bool = False) -> dict:
    """生成公开身份与能力，不暴露存储路径。"""
    if get_index(index.index_id) != index:
        raise SnapshotError("unknown_index_definition")
    return {"index_id": index.index_id, "code": index.code, "name": index.name,
            "full_name": index.full_name, "provider": index.provider, "return_type": "price",
            "frequency": "daily", "aliases": list(index.aliases), "storage_decimals": index.storage_decimals,
            "source_policy_version": index.source_policy_version,
            "capabilities": {"ohlc": "available", "amount": "unavailable", "valuation": "unavailable"},
            "limitations": list(LIMITATIONS) + ([ROUNDING_LIMIT] if index.storage_decimals == 4 else []),
            "writable": writable}
