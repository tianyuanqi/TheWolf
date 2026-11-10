"""单次请求子进程；总期限和父存活监视包含DNS等待，不安装或改动网络环境。"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import threading

from .model import FlowError, canonical, source_url


def write(fd: int, value: bytes) -> None:
    pending = memoryview(value)
    while pending:
        count = os.write(fd, pending)
        if count <= 0:
            raise OSError("short_write")
        pending = pending[count:]


def fetch_once(url: str, limit: int, timeout: int, output: int, metadata: int) -> bool:
    """流式限制的是接收正文，不解压、不跳转、不重试，HTTP失败即停止。"""
    import requests
    size, status, code = 0, None, None
    try:
        source_url(url)
        from urllib.parse import urlsplit
        referer = "https://www.sse.com.cn/" if urlsplit(url).hostname == "query.sse.com.cn" else "https://fund.eastmoney.com/"
        with requests.get(url, stream=True, timeout=(min(5, timeout), timeout), allow_redirects=False,
                          headers={"User-Agent": "TheWolf-etf-flow/1", "Accept": "application/json",
                                   "Accept-Encoding": "identity", "Referer": referer}) as response:
            status = response.status_code
            if status != 200:
                raise FlowError("etf_source_http_rejected")
            if response.headers.get("Content-Encoding", "identity").strip().lower() not in ("", "identity"):
                raise FlowError("etf_source_encoding_rejected")
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isascii() or not length.isdigit() or int(length) > limit):
                raise FlowError("etf_source_length_rejected")
            while size < limit:
                chunk = response.raw.read(min(8192, limit - size), decode_content=False)
                if not chunk:
                    break
                write(output, chunk)
                size += len(chunk)
            if size == limit and length != str(limit):
                raise FlowError("etf_source_body_limit")
            if length is not None and size != int(length):
                raise FlowError("etf_source_incomplete_body")
    except FlowError as error:
        from .transport import ERRORS
        code = error.code if error.code in ERRORS else "etf_source_network_error"
    except Exception:
        code = "etf_source_network_error"
    os.fsync(output)
    write(metadata, canonical({"status": status, "bytes": size, "complete": code is None, "code": code,
                               "finished_at": datetime.now(timezone.utc).isoformat()}))
    os.fsync(metadata)
    return code is None


def _watch_parent() -> None:
    try:
        while os.read(sys.stdin.fileno(), 1):
            pass
    finally:
        os._exit(2)


def main() -> None:
    # 两个监视器在导入网络库前启动，父退出或期限到达都会释放继承锁。
    url, limit, timeout, output, metadata = sys.argv[1:]
    limit, timeout, output, metadata = int(limit), int(timeout), int(output), int(metadata)
    if not 1 <= limit <= 8 * 1024 * 1024 or not 1 <= timeout <= 30:
        raise SystemExit(2)
    threading.Thread(target=_watch_parent, daemon=True).start()
    watchdog = threading.Timer(timeout, lambda: os._exit(3))
    watchdog.daemon = True
    watchdog.start()
    raise SystemExit(0 if fetch_once(url, limit, timeout, output, metadata) else 1)


if __name__ == "__main__":
    main()
