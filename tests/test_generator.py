"""Seeded generator: determinism and planted-trap counts."""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import (BOT_AGENT, events_to_json, generate_events,  # noqa: E402
                       planted_summary)


class TestGenerator(unittest.TestCase):
    def test_deterministic_bytes(self):
        a, b = events_to_json(generate_events()), events_to_json(generate_events())
        self.assertEqual(a, b)
        self.assertEqual(hashlib.md5(a.encode()).hexdigest(),
                         "f7c3abfdd07c564de9587cb1e9d4257f")

    def test_planted_traps_present(self):
        summary = planted_summary(generate_events())
        self.assertEqual(summary["duplicate_rows"], 15)
        self.assertEqual(summary["bot_rows"], 40)
        self.assertEqual(summary["total_rows"], 372)
        self.assertEqual(summary["distinct_event_ids"], 357)

    def test_bot_spike_is_one_day_and_landing_only(self):
        bots = [e for e in generate_events()
                if e["user_agent"] == BOT_AGENT]
        self.assertTrue(all(e["event_type"] == "landing_view" for e in bots))
        self.assertTrue(all(e["event_ts"] // 1440 == 7 for e in bots))

    def test_ingestion_order_is_not_event_time_order(self):
        events = generate_events()
        ts = [e["event_ts"] for e in events]
        self.assertNotEqual(ts, sorted(ts))  # late arrivals moved

    def test_every_human_signup_follows_a_landing(self):
        seen = {}
        for e in sorted(generate_events(), key=lambda x: x["event_ts"]):
            seen.setdefault(e["user_id"], []).append(e["event_type"])
        for uid, steps in seen.items():
            if "signup" in steps:
                self.assertLess(steps.index("landing_view"),
                                steps.index("signup"), uid)


if __name__ == "__main__":
    unittest.main()
