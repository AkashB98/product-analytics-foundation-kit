"""Deterministic synthetic product event stream — fictional users only.

SYNTHETIC DATA ONLY. No real user, customer, or product data is used.
Every row is fabricated from a seeded PRNG so the same seed always
yields the same stream, byte-for-byte.

Shape: 120 users over a 14-day window (days 0..13). Each user has a
signup timestamp (their cohort day) and an ordered journey through:

    landing_view -> signup -> activation_action -> purchase

Events carry: event_id, user_id, event_type, event_ts (integer
minutes since day-0 midnight), user_agent.

Planted data-quality traps (the differentiator — pinned by tests
and golden evals, disclosed in the impact table, never silently
cleaned):

  1. EXACT DUPLICATES — 15 events copied verbatim (same event_id and
     every other business field) and appended to the ingestion list.
  2. LATE / OUT-OF-ORDER ARRIVALS — 10 events moved to the end of
     the ingestion list, so ingestion order != event-time order.
  3. BOT SPIKE — on day 7, 40 extra landing_view events from bot
     users with user_agent 'DataBot/1.0' (see BOT_AGENT).

The generator returns events in INGESTION order (the order a raw
warehouse table would receive them). Event-time order must be
recovered by sorting on event_ts — that is cleaning rule 3.
"""

from __future__ import annotations

import random
from typing import Dict, List

DEFAULT_SEED = 42
N_USERS = 120
WINDOW_DAYS = 14
BOT_DAY = 7
BOT_EVENTS = 40
N_DUPLICATES = 15
N_LATE = 10

BOT_AGENT = "Mozilla/5.0 (compatible; DataBot/1.0; +https://example.invalid/bot)"
NORMAL_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1",
]

STEPS = ["landing_view", "signup", "activation_action", "purchase"]


def generate_events(seed: int = DEFAULT_SEED) -> List[Dict]:
    """Return the full event stream in ingestion order (with traps)."""
    rng = random.Random(seed)
    clean: List[Dict] = []
    eid = 0

    def emit(user_id: str, step: str, ts: int, agent: str) -> None:
        nonlocal eid
        eid += 1
        clean.append({
            "event_id": f"E{eid:05d}",
            "user_id": user_id,
            "event_type": step,
            "event_ts": ts,
            "user_agent": agent,
        })

    for i in range(N_USERS):
        uid = f"U{i + 1:03d}"
        agent = NORMAL_AGENTS[i % len(NORMAL_AGENTS)]
        cohort_day = rng.randrange(WINDOW_DAYS)
        # First landing early on the cohort day.
        t = cohort_day * 1440 + rng.randrange(60, 600)
        emit(uid, "landing_view", t, agent)
        # ~25% browse again later the same day (a second session).
        if rng.random() < 0.25:
            t2 = t + rng.randrange(120, 400)
            emit(uid, "landing_view", t2, agent)
            t = t2
        if rng.random() >= 0.72:  # never signs up
            continue
        t += rng.randrange(2, 25)
        emit(uid, "signup", t, agent)
        if rng.random() >= 0.62:  # signs up, never activates
            continue
        # Activation often happens on a return visit the next day.
        t += rng.randrange(30, 1500)
        emit(uid, "activation_action", t, agent)
        if rng.random() >= 0.48:  # activates, never pays
            continue
        t += rng.randrange(10, 900)
        emit(uid, "purchase", t, agent)

    # --- Trap 3: bot spike on BOT_DAY (landing views only) ---
    bot_events: List[Dict] = []
    for b in range(BOT_EVENTS):
        eid += 1
        bot_events.append({
            "event_id": f"E{eid:05d}",
            "user_id": f"BOT{b + 1:03d}",
            "event_type": "landing_view",
            "event_ts": BOT_DAY * 1440 + 300 + b * 3,
            "user_agent": BOT_AGENT,
        })

    ingestion = sorted(clean + bot_events, key=lambda e: e["event_ts"])

    # --- Trap 1: exact duplicates appended at ingestion ---
    # Sources are human events only, so the bot count stays exactly 40.
    dup_sources = [clean[k * 17] for k in range(N_DUPLICATES)]
    duplicates = [dict(e) for e in dup_sources]

    # --- Trap 2: late arrivals moved to the end of ingestion ---
    late_idx = sorted(rng.sample(range(len(ingestion)), N_LATE))
    late = [ingestion[k] for k in late_idx]
    on_time = [e for k, e in enumerate(ingestion) if k not in set(late_idx)]

    return on_time + late + duplicates


def planted_summary(events: List[Dict]) -> Dict:
    """Count the planted traps actually present in a stream."""
    ids = [e["event_id"] for e in events]
    return {
        "total_rows": len(events),
        "duplicate_rows": len(ids) - len(set(ids)),
        "bot_rows": sum(1 for e in events if "Bot" in e["user_agent"]),
        "distinct_event_ids": len(set(ids)),
    }


def events_to_json(events: List[Dict]) -> str:
    import json
    return json.dumps(events, sort_keys=True) + "\n"
