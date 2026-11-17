"""The advice-quality metric has to be able to fail.

Every other waiver check tests machinery and none of them can move when a
recommendation is wrong — week 8 2026 the audit read 100/100 through four
corrections in a row. These tests exist to keep the replacement falsifiable:
a ranking that knows nothing must score zero, a ranking that knows the answer
must score well, and the pooled-position version that scored +11.7 on nothing
must stay dead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import recommendation_backtest as rb


def _tier(points, projections, positions=None, prior=None):
    n = len(points)
    return pd.DataFrame(
        {
            "player_id": [f"p{i}" for i in range(n)],
            "player_name": [f"P{i}" for i in range(n)],
            "position": positions or ["WR"] * n,
            "projected_points": projections,
            "actual_points": points,
            "prior_points": prior if prior is not None else [0.0] * n,
            "played": [True] * n,
        }
    )


class TestTheMetricCanFail:
    def test_a_ranking_that_knows_nothing_scores_zero(self):
        """Projections uncorrelated with outcomes must not produce lift.

        Averaged over many independent boards, because one week of a 3-player
        pick is noisy enough to land anywhere; the claim is that there is no
        systematic lift, not that any single week is small.
        """
        rng = np.random.default_rng(7)
        lifts = []
        for _ in range(200):
            actual = rng.normal(8, 5, 400)
            noise = rng.normal(8, 5, 400)
            lifts.append(rb.week_lift(_tier(actual, noise), top_k=3)["lift"])
        assert abs(float(np.mean(lifts))) < 0.5

    def test_a_ranking_that_knows_the_answer_scores_well(self):
        actual = list(range(40))
        res = rb.week_lift(_tier(actual, actual), top_k=3)
        assert res["lift"] > 10

    def test_an_inverted_ranking_scores_negative(self):
        """Picking the worst must be punished, or the metric is one-sided."""
        actual = list(range(40))
        res = rb.week_lift(_tier(actual, [-a for a in actual]), top_k=3)
        assert res["lift"] < -10

    def test_the_shuffled_null_is_flat(self):
        rng = np.random.default_rng(3)
        actual = rng.normal(8, 5, 300)
        assert abs(rb.null_lift(_tier(actual, actual), top_k=3, seeds=3000)) < 0.3


class TestPositionsAreScoredSeparately:
    """The bug this metric shipped with for twenty minutes.

    Pooled across positions, "top 3 by projected points" is three
    quarterbacks, and the lift is the QB-versus-WR scoring gap. It read +11.7
    on the real board — a number an always-pick-a-QB model earns for free.
    """

    @staticmethod
    def _mixed():
        # QBs score ~20, WRs ~5; within each group the projection is useless.
        qb = _tier([20.0] * 20, [1.0] * 20, positions=["QB"] * 20)
        wr = _tier([5.0] * 20, [9.0] * 20, positions=["WR"] * 20)
        both = pd.concat([qb, wr], ignore_index=True)
        both["player_id"] = [f"x{i}" for i in range(len(both))]
        return both

    def test_a_positional_gap_does_not_create_lift(self):
        res = rb.week_lift(self._mixed(), top_k=3)
        assert res["lift"] == pytest.approx(0.0, abs=1e-9)

    def test_every_position_is_reported(self):
        res = rb.week_lift(self._mixed(), top_k=3)
        assert set(res["by_pos"]) == {"QB", "WR"}


class TestNoCreditForSilence:
    def test_a_player_with_no_actuals_row_scores_zero(self):
        """Tyler Huntley: 16.8 on our board, never going to take the field.

        Dropping unmatched players would have quietly excused exactly the
        recommendation this whole exercise exists to catch.
        """
        tier = pd.DataFrame(
            {
                "player_id": ["a", "b"],
                "player_name": ["Played", "Inactive"],
                "position": ["QB", "QB"],
                "projected_points": [10.0, 16.8],
            }
        )
        actuals = pd.DataFrame({"player_id": ["a"], "projected_points": [12.0]})
        out = rb.attach_actuals(tier, actuals)
        assert out.set_index("player_name").loc["Inactive", "actual_points"] == 0.0
        assert not out.set_index("player_name").loc["Inactive", "played"]


class TestVerdict:
    BASE = [{"lift": 3.0}, {"lift": 3.2}, {"lift": 2.8}, {"lift": 3.1}]

    def test_a_tie_with_the_naive_baseline_is_called_a_tie(self):
        s = rb.summarise(self.BASE, nulls=[0.0], naive=[3.0, 3.1, 3.0, 3.2])
        assert s["verdict"].startswith("TIED WITH THE BOX SCORE")

    def test_losing_to_the_naive_baseline_is_called_out(self):
        s = rb.summarise(self.BASE, nulls=[0.0], naive=[9.0, 9.0, 9.0, 9.0])
        assert s["verdict"].startswith("BEATEN BY THE BOX SCORE")

    def test_a_real_edge_passes(self):
        s = rb.summarise(self.BASE, nulls=[0.0], naive=[0.0, 0.1, 0.0, 0.1])
        assert s["verdict"] == "RANKING ADDS VALUE"

    def test_a_non_flat_null_voids_the_result(self):
        s = rb.summarise(self.BASE, nulls=[4.0], naive=[0.0])
        assert s["verdict"].startswith("VOID")

    def test_a_lift_below_the_mde_is_not_claimed(self):
        noisy = [{"lift": 0.4}, {"lift": -0.3}, {"lift": 0.5}, {"lift": -0.2}]
        s = rb.summarise(noisy, nulls=[0.0], naive=[0.0])
        assert s["verdict"].startswith("DIRECTIONAL")

    def test_negative_lift_fails_outright(self):
        s = rb.summarise([{"lift": -2.0}] * 4, nulls=[0.0], naive=[0.0])
        assert s["verdict"].startswith("NO VALUE")


class TestPointInTime:
    def test_a_board_written_after_kickoff_is_not_eligible(self, tmp_path, monkeypatch):
        week_dir = tmp_path / "season=2026" / "week=5"
        week_dir.mkdir(parents=True)
        early = week_dir / "projections_half_ppr_20261006_120000.parquet"
        late = week_dir / "projections_half_ppr_20261009_120000.parquet"
        for f in (early, late):
            pd.DataFrame({"player_id": ["a"]}).to_parquet(f)
        monkeypatch.setattr(rb, "GOLD", tmp_path)
        got = rb.pre_kickoff_board(2026, 5, pd.Timestamp("2026-10-08"))
        assert got == str(early)

    def test_no_eligible_board_returns_none(self, tmp_path, monkeypatch):
        week_dir = tmp_path / "season=2026" / "week=5"
        week_dir.mkdir(parents=True)
        pd.DataFrame({"player_id": ["a"]}).to_parquet(
            week_dir / "projections_half_ppr_20261009_120000.parquet"
        )
        monkeypatch.setattr(rb, "GOLD", tmp_path)
        assert rb.pre_kickoff_board(2026, 5, pd.Timestamp("2026-10-08")) is None


class TestTier:
    def test_bye_rows_are_excluded(self):
        board = pd.DataFrame(
            {
                "player_id": list("abcd"),
                "player_name": list("ABCD"),
                "position": ["WR"] * 4,
                "recent_team": ["SF", "DAL", "DAL", "DAL"],
                "projected_points": [9.0, 8.0, 7.0, 6.0],
                "is_bye_week": [False] * 4,
            }
        )
        tier = rb.waiver_tier(board, {"WR": 0}, bye_teams=["SF"])
        assert set(tier["player_name"]) == {"B", "C", "D"}

    def test_starters_are_excluded(self):
        board = pd.DataFrame(
            {
                "player_id": list("abcd"),
                "player_name": list("ABCD"),
                "position": ["WR"] * 4,
                "recent_team": ["DAL"] * 4,
                "projected_points": [9.0, 8.0, 7.0, 6.0],
            }
        )
        tier = rb.waiver_tier(board, {"WR": 2})
        assert set(tier["player_name"]) == {"C", "D"}

    def test_cutoffs_include_a_share_of_the_flex(self):
        cut = rb.starter_cutoffs({"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 3}, 10)
        assert cut["QB"] == 10
        assert cut["RB"] == 30  # 2 + 3/3 per team
        assert cut["WR"] == 40
