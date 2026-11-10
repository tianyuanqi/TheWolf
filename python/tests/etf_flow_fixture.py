"""只从独立假配置取得身份；合成输入不连接网络、不读取真实根。"""
from copy import deepcopy
from pathlib import Path
from typing import Any

from pmi.market_data.etf_flow.calendar import preceding_window
from pmi.market_data.etf_flow.model import Adjustment, Configuration, Input, UNITS, canonical, decode, digest

END = "2026-11-04"
AT = "2026-11-05T12:00:00+08:00"


def configuration(name: str = "single") -> dict[str, Any]:
    return decode((Path(__file__).parent / "fixtures/etf_flow" / (name + ".json")).read_bytes())


def sample(name: str = "single", count: int = 321):
    """末四日F依次为10/20/30/40；来源与币值全部是虚构样本。"""
    config = Configuration.parse(configuration(name))
    dates = preceding_window(END, count)
    rows: list[Input] = []
    adjustments: list[Adjustment] = []
    for member in config.pools[-1].members:
        shares = 10000
        for i, on in enumerate(dates):
            shares += (10, 20, 30, 40)[i - (len(dates) - 4)] if i >= len(dates) - 4 else i % 3 + 1
            fields = {}
            for key, value in {"shares": str(shares), "nav": "1", "close": "1.01", "turnover": "500", "volume": "400"}.items():
                source = {"object_id": digest({"sample": True, "member": member.id, "day": on, "field": key}),
                          "publisher": "虚构发布方", "channel": "隔离测试", "url": member.basis.url,
                          "retrieved_at": AT, "published_at": None, "locator": "合成字段:" + key,
                          "original_unit": UNITS[key], "precision": "合成整数"}
                fields[key] = {"value": value, "date": on, "unit": UNITS[key], "source": source}
            rows.append(Input.parse({"member_id": member.id, "date": on, "fields": fields, "revision_reason": "隔离测试生成"}))
        adjustments.append(Adjustment.parse({"member_id": member.id, "kind": "normal", "start": dates[0], "end": dates[-1],
            "factor": "1", "tail": "0", "source_ids": [digest({"test": "normal", "member": member.id})],
            "confirmed_at": AT, "confirmation": "仅测试：普通份额单位"}))
    return config, tuple(rows), tuple(adjustments), dates


def replace_field(row: Input, key: str, value: str | None) -> Input:
    raw = deepcopy(row.raw)
    if value is None:
        raw["fields"].pop(key)
    else:
        raw["fields"][key]["value"] = value
    return Input.parse(raw)


def stored_sample(store, name="single", count=321):
    """一份显著标假的原件容纳所有合成值，避免持久化测试制造无意义重复文件。"""
    from pmi.market_data.etf_flow.calculation import adjustment_document
    from pmi.market_data.etf_flow.evidence import Evidence
    config, inputs, adjustments, dates = sample(name, count)
    original = store.put(canonical({"synthetic_test_only": True, "values": [
        {"member_id": x.member_id, "date": x.date, "fields": {k: str(f.value) for k, f in x.fields.items()}} for x in inputs]}))
    normalized = []
    for row in inputs:
        raw = deepcopy(row.raw)
        for field in raw["fields"].values():
            field["source"]["object_id"] = original
        normalized.append(Input.parse(raw))
    sources = []
    for adjustment in adjustments:
        source_id = store.put(canonical({"test": "normal", "member": adjustment.member_id}))
        member = next(m for m in config.pools[-1].members if m.id == adjustment.member_id)
        sources.append({"object_id": source_id, "publisher": "虚构测试资料", "channel": "仅隔离测试", "url": member.basis.url,
            "retrieved_at": AT, "published_at": None, "locator": "虚构普通区间", "original_unit": "份", "precision": "仅测试"})
    evidence = Evidence.parse({"format": "etf-flow-evidence-v1", "version": "test-evidence-1", "confirmed_at": AT,
        "confirmation": "隔离测试确认", "sources": sources, "adjustments": [adjustment_document(a) for a in adjustments],
        "disclosures": [], "events": []}, {m.id for m in config.pools[-1].members})
    return config, tuple(normalized), evidence, dates
