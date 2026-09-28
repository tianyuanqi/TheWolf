"""用隔离回环服务验证桌面父进程退出后子服务自行关闭。"""

import os
import socket
import subprocess
import sys
import tempfile
import time


def main() -> None:
    """以父进程管道 EOF 模拟桌面异常退出，并检查端口释放。"""
    with tempfile.TemporaryDirectory() as directory:
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        environment = os.environ.copy()
        environment.update(
            WOLF_SLICE_DATA_ROOT=directory,
            WOLF_PARENT_PIPE="1",
            WOLF_SESSION_TOKEN="isolated-parent-probe",
            WOLF_ALLOWED_HOST=f"127.0.0.1:{port}",
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "pmi.api:app", "--host", "127.0.0.1",
             "--port", str(port)],
            env=environment, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(80):
                with socket.socket() as connection:
                    if connection.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)
            else:
                raise AssertionError("isolated service did not start")
            assert process.stdin is not None
            process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired as error:
                raise AssertionError("service outlived its desktop parent pipe") from error
            with socket.socket() as connection:
                assert connection.connect_ex(("127.0.0.1", port)) != 0
            print("parent pipe closed; child exited; loopback port released")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
