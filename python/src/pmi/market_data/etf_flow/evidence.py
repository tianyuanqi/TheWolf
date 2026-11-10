"""人工确认的披露/事件及调整覆盖；不自动抓取、不按持仓比例分摊金额。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from .model import (Adjustment, FlowError, SHANGHAI, Source, canonical, day, decimal, decode, digest,
                    exact, identifier, instant, number, object_id, text)


@dataclass(frozen=True)
class Holder:
    name: str
    shares: Decimal
    percentage: Decimal
    classification: str | None
    classification_basis: str | None

    @classmethod
    def parse(cls, raw: Any) -> Holder:
        v = exact(raw, set(cls.__dataclass_fields__))
        percentage = decimal(v["percentage"], minimum=Decimal(0))
        if percentage > 100 or ((v["classification"] is None) != (v["classification_basis"] is None)):
            raise FlowError("etf_invalid_disclosure", 422)
        return cls(text(v["name"]), decimal(v["shares"], minimum=Decimal(0)), percentage,
                   text(v["classification"]) if v["classification"] is not None else None,
                   text(v["classification_basis"], 1000) if v["classification_basis"] is not None else None)


@dataclass(frozen=True)
class Disclosure:
    id: str
    member_id: str
    report_date: str
    published_date: str | None
    source_id: str
    locator: str
    state: str
    holders: tuple[Holder, ...]
    note: str

    @classmethod
    def parse(cls, raw: Any) -> Disclosure:
        v = exact(raw, set(cls.__dataclass_fields__))
        report = day(v["report_date"])
        published = day(v["published_date"]) if v["published_date"] is not None else None
        if (published is not None and published < report) or not isinstance(v["holders"], list):
            raise FlowError("etf_invalid_disclosure", 422)
        holders = tuple(Holder.parse(x) for x in v["holders"])
        if v["state"] not in {"disclosed", "not_disclosed"} or (v["state"] == "not_disclosed" and holders):
            raise FlowError("etf_invalid_disclosure", 422)
        if len({h.name for h in holders}) != len(holders):
            raise FlowError("etf_duplicate_holder", 422)
        return cls(identifier(v["id"]), identifier(v["member_id"]), report, published, object_id(v["source_id"]),
                   text(v["locator"], 1000), v["state"], holders, text(v["note"], 1000))


@dataclass(frozen=True)
class Event:
    id: str
    member_ids: tuple[str, ...]
    occurred_start: str | None
    occurred_end: str | None
    published_date: str | None
    source_id: str
    locator: str
    description: str
    subjects: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Any) -> Event:
        v = exact(raw, set(cls.__dataclass_fields__))
        start = day(v["occurred_start"]) if v["occurred_start"] is not None else None
        end = day(v["occurred_end"]) if v["occurred_end"] is not None else None
        if ((start is None) != (end is None) or (start is not None and start > end)
                or not isinstance(v["member_ids"], list) or not isinstance(v["subjects"], list)):
            raise FlowError("etf_invalid_event", 422)
        members = tuple(identifier(x) for x in v["member_ids"])
        if len(set(members)) != len(members):
            raise FlowError("etf_invalid_event", 422)
        return cls(identifier(v["id"]), members, start, end,
                   day(v["published_date"]) if v["published_date"] is not None else None,
                   object_id(v["source_id"]), text(v["locator"], 1000), text(v["description"], 2000),
                   tuple(text(x) for x in v["subjects"]))


@dataclass(frozen=True)
class Evidence:
    version: str
    confirmed_at: str
    confirmation: str
    sources: tuple[Source, ...]
    adjustments: tuple[Adjustment, ...]
    disclosures: tuple[Disclosure, ...]
    events: tuple[Event, ...]
    hash: str
    raw: dict[str, Any]

    @classmethod
    def parse(cls, raw: Any, member_ids: set[str]) -> Evidence:
        """所有归属和原件引用须明确；无事件覆盖可合法为空但无法计算差分。"""
        v = exact(raw, {"format", "version", "confirmed_at", "confirmation", "sources", "adjustments", "disclosures", "events"})
        if v["format"] != "etf-flow-evidence-v1" or any(not isinstance(v[k], list) for k in ("sources", "adjustments", "disclosures", "events")):
            raise FlowError("etf_invalid_evidence", 422)
        confirmed = instant(v["confirmed_at"])
        sources = tuple(Source.parse(x) for x in v["sources"])
        source_map = {s.object_id: s for s in sources}
        adjustments = tuple(Adjustment.parse(x) for x in v["adjustments"])
        disclosures = tuple(Disclosure.parse(x) for x in v["disclosures"])
        events = tuple(Event.parse(x) for x in v["events"])
        if len(source_map) != len(sources) or any(instant(s.retrieved_at) > confirmed for s in sources):
            raise FlowError("etf_invalid_evidence", 422)
        if any(a.member_id not in member_ids or not set(a.source_ids) <= source_map.keys() or instant(a.confirmed_at) > confirmed for a in adjustments):
            raise FlowError("etf_invalid_evidence_reference", 422)
        for records in (disclosures, events):
            if len({x.id for x in records}) != len(records):
                raise FlowError("etf_duplicate_evidence", 422)
            for item in records:
                ids = {item.member_id} if isinstance(item, Disclosure) else set(item.member_ids)
                if not ids <= member_ids or item.source_id not in source_map:
                    raise FlowError("etf_invalid_evidence_reference", 422)
                source = source_map[item.source_id]
                if item.published_date is not None and item.published_date > instant(source.retrieved_at).astimezone(SHANGHAI).date().isoformat():
                    raise FlowError("etf_invalid_evidence_time", 422)
        return cls(identifier(v["version"]), v["confirmed_at"], text(v["confirmation"], 1000), sources,
                   adjustments, disclosures, events, digest(v), decode(canonical(v)))

    def public(self, on: str, *, member_id: str | None = None, include_later: bool = False) -> dict[str, Any]:
        """公开日与报告期分列；后来披露只在事后对照区显示，不称当时已知。"""
        day(on)
        sources = {s.object_id: s for s in self.sources}
        disclosures = []
        events = []
        for disclosure in self.disclosures:
            if member_id is not None and disclosure.member_id != member_id:
                continue
            source = sources[disclosure.source_id]
            known = disclosure.published_date or instant(source.retrieved_at).astimezone(SHANGHAI).date().isoformat()
            later = known > on
            if later and not include_later:
                continue
            value = asdict(disclosure)
            value["holders"] = [{**asdict(h), "shares": number(h.shares), "percentage": number(h.percentage)} for h in disclosure.holders]
            disclosures.append({**value, "url": source.url, "retrieved_at": source.retrieved_at, "known_date": known,
                                "knowledge": "later_comparison" if later else "published_by_evaluation_day",
                                "publication_unknown": disclosure.published_date is None})
        for event in self.events:
            if member_id is not None and member_id not in event.member_ids:
                continue
            source = sources[event.source_id]
            known = event.published_date or instant(source.retrieved_at).astimezone(SHANGHAI).date().isoformat()
            later = known > on
            if later and not include_later:
                continue
            events.append({**asdict(event), "member_ids": list(event.member_ids), "subjects": list(event.subjects),
                "url": source.url, "retrieved_at": source.retrieved_at, "known_date": known,
                "marker_date": event.occurred_start or known, "marker_kind": "occurrence" if event.occurred_start else "announcement",
                "knowledge": "later_comparison" if later else "published_by_evaluation_day", "publication_unknown": event.published_date is None})
        return {"disclosures": disclosures, "events": events}
