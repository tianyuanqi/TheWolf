"""以独立端口、数据根和应用标识启动一个 Tauri 验证会话。"""

import argparse
import errno
import json
import os
import signal
import socket
import subprocess
import tempfile
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def _port(value: str) -> int:
    """解析非特权回环端口，拒绝无效命令参数。"""
    port = int(value)
    if port < 1024 or port > 65535:
        raise argparse.ArgumentTypeError("端口须在 1024–65535 之间")
    return port


def _is_listening(port: int) -> bool:
    """启动前提示已有验证会话；监听探测不代替服务启动时的端口检查。"""
    with socket.socket() as connection:
        connection.settimeout(0.25)
        result = connection.connect_ex(("127.0.0.1", port))
        if result == 0:
            return True
        if result in (errno.ECONNREFUSED, errno.ETIMEDOUT):
            return False
        raise OSError(result, os.strerror(result))


def main() -> int:
    """仅使用显式指定的隔离数据目录运行开发客户端。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", required=True, type=_port)
    parser.add_argument("--service-port", required=True, type=_port)
    parser.add_argument("--data-root", required=True, type=Path)
    args = parser.parse_args()
    if args.frontend_port == args.service_port:
        parser.error("前端与服务端口必须不同")
    data_root = args.data_root.expanduser().resolve()
    if not data_root.is_dir():
        parser.error("数据根必须是已存在的隔离目录")
    if data_root.is_relative_to(APP_ROOT.parent.parent / ".local-data"):
        parser.error("验证会话不得直接使用项目原始 .local-data；请先准备独立副本")
    for label, port in (("前端", args.frontend_port), ("服务", args.service_port)):
        try:
            occupied = _is_listening(port)
        except OSError as error:
            parser.error(f"无法检查{label}端口 {port}：{error}")
        if occupied:
            parser.error(f"{label}端口 {port} 已被占用；请复用已有窗口或改用另一组端口")

    # 不共享应用标识，避免另一组隔离验证会话被单实例机制合并。
    identifier = f"com.thewolf.qa.p{args.frontend_port}.p{args.service_port}"
    override = {
        "identifier": identifier,
        "build": {
            "devUrl": f"http://127.0.0.1:{args.frontend_port}",
            "beforeDevCommand": (
                "npm run dev -- --host 127.0.0.1 "
                f"--port {args.frontend_port} --strictPort"
            ),
        },
    }
    environment = os.environ.copy()
    environment.update(
        CARGO_TARGET_DIR=str(APP_ROOT / "src-tauri" / "target" /
                             f"qa-{args.frontend_port}-{args.service_port}"),
        WOLF_DEV_PORT=str(args.frontend_port),
        WOLF_SERVICE_PORT=str(args.service_port),
        WOLF_SLICE_DATA_ROOT=str(data_root),
        WOLF_ENABLE_DATA_UPDATE="1",
    )
    with tempfile.TemporaryDirectory(prefix="thewolf-qa-config-") as directory:
        config = Path(directory) / "tauri-qa.json"
        config.write_text(json.dumps(override, ensure_ascii=False), encoding="utf-8")
        process = subprocess.Popen(
            ["npm", "run", "tauri", "--", "dev", "--config", str(config)],
            cwd=APP_ROOT, env=environment, start_new_session=True,
        )
        try:
            return process.wait()
        except KeyboardInterrupt:
            # 终止本会话的 npm、Vite、Tauri 进程组，避免只关闭启动脚本。
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
