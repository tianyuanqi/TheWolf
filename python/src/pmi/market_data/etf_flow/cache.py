"""ETF字段合并纯规则；持久缓存只由统一SQLite实现。"""
from .model import Input, instant


def merge(rows: tuple[Input, ...], incoming: tuple[Input, ...], reason: str) -> tuple[Input, ...]:
    """按成员/日/字段追加版本；旧日和未返回字段保留，晚到输入不填零。"""
    values = {(x.member_id, x.date): x for x in rows}
    for row in incoming:
        key = row.member_id, row.date
        prior = values.get(key)
        fields = dict(prior.raw["fields"]) if prior else {}
        for name, field in row.fields.items():
            old = prior.fields.get(name) if prior else None
            if old is None or instant(old.source.retrieved_at) <= instant(field.source.retrieved_at):
                fields[name] = row.raw["fields"][name]
        values[key] = Input.parse({"member_id": row.member_id, "date": row.date, "fields": fields, "revision_reason": reason})
    return tuple(values[k] for k in sorted(values))
