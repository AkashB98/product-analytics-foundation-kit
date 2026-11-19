"""Product analytics metrics AS SQL (stdlib sqlite3).

Python only orchestrates: it loads events into an in-memory sqlite
database, runs the SQL strings below, and asserts on the results.
The metric DEFINITIONS are the SQL strings — read them here.

Two tables are built from the same stream:

  events_raw     — every ingested row, in ingestion order (rowid).
                   Duplicates, bots and late arrivals all present.
  events_cleaned — cleaning rules applied (see README):
                   1. dedupe on event_id (keep first ingested copy)
                   2. drop bot user_agents (LIKE '%Bot%')
                   3. sessionization orders by event_ts, not rowid

Sessionization: a new session starts when the gap from the previous
event for the same user exceeds 30 minutes (or, in the raw table,
when ingestion order disagrees with event time — a late arrival
landing far from its true neighbours). Implemented with LAG().

Funnel: ordered steps. A user counts at step N only if their first
event of that step occurs after their counted event at step N-1
(SQL CTE chaining first-event timestamps).

Payer conversion by signup cohort: cohort = day index of the user's
signup event (event_ts // 1440); conversion = distinct purchasers /
distinct signups in that cohort. ONE table.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List

SESSION_GAP_MINUTES = 30
BOT_PATTERN = "%Bot%"

# ---------------------------------------------------------------- SQL

CREATE_CLEANED_SQL = """
CREATE TABLE events_cleaned AS
SELECT event_id, user_id, event_type, event_ts, user_agent
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY event_id ORDER BY rowid) AS rn
    FROM events_raw
)
WHERE rn = 1 AND user_agent NOT LIKE '%Bot%';
"""

# Canonical session query for BOTH tables, with the ORDER BY column
# substituted: rowid (ingestion order) for raw, event_ts for cleaned.
SESSION_SQL = """
WITH ordered AS (
    SELECT user_id, event_ts,
           LAG(event_ts) OVER (
               PARTITION BY user_id ORDER BY {order_col}) AS prev_ts
    FROM {table}
),
flagged AS (
    SELECT user_id,
           CASE
               WHEN prev_ts IS NULL THEN 1
               WHEN event_ts - prev_ts > 30 THEN 1
               WHEN event_ts - prev_ts < 0 THEN 1
               ELSE 0
           END AS is_new_session
    FROM ordered
)
SELECT COUNT(DISTINCT user_id) AS users, SUM(is_new_session) AS sessions
FROM flagged
"""

FUNNEL_SQL = """
WITH firsts AS (
    SELECT user_id,
           MIN(CASE WHEN event_type = 'landing_view'
                    THEN event_ts END) AS t_landing,
           MIN(CASE WHEN event_type = 'signup'
                    THEN event_ts END) AS t_signup,
           MIN(CASE WHEN event_type = 'activation_action'
                    THEN event_ts END) AS t_activation,
           MIN(CASE WHEN event_type = 'purchase'
                    THEN event_ts END) AS t_purchase
    FROM {table}
    GROUP BY user_id
),
ordered AS (
    SELECT user_id,
           t_landing,
           CASE WHEN t_signup > t_landing
                THEN t_signup END AS s_signup,
           CASE WHEN t_activation > t_signup
                     AND t_signup > t_landing
                THEN t_activation END AS s_activation,
           CASE WHEN t_purchase > t_activation
                     AND t_activation > t_signup
                     AND t_signup > t_landing
                THEN t_purchase END AS s_purchase
    FROM firsts
)
SELECT
    COUNT(t_landing)    AS landing_view,
    COUNT(s_signup)     AS signup,
    COUNT(s_activation) AS activation_action,
    COUNT(s_purchase)   AS purchase
FROM ordered
"""

PAYER_BY_COHORT_SQL = """
WITH signups AS (
    SELECT user_id, MIN(event_ts) / 1440 AS cohort_day
    FROM {table}
    WHERE event_type = 'signup'
    GROUP BY user_id
),
payers AS (
    SELECT DISTINCT user_id FROM {table}
    WHERE event_type = 'purchase'
)
SELECT s.cohort_day AS cohort_day,
       COUNT(*) AS signups,
       SUM(CASE WHEN p.user_id IS NOT NULL THEN 1 ELSE 0 END) AS payers,
       ROUND(1.0 * SUM(CASE WHEN p.user_id IS NOT NULL
                             THEN 1 ELSE 0 END) / COUNT(*), 4)
           AS payer_conversion
FROM signups s
LEFT JOIN payers p ON p.user_id = s.user_id
GROUP BY s.cohort_day
ORDER BY s.cohort_day
"""

# ------------------------------------------------------------ loading

def load_db(events: List[Dict]) -> sqlite3.Connection:
    """Load a stream into events_raw (+ derived events_cleaned)."""
    con = sqlite3.connect(":memory:")
    con.executescript(
        "CREATE TABLE events_raw (event_id TEXT, user_id TEXT,"
        " event_type TEXT, event_ts INTEGER, user_agent TEXT);")
    con.executemany(
        "INSERT INTO events_raw VALUES (?,?,?,?,?)",
        [(e["event_id"], e["user_id"], e["event_type"],
          e["event_ts"], e["user_agent"]) for e in events])
    con.executescript(CREATE_CLEANED_SQL)
    return con


# ------------------------------------------------------------ metrics

def session_count(con: sqlite3.Connection, table: str) -> Dict:
    order_col = "rowid" if table == "events_raw" else "event_ts"
    sql = SESSION_SQL.format(table=table, order_col=order_col)
    users, sessions = con.execute(sql).fetchone()
    return {"users": users, "sessions": sessions}


def funnel(con: sqlite3.Connection, table: str) -> Dict:
    row = con.execute(FUNNEL_SQL.format(table=table)).fetchone()
    counts = dict(zip(
        ["landing_view", "signup", "activation_action", "purchase"], row))
    conv = {}
    steps = list(counts)
    for a, b in zip(steps, steps[1:]):
        conv[f"{a}_to_{b}"] = (round(counts[b] / counts[a], 4)
                               if counts[a] else 0.0)
    conv["landing_to_purchase"] = (round(counts["purchase"]
                                          / counts["landing_view"], 4)
                                    if counts["landing_view"] else 0.0)
    return {"counts": counts, "conversion": conv}


def payer_by_cohort(con: sqlite3.Connection, table: str) -> List[Dict]:
    rows = con.execute(PAYER_BY_COHORT_SQL.format(table=table)).fetchall()
    return [{"cohort_day": d, "signups": s, "payers": p,
             "payer_conversion": c} for d, s, p, c in rows]


def headline(con: sqlite3.Connection, table: str) -> Dict:
    cohorts = payer_by_cohort(con, table)
    signups = sum(r["signups"] for r in cohorts)
    payers = sum(r["payers"] for r in cohorts)
    return {
        "sessions": session_count(con, table),
        "funnel": funnel(con, table),
        "payer_by_cohort": cohorts,
        "payer_conversion_overall": (round(payers / signups, 4)
                                     if signups else 0.0),
        "signups": signups,
        "payers": payers,
    }


def impact_table(events: List[Dict]) -> Dict:
    """Headline metrics WITH traps (raw) vs AFTER cleaning."""
    con = load_db(events)
    raw = headline(con, "events_raw")
    clean = headline(con, "events_cleaned")
    con.close()
    return {"with_traps": raw, "cleaned": clean}
