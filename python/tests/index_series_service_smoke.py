"""显式执行六指数真实 HTTP 链路；无参数时不启动服务或访问数据根。

此工具会通过获准服务真实取数。执行者须显式选择已有根和新的证据目录；
本文件不注入时钟、来源响应、handler 或业务数据库，也不自动重试取数。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import quote
import uuid

import requests

EXACT_IDS = frozenset({"csi:000300:price", "sse:000001:price", "csi:000852:price",
                       "szse:399001:price", "szse:399006:price", "sse:000688:price"})
DIRECTORIES = {"csi:000300:price": "indices/csi000300", "sse:000001:price": "indices/sse000001",
               "csi:000852:price": "indices/csi000852", "szse:399001:price": "indices/szse399001",
               "szse:399006:price": "indices/szse399006", "sse:000688:price": "indices/sse000688"}
LEDGER = "index-v2-network-ledger.jsonl"
SUCCESS = {"business_changed", "evidence_changed", "unchanged"}
MAX_ATTEMPTS = 16
MAX_BYTES = 16 * 1024 * 1024
HTTP_BYTES = 16 * 1024 * 1024


class CheckFailed(RuntimeError):
    """只保存检查标签，不把金融响应或环境配置拼进异常。"""


def require(condition: object, label: str) -> None:
    """在优化模式下也执行验收断言。"""
    if not condition:
        raise CheckFailed(label)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_member")
        result[key] = value
    return result


def load(content: bytes) -> object:
    """拒绝重复 JSON 成员，不接受非有限 JSON 常量。"""
    def invalid(value: str) -> None:
        raise CheckFailed("invalid_json_constant")
    return json.loads(content, object_pairs_hook=unique, parse_constant=invalid)


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def save(path: Path, value: object) -> None:
    """证据只写入本次独占输出根。"""
    path.write_bytes(canonical(value) + b"\n")


def hash_tree(root: Path) -> dict[str, str]:
    """流式核对所有既有普通文件；拒绝符号链接和特殊文件。"""
    result = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), "data_tree_symlink")
        if stat.S_ISDIR(mode):
            continue
        require(stat.S_ISREG(mode), "data_tree_special_file")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        result[path.relative_to(root).as_posix()] = digest.hexdigest()
    return result


def verify_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """旧文件不能删除或改变，新文件只能位于六指数及两个父控制文件。"""
    require(all(after.get(path) == digest for path, digest in before.items()), "preexisting_file_changed")
    added = sorted(after.keys() - before.keys())
    require(all(path in {LEDGER, ".writer.lock"} or any(path.startswith(directory + "/")
                for directory in DIRECTORIES.values()) for path in added), "new_file_outside_six_indices")
    return added


def port_free(port: int) -> bool:
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


@dataclass
class Receipt:
    status: int
    body: object
    headers: dict[str, str]


class Loopback:
    """真实回环客户端，响应原字节单独保存且禁止重定向和代理。"""

    def __init__(self, endpoint: str, origin: str, output: Path, phase: str):
        self.endpoint, self.origin, self.output, self.phase = endpoint, origin, output, phase
        self.session = requests.Session()
        self.session.trust_env = False
        self.sequence = 0
        self.instance: str | None = None
        self.config: str | None = None

    def request(self, method: str, path: str, *, params: dict | None = None,
                request_id: str | None = None, expected: tuple[int, ...] = (200,), bind: bool = True,
                deadline: float | None = None) -> Receipt:
        self.sequence += 1
        name = f"{self.phase}-{self.sequence:04d}"
        headers = {"Origin": self.origin, "X-Wolf-Client": "1"}
        if bind:
            require(self.instance is not None and self.config is not None, "unbound_client")
            headers.update({"X-Wolf-Expected-Instance": self.instance, "X-Wolf-Expected-Config": self.config})
        if method == "POST":
            require(request_id is not None, "post_without_request_id")
            headers.update({"Content-Type": "application/json", "X-Wolf-Request-Id": request_id})
        record = {"started_at": stamp(), "method": method, "path": path, "params": params,
                  "request_id": request_id, "expected_instance": self.instance if bind else None,
                  "expected_config": self.config if bind else None}
        try:
            remaining = deadline - time.monotonic() if deadline is not None else 5
            require(remaining > 0, "http_deadline")
            with self.session.request(method, self.endpoint + path, params=params, headers=headers,
                                      data=b"{}" if method == "POST" else None,
                                      timeout=(min(2, remaining), min(5, remaining)),
                                      allow_redirects=False, stream=True) as response:
                content = bytearray()
                for block in response.iter_content(65536):
                    content.extend(block)
                    require(len(content) <= HTTP_BYTES, "http_response_too_large")
                    require(deadline is None or time.monotonic() <= deadline, "http_deadline")
                raw = bytes(content)
                (self.output / (name + ".body")).write_bytes(raw)
                selected = {key: response.headers.get(key) for key in ("Content-Type", "X-Wolf-Instance", "X-Wolf-Config", "Cache-Control")}
                record.update(status=response.status_code, headers=selected, body_file=name + ".body",
                              body_bytes=len(raw), body_sha256=sha(raw))
                require(response.status_code in expected, "unexpected_http_status")
                body = load(raw)
                if bind and response.status_code < 300:
                    require(selected["X-Wolf-Instance"] == self.instance and selected["X-Wolf-Config"] == self.config, "response_binding_changed")
                return Receipt(response.status_code, body, selected)
        except Exception as error:
            record["error_type"] = type(error).__name__
            raise
        finally:
            record["completed_at"] = stamp()
            save(self.output / (name + ".json"), record)


class Run:
    """只拥有本次服务进程、回环会话和独占证据目录。"""

    def __init__(self, args: argparse.Namespace):
        self.args, self.root, self.output = args, args.data_root, args.output
        self.process: subprocess.Popen | None = None
        self.log = None
        self.client: Loopback | None = None
        self.phase = "not_started"
        self.before: dict[str, str] | None = None
        self.summary: dict = {"result": "running", "mode": args.mode, "started_at": stamp(),
                              "acquisition_retry": False, "network_scope": "service only; loopback client trust_env=False"}

    def command(self, action: str, *, readonly: bool) -> list[str]:
        command = [self.args.python, "-m", "pmi.service", action, "--data-root", str(self.root),
                   "--port", str(self.args.port), "--origin", self.args.origin,
                   "--index-max-attempts", str(MAX_ATTEMPTS), "--index-max-bytes", str(MAX_BYTES)]
        if not readonly:
            for index_id in self.ids:
                command += ["--index-write-id", index_id]
            if self.args.mode == "startup":
                for index_id in self.ids:
                    command += ["--startup-index-id", index_id]
        return command

    def start(self, phase: str, *, readonly: bool) -> dict:
        """先从独立 CLI 得到预期，再启动标准服务并核对 ready。"""
        self.phase = phase
        require(port_free(self.args.port), "port_already_occupied")
        environment = os.environ.copy()
        if readonly:
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                environment[key] = "http://127.0.0.1:1"
            environment.update(NO_PROXY="", no_proxy="")
        command = self.command("describe-index-config", readonly=readonly)
        description = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=30, env=environment, check=False)
        (self.output / f"{phase}-descriptor.stdout").write_bytes(description.stdout)
        (self.output / f"{phase}-descriptor.stderr").write_bytes(description.stderr)
        save(self.output / f"{phase}-descriptor-process.json", {"command": command, "exit_code": description.returncode,
             "stdout_sha256": sha(description.stdout), "stderr_sha256": sha(description.stderr)})
        require(description.returncode == 0, "descriptor_cli_failed")
        descriptor = load(description.stdout)
        require(isinstance(descriptor, dict) and descriptor["endpoint"] == f"http://127.0.0.1:{self.args.port}", "descriptor_endpoint")
        require(descriptor["write_indices"] == ([] if readonly else self.ids), "descriptor_permissions")
        require(descriptor["startup_indices"] == (self.ids if not readonly and self.args.mode == "startup" else []), "descriptor_startup")
        require(descriptor["policy"]["network"]["max_attempts"] == MAX_ATTEMPTS
                and descriptor["policy"]["network"]["max_bytes"] == MAX_BYTES, "descriptor_budget")
        command = self.command("serve", readonly=readonly)
        self.log = (self.output / f"{phase}-service.log").open("wb")
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log,
                                        env=environment, start_new_session=True)
        save(self.output / f"{phase}-start.json", {"at": stamp(), "pid": self.process.pid, "command": command,
             "readonly_child_bad_proxy": readonly, "global_environment_changed": False})
        self.client = Loopback(descriptor["endpoint"], self.args.origin, self.output, phase)
        deadline = time.monotonic() + 30
        while True:
            require(self.process.poll() is None, "service_exited_before_ready")
            require(time.monotonic() < deadline, "service_ready_deadline")
            try:
                ready = self.client.request("GET", "/api/index-series/session", bind=False, deadline=deadline)
                break
            except requests.ConnectionError:
                require(time.monotonic() < deadline, "service_ready_deadline")
                time.sleep(.1)
        body = ready.body
        require(isinstance(body, dict) and body.get("status") == "ready", "ready_status")
        instance = body.get("instance_id")
        require(isinstance(instance, str) and str(uuid.UUID(instance)) == instance and uuid.UUID(instance).version == 4, "ready_instance")
        require({key: value for key, value in body.items() if key not in {"status", "instance_id"}}
                == {key: value for key, value in descriptor.items() if key != "endpoint"}, "ready_does_not_match_independent_descriptor")
        require(ready.headers["X-Wolf-Instance"] == instance and ready.headers["X-Wolf-Config"] == descriptor["config_id"], "ready_headers")
        self.client.instance, self.client.config = instance, descriptor["config_id"]
        catalog = self.client.request("GET", "/api/index-series/catalog").body
        require({item["index_id"] for item in catalog["indices"]} == EXACT_IDS and len(catalog["indices"]) == 6, "http_catalog_scope")
        require(all(item["writable"] is (not readonly) for item in catalog["indices"]), "http_catalog_permissions")
        return {"descriptor": descriptor, "instance_id": instance}

    def stop(self) -> None:
        """TERM 最多 10 秒，随后 KILL 最多 5 秒并回收自有进程。"""
        if self.process is None:
            return
        process = self.process
        record = {"started_at": stamp(), "pid": process.pid, "term_sent": False, "kill_sent": False}
        try:
            if process.poll() is None:
                process.terminate()
                record["term_sent"] = True
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    record["kill_sent"] = True
                    process.wait(timeout=5)
            # 防止已退出 leader 留下同组的自有采集进程；不触碰其他进程组。
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                os.killpg(process.pid, signal.SIGKILL)
                record["remaining_owned_group_killed"] = True
            deadline = time.monotonic() + 2
            while not port_free(self.args.port) and time.monotonic() < deadline:
                time.sleep(.1)
            record.update(exit_code=process.returncode, reaped=process.poll() is not None, port_released=port_free(self.args.port))
            require(record["reaped"] and record["port_released"], "service_cleanup_incomplete")
        finally:
            if self.client:
                self.client.session.close()
            if self.log:
                self.log.close()
            record["completed_at"] = stamp()
            save(self.output / f"{self.phase}-stop.json", record)
            if process.poll() is not None:
                self.process = None

    def controls(self) -> dict:
        """仅监测任务控制状态和期限；金融验收始终走 HTTP。"""
        result = {}
        for index_id in self.ids:
            path = self.root / DIRECTORIES[index_id] / "update-v2-status.json"
            if not path.exists():
                continue
            state = load(path.read_bytes())
            require(state.get("index_id") == index_id, "control_index_identity")
            stage, outcome = state.get("stage"), state.get("result")
            require(stage not in {"failed", "interrupted"} and outcome != "source_not_ready", "job_failed_stop_without_retry")
            if stage == "completed":
                require(outcome in SUCCESS, "job_not_successful")
            else:
                started = datetime.fromisoformat(state["started_at"].replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - started).total_seconds()
                require(0 <= age <= 120, "job_deadline_120_seconds")
            result[index_id] = {key: state.get(key) for key in ("index_id", "job_id", "trigger", "stage", "result", "started_at", "finished_at", "snapshot_id")}
        return result

    def operation(self, index_id: str, request_id: str, identity: dict | None = None) -> dict:
        context = identity or {"instance_id": self.client.instance, "config_id": self.client.config}
        expected = {"instance_id": context["instance_id"], "config_id": context["config_id"],
                    "operation": "index.series.update", "index_id": index_id}
        result = self.client.request("GET", "/api/index-series/operations/" + request_id, params=expected).body
        require(all(result[key] == value for key, value in {**expected, "request_id": request_id}.items()), "operation_full_identity")
        return result

    def acquire(self) -> dict:
        """首存仅通过 serve 的启动补齐或逐项真实 HTTP POST。"""
        from pmi.market_data.index_history_calendar import complete_window
        requests_by_index = {}
        if self.args.mode == "startup":
            deadline = time.monotonic() + 6 * 120
            while True:
                states = self.controls()
                require(complete_window(datetime.now(timezone.utc)).anchor_date == self.window.anchor_date, "shanghai_day_changed")
                require(self.process.poll() is None, "service_exited_during_startup")
                if len(states) == 6 and all(state["stage"] == "completed" for state in states.values()):
                    break
                require(time.monotonic() < deadline, "startup_total_deadline")
                time.sleep(.25)
            self.summary["startup_control_monitor"] = states
            self.summary["request_replay_checks"] = "not_applicable_startup_has_no_http_request_association; covered by manual mode"
            return {index_id: {"request_id": uuid.uuid4().hex, "receipt": None} for index_id in self.ids}
        for index_id in self.ids:
            require(complete_window(datetime.now(timezone.utc)).anchor_date == self.window.anchor_date, "shanghai_day_changed")
            request_id = uuid.uuid4().hex
            receipt = self.client.request("POST", self.path(index_id) + "/update", request_id=request_id, expected=(202,)).body
            require(receipt["request_id"] == request_id and receipt["index_id"] == index_id and receipt["operation"] == "index.series.update"
                    and receipt["instance_id"] == self.client.instance and receipt["config_id"] == self.client.config, "accepted_identity")
            requests_by_index[index_id] = {"request_id": request_id, "receipt": receipt}
            deadline = time.monotonic() + 120
            while True:
                self.controls()
                result = self.operation(index_id, request_id)
                require(all(result[key] == receipt[key] for key in ("instance_id", "config_id", "request_id", "index_id", "operation", "job_id")), "operation_identity")
                if result["state"] == "completed":
                    require(result["business_status"]["result"] in SUCCESS, "operation_not_successful")
                    break
                require(result["state"] in {"accepted", "running"}, "operation_failed_or_unknown")
                require(time.monotonic() < deadline, "job_deadline_120_seconds")
                time.sleep(.25)
        return requests_by_index

    @staticmethod
    def path(index_id: str) -> str:
        return "/api/index-series/" + quote(index_id, safe="")

    def financial_reads(self, index_id: str, prior: dict | None = None) -> dict:
        """验证 current、固定快照、两份证据及单字段范围，原值不写 stdout。"""
        base = self.path(index_id)
        current = self.client.request("GET", base).body
        require(current["index_id"] == index_id and current["format"] == "v2", "current_identity")
        snapshot = current["snapshot"]
        snapshot_id = snapshot["snapshot_id"]
        require(snapshot["instrument"]["id"] == index_id, "snapshot_identity")
        manifest = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "observation_id", "retrieval"}}
        require(sha(canonical(manifest)) == snapshot_id, "snapshot_content_hash")
        require(snapshot["window"] == self.window.as_dict() and snapshot["calendar_dates"] == list(self.window.dates), "real_three_year_window")
        require([bar["trade_date"] for bar in snapshot["bars"]] == list(self.window.dates), "complete_http_bars")
        fixed = self.client.request("GET", base + "/snapshots/" + snapshot_id).body
        require(fixed == current, "fixed_current_differ")
        require(len(snapshot["evidence"]) == 2, "two_source_evidence")
        require([source["source"] for source in snapshot["evidence"]]
                == ["cnindex" if index_id.startswith("szse:") else "csindex", "eastmoney"], "http_evidence_source_scope")
        evidence_hashes = []
        for source in snapshot["evidence"]:
            evidence = self.client.request("GET", base + f"/snapshots/{snapshot_id}/evidence/{source['object_id']}").body
            require(evidence["index_id"] == index_id and evidence["format"] == "v2", "evidence_index_identity")
            detail = evidence["evidence"]
            require(detail["snapshot_id"] == snapshot_id and detail["observation_id"] == snapshot["observation_id"]
                    and all(detail[key] == source[key] for key in ("source", "object_id", "url", "rows")), "evidence_fixed_contents")
            evidence_hashes.append(sha(canonical(evidence)))
        ranged = self.client.request("GET", base + "/range", params={"start": self.window.start, "end": self.window.end,
            "fields": "close", "snapshot_id": snapshot_id}).body
        require(ranged["index_id"] == index_id and ranged["snapshot_id"] == snapshot_id and ranged["fields"] == ["close"], "range_identity")
        require(ranged["rows"] == [{"trade_date": bar["trade_date"], "values": {"close": bar["close"]}} for bar in snapshot["bars"]], "range_single_field_values")
        result = {"snapshot_id": snapshot_id, "rows": len(snapshot["bars"]), "current_sha256": sha(canonical(current)),
                  "fixed_sha256": sha(canonical(fixed)), "evidence_sha256": evidence_hashes, "range_sha256": sha(canonical(ranged))}
        if prior is not None:
            require(result == prior, "readonly_restart_changed_fixed_financial_response")
        return result

    def ledger(self) -> dict:
        content = (self.root / LEDGER).read_bytes()
        entries = [load(line) for line in content.splitlines()]
        attempts = [entry for entry in entries if entry["event"] == "attempt"]
        finished = [entry for entry in entries if entry["event"] == "finished"]
        require(len(attempts) == 12 and len(finished) == 12, "expected_exactly_twelve_source_requests")
        require(len({entry["attempt_id"] for entry in attempts}) == 12, "duplicate_network_attempt")
        require({entry["attempt_id"] for entry in attempts} == {entry["attempt_id"] for entry in finished}, "network_settlement_missing")
        require(all(entry["success"] is True for entry in finished), "source_request_failed")
        for index_id in self.ids:
            sources = [entry["source"] for entry in attempts if entry["index_id"] == index_id]
            official = "cnindex" if index_id.startswith("szse:") else "csindex"
            require(sources == [official, "eastmoney"], "source_request_scope_or_order")
        charged = sum(entry["charged_bytes"] for entry in finished)
        require(charged <= MAX_BYTES, "network_budget_overrun")
        return {"sha256": sha(content), "attempts": len(attempts), "charged_bytes": charged}

    def execute(self) -> None:
        """执行两个有界服务生命周期；第二次禁写并使用子进程坏代理。"""
        from pmi.market_data import MarketData
        from pmi.market_data.index_history_calendar import complete_window
        facade = MarketData(self.root, {})
        catalog = facade.index_catalog()
        self.ids = sorted(item["index_id"] for item in catalog["indices"])
        require(len(self.ids) == 6 and set(self.ids) == EXACT_IDS, "local_catalog_scope")
        require(not (self.root / LEDGER).exists() and all(not (self.root / directory / name).exists()
                for directory in DIRECTORIES.values() for name in ("index-v2.sqlite", "update-v2-status.json", "index-v2-original-observations.jsonl")), "requires_fresh_v2_first_save_without_previous_attempts")
        before = hash_tree(self.root)
        self.before = before
        save(self.output / "files-before.json", before)
        self.window = complete_window(datetime.now(timezone.utc))
        self.summary["window"] = self.window.as_dict()
        self.summary["catalog"] = catalog
        first = self.start("write", readonly=False)
        associations = self.acquire()
        # 控制终态可能早于线程释放父锁；只等待对应 GET 状态可读，不发新写请求。
        for index_id in self.ids:
            deadline = time.monotonic() + 5
            while True:
                state = self.client.request("GET", self.path(index_id) + "/update", expected=(200, 409))
                if state.status == 200:
                    require(state.body["stage"] == "completed" and state.body["result"] in SUCCESS, "http_terminal_status")
                    break
                require(time.monotonic() < deadline, "writer_lock_not_released")
                time.sleep(.1)
        results = {index_id: self.financial_reads(index_id) for index_id in self.ids}
        ledger = self.ledger()
        if self.args.mode == "manual":
            for position, index_id in enumerate(self.ids):
                association = associations[index_id]
                repeat = self.client.request("POST", self.path(index_id) + "/update", request_id=association["request_id"], expected=(202,)).body
                require(repeat == association["receipt"], "duplicate_post_not_initial_receipt")
                conflict = self.client.request("POST", self.path(self.ids[(position + 1) % 6]) + "/update",
                    request_id=association["request_id"], expected=(409,)).body
                require(conflict["detail"]["code"] == "request_id_conflict", "cross_index_request_not_conflict")
            require(self.ledger() == ledger, "repeated_request_caused_network")
            self.summary["request_replay_checks"] = "six initial receipts replayed; six cross-index conflicts; ledger unchanged"
        self.stop()
        after_write = hash_tree(self.root)
        added = verify_changes(before, after_write)
        save(self.output / "files-after-write.json", after_write)
        self.summary.update(write_binding=first, acquired=results, new_files=added, network=ledger)
        second = self.start("readonly", readonly=True)
        require(first["instance_id"] != second["instance_id"] and first["descriptor"]["config_id"] != second["descriptor"]["config_id"], "restart_identity_not_changed")
        require(first["descriptor"]["data_scope_id"] == second["descriptor"]["data_scope_id"], "restart_data_scope_changed")
        for index_id in self.ids:
            self.financial_reads(index_id, results[index_id])
            request_id = associations[index_id]["request_id"]
            for identity in (None, {"instance_id": first["instance_id"], "config_id": first["descriptor"]["config_id"]}):
                result = self.operation(index_id, request_id, identity)
                require(result["state"] == "unknown" and result["business_status"] is None and result["job_id"] is None, "restart_reconstructed_operation")
        disabled = self.client.request("POST", self.path(self.ids[0]) + "/update", request_id=uuid.uuid4().hex, expected=(403,)).body
        require(disabled["detail"]["code"] == "index_update_disabled", "readonly_update_enabled")
        self.stop()
        after_read = hash_tree(self.root)
        save(self.output / "files-after-readonly.json", after_read)
        require(after_read == after_write and self.ledger() == ledger, "readonly_restart_mutated_data_or_ledger")
        self.summary.update(readonly_binding=second, result="passed", readonly_proof="disabled writes, no startup, child-only bad proxies, identical file hashes and ledger; no global network disable")


def arguments() -> argparse.Namespace:
    """所有执行参数必须显式提供；help 和缺参数均不接触业务根。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--mode", required=True, choices=("startup", "manual"))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    if not args.data_root.is_absolute() or not args.data_root.is_dir() or args.data_root.resolve() != args.data_root:
        parser.error("data-root 必须是已存在的规范绝对目录")
    if (not args.output.is_absolute() or args.output.exists() or args.output.resolve() != args.output
            or not args.output.parent.is_dir() or args.output.is_relative_to(args.data_root) or args.data_root.is_relative_to(args.output)):
        parser.error("output 必须是数据根之外、父目录已存在的新规范绝对目录")
    if not 0 < args.port < 65536:
        parser.error("port 无效")
    return args


def main() -> int:
    args = arguments()
    args.output.mkdir(mode=0o700)
    run = Run(args)
    try:
        run.execute()
    except BaseException as error:
        run.summary.update(result="failed", error_type=type(error).__name__,
                           error_label=str(error) if isinstance(error, CheckFailed) else "see_saved_process_and_http_receipts")
    finally:
        try:
            run.stop()
        except BaseException as error:
            run.summary.update(result="failed", cleanup_error_type=type(error).__name__)
        if run.before is not None:
            try:
                final_files = hash_tree(args.data_root)
                save(args.output / "files-final.json", final_files)
                added = verify_changes(run.before, final_files)
                run.summary["final_original_files_unchanged"] = True
                run.summary["final_new_files_within_scope"] = added
            except BaseException as error:
                run.summary.update(result="failed", final_files_check_error_type=type(error).__name__,
                                   final_original_files_unchanged=False)
        run.summary["completed_at"] = stamp()
        save(args.output / "result.json", run.summary)
    print(json.dumps({"result": run.summary["result"], "evidence": str(args.output),
                      "result_sha256": sha((args.output / "result.json").read_bytes())}, ensure_ascii=False))
    return 0 if run.summary["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
