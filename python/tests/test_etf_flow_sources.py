"""来源A仅用合成响应验证；具体基金身份始终由独立假配置提供。"""
from copy import deepcopy
import hashlib
import unittest

from etf_flow_fixture import AT, END, configuration, sample
from pmi.market_data.etf_flow.calendar import preceding_window
from pmi.market_data.etf_flow.model import Configuration, FlowError, canonical
from pmi.market_data.etf_flow.sources import QUOTE_QUERY, SHARES_QUERY, parse, plan, request_for, verify_nav_pages


def parsed(member, request, value):
    raw = canonical(value)
    return parse(member, request, raw, hashlib.sha256(raw).hexdigest(), AT)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.config = Configuration.parse(configuration("multiple"))
        self.member = self.config.pools[0].members[0]

    def test_official_shares_and_quote_units_precision(self):
        request = request_for(self.member, "shares", END, END)
        body = {"sqlId": SHARES_QUERY, "result": [{"SEC_CODE": self.member.code, "STAT_DATE": END, "TOT_VOL": "12.34"}]}
        result = parsed(self.member, request, body)
        self.assertEqual(result.rows[0].value("shares"), 123400)
        self.assertEqual(result.rows[0].fields["shares"].source.original_unit, "万份")
        request = request_for(self.member, "quote", END, END)
        quote = {"sqlId": QUOTE_QUERY, "result": [{"SEC_CODE": self.member.code, "TX_DATE": END.replace("-", ""),
            "DATE_TYPE": "D", "CLOSE_PRICE": "2.345", "TRADE_AMT": "123.45", "TRADE_VOL": "67.89"}]}
        row = parsed(self.member, request, quote).rows[0]
        self.assertEqual(row.value("turnover"), 1234500)
        self.assertEqual(row.value("volume"), 678900)
        self.assertEqual(str(row.value("close")), "2.345")
        quote["result"][0]["TRADE_AMT"] = "123.456"
        with self.assertRaises(FlowError):
            parsed(self.member, request, quote)

    def test_mismatch_empty_duplicate_and_changed_source_rejected(self):
        request = request_for(self.member, "shares", END, END)
        body = {"sqlId": SHARES_QUERY, "result": [{"SEC_CODE": self.member.code, "STAT_DATE": END, "TOT_VOL": "12.34"}]}
        for key, value in (("SEC_CODE", self.config.pools[0].members[-1].code), ("STAT_DATE", "2026-11-03"), ("TOT_VOL", "NaN")):
            changed = deepcopy(body)
            changed["result"][0][key] = value
            with self.assertRaises(FlowError):
                parsed(self.member, request, changed)
        for records in ([], body["result"] * 2):
            with self.assertRaises(FlowError):
                parsed(self.member, request, {"sqlId": SHARES_QUERY, "result": records})
        with self.assertRaises(FlowError):
            parse(self.member, request, canonical(body), "0" * 64, AT)

    def nav(self, dates, page, total):
        return {"ErrCode": 0, "PageSize": 20, "PageIndex": page, "TotalCount": total,
                "Data": {"LSJZList": [{"FSRQ": d, "DWJZ": "1.2345", "LJJZ": "99.9999"} for d in dates]}}

    def test_nav_small_pages_identity_bound_url_and_unit_not_cumulative(self):
        dates = preceding_window(END, 21)
        reverse = list(reversed(dates))
        first = parsed(self.member, request_for(self.member, "nav", dates[0], END), self.nav(reverse[:20], 1, 21))
        last = parsed(self.member, request_for(self.member, "nav", dates[0], END, page=2), self.nav(reverse[20:], 2, 21))
        self.assertEqual(str(first.rows[0].value("nav")), "1.2345")
        self.assertIn("受控请求绑定", first.rows[0].fields["nav"].source.channel)
        self.assertEqual(verify_nav_pages((first, last), dates[0], END), ())
        with self.assertRaises(FlowError):
            verify_nav_pages((first,), dates[0], END)
        duplicate = parsed(self.member, request_for(self.member, "nav", dates[0], END, page=2), self.nav(reverse[:1], 2, 21))
        with self.assertRaises(FlowError):
            verify_nav_pages((first, duplicate), dates[0], END)

    def test_empty_large_page_not_missing_and_actual_missing_never_zero(self):
        dates = preceding_window(END, 2)
        request = request_for(self.member, "nav", dates[0], END)
        with self.assertRaises(FlowError):
            parsed(self.member, request, {"ErrCode": 0, "Data": None, "TotalCount": 0, "PageSize": 0, "PageIndex": 1})
        page = parsed(self.member, request, self.nav([END], 1, 1))
        self.assertEqual(verify_nav_pages((page,), dates[0], END), (dates[0],))
        self.assertEqual(len(page.rows), 1)
        self.assertEqual(page.rows[0].date, END)

    def test_request_counts_depend_on_config_and_actual_missing_fields(self):
        config, rows, _, dates = sample("multiple")
        count = sum(len(plan(member, dates[0], END, {})) for member in config.pools[-1].members)
        self.assertEqual(count, len(config.pools[-1].members) * (321 * 2 + 17))
        existing = {(x.member_id, x.date): x for x in rows}
        self.assertEqual(plan(self.member, dates[0], END, existing), ())
        del existing[self.member.id, END]
        requests = plan(self.member, dates[0], END, existing)
        self.assertEqual([r.kind for r in requests], ["shares", "quote", "nav"])
        self.assertTrue(all(r.start == r.end == END for r in requests))


if __name__ == "__main__":
    unittest.main()
