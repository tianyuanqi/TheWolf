"""总览端到端性能基准：三年合成行情、真实HTTP与浏览器，禁止外网。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[2]


def network_guard(event: str, args: tuple) -> None:
    """包括子服务在内只允许本机连接，不以模拟HTTP代替读取链。"""
    if event == "socket.connect" and isinstance(args[1], tuple):
        if args[1][0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("性能基准禁止连接外网")


def configuration(root: Path, backend: int, frontend: int):
    from pmi.service_config import ServiceConfig
    from pmi.market_data.activity.model import Options
    return ServiceConfig(root / "data", backend, (f"http://127.0.0.1:{frontend}",),
                         index_max_attempts=0, index_max_bytes=0,
                         activity_options=Options(root / "data", max_attempts=0, max_bytes=0))


def serve(root: Path, backend: int, frontend: int) -> None:
    """冷进程直接启动实际应用；只记录阶段时长，不预读或替换用例。"""
    import uvicorn
    import pmi.api as api
    from unittest.mock import patch
    actual = api._dispatch

    def measured(boundary, operation, paths, query, updates):
        started = time.perf_counter()
        response = actual(boundary, operation, paths, query, updates)
        with (root / "http-timings.jsonl").open("a") as out:
            out.write(json.dumps({"operation": operation, "paths": paths,
                                  "seconds": time.perf_counter() - started,
                                  "bytes": len(response.body), "status": response.status_code}) + "\n")
        return response

    with patch.object(api, "_dispatch", measured):
        uvicorn.run(api.create_app(configuration(root, backend, frontend)), host="127.0.0.1", port=backend,
                    access_log=False, log_level="warning")


def seed_complete(root: Path) -> None:
    """性能样本使用完整三市；缺日反例由功能测试另测，不用失败空值计完整。"""
    from datetime import datetime
    from periodic_fixture import seed
    from test_three_market import original
    from pmi.market_data import MarketData
    from pmi.market_data.activity import three_market
    from pmi.market_data.activity.model import MARKET, TWO_MARKET, Options, canonical, digest
    from pmi.market_data.index_history_calendar import complete_window
    seed(root)
    data = MarketData(root / "data", {}, activity_options=Options(root / "data"))
    try:
        runtime = data._activity_runtime
        window = complete_window(datetime.fromisoformat("2026-10-29T07:00:00+08:00"))
        with runtime.store.lock(write=True):
            retained, _ = runtime._market_inputs(TWO_MARKET, window, refresh_missing=False)
            items = [*retained.values(), *(original("bse", day) for day in window.dates)]
            manifest = three_market.manifest(window, items)
            operation = {"series_id": MARKET, "request_id": "perf-seed", "config_id": "fixture", "instance_id": "fixture",
                         "target": window.anchor_date, "signature": digest({"synthetic": True}), "state": "preparing",
                         "activity_id": None, "reason": None, "recovered_from_instance": None, "observation_id": None}
            runtime.store.publish(manifest, {x.object_id: x.content for x in items}, None, operation,
                                  {"series_id": MARKET, "sources": [{"source": x.source, "object_id": x.object_id, "url": x.url,
                                   "started_at": x.started_at, "completed_at": x.completed_at, "published_at": None} for x in items]})
            runtime.store.write(("operations", "perf-seed.json"), canonical(runtime.store.current(MARKET, window.anchor_date)["operation"]))
    finally:
        data.close_updates()


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def opened(number: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", number)) == 0


@contextmanager
def process(command: list[str], root: Path, label: str, env: dict):
    """只回收本次启动的进程组；失败同样等待退出并保存退出码。"""
    with (root / (label + ".log")).open("wb") as out:
        child = subprocess.Popen(command, cwd=REPO, env=env, stdout=out, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            yield child
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            with (root / "processes.jsonl").open("a") as log:
                log.write(json.dumps({"label": label, "pid": child.pid, "exit": child.returncode}) + "\n")


def main(parent: Path, samples: int, built: bool) -> None:
    """真实浏览器计时，服务首次只等TCP就绪；准备不预热金融读取。"""
    from http_test_support import disk
    if not parent.is_dir() or parent.is_symlink() or parent.resolve() != parent or not str(parent).startswith("/private/tmp/wolf-overview-perf-"):
        raise ValueError("必须显式提供本次独占性能临时根")
    root = Path(tempfile.mkdtemp(prefix="browser-", dir=parent))
    print(root, flush=True)
    seed_complete(root)
    before = {name: disk(root / name) for name in ("data", "activity")}
    backend, frontend = port(), port()
    while backend == frontend:
        frontend = port()
    config = configuration(root, backend, frontend)
    for name, descriptor in (("base", config.public_descriptor()), ("index", config.public_index_descriptor()),
                             ("activity", config.public_activity_descriptor())):
        (root / (name + ".json")).write_text(json.dumps(descriptor))
    config.market_data.close_updates()
    env = {k: v for k, v in os.environ.items() if not k.startswith("WOLF_") and k not in ("NODE_OPTIONS", "PYTHONHOME", "NODE_COMPILE_CACHE")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(REPO / "python/src") + os.pathsep + str(REPO / "python/tests"),
               WOLF_DEV_PORT=str(frontend), WOLF_BROWSER_CONFIG=str(root / "base.json"),
               WOLF_INDEX_BROWSER_CONFIG=str(root / "index.json"), WOLF_ACTIVITY_BROWSER_CONFIG=str(root / "activity.json"),
               WOLF_VITE_CACHE=str(root / "vite-cache"), WOLF_UI_ORIGIN=f"http://127.0.0.1:{frontend}",
               WOLF_PERFORMANCE_ROOT=str(root), WOLF_PERFORMANCE_SAMPLES=str(samples),
               WOLF_PLAYWRIGHT_MODULE=os.environ["WOLF_PLAYWRIGHT_MODULE"])
    if os.environ.get("WOLF_BROWSER_EXECUTABLE"):
        env["WOLF_BROWSER_EXECUTABLE"] = os.environ["WOLF_BROWSER_EXECUTABLE"]
    command = ["node", "apps/desktop/node_modules/vite/bin/vite.js"]
    if built:
        build = command + ["build", "apps/desktop", "--config", "apps/desktop/vite.config.ts", "--configLoader", "runner", "--outDir", str(root / "build")]
        with (root / "build.log").open("wb") as out:
            subprocess.run(build, cwd=REPO, env=env, stdout=out, stderr=subprocess.STDOUT, check=True)
        command += ["preview"]
    command += ["apps/desktop", "--config", "apps/desktop/vite.config.ts", "--configLoader", "runner"]
    if built:
        command += ["--outDir", str(root / "build")]
    result = {"root": str(root), "synthetic_only": True, "built": built, "samples": samples,
              "cold_data_preload": False, "external_fetches": 0,
              "measurement_completed": False, "functional_passed": False, "target_met": False}
    try:
        with process([sys.executable, "-B", __file__, "--serve", str(root), str(backend), str(frontend)], root, "service", env) as backend_process:
            with process(command, root, "frontend", env) as frontend_process:
                deadline = time.monotonic() + 40
                while not (opened(backend) and opened(frontend)):
                    if backend_process.poll() is not None or frontend_process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("隔离服务未正常启动，见日志")
                    time.sleep(.05)
                with (root / "browser.log").open("wb") as out:
                    subprocess.run(["node", "apps/desktop/scripts/overview_performance.harness.mjs"], cwd=REPO, env=env,
                                   stdout=out, stderr=subprocess.STDOUT, check=True, timeout=180 + 180 * samples)
                measured = json.loads((root / "browser-result.json").read_text())
                result["measurement_completed"] = True
                result["functional_passed"] = measured["functional"]
                result["target_met"] = measured["targetMet"]
    finally:
        result["data_unchanged"] = all(disk(root / name) == before[name] for name in before)
        result["ports_closed"] = not opened(backend) and not opened(frontend)
        (root / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        assert result["data_unchanged"] and result["ports_closed"], result


if __name__ == "__main__":
    sys.addaudithook(network_guard)
    if sys.argv[1:2] == ["--serve"]:
        serve(Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
    else:
        parser = argparse.ArgumentParser()
        parser.add_argument("root", type=Path)
        parser.add_argument("--samples", type=int, default=20)
        parser.add_argument("--built", action="store_true")
        args = parser.parse_args()
        if not 1 <= args.samples <= 20:
            raise ValueError("样本次数需在1至20")
        main(args.root, args.samples, args.built)
