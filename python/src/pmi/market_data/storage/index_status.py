"""指数状态和观察的纯校验，沿用既有金融/时间约束，不执行存储I/O。"""
from __future__ import annotations
from datetime import date, datetime
import json
import re
from typing import TypedDict
from pmi.market_data import SnapshotError
from pmi.market_data.index_catalog import IndexDefinition
from pmi.market_data.index_series_contract import Original, SeriesManifest, canonical, digest, utc
ACTIVE = frozenset({"preparing", "fetching_csindex", "fetching_cnindex", "fetching_eastmoney", "validating", "publishing"})
TERMINAL = frozenset({"idle", "completed", "failed", "interrupted"})


class UpdateState(TypedDict):
    """落盘任务状态；enabled 仅由公开门面注入。"""

    index_id: str
    job_id: str | None
    trigger: str | None
    stage: str
    result: str | None
    started_at: str | None
    finished_at: str | None
    target_start: str | None
    target_end: str | None
    previous_snapshot_id: str | None
    snapshot_id: str | None
    observation_id: str | None
    last_success_at: str | None
    added_dates: list[str]
    revised_dates: list[str]
    message: str
    differences: list[dict[str, str]]


class SourceReceipt(TypedDict):
    """来源原件的独立观察时间；不代表来源发布时刻。"""

    source: str
    url: str
    started_at: str
    completed_at: str
    object_id: str
    published_at: None


class Retrieval(TypedDict):
    """快照观察与内容分离，首次观察引用保持不变。"""

    index_id: str
    snapshot_id: str
    sources: list[SourceReceipt]
    observed_at: str


class SeriesSnapshot(SeriesManifest):
    """已完整重放的 manifest 加固定观察身份。"""

    snapshot_id: str
    observation_id: str
    retrieval: Retrieval


def validate_id(value: str) -> None:
    """仅准入内容 hash，禁止将外部字符串解释为文件路径。"""
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SnapshotError("invalid_object_id")


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError("duplicate_local_json_member")
        result[key] = value
    return result


def load_json(content: bytes | str) -> dict:
    """只接受对象及唯一成员；本地损坏不宽容解析。"""
    try:
        value = json.loads(content, object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise SnapshotError("invalid_local_json") from error


class PublicationUncertain(SnapshotError):
    """正式建名已发生但同步或最终核验未确认；必须保留副本并报告 unknown。"""


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(utc(value).replace("Z", "+00:00"))


def _receipt(index: IndexDefinition, snapshot_id: str, originals: tuple[Original, ...]) -> Retrieval:
    sources = [{"source": item.source, "url": item.url, "started_at": utc(item.started_at),
                "completed_at": utc(item.completed_at), "object_id": digest(item.content), "published_at": None} for item in originals]
    return {"index_id": index.index_id, "snapshot_id": snapshot_id, "sources": sources,
            "observed_at": max((item["completed_at"] for item in sources), key=_instant)}


def idle_state(index: IndexDefinition) -> UpdateState:
    """返回新字典，避免实例间共享状态。"""
    return {"index_id": index.index_id, "job_id": None, "trigger": None, "stage": "idle", "result": None,
            "started_at": None, "finished_at": None, "target_start": None, "target_end": None,
            "previous_snapshot_id": None, "snapshot_id": None, "observation_id": None, "last_success_at": None,
            "added_dates": [], "revised_dates": [], "message": "尚无指数更新任务", "differences": []}


def _validate_state(state: dict, index: IndexDefinition) -> None:
    """落盘和重读使用同一精确状态边界，损坏数据不能变成业务结果。"""
    try:
        if (set(state) != set(idle_state(index)) or state["index_id"] != index.index_id
                or state["stage"] not in ACTIVE | TERMINAL
                or state["trigger"] not in {None, "manual", "startup"}
                or state["result"] not in {None, "business_changed", "evidence_changed", "unchanged", "source_not_ready", "failed", "interrupted"}
                or not isinstance(state["message"], str)):
            raise ValueError("shape")
        job = state["job_id"]
        if state["stage"] != "idle" and (not isinstance(job, str) or not job.isascii() or not 1 <= len(job) <= 128):
            raise ValueError("job")
        for key in ("previous_snapshot_id", "snapshot_id", "observation_id"):
            if state[key] is not None:
                validate_id(state[key])
        for key in ("started_at", "finished_at", "last_success_at"):
            if state[key] is not None:
                utc(state[key])
        for key in ("target_start", "target_end"):
            if state[key] is not None and date.fromisoformat(state[key]).isoformat() != state[key]:
                raise ValueError("date")
        for key in ("added_dates", "revised_dates"):
            if not isinstance(state[key], list) or any(date.fromisoformat(day).isoformat() != day for day in state[key]):
                raise ValueError("dates")
        if not isinstance(state["differences"], list):
            raise ValueError("differences")
        for difference in state["differences"]:
            if (not isinstance(difference, dict) or set(difference) != {"date", "field", "official_raw", "comparison_value", "eastmoney_raw"}
                    or any(not isinstance(value, str) for value in difference.values())
                    or difference["field"] not in {"open", "high", "low", "close"}
                    or date.fromisoformat(difference["date"]).isoformat() != difference["date"]):
                raise ValueError("difference")
    except (ValueError, TypeError, KeyError) as error:
        raise SnapshotError("invalid_index_status") from error


def _validate_job_state(state: dict, index: IndexDefinition, job_id: str, snapshot_id: str, receipt: dict) -> None:
    """核验已完整重放观察所对应的任务，供全库存与单 job 两条读路径共用。"""
    _validate_state(state, index)
    if (state["job_id"] != job_id or state["snapshot_id"] != snapshot_id or state["stage"] != "completed"
            or receipt["snapshot_id"] != snapshot_id or digest(canonical(receipt)) != state["observation_id"]):
        raise SnapshotError("committed_job_identity_mismatch")
    if (state["last_success_at"] != receipt["observed_at"] or state["finished_at"] is None
            or state["started_at"] is None or _instant(state["finished_at"]) < _instant(state["started_at"])
            or _instant(state["finished_at"]) < _instant(receipt["observed_at"])):
        raise SnapshotError("committed_observation_time_mismatch")
