"""P2真实HTTP/浏览器联调；仅在显式临时根生成合成三年价格，禁止真实取数。"""
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from pmi.market_data.index_calculations import FORMULA_VERSION

from http_test_support import port, request
from http_test_support import disk
from test_index_series_contract import WINDOW, originals, encoded
from test_index_series_runtime import state
from pmi.market_data import MarketData
from pmi.market_data.index_catalog import INDICES
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data.storage import index_store as store
from sqlite_fixture import initialize, price_writer as writer_lock
from pmi.service_config import ServiceConfig

REPO = Path(__file__).resolve().parents[2]
IDS = ("sse:000001:price", "szse:399001:price", "szse:399006:price", "sse:000688:price")


def varied_originals(index):
    """人工确定的起伏用于图表检查，所有原件仍经过实际领域构建和发布。"""
    items = originals(index, WINDOW)
    primary = json.loads(items[0].content, parse_float=Decimal)
    secondary = json.loads(items[1].content, parse_float=Decimal)
    prices = {}
    for i, day in enumerate(WINDOW.dates):
        base = Decimal(100 + IDS.index(index.index_id) * 100 + i // 15 + (i % 23) - 11)
        close = base + Decimal("0.1234" if index.storage_decimals == 4 else "0.12")
        opening = close + Decimal("1.25") * (1 if i % 2 else -1)
        high, low = max(opening, close) + 2, min(opening, close) - 2
        prices[day] = (opening, high, low, close)
        o, h, low_value, c = [format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f") for value in prices[day]]
        secondary["data"]["klines"][i] = f"{day},{o},{c},{h},{low_value},0,0,0"
    if index.provider == "csindex":
        for row in primary["data"]:
            token = row["tradeDate"]
            day = f"{token[:4]}-{token[4:6]}-{token[6:]}"
            row.update(zip(("open", "high", "low", "close"), prices[day]))
    else:
        for row in primary["data"]["data"]:
            opening, high, low, close = prices[row[0]]
            row[1:6] = [close, high, opening, low, close]
    return tuple(replace(item, content=encoded(body).encode()) for item, body in zip(items, (primary, secondary)))


def main():
    """显式关闭全部采集，保存真实HTTP结果，finally回收并核验自有资源。"""
    parent = Path(os.environ["WOLF_TEST_ROOT"])
    if not parent.is_absolute() or parent.is_symlink() or parent.resolve() != parent or not str(parent).startswith("/private/tmp/"):
        raise ValueError("必须显式提供本次独占的/private/tmp规范目录")
    root = Path(tempfile.mkdtemp(prefix="overview-", dir=parent))
    data = root / "synthetic-data"; data.mkdir()
    initialize(data)
    for index in INDICES:
        if index.index_id not in IDS:
            continue
        items = varied_originals(index)
        with writer_lock(data):
            store.prepare_directories(data, index)
            store.publish(data, index, WINDOW, build_manifest(index, WINDOW, items), items, state(index, "fixture-" + index.index_id.replace(":", "-")))
    before = disk(data)
    backend, frontend = port(), port()
    while backend == frontend:
        frontend = port()
    config = ServiceConfig(data, backend, (f"http://127.0.0.1:{frontend}",))
    legacy, descriptor = config.public_descriptor(), config.public_index_descriptor()
    (root / "legacy.json").write_text(json.dumps(legacy))
    (root / "index.json").write_text(json.dumps(descriptor))
    fixture = {"legacy": legacy, "descriptor": descriptor,
               "views": {index_id: MarketData(data, {}).read_daily(index_id) for index_id in IDS}}
    fixture["calculations"] = {index_id: MarketData(data, {}).read_index_calculations(
        index_id, fixture["views"][index_id]["snapshot"]["snapshot_id"], FORMULA_VERSION) for index_id in IDS}
    (root / "fixture.json").write_text(json.dumps(fixture))
    env = os.environ.copy()
    env.update(WOLF_DEV_PORT=str(frontend), WOLF_BROWSER_CONFIG=str(root / "legacy.json"),
               WOLF_INDEX_BROWSER_CONFIG=str(root / "index.json"), WOLF_VITE_CACHE=str(root / "vite-cache"),
               WOLF_UI_OUTPUT=str(root), WOLF_UI_ORIGIN=f"http://127.0.0.1:{frontend}", WOLF_API_ORIGIN=descriptor["endpoint"],
               WOLF_SERIES_FIXTURE=str(root / "fixture.json"), WOLF_SYNTHETIC_DATA=str(data), WOLF_SCOPE_PYTHON=sys.executable)
    children, streams, active = [], [], []
    record = {"root": str(root), "synthetic_only": True, "before": {"files": len(before)}, "checks": [], "children": []}

    def start(label, command):
        stream = (root / (label + ".log")).open("wb"); streams.append(stream)
        child = subprocess.Popen(command, cwd=REPO, env=env, stdout=stream, stderr=stream, start_new_session=True)
        children.append(child); active.append(child); record["children"].append({"label": label, "pid": child.pid})
        return child

    def stop(child):
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=5)
        if child in active:
            active.remove(child)

    def wait_ready(number, path, headers=None):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if any(child.poll() is not None for child in active):
                raise RuntimeError(f"合成服务提前退出：{root}")
            try:
                if request(number, path, headers=headers)[0] == 200:
                    return
            except OSError:
                pass
            time.sleep(.1)
        raise RuntimeError(f"服务启动超时：{root}")

    try:
        with (root / "client-tests.log").open("wb") as log:
            result = subprocess.run(["node", "--test", "apps/desktop/scripts/index_series_client.harness.mjs"], cwd=REPO, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
        record["client_exit"] = result.returncode
        if result.returncode:
            raise RuntimeError(f"客户端反例失败：{root}")
        service = start("service", [sys.executable, "-B", "-m", "pmi.service", "serve", "--data-root", str(data),
                                   "--port", str(backend), "--origin", env["WOLF_UI_ORIGIN"]])
        vite_command = ["node", "apps/desktop/node_modules/vite/bin/vite.js", "apps/desktop", "--config", "apps/desktop/vite.config.ts", "--configLoader", "runner"]
        vite = start("vite", vite_command)
        wait_ready(backend, "/api/session/ready", {"X-Wolf-Client": "1"}); wait_ready(frontend, "/__wolf/config")
        current = json.loads(request(backend, "/api/index-series/session", headers={"X-Wolf-Client": "1"})[2])
        headers = {"X-Wolf-Client": "1", "X-Wolf-Expected-Instance": current["instance_id"], "X-Wolf-Expected-Config": descriptor["config_id"]}
        for index_id in IDS:
            status, _, body = request(backend, "/api/index-series/" + index_id, headers=headers)
            assert status == 200 and json.loads(body) == fixture["views"][index_id]
        record["checks"].append("four-real-api-responses-equal-published-fixtures")
        calculation_metrics = []
        for index_id in IDS:
            snapshot = fixture["views"][index_id]["snapshot"]
            path = "/api/index-series/" + index_id + "/snapshots/" + snapshot["snapshot_id"] + "/calculations?formula_version=" + FORMULA_VERSION
            started = time.monotonic()
            with urlopen(Request(descriptor["endpoint"] + path, headers=headers), timeout=30) as reply:
                assert reply.status == 200
                assert reply.headers["X-Wolf-Instance"] == current["instance_id"]
                assert reply.headers["X-Wolf-Config"] == descriptor["config_id"]
                body = reply.read()
            calculated = json.loads(body)
            assert calculated == MarketData(data, {}).read_index_calculations(index_id, snapshot["snapshot_id"], FORMULA_VERSION)
            assert calculated["daily"]["rows"][-1]["change_pct"]["value"] == snapshot["summary"]["daily_change_pct"]
            calculation_metrics.append({"index_id": index_id, "bytes": len(body), "seconds": round(time.monotonic()-started, 3)})
        record["calculation_http"] = calculation_metrics
        record["checks"].append("four-fixed-calculations-real-http-context-and-summary-match")

        assert request(backend, "/api/index-series/sse:000001:price", headers={**headers, "X-Wolf-Expected-Config": legacy["config_id"]})[0] == 409
        for path in ("/__wolf/config", "/__wolf/index-config"):
            assert request(frontend, path, headers={"Host": "evil.invalid"})[0] == 403
            assert request(frontend, path, headers={"Origin": "https://evil.invalid"})[0] == 403
            assert request(frontend, path, headers={"X-Forwarded-Host": "evil.invalid"})[0] == 403
            assert request(frontend, path + "?override=1")[0] == 400
            assert request(frontend, path, method="POST")[0] == 400
            assert request(frontend, path, method="HEAD")[0] == 200
        record["checks"].append("native-host-origin-method-and-v1-v2-config-rejection")
        def browser_case(scenario):
            env["WOLF_OVERVIEW_CASE"] = scenario
            with (root / ("browser-" + (scenario or "full") + ".log")).open("wb") as log:
                result = subprocess.run(["node", "apps/desktop/scripts/market_overview.harness.mjs"], cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f"真实浏览器检查失败：{root}")
        browser_case("")
        stop(vite); stop(service)
        assert before == disk(data)
        empty = root / "empty-data"; empty.mkdir()
        initialize(empty)
        empty_before = disk(empty)
        empty_config = ServiceConfig(empty, backend, (env["WOLF_UI_ORIGIN"],))
        (root / "legacy.json").write_text(json.dumps(empty_config.public_descriptor()))
        (root / "index.json").write_text(json.dumps(empty_config.public_index_descriptor()))
        service = start("empty-service", [sys.executable, "-B", "-m", "pmi.service", "serve", "--data-root", str(empty),
                                         "--port", str(backend), "--origin", env["WOLF_UI_ORIGIN"]])
        vite = start("empty-vite", vite_command)
        wait_ready(backend, "/api/session/ready", {"X-Wolf-Client": "1"}); wait_ready(frontend, "/__wolf/index-config")
        browser_case("empty")
        stop(vite); env.pop("WOLF_INDEX_BROWSER_CONFIG")
        vite = start("legacy-only-vite", vite_command); wait_ready(frontend, "/__wolf/config")
        assert request(frontend, "/__wolf/index-config")[0] == 404
        browser_case("missing-config")
        record["empty_data_unchanged"] = disk(empty) == empty_before
        assert record["empty_data_unchanged"]
        stop(vite); stop(service)
        with (root / "browser-scope.log").open("wb") as log:
            result = subprocess.run(["node", "apps/desktop/scripts/market_scope.harness.mjs"], cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
        assert result.returncode == 0, f"跨资料根隔离检查失败：{root}"
        record["checks"].append("cross-root-missing-v2-ready-mismatch-and-late-body-isolation")
        record["passed"] = True
    finally:
        for child in reversed(children):
            stop(child)
        for stream in streams:
            stream.close()
        record["exits"] = {str(child.pid): child.poll() for child in children}
        record["data_unchanged"] = before == disk(data)
        record["ports_closed"] = {}
        for number in (backend, frontend):
            with socket.socket() as probe:
                record["ports_closed"][str(number)] = probe.connect_ex(("127.0.0.1", number)) != 0
        (root / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(record, ensure_ascii=False))
        assert record["data_unchanged"] and all(record["ports_closed"].values())


if __name__ == "__main__":
    main()
