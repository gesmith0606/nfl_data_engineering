"""Regression tests for the nflverse spread_line sign convention.

nflverse ``spread_line`` is the expected HOME margin: POSITIVE when the home
team is favored. Verified empirically vs moneylines (99.6% agreement,
2022-24 schedules). A 2026-06-12 audit found five fantasy-side functions
assuming the opposite (betting-odds) convention, which swapped implied team
totals between favorites and underdogs in every game and inverted the RB
run-heavy bonus. These tests pin the corrected behavior.

Canonical example (2024 w18): BAL home vs CLE, spread_line=+19.5,
total_line=42.5, home_moneyline=-2400 → BAL implied 31.0, CLE implied 11.5.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture
def schedule_home_favorite() -> pd.DataFrame:
    """One game: home team favored by 7, total 44 → home 25.5, away 18.5."""
    return pd.DataFrame(
        [
            {
                "season": 2024,
                "week": 1,
                "home_team": "KC",
                "away_team": "CAR",
                "spread_line": 7.0,  # nflverse: positive = HOME favored
                "total_line": 44.0,
            }
        ]
    )


class TestImpliedTotalsFavoriteGetsMore:
    """The favorite must always carry the larger implied total."""

    def test_player_analytics_compute_implied_team_totals(
        self, schedule_home_favorite: pd.DataFrame
    ) -> None:
        from player_analytics import compute_implied_team_totals

        totals = compute_implied_team_totals(schedule_home_favorite)
        assert totals["KC"] == pytest.approx(25.5)
        assert totals["CAR"] == pytest.approx(18.5)

    def test_backtest_week_implied_totals(
        self, schedule_home_favorite: pd.DataFrame
    ) -> None:
        from backtest_projections import _compute_week_implied_totals

        totals = _compute_week_implied_totals(schedule_home_favorite, week=1)
        assert totals is not None
        assert totals["KC"] == pytest.approx(25.5)
        assert totals["CAR"] == pytest.approx(18.5)

    def test_generate_projections_load_implied_totals(
        self, schedule_home_favorite: pd.DataFrame
    ) -> None:
        from generate_projections import _load_implied_totals

        totals = _load_implied_totals(schedule_home_favorite, week=1)
        assert totals is not None
        assert totals["KC"] == pytest.approx(25.5)
        assert totals["CAR"] == pytest.approx(18.5)

    def test_feature_engineering_implied_team_total(
        self, schedule_home_favorite: pd.DataFrame
    ) -> None:
        from player_feature_engineering import _add_implied_totals

        players = pd.DataFrame(
            [
                {"recent_team": "KC", "season": 2024, "week": 1},
                {"recent_team": "CAR", "season": 2024, "week": 1},
            ]
        )
        out = _add_implied_totals(players, schedule_home_favorite)
        kc = out.loc[out["recent_team"] == "KC", "implied_team_total"].iloc[0]
        car = out.loc[out["recent_team"] == "CAR", "implied_team_total"].iloc[0]
        assert kc == pytest.approx(25.5)
        assert car == pytest.approx(18.5)


class TestSpreadByTeamBettingConvention:
    """_build_spread_by_team outputs negative = favored (betting convention)."""

    def test_home_favorite_gets_negative_spread(
        self, schedule_home_favorite: pd.DataFrame
    ) -> None:
        from projection_engine import _build_spread_by_team

        spreads = _build_spread_by_team(schedule_home_favorite, week=1)
        assert spreads["KC"] == pytest.approx(-7.0)
        assert spreads["CAR"] == pytest.approx(7.0)

    def test_rb_run_heavy_bonus_fires_for_favorite(self) -> None:
        """RB bonus requires implied < 20 AND the team FAVORED (spread < -7).

        RB ships with VEGAS_BETA == 0 (multiplier neutral); the bonus
        mechanism is verified under a temporary beta override.
        """
        import projection_engine
        from projection_engine import _vegas_multiplier

        original = dict(projection_engine.VEGAS_BETA)
        try:
            projection_engine.VEGAS_BETA["RB"] = 1.0
            favored = _vegas_multiplier(
                "PIT", {"PIT": 18.0}, "RB", spread_by_team={"PIT": -8.0}
            )
            dog = _vegas_multiplier(
                "NE", {"NE": 18.0}, "RB", spread_by_team={"NE": 8.0}
            )
        finally:
            projection_engine.VEGAS_BETA.clear()
            projection_engine.VEGAS_BETA.update(original)

        assert favored > dog
        # Base raw 18/23 clips to the 0.80 floor; bonus multiplies on top.
        assert favored == pytest.approx(0.80 * 1.05, abs=1e-3)

    def test_vegas_beta_damping(self) -> None:
        """QB beta=0.25 damps the multiplier; RB/WR/TE beta=0 → neutral."""
        from projection_engine import _vegas_multiplier

        qb = _vegas_multiplier("KC", {"KC": 27.6}, "QB")
        assert qb == pytest.approx(1.2**0.25, abs=1e-3)
        for pos in ["RB", "WR", "TE"]:
            assert _vegas_multiplier("KC", {"KC": 27.6}, pos) == 1.0


class TestGameScriptBoostDirection:
    """predicted_script_boost must boost favorites (leading scripts)."""

    def test_favorite_boost_above_underdog(
        self, schedule_home_favorite: pd.DataFrame
    ) -> None:
        from graph_game_script import _add_predicted_script_boost

        players = pd.DataFrame(
            [
                {"recent_team": "KC", "season": 2024, "week": 1},
                {"recent_team": "CAR", "season": 2024, "week": 1},
            ]
        )
        out = _add_predicted_script_boost(players, schedule_home_favorite)
        kc = out.loc[out["recent_team"] == "KC", "predicted_script_boost"].iloc[0]
        car = out.loc[
            out["recent_team"] == "CAR", "predicted_script_boost"
        ].iloc[0]
        # KC favored by 7 → leading script boost (>1); CAR mirrored (<1)
        assert kc > 1.0
        assert car < 1.0
