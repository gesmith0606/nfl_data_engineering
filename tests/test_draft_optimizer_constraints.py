"""
Roster-construction constraint tests for DraftAdvisor.recommend().

Doctrine rules under test (docs/DRAFT_DOCTRINE.md):
    §0  starters before backups — never the N+1th player at a position while
        a different dedicated starting slot is unfilled (the 2026-08 live
        mock recommended an RB3 while the roster had fewer than 2 WRs).
    §38 roster-count checkpoints — by R6 2 RB / 3 WR, by R10 4 RB / 4-5 WR.
    §39 TE2 never before round 9.
    §40 QB window — elite R3-5 or R9+, never rounds 6-8.
    §0  house rule — K/DST only in the final picks; DST must actually be
        recommendable there (ADP-only board rows, no projection needed).

Demotions are hard (below all need-filling picks) but the demoted rows stay
visible in the recs frame with a machine-readable ``demotion_rule`` string.
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_optimizer import (
    DraftAdvisor,
    DraftBoard,
    compute_value_scores,
)


def _skill_pool():
    """Projections with clear per-position VORP hierarchies.

    The best remaining RB is deliberately the highest-VORP player on the
    board so any test showing him NOT recommended proves a hard demotion,
    not a score tweak.
    """
    rows = []
    for i in range(8):
        rows.append(("qb%d" % i, "QB %d" % i, "QB", 380.0 - i * 10))
    rows.append(("rb0", "RB 0", "RB", 400.0))  # monster VORP RB
    for i in range(1, 12):
        rows.append(("rb%d" % i, "RB %d" % i, "RB", 330.0 - i * 10))
    for i in range(12):
        rows.append(("wr%d" % i, "WR %d" % i, "WR", 300.0 - i * 10))
    for i in range(8):
        rows.append(("te%d" % i, "TE %d" % i, "TE", 250.0 - i * 10))
    return pd.DataFrame(
        rows,
        columns=["player_id", "player_name", "position", "projected_season_points"],
    )


def _board(my_ids=()):
    proj = compute_value_scores(_skill_pool(), roster_format="standard", n_teams=12)
    board = DraftBoard(proj, roster_format="standard", n_teams=12)
    for pid in my_ids:
        board.draft_player(pid, by_me=True)
    return board


class TestStartersBeforeBackups(unittest.TestCase):
    """(a) WR2 outstanding blocks RB3 from the top recommendation."""

    def test_rb3_demoted_while_wr2_outstanding(self):
        # 2 RB + 1 WR rostered (round 4): WR2/QB1/TE1 starters still open.
        board = _board(my_ids=["rb1", "rb2", "wr5"])
        advisor = DraftAdvisor(board)
        # top_n covers the whole pool: demoted rows must still be IN the
        # frame (visible alternatives), just below every need-filling pick.
        recs, reasoning = advisor.recommend(top_n=40)

        self.assertIn("demotion_rule", recs.columns)
        # The monster-VORP RB must NOT be the top pick.
        self.assertNotEqual(recs.iloc[0]["position"], "RB")
        rb_rows = recs[recs["position"] == "RB"]
        self.assertFalse(rb_rows.empty, "demoted RBs stay visible as alternatives")
        for _, row in rb_rows.iterrows():
            self.assertIn("§0", row["demotion_rule"])
            self.assertIn("WR2", row["demotion_rule"])
        # Every non-demoted rec outranks every demoted rec.
        clean = recs[recs["demotion_rule"] == ""]
        self.assertFalse(clean.empty)
        self.assertGreater(
            clean["recommendation_score"].min(),
            rb_rows["recommendation_score"].max(),
        )

    def test_no_demotion_when_dedicated_starters_open_everywhere(self):
        board = _board(my_ids=[])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10)
        self.assertTrue((recs["demotion_rule"] == "").all())


class TestQbWindow(unittest.TestCase):
    """(b) QB demoted in rounds 6-8, allowed again at round 9+."""

    def test_qb_demoted_round_6(self):
        # 5 picks made -> this is round 6. RB2/WR3 checkpoint already met.
        board = _board(my_ids=["rb1", "rb2", "wr0", "wr1", "wr2"])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10)

        self.assertNotEqual(recs.iloc[0]["position"], "QB")
        qb_rows = recs[recs["position"] == "QB"]
        self.assertFalse(qb_rows.empty)
        for _, row in qb_rows.iterrows():
            self.assertIn("§40", row["demotion_rule"])
        # TE is the only skill starter neither demoted nor capped -> top rec.
        self.assertEqual(recs.iloc[0]["position"], "TE")

    def test_qb_allowed_round_9(self):
        # 8 picks made -> round 9; QB1 is the only dedicated starter open.
        board = _board(my_ids=["rb1", "rb2", "wr0", "wr1", "wr2", "te0", "rb3", "wr3"])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=5)
        self.assertEqual(recs.iloc[0]["position"], "QB")
        self.assertEqual(recs.iloc[0]["demotion_rule"], "")


class TestTe2Timing(unittest.TestCase):
    """(c) TE2 demoted before round 9, allowed after."""

    def test_te2_demoted_round_8(self):
        # QB/RB2+1/WR2/TE1 rostered (7 picks -> round 8); FLEX open.
        board = _board(my_ids=["qb0", "rb1", "rb2", "rb3", "wr0", "wr1", "te0"])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=40)
        te_rows = recs[recs["position"] == "TE"]
        self.assertFalse(te_rows.empty)
        for _, row in te_rows.iterrows():
            self.assertIn("§39", row["demotion_rule"])
        self.assertNotEqual(recs.iloc[0]["position"], "TE")

    def test_te2_allowed_round_11(self):
        # 10 picks made -> round 11, checkpoints passed, TE2 is legal.
        board = _board(
            my_ids=[
                "qb0",
                "rb1",
                "rb2",
                "rb3",
                "rb4",
                "wr0",
                "wr1",
                "wr2",
                "wr3",
                "te0",
            ]
        )
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10)
        te_rows = recs[recs["position"] == "TE"]
        if not te_rows.empty:
            for _, row in te_rows.iterrows():
                self.assertEqual(row["demotion_rule"], "")


class TestQb2HouseRule(unittest.TestCase):
    """House rule §0: never a 2nd QB in a 1-QB league (verify not broken)."""

    def test_no_second_qb_recommended(self):
        board = _board(my_ids=["qb0", "rb1", "rb2", "rb3", "wr0", "wr1", "wr2", "te0"])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10)
        self.assertNotIn("QB", set(recs["position"]))


class TestDstAdpOnlyPath(unittest.TestCase):
    """(d) DST/K survive onto the board without projections and become
    recommendable in the final-picks window — never before."""

    def _adp(self):
        pool = _skill_pool()
        rows = [
            {"player_name": n, "position": p, "adp_rank": i + 1}
            for i, (n, p) in enumerate(zip(pool["player_name"], pool["position"]))
        ]
        rows += [
            {"player_name": "DST A", "position": "DST", "adp_rank": 110},
            {"player_name": "DST B", "position": "DST", "adp_rank": 120},
            {"player_name": "DST C", "position": "DST", "adp_rank": 130},
            {"player_name": "K A", "position": "K", "adp_rank": 140},
            {"player_name": "K B", "position": "K", "adp_rank": 150},
        ]
        return pd.DataFrame(rows)

    def _kd_board(self, my_ids=()):
        enriched = compute_value_scores(
            _skill_pool(), adp_df=self._adp(), roster_format="standard", n_teams=12
        )
        board = DraftBoard(enriched, roster_format="standard", n_teams=12)
        for pid in my_ids:
            board.draft_player(pid, by_me=True)
        return board

    def test_dst_rows_survive_compute_value_scores(self):
        enriched = compute_value_scores(_skill_pool(), adp_df=self._adp())
        dst = enriched[enriched["position"] == "DST"]
        self.assertEqual(len(dst), 3)
        self.assertTrue(dst["vorp"].isna().all())
        self.assertEqual(sorted(dst["adp_rank"].tolist()), [110.0, 120.0, 130.0])
        k = enriched[enriched["position"] == "K"]
        self.assertEqual(len(k), 2)

    def test_no_append_when_adp_lacks_position(self):
        adp = self._adp().drop(columns=["position"])
        enriched = compute_value_scores(_skill_pool(), adp_df=adp)
        self.assertNotIn("DST", set(enriched["position"]))

    def test_no_duplicate_when_projections_already_have_dst(self):
        pool = pd.concat(
            [
                _skill_pool(),
                pd.DataFrame(
                    [
                        {
                            "player_id": "dstx",
                            "player_name": "DST A",
                            "position": "DST",
                            "projected_season_points": np.nan,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        enriched = compute_value_scores(pool, adp_df=self._adp())
        self.assertEqual(len(enriched[enriched["position"] == "DST"]), 1)

    _FULL_SKILL = [
        "qb0",
        "rb1",
        "rb2",
        "rb3",
        "rb4",
        "wr0",
        "wr1",
        "wr2",
        "wr3",
        "te0",
        "rb5",
        "wr4",
        "rb6",
    ]

    def test_dst_never_recommended_before_final_picks(self):
        board = self._kd_board(my_ids=self._FULL_SKILL)
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10, my_picks_remaining=6)
        self.assertFalse(set(recs["position"]) & {"K", "DST"})

    def test_dst_not_top_in_buffer_window(self):
        # my_picks_remaining == open K/DST + 1: visible but never on top.
        board = self._kd_board(my_ids=self._FULL_SKILL)
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10, my_picks_remaining=3)
        self.assertNotIn(recs.iloc[0]["position"], ("K", "DST"))

    def test_best_adp_dst_recommended_in_final_picks(self):
        board = self._kd_board(my_ids=self._FULL_SKILL)
        advisor = DraftAdvisor(board)
        recs, reasoning = advisor.recommend(top_n=5, my_picks_remaining=2)
        self.assertEqual(recs.iloc[0]["player_name"], "DST A")
        self.assertIn(recs.iloc[0]["position"], ("K", "DST"))
        self.assertIn("final picks", reasoning)
        # Among ADP-only DSTs, room ADP orders the recommendation.
        dst_rows = recs[recs["position"] == "DST"]
        adps = dst_rows["adp_rank"].tolist()
        self.assertEqual(adps, sorted(adps))

    def test_queue_includes_dst_when_forced(self):
        # build_queue must be able to draft an ADP-only row (NaN player_id)
        # without stalling or duplicating entries.
        board = self._kd_board(my_ids=self._FULL_SKILL)
        advisor = DraftAdvisor(board)
        queue = advisor.build_queue(depth=4, my_picks_remaining=2)
        names = [q["player_name"] for q in queue]
        self.assertEqual(len(names), len(set(names)), "no duplicate queue entries")
        self.assertIn("DST A", names)


class TestCheckpointUrgency(unittest.TestCase):
    """§38: once the remaining picks before a checkpoint are all needed to
    hit it, non-lagging positions are demoted."""

    def test_round6_checkpoint_forces_rb_wr(self):
        # Round 5 (4 picks), only 1 RB + 1 WR: need 1 RB + 2 WR in 2 picks
        # by R6 — impossible slack, so QB/TE are demoted with a §38 tag.
        board = _board(my_ids=["rb1", "wr0", "qb0", "te0"])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10)
        self.assertIn(recs.iloc[0]["position"], ("RB", "WR"))

    def test_checkpoint_lagging_wr3_exempt_from_starters_first(self):
        # Round 6, 2 RB + 2 WR + QB rostered: WR dedicated starters are full
        # but the R6 checkpoint still wants a 3rd WR — §38 outranks §0's
        # "backup" reading, so WR must be the top rec (not demoted), while
        # TE (a dedicated starter!) yields to the closing checkpoint.
        board = _board(my_ids=["qb0", "rb1", "rb2", "wr0", "wr1"])
        advisor = DraftAdvisor(board)
        recs, _ = advisor.recommend(top_n=10)
        self.assertEqual(recs.iloc[0]["position"], "WR")
        self.assertEqual(recs.iloc[0]["demotion_rule"], "")


if __name__ == "__main__":
    unittest.main()
