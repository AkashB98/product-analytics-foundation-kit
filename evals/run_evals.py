"""Golden evals for product-analytics-foundation-kit.

SYNTHETIC DATA ONLY. Deterministic: run_evals.py writes
eval_report.json, byte-identical across runs (names, booleans and
pinned values only — no timestamps or paths).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import events_to_json, generate_events, planted_summary  # noqa: E402
from metrics import impact_table  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    return passed


def main() -> int:
    print("== golden evals: product-analytics-foundation-kit ==")
    events = generate_events()
    impact = impact_table(events)
    raw, clean = impact["with_traps"], impact["cleaned"]
    planted = planted_summary(events)

    md5 = hashlib.md5(events_to_json(events).encode()).hexdigest()
    check("E1_generator_determinism", md5 == "f7c3abfdd07c564de9587cb1e9d4257f",
          f"stream md5 {md5}")
    check("E2_planted_traps",
          planted == {"total_rows": 372, "duplicate_rows": 15,
                      "bot_rows": 40, "distinct_event_ids": 357},
          str(planted))
    check("E3_sessions_pinned",
          raw["sessions"]["sessions"] == 288
          and clean["sessions"] == {"users": 120, "sessions": 232},
          f"raw {raw['sessions']['sessions']} -> cleaned "
          f"{clean['sessions']['sessions']}")
    check("E4_funnel_pinned",
          clean["funnel"]["counts"] == {"landing_view": 120, "signup": 84,
                                        "activation_action": 51,
                                        "purchase": 30}
          and clean["funnel"]["conversion"]["landing_view_to_signup"] == 0.7
          and clean["funnel"]["conversion"]["landing_to_purchase"] == 0.25,
          str(clean["funnel"]["counts"]))
    check("E5_trap_impact_funnel_top",
          raw["funnel"]["counts"]["landing_view"] == 160
          and raw["funnel"]["conversion"]["landing_view_to_signup"] == 0.525,
          "bots dilute landing->signup 0.7000 -> 0.5250")
    check("E6_payer_conversion_pinned",
          clean["payer_conversion_overall"] == 0.3571
          and clean["signups"] == 84 and clean["payers"] == 30
          and len(clean["payer_by_cohort"]) == 14,
          f"overall {clean['payer_conversion_overall']}")
    check("E7_cleaning_invents_nothing",
          raw["signups"] == clean["signups"]
          and raw["payers"] == clean["payers"],
          "signups/payers identical raw vs cleaned")
    check("E8_impact_is_deterministic",
          impact_table(generate_events()) == impact)

    passed = sum(1 for r in RESULTS if r["passed"])
    report = {"evals": RESULTS, "passed": passed, "total": len(RESULTS)}
    with open(os.path.join(HERE, "eval_report.json"), "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"== {passed}/{len(RESULTS)} evals passed ==")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
