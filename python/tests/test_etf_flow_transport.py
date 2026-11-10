"""有界传输隔离验证：假requests模块仅注入测试子进程，绝不访问金融源。"""
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from etf_flow_fixture import configuration
from pmi.market_data.etf_flow.budget import Budget, Grant, Request
from pmi.market_data.etf_flow.model import FlowError, canonical, decode, digest
from pmi.market_data.storage.etf_store import Store
from pmi.market_data.etf_flow.transport import Transport, receipt
from pmi.market_data.etf_flow.transport_worker import fetch_once


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="etf-transport-test-", dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir(mode=0o700)
        self.store = Store(self.data)
        self.store.initialize()
        now = datetime.now(timezone.utc)
        member = configuration()["pool_versions"][0]["members"][0]
        grant = Grant.parse({"id": "isolated-transport", "confirmation": "仅隔离测试，无真实取数",
            "confirmed_at": (now - timedelta(minutes=1)).isoformat(), "expires_at": (now + timedelta(days=1)).isoformat(),
            "members": [member["id"]], "start": "2026-11-03", "end": "2026-11-04", "domains": ["www.sse.com.cn"],
            "max_requests": 1, "max_bytes": 64, "response_limit": 64, "interval_seconds": 3, "timeout_seconds": 1})
        self.budget = Budget(self.store, grant)
        self.request = Request("shares", member["id"], "2026-11-04", "2026-11-04", member["basis"]["url"])
        with self.store.writer():
            self.budget.initialize()
        self.stop = threading.Event()
        self.transport = Transport(self.budget, self.stop)

    def tearDown(self):
        self.tmp.cleanup()
        self.assertFalse(self.root.exists())

    def fake_module(self, body):
        (self.root / "requests.py").write_text(body)
        return patch.dict(os.environ, {"PYTHONPATH": str(self.root) + os.pathsep + os.environ.get("PYTHONPATH", "")})

    def test_real_child_success_and_persistent_receipt(self):
        fake = '''import io
class Raw(io.BytesIO):
    def read(self, n, decode_content=False): return super().read(n)
class Response:
    status_code=200
    headers={"Content-Length":"2"}
    raw=Raw(b"{}")
    def __enter__(self): return self
    def __exit__(self,*args): pass
def get(url, **kwargs):
    assert kwargs["allow_redirects"] is False
    assert kwargs["headers"]["Accept-Encoding"] == "identity"
    return Response()
'''
        with self.fake_module(fake), self.store.writer():
            original = self.transport.fetch(self.request, digest("operation"))
        self.assertEqual(original.raw, b"{}")
        self.assertEqual(self.store.get(original.object_id), b"{}")
        self.assertEqual(self.budget.usage()["requests"], 1)
        self.assertEqual(self.budget.usage()["reserved_bytes"], 64)
        self.assertEqual(self.store.get_json(original.receipt_id)["worker_receipt"]["status"], 200)
        self.assertEqual(len(list((self.data / "incoming").iterdir())), 2)

    def test_total_deadline_includes_blocked_get_and_reaps_child(self):
        started = time.monotonic()
        with self.fake_module('import time\ndef get(*a, **kw): time.sleep(60)\n'), self.store.writer():
            with self.assertRaises(FlowError):
                self.transport.fetch(self.request, digest("operation"))
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(self.budget.usage()["requests"], 1)
        self.assertEqual(self.budget.usage()["reserved_bytes"], 64)
        self.assertFalse(self.budget.read()[1]["attempts"][0]["success"])
        with Store(self.data).writer():
            pass  # 子进程已经退出，继承的flock不能残留。

    def test_parent_eof_stops_real_worker_without_waiting_network_timeout(self):
        with self.fake_module('import time\ndef get(*a, **kw): time.sleep(60)\n'), self.store.writer():
            attempt = "a" * 32
            fds = [self.store.create_spool(attempt, suffix) for suffix in ("raw", "receipt")]
            child = None
            try:
                child = subprocess.Popen([sys.executable, "-B", "-m", "pmi.market_data.etf_flow.transport_worker",
                    self.request.url, "64", "30", *map(str, fds)], stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    pass_fds=(*fds, self.store.inherited_lock()))
                child.stdin.close()
                self.assertEqual(child.wait(timeout=3), 2)
            finally:
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait(timeout=2)
                for fd in fds:
                    os.close(fd)

    def test_inherited_lock_blocks_false_recovery_after_parent_releases(self):
        child = None
        try:
            with self.store.writer():
                child = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(30)"],
                    pass_fds=(self.store.inherited_lock(),))
            with self.assertRaises(FlowError):
                with Store(self.data).writer():
                    self.fail("网络子进程尚未结束时不应允许恢复")
        finally:
            if child is not None:
                child.kill()
                child.wait(timeout=2)
        with Store(self.data).writer():
            pass

    def run_response(self, response):
        paths = [self.root / "raw", self.root / "metadata"]
        fds = [os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600) for path in paths]
        try:
            with patch("requests.get", return_value=response):
                fetch_once(self.request.url, 64, 1, *fds)
        finally:
            for fd in fds:
                os.close(fd)
        return paths[0].read_bytes(), decode(paths[1].read_bytes())

    def test_http_encoding_length_and_partial_body_stop_without_retry(self):
        class Raw(io.BytesIO):
            def read(self, n, decode_content=False):
                return super().read(n)
        class Response:
            def __init__(self, status=200, headers=None, body=b"{}"):
                self.status_code, self.headers, self.raw = status, headers or {}, Raw(body)
            def __enter__(self): return self
            def __exit__(self, *args): pass
        for response, code, body in [
            (Response(status=429), "etf_source_http_rejected", b""),
            (Response(status=302), "etf_source_http_rejected", b""),
            (Response(headers={"Content-Encoding": "gzip"}), "etf_source_encoding_rejected", b""),
            (Response(headers={"Content-Length": "65"}), "etf_source_length_rejected", b""),
            (Response(headers={"Content-Length": "3"}), "etf_source_incomplete_body", b"{}"),
            (Response(body=b"x" * 80), "etf_source_body_limit", b"x" * 64),
        ]:
            with self.subTest(code=code):
                raw, result = self.run_response(response)
                self.assertEqual(result["code"], code)
                self.assertFalse(result["complete"])
                self.assertEqual(raw, body)

    def test_explicit_recovery_keeps_partial_and_unknown_charge(self):
        operation = digest("interrupted")
        with self.store.writer():
            attempt = self.budget.charge(self.request, operation)
            fd = self.store.create_spool(attempt, "raw")
            os.write(fd, b"partial")
            os.close(fd)
            self.transport.recover(operation)
            self.transport.recover(operation)
        row = self.budget.read()[1]["attempts"][0]
        self.assertIsNone(row["success"])
        self.assertIsNone(row["actual_bytes"])
        self.assertIsNotNone(row["closed_at"])
        self.assertEqual(self.store.get(digest_bytes(b"partial")), b"partial")
        self.assertEqual(self.budget.usage()["requests"], 1)

    def test_receipt_rejects_partial_wrong_size_and_time(self):
        self.assertIsNone(receipt(b"{", 2, "2026-11-05T00:00:00Z"))
        v = {"status": 200, "bytes": 2, "complete": True, "code": None, "finished_at": "2026-11-04T00:00:00Z"}
        self.assertIsNone(receipt(canonical(v), 2, "2026-11-05T00:00:00Z"))
        v["finished_at"] = "2026-11-05T00:00:00Z"
        self.assertIsNone(receipt(canonical(v), 3, v["finished_at"]))


def digest_bytes(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()
