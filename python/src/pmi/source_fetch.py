"""为更新任务提供可终止的单次白名单获取子进程，不直接写数据根。"""

import argparse
import json
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

from pmi.sina_slice import SINA_URL, SZSE_PARAMS, SZSE_URL, _fetch_original
from pmi.snapshot import SnapshotError


def _watch_parent() -> None:
    """父进程退出关闭管道时立即停止网络获取，避免遗留来源进程。"""
    # 使用无缓冲系统读取，避免正常解释器退出与 daemon 线程争夺 stdin 缓冲锁。
    while os.read(sys.stdin.fileno(), 1):
        pass
    os.kill(os.getpid(), signal.SIGTERM)


def main() -> None:
    """仅获取一个固定行情来源，结果及完成时刻写入父进程的临时目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("sina", "szse"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    threading.Thread(target=_watch_parent, daemon=True).start()
    url, params = (SINA_URL, None) if args.source == "sina" else (SZSE_URL, SZSE_PARAMS)
    try:
        content = _fetch_original(url, params)
    except (SnapshotError, requests.RequestException) as error:
        message = str(error) if isinstance(error, SnapshotError) else f"source network unavailable ({type(error).__name__})"
        (args.output / "failure.json").write_text(json.dumps({"message": message}))
        raise SystemExit(1) from error
    (args.output / "original").write_bytes(content)
    (args.output / "receipt.json").write_text(json.dumps({"completed_at": datetime.now(timezone.utc).isoformat()}))


if __name__ == "__main__":
    main()
