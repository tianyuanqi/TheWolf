import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pmi.api import app
from pmi.snapshot import publish_snapshot, read_snapshot
from test_snapshot import fixture


async def asgi_get(path: str, headers: dict[str, str], method: str = "GET",
                   body: bytes = b"", query: bytes = b"") -> tuple[int, bytes]:
    """直接调用 ASGI 应用，避免启动真实网络或执行 lifespan。"""
    messages: list[dict] = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": query, "root_path": "", "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8000),
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    await app(scope, receive, send)
    status = next(message["status"] for message in messages
                  if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in messages
                    if message["type"] == "http.response.body")
    return status, body


class SliceApiTests(unittest.TestCase):
    def test_update_rejects_unauthorized_and_injected_requests_without_work(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "WOLF_SLICE_DATA_ROOT": directory, "WOLF_SESSION_TOKEN": "synthetic",
            "WOLF_ALLOWED_HOST": "127.0.0.1:8000", "WOLF_ENABLE_DATA_UPDATE": "1"}), \
                patch("pmi.api.start_update", return_value={"stage": "preparing", "job_id": "fixture"}) as start:
            base = {"host": "127.0.0.1:8000", "x-wolf-session": "synthetic", "content-type": "application/json"}
            for method in ("GET", "POST"):
                for headers, expected in (({"host": base["host"]}, 401),
                                          ({**base, "host": "evil.invalid"}, 403),
                                          ({**base, "origin": "http://evil.invalid"}, 403)):
                    self.assertEqual(asyncio.run(asgi_get("/api/slice/update", headers, method, b"{}"))[0], expected)
            for key in ("url", "data_root", "security", "observed_at"):
                self.assertEqual(asyncio.run(asgi_get("/api/slice/update", base, "POST", json.dumps({key: "injected"}).encode()))[0], 422)
            self.assertEqual(asyncio.run(asgi_get("/api/slice/update", base, "POST", b"{}", b"url=evil"))[0], 422)
            with patch.dict(os.environ, {"WOLF_ENABLE_DATA_UPDATE": "0"}):
                self.assertEqual(asyncio.run(asgi_get("/api/slice/update", base, "POST", b"{}"))[0], 403)
            start.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])
            status, body = asyncio.run(asgi_get("/api/slice/update", base, "POST", b"{}"))
            self.assertEqual(status, 202)
            self.assertEqual(json.loads(body)["job_id"], "fixture")
            start.assert_called_once_with(Path(directory))

    def test_corrupt_database_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "slice.sqlite").write_bytes(b"not a SQLite database")
            old_root = os.environ.get("WOLF_SLICE_DATA_ROOT")
            old_token = os.environ.get("WOLF_SESSION_TOKEN")
            os.environ["WOLF_SLICE_DATA_ROOT"] = directory
            os.environ["WOLF_SESSION_TOKEN"] = "isolated-test-session"
            headers = {"host": "127.0.0.1:8000", "x-wolf-session": "isolated-test-session"}
            try:
                for path in ("/api/slice", "/api/snapshots/" + "a" * 64,
                             "/api/snapshots/" + "a" * 64 + "/pdf/" + "b" * 64):
                    status, body = asyncio.run(asgi_get(path, headers))
                    self.assertEqual(status, 409)
                    self.assertEqual(json.loads(body)["detail"]["code"], "storage_unavailable")
                with patch("pmi.api.read_snapshot",
                           side_effect=sqlite3.OperationalError("database is locked")):
                    status, body = asyncio.run(asgi_get("/api/slice", headers))
                    self.assertEqual(status, 409)
                    self.assertEqual(json.loads(body)["detail"]["code"], "storage_unavailable")
            finally:
                if old_root is None:
                    os.environ.pop("WOLF_SLICE_DATA_ROOT", None)
                else:
                    os.environ["WOLF_SLICE_DATA_ROOT"] = old_root
                if old_token is None:
                    os.environ.pop("WOLF_SESSION_TOKEN", None)
                else:
                    os.environ["WOLF_SESSION_TOKEN"] = old_token

    def test_auth_origin_host_and_object_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            old_root = os.environ.get("WOLF_SLICE_DATA_ROOT")
            old_token = os.environ.get("WOLF_SESSION_TOKEN")
            os.environ["WOLF_SLICE_DATA_ROOT"] = directory
            os.environ["WOLF_SESSION_TOKEN"] = "isolated-test-session"
            try:
                snapshot_id = publish_snapshot(Path(directory), fixture())
                document = read_snapshot(Path(directory))
                base = {"host": "127.0.0.1:8000", "x-wolf-session": "isolated-test-session"}
                self.assertEqual(asyncio.run(asgi_get("/api/slice", {"host": base["host"]}))[0], 401)
                self.assertEqual(asyncio.run(asgi_get("/api/session/ready", {"host": base["host"]}))[0], 401)
                self.assertEqual(asyncio.run(asgi_get("/api/session/ready", base))[0], 200)
                self.assertEqual(asyncio.run(asgi_get("/api/demo/research", base))[0], 404)
                self.assertEqual(asyncio.run(asgi_get("/api/slice", {**base, "host": "evil.example"}))[0], 403)
                self.assertEqual(asyncio.run(asgi_get("/api/slice", {
                    **base, "origin": "https://evil.example"}))[0], 403)
                status, content = asyncio.run(asgi_get("/api/slice", base))
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(content)["snapshot_id"], snapshot_id)
                path = f"/api/snapshots/{snapshot_id}/pdf/{document['pdf_object_id']}"
                status, content = asyncio.run(asgi_get(path, base))
                self.assertEqual((status, content), (200, fixture().pdf_bytes))
                report_pdf = b"%PDF-1.4\nsecond synthetic report"
                expanded = replace(
                    fixture(), batch_id="synthetic-api-with-report",
                    additional_documents=(replace(fixture().document,
                                                  document_id="fixture-report-002"),),
                    additional_pdf_bytes=(report_pdf,))
                expanded_id = publish_snapshot(Path(directory), expanded)
                expanded_snapshot = read_snapshot(Path(directory), expanded_id)
                second_id = expanded_snapshot["documents"][1]["pdf_object_id"]
                status, content = asyncio.run(asgi_get(
                    f"/api/snapshots/{expanded_id}/pdf/{second_id}", base))
                self.assertEqual((status, content), (200, report_pdf))
                self.assertEqual(asyncio.run(asgi_get(
                    f"/api/snapshots/{snapshot_id}/pdf/{second_id}", base))[0], 409)
                self.assertEqual(asyncio.run(asgi_get(
                    f"/api/snapshots/{snapshot_id}/pdf/other", base))[0], 409)
            finally:
                if old_root is None:
                    os.environ.pop("WOLF_SLICE_DATA_ROOT", None)
                else:
                    os.environ["WOLF_SLICE_DATA_ROOT"] = old_root
                if old_token is None:
                    os.environ.pop("WOLF_SESSION_TOKEN", None)
                else:
                    os.environ["WOLF_SESSION_TOKEN"] = old_token


if __name__ == "__main__":
    unittest.main()
