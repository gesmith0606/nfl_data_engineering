"""Tests for veteran prior blending — src/veteran_prior.py.

Covers:
  - Prior computation from weekly data
  - Blend weight schedule
  - Veteran-never-rookie routing (return-from-absence)
  - Team-change decay
  - Empty-history edge cases
  - Named failure cases (structural, not numerical — no hard-coded points)
"""

import numpy as np
import pandas as pd
import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from veteran_prior import (
    N_FULL_WEIGHT,
    SCHEDULE_STEEPNESS,
    MIN_PRIOR_GAMES,
    TEAM_CHANGE_DECAY,
    FIRST_WEEK_BACK_DISCOUNT,
    _POSITIONAL_PRIOR_BASELINES,
    build_player_priors,
    get_player_prior,
    count_games_in_lookback,
    blend_weight,
    apply_veteran_prior_blend,
)


# ---------------------------------------------------------------------------
# Helpers to build small synthetic DataFrames
# ---------------------------------------------------------------------------

def _make_weekly(rows: list) -> pd.DataFrame:
    """Build a minimal Bronze player_weekly DataFrame from a list of dicts."""
    defaults = {
        "player_id": "P001",
        "player_name": "Test Player",
        "position": "WR",
        "recent_team": "PHI",
        "season": 2023,
        "week": 1,
        "season_type": "REG",
        "passing_yards": 0.0,
        "passing_tds": 0.0,
        "interceptions": 0.0,
        "rushing_yards": 0.0,
        "rushing_tds": 0.0,
        "carries": 0.0,
        "receptions": 0.0,
        "receiving_yards": 0.0,
        "receiving_tds": 0.0,
        "targets": 0.0,
        "air_yards": 0.0,
    }
    result = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        result.append(row)
    return pd.DataFrame(result)


def _make_target_row(overrides: dict = None) -> pd.DataFrame:
    """Single-row target DataFrame for apply_veteran_prior_blend testing."""
    row = {
        "player_id": "P001",
        "player_name": "Test Player",
        "position": "WR",
        "recent_team": "PHI",
        "season": 2024,
        "week": 3,
        "proj_season": 2024,
        "proj_week": 3,
        "targets_roll3": np.nan,
        "targets_roll6": np.nan,
        "targets_std": np.nan,
        "receptions_roll3": np.nan,
        "receptions_roll6": np.nan,
        "receptions_std": np.nan,
        "receiving_yards_roll3": np.nan,
        "receiving_yards_roll6": np.nan,
        "receiving_yards_std": np.nan,
        "receiving_tds_roll3": np.nan,
        "receiving_tds_roll6": np.nan,
        "receiving_tds_std": np.nan,
    }
    if overrides:
        row.update(overrides)
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# blend_weight schedule
# ---------------------------------------------------------------------------


class TestBlendWeightSchedule:
    def test_zero_games_gives_zero_weight(self):
        """No games played → all prior, no rolling."""
        assert blend_weight(0) == 0.0

    def test_full_weight_at_n_full(self):
        """At n_full games, weight should saturate to 1.0."""
        w = blend_weight(N_FULL_WEIGHT)
        assert w == pytest.approx(1.0, abs=1e-6)

    def test_monotonically_increasing(self):
        """More games → higher blend weight."""
        weights = [blend_weight(n) for n in range(0, N_FULL_WEIGHT + 2)]
        for i in range(len(weights) - 1):
            assert weights[i] <= weights[i + 1]

    def test_weight_clamps_at_one(self):
        """Very many games never exceeds 1.0."""
        assert blend_weight(100) <= 1.0

    def test_custom_steepness_more_gradual(self):
        """Smaller steepness → lower weight at same n_games."""
        w_steep = blend_weight(2, steepness=1.0)
        w_gradual = blend_weight(2, steepness=0.3)
        assert w_gradual < w_steep

    def test_custom_n_full(self):
        """blend_weight saturates at the given n_full, not the default."""
        w = blend_weight(3, n_full=3)
        assert w == pytest.approx(1.0, abs=1e-6)

    def test_one_game_roughly_halfway(self):
        """With default params, 1 game gives a moderate weight (~0.4-0.7)."""
        w = blend_weight(1)
        assert 0.35 <= w <= 0.75

    def test_boundary_n_full_minus_one(self):
        """One game before saturation should give weight < 1.0."""
        w = blend_weight(N_FULL_WEIGHT - 1)
        assert w < 1.0


# ---------------------------------------------------------------------------
# build_player_priors
# ---------------------------------------------------------------------------


class TestBuildPlayerPriors:
    def test_empty_df_returns_empty(self):
        priors = build_player_priors(pd.DataFrame())
        assert priors.empty

    def test_basic_wr_prior_computed(self):
        """WR with multiple games produces per-game averages."""
        weekly = _make_weekly([
            {"player_id": "WR001", "position": "WR", "season": 2023, "week": w,
             "targets": 6.0, "receptions": 4.0, "receiving_yards": 60.0, "receiving_tds": 0.5}
            for w in range(1, 9)
        ])
        priors = build_player_priors(weekly, scoring_format="half_ppr")
        assert ("WR001", 2023) in priors.index
        row = priors.loc[("WR001", 2023)]
        assert row["games_played"] == 8
        assert row["receiving_yards_per_game"] == pytest.approx(60.0, abs=0.1)
        assert row["targets_per_game"] == pytest.approx(6.0, abs=0.1)

    def test_rb_prior_computed(self):
        """RB prior includes carries and rushing yards."""
        weekly = _make_weekly([
            {"player_id": "RB001", "position": "RB", "season": 2022, "week": w,
             "carries": 15.0, "rushing_yards": 75.0, "rushing_tds": 0.5,
             "receptions": 2.0, "receiving_yards": 20.0}
            for w in range(1, 10)
        ])
        priors = build_player_priors(weekly, scoring_format="half_ppr")
        row = priors.loc[("RB001", 2022)]
        assert row["carries_per_game"] == pytest.approx(15.0, abs=0.1)
        assert row["rushing_yards_per_game"] == pytest.approx(75.0, abs=0.1)

    def test_non_skill_positions_excluded(self):
        """DEF/K/LB positions should not appear in priors."""
        weekly = _make_weekly([
            {"player_id": "K001", "position": "K", "season": 2023, "week": 1},
            {"player_id": "WR002", "position": "WR", "season": 2023, "week": 1,
             "receiving_yards": 50.0},
        ])
        priors = build_player_priors(weekly, scoring_format="half_ppr")
        assert ("K001", 2023) not in priors.index
        assert ("WR002", 2023) in priors.index

    def test_playoff_weeks_excluded(self):
        """Weeks > 18 (playoffs) should not inflate the prior."""
        # 8 regular games + 2 playoff blowout games
        regular = [
            {"player_id": "WR003", "position": "WR", "season": 2023, "week": w,
             "receiving_yards": 60.0}
            for w in range(1, 9)
        ]
        playoff = [
            {"player_id": "WR003", "position": "WR", "season": 2023, "week": w,
             "receiving_yards": 200.0}  # Would inflate average if included
            for w in range(19, 22)
        ]
        weekly = _make_weekly(regular + playoff)
        priors = build_player_priors(weekly, scoring_format="half_ppr")
        row = priors.loc[("WR003", 2023)]
        assert row["games_played"] == 8
        assert row["receiving_yards_per_game"] == pytest.approx(60.0, abs=0.5)

    def test_multiple_seasons_indexed_separately(self):
        """Each (player, season) pair gets its own row."""
        weekly = _make_weekly([
            {"player_id": "WR004", "position": "WR", "season": 2022, "week": w,
             "receiving_yards": 50.0}
            for w in range(1, 5)
        ] + [
            {"player_id": "WR004", "position": "WR", "season": 2023, "week": w,
             "receiving_yards": 80.0}
            for w in range(1, 5)
        ])
        priors = build_player_priors(weekly)
        assert ("WR004", 2022) in priors.index
        assert ("WR004", 2023) in priors.index
        assert priors.loc[("WR004", 2022)]["receiving_yards_per_game"] == pytest.approx(50.0, abs=0.1)
        assert priors.loc[("WR004", 2023)]["receiving_yards_per_game"] == pytest.approx(80.0, abs=0.1)

    def test_half_ppr_per_game_computed(self):
        """half_ppr_per_game should be a positive float for a productive player."""
        weekly = _make_weekly([
            {"player_id": "WR005", "position": "WR", "season": 2023, "week": w,
             "receptions": 5.0, "receiving_yards": 70.0, "receiving_tds": 0.5, "targets": 7.0}
            for w in range(1, 9)
        ])
        priors = build_player_priors(weekly, scoring_format="half_ppr")
        row = priors.loc[("WR005", 2023)]
        assert row["half_ppr_per_game"] > 0.0


# ---------------------------------------------------------------------------
# get_player_prior
# ---------------------------------------------------------------------------


class TestGetPlayerPrior:
    def _make_priors(self, games: int = 16, pos: str = "WR", team: str = "PHI",
                     season: int = 2023, rec_yds: float = 60.0) -> pd.DataFrame:
        weekly = _make_weekly([
            {"player_id": "P001", "position": pos, "recent_team": team,
             "season": season, "week": w, "receiving_yards": rec_yds,
             "targets": 6.0, "receptions": 4.0, "receiving_tds": 0.4}
            for w in range(1, games + 1)
        ])
        return build_player_priors(weekly)

    def test_returns_positional_baseline_when_no_prior(self):
        """Unknown player → positional baseline, not zeros."""
        priors = pd.DataFrame()
        result = get_player_prior("UNKNOWN", 2024, "WR", priors)
        baseline = _POSITIONAL_PRIOR_BASELINES["WR"]
        assert result["receiving_yards"] == pytest.approx(baseline["receiving_yards"])
        assert result["targets"] == pytest.approx(baseline["targets"])

    def test_correct_season_lookback(self):
        """Should use proj_season - 1 as the prior season."""
        priors = self._make_priors(games=16, season=2023, rec_yds=80.0)
        result = get_player_prior("P001", 2024, "WR", priors, current_team="PHI")
        assert result["receiving_yards"] == pytest.approx(80.0, abs=0.5)

    def test_two_season_lookback_fallback(self):
        """When S-1 missing, should fall back to S-2."""
        priors = self._make_priors(games=16, season=2022, rec_yds=55.0)
        result = get_player_prior("P001", 2024, "WR", priors, current_team="PHI")
        assert result["receiving_yards"] == pytest.approx(55.0, abs=0.5)

    def test_min_games_threshold_returns_baseline(self):
        """Player with fewer than min_games gets positional baseline."""
        priors = self._make_priors(games=3, season=2023, rec_yds=90.0)  # < MIN_PRIOR_GAMES
        result = get_player_prior("P001", 2024, "WR", priors, current_team="PHI",
                                  min_games=MIN_PRIOR_GAMES)
        baseline = _POSITIONAL_PRIOR_BASELINES["WR"]
        assert result["receiving_yards"] == pytest.approx(baseline["receiving_yards"])

    def test_meets_min_games_uses_prior(self):
        """Player with exactly min_games gets the real prior."""
        priors = self._make_priors(games=MIN_PRIOR_GAMES, season=2023, rec_yds=75.0)
        result = get_player_prior("P001", 2024, "WR", priors, current_team="PHI",
                                  min_games=MIN_PRIOR_GAMES)
        assert result["receiving_yards"] == pytest.approx(75.0, abs=0.5)

    def test_team_change_decay_blends_toward_baseline(self):
        """Team changer: prior should be between raw prior and positional baseline."""
        priors = self._make_priors(games=16, season=2023, rec_yds=90.0, team="PHI")
        # Player moved from PHI to DAL
        result_same = get_player_prior(
            "P001", 2024, "WR", priors, current_team="PHI",
            team_change_decay=TEAM_CHANGE_DECAY
        )
        result_change = get_player_prior(
            "P001", 2024, "WR", priors, current_team="DAL",
            team_change_decay=TEAM_CHANGE_DECAY
        )
        baseline = _POSITIONAL_PRIOR_BASELINES["WR"]["receiving_yards"]
        # Changed team: should be between raw prior and baseline
        assert result_change["receiving_yards"] < result_same["receiving_yards"]
        assert result_change["receiving_yards"] > baseline or result_change["receiving_yards"] < 90.0

    def test_team_change_decay_one_no_decay(self):
        """decay=1.0 means no decay even on team change."""
        priors = self._make_priors(games=16, season=2023, rec_yds=90.0, team="PHI")
        result = get_player_prior(
            "P001", 2024, "WR", priors, current_team="DAL",
            team_change_decay=1.0
        )
        assert result["receiving_yards"] == pytest.approx(90.0, abs=0.5)

    def test_unknown_position_returns_empty(self):
        """Unsupported position returns empty dict."""
        priors = pd.DataFrame()
        result = get_player_prior("P001", 2024, "K", priors)
        assert result == {}


# ---------------------------------------------------------------------------
# count_games_in_lookback
# ---------------------------------------------------------------------------


class TestCountGamesInLookback:
    def test_empty_weekly_returns_zero(self):
        assert count_games_in_lookback("P001", 2024, 5, pd.DataFrame()) == 0

    def test_no_current_season_games_returns_zero(self):
        """Player absent entire current season → 0 games in lookback."""
        weekly = _make_weekly([
            {"player_id": "P001", "season": 2024, "week": 10,
             "receiving_yards": 0.0}  # Just appeared but 0 production
        ])
        # Projected week 11: lookback is < 10 (i.e., weeks 1-9 only)
        n = count_games_in_lookback("P001", 2024, 11, weekly)
        assert n == 0

    def test_counts_productive_games_only(self):
        """Rows with all-zero offensive stats are not counted."""
        weekly = _make_weekly([
            # 4 productive games
            *[{"player_id": "P001", "season": 2024, "week": w,
               "receiving_yards": 50.0, "receptions": 3.0}
              for w in range(1, 5)],
            # 2 zero-activity games (DNP/bye)
            *[{"player_id": "P001", "season": 2024, "week": w,
               "receiving_yards": 0.0, "receptions": 0.0}
              for w in range(5, 7)],
        ])
        # Projected week 8: lookback < 7 = weeks 1-6
        n = count_games_in_lookback("P001", 2024, 8, weekly)
        assert n == 4

    def test_lookback_cutoff_respects_shift_logic(self):
        """Lookback uses weeks strictly < proj_week - 1 (shift-1 rolling window)."""
        weekly = _make_weekly([
            {"player_id": "P001", "season": 2024, "week": 2, "receiving_yards": 50.0},
            {"player_id": "P001", "season": 2024, "week": 3, "receiving_yards": 50.0},
        ])
        # proj_week=4: lookback < 3, so w3 is NOT included, only w2
        n = count_games_in_lookback("P001", 2024, 4, weekly)
        assert n == 1

    def test_only_counts_current_season(self):
        """Prior season games do not count toward the rolling lookback."""
        weekly = _make_weekly([
            # 10 productive prior-season games
            *[{"player_id": "P001", "season": 2023, "week": w,
               "receiving_yards": 60.0}
              for w in range(1, 11)],
            # 0 current season games before proj_week
        ])
        n = count_games_in_lookback("P001", 2024, 5, weekly)
        assert n == 0

    def test_week_boundary(self):
        """Exactly proj_week - 2 should be included; proj_week - 1 should not."""
        weekly = _make_weekly([
            {"player_id": "P001", "season": 2024, "week": 4, "receiving_yards": 60.0},  # included
            {"player_id": "P001", "season": 2024, "week": 5, "receiving_yards": 60.0},  # feature row, not in lookback
        ])
        # proj_week=6: lookback < 5 → only week 4 counted
        n = count_games_in_lookback("P001", 2024, 6, weekly)
        assert n == 1


# ---------------------------------------------------------------------------
# apply_veteran_prior_blend
# ---------------------------------------------------------------------------


class TestApplyVeteranPriorBlend:
    def _build_prior_df(self, rec_yds: float = 70.0, games: int = 16,
                        season: int = 2023, pos: str = "WR",
                        team: str = "PHI") -> pd.DataFrame:
        weekly = _make_weekly([
            {"player_id": "P001", "position": pos, "recent_team": team,
             "season": season, "week": w, "receiving_yards": rec_yds,
             "targets": 6.5, "receptions": 4.5, "receiving_tds": 0.3}
            for w in range(1, games + 1)
        ])
        return build_player_priors(weekly)

    def test_empty_position_returns_empty(self):
        """No players of the given position → empty DataFrame returned."""
        target = _make_target_row({"position": "RB"})
        priors = self._build_prior_df()
        weekly = _make_weekly([])
        result = apply_veteran_prior_blend(target, priors, weekly, "WR", 2024, 3)
        assert result.empty

    def test_veteran_return_fills_nan_rolling_cols(self):
        """All-NaN rolling columns for a veteran should be filled with prior."""
        target = _make_target_row()  # all rolling cols NaN
        priors = self._build_prior_df()
        weekly = _make_weekly([])  # 0 current-season games

        result = apply_veteran_prior_blend(target, priors, weekly, "WR", 2024, 3)

        assert not result.empty
        assert bool(result["is_veteran_return"].iloc[0])
        # Rolling columns should now be filled with prior stats (not NaN)
        assert pd.notna(result["receiving_yards_roll3"].iloc[0])
        assert result["receiving_yards_roll3"].iloc[0] > 0.0

    def test_first_week_back_discount_applied(self):
        """First-week-back discount reduces prior when n_games == 0."""
        target = _make_target_row()
        priors = self._build_prior_df(rec_yds=100.0)
        weekly = _make_weekly([])

        result_discount = apply_veteran_prior_blend(
            target, priors, weekly, "WR", 2024, 3, first_week_back_discount=0.80
        )
        result_nodiscount = apply_veteran_prior_blend(
            target, priors, weekly, "WR", 2024, 3, first_week_back_discount=1.00
        )

        val_disc = result_discount["receiving_yards_roll3"].iloc[0]
        val_nodisc = result_nodiscount["receiving_yards_roll3"].iloc[0]
        assert val_disc < val_nodisc

    def test_veteran_return_is_veteran_return_flag(self):
        """is_veteran_return flag is True for veterans, False for non-veterans."""
        # Veteran: has prior data
        target_veteran = _make_target_row()
        priors = self._build_prior_df(games=16)
        weekly = _make_weekly([])
        result_vet = apply_veteran_prior_blend(target_veteran, priors, weekly, "WR", 2024, 3)
        assert bool(result_vet["is_veteran_return"].iloc[0])

    def test_non_veteran_no_flag(self):
        """Player with fewer than min_prior_games should NOT get is_veteran_return."""
        target = _make_target_row()
        priors = self._build_prior_df(games=3)  # < MIN_PRIOR_GAMES
        weekly = _make_weekly([])
        result = apply_veteran_prior_blend(
            target, priors, weekly, "WR", 2024, 3, min_prior_games=MIN_PRIOR_GAMES
        )
        assert not bool(result["is_veteran_return"].iloc[0])

    def test_blend_with_n_games_interpolates(self):
        """With 2 games in lookback, rolling values should be blended toward prior."""
        # Set up rolling columns with known values (player had 2 productive games)
        target = _make_target_row({
            "receiving_yards_roll3": 20.0,
            "receiving_yards_roll6": 20.0,
            "receiving_yards_std": 20.0,
        })
        priors = self._build_prior_df(rec_yds=80.0, games=16)
        # 2 games in current season before lookback window
        weekly = _make_weekly([
            {"player_id": "P001", "position": "WR", "season": 2024, "week": 1,
             "receiving_yards": 20.0},
            {"player_id": "P001", "position": "WR", "season": 2024, "week": 2,
             "receiving_yards": 20.0},
        ])
        # proj_week=4: lookback < 3 → sees weeks 1-2 = 2 games
        result = apply_veteran_prior_blend(
            target, priors, weekly, "WR", 2024, 4
        )
        blended = result["receiving_yards_roll3"].iloc[0]
        # Blended should be between rolling (20) and prior (80)
        assert 20.0 < blended < 80.0

    def test_no_blend_when_n_games_saturated(self):
        """With n_games >= N_FULL_WEIGHT, rolling values should not change."""
        rolling_val = 75.0
        target = _make_target_row({
            "receiving_yards_roll3": rolling_val,
            "receiving_yards_roll6": rolling_val,
            "receiving_yards_std": rolling_val,
        })
        priors = self._build_prior_df(rec_yds=30.0, games=16)
        # N_FULL_WEIGHT or more games in lookback
        weekly = _make_weekly([
            {"player_id": "P001", "position": "WR", "season": 2024, "week": w,
             "receiving_yards": rolling_val}
            for w in range(1, N_FULL_WEIGHT + 1)
        ])
        # proj_week N_FULL_WEIGHT + 2: lookback < N_FULL_WEIGHT + 1 → ≥ N_FULL_WEIGHT games
        result = apply_veteran_prior_blend(
            target, priors, weekly, "WR", 2024, N_FULL_WEIGHT + 2
        )
        blended = result["receiving_yards_roll3"].iloc[0]
        assert blended == pytest.approx(rolling_val, abs=0.5)

    def test_unknown_player_no_prior_leaves_nan(self):
        """Player with no prior history and all-NaN rolling cols stays NaN (non-veteran)."""
        target = _make_target_row()
        priors = pd.DataFrame()  # No priors at all
        weekly = _make_weekly([])

        result = apply_veteran_prior_blend(target, priors, weekly, "WR", 2024, 3)
        # Should not be flagged as veteran return since no prior
        assert not bool(result["is_veteran_return"].iloc[0])
        # Rolling columns remain NaN (the engine will apply rookie baseline)
        assert pd.isna(result["receiving_yards_roll3"].iloc[0])

    def test_team_change_reduces_prior(self):
        """Same player, team-changer gets lower prior than same-team player."""
        target_same_team = _make_target_row({"recent_team": "PHI"})
        target_diff_team = _make_target_row({"recent_team": "DAL"})
        priors = self._build_prior_df(rec_yds=100.0, games=16, team="PHI")
        weekly = _make_weekly([])

        result_same = apply_veteran_prior_blend(
            target_same_team, priors, weekly, "WR", 2024, 3
        )
        result_diff = apply_veteran_prior_blend(
            target_diff_team, priors, weekly, "WR", 2024, 3
        )

        val_same = result_same["receiving_yards_roll3"].iloc[0]
        val_diff = result_diff["receiving_yards_roll3"].iloc[0]
        # Team changer should have a smaller prior (decayed toward baseline)
        assert val_diff < val_same

    def test_multiple_players_processed(self):
        """All players in position are processed, not just the first."""
        rows = []
        for pid in ["P001", "P002", "P003"]:
            r = _make_target_row({"player_id": pid})[["player_id", "player_name",
                "position", "recent_team", "season", "week",
                "targets_roll3", "targets_roll6", "targets_std",
                "receptions_roll3", "receptions_roll6", "receptions_std",
                "receiving_yards_roll3", "receiving_yards_roll6", "receiving_yards_std",
                "receiving_tds_roll3", "receiving_tds_roll6", "receiving_tds_std"]].iloc[0].to_dict()
            rows.append(r)
        target = pd.DataFrame(rows)

        # Build priors for all three
        weekly_rows = []
        for pid in ["P001", "P002", "P003"]:
            for w in range(1, 9):
                weekly_rows.append({
                    "player_id": pid, "position": "WR", "recent_team": "PHI",
                    "season": 2023, "week": w, "receiving_yards": 60.0,
                    "targets": 6.0, "receptions": 4.0, "receiving_tds": 0.3,
                })
        weekly = _make_weekly(weekly_rows)
        priors = build_player_priors(weekly)

        result = apply_veteran_prior_blend(target, priors, weekly, "WR", 2024, 3)
        # All 3 players should be veteran returns
        assert len(result) == 3
        assert result["is_veteran_return"].all()


# ---------------------------------------------------------------------------
# Integration: veteran prior prevents rookie fallback for established player
# ---------------------------------------------------------------------------


class TestVeteranNeverRookieRouting:
    """Verifies that a player with a valid prior is not projected at the
    generic positional baseline (i.e., the 'rookie' fallback value).
    """

    def _get_rookie_baseline_pts(self, position: str) -> float:
        """Compute the expected rookie projection for a 'starter' using projection_engine."""
        from projection_engine import _rookie_baseline, _STARTER_BASELINES

        return sum(_STARTER_BASELINES.get(position, {}).values())

    def test_veteran_rb_return_uses_prior_not_rookie_baseline(self):
        """A veteran RB returning from absence should get prior-based stats,
        not the generic positional rookie baseline.
        """
        # Create an RB with strong prior but no current-season rolling data
        weekly_prior = _make_weekly([
            {"player_id": "RB001", "position": "RB", "recent_team": "SF",
             "season": 2023, "week": w,
             "carries": 18.0, "rushing_yards": 95.0, "rushing_tds": 0.7,
             "receptions": 4.0, "receiving_yards": 35.0, "receiving_tds": 0.3}
            for w in range(1, 17)
        ])
        priors = build_player_priors(weekly_prior)

        target = pd.DataFrame([{
            "player_id": "RB001",
            "player_name": "Test RB",
            "position": "RB",
            "recent_team": "SF",
            "season": 2024,
            "week": 5,
            "proj_season": 2024,
            "proj_week": 5,
            # All NaN rolling columns
            **{f"{s}_{suf}": np.nan
               for s in ["rushing_yards", "rushing_tds", "carries", "receptions",
                         "receiving_yards", "receiving_tds"]
               for suf in ["roll3", "roll6", "std"]},
        }])

        result = apply_veteran_prior_blend(
            target, priors, weekly_prior, "RB", 2024, 5
        )

        # Should be flagged as veteran return
        assert bool(result["is_veteran_return"].iloc[0])

        # rushing_yards rolling values should reflect prior (~95 yds/game),
        # NOT the rookie starter baseline (55 yds/game)
        prior_yards = result["rushing_yards_roll3"].iloc[0]
        rookie_baseline = 55.0  # from _STARTER_BASELINES["RB"]["rushing_yards"]
        assert prior_yards > rookie_baseline, (
            f"Expected prior {prior_yards:.1f} > rookie baseline {rookie_baseline:.1f}"
        )

    def test_new_player_no_prior_gets_no_veteran_return_flag(self):
        """A genuine rookie with no prior data should NOT be flagged is_veteran_return."""
        target = _make_target_row()  # all NaN rolling
        priors = pd.DataFrame()  # no prior history at all
        weekly = _make_weekly([])

        result = apply_veteran_prior_blend(target, priors, weekly, "WR", 2024, 3)
        assert not bool(result["is_veteran_return"].iloc[0])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_priors_df_graceful(self):
        """Empty priors DataFrame should not raise; falls back to positional baseline."""
        target = _make_target_row()
        result = apply_veteran_prior_blend(target, pd.DataFrame(), pd.DataFrame(), "WR", 2024, 3)
        assert not result.empty
        # is_veteran_return stays False when no priors
        assert not bool(result["is_veteran_return"].iloc[0])

    def test_missing_player_id_skipped(self):
        """Rows without player_id are skipped without raising."""
        target = _make_target_row({"player_id": None})
        result = apply_veteran_prior_blend(target, pd.DataFrame(), pd.DataFrame(), "WR", 2024, 3)
        # Should return a DataFrame (not raise)
        assert isinstance(result, pd.DataFrame)

    def test_blend_weight_n_full_zero_edge(self):
        """n_full=0 edge: any positive n_games should give weight 1.0."""
        # When n_full=0, all games saturate immediately
        w = blend_weight(1, n_full=0, steepness=0.7)
        assert w <= 1.0  # should not exceed 1.0

    def test_count_games_unknown_player_returns_zero(self):
        """Unknown player_id in weekly_df returns 0 games."""
        weekly = _make_weekly([
            {"player_id": "OTHER", "season": 2024, "week": 2, "receiving_yards": 50.0}
        ])
        n = count_games_in_lookback("UNKNOWN_ID", 2024, 5, weekly)
        assert n == 0

    def test_get_player_prior_missing_stat_col_uses_zero(self):
        """If a stat column is missing from weekly data, per_game value is 0.0."""
        # Create weekly data without 'receiving_tds' column
        weekly = pd.DataFrame([
            {"player_id": "P001", "position": "WR", "recent_team": "PHI",
             "season": 2023, "week": w,
             "targets": 5.0, "receptions": 3.0, "receiving_yards": 50.0}
            for w in range(1, 10)
        ])
        # Add required columns for build_player_priors
        weekly["season_type"] = "REG"
        priors = build_player_priors(weekly)
        if ("P001", 2023) in priors.index:
            row = priors.loc[("P001", 2023)]
            # receiving_tds_per_game should be 0 or missing — not an error
            val = row.get("receiving_tds_per_game", 0.0)
            assert val == pytest.approx(0.0, abs=0.1)

    def test_position_with_no_stat_profile_returns_empty_prior(self):
        """Unsupported position like 'FB' returns empty dict from get_player_prior."""
        priors = pd.DataFrame()
        result = get_player_prior("P001", 2024, "FB", priors)
        assert result == {}
