"""新指数同源HTTP结构、旧协议冻结及十进制无损投影的离线验证。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import tempfile
import unittest
from sqlite_fixture import initialize
from http_test_support import disk

from jsonschema import Draft202012Validator

from pmi.http_contract import ContractResponseError, response_value, verify_resources
from pmi.market_data.index_catalog import INDICES, public_index
from pmi.market_data.index_history_calendar import complete_window
from pmi.market_data.index_series_contract import Original, build_manifest, canonical, source_url


ROOT = Path(__file__).resolve().parents[2]
STAMP = "2026-10-28T01:00:00Z"
WINDOW = complete_window(datetime(2026, 10, 28, 1, tzinfo=timezone.utc))
# 来自本任务改动前全部旧paths/components及顶层语义的规范结构，非新生成物摘要。
LEGACY_STRUCTURE_SHA256 = "654ac63cd39da34047767a0416898f785a43ca2d36e22de0542d010172460fc5"


def synthetic_originals(index) -> tuple[Original, Original]:
    """以固定人工价格构造完整双源三年窗口，不访问网络或金融数据根。"""
    prices = ("100.1250", "102.3450", "99.9950", "101.5550") if index.storage_decimals == 4 else (
        "100.12", "102.34", "99.99", "101.55")
    comparison = ("100.13", "102.35", "100.00", "101.56") if index.storage_decimals == 4 else prices
    opening, high, low, close = prices
    if index.provider == "csindex":
        identity = json.dumps({"indexCode": index.code, "indexNameCn": index.name,
            "indexNameCnAll": index.full_name, "indexNameEn": index.english_name,
            "indexNameEnAll": index.english_full_name}, ensure_ascii=False)[:-1]
        rows = [identity + ',"tradeDate":"' + day.replace("-", "") + '",'
                + f'"open":{opening},"high":{high},"low":{low},"close":{close}' + "}"
                for day in WINDOW.dates]
        content = '{"code":"200","msg":"Success","success":true,"data":[' + ",".join(rows) + "]}"
    else:
        rows = ['["' + day + f'",0,{high},{opening},{low},{close},0,0,0,0,0]' for day in reversed(WINDOW.dates)]
        identity = json.dumps({"indexCode": index.code, "indexName": index.name,
            "indexEName": index.english_name,
            "item": ["timestamp", "current", "high", "open", "low", "close", "chg", "percent", "amount", "volume", "avg"]},
            ensure_ascii=False)[:-1]
        content = '{"code":200,"message":"","total":' + str(len(rows)) + ',"data":' + identity + ',"data":[' + ",".join(rows) + "]}}"
    opening, high, low, close = comparison
    secondary = json.dumps({"rc": 0, "data": {"code": index.code, "name": index.name,
        "market": index.eastmoney_market, "decimal": 2,
        "klines": [f"{day},{opening},{close},{high},{low},0,0,0" for day in WINDOW.dates]}}, ensure_ascii=False)
    return tuple(Original(source, payload.encode(), STAMP, STAMP, source_url(index, source, WINDOW))
                 for source, payload in zip(index.sources, (content, secondary)))


def synthetic_view(index) -> dict:
    """将真实领域构造结果接入冻结的HTTP观察外壳，供纯结构与无损检查。"""
    originals = synthetic_originals(index)
    manifest = build_manifest(index, WINDOW, originals)
    snapshot_id = hashlib.sha256(canonical(manifest)).hexdigest()
    retrieval = {"index_id": index.index_id, "snapshot_id": snapshot_id, "observed_at": STAMP,
        "sources": [{"source": original.source, "object_id": hashlib.sha256(original.content).hexdigest(),
                     "url": original.url, "started_at": STAMP, "completed_at": STAMP, "published_at": None}
                    for original in originals]}
    return {"index_id": index.index_id, "format": "v2", "snapshot": {
        **manifest, "snapshot_id": snapshot_id, "observation_id": "b" * 64, "retrieval": retrieval}}


class IndexSeriesHttpContractTests(unittest.TestCase):
    """金融语义由领域测试验证；这里拒绝字段漂移、丢精度和旧协议扩大。"""

    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads((ROOT / "contracts/openapi.yaml").read_text())
        cls.schemas = json.loads(files("pmi.http_contract").joinpath("schemas.json").read_text())

    def validator(self, name: str) -> Draft202012Validator:
        return Draft202012Validator({**self.schemas, "$ref": "#/$defs/" + name})

    def test_current_structure_excludes_retired_contracts_and_resources_match(self):
        self.assertEqual(self.spec["info"]["version"], "3.0.0")
        self.assertNotIn("/api/slice", self.spec["paths"])
        self.assertNotIn("/api/indices/000300", self.spec["paths"])
        self.assertNotIn("OperationKind", self.spec["components"]["schemas"])
        self.assertNotIn("writes", self.spec["components"]["schemas"]["Ready"]["properties"])
        verify_resources()

    def test_six_full_windows_and_evidence_keep_official_precision(self):
        for index in INDICES:
            with self.subTest(index_id=index.index_id):
                view = synthetic_view(index)
                original = deepcopy(view)
                self.assertEqual(response_value("IndexSeriesView", view), original)
                self.assertEqual(view, original)
                snapshot = view["snapshot"]
                self.assertEqual(len(snapshot["bars"]), len(WINDOW.dates))
                expected_close = "101.5550" if index.storage_decimals == 4 else "101.55"
                self.assertEqual(snapshot["bars"][0]["close"], expected_close)
                evidence = {"index_id": index.index_id, "format": "v2", "evidence": {
                    **snapshot["evidence"][0], "snapshot_id": snapshot["snapshot_id"],
                    "observation_id": snapshot["observation_id"], "retrieval": snapshot["retrieval"]["sources"][0],
                    "verification": snapshot["verification"], "text_preview": "合成证据", "preview_truncated": False}}
                self.assertEqual(response_value("IndexSeriesEvidenceView", evidence), evidence)
                self.assertEqual(evidence["evidence"]["rows"][0]["raw_values"]["close"], expected_close)
                self.assertEqual(evidence["evidence"]["rows"][0]["comparison_values"]["close"],
                                 "101.56" if index.storage_decimals == 4 else "101.55")

    def test_new_contract_rejects_precision_loss_missing_provenance_and_extra_fields(self):
        view = synthetic_view(INDICES[3])
        mutations = (
            lambda value: value["snapshot"]["bars"][0].update(close=101.555),
            lambda value: value["snapshot"]["bars"][0].update(close="101.555"),
            lambda value: value["snapshot"]["evidence"][0]["rows"][0].pop("raw_values"),
            lambda value: value["snapshot"]["completion_basis"]["sources"][0].pop("evidence_sha256"),
            lambda value: value["snapshot"]["verification"].update(tolerance="0.005"),
            lambda value: value.update(format="legacy_v1"),
        )
        for mutate in mutations:
            broken = deepcopy(view)
            mutate(broken)
            with self.subTest(mutation=mutate), self.assertRaises(ContractResponseError):
                response_value("IndexSeriesView", broken)

    def test_descriptor_ready_and_catalog_validate_without_creating_data(self):
        from pmi.service_config import ServiceConfig
        with tempfile.TemporaryDirectory(prefix="thewolf-series-contract-") as directory:
            root = Path(directory).resolve(); initialize(root); before=disk(root)
            config = ServiceConfig(root, 18080, ("http://127.0.0.1:18081",),
                                   index_write_ids=(INDICES[3].index_id,))
            descriptor = config.public_index_descriptor()
            self.assertEqual(response_value("IndexSeriesDescriptor", descriptor), descriptor)
            ready = {key: value for key, value in descriptor.items() if key != "endpoint"}
            ready.update(status="ready", instance_id="11111111-1111-4111-8111-111111111111")
            self.assertEqual(response_value("IndexSeriesReady", ready), ready)
            self.assertFalse(self.validator("Ready").is_valid(ready))
            catalog = config.market_data.index_catalog()
            self.assertEqual(response_value("IndexSeriesCatalog", catalog), catalog)
            self.assertEqual(catalog["indices"], [public_index(index, index.index_id == INDICES[3].index_id) for index in INDICES])
            self.assertEqual(disk(root),before)
        self.assertFalse(root.exists())

    def test_status_retains_every_mismatch_and_cannot_enter_legacy_operation(self):
        status = {"index_id": INDICES[3].index_id, "job_id": "synthetic-job", "trigger": "manual",
            "stage": "failed", "result": "failed", "started_at": STAMP, "finished_at": STAMP,
            "last_success_at": None, "target_start": WINDOW.start, "target_end": WINDOW.end,
            "previous_snapshot_id": None, "snapshot_id": None, "observation_id": None,
            "message": "合成差异", "added_dates": [], "revised_dates": [], "enabled": True,
            "differences": [{"date": day, "field": field, "official_raw": "100.1250",
                             "comparison_value": "100.13", "eastmoney_raw": "100.12"}
                            for day in WINDOW.dates for field in ("open", "high", "low", "close")]}
        self.assertEqual(response_value("IndexSeriesUpdateStatus", status), status)
        identity = {"instance_id": "11111111-1111-4111-8111-111111111111", "config_id": "a" * 64,
                    "request_id": "synthetic-request", "operation": "index.series.update", "index_id": INDICES[3].index_id}
        result = {**identity, "state": "failed", "job_id": status["job_id"], "reused_job": False,
                  "business_status": status, "rejection": None}
        self.assertEqual(response_value("IndexSeriesOperationResult", result), result)
        self.assertNotIn("OperationResult", self.schemas["$defs"])
        accepted_status = {**status, "stage": "preparing", "result": None, "finished_at": None, "differences": []}
        accepted = {**result, "state": "accepted", "business_status": accepted_status}
        self.assertEqual(response_value("IndexSeriesAcceptedOperation", accepted), accepted)
        unknown = {**identity, "state": "unknown", "job_id": None, "reused_job": None, "business_status": None, "rejection": None}
        self.assertEqual(response_value("IndexSeriesOperationResult", unknown), unknown)
        rejected = {**unknown, "state": "rejected", "rejection": {"status": 409,
            "body": {"detail": {"code": "index_series_unavailable", "message": "合成拒绝"}}}}
        self.assertEqual(response_value("IndexSeriesOperationResult", rejected), rejected)

    def test_new_routes_are_bound_and_have_uncached_metadata_preflight(self):
        paths = list(self.spec["paths"])
        dynamic = paths.index("/api/index-series/{index_id}")
        for path in ("/api/index-series/session", "/api/index-series/catalog", "/api/index-series/operations/{request_id}"):
            self.assertLess(paths.index(path), dynamic)
        new_routes = {path: item for path, item in self.spec["paths"].items() if path.startswith("/api/index-series")}
        self.assertEqual(set(new_routes), {"/api/index-series/session", "/api/index-series/catalog", "/api/index-series/operations/{request_id}",
            "/api/index-series/{index_id}", "/api/index-series/{index_id}/update", "/api/index-series/{index_id}/range",
            "/api/index-series/{index_id}/snapshots/{snapshot_id}", "/api/index-series/{index_id}/snapshots/{snapshot_id}/evidence/{object_id}",
            "/api/index-series/{index_id}/snapshots/{snapshot_id}/calculations", "/api/index-series/{index_id}/view"})
        for path, item in new_routes.items():
            self.assertEqual(item["options"]["responses"]["204"]["headers"]["Access-Control-Max-Age"]["schema"]["const"], "0")
            for method in ("get", "post"):
                if method not in item:
                    continue
                operation = item[method]
                refs = {parameter.get("$ref") for parameter in operation["parameters"]}
                self.assertIn("#/components/parameters/ClientMarker", refs)
                if path != "/api/index-series/session":
                    self.assertTrue({"#/components/parameters/ExpectedInstance", "#/components/parameters/ExpectedConfig"} <= refs)
                self.assertIn("wolf-index-config-v2", operation["x-wolf-response-context"])
                self.assertEqual(set(operation["responses"]["500"]["content"]), {"text/plain"})
        post = new_routes["/api/index-series/{index_id}/update"]["post"]
        self.assertIn({"$ref": "#/components/parameters/RequestId"}, post["parameters"])
        self.assertEqual(post["requestBody"]["content"]["application/json"]["schema"], {"$ref": "#/components/schemas/UpdateRequest"})

    def test_assembled_read_errors_status_lookup_and_preflight_match_contract(self):
        from http_test_support import ReadClient
        with tempfile.TemporaryDirectory(prefix="thewolf-series-asgi-") as directory:
            root = Path(directory).resolve(); initialize(root); before=disk(root)
            client = ReadClient(root)
            client.headers["x-wolf-expected-config"] = client.config.index_config_id
            base = "/api/index-series/" + INDICES[3].index_id
            for path, operation, expected in (
                ("/api/index-series/session", "indexSeriesReady", 200),
                ("/api/index-series/catalog?query=399006", "indexSeriesCatalog", 200),
                (base, "currentIndexSeries", 404),
                (base + "/update", "indexSeriesStatus", 200),
                (base + "/range?start=2026-10-27&end=2026-10-26", "indexSeriesRange", 422),
                (base + "/range?start=2026-10-26&end=2026-10-27&fields=close,close", "indexSeriesRange", 422),
            ):
                with self.subTest(path=path):
                    reply = client.request(path)
                    self.assertEqual(reply.status, expected, reply.body)
                    client.app.state.boundary.response(operation, reply.status, reply.json())
                    self.assertEqual(reply.headers["x-wolf-config"], client.config.index_config_id)
            lookup = ("/api/index-series/operations/missing?instance_id=" + client.app.state.boundary.instance
                      + "&config_id=" + client.config.index_config_id + "&operation=index.series.update&index_id=" + INDICES[3].index_id)
            reply = client.request(lookup)
            self.assertEqual(reply.status, 200, reply.body)
            self.assertEqual(reply.json()["state"], "unknown")
            client.app.state.boundary.response("indexSeriesOperationResult", 200, reply.json())
            preflight = client.request(base + "/update", "OPTIONS", headers={
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type,x-wolf-client,x-wolf-expected-instance,x-wolf-expected-config,x-wolf-request-id"})
            self.assertEqual(preflight.status, 204, preflight.body)
            self.assertEqual(preflight.headers["access-control-max-age"], "0")
            denied = client.request(base + "/update", "POST", headers={"content-type": "application/json"}, body=b"{}")
            self.assertEqual(denied.status, 403, denied.body)
            client.app.state.boundary.response("startIndexSeries", 403, denied.json())
            self.assertEqual(disk(root),before)
        self.assertFalse(root.exists())

    def test_old_view_cannot_enter_current_series_contract(self):
        forged = {"index_id": "csi:000300:price", "format": "legacy_v1", "snapshot": {}}
        with self.assertRaises(ContractResponseError):
            response_value("IndexSeriesView", forged)
        self.assertNotIn("IndexSeriesLegacyView", self.spec["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
