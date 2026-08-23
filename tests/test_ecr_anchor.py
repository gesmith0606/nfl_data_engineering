"""
Unit tests for the WR weekly-ECR ordinal anchor lever
(.planning/WR_ECR_ORDINAL_GATE.md).
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from ecr_anchor import (  # noqa: E402
    EPSILON,
    ECR_SCORING_PREFERENCE,
    NUDGE,
    WR_POSITION,
    _load_ecr_season,
    apply_ecr_anchor,
    apply_ecr_anchor_blend,
    apply_ecr_anchor_near_tie,
    build_ecr_lookup,
    compute_team_kickoff_dates,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _schedule_row(season, week, home, away, gameday, game_type="REG"):
    return {
        "season": season,
        "week": week,
        "game_type": game_type,
        "gameday": gameday,
        "home_team": home,
        "away_team": away,
    }


@pytest.fixture
def schedules_df():
    # Week 5, 2023: TeamA @ TeamB plays THURSDAY (2023-10-05); TeamC @ TeamD
    # plays SUNDAY (2023-10-08). ECR scrape_date for week 5 is Friday
    # 2023-10-06 (matches real archive behavior).
    return pd.DataFrame(
        [
            _schedule_row(2023, 5, "TB", "TA", "2023-10-05"),
            _schedule_row(2023, 5, "TD", "TC", "2023-10-08"),
        ]
    )


def _wr_row(player_id, team, points, position="WR", season=2023, week=5):
    return {
        "player_id": player_id,
        "season": season,
        "week": week,
        "position": position,
        "recent_team": team,
        "projected_points": points,
    }


def _write_ecr_parquet(tmp_path, season, rows):
    silver_dir = tmp_path / "fp_ecr"
    season_dir = silver_dir / f"season={season}"
    season_dir.mkdir(parents=True)
    df = pd.DataFrame(rows)
    df.to_parquet(season_dir / f"fp_ecr_{season}.parquet", index=False)
    return str(silver_dir)


def _ecr_row(gsis_id, week, pos_rank, scrape_date="2023-10-06", position="WR", scoring="ppr"):
    return {
        "season": 2023,
        "week": week,
        "scrape_date": scrape_date,
        "scoring": scoring,
        "position": position,
        "gsis_id": gsis_id,
        "pos_rank": pos_rank,
    }


# ---------------------------------------------------------------------------
# compute_team_kickoff_dates
# ---------------------------------------------------------------------------


class TestComputeTeamKickoffDates:
    def test_one_row_per_week_team(self, schedules_df):
        out = compute_team_kickoff_dates(schedules_df, 2023)
        assert set(out["team"]) == {"TB", "TA", "TD", "TC"}
        assert len(out) == 4

    def test_empty_on_missing_columns(self):
        out = compute_team_kickoff_dates(pd.DataFrame({"a": [1]}), 2023)
        assert out.empty
        assert list(out.columns) == ["week", "team", "kickoff_date"]

    def test_filters_to_requested_season(self, schedules_df):
        out = compute_team_kickoff_dates(schedules_df, 2099)
        assert out.empty


# ---------------------------------------------------------------------------
# build_ecr_lookup -- Thursday-exclusion + coverage stats
# ---------------------------------------------------------------------------


class TestBuildEcrLookup:
    def test_thursday_game_excluded_sunday_included(self, tmp_path, schedules_df):
        proj = pd.DataFrame(
            [
                _wr_row("P_THU", "TA", 12.0),  # Thursday team -> excluded
                _wr_row("P_SUN", "TC", 10.0),  # Sunday team -> included
            ]
        )
        silver_dir = _write_ecr_parquet(
            tmp_path,
            2023,
            [_ecr_row("P_THU", 5, 3), _ecr_row("P_SUN", 5, 7)],
        )
        lookup, stats = build_ecr_lookup(proj, 2023, 5, schedules_df, silver_dir=silver_dir)

        assert stats["n_ecr_wr_rows"] == 2
        assert stats["n_team_resolved"] == 2
        assert stats["n_thursday_excluded"] == 1
        assert stats["n_final_matched"] == 1
        assert stats["n_proj_wr_rows"] == 2
        assert list(lookup["player_id"]) == ["P_SUN"]
        assert lookup.set_index("player_id").loc["P_SUN", "ecr_pos_rank"] == 7

    def test_no_match_when_player_not_on_a_scheduled_team(self, tmp_path, schedules_df):
        proj = pd.DataFrame([_wr_row("P_UNKNOWN", "ZZ", 9.0)])
        silver_dir = _write_ecr_parquet(tmp_path, 2023, [_ecr_row("P_UNKNOWN", 5, 1)])
        lookup, stats = build_ecr_lookup(proj, 2023, 5, schedules_df, silver_dir=silver_dir)
        # ZZ has no kickoff date at all -- treated as unresolved, not leak-free.
        assert stats["n_thursday_excluded"] == 1
        assert lookup.empty

    def test_no_ecr_data_for_season_is_empty_not_error(self, schedules_df):
        proj = pd.DataFrame([_wr_row("P1", "TC", 9.0)])
        lookup, stats = build_ecr_lookup(
            proj, 2023, 5, schedules_df, silver_dir="/nonexistent/path"
        )
        assert lookup.empty
        assert stats["n_ecr_wr_rows"] == 0

    def test_empty_proj_df(self, schedules_df):
        lookup, stats = build_ecr_lookup(pd.DataFrame(), 2023, 5, schedules_df)
        assert lookup.empty
        assert stats["n_proj_wr_rows"] == 0

    def test_non_wr_rows_excluded_from_coverage_denominator(self, tmp_path, schedules_df):
        proj = pd.DataFrame(
            [
                _wr_row("P_WR", "TC", 10.0, position="WR"),
                _wr_row("P_RB", "TC", 15.0, position="RB"),
            ]
        )
        silver_dir = _write_ecr_parquet(tmp_path, 2023, [_ecr_row("P_WR", 5, 1)])
        _lookup, stats = build_ecr_lookup(proj, 2023, 5, schedules_df, silver_dir=silver_dir)
        assert stats["n_proj_wr_rows"] == 1


# ---------------------------------------------------------------------------
# apply_ecr_anchor_blend (mechanism a)
# ---------------------------------------------------------------------------


class TestApplyEcrAnchorBlend:
    def _pool(self):
        # our order (desc points): A(20) > B(18) > C(16) > D(14)
        # ecr_pos_rank: A worst(4), B best(1), C 3rd, D 2nd -- full inversion
        return pd.DataFrame(
            [
                _wr_row("A", "TC", 20.0),
                _wr_row("B", "TC", 18.0),
                _wr_row("C", "TC", 16.0),
                _wr_row("D", "TC", 14.0),
            ]
        )

    def _lookup(self):
        return pd.DataFrame(
            {"player_id": ["A", "B", "C", "D"], "ecr_pos_rank": [4, 1, 3, 2]}
        )

    def test_weight_zero_is_noop(self):
        proj = self._pool()
        out = apply_ecr_anchor_blend(proj, self._lookup(), weight=0.0)
        pd.testing.assert_series_equal(
            out["projected_points"], proj["projected_points"], check_names=True
        )
        assert not out["ecr_anchor_flag"].any()

    def test_weight_one_fully_realizes_ecr_order(self):
        proj = self._pool()
        out = apply_ecr_anchor_blend(proj, self._lookup(), weight=1.0)
        # blended_rank == ecr_pos_rank exactly -> target order B > D > C > A
        # original values sorted desc [20,18,16,14] assigned in that order.
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["B"] == 20.0
        assert ordered["D"] == 18.0
        assert ordered["C"] == 16.0
        assert ordered["A"] == 14.0
        assert out["ecr_anchor_flag"].sum() == 4

    def test_value_multiset_conserved(self):
        """Reassignment permutes existing values -- never invents new ones."""
        proj = self._pool()
        out = apply_ecr_anchor_blend(proj, self._lookup(), weight=0.5)
        before = sorted(proj["projected_points"].tolist())
        after = sorted(out["projected_points"].tolist())
        assert before == after

    def test_unmatched_wr_passthrough(self):
        proj = self._pool()
        lookup = pd.DataFrame({"player_id": ["A", "B"], "ecr_pos_rank": [2, 1]})
        out = apply_ecr_anchor_blend(proj, lookup, weight=1.0)
        # C, D never matched -> untouched.
        assert out.set_index("player_id").loc["C", "projected_points"] == 16.0
        assert out.set_index("player_id").loc["D", "projected_points"] == 14.0
        assert not out.set_index("player_id").loc["C", "ecr_anchor_flag"]

    def test_non_wr_rows_never_touched(self):
        proj = pd.concat(
            [self._pool(), pd.DataFrame([_wr_row("RB1", "TC", 12.0, position="RB")])],
            ignore_index=True,
        )
        lookup = pd.concat(
            [self._lookup(), pd.DataFrame({"player_id": ["RB1"], "ecr_pos_rank": [1]})],
            ignore_index=True,
        )
        out = apply_ecr_anchor_blend(proj, lookup, weight=1.0)
        assert out.set_index("player_id").loc["RB1", "projected_points"] == 12.0
        assert not out.set_index("player_id").loc["RB1", "ecr_anchor_flag"]

    def test_empty_lookup_is_noop(self):
        proj = self._pool()
        out = apply_ecr_anchor_blend(proj, pd.DataFrame(columns=["player_id", "ecr_pos_rank"]), weight=0.5)
        pd.testing.assert_frame_equal(
            out.drop(columns=["ecr_anchor_flag"]), proj, check_like=True
        )


# ---------------------------------------------------------------------------
# apply_ecr_anchor_near_tie (mechanism b)
# ---------------------------------------------------------------------------


class TestApplyEcrAnchorNearTie:
    def test_nudges_disagreeing_near_tie_pair(self):
        # gap 1.0 <= EPSILON; ecr says LOW is actually better (lower rank).
        proj = pd.DataFrame(
            [_wr_row("HI", "TC", 20.0), _wr_row("LOW", "TC", 19.0)]
        )
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "ecr_pos_rank": [5, 1]})
        out = apply_ecr_anchor_near_tie(proj, lookup)
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["HI"] == 20.0 - NUDGE
        assert ordered["LOW"] == 19.0 + NUDGE
        assert out["ecr_anchor_flag"].all()

    def test_agreeing_pair_untouched(self):
        proj = pd.DataFrame(
            [_wr_row("HI", "TC", 20.0), _wr_row("LOW", "TC", 19.0)]
        )
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "ecr_pos_rank": [1, 5]})
        out = apply_ecr_anchor_near_tie(proj, lookup)
        ordered = out.set_index("player_id")["projected_points"]
        assert ordered["HI"] == 20.0
        assert ordered["LOW"] == 19.0
        assert not out["ecr_anchor_flag"].any()

    def test_gap_beyond_epsilon_untouched(self):
        proj = pd.DataFrame(
            [_wr_row("HI", "TC", 20.0), _wr_row("LOW", "TC", 20.0 - EPSILON - 1.0)]
        )
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "ecr_pos_rank": [5, 1]})
        out = apply_ecr_anchor_near_tie(proj, lookup)
        assert not out["ecr_anchor_flag"].any()

    def test_missing_signal_one_side_no_fire(self):
        proj = pd.DataFrame(
            [_wr_row("HI", "TC", 20.0), _wr_row("LOW", "TC", 19.0)]
        )
        lookup = pd.DataFrame({"player_id": ["HI"], "ecr_pos_rank": [5]})
        out = apply_ecr_anchor_near_tie(proj, lookup)
        assert not out["ecr_anchor_flag"].any()

    def test_non_negative_clip(self):
        proj = pd.DataFrame(
            [_wr_row("HI", "TC", 0.3), _wr_row("LOW", "TC", 0.1)]
        )
        lookup = pd.DataFrame({"player_id": ["HI", "LOW"], "ecr_pos_rank": [5, 1]})
        out = apply_ecr_anchor_near_tie(proj, lookup)
        assert (out["projected_points"] >= 0).all()


# ---------------------------------------------------------------------------
# apply_ecr_anchor dispatcher
# ---------------------------------------------------------------------------


class TestApplyEcrAnchorDispatch:
    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            apply_ecr_anchor(pd.DataFrame(), pd.DataFrame(), mode="bogus")

    def test_blend_requires_weight_defaults_zero_noop(self):
        proj = pd.DataFrame([_wr_row("A", "TC", 20.0)])
        lookup = pd.DataFrame({"player_id": ["A"], "ecr_pos_rank": [1]})
        out = apply_ecr_anchor(proj, lookup, mode="blend")  # no weight -> 0.0
        assert out["projected_points"].iloc[0] == 20.0


# ---------------------------------------------------------------------------
# Shuffle-collapse sanity check (leak/signal-validity test)
# ---------------------------------------------------------------------------


class TestShuffleCollapse:
    def test_true_signal_fixes_pairs_shuffled_signal_does_not(self):
        """6 near-tie pairs, all misordered vs our own projection. A
        perfectly-truth-correlated ECR lookup should fix (nudge toward
        correct) every pair; a shuffled (decorrelated) lookup, applied to
        the same population, should fix far fewer -- the shuffle-collapse
        property the pre-registered gate's leak/sanity test depends on.
        """
        rows = []
        for i in range(6):
            hi_id, lo_id = f"HI{i}", f"LO{i}"
            # our order: HI > LO by 0.5 (near-tie), but LO is the true
            # better player in every pair (ecr correctly favors LO).
            rows.append(_wr_row(hi_id, "TC", 10.0 + i, week=5))
            rows.append(_wr_row(lo_id, "TC", 10.0 + i - 0.5, week=5))
        proj = pd.DataFrame(rows)

        true_lookup_rows = []
        for i in range(6):
            true_lookup_rows.append({"player_id": f"HI{i}", "ecr_pos_rank": 2})
            true_lookup_rows.append({"player_id": f"LO{i}", "ecr_pos_rank": 1})
        true_lookup = pd.DataFrame(true_lookup_rows)

        out_true = apply_ecr_anchor_near_tie(proj, true_lookup)
        n_fired_true = int(out_true["ecr_anchor_flag"].sum())
        assert n_fired_true == 12  # every pair fires (all 6 pairs, both members)

        # Shuffle: derange the (player_id -> ecr_pos_rank) assignment with
        # a fixed seed so ecr_pos_rank no longer tracks which member of
        # each pair is "really" better.
        rng = np.random.default_rng(42)
        shuffled_ranks = true_lookup["ecr_pos_rank"].to_numpy().copy()
        rng.shuffle(shuffled_ranks)
        shuffled_lookup = true_lookup.copy()
        shuffled_lookup["ecr_pos_rank"] = shuffled_ranks

        out_shuffled = apply_ecr_anchor_near_tie(proj, shuffled_lookup)
        n_fired_shuffled = int(out_shuffled["ecr_anchor_flag"].sum())

        # The true signal fires on strictly more (player, pair)
        # instances than the decorrelated shuffle -- the effect collapses
        # once the signal is randomized, rather than persisting at the
        # same magnitude regardless of what's being nudged.
        assert n_fired_shuffled < n_fired_true


# ---------------------------------------------------------------------------
# Scoring-preference generalization (ECR_ANCHOR_FORWARD_GATE.md #0.2):
# ECR_SCORING="ppr" hardcode -> ECR_SCORING_PREFERENCE=("ppr", "half_ppr").
# Historical (season<=2024, 100% ppr) reads MUST stay byte-identical; the
# live 2026+ bridge (100% half_ppr) must now read nonzero rows.
# ---------------------------------------------------------------------------

_HISTORICAL_2024_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "silver", "fp_ecr", "season=2024", "fp_ecr_2024.parquet"
)
_HISTORICAL_2024_SILVER_DIR = os.path.dirname(os.path.dirname(_HISTORICAL_2024_FILE))


class TestScoringPreferenceRegression:
    @pytest.mark.skipif(
        not os.path.exists(_HISTORICAL_2024_FILE),
        reason="Local-only historical FP-ECR archive not present in this checkout",
    )
    def test_load_ecr_season_byte_identical_to_old_hardcoded_ppr_filter(self):
        raw = pd.read_parquet(_HISTORICAL_2024_FILE)
        old_behavior = raw[(raw["position"] == WR_POSITION) & (raw["scoring"] == "ppr")].copy()

        new_behavior = _load_ecr_season(2024, silver_dir=_HISTORICAL_2024_SILVER_DIR)

        pd.testing.assert_frame_equal(
            old_behavior.reset_index(drop=True), new_behavior.reset_index(drop=True)
        )

    @pytest.mark.skipif(
        not os.path.exists(_HISTORICAL_2024_FILE),
        reason="Local-only historical FP-ECR archive not present in this checkout",
    )
    def test_build_ecr_lookup_byte_identical_for_2024(self, schedules_df):
        # schedules_df fixture is season=2023; build_ecr_lookup for a season
        # with no matching schedule rows returns an empty (but still
        # correctly-shaped) lookup either way -- what matters here is that
        # the OLD single-value filter and the NEW preference filter feed
        # build_ecr_lookup identical upstream rows, which the direct
        # _load_ecr_season comparison above already proves. This test
        # additionally proves build_ecr_lookup's own dispatch doesn't
        # regress the empty-schedule path for a season it has no schedule
        # fixture for.
        proj = pd.DataFrame([_wr_row("ANY", "ZZ", 9.0, season=2024, week=1)])
        lookup_old, stats_old = build_ecr_lookup(
            proj, 2024, 1, schedules_df, silver_dir=_HISTORICAL_2024_SILVER_DIR,
            scoring_preference=("ppr",),
        )
        lookup_new, stats_new = build_ecr_lookup(
            proj, 2024, 1, schedules_df, silver_dir=_HISTORICAL_2024_SILVER_DIR,
        )
        pd.testing.assert_frame_equal(lookup_old, lookup_new)
        assert stats_old == stats_new

    def test_live_half_ppr_season_now_reads_nonzero_rows(self, tmp_path, schedules_df):
        # Regression for the bug itself: a season whose Silver file is
        # honestly labeled scoring="half_ppr" (the live bridge's output)
        # used to be read as ZERO rows by the old hardcoded ECR_SCORING="ppr"
        # filter. The default ECR_SCORING_PREFERENCE must now read it.
        silver_dir = _write_ecr_parquet(
            tmp_path,
            2023,
            [_ecr_row("P_SUN", 5, 7, scoring="half_ppr")],
        )
        proj = pd.DataFrame([_wr_row("P_SUN", "TC", 10.0)])
        lookup, stats = build_ecr_lookup(proj, 2023, 5, schedules_df, silver_dir=silver_dir)
        assert stats["n_ecr_wr_rows"] == 1
        assert not lookup.empty
        assert lookup.set_index("player_id").loc["P_SUN", "ecr_pos_rank"] == 7

    def test_old_hardcoded_ppr_only_would_have_missed_half_ppr_row(self, tmp_path, schedules_df):
        """Documents exactly the bug being fixed: filtering scoring=="ppr"
        only (the pre-fix behavior) reads zero rows from a half_ppr-labeled
        season, while the new default preference list reads it."""
        silver_dir = _write_ecr_parquet(
            tmp_path, 2023, [_ecr_row("P_SUN", 5, 7, scoring="half_ppr")]
        )
        proj = pd.DataFrame([_wr_row("P_SUN", "TC", 10.0)])
        lookup_old_style, _ = build_ecr_lookup(
            proj, 2023, 5, schedules_df, silver_dir=silver_dir, scoring_preference=("ppr",)
        )
        assert lookup_old_style.empty

    def test_default_preference_is_ppr_then_half_ppr(self):
        assert ECR_SCORING_PREFERENCE == ("ppr", "half_ppr")
