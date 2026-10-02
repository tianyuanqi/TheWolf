"""在隔离数据根执行开发服务的本机回环冒烟检查。

从仓库根目录运行，并设置 PYTHONPATH=python/src:python/tests。
程序只在临时目录生成合成测试数据。
"""

import os
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from pmi.snapshot import publish_snapshot, read_snapshot
from test_snapshot import fixture


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        snapshot_id = publish_snapshot(root, fixture())
        pdf_id = read_snapshot(root)["pdf_object_id"]
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.close()
        environment = os.environ.copy()
        environment.update(
            WOLF_SLICE_DATA_ROOT=directory,
            WOLF_SESSION_TOKEN="isolated-integration-token",
            WOLF_ALLOWED_HOST=f"127.0.0.1:{port}",
            WOLF_ENABLE_DATA_UPDATE="1",
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "pmi.api:app", "--host", "127.0.0.1",
             "--port", str(port)],
            env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(80):
                try:
                    urllib.request.urlopen(base + "/api/health", timeout=0.25).read()
                    break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("service did not become ready")
            headers = {"X-Wolf-Session": "isolated-integration-token"}
            request = urllib.request.Request(base + "/api/slice", headers=headers)
            content = urllib.request.urlopen(request, timeout=2).read()
            assert snapshot_id.encode() in content
            request = urllib.request.Request(
                base + f"/api/snapshots/{snapshot_id}/pdf/{pdf_id}", headers=headers)
            assert urllib.request.urlopen(request, timeout=2).read() == fixture().pdf_bytes
            try:
                urllib.request.urlopen(base + "/api/slice", timeout=2)
            except urllib.error.HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError("unauthorized request succeeded")
            update_url = base + "/api/slice/update"
            for body, request_headers, expected in ((b"{}", {}, 401),
                                                    (b'{"url":"http://evil.invalid"}', headers, 422)):
                request = urllib.request.Request(update_url, data=body, headers={**request_headers, "Content-Type": "application/json"})
                try:
                    urllib.request.urlopen(request, timeout=2)
                except urllib.error.HTTPError as error:
                    assert error.code == expected
                else:
                    raise AssertionError("invalid update request succeeded")
            request = urllib.request.Request(update_url, data=b"{}", headers={**headers, "Content-Type": "application/json"})
            job = json.loads(urllib.request.urlopen(request, timeout=2).read())
            assert job["job_id"]
            for _ in range(40):
                state = json.loads(urllib.request.urlopen(urllib.request.Request(update_url, headers=headers), timeout=2).read())
                if state["stage"] == "failed": break
                time.sleep(.05)
            else:
                raise AssertionError("synthetic single announcement must fail before network")
            assert state["job_id"] == job["job_id"]
            assert read_snapshot(root)["snapshot_id"] == snapshot_id
            print("loopback: health 200, snapshot 200, PDF 200, missing token 401")
            print("update: POST 202, GET terminal failure, no-network invalid local evidence, old pointer retained; unauthorized 401, injection 422")
        finally:
            process.terminate()
            process.wait(timeout=5)
        probe = socket.socket()
        try:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
        print("service terminated; loopback port closed")


if __name__ == "__main__":
    main()
