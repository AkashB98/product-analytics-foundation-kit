# product-analytics-foundation-kit

**The first week of product analytics, done honestly: a synthetic product event stream loaded into SQLite, with sessionization, an ordered conversion funnel, and payer conversion by signup cohort defined as readable SQL — and every headline number reported twice, once with the planted data-quality traps in the data and once after documented cleaning rules, so the cost of dirty data is a table, not a rumour.**

Product analytics looks simple until the data arrives the way real data arrives: some events fire twice, some arrive hours late, and one day a bot shows up and quietly dilutes your funnel. The craft this project demonstrates is the foundation layer a product analyst actually gets hired to build — **event modelling** (a small, explicit event vocabulary: `landing_view → signup → activation_action → purchase`), **sessionization** (grouping a user's events into visits with a 30-minute inactivity gap, via a `LAG()` window function), an **ordered funnel** (a user counts at a step only if it happened *after* the previous step — unordered step counts flatter every funnel), and **monetization as one honest table** (payer conversion by signup cohort — who signed up, who eventually paid). Every metric definition lives in SQL strings in `metrics.py`; Python only loads, orchestrates, and asserts.

> **Synthetic data only.** Every user and event is fictional, fabricated by a seeded generator. No real product, user, or event data is used anywhere in this project.

Stdlib-only Python. Zero network, zero API keys, zero external dependencies.

*This is a proof of concept built on synthetic data to demonstrate the foundation pattern — event model, SQL metric definitions, and trap-impact disclosure — not a production analytics pipeline.*

## How this differs from its sibling projects

> **Retention and cohort retention curves live in `ai-adoption-analytics` — they are deliberately out of scope here.** This kit stops at acquisition, activation, and first payment; it builds no retention matrix and no cohort retention curves, because that sibling already does them.

## Quickstart

```bash
# 1. End-to-end demo: generate -> SQL metrics -> trap-impact table
python3 demo.py

# 2. Unit tests (incl. hand-computable cases)
python3 -m unittest discover -s tests

# 3. Golden evals (pins the seeded headline + trap-impact numbers)
python3 evals/run_evals.py
```

## The seeded stream at a glance (seed 42)

**120 fictional users** over 14 days, **357 distinct events**, **372 rows ingested** — the gap between those last two numbers is the point (see traps below).

**Sessions (cleaned): 232** across 120 users.

**Ordered funnel (cleaned):**

| Step | Users | Conversion from previous |
|---|---|---|
| landing_view | 120 | — |
| signup | 84 | 0.7000 |
| activation_action | 51 | 0.6071 |
| purchase | 30 | 0.5882 |

Landing → purchase overall: **0.2500**.

**Payer conversion by signup cohort (cleaned)** — the one monetization table in this project:

| Cohort day | Signups | Payers | Conversion |
|---|---|---|---|
| 0 | 4 | 2 | 0.5000 |
| 1 | 11 | 3 | 0.2727 |
| 2 | 6 | 3 | 0.5000 |
| 3 | 3 | 0 | 0.0000 |
| 4 | 3 | 1 | 0.3333 |
| 5 | 4 | 2 | 0.5000 |
| 6 | 8 | 3 | 0.3750 |
| 7 | 5 | 2 | 0.4000 |
| 8 | 6 | 3 | 0.5000 |
| 9 | 10 | 5 | 0.5000 |
| 10 | 5 | 1 | 0.2000 |
| 11 | 6 | 1 | 0.1667 |
| 12 | 8 | 2 | 0.2500 |
| 13 | 5 | 2 | 0.4000 |

Overall payer conversion: **30 / 84 = 0.3571**. Small cohorts swing wildly (day 3 has 3 signups) — the table shows its denominators precisely so nobody over-reads a 0.5000 built on 4 signups.

## The planted traps and the cleaning rules

Nothing in this project is silently cleaned. The generator plants three traps, the demo reports every headline metric **with traps present vs after cleaning**, and the rules are exactly these:

| # | Trap (planted) | Cleaning rule |
|---|---|---|
| 1 | **Exact duplicate rows** — 15 events ingested twice, verbatim, same `event_id` | Dedupe on `event_id`, keep the first ingested copy (`ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY rowid) = 1`) |
| 2 | **Bot spike** — 40 `landing_view` events on day 7 from bot users, `user_agent` containing `DataBot` | Drop rows whose `user_agent` matches `LIKE '%Bot%'` |
| 3 | **Late / out-of-order arrivals** — 10 events moved to the end of ingestion, so ingestion order ≠ event-time order | Sessionization orders by `event_ts` (event time), never by ingestion order |

**Trap impact (seed 42):**

| Metric | With traps | Cleaned | What moved it |
|---|---|---|---|
| Sessions | 288 | 232 | Bots add 40 one-event sessions; duplicates and late arrivals, read in ingestion order, fracture real sessions |
| Funnel: landing_view users | 160 | 120 | The 40 bot users sit in the funnel top and never convert |
| Conversion: landing → signup | 0.5250 | 0.7000 | Bot dilution alone costs 17.5 points of apparent conversion |
| Conversion: landing → purchase | 0.1875 | 0.2500 | Same dilution, end to end |
| Signups / payers / payer conversion | 84 / 30 / 0.3571 | 84 / 30 / 0.3571 | Bots never sign up and duplicates share an `event_id`, so cleaning changes nothing here — reported, not assumed |

That last row matters as much as the others: an honest impact table also shows where a trap *doesn't* bite.

## The metrics live in SQL

Product-analyst roles screen on SQL, so the headline numbers are not Python-only computations with SQL theatre around them — the definitions *are* the SQL strings in `metrics.py`, run against an in-memory `sqlite3` database:

| SQL constant | Computes |
|---|---|
| `SESSION_SQL` | Sessionization: `LAG(event_ts) OVER (PARTITION BY user_id ORDER BY …)`; a new session starts on a gap > 30 minutes (raw table orders by `rowid`, cleaned by `event_ts` — that one-word difference is cleaning rule 3) |
| `FUNNEL_SQL` | Ordered funnel: per-user first timestamp per step, chained so a step counts only after the previous step's timestamp |
| `PAYER_BY_COHORT_SQL` | Payer conversion by signup cohort: cohort = signup day (`event_ts / 1440`), payers = distinct purchasers, one grouped table |
| `CREATE_CLEANED_SQL` | The cleaning rules themselves, as a view-style `CREATE TABLE … AS SELECT` (dedupe + bot filter) |

## Architecture

| Module | Job |
|---|---|
| `generator.py` | Deterministic synthetic stream: 120 users, ordered journeys, seeded PRNG; plants the duplicates, the late arrivals, and the day-7 bot spike |
| `metrics.py` | Loads the stream into in-memory sqlite3 (`events_raw` + `events_cleaned`) and runs the SQL metric definitions; `impact_table()` returns both sides |
| `demo.py` | End-to-end narrative with asserts: determinism, trap counts, trap-impact table, payer-by-cohort table, report md5 |
| `evals/run_evals.py` | 8 golden evals pinning the seeded stream md5, trap counts, headline numbers, and trap-impact numbers |
| `tests/` | 18 tests: hand-computable session/funnel/payer cases on a 3-user set, the 30-minute gap boundary, ordered-funnel rejection of an out-of-order signup, generator determinism, SQL-string presence, no-network guard |

## Evals

`python3 evals/run_evals.py` → **8/8 golden evals**, report committed at `evals/eval_report.json`:

- **E1** generator determinism — stream bytes pinned by md5 (`f7c3abfdd07c564de9587cb1e9d4257f`)
- **E2** planted traps pinned (372 rows, 15 duplicates, 40 bot rows, 357 distinct events)
- **E3** sessions pinned (288 with traps → 232 cleaned)
- **E4** funnel pinned (120 → 84 → 51 → 30; landing→signup 0.7000, landing→purchase 0.2500)
- **E5** trap impact pinned (bot dilution: landing→signup 0.5250 with traps vs 0.7000 cleaned)
- **E6** payer conversion pinned (84 signups, 30 payers, 0.3571, 14 cohort rows)
- **E7** cleaning invents nothing (signups and payers identical raw vs cleaned)
- **E8** impact table deterministic across regenerated streams

Unit tests: `python3 -m unittest discover -s tests` → **18 tests**, including the hand-built 3-user set where 5 sessions, the 3→2→1→1 funnel, and 0.5 payer conversion are known by hand before any code runs.

## Scope and honest limits

- **No retention, by design.** Retention and cohort retention curves are owned by the sibling project `ai-adoption-analytics` (see above) and are deliberately absent here — this kit covers acquisition, activation, and first payment only.
- **Monetization is one table.** Payer conversion by signup cohort, nothing more: no revenue amounts, no per-user value modelling. The event stream carries no amounts, so any revenue metric would be invented.
- **Bot detection is a user-agent pattern.** That catches this planted spike because the spike is labelled; a production system would need behavioural signals too. The rule is documented so its weakness is visible.
- **Sessionization is per-user with a single 30-minute gap.** No cross-device identity resolution, no session attribution to campaigns — the stream has neither devices nor campaigns.
- **Small numbers are small.** 120 users over 14 days makes cohort rows with 3–11 signups; conversions on those denominators are demonstrations of method, not findings about any real product.

## Why this project

It rebuilds the author's day-job craft — event instrumentation, funnel definitions, and data-quality scepticism from web and marketing analytics — on the product side of the house: the foundation layer a product analyst builds in week one, and the same discipline a forward-deployed engineer brings to a customer deployment: make the definitions inspectable SQL, make the outputs reproducible, and make the dirty-data cost a printed table instead of a quiet assumption.
