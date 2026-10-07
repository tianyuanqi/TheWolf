"""指数首版合成反例；所有库和状态位于独立临时根，不访问真实来源。"""

import asyncio
import json
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from test_api_slice import asgi_get
from contextlib import nullcontext

class LocalResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body
    def json(self):
        return json.loads(self.body)


class TestClient:
    """复用项目ASGI消费者，不增加httpx依赖，不运行网络或lifespan。"""
    def __init__(self, unused):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def get(self, path, headers=None):
        return self.send(path, headers, "GET", b"")
    def post(self, path, headers=None, json=None):
        return self.send(path, headers, "POST", __import__("json").dumps(json).encode())
    def send(self, path, headers, method, body):
        route, _, query = path.partition("?")
        return LocalResponse(*asyncio.run(asgi_get(route, {"host": "testserver", "content-type": "application/json", **{key.lower():value for key,value in (headers or {}).items()}}, method, body, query.encode())))

app = None
from pmi.index_calendar import complete_window
from pmi.index_contract import (Original, SourceNotReady, build_manifest, canonical, point,
                                summarize)
from pmi.index_snapshot import (committed_job, index_root, publish, read_evidence,
                                read_snapshot)
from pmi.index_update import (_record_attempt, _save_state, classify_change, perform_update,
                              fetch_bounded, start_update, update_status)
from pmi.index_fetch import fetch_once
from pmi.snapshot import SnapshotError
from pmi.writer_lock import writer_lock

CLOCK = datetime(2026, 10, 5, tzinfo=timezone.utc)
DAYS = complete_window(CLOCK)


def originals(days=DAYS, close="105.00", stamp="2026-10-05T01:00:00Z", extra=None):
    """构造两源明确合成价格原件，保留开/收/高/低的不同值证明映射。"""
    east = {"code": 0, "data": {"sh000300": {"qt": {"sh000300": ["1", "沪深300", "000300"]},
                    "day": [[day, "100.00", close, "110.00", "90.00", "0"] for day in days]}}}
    official = {"code": "200", "msg": "Success", "data": [
        {"tradeDate": day.replace("-", ""), "indexCode": "000300", "indexNameCn": "沪深300", "indexNameCnAll": "沪深300指数",
         "open": "100.00", "high": "110.00", "low": "90.00", "close": close} for day in days]}
    if extra:
        east.update(extra)
    return (Original("tencent", canonical(east), stamp, stamp), Original("csindex", canonical(official), stamp, stamp))


def mutated(items, source, mutation):
    """只改变指定原件，反例不绕过真实来源解析。"""
    result = list(items)
    raw = json.loads(result[source].content)
    mutation(raw)
    result[source] = Original(result[source].source, canonical(raw), result[source].started_at, result[source].completed_at)
    return tuple(result)


def state(job="synthetic-job"):
    return {"job_id": job, "stage": "preparing", "last_success_at": None, "target_start": DAYS[0], "target_end": DAYS[-1]}


class IndexContractTests(unittest.TestCase):
    def test_calendar_identity_and_mapping(self):
        self.assertEqual((DAYS[0], DAYS[-1], len(DAYS)), ("2025-09-04", "2026-09-30", 260))
        self.assertEqual(complete_window(datetime(2026, 10, 1, 0, tzinfo=timezone.utc)), DAYS)
        for year in (2025, 2027):
            with self.assertRaisesRegex(SnapshotError, "calendar_uncovered"):
                complete_window(datetime(year, 1, 5, tzinfo=timezone.utc))
        manifest = build_manifest(DAYS, originals())
        self.assertEqual([manifest["bars"][0][key] for key in ("open", "high", "low", "close")], ["100.00", "110.00", "90.00", "105.00"])
        self.assertEqual(manifest["instrument"]["id"], "csi:000300:price")
        for mutate in (lambda raw: raw["data"]["sh000300"]["qt"]["sh000300"].__setitem__(2, "H00300"),
                       lambda raw: raw["data"]["sh000300"]["qt"]["sh000300"].__setitem__(1, "其他指数"),
                       lambda raw: raw["data"].update(sh000300={}), lambda raw: raw.update(code=1)):
            with self.assertRaises(SnapshotError):
                build_manifest(DAYS, mutated(originals(), 0, mutate))
        for invalid_day in ("2026-10-05", "2026-10-08", DAYS[0]):
            with self.assertRaises(SnapshotError):
                build_manifest(DAYS, mutated(originals(), 0, lambda raw: raw["data"]["sh000300"]["day"].__setitem__(-1, [invalid_day,"100","105","110","90","0"])))

    def test_decimal_and_calculation_boundaries(self):
        self.assertEqual(point("100.000"), "100.00")
        for value in ("100.001", "NaN", "Infinity", "0", "-1", 100.1, None):
            with self.assertRaises(SnapshotError):
                point(value)
        bars = [{"trade_date": "2026-09-29", "close": "100.00", "evidence_refs": []},
                {"trade_date": "2026-09-30", "close": "110.00", "evidence_refs": []}]
        self.assertEqual(summarize(bars)["daily_change_pct"], "10.00")
        self.assertEqual(summarize(bars[:1])["reason"], "first_row_without_previous_close")
        for close, expected in (("100.01", "0.01"), ("99.99", "-0.01"), ("100.00", "0.00")):
            bars[0]["close"] = "200.00"; bars[1]["close"] = {"100.01": "200.01", "99.99": "199.99", "100.00": "200.00"}[close]
            self.assertEqual(summarize(bars)["daily_change_pct"], expected)
        for value in ("100.001", "120", "85"):
            with self.assertRaises(SnapshotError):
                build_manifest(DAYS, originals(close=value))
        equal = mutated(originals(), 1, lambda raw: raw["data"][0].update(open="100.000", high="110.000"))
        self.assertEqual(build_manifest(DAYS, equal)["bars"][0]["open"], "100.00")
        # 原始JSON小数而非字符串，尾零和非零第三位分别验证。
        raw = equal[1].content.replace(b'"100.000"', b'100.000')
        build_manifest(DAYS, (equal[0], Original("csindex", raw, equal[1].started_at, equal[1].completed_at)))
        with self.assertRaises(SnapshotError):
            build_manifest(DAYS, (equal[0], Original("csindex", raw.replace(b'100.000', b'100.001'), equal[1].started_at, equal[1].completed_at)))

    def test_missing_and_mismatch(self):
        items = originals()
        with self.assertRaises(SourceNotReady):
            build_manifest(DAYS, mutated(items, 0, lambda raw: raw["data"]["sh000300"]["day"].pop()))
        with self.assertRaisesRegex(SnapshotError, "内部缺日"):
            build_manifest(DAYS, mutated(items, 0, lambda raw: raw["data"]["sh000300"]["day"].pop(100)))
        mismatch = mutated(items, 1, lambda raw: raw["data"][0].update(close="104.99"))
        with self.assertRaisesRegex(SnapshotError, "双源不一致"):
            build_manifest(DAYS, mismatch)
        with self.assertRaisesRegex(SnapshotError, "双源不一致"):
            build_manifest(DAYS, mutated(mismatch, 0, lambda raw: raw["data"]["sh000300"]["day"].pop()))


class IndexStorageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="thewolf-index-test-")
        self.root = Path(self.directory.name).resolve()

    def tearDown(self):
        self.directory.cleanup()

    def publish(self, items, job, days=DAYS, checkpoint=None):
        with writer_lock(self.root):
            return publish(self.root, build_manifest(days, items), items, {**state(job), "result": "business_changed"}, checkpoint)

    def test_immutable_observations_and_no_cutoff_regression(self):
        first = originals()
        a = self.publish(first, "a")
        fixed = read_snapshot(self.root, a)
        b = self.publish(originals(close="106.00", stamp="2026-10-05T02:00:00Z"), "b")
        self.publish(first, "old-a")
        self.assertEqual(read_snapshot(self.root)["snapshot_id"], b)
        self.publish(originals(stamp="2026-10-05T03:00:00Z"), "new-a")
        self.assertEqual(read_snapshot(self.root)["snapshot_id"], a)
        self.assertEqual(read_snapshot(self.root, a), fixed)
        self.publish(originals(close="106.00", stamp="2026-10-05T02:00:00+00:00"), "old-b")
        self.assertEqual(read_snapshot(self.root)["snapshot_id"], a)
        newer_days = complete_window(datetime(2026, 10, 9, tzinfo=timezone.utc))
        newest = self.publish(originals(newer_days, stamp="2026-10-09T01:00:00Z"), "next", newer_days)
        self.publish(originals(stamp="2026-10-10T01:00:00Z"), "late-old-window")
        self.assertEqual(read_snapshot(self.root)["snapshot_id"], newest)
        self.assertEqual(read_snapshot(self.root, a), fixed)
        with sqlite3.connect(index_root(self.root) / "index.sqlite") as db:
            self.assertEqual(db.execute("SELECT count(*) FROM observations").fetchone()[0], 5)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_classification_and_fixed_evidence(self):
        items = originals()
        a = self.publish(items, "a")
        previous = read_snapshot(self.root)
        self.assertEqual(classify_change(previous, build_manifest(DAYS, items))[0], "unchanged")
        extra = originals(extra={"unused": "changed"})
        self.assertEqual(classify_change(previous, build_manifest(DAYS, extra))[0], "evidence_changed")
        revised = originals(close="106.00")
        self.assertEqual(classify_change(previous, build_manifest(DAYS, revised))[0], "business_changed")
        oid = previous["evidence"][0]["object_id"]
        evidence = read_evidence(self.root, a, oid)
        self.assertEqual(evidence["rows"][0]["raw_values"]["close"], "105.00")
        self.publish(extra, "evidence-change")
        self.assertEqual(read_evidence(self.root, a, oid), evidence)
        with self.assertRaises(SnapshotError):
            read_evidence(self.root, a, read_snapshot(self.root)["evidence"][0]["object_id"])
        index_root(self.root).joinpath("objects", oid).write_bytes(b"tampered")
        with self.assertRaisesRegex(SnapshotError, "哈希损坏"):
            read_snapshot(self.root, a)

    def test_read_only_empty_and_symlink(self):
        missing = self.root / "missing"
        self.assertIsNone(read_snapshot(missing))
        self.assertEqual(update_status(missing)["stage"], "idle")
        self.assertFalse(missing.exists())
        self.root.joinpath("indices").symlink_to(self.root.parent, target_is_directory=True)
        for action in (lambda: read_snapshot(self.root), lambda: start_update(self.root, CLOCK), lambda: update_status(self.root)):
            with self.assertRaisesRegex(SnapshotError, "符号链接"):
                action()
        self.assertFalse(self.root.joinpath(".writer.lock").exists())

    def test_database_links_and_sidecars_fail_closed(self):
        """损坏当前映射/首次观察/job以及SQLite旁文件时明确失败，不回退。"""
        sid = self.publish(originals(), "a")
        database = index_root(self.root) / "index.sqlite"
        original = database.read_bytes()
        cases = (
            ("UPDATE snapshots SET first_observation='missing'", lambda: read_snapshot(self.root)),
            ("UPDATE current_snapshot SET snapshot_id='missing'", lambda: read_snapshot(self.root)),
            ("UPDATE current_snapshot SET observation_id='missing'", lambda: read_snapshot(self.root)),
            ("UPDATE committed_jobs SET state='{}'", lambda: committed_job(self.root, "a")),
        )
        for statement, action in cases:
            database.write_bytes(original)
            with sqlite3.connect(database) as connection:
                connection.execute(statement)
            with self.assertRaises(SnapshotError):
                action()
        database.write_bytes(original)
        for suffix in ("-wal", "-shm", "-journal"):
            path = Path(str(database) + suffix)
            path.symlink_to(database)
            with self.assertRaisesRegex(SnapshotError, "符号链接"):
                read_snapshot(self.root, sid)
            path.unlink()
        self.assertEqual(read_snapshot(self.root)["snapshot_id"], sid)

    def test_real_process_crash_at_publish_boundaries(self):
        a = self.publish(originals(), "a")
        for checkpoint in ("objects_written", "before_commit", "after_commit", "before_status"):
            job = "crash-" + checkpoint
            script = '''
import os,sys
from pathlib import Path
from test_index import originals,DAYS,state
from pmi.index_snapshot import index_root
from pmi.index_update import _save_state,perform_update
from pmi.writer_lock import writer_lock
root=Path(sys.argv[1]);job=sys.argv[2];stage=sys.argv[3]
with writer_lock(root):
    current=state(job);_save_state(root,current)
    perform_update(root,current,DAYS,lambda parent,source,days,job: next(item for item in originals(close="106.00",stamp=f"2026-10-05T{3+2*list(('objects_written','before_commit','after_commit','before_status')).index(stage):02d}:00:00Z") if item.source==source),lambda point: os._exit(71) if point==stage else None)
'''
            process = subprocess.run([sys.executable, "-c", script, str(self.root), job, checkpoint], env={**os.environ, "PYTHONPATH": "python/src:python/tests"})
            self.assertEqual(process.returncode, 71)
            files = {str(path): path.read_bytes() for path in index_root(self.root).rglob("*") if path.is_file()}
            recovered = update_status(self.root)
            self.assertEqual({str(path): path.read_bytes() for path in index_root(self.root).rglob("*") if path.is_file()}, files, "GET恢复绝不写盘")
            committed = checkpoint in ("after_commit", "before_status")
            self.assertEqual(recovered["stage"], "completed" if committed else "interrupted")
            self.assertEqual(committed_job(self.root, job) is not None, committed)
            if not committed:
                self.assertEqual(read_snapshot(self.root)["snapshot_id"], a)
            else:
                self.assertEqual(read_snapshot(self.root)["bars"][0]["close"], "106.00")
            # 每次下一断点前恢复旧内容，使用真实新观察而非重放旧观察。
            a = self.publish(originals(stamp=f"2026-10-05T{4 + 2 * list(('objects_written','before_commit','after_commit','before_status')).index(checkpoint):02d}:00:00Z"), "restore-" + checkpoint)

    def test_update_failure_not_ready_and_lock(self):
        a = self.publish(originals(), "a")
        prior = read_snapshot(self.root)
        for kind in ("tail", "middle", "network", "mismatch"):
            def fetch(parent, source, days, job):
                if kind == "network":
                    raise SnapshotError("synthetic network unavailable")
                items = originals(stamp="2026-10-05T02:00:00Z")
                if kind in ("tail", "middle"):
                    items = mutated(items, 0, lambda raw: raw["data"]["sh000300"]["day"].pop(-1 if kind == "tail" else 100))
                if kind == "mismatch":
                    items = mutated(items, 1, lambda raw: raw["data"][0].update(close="104.99"))
                return next(item for item in items if item.source == source)
            with writer_lock(self.root):
                result = perform_update(self.root, state(kind), DAYS, fetch)
            self.assertEqual(result["result"], "source_not_ready" if kind == "tail" else "failed")
            self.assertEqual(result["stage"], "completed" if kind == "tail" else "failed")
            self.assertIsNone(result["last_success_at"])
            self.assertEqual(read_snapshot(self.root), prior)
        with writer_lock(self.root):
            with self.assertRaisesRegex(SnapshotError, "writer_busy"):
                start_update(self.root, CLOCK)
        self.assertEqual(read_snapshot(self.root)["snapshot_id"], a)

    def test_start_update_and_budget(self):
        items = originals()
        def fetch(parent, source, days, job):
            self.assertEqual(days, DAYS)
            return next(item for item in items if item.source == source)
        result = start_update(self.root, CLOCK, fetch)
        self.assertEqual(result["stage"], "preparing")
        for _ in range(100):
            result = update_status(self.root)
            if result["stage"] not in ("preparing", "fetching_tencent", "fetching_csindex", "validating", "publishing"):
                break
            time.sleep(.01)
        self.assertEqual(result["stage"], "completed")
        ledger = self.root / "budget.jsonl"
        with patch.dict(os.environ, {"WOLF_INDEX_BUDGET_LEDGER": str(ledger)}):
            for index in range(12):
                attempt = {"event": "attempt", "job_id": str(index // 2), "attempt_id": str(index), "source": "eastmoney"}
                _record_attempt(self.root, attempt)
                _record_attempt(self.root, {"event": "finished", "attempt_id": str(index), "bytes": 0})
            with self.assertRaisesRegex(SnapshotError, "预算不足"):
                _record_attempt(self.root, {"event": "attempt", "job_id": "extra", "attempt_id": "extra"})


class IndexBudgetTests(unittest.TestCase):
    """用独立合成账本验证新增授权及原请求/正文边界，不访问真实来源。"""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="thewolf-index-budget-")
        self.root = Path(self.directory.name).resolve()
        self.ledger = self.root / "budget.jsonl"
        self.environment = patch.dict(os.environ, {"WOLF_INDEX_BUDGET_LEDGER": str(self.ledger)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def attempt(self, job_id, attempt_id, completed_bytes=None):
        _record_attempt(self.root, {"event": "attempt", "job_id": job_id,
                                    "attempt_id": attempt_id, "source": "eastmoney"})
        if completed_bytes is not None:
            _record_attempt(self.root, {"event": "finished", "attempt_id": attempt_id,
                                        "bytes": completed_bytes})

    def test_eighth_job_allowed_ninth_rejected_without_rewriting_history(self):
        """第八job可开始并继续第二源；第九job拒绝，原失败计数不清零。"""
        for index in range(7):
            self.attempt(f"job-{index}", f"attempt-{index}", 0)
        history = self.ledger.read_bytes()
        self.attempt("job-7", "eighth", 0)
        self.attempt("job-7", "eighth-second-source", 0)
        self.assertTrue(self.ledger.read_bytes().startswith(history))
        before_rejection = self.ledger.read_bytes()
        with self.assertRaisesRegex(SnapshotError, "预算不足"):
            self.attempt("job-8", "ninth", 0)
        self.assertEqual(self.ledger.read_bytes(), before_rejection)

    def test_twelve_attempt_limit_is_unchanged(self):
        """七job内第十二次可记录，第十三次拒绝，终态失败仍占尝试额度。"""
        for index in range(12):
            self.attempt(f"job-{index % 7}", f"attempt-{index}", 0)
        before_rejection = self.ledger.read_bytes()
        with self.assertRaisesRegex(SnapshotError, "预算不足"):
            self.attempt("job-0", "thirteenth", 0)
        self.assertEqual(self.ledger.read_bytes(), before_rejection)

    def test_body_limit_and_unfinished_reservation_are_unchanged(self):
        """已完成及中断尝试合计64MiB时拒绝新增，未知正文按8MiB预留。"""
        for index in range(8):
            self.attempt("same-job", f"attempt-{index}", 8 * 1024 * 1024 if index < 4 else None)
        before_rejection = self.ledger.read_bytes()
        with self.assertRaisesRegex(SnapshotError, "预算不足"):
            self.attempt("same-job", "over-body-limit", 0)
        self.assertEqual(self.ledger.read_bytes(), before_rejection)


class IndexTransportTests(unittest.TestCase):
    def test_response_limits_and_no_redirect_or_retry(self):
        """替代requests传输，检查真实流读取上限及拒绝压缩/重定向。"""
        class Response:
            def __init__(self, content, headers=None, status=200):
                self.raw = io.BytesIO(content)
                self.headers = headers or {}
                self.status_code = status
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        # BytesIO不接受urllib3的decode_content参数，保留真实读取长度。
        class Raw:
            def __init__(self, content):
                self.stream = io.BytesIO(content)
            def read(self, amount, decode_content=False):
                self.assert_decode = decode_content
                return self.stream.read(amount)
        with tempfile.TemporaryDirectory() as directory, patch("pmi.index_fetch.MAX_BODY", 32):
            root = Path(directory)
            for response, accepted, size in (
                (Response(b"ok", {"Content-Length": "2"}), True, 2),
                (Response(b"x" * 33), False, 32),
                (Response(b"x" * 32, {"Content-Length": "32"}), True, 32),
                (Response(b"bad", {"Content-Encoding": "gzip"}), False, 0),
                (Response(b"bad", status=302), False, 0),
                (Response(b"bad", {"Content-Length": "33"}), False, 0),
            ):
                response.raw = Raw(response.raw.getvalue())
                with patch("pmi.index_fetch.requests.get", return_value=response) as get:
                    if accepted:
                        fetch_once("https://synthetic.invalid", root)
                    else:
                        with self.assertRaises(SnapshotError):
                            fetch_once("https://synthetic.invalid", root)
                    self.assertEqual(get.call_count, 1)
                    self.assertEqual(get.call_args.kwargs["timeout"], (5, 15))
                    self.assertFalse(get.call_args.kwargs["allow_redirects"])
                    self.assertEqual(get.call_args.kwargs["headers"]["Accept-Encoding"], "identity")
                    self.assertEqual(json.loads(root.joinpath("receipt.json").read_text())["bytes"], size)

    def test_deadline_reaps_real_child_and_accounts_failure(self):
        """将截止缩短至50ms；真实休眠子进程被回收，账本保留失败尝试。"""
        actual_popen = subprocess.Popen
        children = []
        def synthetic_child(command, **kwargs):
            child = actual_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)
            children.append(child)
            return child
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            index_root(root).mkdir(parents=True)
            with patch.dict(os.environ, {"WOLF_INDEX_BUDGET_LEDGER": ""}), patch("pmi.index_update.subprocess.Popen", side_effect=synthetic_child), patch("pmi.index_update._FETCH_DEADLINE_SECONDS", .05):
                with self.assertRaisesRegex(SnapshotError, "硬截止"):
                    fetch_bounded(root, "tencent", DAYS, "deadline")
            self.assertIsNotNone(children[0].poll())
            self.assertTrue(children[0].stdin.closed)
            entries = [json.loads(line) for line in index_root(root).joinpath("network-ledger.jsonl").read_text().splitlines()]
            self.assertEqual([row["event"] for row in entries], ["attempt", "finished"])
            self.assertFalse(entries[-1]["success"])

    def test_fetch_parent_eof_exits_without_network(self):
        """真实获取模块使用明确合成requests替身挂起；父管道EOF触发退出。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.joinpath("requests.py").write_text("import time\nclass RequestException(Exception): pass\ndef get(*args, **kwargs):\n    time.sleep(60)\n")
            child = subprocess.Popen([sys.executable, "-m", "pmi.index_fetch", "--source", "tencent", "--start", DAYS[0], "--end", DAYS[-1], "--output", str(root)],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     env={**os.environ, "PYTHONPATH": str(root) + os.pathsep + str(Path("python/src").resolve())})
            try:
                for _ in range(100):
                    if root.joinpath("receipt.json").exists():
                        break
                    time.sleep(.01)
                self.assertTrue(root.joinpath("receipt.json").exists())
                child.stdin.close()
                child.wait(timeout=3)
                self.assertNotEqual(child.returncode, 0)
                self.assertFalse(root.joinpath("original").exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=3)
                if not child.stdin.closed:
                    child.stdin.close()


class IndexApiTests(unittest.TestCase):
    def test_authenticated_boundaries_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "empty"
            environment = {"WOLF_SLICE_DATA_ROOT": str(root), "WOLF_SESSION_TOKEN": "index-test", "WOLF_ALLOWED_HOST": "testserver", "WOLF_ENABLE_INDEX_UPDATE": "0"}
            with patch.dict(os.environ, environment), TestClient(app) as client:
                headers = {"X-Wolf-Session": "index-test"}
                path = "/api/indices/000300"
                for url in (path, path + "/update", path + "/snapshots/" + "a" * 64):
                    self.assertEqual(client.get(url).status_code, 401)
                    self.assertEqual(client.get(url, headers={**headers, "Host": "evil"}).status_code, 403)
                    self.assertEqual(client.get(url, headers={**headers, "Origin": "https://evil"}).status_code, 403)
                self.assertEqual(client.get(path, headers=headers).status_code, 404)
                self.assertEqual(client.get(path + "/snapshots/invalid", headers=headers).status_code, 422)
                self.assertEqual(client.get(path + "/update", headers=headers).json()["stage"], "idle")
                self.assertFalse(root.exists())
                self.assertEqual(client.post(path + "/update", headers=headers, json={}).status_code, 403)
                for extra in ({"url": "http://evil"}, {"date": "2026-10-05"}, {"instrument": "ETF"}):
                    self.assertEqual(client.post(path + "/update", headers=headers, json=extra).status_code, 422)
                self.assertEqual(client.post(path + "/update?date=x", headers=headers, json={}).status_code, 422)
                self.assertFalse(root.exists())
                with writer_lock(root):
                    items = originals();sid = publish(root, build_manifest(DAYS, items), items, state())
                view = client.get(path, headers=headers).json()
                self.assertEqual(view["snapshot_id"], sid)
                self.assertEqual(view["summary"]["daily_change_pct"], "0.00")
                oid = view["evidence"][0]["object_id"]
                self.assertEqual(client.get(path + f"/snapshots/{sid}/evidence/{oid}", headers=headers).status_code, 200)
                self.assertEqual(client.get(path + f"/snapshots/{sid}/evidence/" + "0" * 64, headers=headers).status_code, 404)
                with patch.dict(os.environ, {"WOLF_ENABLE_INDEX_UPDATE": "1", "WOLF_ENABLE_DATA_UPDATE": "1"}), writer_lock(root):
                    self.assertEqual(client.post(path + "/update", headers=headers, json={}).status_code, 409)
                    self.assertEqual(client.post("/api/slice/update", headers=headers, json={}).status_code, 409)
                index_root(root).joinpath("objects", oid).write_bytes(b"tamper")
                self.assertEqual(client.get(path, headers=headers).status_code, 409)


if __name__ == "__main__":
    unittest.main()
