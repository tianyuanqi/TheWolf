"""隔离合成指数真实回环消费者与父管道退出，不访问金融来源。"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from pmi.index_contract import build_manifest
from pmi.index_snapshot import publish, read_snapshot
from pmi.writer_lock import writer_lock
from test_index import DAYS, originals, state
from test_data_update import old_snapshot


def main() -> None:
    """检查固定视图、原件、权限/输入边界，随后关闭父管道并核对端口。"""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        old_id = old_snapshot(root)
        items = originals()
        with writer_lock(root):
            snapshot_id = publish(root, build_manifest(DAYS, items), items, state())
        index = read_snapshot(root)
        listener = socket.socket(); listener.bind(("127.0.0.1", 0)); port = listener.getsockname()[1]; listener.close()
        environment = {**os.environ, "WOLF_SLICE_DATA_ROOT": str(root), "WOLF_SESSION_TOKEN": "synthetic-index-loopback",
                       "WOLF_ALLOWED_HOST": f"127.0.0.1:{port}", "WOLF_PARENT_PIPE": "1", "WOLF_ENABLE_INDEX_UPDATE": "0"}
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "pmi.api:app", "--host", "127.0.0.1", "--port", str(port)],
                                   env=environment, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        headers = {"X-Wolf-Session": environment["WOLF_SESSION_TOKEN"]}
        # 回环请求明确不使用外部代理，金融来源进程并未启动。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path, expected=200, custom_headers=None, body=None):
            req = urllib.request.Request(base + path, data=body, headers=custom_headers if custom_headers is not None else headers)
            try:
                with opener.open(req, timeout=2) as response:
                    assert response.status == expected
                    return json.loads(response.read())
            except urllib.error.HTTPError as error:
                assert error.code == expected, (path, error.code, expected)
                return None
        try:
            for _ in range(80):
                try:
                    request("/api/health"); break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(.1)
            else:
                raise AssertionError("service not ready")
            path = "/api/indices/000300"
            assert request(path)["snapshot_id"] == snapshot_id
            assert request(path + "/snapshots/" + snapshot_id) == request(path)
            for item in index["evidence"]:
                evidence = request(path + f"/snapshots/{snapshot_id}/evidence/{item['object_id']}")
                assert evidence["rows"][0]["open"] == "100.00"
                assert evidence["snapshot_id"] == snapshot_id
            assert request("/api/slice")["snapshot_id"] == old_id
            request(path, 401, {})
            request(path, 403, {**headers, "Host": "evil.invalid"})
            request(path, 403, {**headers, "Origin": "https://evil.invalid"})
            request(path + "/snapshots/invalid", 422)
            request(path + f"/snapshots/{snapshot_id}/evidence/" + "0" * 64, 404)
            request(path + "/update", 403, {**headers, "Content-Type": "application/json"}, b"{}")
            request(path + "/update?date=x", 422, {**headers, "Content-Type": "application/json"}, b"{}")
            request(path + "/update", 422, {**headers, "Content-Type": "application/json"}, b'{"url":"https://evil.invalid"}')
            assert not (root / "indices/csi000300/network-ledger.jsonl").exists()
            print("index loopback: current/fixed/evidence/legacy 200; token401, host/origin403, IDs422/404, disabled403, input422; no source requests")
            process.stdin.close(); process.wait(timeout=3)
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", port)) != 0
            print("index service parent EOF: exit and port closed")
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


if __name__ == "__main__":
    main()
