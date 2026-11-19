"""End-to-end demo: generate -> load to sqlite -> SQL metrics ->
trap-impact table (with traps vs cleaned).

SYNTHETIC DATA ONLY. Runs fully offline, stdlib only. Every stage
asserts; exit 0 means the whole narrative held.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generator import events_to_json, generate_events, planted_summary  # noqa: E402
from metrics import impact_table, load_db  # noqa: E402


def render_report(impact: dict, planted: dict) -> str:
    raw, clean = impact["with_traps"], impact["cleaned"]
    lines = [
        "# product-analytics-foundation-kit — demo report",
        "",
        f"rows ingested: {planted['total_rows']} "
        f"(duplicates: {planted['duplicate_rows']}, "
        f"bot rows: {planted['bot_rows']}, "
        f"distinct events: {planted['distinct_event_ids']})",
        "",
        "## Trap-impact table (headline metrics)",
        "",
        "| Metric | With traps | Cleaned | Delta |",
        "|---|---|---|---|",
        f"| sessions | {raw['sessions']['sessions']} | "
        f"{clean['sessions']['sessions']} | "
        f"{clean['sessions']['sessions'] - raw['sessions']['sessions']:+d} |",
        f"| users in funnel | {raw['funnel']['counts']['landing_view']} | "
        f"{clean['funnel']['counts']['landing_view']} | "
        f"{clean['funnel']['counts']['landing_view'] - raw['funnel']['counts']['landing_view']:+d} |",
    ]
    for step in ["landing_view", "signup", "activation_action", "purchase"]:
        lines.append(
            f"| funnel: {step} (users) | {raw['funnel']['counts'][step]} | "
            f"{clean['funnel']['counts'][step]} | "
            f"{clean['funnel']['counts'][step] - raw['funnel']['counts'][step]:+d} |")
    for key in ["landing_view_to_signup", "signup_to_activation_action",
                "activation_action_to_purchase", "landing_to_purchase"]:
        lines.append(
            f"| conversion: {key} | {raw['funnel']['conversion'][key]} | "
            f"{clean['funnel']['conversion'][key]} | "
            f"{clean['funnel']['conversion'][key] - raw['funnel']['conversion'][key]:+.4f} |")
    lines.append(
        f"| payer conversion (overall) | {raw['payer_conversion_overall']} | "
        f"{clean['payer_conversion_overall']} | "
        f"{clean['payer_conversion_overall'] - raw['payer_conversion_overall']:+.4f} |")
    lines += ["", "## Payer conversion by signup cohort (cleaned)", "",
              "| Cohort day | Signups | Payers | Conversion |",
              "|---|---|---|---|"]
    for r in clean["payer_by_cohort"]:
        lines.append(f"| {r['cohort_day']} | {r['signups']} | "
                     f"{r['payers']} | {r['payer_conversion']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    print("== 1. generate synthetic event stream (seed=42) ==")
    events = generate_events()
    assert events == generate_events(), "generator must be deterministic"
    planted = planted_summary(events)
    print(f"   {planted}")
    assert planted["duplicate_rows"] == 15, planted
    assert planted["bot_rows"] == 40, planted

    print("\n== 2. SQL metrics: with traps vs cleaned ==")
    impact = impact_table(events)
    raw, clean = impact["with_traps"], impact["cleaned"]
    # Bots inflate the funnel top; cleaning must remove exactly them.
    assert (raw["funnel"]["counts"]["landing_view"]
            - clean["funnel"]["counts"]["landing_view"] == 40)
    # Cleaning never invents payers or signups.
    assert raw["signups"] == clean["signups"]
    assert raw["payers"] == clean["payers"]
    print(f"   sessions: raw {raw['sessions']['sessions']} -> "
          f"cleaned {clean['sessions']['sessions']}")
    print(f"   funnel (cleaned): {clean['funnel']['counts']}")
    print(f"   payer conversion (cleaned): "
          f"{clean['payer_conversion_overall']}")

    print("\n== 3. report determinism ==")
    report = render_report(impact, planted)
    again = render_report(impact_table(generate_events()),
                          planted_summary(generate_events()))
    assert report == again
    digest = hashlib.md5(report.encode()).hexdigest()
    print(f"   report md5: {digest}")
    print(f"   stream md5: "
          f"{hashlib.md5(events_to_json(events).encode()).hexdigest()}")

    print("\n" + report)
    print("Demo OK: generate, SQL sessionization, ordered funnel, "
          "payer-by-cohort and trap-impact table verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
