"""六指数契约的合成身份、时间、精度与证据反例；不访问网络或真实根。"""

import copy
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext

from pmi.market_data import SnapshotError
from pmi.market_data.index_catalog import INDICES, get_index, public_index, resolve_index, search_indices
from pmi.market_data.index_history_calendar import (FrozenWindow, _natural_start, complete_window,
                                                   from_manifest_window, validate_window)
from pmi.market_data.index_series_contract import (FIELDS, Original, SourceMismatch, SourceNotReady,
                                                  build_manifest, canonical, digest, parse_evidence,
                                                  rebuild_manifest, source_url, summarize, utc)

NOW = datetime(2026, 10, 28, 1, tzinfo=timezone.utc)
WINDOW = complete_window(NOW)
STAMP = NOW.isoformat()


def encoded(value):
    """直接写出合成 Decimal token，测试原件不经 float。"""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key, ensure_ascii=False) + ":" + encoded(item) for key, item in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(encoded(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def originals(index=INDICES[0], window=WINDOW, *, prices=None):
    """构造全部预期交易日及两种官方布局，不从生产行情派生。"""
    prices = prices or (("100.0049", "110.0050", "90.0000", "105.1234") if index.storage_decimals == 4 else ("100.01", "110.02", "90.00", "105.12"))
    numbers = [Decimal(value) for value in prices]
    compared = [format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f") for value in numbers]
    if index.provider == "csindex":
        official = {"code": "200", "msg": "Success", "success": True,
                    "data": [{"tradeDate": day.replace("-", ""), "indexCode": index.code,
                              "indexNameCn": index.name, "indexNameCnAll": index.full_name,
                              "indexNameEn": index.english_name, "indexNameEnAll": index.english_full_name,
                              **dict(zip(FIELDS, numbers))} for day in window.dates]}
    else:
        opening, high, low, close = numbers
        official = {"code": 200, "message": "", "total": len(window.dates), "sampleDate": "",
                    "data": {"indexCode": index.code, "indexName": index.name, "indexEName": index.english_name,
                             "item": ["timestamp", "current", "high", "open", "low", "close", "chg", "percent", "amount", "volume", "avg"],
                             "data": [[day, close, high, opening, low, close, 0, 0, 0, 0, 0] for day in reversed(window.dates)]}}
    opening, high, low, close = compared
    eastmoney = {"rc": 0, "data": {"code": index.code, "market": index.eastmoney_market, "name": index.name,
                                 "decimal": 2, "dktotal": len(window.dates),
                                 "klines": [f"{day},{opening},{close},{high},{low},0,0,0" for day in window.dates]}}
    return tuple(Original(source, encoded(body).encode(), STAMP, STAMP, source_url(index, source, window))
                 for source, body in zip(index.sources, (official, eastmoney)))


def changed(items, position, mutation):
    """只改原始响应，所有反例走实际契约解析器。"""
    result = list(items)
    body = json.loads(result[position].content, parse_float=Decimal)
    mutation(body)
    result[position] = replace(result[position], content=encoded(body).encode())
    return tuple(result)


def change_east_price(body, row, column, value):
    fields = body["data"]["klines"][row].split(",")
    fields[column] = value
    body["data"]["klines"][row] = ",".join(fields)


class CatalogTests(unittest.TestCase):
    def test_six_exact_identities_and_aliases(self):
        self.assertEqual(len(search_indices()), 6)
        self.assertEqual(search_indices(""), list(INDICES))
        for index in INDICES:
            for query in (index.index_id, *index.aliases):
                self.assertEqual(resolve_index(query), index)
            self.assertEqual(get_index(index.index_id), index)
            self.assertEqual(resolve_index(index.aliases[1].lower()) if "." in index.aliases[1] else index, index)
        self.assertEqual(resolve_index("399300.SZ"), INDICES[0])
        self.assertEqual(resolve_index("399852.sz"), INDICES[2])

    def test_unknown_wrong_market_total_return_and_stock_not_guessed(self):
        for query in ("000001.SZ", "399006.SH", "000852.SZ", "399300.SH", "H00300", "399606", "510300", "000002", "39900", "", None, "沪深"):
            with self.subTest(query=query), self.assertRaises(SnapshotError):
                resolve_index(query)
        self.assertEqual(search_indices("39900"), [])
        self.assertEqual(search_indices("沪深"), [INDICES[0]])
        with self.assertRaises(SnapshotError):
            get_index("000300")

    def test_public_shape_has_no_paths_or_mutable_alias_sharing(self):
        index = INDICES[3]
        public = public_index(index, writable=True)
        self.assertEqual(set(public), {"index_id", "code", "name", "full_name", "provider", "return_type", "frequency", "aliases", "storage_decimals", "source_policy_version", "capabilities", "limitations", "writable"})
        self.assertIsNone(public["full_name"])
        self.assertEqual(public["capabilities"]["amount"], "unavailable")
        public["aliases"].clear()
        self.assertTrue(public_index(index)["aliases"])
        with self.assertRaises(FrozenInstanceError):
            index.code = "000001"
        with self.assertRaises(SnapshotError):
            public_index(replace(index, relative_dir="indices/csi000300"))


class CalendarTests(unittest.TestCase):
    def test_three_natural_years_and_actual_trade_boundaries(self):
        self.assertEqual((WINDOW.anchor_date, WINDOW.natural_start, WINDOW.start, WINDOW.end, len(WINDOW.dates)),
                         ("2026-10-28", "2023-10-28", "2023-10-30", "2026-10-27", 725))
        next_day = complete_window(NOW + timedelta(days=1))
        self.assertEqual((next_day.end, len(next_day.dates)), ("2026-10-28", 726))
        self.assertNotIn("2026-10-29", next_day.dates)
        self.assertIn("2024-09-27", WINDOW.dates)
        for closed in ("2024-02-09", "2024-02-16", "2025-01-28", "2025-02-04", "2026-02-16", "2026-02-23", "2026-10-07"):
            self.assertNotIn(closed, WINDOW.dates)
        for open_day in ("2024-02-19", "2025-02-05", "2026-02-24", "2026-10-08"):
            self.assertIn(open_day, WINDOW.dates)

    def test_timezone_cutoff_and_unknown_year_fail_closed(self):
        before = complete_window(datetime(2026, 10, 28, 15, 59, tzinfo=timezone.utc))
        after = complete_window(datetime(2026, 10, 28, 16, tzinfo=timezone.utc))
        self.assertEqual(before.anchor_date, "2026-10-28")
        self.assertEqual(after.anchor_date, "2026-10-29")
        for clock in (datetime(2026, 10, 28), datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc)):
            with self.assertRaises(SnapshotError):
                complete_window(clock)
        self.assertEqual(_natural_start(date(2024, 2, 29)), date(2021, 2, 28))

    def test_window_immutability_and_manifest_reconstruction(self):
        basis = WINDOW.completion_basis
        basis["sources"][0]["url"] = "wrong"
        self.assertNotEqual(WINDOW.completion_basis, basis)
        for altered in (replace(WINDOW, dates=WINDOW.dates[:-1]), replace(WINDOW, natural_start="2023-10-30"),
                        replace(WINDOW, anchor_date="2026-10-29"), replace(WINDOW, calendar_version="invented")):
            with self.assertRaises(SnapshotError):
                validate_window(altered)
        manifest = {"window": WINDOW.as_dict(), "calendar_dates": list(WINDOW.dates),
                    "calendar_version": WINDOW.calendar_version, "completion_basis": WINDOW.completion_basis}
        self.assertEqual(from_manifest_window(manifest), WINDOW)
        manifest["window"]["actual_count"] = False
        with self.assertRaises(SnapshotError):
            from_manifest_window(manifest)


class SeriesContractTests(unittest.TestCase):
    def test_all_six_full_window_mapping_and_replay(self):
        for index in INDICES:
            with self.subTest(index=index.index_id):
                items = originals(index)
                manifest = build_manifest(index, WINDOW, items)
                self.assertEqual(len(manifest["bars"]), 725)
                self.assertEqual(manifest["instrument"]["id"], index.index_id)
                self.assertEqual([item["source"] for item in manifest["evidence"]], list(index.sources))
                self.assertEqual(rebuild_manifest(index, manifest, items), manifest)
                for item, evidence in zip(items, manifest["evidence"]):
                    self.assertEqual(parse_evidence(index, manifest, item), evidence)
                    self.assertEqual(evidence["object_id"], digest(item.content))
                first = manifest["bars"][0]
                expected = ("100.0049", "110.0050", "90.0000", "105.1234") if index.storage_decimals == 4 else ("100.01", "110.02", "90.00", "105.12")
                self.assertEqual(tuple(first[field] for field in FIELDS), expected)
                if index.storage_decimals == 4:
                    self.assertEqual(first["evidence_refs"][0]["locator"], "data.data[724]")

    def test_official_raw_precision_is_kept_comparison_is_separate(self):
        index = INDICES[3]
        manifest = build_manifest(index, WINDOW, originals(index))
        first = manifest["evidence"][0]["rows"][0]
        self.assertEqual(first["raw_values"]["high"], "110.0050")
        self.assertEqual(first["high"], "110.0050")
        self.assertEqual(first["comparison_values"]["high"], "110.01")
        self.assertEqual(manifest["evidence"][1]["rows"][0]["raw_values"]["high"], "110.01")
        self.assertEqual(manifest["verification"]["mode"], "rounding_aware")
        cs = build_manifest(INDICES[0], WINDOW, originals(prices=("100.0", "110.000", "90", "105.10")))
        self.assertEqual(cs["bars"][0]["high"], "110.00")
        self.assertEqual(cs["evidence"][0]["rows"][0]["raw_values"]["high"], "110.000")

    def test_comparison_does_not_depend_on_ambient_decimal_precision(self):
        index = INDICES[3]
        items = originals(index)
        with localcontext() as context:
            context.prec = 3
            manifest = build_manifest(index, WINDOW, items)
        self.assertEqual(manifest["bars"][0]["close"], "105.1234")
        self.assertEqual(manifest["evidence"][0]["rows"][0]["comparison_values"]["close"], "105.12")

    def test_half_boundaries_and_same_quantization_bin(self):
        index = INDICES[3]
        for raw, comparison in (("100.0049", "100.00"), ("100.0050", "100.01"), ("100.0051", "100.01"), ("100.0040", "100.00"), ("100.0060", "100.01")):
            with self.subTest(raw=raw):
                manifest = build_manifest(index, WINDOW, originals(index, prices=(raw, "110.0000", "90.0000", "105.0000")))
                self.assertEqual(manifest["bars"][0]["open"], raw)
                self.assertEqual(manifest["evidence"][0]["rows"][0]["comparison_values"]["open"], comparison)
        # 0.0001 点跨越半分界也必须报错；并非绝对误差容限。
        items = originals(index, prices=("100.0050", "110.0000", "90.0000", "105.0000"))
        items = changed(items, 1, lambda body: change_east_price(body, 0, 1, "100.00"))
        with self.assertRaises(SourceMismatch) as raised:
            build_manifest(index, WINDOW, items)
        self.assertEqual(raised.exception.details[0]["official_raw"], "100.0050")

    def test_all_differences_are_reported_without_truncation(self):
        items = originals()
        def all_prices(body):
            for row in range(len(WINDOW.dates)):
                for column, value in ((1, "101.01"), (2, "106.12"), (3, "111.02"), (4, "91.00")):
                    change_east_price(body, row, column, value)
        with self.assertRaises(SourceMismatch) as raised:
            build_manifest(INDICES[0], WINDOW, changed(items, 1, all_prices))
        self.assertEqual(len(raised.exception.details), 2900)
        self.assertEqual(raised.exception.details[-1], {"date": WINDOW.end, "field": "close", "official_raw": "105.12", "comparison_value": "105.12", "eastmoney_raw": "106.12"})

    def test_exact_policy_rejects_one_cent_and_extra_nonzero_precision(self):
        items = changed(originals(), 1, lambda body: change_east_price(body, 0, 1, "100.02"))
        with self.assertRaises(SourceMismatch):
            build_manifest(INDICES[0], WINDOW, items)
        for index, value in ((INDICES[0], "100.001"), (INDICES[3], "100.00001")):
            with self.assertRaisesRegex(SnapshotError, "unsupported_price_precision"):
                build_manifest(index, WINDOW, originals(index, prices=(value, "110", "90", "105")))

    def test_summary_uses_official_four_decimal_prices(self):
        refs = [{"source": "cnindex", "object_id": "synthetic", "locator": "synthetic"}]
        bars = [{"trade_date": "2026-10-26", "close": "100.0049", "evidence_refs": refs},
                {"trade_date": "2026-10-27", "close": "100.0100", "evidence_refs": refs}]
        self.assertEqual(summarize(bars)["daily_change_pct"], "0.01")
        # 若先按两位用于计算，这个反例会错误得到 -0.01%。
        bars[0]["close"] = "100.0051"
        bars[1]["close"] = "100.0002"
        self.assertEqual(summarize(bars)["daily_change_pct"], "0.00")
        self.assertEqual(summarize(bars)["input_refs"][0]["close"], "100.0051")
        self.assertIsNone(summarize(bars[:1])["daily_change_pct"])

    def test_tail_missing_only_after_overlap_comparison(self):
        items = changed(originals(), 1, lambda body: body["data"]["klines"].pop())
        with self.assertRaises(SourceNotReady):
            build_manifest(INDICES[0], WINDOW, items)
        with self.assertRaises(SourceMismatch):
            build_manifest(INDICES[0], WINDOW, changed(items, 1, lambda body: change_east_price(body, 0, 1, "100.02")))
        for position in (0, 100):
            with self.assertRaises(SnapshotError) as raised:
                build_manifest(INDICES[0], WINDOW, changed(originals(), 1, lambda body: body["data"]["klines"].pop(position)))
            self.assertNotIsInstance(raised.exception, SourceNotReady)

    def test_two_sources_cannot_complement_missing_days(self):
        items = changed(originals(), 0, lambda body: body["data"].pop(0))
        items = changed(items, 1, lambda body: body["data"]["klines"].pop())
        with self.assertRaises(SnapshotError) as raised:
            build_manifest(INDICES[0], WINDOW, items)
        self.assertNotIsInstance(raised.exception, SourceNotReady)

    def test_descending_cnindex_contiguous_tail_is_not_ready(self):
        index = INDICES[3]
        def truncate(body):
            body["data"]["data"].pop(0)
            body["total"] -= 1
        with self.assertRaises(SourceNotReady):
            build_manifest(index, WINDOW, changed(originals(index), 0, truncate))

    def test_duplicate_json_members_any_depth_reject(self):
        items = originals()
        for old, new in ((b'"code":"200"', b'"code":"200","code":"200"'),
                         (b'"open":100.01', b'"open":100.01,"open":100.02')):
            altered = (replace(items[0], content=items[0].content.replace(old, new, 1)), items[1])
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, altered)

    def test_non_numeric_nonfinite_negative_zero_and_range_reject(self):
        for value in ("100.01", True, None, Decimal("0"), Decimal("-0.00"), Decimal("-1"), Decimal("1000000000001")):
            with self.subTest(value=value), self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, changed(originals(), 0, lambda body: body["data"][0].__setitem__("open", value)))
        items = originals()
        for token in (b"NaN", b"Infinity", b"1e2"):
            altered = (replace(items[0], content=items[0].content.replace(b'"open":100.01', b'"open":' + token, 1)), items[1])
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, altered)

    def test_invalid_ohlc_and_source_prices_shape_reject(self):
        for value in (Decimal("89.99"), Decimal("110.03")):
            with self.assertRaisesRegex(SnapshotError, "invalid_ohlc"):
                build_manifest(INDICES[0], WINDOW, changed(originals(), 0, lambda body: body["data"][0].__setitem__("open", value)))
        with self.assertRaises(SnapshotError):
            build_manifest(INDICES[0], WINDOW, changed(originals(), 1, lambda body: body["data"]["klines"].__setitem__(0, "2023-10-30,100.01,105.12,110.02,90.00")))

    def test_wrong_identity_headers_names_precision_and_fields_reject(self):
        for position, mutate in ((0, lambda body: body["data"][1].__setitem__("indexCode", "000852")),
                                 (0, lambda body: body["data"][1].__setitem__("indexNameCnAll", "全收益指数")),
                                 (0, lambda body: body.__setitem__("success", False)),
                                 (1, lambda body: body["data"].__setitem__("market", 0)),
                                 (1, lambda body: body["data"].__setitem__("decimal", True)),
                                 (1, lambda body: body["data"].__setitem__("name", "其他指数"))):
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, changed(originals(), position, mutate))
        for mutate in (lambda body: body["data"].__setitem__("indexEName", "Unknown"),
                       lambda body: body.__setitem__("total", 726),
                       lambda body: body["data"]["item"].__setitem__(3, "close")):
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[3], WINDOW, changed(originals(INDICES[3]), 0, mutate))

    def test_source_url_order_and_cross_index_originals_reject(self):
        items = originals()
        for altered in ((items[1], items[0]), (items[0], items[0]), items[:1],
                        (replace(items[0], url=items[0].url + "&fqt=1"), items[1]),
                        (replace(items[0], source="tencent"), items[1])):
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, altered)
        with self.assertRaises(SnapshotError):
            build_manifest(INDICES[2], WINDOW, items)
        self.assertIn("startDate=20231030", source_url(INDICES[0], "csindex", WINDOW))
        self.assertNotIn("20231028", source_url(INDICES[0], "csindex", WINDOW))

    def test_duplicate_out_of_window_nontrading_and_order_reject(self):
        for mutate in (lambda body: body["data"].append(copy.deepcopy(body["data"][0])),
                       lambda body: body["data"].reverse(),
                       lambda body: body["data"][0].__setitem__("tradeDate", "20231028"),
                       lambda body: body["data"][-1].__setitem__("tradeDate", "20261028"),
                       lambda body: body["data"][0].__setitem__("tradeDate", "20230229"),
                       lambda body: body.__setitem__("data", [])):
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, changed(originals(), 0, mutate))

    def test_retrieval_times_excluded_from_content_hash_but_validated(self):
        items = originals()
        manifest = build_manifest(INDICES[0], WINDOW, items)
        later = tuple(replace(item, started_at="2026-10-29T00:00:00Z", completed_at="2026-10-29T00:00:01Z") for item in items)
        self.assertEqual(canonical(build_manifest(INDICES[0], WINDOW, later)), canonical(manifest))
        for stamp in ("2026-10-29T00:00:00", "invalid"):
            with self.assertRaises(SnapshotError):
                build_manifest(INDICES[0], WINDOW, (replace(items[0], started_at=stamp), items[1]))
        with self.assertRaises(SnapshotError):
            build_manifest(INDICES[0], WINDOW, (replace(items[0], completed_at="2026-01-01T00:00:00Z"), items[1]))
        self.assertEqual(utc("2026-10-28T09:00:00+08:00"), "2026-10-28T01:00:00Z")

    def test_full_replay_rejects_each_stored_fact_tampering(self):
        items = originals(INDICES[3])
        manifest = build_manifest(INDICES[3], WINDOW, items)
        mutations = (lambda m: m.__setitem__("schema_version", "v9"),
                     lambda m: m.__setitem__("source_policy_version", "relaxed"),
                     lambda m: m.__setitem__("catalog_version", "unknown"),
                     lambda m: m["window"].__setitem__("anchor_date", "2026-10-29"),
                     lambda m: m["calendar_dates"].pop(),
                     lambda m: m["bars"][0].__setitem__("open", "100.00"),
                     lambda m: m["bars"][0]["evidence_refs"][0].__setitem__("locator", "wrong"),
                     lambda m: m["evidence"][0]["rows"][0]["raw_values"].__setitem__("high", "110.0049"),
                     lambda m: m["summary"].__setitem__("close", "105.12"),
                     lambda m: m["verification"].__setitem__("comparison_rounding", None),
                     lambda m: m.__setitem__("observation_id", "not_content"))
        for mutate in mutations:
            altered = copy.deepcopy(manifest)
            mutate(altered)
            with self.assertRaises(SnapshotError):
                rebuild_manifest(INDICES[3], altered, items)

    def test_evidence_response_rejects_forgery(self):
        index = INDICES[0]
        items = originals()
        manifest = build_manifest(index, WINDOW, items)
        manifest["evidence"][0]["rows"][0]["comparison_values"]["open"] = "999.00"
        with self.assertRaises(SnapshotError):
            parse_evidence(index, manifest, items[0])


if __name__ == "__main__":
    unittest.main()
