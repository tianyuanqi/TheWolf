"""ETF预定金融反例：身份从假配置读取，数字预期独立于实现推导。"""
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal
import unittest

from etf_flow_fixture import AT, END, configuration, replace_field, sample
from pmi.market_data.etf_flow.calculation import Calculator, cumulative, streak
from pmi.market_data.etf_flow.model import Adjustment, Configuration, FlowError, Input


def calculator(config, inputs, adjustments, *, admissions=(), at=AT, qualify=True):
    calc = Calculator(config, inputs, adjustments, admissions, selection_at=at, end=END)
    if qualify:
        calc = Calculator(config, inputs, adjustments, calc.qualify(), selection_at=at, end=END)
    return calc


class CalculationTests(unittest.TestCase):
    def test_large_valid_decimal_products_keep_all_integer_digits(self):
        config, rows, adjustments, dates = sample()
        base = 10**29 + 1
        rows = (*rows[:-2], replace_field(rows[-2], 'shares', str(base)),
                replace_field(replace_field(rows[-1], 'shares', '0'), 'nav', str(base)))
        special = Adjustment.parse({'member_id': config.pools[-1].members[0].id, 'kind': 'adjustment',
            'start': END, 'end': END, 'factor': str(base), 'tail': '0', 'source_ids': list(adjustments[0].source_ids),
            'confirmed_at': AT, 'confirmation': '仅隔离算术上界测试'})
        calc = calculator(config, rows, (*adjustments, special), qualify=False)
        # (10^29+1)^3 的整数展开独立于Decimal实现，不能先按默认精度截断。
        self.assertEqual(calc.metrics(config.pools[-1].members[0].id, END)['amount'],
                         str(-(10**87 + 3*10**58 + 3*10**29 + 1)))

    def test_single_c1_sample_deviation_excludes_today_and_equal_boundary(self):
        config, rows, adjustments, dates = sample()
        calc = calculator(config, rows, adjustments)
        value = calc.evaluate(END)
        # 此前10/20/30的均值20、样本标准差10；当日40恰好等于上界。
        self.assertEqual(value["amount"], "40")
        self.assertEqual(value["c1"]["mean"], "20")
        self.assertEqual(value["c1"]["standard_deviation"], "10")
        self.assertEqual(value["c1"]["upper"], "40")
        self.assertTrue(value["c1"]["incoming"])
        self.assertEqual(value["c2"]["state"], "insufficient")
        self.assertIsNone(value["c2"]["positive_ratio"])
        self.assertEqual(value["state"], "insufficient")
        self.assertEqual(calc.admissions[0].first_qualified_at, AT)
        self.assertEqual(calc.admissions[0].start, dates[0])

    def test_history_320_321_missing_middle_and_longer_window(self):
        config, rows, adjustments, _ = sample()
        full = calculator(config, rows, adjustments)
        for bad in (rows[1:], rows[:100] + rows[101:]):
            calc = calculator(config, bad, adjustments)
            self.assertFalse(calc.admissions)
            value = calc.evaluate(END)
            self.assertEqual(value["valid_count"], 0)
            self.assertIsNone(value["amount"])
            self.assertEqual(value["exclusions"][0]["reason"], "history_insufficient")
        raw = configuration()
        raw["rule_versions"][0]["window"] = 61
        longer = calculator(Configuration.parse(raw), rows, adjustments, admissions=full.admissions)
        self.assertIsNone(longer.admission(config.pools[0].members[0].id))

    def test_five_members_added_and_deactivated_regrouped_by_configuration(self):
        config, rows, adjustments, _ = sample("multiple")
        calc = calculator(config, rows, adjustments)
        value = calc.evaluate(END)
        self.assertEqual(len(config.pools[0].members), 4)
        self.assertEqual(value["valid_count"], 5)
        self.assertEqual(value["c2"]["denominator"], 5)
        self.assertEqual(value["c2"]["positive_ratio"], "1")
        raw = configuration("multiple")
        new = deepcopy(raw["pool_versions"][-1])
        new.update(version="test-change", effective_date="2026-11-06", confirmed_at="2026-11-06T08:00:00+08:00", change="仅修改停用和分组")
        new["members"][0]["disabled_date"] = "2026-11-06"
        new["members"][1]["group"] = new["members"][-1]["group"]
        raw["pool_versions"].append(new)
        changed = calculator(Configuration.parse(raw), rows, adjustments, admissions=calc.admissions, at="2026-11-06T12:00:00+08:00")
        self.assertEqual(changed.evaluate(END)["valid_count"], 4)
        self.assertIn({"member_id": new["members"][0]["id"], "reason": "disabled"}, changed.evaluate(END)["exclusions"])
        self.assertEqual(changed.pool.members[1].group, changed.pool.members[-1].group)
        self.assertEqual(calc.evaluate(END), value)
        self.assertNotEqual(value["result_id"], changed.evaluate(END)["result_id"])

    def test_zero_counts_only_in_denominator_and_negative_direction(self):
        config, rows, adjustments, dates = sample("multiple")
        established = calculator(config, rows, adjustments)
        last = config.pools[-1].members[-1].id
        previous = next(x for x in rows if x.member_id == last and x.date == dates[-2])
        zeros = tuple(replace_field(x, "shares", str(previous.value("shares"))) if x.member_id == last and x.date == END else x for x in rows)
        value = calculator(config, zeros, adjustments, admissions=established.admissions).evaluate(END)
        self.assertEqual(value["c2"]["positive_count"], 4)
        self.assertEqual(value["c2"]["denominator"], 5)
        self.assertEqual(value["c2"]["positive_ratio"], "0.8")
        self.assertTrue(value["c2"]["incoming"])
        negative = tuple(replace_field(x, "shares", str(previous.value("shares") - 1)) if x.member_id == last and x.date == END else x for x in rows)
        value = calculator(config, negative, adjustments, admissions=established.admissions).evaluate(END)
        self.assertEqual(value["c2"]["negative_count"], 1)
        self.assertEqual(value["c2"]["negative_ratio"], "0.2")

    def test_late_nav_mature_partial_and_cumulative_gap(self):
        config, rows, adjustments, _ = sample("multiple")
        calc = calculator(config, rows, adjustments)
        member = config.pools[-1].members[0].id
        missing = tuple(replace_field(x, "nav", None) if x.member_id == member and x.date == END else x for x in rows)
        late = calculator(config, missing, adjustments, admissions=calc.admissions)
        value = late.evaluate(END)
        self.assertEqual(value["ready_count"], 5)
        self.assertEqual(value["valid_count"], 4)
        self.assertTrue(value["partial"])
        self.assertEqual(value["amount"], "160")
        self.assertEqual(late.metrics(member, END)["delta"], "40")
        self.assertEqual(late.metrics(member, END)["reason"], "waiting_nav")
        self.assertIsNone(late.member_cumulative(member, END, 5))
        self.assertIsNone(cumulative([value], 1))

    def test_adjustment_tail_unknown_and_no_cross_gap(self):
        config, rows, adjustments, dates = sample()
        member = config.pools[-1].members[0].id
        normalized = list(rows)
        normalized[-2] = replace_field(normalized[-2], "shares", "1000")
        normalized[-1] = replace_field(normalized[-1], "shares", "2010")
        normalized[-1] = replace_field(normalized[-1], "nav", "3")
        split = replace(adjustments[0], kind="adjustment", start=END, end=END, factor=Decimal(2), tail=Decimal(3))
        calc = calculator(config, tuple(normalized), adjustments + (split,))
        self.assertEqual(calc.metrics(member, END)["comparable_previous"], "2003")
        self.assertEqual(calc.metrics(member, END)["delta"], "7")
        self.assertEqual(calc.metrics(member, END)["amount"], "21")
        unknown = calculator(config, rows, (), qualify=False)
        self.assertEqual(unknown.metrics(member, END)["reason"], "adjustment_unverified")
        gap = calculator(config, rows[:-2] + rows[-1:], adjustments, qualify=False)
        self.assertEqual(gap.metrics(member, END)["reason"], "previous_day_missing")

    def test_zero_comparable_invalidates_only_ratio_not_known_delta(self):
        config, rows, adjustments, _ = sample()
        member = config.pools[-1].members[0].id
        changed = list(rows)
        changed[-2] = replace_field(changed[-2], "shares", "0")
        changed[-1] = replace_field(changed[-1], "shares", "7")
        changed[-1] = replace_field(changed[-1], "nav", "3")
        metrics = calculator(config, tuple(changed), adjustments).metrics(member, END)
        self.assertEqual(metrics["delta"], "7")
        self.assertEqual(metrics["amount"], "21")
        self.assertIsNone(metrics["change_rate"])

    def test_parameters_pending_and_zero_variance(self):
        config, rows, adjustments, _ = sample("multiple")
        raw = configuration("multiple")
        raw["rule_versions"][0].update(confirmed_at=None, confirmation=None, k=None, direction_ratio=None, streak_days=None)
        calc = calculator(Configuration.parse(raw), rows, adjustments)
        value = calc.evaluate(END)
        self.assertEqual(value["c1"]["state"], "parameters_pending")
        self.assertEqual(value["c2"]["state"], "parameters_pending")
        self.assertEqual(value["state"], "parameters_pending")
        self.assertEqual(streak([value], calc.rule, AT)["state"], "parameters_pending")
        one, one_rows, normal, dates = sample()
        flat = []
        for i, row in enumerate(one_rows):
            flat.append(replace_field(row, "shares", str(1000 + i)))
        result = calculator(one, tuple(flat), normal).evaluate(END)
        self.assertEqual(result["c1"]["reason"], "zero_variance")
        self.assertIsNone(result["c1"]["incoming"])

    def test_daily_sum_uses_each_days_nav_and_future_values_do_not_affect_earlier(self):
        config, rows, adjustments, dates = sample()
        changed = tuple(replace_field(row, "nav", "2") if row.date == END else row for row in rows)
        baseline = calculator(config, rows, adjustments)
        calc = calculator(config, changed, adjustments)
        member = config.pools[-1].members[0].id
        self.assertEqual(calc.member_cumulative(member, END, 3), "130")  # 20×1 + 30×1 + 40×2
        self.assertEqual(baseline.evaluate(dates[-2])["amount"], calc.evaluate(dates[-2])["amount"])
        self.assertEqual(baseline.evaluate(dates[-2])["c1"], calc.evaluate(dates[-2])["c1"])

    def test_duplicate_non_trading_wrong_date_unit_and_identity_rejected(self):
        config, rows, adjustments, _ = sample()
        with self.assertRaises(FlowError):
            calculator(config, rows + rows[-1:], adjustments)
        raw = deepcopy(rows[-1].raw)
        raw["fields"]["nav"]["date"] = "2026-11-03"
        with self.assertRaises(FlowError):
            Input.parse(raw)
        raw = deepcopy(rows[-1].raw)
        raw["fields"]["shares"]["unit"] = "亿份"
        with self.assertRaises(FlowError):
            Input.parse(raw)
        raw = deepcopy(rows[-1].raw)
        raw["date"] = "2026-11-01"
        for field in raw["fields"].values():
            field["date"] = raw["date"]
        with self.assertRaises(FlowError):
            calculator(config, rows + (Input.parse(raw),), adjustments)
        raw_config = configuration()
        raw_config["pool_versions"][0]["members"].append(deepcopy(raw_config["pool_versions"][0]["members"][0]))
        with self.assertRaises(FlowError):
            Configuration.parse(raw_config)


if __name__ == "__main__":
    unittest.main()
