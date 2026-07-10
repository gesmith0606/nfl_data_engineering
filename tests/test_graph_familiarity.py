"""Tests for the cross-team familiarity network (UC2)."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_familiarity import (
    FAMILIARITY_FEATURE_COLUMNS,
    build_expected_qb_map,
    compute_familiarity_features,
    compute_pair_history,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
#
# Story: QB_A and WR_X played together on DAL in 2023 (weeks 1-2). In 2024
# QB_A signed with NYG where WR_Y is the incumbent (cold start for WR_Y
# until they build history) and WR_X later joins NYG too in 2024 (reunion).


@pytest.fixture
def pair_stats():
    """Multi-season pair-week stats (build_qb_wr_chemistry schema)."""
    return pd.DataFrame(
        [
            # DAL 2023: QB_A -> WR_X, two games
            dict(
                passer_id="QB_A",
                receiver_id="WR_X",
                season=2023,
                week=1,
                targets=8,
                completions=6,
                epa_sum=4.0,
            ),
            dict(
                passer_id="QB_A",
                receiver_id="WR_X",
                season=2023,
                week=2,
                targets=12,
                completions=8,
                epa_sum=2.0,
            ),
            # NYG 2024: QB_A -> WR_Y from week 1 on
            dict(
                passer_id="QB_A",
                receiver_id="WR_Y",
                season=2024,
                week=1,
                targets=10,
                completions=7,
                epa_sum=1.0,
            ),
            dict(
                passer_id="QB_A",
                receiver_id="WR_Y",
                season=2024,
                week=2,
                targets=9,
                completions=5,
                epa_sum=-0.5,
            ),
            # NYG 2024: QB_A -> WR_X reunion in week 3
            dict(
                passer_id="QB_A",
                receiver_id="WR_X",
                season=2024,
                week=3,
                targets=7,
                completions=5,
                epa_sum=3.0,
            ),
        ]
    )


@pytest.fixture
def weekly_multi():
    """player_weekly for 2023 (DAL) and 2024 (NYG) with QB attempts."""
    rows = []
    # 2023: QB_A + WR_X on DAL; QB_B + WR_Y on NYG
    for week in (1, 2):
        rows += [
            dict(
                player_id="QB_A",
                recent_team="DAL",
                position="QB",
                season=2023,
                week=week,
                attempts=35,
                targets=0,
            ),
            dict(
                player_id="WR_X",
                recent_team="DAL",
                position="WR",
                season=2023,
                week=week,
                attempts=0,
                targets=10,
            ),
            dict(
                player_id="QB_B",
                recent_team="NYG",
                position="QB",
                season=2023,
                week=week,
                attempts=30,
                targets=0,
            ),
            dict(
                player_id="WR_Y",
                recent_team="NYG",
                position="WR",
                season=2023,
                week=week,
                attempts=0,
                targets=9,
            ),
        ]
    # 2024: QB_A now on NYG; WR_Y still NYG; WR_X joins NYG
    for week in (1, 2, 3):
        rows += [
            dict(
                player_id="QB_A",
                recent_team="NYG",
                position="QB",
                season=2024,
                week=week,
                attempts=33,
                targets=0,
            ),
            dict(
                player_id="WR_Y",
                recent_team="NYG",
                position="WR",
                season=2024,
                week=week,
                attempts=0,
                targets=8,
            ),
        ]
    rows.append(
        dict(
            player_id="WR_X",
            recent_team="NYG",
            position="WR",
            season=2024,
            week=3,
            attempts=0,
            targets=7,
        )
    )
    return pd.DataFrame(rows)


@pytest.fixture
def roster_2024():
    return pd.DataFrame(
        [
            dict(player_id="QB_A", team="NYG", position="QB"),
            dict(player_id="WR_Y", team="NYG", position="WR"),
            dict(player_id="WR_X", team="NYG", position="WR"),
        ]
    )


# ---------------------------------------------------------------------------
# compute_pair_history
# ---------------------------------------------------------------------------


class TestPairHistory:
    def test_cross_season_cross_team_accumulation(self, pair_stats):
        hist = compute_pair_history(pair_stats)
        # QB_A + WR_X reunion game (2024 w3): 2 prior games from DAL 2023
        reunion = hist[(hist["receiver_id"] == "WR_X") & (hist["season"] == 2024)].iloc[
            0
        ]
        assert reunion["career_games_prior"] == 2
        assert reunion["career_games_after"] == 3

    def test_epa_per_target_prior(self, pair_stats):
        hist = compute_pair_history(pair_stats)
        reunion = hist[(hist["receiver_id"] == "WR_X") & (hist["season"] == 2024)].iloc[
            0
        ]
        # Prior: (4.0 + 2.0) / (8 + 12) = 0.30
        assert reunion["career_epa_per_target_prior"] == pytest.approx(0.30)

    def test_first_game_has_zero_prior(self, pair_stats):
        hist = compute_pair_history(pair_stats)
        first = hist[
            (hist["receiver_id"] == "WR_X")
            & (hist["season"] == 2023)
            & (hist["week"] == 1)
        ].iloc[0]
        assert first["career_games_prior"] == 0
        assert np.isnan(first["career_epa_per_target_prior"])

    def test_empty_input(self):
        assert compute_pair_history(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_expected_qb_map (lag discipline)
# ---------------------------------------------------------------------------


class TestExpectedQbMap:
    def test_in_season_uses_prior_week_qb(self, weekly_multi):
        qb_map = build_expected_qb_map(weekly_multi, season=2024)
        w2 = qb_map[(qb_map["team"] == "NYG") & (qb_map["week"] == 2)].iloc[0]
        assert w2["expected_qb_id"] == "QB_A"

    def test_week1_falls_back_to_prior_season_qb_if_rostered(
        self, weekly_multi, roster_2024
    ):
        # NYG's 2023 QB was QB_B; he is NOT on the 2024 roster, so the
        # fallback must pick the rostered QB with most prior attempts: QB_A.
        qb_map = build_expected_qb_map(weekly_multi, season=2024, roster_df=roster_2024)
        w1 = qb_map[(qb_map["team"] == "NYG") & (qb_map["week"] == 1)].iloc[0]
        assert w1["expected_qb_id"] == "QB_A"

    def test_week1_prior_season_qb_kept_when_still_rostered(self, weekly_multi):
        roster = pd.DataFrame([dict(player_id="QB_B", team="NYG", position="QB")])
        qb_map = build_expected_qb_map(weekly_multi, season=2024, roster_df=roster)
        w1 = qb_map[(qb_map["team"] == "NYG") & (qb_map["week"] == 1)].iloc[0]
        assert w1["expected_qb_id"] == "QB_B"

    def test_no_same_week_leakage(self, weekly_multi):
        """Week W expected QB must not be derived from week W data."""
        # Make week 2's actual primary QB a different player (QB_A benched).
        wm = weekly_multi.copy()
        wm.loc[
            (wm["player_id"] == "QB_A") & (wm["season"] == 2024) & (wm["week"] == 2),
            "attempts",
        ] = 0
        wm = pd.concat(
            [
                wm,
                pd.DataFrame(
                    [
                        dict(
                            player_id="QB_C",
                            recent_team="NYG",
                            position="QB",
                            season=2024,
                            week=2,
                            attempts=40,
                            targets=0,
                        )
                    ]
                ),
            ],
            ignore_index=True,
        )
        qb_map = build_expected_qb_map(wm, season=2024)
        w2 = qb_map[(qb_map["team"] == "NYG") & (qb_map["week"] == 2)].iloc[0]
        # Expected QB for week 2 is still week 1's starter, not QB_C.
        assert w2["expected_qb_id"] == "QB_A"
        # And week 3 picks up the change.
        w3 = qb_map[(qb_map["team"] == "NYG") & (qb_map["week"] == 3)].iloc[0]
        assert w3["expected_qb_id"] == "QB_C"

    def test_empty_input(self):
        assert build_expected_qb_map(pd.DataFrame(), season=2024).empty


# ---------------------------------------------------------------------------
# compute_familiarity_features
# ---------------------------------------------------------------------------


class TestFamiliarityFeatures:
    def _feats(self, pair_stats, weekly_multi, roster_2024):
        return compute_familiarity_features(
            qb_wr_df=pair_stats,
            player_weekly_multi_df=weekly_multi,
            season=2024,
            roster_df=roster_2024,
        )

    def test_output_schema(self, pair_stats, weekly_multi, roster_2024):
        feats = self._feats(pair_stats, weekly_multi, roster_2024)
        for col in FAMILIARITY_FEATURE_COLUMNS:
            assert col in feats.columns
        assert (feats["season"] == 2024).all()

    def test_cold_start_flagged(self, pair_stats, weekly_multi, roster_2024):
        feats = self._feats(pair_stats, weekly_multi, roster_2024)
        # WR_Y week 1 2024: expected QB is QB_A (new signing) with zero
        # prior games together -> cold start.
        w1 = feats[(feats["player_id"] == "WR_Y") & (feats["week"] == 1)].iloc[0]
        assert w1["qb_is_new"] == 1
        assert w1["qb_familiarity_games"] == 0

    def test_familiarity_accumulates(self, pair_stats, weekly_multi, roster_2024):
        feats = self._feats(pair_stats, weekly_multi, roster_2024)
        # WR_Y week 3: two games with QB_A now behind them.
        w3 = feats[(feats["player_id"] == "WR_Y") & (feats["week"] == 3)].iloc[0]
        assert w3["qb_is_new"] == 0
        assert w3["qb_familiarity_games"] == 2

    def test_reunion_carries_cross_team_history(
        self, pair_stats, weekly_multi, roster_2024
    ):
        feats = self._feats(pair_stats, weekly_multi, roster_2024)
        # WR_X week 3 2024 (first NYG game): 2 games with QB_A from DAL 2023.
        reunion = feats[(feats["player_id"] == "WR_X") & (feats["week"] == 3)].iloc[0]
        assert reunion["qb_is_new"] == 0
        assert reunion["qb_familiarity_games"] == 2
        # Career EPA/target through 2023: 6.0 / 20 = 0.30
        assert reunion["reunion_epa_prior"] == pytest.approx(0.30)

    def test_continuity_features_present(self, pair_stats, weekly_multi, roster_2024):
        feats = self._feats(pair_stats, weekly_multi, roster_2024)
        nyg = feats[feats["player_id"] == "WR_Y"].iloc[0]
        # NYG 2023 targets all went to WR_Y (still rostered) -> continuity 1.0
        assert nyg["offense_continuity_pct"] == pytest.approx(1.0)
        # QB_A's 2023 receivers (WR_X on DAL) — WR_X IS on NYG's 2024
        # roster, so weapons_new_pct = 0.0
        assert nyg["weapons_new_pct"] == pytest.approx(0.0)

    def test_empty_inputs(self):
        feats = compute_familiarity_features(
            qb_wr_df=pd.DataFrame(),
            player_weekly_multi_df=pd.DataFrame(),
            season=2024,
        )
        assert feats.empty
        for col in FAMILIARITY_FEATURE_COLUMNS:
            assert col in feats.columns

    def test_one_row_per_player_week(self, pair_stats, weekly_multi, roster_2024):
        feats = self._feats(pair_stats, weekly_multi, roster_2024)
        assert not feats.duplicated(subset=["player_id", "season", "week"]).any()


# ---------------------------------------------------------------------------
# Post-review regression coverage
# ---------------------------------------------------------------------------


class TestReviewRegressions:
    def test_history_scoped_to_current_expected_qb(self):
        """A receiver's history with a DIFFERENT past QB must not leak in.

        R played 10 games with Q_OLD (chronologically later) and 1 game
        with Q_NEW. Current expected QB is Q_NEW — familiarity must be 1
        game at Q_NEW's EPA, not Q_OLD's record.
        """
        pairs = pd.DataFrame(
            [
                dict(
                    passer_id="Q_NEW",
                    receiver_id="R",
                    season=2022,
                    week=1,
                    targets=5,
                    epa_sum=1.0,
                )
            ]
            + [
                dict(
                    passer_id="Q_OLD",
                    receiver_id="R",
                    season=2023,
                    week=w,
                    targets=8,
                    epa_sum=8.0,
                )
                for w in range(1, 11)
            ]
        )
        pw = pd.DataFrame(
            [
                dict(
                    player_id="Q_NEW",
                    recent_team="KC",
                    position="QB",
                    season=2024,
                    week=1,
                    attempts=30,
                    targets=0,
                ),
                dict(
                    player_id="Q_NEW",
                    recent_team="KC",
                    position="QB",
                    season=2024,
                    week=2,
                    attempts=30,
                    targets=0,
                ),
                dict(
                    player_id="R",
                    recent_team="KC",
                    position="WR",
                    season=2024,
                    week=2,
                    attempts=0,
                    targets=8,
                ),
            ]
        )
        feats = compute_familiarity_features(pairs, pw, 2024, None)
        r = feats[(feats["player_id"] == "R") & (feats["week"] == 2)].iloc[0]
        assert r["qb_familiarity_games"] == 1
        assert r["reunion_epa_prior"] == pytest.approx(0.2)

    def test_week1_qb_uses_per_team_earliest_week(self):
        """A team whose first data week is later than the league minimum
        must still resolve its own first-week expected QB (global-min bug)."""
        pw = pd.DataFrame(
            [
                # KC has week 1; DEN's first data week is 2.
                dict(
                    player_id="QB_KC",
                    recent_team="KC",
                    position="QB",
                    season=2023,
                    week=18,
                    attempts=30,
                    targets=0,
                ),
                dict(
                    player_id="QB_DEN",
                    recent_team="DEN",
                    position="QB",
                    season=2023,
                    week=18,
                    attempts=30,
                    targets=0,
                ),
                dict(
                    player_id="QB_KC",
                    recent_team="KC",
                    position="QB",
                    season=2024,
                    week=1,
                    attempts=30,
                    targets=0,
                ),
                dict(
                    player_id="QB_DEN",
                    recent_team="DEN",
                    position="QB",
                    season=2024,
                    week=2,
                    attempts=30,
                    targets=0,
                ),
                dict(
                    player_id="WR_DEN",
                    recent_team="DEN",
                    position="WR",
                    season=2024,
                    week=2,
                    attempts=0,
                    targets=8,
                ),
            ]
        )
        qb_map = build_expected_qb_map(pw, season=2024)
        den_first = qb_map[(qb_map["team"] == "DEN")].sort_values("week").iloc[0]
        # DEN's first observed week falls back to the 2023 QB, not NaN.
        assert den_first["expected_qb_id"] == "QB_DEN"


# ---------------------------------------------------------------------------
# Integration smoke test on real local data
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRealDataSmoke:
    def test_build_2024_features(self):
        import glob

        from graph_familiarity import build_familiarity_data
        from graph_qb_wr_chemistry import build_qb_wr_chemistry

        base = os.path.join(os.path.dirname(__file__), "..", "data", "bronze")
        pbp_files = sorted(
            glob.glob(os.path.join(base, "pbp", "season=2023", "*.parquet"))
        )
        pbp_files += sorted(
            glob.glob(os.path.join(base, "pbp", "season=2024", "*.parquet"))
        )
        pw_files = sorted(
            glob.glob(os.path.join(base, "players/weekly", "season=2023", "*.parquet"))
        )
        pw_files += sorted(
            glob.glob(os.path.join(base, "players/weekly", "season=2024", "*.parquet"))
        )
        if not pbp_files or not pw_files:
            pytest.skip("Local Bronze PBP/weekly for 2023-2024 not available")

        pbp = pd.concat([pd.read_parquet(f) for f in pbp_files], ignore_index=True)
        pw = pd.concat([pd.read_parquet(f) for f in pw_files], ignore_index=True)

        pairs = build_qb_wr_chemistry(pbp)
        feats = build_familiarity_data(2024, pairs, pw)
        assert not feats.empty
        assert feats["qb_is_new"].sum() > 0  # some cold starts exist
        assert feats["qb_familiarity_games"].max() > 10  # long-running pairs
        # Week 1 must have expected QBs resolved for most teams
        w1 = feats[feats["week"] == 1]
        assert len(w1) > 50
