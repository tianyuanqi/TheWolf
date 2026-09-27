from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from pmi.snapshot import SnapshotError, read_pdf, read_snapshot
from pmi.storage import demo_research, document_evidence, initialize_demo_data


app = FastAPI(title="TheWolf Local Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "tauri://localhost",
                   "http://tauri.localhost"],
    allow_methods=["GET"],
    allow_headers=["X-Wolf-Session"],
)


@app.on_event("startup")
def startup() -> None:
    """仅在未配置真实切片根时初始化开发样本。"""
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
    if origin and origin not in {
        "http://127.0.0.1:5173", "http://localhost:1420",
        "tauri://localhost", "http://tauri.localhost"
    }:
        raise HTTPException(status_code=403, detail={"code": "bad_origin",
                                                    "message": "请求来源不受信任"})


@app.get("/api/slice", dependencies=[Depends(_authorized)])
def latest_slice() -> dict:
    """返回当前已发布切片；无快照或原件损坏时给出明确错误。"""
    try:
        item = read_snapshot(_slice_root())
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
    except (SnapshotError, OSError, ValueError) as error:
        raise HTTPException(status_code=409, detail={"code": "object_invalid",
                                                      "message": str(error)}) from error
    return Response(content, media_type="application/pdf",
                    headers={"Cache-Control": "no-store",
                             "Content-Disposition": "inline; filename=announcement.pdf"})
