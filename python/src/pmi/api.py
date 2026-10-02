from __future__ import annotations

import os
import secrets
import signal
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from pmi.data_update import start_update, update_status
from pmi.snapshot import SnapshotError, read_pdf, read_snapshot
from pmi.storage import demo_research, document_evidence, initialize_demo_data


def _dev_origin() -> Optional[str]:
    """仅接受显式配置的本机前端端口作为隔离验证来源。"""
    value = os.environ.get("WOLF_DEV_PORT", "")
    if value.isascii() and value.isdecimal() and len(value) <= 5 and 0 < int(value) <= 65535:
        return f"http://127.0.0.1:{value}"
    return None


def _watch_parent_pipe() -> None:
    """父桌面进程异常退出时由管道 EOF 触发服务正常终止。"""
    try:
        while sys.stdin.buffer.read(1):
            pass
    except OSError:
        pass
    os.kill(os.getpid(), signal.SIGTERM)


app = FastAPI(title="TheWolf Local Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in (
        "http://127.0.0.1:5173", "http://127.0.0.1:5174", _dev_origin(),
        "tauri://localhost", "http://tauri.localhost") if origin],
    allow_methods=["GET", "POST"],
    allow_headers=["X-Wolf-Session"],
)


@app.on_event("startup")
def startup() -> None:
    """初始化开发样本，并在桌面托管模式监视父进程管道。"""
    if os.environ.get("WOLF_PARENT_PIPE") == "1":
        threading.Thread(target=_watch_parent_pipe, daemon=True).start()
    if not os.environ.get("WOLF_SLICE_DATA_ROOT"):
        initialize_demo_data()


@app.get("/api/health")
def health() -> dict:
    """返回本地服务存活状态。"""
    return {"status": "ok", "service": "thewolf-local-service", "storage": "sqlite"}


@app.get("/api/demo/research")
def research_demo() -> dict:
    """仅在样本模式返回开发夹具，真实切片模式拒绝混入样本。"""
    if os.environ.get("WOLF_SLICE_DATA_ROOT"):
        raise HTTPException(status_code=404, detail="development fixture is disabled")
    return demo_research()


@app.get("/api/documents/{document_id}/evidence")
def evidence(document_id: str) -> dict:
    """仅在样本模式返回开发公告证据。"""
    if os.environ.get("WOLF_SLICE_DATA_ROOT"):
        raise HTTPException(status_code=404, detail="development fixture is disabled")
    item = document_evidence(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail="document was not found")
    return item


def _slice_root() -> Path:
    """解析显式配置的真实切片数据根，缺失时拒绝真实数据请求。"""
    configured = os.environ.get("WOLF_SLICE_DATA_ROOT")
    if not configured:
        raise HTTPException(status_code=503, detail={"code": "slice_not_configured",
                                                    "message": "真实数据目录未配置"})
    return Path(configured).expanduser()


def _authorized(request: Request, x_wolf_session: Optional[str] = Header(default=None)) -> None:
    """以会话凭据、Host 和 Origin 限制真实快照的本地读取。"""
    expected = os.environ.get("WOLF_SESSION_TOKEN")
    if not expected or not x_wolf_session or not secrets.compare_digest(
        x_wolf_session, expected
    ):
        raise HTTPException(status_code=401, detail={"code": "unauthorized",
                                                    "message": "缺少有效会话凭据"})
    allowed_host = os.environ.get("WOLF_ALLOWED_HOST", "127.0.0.1:8000")
    if request.headers.get("host") != allowed_host:
        raise HTTPException(status_code=403, detail={"code": "bad_host",
                                                    "message": "请求主机不受信任"})
    origin = request.headers.get("origin")
    allowed_origins = {
        "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:1420",
        "tauri://localhost", "http://tauri.localhost"
    }
    dev_origin = _dev_origin()
    if dev_origin:
        allowed_origins.add(dev_origin)
    if origin and origin not in allowed_origins:
        raise HTTPException(status_code=403, detail={"code": "bad_origin",
                                                    "message": "请求来源不受信任"})


@app.get("/api/session/ready", dependencies=[Depends(_authorized)])
def session_ready() -> Response:
    """只对持有本次桌面会话凭据的调用方确认服务及进程身份。"""
    return Response(content='{"status":"ready"}', media_type="application/json",
                    headers={"X-Wolf-Service-Pid": str(os.getpid())})


@app.get("/api/slice", dependencies=[Depends(_authorized)])
def latest_slice() -> dict:
    """返回当前已发布切片；无快照或原件损坏时给出明确错误。"""
    try:
        item = read_snapshot(_slice_root())
    except sqlite3.Error as error:
        raise HTTPException(status_code=409, detail={"code": "storage_unavailable",
                                                      "message": "本地快照数据库不可用，请检查数据目录"}) from error
    except (SnapshotError, OSError, ValueError) as error:
        raise HTTPException(status_code=409, detail={"code": "snapshot_invalid",
                                                      "message": str(error)}) from error
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "slice_empty",
                                                      "message": "尚无已发布的真实数据快照"})
    return item


@app.get("/api/snapshots/{snapshot_id}", dependencies=[Depends(_authorized)])
def fixed_snapshot(snapshot_id: str) -> dict:
    """按固定 ID 读取历史快照，不用当前指针替换旧事实。"""
    try:
        item = read_snapshot(_slice_root(), snapshot_id)
    except sqlite3.Error as error:
        raise HTTPException(status_code=409, detail={"code": "storage_unavailable",
                                                      "message": "本地快照数据库不可用，请检查数据目录"}) from error
    except (SnapshotError, OSError, ValueError) as error:
        raise HTTPException(status_code=409, detail={"code": "snapshot_invalid",
                                                      "message": str(error)}) from error
    if item is None:
        raise HTTPException(status_code=404, detail={"code": "snapshot_not_found",
                                                      "message": "快照不存在"})
    return item


@app.get("/api/snapshots/{snapshot_id}/pdf/{object_id}",
         dependencies=[Depends(_authorized)])
def snapshot_pdf(snapshot_id: str, object_id: str) -> Response:
    """仅返回指定快照引用的公告 PDF，禁止跨快照读取。"""
    try:
        content = read_pdf(_slice_root(), snapshot_id, object_id)
    except sqlite3.Error as error:
        raise HTTPException(status_code=409, detail={"code": "storage_unavailable",
                                                      "message": "本地快照数据库不可用，请检查数据目录"}) from error
    except (SnapshotError, OSError, ValueError) as error:
        raise HTTPException(status_code=409, detail={"code": "object_invalid",
                                                      "message": str(error)}) from error
    return Response(content, media_type="application/pdf",
                    headers={"Cache-Control": "no-store",
                             "Content-Disposition": "inline; filename=announcement.pdf"})


class UpdateRequest(BaseModel):
    """更新不接受客户端来源、目录、证券或时间参数。"""

    model_config = ConfigDict(extra="forbid")


class UpdateStatus(BaseModel):
    """定义本地更新任务阶段、结果和固定快照关联的输出契约。"""

    stage: Literal["idle", "preparing", "fetching_sina", "fetching_szse", "validating", "publishing", "completed", "failed", "interrupted"]
    job_id: Optional[str] = None
    result: Optional[Literal["business_changed", "evidence_changed", "unchanged", "source_not_ready", "failed", "interrupted"]] = None
    enabled: bool = False
    message: Optional[str] = None
    started_at: Optional[str] = None
    observed_at: Optional[str] = None
    last_success_at: Optional[str] = None
    target_start: Optional[str] = None
    target_end: Optional[str] = None
    previous_snapshot_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    added_dates: list[str] = Field(default_factory=list)
    removed_dates: list[str] = Field(default_factory=list)
    revised_dates: list[str] = Field(default_factory=list)


@app.get("/api/slice/update", dependencies=[Depends(_authorized)], response_model=UpdateStatus)
def slice_update_status() -> dict:
    """返回本地检查状态及写入启用状态，轮询不采集上游。"""
    try:
        return {**update_status(_slice_root()), "enabled": os.environ.get("WOLF_ENABLE_DATA_UPDATE") == "1"}
    except (SnapshotError, OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=409, detail={"code": "update_status_invalid", "message": "本地更新状态不可用"}) from error


@app.post("/api/slice/update", dependencies=[Depends(_authorized)], status_code=202, response_model=UpdateStatus)
def slice_update(body: UpdateRequest, request: Request) -> dict:
    """仅在显式启用的服务数据根启动手动更新，拒绝客户端参数注入。"""
    if request.query_params:
        raise HTTPException(status_code=422, detail={"code": "unexpected_parameters", "message": "更新不接受自选参数"})
    if os.environ.get("WOLF_ENABLE_DATA_UPDATE") != "1":
        raise HTTPException(status_code=403, detail={"code": "update_disabled", "message": "此数据根尚未启用更新，请先完成隔离验证或原库切换"})
    try:
        return {**start_update(_slice_root()), "enabled": True}
    except (SnapshotError, OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=409, detail={"code": "update_unavailable", "message": str(error) if isinstance(error, SnapshotError) else "本地更新任务不可用"}) from error
