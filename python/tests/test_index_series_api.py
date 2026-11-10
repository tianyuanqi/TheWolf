"""参数化指数的真实ASGI边界与公共门面联调；来源全部为隔离合成原件。"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from pmi.api import create_app
from pmi.market_data import MarketData, SnapshotError
from pmi.market_data.index_catalog import INDICES
from sqlite_fixture import price_writer as writer_lock, initialize as initialize_sqlite
from pmi.service_config import ServiceConfig
from http_test_support import ReadClient, disk
from test_index_series_contract import NOW, originals


class SeriesClient(ReadClient):
    def __init__(self, root, write_ids=(), startup_ids=()):
        self.config = ServiceConfig(root, 18080, ("http://127.0.0.1:18081",),
                                    index_write_ids=tuple(write_ids), startup_index_ids=tuple(startup_ids))
        self.app = create_app(self.config)
        self.headers = {"host": self.config.authority, "origin": self.config.allowed_origins[0], "x-wolf-client": "1",
                        "x-wolf-expected-instance": self.app.state.boundary.instance,
                        "x-wolf-expected-config": self.config.index_config_id, "content-type": "application/json"}

    def post(self, index_id, request_id="series-request", **kwargs):
        return self.request(f"/api/index-series/{index_id}/update", "POST", body=b"{}",
                            headers={"x-wolf-request-id": request_id, **kwargs.pop("headers", {})}, **kwargs)

    def lookup(self, index_id, request_id="series-request"):
        return self.request(f"/api/index-series/operations/{request_id}?instance_id={self.app.state.boundary.instance}"
                            f"&config_id={self.config.index_config_id}&operation=index.series.update&index_id={index_id}")

    def finish(self, index_id, request_id="series-request"):
        if not self.config.market_data.wait_updates(10):
            raise AssertionError("合成任务没有退出")
        return self.lookup(index_id, request_id).json()


@contextmanager
def sources(gate=None):
    calls = []
    def fetch(parent, index, source, window, *args, **kwargs):
        if gate is not None and not gate.wait(4):
            raise AssertionError("合成来源门闩未释放")
        calls.append((index.index_id, source))
        return next(item for item in originals(index, window) if item.source == source)
    with patch("pmi.market_data.datetime") as clock, patch("pmi.market_data.index_series_update.fetch_bounded", side_effect=fetch):
        clock.now.return_value = NOW
        yield calls


class IndexSeriesAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        initialize_sqlite(self.root)

    def client(self, *args, **kwargs):
        client = SeriesClient(self.root, *args, **kwargs)
        self.addCleanup(client.app.state.updates.close)
        return client

    def test_catalog_readiness_and_empty_get_create_nothing(self):
        client = self.client()
        before = disk(self.root)
        ready = client.request("/api/index-series/session")
        self.assertEqual(ready.status, 200)
        self.assertEqual(ready.headers["x-wolf-config"], client.config.index_config_id)
        self.assertNotEqual(client.config.index_config_id, client.config.config_id)
        result = client.request("/api/index-series/catalog?query=399852.sz")
        self.assertEqual(result.status, 200)
        self.assertEqual(result.json()["resolved_index_id"], "csi:000852:price")
        self.assertEqual(len(client.request("/api/index-series/catalog").json()["indices"]), 6)
        for index in INDICES:
            self.assertEqual(client.request(f"/api/index-series/{index.index_id}").status, 404)
            status = client.request(f"/api/index-series/{index.index_id}/update")
            self.assertEqual(status.status, 200)
            self.assertEqual(status.json()["stage"], "idle")
            self.assertFalse(status.json()["enabled"])
        self.assertEqual(disk(self.root), before)

    def test_write_permission_binding_and_legacy_flag_do_not_expand(self):
        allowed, other = INDICES[0].index_id, INDICES[3].index_id
        client = self.client((allowed,))
        before = disk(self.root)
        self.assertEqual(client.post(other).status, 403)
        self.assertEqual(client.post(allowed, headers={"x-wolf-expected-config": client.config.config_id}).status, 409)
        self.assertEqual(client.post(allowed, headers={"x-wolf-expected-instance": "00000000-0000-4000-8000-000000000000"}).status, 409)
        self.assertEqual(client.request("/api/index-series/000001/update", "POST", headers={"x-wolf-request-id": "wrong-domain"}, body=b"{}").status, 422)
        self.assertEqual(disk(self.root), before)
        disabled = self.client(())
        self.assertEqual(disabled.post(allowed).status, 403)
        with self.assertRaises(SnapshotError):
            disabled.config.market_data.update(allowed)

    def test_duplicate_and_cross_index_or_legacy_request_do_not_repeat_business(self):
        first, second = INDICES[3].index_id, INDICES[4].index_id
        client = self.client((first, second))
        gate = threading.Event()
        called = []
        real_update = MarketData.update
        def tracked(data, code, **kwargs):
            called.append(code)
            return real_update(data, code, **kwargs)
        with sources(gate) as fetches, patch.object(MarketData, "update", tracked):
            try:
                initial = client.post(first)
                self.assertEqual(initial.status, 202, initial.body)
                self.assertEqual(client.post(first).json(), initial.json())
                conflict = client.post(second)
                self.assertEqual(conflict.status, 409)
                self.assertEqual(conflict.json()["detail"]["code"], "request_id_conflict")
                legacy = client.request("/api/indices/000300/update", "POST", body=b"{}", headers={
                    "x-wolf-request-id": "series-request", "x-wolf-expected-config": client.config.config_id})
                self.assertEqual(legacy.status, 404)
                self.assertEqual(legacy.json()["detail"]["code"], "route_not_found")
                self.assertEqual(client.lookup(second).json()["state"], "unknown")
                self.assertEqual(called, [first])
            finally:
                gate.set()
            result = client.finish(first)
        self.assertEqual(result["state"], "completed", result)
        self.assertEqual(len(fetches), 2)
        self.assertEqual(client.post(first).json(), initial.json())
        view = client.request(f"/api/index-series/{first}")
        self.assertEqual(view.status, 200, view.body)
        self.assertRegex(view.json()["snapshot"]["bars"][0]["close"], r"\.[0-9]{4}$")

    def test_six_indices_fixed_evidence_range_and_offline_reopen(self):
        ids = tuple(item.index_id for item in INDICES)
        client = self.client(ids)
        views = {}
        with sources() as calls:
            for index_id in ids:
                request_id = "save-" + index_id.replace(":", "-")
                accepted = client.post(index_id, request_id)
                self.assertEqual(accepted.status, 202, accepted.body)
                result = client.finish(index_id, request_id)
                self.assertEqual(result["state"], "completed", result)
                reply = client.request(f"/api/index-series/{index_id}")
                self.assertEqual(reply.status, 200, reply.body)
                view = reply.json()
                self.assertEqual(view["index_id"], index_id)
                self.assertEqual(view["snapshot"]["instrument"]["id"], index_id)
                self.assertEqual(len(view["snapshot"]["bars"]), 725)
                views[index_id] = view
            self.assertEqual(len(calls), 12)
        self.assertTrue(client.app.state.updates.close())
        offline = self.client()
        before = disk(self.root)
        for index_id in ids:
            request_id = "save-" + index_id.replace(":", "-")
            self.assertEqual(offline.lookup(index_id, request_id).json()["state"], "unknown")
        with patch("pmi.market_data.index_series_update.fetch_bounded", side_effect=AssertionError("只读不得采集")):
            for index_id, view in views.items():
                snapshot = view["snapshot"]
                fixed = f"/api/index-series/{index_id}/snapshots/{snapshot['snapshot_id']}"
                self.assertEqual(offline.request(fixed).json(), view)
                for evidence in snapshot["evidence"]:
                    reply = offline.request(fixed + "/evidence/" + evidence["object_id"])
                    self.assertEqual(reply.status, 200, reply.body)
                    self.assertEqual(reply.json()["index_id"], index_id)
                start, end = snapshot["bars"][-3]["trade_date"], snapshot["bars"][-1]["trade_date"]
                reply = offline.request(f"/api/index-series/{index_id}/range?start={start}&end={end}&fields=close&snapshot_id={snapshot['snapshot_id']}")
                self.assertEqual(reply.status, 200, reply.body)
                self.assertEqual([r["values"]["close"] for r in reply.json()["rows"]], [r["close"] for r in snapshot["bars"][-3:]])
                self.assertEqual(offline.request(f"/api/index-series/{index_id}/range?start=2023-01-01&end={end}").status, 422)
                other = next(key for key in views if key != index_id)
                self.assertEqual(offline.request(f"/api/index-series/{other}/snapshots/{snapshot['snapshot_id']}").status, 404)
        self.assertEqual(disk(self.root), before)

    def test_startup_stops_after_failed_index_without_next_source(self):
        ids = (INDICES[0].index_id, INDICES[3].index_id)
        client = self.client(ids, ids)
        with patch("pmi.market_data.datetime") as clock, patch(
                "pmi.market_data.index_series_update.fetch_bounded", side_effect=OSError("isolated source failure")) as fetch:
            clock.now.return_value = NOW
            client.app.state.updates.start_startup()
            client.app.state.updates._startup_thread.join(8)
            self.assertFalse(client.app.state.updates._startup_thread.is_alive())
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(len(client.app.state.updates.startup_results), 1)
            self.assertEqual(client.app.state.updates.startup_results[0]["stage"], "failed")
            self.assertEqual(client.config.market_data.status(ids[1])["stage"], "idle")

    def test_publication_uncertainty_stays_unknown_after_status_and_duplicate_post(self):
        from pmi.market_data.storage import database as storage
        index_id, other = INDICES[0].index_id, INDICES[3].index_id
        client = self.client((index_id, other))
        with sources():
            self.assertEqual(client.post(index_id, "initial-publication").status, 202)
            self.assertEqual(client.finish(index_id, "initial-publication")["state"], "completed")
        real_commit = storage._commit
        failed, notifications = [], []
        real_notify = client.app.state.updates._series_notify
        def commit(connection):
            published = connection.execute("SELECT count(*) FROM operation WHERE domain_id='price-v2' AND state='completed'").fetchone()[0]
            real_commit(connection)
            if published == 2 and not failed:
                failed.append(True)
                raise OSError('synthetic lost COMMIT acknowledgement')
        def notify(code, state):
            notifications.append((code, state["stage"]))
            return real_notify(code, state)
        with sources() as fetches, patch.object(storage, "_commit", side_effect=commit), \
                patch.object(client.app.state.updates, "_series_notify", side_effect=notify):
            accepted = client.post(index_id, "uncertain-publication")
            self.assertEqual(accepted.status, 202, accepted.body)
            result = client.finish(index_id, "uncertain-publication")
            self.assertEqual(result["state"], "unknown", result)
            self.assertIsNone(result["business_status"])
            self.assertEqual(result["job_id"], accepted.json()["job_id"])
            self.assertNotIn((index_id, "completed"), notifications)
            self.assertEqual(len(fetches), 2)
            self.assertEqual(len(failed), 1)
            self.assertFalse((self.root / "facts.sqlite-journal").exists())
            # A readable committed job cannot retroactively certify this request's durability.
            status = client.request(f"/api/index-series/{index_id}/update")
            self.assertEqual(status.status, 200, status.body)
            self.assertEqual(status.json()["stage"], "completed")
            self.assertEqual(client.lookup(index_id, "uncertain-publication").json(), result)
            self.assertEqual(client.post(index_id, "uncertain-publication").json(), accepted.json())
            self.assertEqual(len(fetches), 2)
            self.assertEqual(client.request(f"/api/index-series/{other}/update").json()["stage"], "idle")

    def test_retired_files_are_not_read_or_rewritten(self):
        # An old database is deliberately not valid SQLite: a v2 GET must not open it.
        old = self.root / "indices/csi000300"
        old.mkdir(parents=True)
        (old / "index.sqlite").write_bytes(b"retired synthetic database")
        (self.root / "slice.sqlite").write_bytes(b"retired synthetic stock")
        before = disk(self.root)
        client = self.client()
        self.assertEqual(client.request("/api/indices/000300").status, 404)
        self.assertEqual(client.request("/api/slice").status, 404)
        self.assertEqual(client.request("/api/index-series/csi:000300:price").status, 404)
        self.assertEqual(disk(self.root), before)

    def test_explicit_startup_uses_same_path_and_skips_covered(self):
        ids = (INDICES[0].index_id, INDICES[3].index_id)
        client = self.client(ids, ids)
        with sources() as calls:
            client.app.state.updates.start_startup()
            client.app.state.updates._startup_thread.join(12)
            self.assertFalse(client.app.state.updates._startup_thread.is_alive())
            self.assertEqual(len(calls), 4)
            self.assertEqual([r["result"] for r in client.app.state.updates.startup_results], ["business_changed"] * 2)
        self.assertTrue(client.app.state.updates.close())
        reopened = self.client(ids, ids)
        before = disk(self.root)
        with sources() as calls:
            reopened.app.state.updates.start_startup()
            reopened.app.state.updates._startup_thread.join(8)
            self.assertFalse(reopened.app.state.updates._startup_thread.is_alive())
            self.assertEqual(calls, [])
            self.assertEqual([r["result"] for r in reopened.app.state.updates.startup_results], ["already_covered"] * 2)
        self.assertEqual(disk(self.root), before)
