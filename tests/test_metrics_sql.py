"""SQL metrics on the seeded stream: pinned headline numbers,
trap impact, and proof the definitions live in SQL strings."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import metrics  # noqa: E402
from generator import generate_events  # noqa: E402
from metrics import impact_table  # noqa: E402


class TestSqlDefinitions(unittest.TestCase):
    def test_sessionization_is_sql_with_lag(self):
        self.assertIn("LAG(", metrics.SESSION_SQL)
        self.assertIn("PARTITION BY user_id", metrics.SESSION_SQL)

    def test_funnel_and_payer_are_sql(self):
        self.assertIn("activation_action", metrics.FUNNEL_SQL)
        self.assertIn("cohort_day", metrics.PAYER_BY_COHORT_SQL)


class TestSeededHeadlines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.impact = impact_table(generate_events())

    def test_cleaned_sessions_pinned(self):
        self.assertEqual(self.impact["cleaned"]["sessions"],
                         {"users": 120, "sessions": 232})
        self.assertEqual(self.impact["with_traps"]["sessions"]["sessions"], 288)

    def test_cleaned_funnel_pinned(self):
        counts = self.impact["cleaned"]["funnel"]["counts"]
        self.assertEqual(counts, {"landing_view": 120, "signup": 84,
                                  "activation_action": 51, "purchase": 30})
        conv = self.impact["cleaned"]["funnel"]["conversion"]
        self.assertEqual(conv["landing_view_to_signup"], 0.7)
        self.assertEqual(conv["signup_to_activation_action"], 0.6071)
        self.assertEqual(conv["activation_action_to_purchase"], 0.5882)
        self.assertEqual(conv["landing_to_purchase"], 0.25)

    def test_trap_impact_on_funnel_top(self):
        raw = self.impact["with_traps"]["funnel"]
        self.assertEqual(raw["counts"]["landing_view"], 160)  # +40 bots
        self.assertEqual(raw["conversion"]["landing_view_to_signup"], 0.525)

    def test_payer_conversion_pinned(self):
        clean = self.impact["cleaned"]
        self.assertEqual(clean["signups"], 84)
        self.assertEqual(clean["payers"], 30)
        self.assertEqual(clean["payer_conversion_overall"], 0.3571)
        self.assertEqual(len(clean["payer_by_cohort"]), 14)


if __name__ == "__main__":
    unittest.main()
