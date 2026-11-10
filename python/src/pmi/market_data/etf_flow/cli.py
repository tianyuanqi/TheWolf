"""ETF显式初始化/既有原件导入；只供逐次获准的本机操作，无隐式联网或启用。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from .budget import Budget, Grant
from pmi.market_data.storage.etf_cache import Cache
from .model import Configuration, FlowError, canonical, decode, digest, exact, instant, integer, object_id, text
from .sources import parse, request_for, verify_nav_pages
from pmi.market_data.storage.etf_store import MAX_OBJECT_BYTES, Store, location
from .transport import Original


def read_file(path: Path, limit: int = MAX_OBJECT_BYTES) -> bytes:
    """只读明确给定的现存普通文件，有限读取并核对文件未被替换。"""
    location(path, directory=False)
    stat = path.stat()
    if stat.st_size > limit:
        raise FlowError("etf_import_file_too_large", 422)
    from pmi.market_data.read_only import read_bytes
    raw = read_bytes(path, limit + 1)
    after = path.stat()
    if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(raw) > limit:
        raise FlowError("etf_import_file_changed")
    return raw


def initialize(root: Path, grant_path: Path, authorization: str) -> dict:
    """仅初始化新空根及一次性授权账本；不发布输入、启用成员或启动服务。"""
    text(authorization, 1000)
    grant = Grant.parse(decode(read_file(grant_path, 8 * 1024 * 1024)))
    store = Store(root)
    store.initialize()
    with store.writer():
        budget = Budget(store, grant)
        budget.initialize()
        record = store.put_json({"format": "etf-flow-initialization-v1", "scope": store.scope,
            "grant_id": grant.id, "authorization": authorization, "at": datetime.now(timezone.utc).isoformat()})
    return {"scope": store.scope, "record_id": record, "grant_id": grant.id, "published": False}


def add_grant(root: Path, grant_path: Path, authorization: str) -> dict:
    """追加另一次明确授权，不删除、改写或复位已用额度；未决操作先恢复。"""
    text(authorization, 1000)
    store = Store(root)
    grant = Grant.parse(decode(read_file(grant_path, 8 * 1024 * 1024)))
    with store.writer():
        _no_unresolved(store)
        Budget(store, grant).initialize()
        record = store.put_json({"format": "etf-flow-grant-authorization-v1", "grant_id": grant.id,
            "authorization": authorization, "at": datetime.now(timezone.utc).isoformat()})
    return {"grant_id": grant.id, "record_id": record, "published": False}


def _no_unresolved(store: Store) -> None:
    """CLI和HTTP使用同一持久占位，不能绕过未恢复的更新改变输入。"""
    key = digest({"format": "etf-flow-operations-v1", "scope": store.scope})
    reference, value = store.journal(key)
    if reference is not None:
        value = exact(value, {"operations"})
        if not isinstance(value["operations"], list) or any(row.get("state") not in {"completed", "failed", "interrupted"}
                                                        or row.get("lease_closed") is not True for row in value["operations"]):
            raise FlowError("etf_unresolved_operation")


def import_originals(root: Path, configuration: Path, manifest_path: Path, authorization: str) -> dict:
    """导入经授权复用的已取得原件；重新解析来源字段，不接收人工填写的金融序列。"""
    text(authorization, 1000)
    config = Configuration.parse(decode(read_file(configuration, 8 * 1024 * 1024)))
    manifest = exact(decode(read_file(manifest_path, 8 * 1024 * 1024)), {"format", "revision", "requests", "evidence_originals"})
    if manifest["format"] != "etf-flow-import-v1" or not isinstance(manifest["requests"], list) or not isinstance(manifest["evidence_originals"], list):
        raise FlowError("etf_invalid_import", 422)
    from .model import identifier
    if manifest["revision"] is not None:
        identifier(manifest["revision"])
    store = Store(root)
    members = {m.id: m for p in config.pools for m in p.members}
    cache = Cache(store, manifest["revision"], config)
    checked, evidence = [], []
    keys = set()
    # 先全部验证文件/hash/字段；无效清单不能部分写入缓存。
    for item in manifest["requests"]:
        value = exact(item, {"member_id", "kind", "start", "end", "page", "path", "object_id", "retrieved_at"})
        member = members.get(value["member_id"])
        if member is None or instant(value["retrieved_at"]) > datetime.now(timezone.utc):
            raise FlowError("etf_invalid_import", 422)
        request = request_for(member, value["kind"], value["start"], value["end"], page=integer(value["page"], 1))
        if request.key in keys:
            raise FlowError("etf_duplicate_import", 422)
        keys.add(request.key)
        raw = read_file(Path(value["path"]))
        if hashlib.sha256(raw).hexdigest() != object_id(value["object_id"]):
            raise FlowError("etf_import_hash_mismatch")
        parsed = parse(member, request, raw, value["object_id"], value["retrieved_at"])
        checked.append((request, raw, value["object_id"], value["retrieved_at"], parsed))
    for item in manifest["evidence_originals"]:
        value = exact(item, {"path", "object_id"})
        raw = read_file(Path(value["path"]))
        if hashlib.sha256(raw).hexdigest() != object_id(value["object_id"]):
            raise FlowError("etf_import_hash_mismatch")
        evidence.append(raw)
    nav = {}
    for request, _, _, _, parsed in checked:
        if request.kind == "nav":
            nav.setdefault((request.member_id, request.start, request.end), []).append(parsed)
    for (_, start, end), pages in nav.items():
        verify_nav_pages(tuple(sorted(pages, key=lambda p: p.page)), start, end)
    with store.writer():
        _no_unresolved(store)
        cache.check_configuration()
        for request, _, source, _, _ in checked:
            prior = cache.response(request)
            if prior is not None and prior["object_id"] != source:
                raise FlowError("etf_import_revision_required")
        cache.bind_configuration()
        imported, reused = [], 0
        for request, raw, source, retrieved, parsed in checked:
            prior = cache.response(request)
            if prior is not None:
                reused += 1
                imported.extend(parsed.rows)  # 上次若在原件回执后中断，也能补全已验证输入缓存。
                continue
            store.put(raw)
            receipt = store.put_json({"format": "etf-flow-import-receipt-v1", "object_id": source, "request_key": request.key,
                "code": None, "retrieved_at": retrieved, "authorization": authorization, "imported_at": datetime.now(timezone.utc).isoformat()})
            cache.save_response(Original(request, "import", source, raw, retrieved, receipt))
            imported.extend(parsed.rows)
        cache.save_inputs(tuple(imported))
        evidence_ids = [store.put(raw) for raw in evidence]
        record = store.put_json({"format": "etf-flow-import-record-v1", "manifest_hash": digest(manifest),
            "authorization": authorization, "at": datetime.now(timezone.utc).isoformat(),
            "source_ids": [row[2] for row in checked], "evidence_ids": evidence_ids, "reused_requests": reused})
    return {"record_id": record, "imported_requests": len(checked) - reused, "reused_requests": reused,
            "evidence_count": len(evidence), "published": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initialize", "add-grant", "import-originals"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--grant", type=Path)
    parser.add_argument("--configuration", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.action in {"initialize", "add-grant"}:
            if args.grant is None or args.configuration is not None or args.manifest is not None:
                raise FlowError("etf_invalid_cli_options", 422)
            result = (initialize if args.action == "initialize" else add_grant)(args.root, args.grant, args.authorization)
        else:
            if args.configuration is None or args.manifest is None or args.grant is not None:
                raise FlowError("etf_invalid_cli_options", 422)
            result = import_originals(args.root, args.configuration, args.manifest, args.authorization)
        print(canonical(result).decode())
    except (FlowError, OSError, ValueError) as error:
        parser.error(error.code if isinstance(error, FlowError) else "etf_local_operation_failed")


if __name__ == "__main__":
    main()
