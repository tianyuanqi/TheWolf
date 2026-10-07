"""单次固定指数来源获取子进程；父管道/硬截止由调用方管理。"""

import argparse
import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from pmi.index_contract import SOURCES, source_url
from pmi.snapshot import SnapshotError

MAX_BODY = 8 * 1024 * 1024


def _watch_parent() -> None:
    """父进程消失时退出当前获取子进程，不留下外部连接。"""
    while os.read(sys.stdin.fileno(), 1):
        pass
    os.kill(os.getpid(), signal.SIGTERM)


def fetch_once(url: str, output: Path) -> None:
    """单请求，无重定向/重试，保留代理和TLS，流式与解压后均限8MiB。

    为避免压缩流绕过线速限额，请求identity并明确拒绝压缩响应。
    """
    size = 0
    output.joinpath("receipt.json").write_text(json.dumps({"bytes": 0}))
    with requests.get(url, stream=True, timeout=(5, 15), allow_redirects=False,
                      headers={"User-Agent": "TheWolf-csi300/0.1", "Accept-Encoding": "identity"}) as response:
        if response.status_code != 200:
            raise SnapshotError(f"来源HTTP {response.status_code}，不跟随重定向、不自动重试")
        if response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
            raise SnapshotError("来源压缩响应未准入")
        if int(response.headers.get("Content-Length", "0")) > MAX_BODY:
            raise SnapshotError("来源正文超过8MiB")
        with output.joinpath("original").open("wb") as stream:
            while size < MAX_BODY:
                chunk = response.raw.read(min(8192, MAX_BODY - size), decode_content=False)
                if not chunk:
                    break
                size += len(chunk)
                output.joinpath("receipt.json").write_text(json.dumps({"bytes": size}))
                stream.write(chunk)
            if size == MAX_BODY and response.headers.get("Content-Length") != str(MAX_BODY):
                raise SnapshotError("来源达到8MiB读取上限，无法确认完整正文")
            stream.flush()
            os.fsync(stream.fileno())
    output.joinpath("receipt.json").write_text(json.dumps({"bytes": size, "completed_at": datetime.now(timezone.utc).isoformat()}))


def main() -> None:
    """只接受固定来源和窗口边界，不接受任意URL。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    threading.Thread(target=_watch_parent, daemon=True).start()
    try:
        fetch_once(source_url(args.source, (args.start, args.end)), args.output)
    except (SnapshotError, requests.RequestException, OSError, ValueError) as error:
        message = str(error) if isinstance(error, SnapshotError) else f"source network unavailable ({type(error).__name__})"
        args.output.joinpath("failure.json").write_text(json.dumps({"message": message}))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
