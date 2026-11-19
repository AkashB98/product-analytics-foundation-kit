"""Hand-computable cases: a tiny event set whose session count,
funnel numbers and payer conversion are known by hand.

Hand set (agent 'HumanAgent' throughout):
  U1: landing 0, signup 10, activation 20, purchase 100
      gaps 10, 10, 80  -> 2 sessions (new session at t=100)
  U2: landing 0, signup 50
      gap 50 > 30      -> 2 sessions
  U3: landing 200      -> 1 session
  Total: 5 sessions, 3 users.
  Funnel: landing 3, signup 2, activation 1, purchase 1.
  Payer: cohort day 0 has both signups (t=10, t=50); U1 pays -> 0.5.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics import funnel, headline, load_db, payer_by_cohort, session_count  # noqa: E402

AGENT = "HumanAgent"


def ev(eid, uid, step, ts, agent=AGENT):
    return {"event_id": eid, "user_id": uid, "event_type": step,
            "event_ts": ts, "user_agent": agent}


HAND = [
    ev("H1", "U1", "landing_view", 0),
    ev("H2", "U1", "signup", 10),
    ev("H3", "U1", "activation_action", 20),
    ev("H4", "U1", "purchase", 100),
    ev("H5", "U2", "landing_view", 0),
    ev("H6", "U2", "signup", 50),
    ev("H7", "U3", "landing_view", 200),
]


class TestHandCases(unittest.TestCase):
    def setUp(self):
        self.con = load_db(HAND)

    def tearDown(self):
        self.con.close()

    def test_sessions_by_hand(self):
        self.assertEqual(session_count(self.con, "events_cleaned"),
                         {"users": 3, "sessions": 5})

    def test_funnel_by_hand(self):
        f = funnel(self.con, "events_cleaned")
        self.assertEqual(f["counts"], {"landing_view": 3, "signup": 2,
                                       "activation_action": 1,
                                       "purchase": 1})
        self.assertEqual(f["conversion"]["landing_view_to_signup"], 0.6667)
        self.assertEqual(f["conversion"]["signup_to_activation_action"], 0.5)
        self.assertEqual(f["conversion"]["activation_action_to_purchase"], 1.0)
        self.assertEqual(f["conversion"]["landing_to_purchase"], 0.3333)

    def test_payer_by_hand(self):
        rows = payer_by_cohort(self.con, "events_cleaned")
        self.assertEqual(rows, [{"cohort_day": 0, "signups": 2,
                                 "payers": 1, "payer_conversion": 0.5}])
        self.assertEqual(headline(self.con, "events_cleaned")
                         ["payer_conversion_overall"], 0.5)

    def test_gap_boundary_30_same_31_new(self):
        events = [ev("G1", "U9", "landing_view", 0),
                  ev("G2", "U9", "landing_view", 30),
                  ev("G3", "U9", "landing_view", 61)]
        con = load_db(events)
        # 0->30 is exactly 30 (same session); 30->61 is 31 (new).
        self.assertEqual(session_count(con, "events_cleaned")["sessions"], 2)
        con.close()

    def test_ordered_funnel_rejects_out_of_order_signup(self):
        # Signup timestamped BEFORE the landing view must not count.
        events = [ev("O1", "U8", "signup", 5),
                  ev("O2", "U8", "landing_view", 10)]
        con = load_db(events)
        f = funnel(con, "events_cleaned")
        self.assertEqual(f["counts"]["landing_view"], 1)
        self.assertEqual(f["counts"]["signup"], 0)
        con.close()

    def test_cleaning_neutralises_dup_and_bot(self):
        from generator import BOT_AGENT
        trapped = HAND + [dict(HAND[3])] + [
            ev("B1", "BOT001", "landing_view", 300, agent=BOT_AGENT)]
        con = load_db(trapped)
        clean = headline(con, "events_cleaned")
        self.assertEqual(clean["sessions"], {"users": 3, "sessions": 5})
        self.assertEqual(clean["funnel"]["counts"]["landing_view"], 3)
        raw = headline(con, "events_raw")
        self.assertEqual(raw["funnel"]["counts"]["landing_view"], 4)
        con.close()


if __name__ == "__main__":
    unittest.main()
