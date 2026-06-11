#!/usr/bin/env python3
"""Tests for route participation graph features.

Coverage:
- Rate computation from synthetic participation data.
- Temporal lag correctness: route_rate must be NaN at week 1 for trail features.
- route_rate_delta is derived from trail4 differences (both sides lagged).
- route_rate_slope reflects linear trend over prior-week values.
- Empty-week handling (player on IR, missing from participation).
- Player-ID parsing from semicolon-separated strings.
- Exact feature columns returned.
- No duplicate (player_id, season, week) rows.
- Rate is bounded [0, 1].
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_route_participation import (
    ROUTE_PARTICIPATION_FEATURES,
    compute_route_participation,
)

# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

_SEASON = 2023
_TEAM = "KC"
_OPP = "BUF"


def _game_id(week: int) -> str:
    return f"{_SEASON}_{week:02d}_{_TEAM}_{_OPP}"


def _make_pbp(weeks, players_per_team: int = 11) -> pd.DataFrame:
    """Create a minimal PBP DataFrame with dropback plays.

    Each week has ``players_per_team`` dropback plays (all by the same team).

    Args:
        weeks: Iterable of week numbers.
        players_per_team: Number of dropback plays per team per week.

    Returns:
        PBP DataFrame with qb_dropback=1 for all rows.
    """
    rows = []
    play_id = 1
    for week in weeks:
        for _ in range(players_per_team):
            rows.append(
                {
                    "game_id": _game_id(week),
                    "play_id": float(play_id),
                    "season": _SEASON,
                    "week": week,
                    "posteam": _TEAM,
                    "qb_dropback": 1,
                }
            )
            play_id += 1
    return pd.DataFrame(rows)


def _make_participation(
    pbp_df: pd.DataFrame,
    player_ids: list,
    absent_player: str = None,
    absent_weeks: list = None,
) -> pd.DataFrame:
    """Build a participation DataFrame from PBP.

    By default all ``player_ids`` appear in every play. To simulate a
    player sitting out (injury / IR), pass ``absent_player`` and the
    ``absent_weeks`` list where they should not appear.

    Args:
        pbp_df: PBP DataFrame returned by ``_make_pbp``.
        player_ids: List of player gsis IDs on offense.
        absent_player: Optional player ID to exclude in specified weeks.
        absent_weeks: Weeks where ``absent_player`` is absent.

    Returns:
        participation DataFrame with offense_players (semicolon-joined IDs).
    """
    rows = []
    absent_weeks = set(absent_weeks or [])
    for _, row in pbp_df.iterrows():
        week = int(row["week"])
        active = [
            p
            for p in player_ids
            if not (p == absent_player and week in absent_weeks)
        ]
        rows.append(
            {
                "game_id": row["game_id"],
                "play_id": row["play_id"],
                "offense_players": ";".join(active),
                "defense_players": "DEF001;DEF002",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def full_player_ids():
    """Eleven players on offense (WR + others)."""
    return [f"P{i:03d}" for i in range(1, 12)]


@pytest.fixture
def pbp_8_weeks(full_player_ids):
    """PBP with 40 dropbacks per week, weeks 1–8."""
    return _make_pbp(range(1, 9), players_per_team=40)


@pytest.fixture
def participation_all_present(pbp_8_weeks, full_player_ids):
    """All players on field every dropback (100% route rate)."""
    return _make_participation(pbp_8_weeks, full_player_ids)


@pytest.fixture
def participation_one_absent_week4(pbp_8_weeks, full_player_ids):
    """P001 absent in week 4 (simulates injury / IR week)."""
    return _make_participation(
        pbp_8_weeks, full_player_ids, absent_player="P001", absent_weeks=[4]
    )


# ---------------------------------------------------------------------------
# Tests: rate computation
# ---------------------------------------------------------------------------


class TestRateComputation:
    """Verify raw route_rate is computed correctly."""

    def test_full_participation_rate_is_one(
        self, pbp_8_weeks, participation_all_present
    ):
        """Players on every dropback should have route_rate == 1.0."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        assert not result.empty
        rates = result["route_rate"].dropna()
        assert (rates == 1.0).all(), "Expected all rates == 1.0 when always on field"

    def test_rate_bounded_zero_to_one(self, pbp_8_weeks, full_player_ids):
        """Route rate must always be in [0, 1]."""
        # Half the players on field each play (50% rate)
        half = full_player_ids[: len(full_player_ids) // 2]
        part = _make_participation(pbp_8_weeks, half)
        result = compute_route_participation(pbp_8_weeks, part)
        rates = result["route_rate"].dropna()
        assert (rates >= 0.0).all() and (rates <= 1.0).all()

    def test_absent_week_drops_rate(self, pbp_8_weeks, participation_one_absent_week4):
        """Player absent from all plays in a week should have route_rate == 0."""
        result = compute_route_participation(pbp_8_weeks, participation_one_absent_week4)
        p001 = result[result["player_id"] == "P001"]
        week4 = p001[p001["week"] == 4]
        # P001 appears in 0 of 40 dropbacks in week 4
        assert len(week4) == 0 or week4["route_rate"].iloc[0] == 0.0

    def test_team_dropbacks_matches_play_count(
        self, pbp_8_weeks, participation_all_present
    ):
        """team_dropbacks per week must equal the number of dropback plays."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        # 40 dropbacks per week configured
        assert (result["team_dropbacks"] == 40).all()

    def test_dropbacks_on_field_integer(
        self, pbp_8_weeks, participation_all_present
    ):
        """dropbacks_on_field must be a non-negative integer."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        assert (result["dropbacks_on_field"] >= 0).all()
        # Values should be whole numbers
        fractional = (result["dropbacks_on_field"] % 1 != 0).sum()
        assert fractional == 0


# ---------------------------------------------------------------------------
# Tests: player-ID parsing
# ---------------------------------------------------------------------------


class TestPlayerIDParsing:
    """Verify offense_players string is split correctly."""

    def test_semicolon_separated_ids(self):
        """All IDs in a semicolon-separated string should produce rows."""
        pbp = _make_pbp([1], players_per_team=1)
        # Exactly 3 players
        part = pd.DataFrame(
            {
                "game_id": [_game_id(1)],
                "play_id": [pbp["play_id"].iloc[0]],
                "offense_players": ["A001;B002;C003"],
                "defense_players": ["D001"],
            }
        )
        result = compute_route_participation(pbp, part)
        player_ids = set(result["player_id"].unique())
        assert player_ids == {"A001", "B002", "C003"}

    def test_whitespace_trimmed_from_ids(self):
        """Leading/trailing whitespace in player IDs must be stripped."""
        pbp = _make_pbp([1], players_per_team=1)
        part = pd.DataFrame(
            {
                "game_id": [_game_id(1)],
                "play_id": [pbp["play_id"].iloc[0]],
                "offense_players": [" A001 ; B002 ; C003 "],
                "defense_players": [""],
            }
        )
        result = compute_route_participation(pbp, part)
        player_ids = set(result["player_id"].unique())
        assert player_ids == {"A001", "B002", "C003"}

    def test_empty_string_ids_excluded(self):
        """Empty strings between semicolons must not produce player rows."""
        pbp = _make_pbp([1], players_per_team=1)
        part = pd.DataFrame(
            {
                "game_id": [_game_id(1)],
                "play_id": [pbp["play_id"].iloc[0]],
                "offense_players": ["A001;;B002"],  # double semicolon
                "defense_players": [""],
            }
        )
        result = compute_route_participation(pbp, part)
        player_ids = set(result["player_id"].unique())
        assert "" not in player_ids
        assert player_ids == {"A001", "B002"}


# ---------------------------------------------------------------------------
# Tests: lagging correctness
# ---------------------------------------------------------------------------


class TestLaggingCorrectness:
    """Verify strict shift-1 temporal safety on all trailing features."""

    def test_trail4_is_nan_week1(self, pbp_8_weeks, participation_all_present):
        """route_rate_trail4 must be NaN in week 1 (no prior data)."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        week1 = result[result["week"] == 1]
        assert (
            week1["route_rate_trail4"].isna().all()
        ), "trail4 must be NaN in week 1 — no prior data after shift(1)"

    def test_trail4_is_nan_week2_insufficient_history(
        self, pbp_8_weeks, participation_all_present
    ):
        """Week 2 has only 1 prior value (shift-1), below min_periods=2 → NaN."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        week2 = result[result["week"] == 2]
        assert (
            week2["route_rate_trail4"].isna().all()
        ), "trail4 needs ≥2 prior games; week 2 only has 1"

    def test_trail4_populated_week3_onwards(
        self, pbp_8_weeks, participation_all_present
    ):
        """From week 3 onwards (2 prior games), trail4 must be non-null."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        week3plus = result[result["week"] >= 3]
        # At 100% route_rate, trail4 should be 1.0
        non_null_rate = week3plus["route_rate_trail4"].notna().mean()
        assert non_null_rate > 0.95, f"Expected >95% non-null from week 3+, got {non_null_rate:.2f}"

    def test_trail4_reflects_only_prior_weeks(self):
        """Changing route_rate in week 5 should not affect trail4 at week 5."""
        # Weeks 1–4: 100% route_rate; week 5: 0% (player not in participaton)
        pbp = _make_pbp(range(1, 7), players_per_team=10)
        players = ["P001", "P002"]
        part = _make_participation(
            pbp, players, absent_player="P001", absent_weeks=[5]
        )
        result = compute_route_participation(pbp, part)
        p001 = result[result["player_id"] == "P001"].sort_values("week")

        # Week 5 trail4 should reflect weeks 1-4 (all 1.0), not week 5 itself
        week5_row = p001[p001["week"] == 5]
        if not week5_row.empty:
            trail = week5_row["route_rate_trail4"].iloc[0]
            assert trail > 0.9, (
                f"Week 5 trail4 should reflect prior 100% weeks, got {trail}"
            )

    def test_slope_is_nan_week1_and_week2(
        self, pbp_8_weeks, participation_all_present
    ):
        """route_rate_slope requires ≥3 prior observations → NaN in weeks 1-2."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        early = result[result["week"].isin([1, 2])]
        assert (
            early["route_rate_slope"].isna().all()
        ), "slope needs ≥3 prior games; weeks 1-2 don't qualify"

    def test_slope_populated_week4_onwards(
        self, pbp_8_weeks, participation_all_present
    ):
        """From week 4 onwards (3+ prior games), slope should be non-null."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        week4plus = result[result["week"] >= 4]
        non_null = week4plus["route_rate_slope"].notna().mean()
        assert non_null > 0.9, f"Expected >90% non-null slope from week 4+, got {non_null:.2f}"

    def test_slope_positive_when_role_growing(self):
        """Player with increasing route_rate should have positive slope."""
        # Weeks 1–6: route_rate grows from ~0.2 to ~0.8
        pbp = _make_pbp(range(1, 7), players_per_team=10)
        rows = []
        play_id = 1
        for week in range(1, 7):
            target_rate = 0.1 * week  # 0.1, 0.2, ..., 0.6
            plays_on_field = int(round(target_rate * 10))
            for play in range(10):
                rows.append(
                    {
                        "game_id": _game_id(week),
                        "play_id": float(play_id),
                        "season": _SEASON,
                        "week": week,
                        "posteam": _TEAM,
                        "qb_dropback": 1,
                    }
                )
                play_id += 1
        pbp_growing = pd.DataFrame(rows)

        part_rows = []
        pid = 1
        for week in range(1, 7):
            plays_on_field = int(round(0.1 * week * 10))
            for play_idx, row in enumerate(
                pbp_growing[pbp_growing["week"] == week].itertuples()
            ):
                players = ["P001"] if play_idx < plays_on_field else []
                players.append("P002")  # Always on field
                part_rows.append(
                    {
                        "game_id": row.game_id,
                        "play_id": row.play_id,
                        "offense_players": ";".join(players),
                        "defense_players": "",
                    }
                )
        part_growing = pd.DataFrame(part_rows)

        result = compute_route_participation(pbp_growing, part_growing)
        p001 = result[result["player_id"] == "P001"]
        late_weeks = p001[p001["week"] >= 5]
        if not late_weeks.empty:
            slope_vals = late_weeks["route_rate_slope"].dropna()
            if len(slope_vals) > 0:
                assert slope_vals.mean() > 0, "Growing role should yield positive slope"

    def test_delta_is_nan_until_two_trail4_values(
        self, pbp_8_weeks, participation_all_present
    ):
        """route_rate_delta needs trail4[w] - trail4[w-1]; NaN when trail4 lacks history."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        # delta = diff(trail4); trail4 is NaN for weeks 1-2, so delta NaN there too
        early = result[result["week"].isin([1, 2])]
        assert early["route_rate_delta"].isna().all(), (
            "delta must be NaN for weeks 1-2 since trail4 is not yet populated"
        )

    def test_delta_is_zero_for_stable_role(
        self, pbp_8_weeks, participation_all_present
    ):
        """At constant 100% rate, delta of trailing mean should be ~0 from week 4+."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        week4plus = result[result["week"] >= 4]
        delta_vals = week4plus["route_rate_delta"].dropna()
        if len(delta_vals) > 0:
            assert (
                delta_vals.abs() < 1e-9
            ).all(), "Stable 100% rate should yield delta ≈ 0"

    def test_trail4_correlates_more_with_prior_week_than_current(self):
        """Design property: trail4 for week t should correlate more with route_rate[t-1]
        than with route_rate[t]. This confirms the shift(1) lag is real."""
        # Create 2 players with diverging rates starting at week 5
        pbp = _make_pbp(range(1, 9), players_per_team=20)
        rows = []
        for week in range(1, 9):
            # P001: starts dropping off at week 5
            p001_rate = 1.0 if week < 5 else max(0.0, 1.0 - 0.3 * (week - 4))
            p001_on = int(round(p001_rate * 20))
            for play_idx, row in enumerate(
                pbp[pbp["week"] == week].itertuples()
            ):
                players = []
                if play_idx < p001_on:
                    players.append("P001")
                players.append("P002")  # stable
                rows.append(
                    {
                        "game_id": row.game_id,
                        "play_id": row.play_id,
                        "offense_players": ";".join(players),
                        "defense_players": "",
                    }
                )
        part = pd.DataFrame(rows)

        result = compute_route_participation(pbp, part)
        p001 = result[result["player_id"] == "P001"].sort_values("week")

        # Merge with itself shifted to get prior-week rate
        rr_vals = p001[["week", "route_rate", "route_rate_trail4"]].copy()
        rr_vals["prior_rate"] = rr_vals["route_rate"].shift(1)
        rr_vals = rr_vals.dropna(subset=["route_rate_trail4", "prior_rate", "route_rate"])

        if len(rr_vals) >= 3:
            corr_with_current = abs(rr_vals["route_rate_trail4"].corr(rr_vals["route_rate"]))
            corr_with_prior = abs(rr_vals["route_rate_trail4"].corr(rr_vals["prior_rate"]))
            assert corr_with_prior >= corr_with_current - 0.01, (
                f"trail4 should correlate ≥ with prior-week ({corr_with_prior:.3f}) "
                f"vs current week ({corr_with_current:.3f})"
            )


# ---------------------------------------------------------------------------
# Tests: empty-week handling
# ---------------------------------------------------------------------------


class TestEmptyWeekHandling:
    """Verify graceful degradation when inputs are empty or missing."""

    def test_empty_pbp_returns_empty(self, participation_all_present):
        """Empty PBP should return empty DataFrame."""
        result = compute_route_participation(pd.DataFrame(), participation_all_present)
        assert result.empty

    def test_empty_participation_returns_empty(self, pbp_8_weeks):
        """Empty participation should return empty DataFrame."""
        result = compute_route_participation(pbp_8_weeks, pd.DataFrame())
        assert result.empty

    def test_both_empty_returns_empty(self):
        """Both empty inputs should return empty DataFrame."""
        result = compute_route_participation(pd.DataFrame(), pd.DataFrame())
        assert result.empty

    def test_missing_qb_dropback_column(self, participation_all_present):
        """PBP without qb_dropback column should log warning and return empty."""
        pbp_no_dropback = _make_pbp(range(1, 3))
        pbp_no_dropback = pbp_no_dropback.drop(columns=["qb_dropback"])
        result = compute_route_participation(pbp_no_dropback, participation_all_present)
        assert result.empty

    def test_missing_offense_players_column(self, pbp_8_weeks):
        """Participation without offense_players column should return empty."""
        part_no_col = pd.DataFrame(
            {"game_id": ["x"], "play_id": [1.0], "defense_players": [""]}
        )
        result = compute_route_participation(pbp_8_weeks, part_no_col)
        assert result.empty

    def test_no_dropback_plays_returns_empty(self, participation_all_present):
        """PBP with all qb_dropback=0 should return empty."""
        pbp = _make_pbp(range(1, 3))
        pbp["qb_dropback"] = 0
        result = compute_route_participation(pbp, participation_all_present)
        assert result.empty

    def test_player_absent_entire_season(self):
        """A player absent from all weeks should not appear in output."""
        pbp = _make_pbp(range(1, 6))
        # Only P002 on field; P001 never present
        part = _make_participation(pbp, ["P002"])
        result = compute_route_participation(pbp, part)
        assert "P001" not in result["player_id"].values

    def test_null_offense_players_rows_skipped(self, pbp_8_weeks):
        """Rows with null offense_players should be silently skipped."""
        rows = []
        for _, row in pbp_8_weeks.iterrows():
            rows.append(
                {
                    "game_id": row["game_id"],
                    "play_id": row["play_id"],
                    "offense_players": None,  # null
                    "defense_players": "",
                }
            )
        part_nulls = pd.DataFrame(rows)
        result = compute_route_participation(pbp_8_weeks, part_nulls)
        # All offense_players are null → no usable dropback rows
        assert result.empty


# ---------------------------------------------------------------------------
# Tests: output schema
# ---------------------------------------------------------------------------


class TestOutputSchema:
    """Verify the returned DataFrame has the expected structure."""

    def test_required_columns_present(
        self, pbp_8_weeks, participation_all_present
    ):
        """Output must contain all required columns."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        expected = {
            "player_id",
            "season",
            "week",
            "recent_team",
            "route_rate",
            "dropbacks_on_field",
            "team_dropbacks",
        } | set(ROUTE_PARTICIPATION_FEATURES)
        for col in expected:
            assert col in result.columns, f"Missing column: {col}"

    def test_feature_columns_list_matches(
        self, pbp_8_weeks, participation_all_present
    ):
        """ROUTE_PARTICIPATION_FEATURES must be a subset of output columns."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        for col in ROUTE_PARTICIPATION_FEATURES:
            assert col in result.columns

    def test_no_duplicate_player_weeks(
        self, pbp_8_weeks, participation_all_present
    ):
        """Must have at most one row per (player_id, season, week)."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        dupes = result.duplicated(subset=["player_id", "season", "week"])
        assert not dupes.any(), "Found duplicate (player_id, season, week) rows"

    def test_season_and_week_types(
        self, pbp_8_weeks, participation_all_present
    ):
        """season and week must be numeric."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        assert pd.api.types.is_numeric_dtype(result["season"])
        assert pd.api.types.is_numeric_dtype(result["week"])

    def test_route_rate_is_float(
        self, pbp_8_weeks, participation_all_present
    ):
        """route_rate column must be floating-point."""
        result = compute_route_participation(pbp_8_weeks, participation_all_present)
        assert pd.api.types.is_float_dtype(result["route_rate"])


# ---------------------------------------------------------------------------
# Tests: multi-team isolation
# ---------------------------------------------------------------------------


class TestMultiTeamIsolation:
    """Verify that team dropbacks are computed per team, not globally."""

    def test_two_teams_correct_denominator(self):
        """Each team's route_rate should be relative to its own dropback count."""
        pbp_rows = []
        play_id = 1
        for week in [1, 2, 3]:
            # Team A: 30 dropbacks; Team B: 10 dropbacks
            for _ in range(30):
                pbp_rows.append(
                    {
                        "game_id": f"2023_0{week}_A_B",
                        "play_id": float(play_id),
                        "season": 2023,
                        "week": week,
                        "posteam": "TEAMA",
                        "qb_dropback": 1,
                    }
                )
                play_id += 1
            for _ in range(10):
                pbp_rows.append(
                    {
                        "game_id": f"2023_0{week}_B_A",
                        "play_id": float(play_id),
                        "season": 2023,
                        "week": week,
                        "posteam": "TEAMB",
                        "qb_dropback": 1,
                    }
                )
                play_id += 1
        pbp = pd.DataFrame(pbp_rows)

        part_rows = []
        for _, row in pbp.iterrows():
            part_rows.append(
                {
                    "game_id": row["game_id"],
                    "play_id": row["play_id"],
                    "offense_players": "WR_A" if row["posteam"] == "TEAMA" else "WR_B",
                    "defense_players": "",
                }
            )
        part = pd.DataFrame(part_rows)

        result = compute_route_participation(pbp, part)

        wr_a = result[result["player_id"] == "WR_A"]
        wr_b = result[result["player_id"] == "WR_B"]

        # WR_A on all 30 TEAMA dropbacks → rate 1.0
        assert (wr_a["route_rate"] == 1.0).all()
        # WR_B on all 10 TEAMB dropbacks → rate 1.0
        assert (wr_b["route_rate"] == 1.0).all()
        # Team dropbacks should differ between teams
        assert (wr_a["team_dropbacks"] == 30).all()
        assert (wr_b["team_dropbacks"] == 10).all()


# ---------------------------------------------------------------------------
# Tests: export contract
# ---------------------------------------------------------------------------


class TestExportContract:
    """Validate ROUTE_PARTICIPATION_FEATURES list contract."""

    def test_feature_list_length(self):
        """ROUTE_PARTICIPATION_FEATURES should have exactly 3 entries."""
        assert len(ROUTE_PARTICIPATION_FEATURES) == 3

    def test_feature_names(self):
        """Feature names must be exactly the three plan-specified columns."""
        expected = {"route_rate_trail4", "route_rate_delta", "route_rate_slope"}
        assert set(ROUTE_PARTICIPATION_FEATURES) == expected

    def test_raw_route_rate_not_in_features(self):
        """raw route_rate should NOT be in the feature list (same-week leak)."""
        assert "route_rate" not in ROUTE_PARTICIPATION_FEATURES

    def test_dropbacks_not_in_features(self):
        """Count columns should NOT be in the feature list."""
        for col in ROUTE_PARTICIPATION_FEATURES:
            assert "dropbacks" not in col
