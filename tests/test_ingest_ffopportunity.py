"""
Tests for scripts/ingest_ffopportunity.py

Covers:
  - Aggregation math: passing/receiving/rushing yards + fantasy points sum
    correctly across multiple plays for the same player-week
  - gsis id passthrough: player_id values are not mangled by the aggregation
  - A player who both rushes and catches passes in the same week gets one
    merged row with contributions from both roles
  - Empty-season fail-loud: build_player_week_features raises rather than
    silently returning an empty DataFrame
  - Feature column contract: build_player_week_features always returns
    exactly FEATURE_COLUMNS, in order

Fixtures replicate the real ep_pbp_pass/ep_pbp_rush schema gotcha where
0/1 flag columns (complete_pass, pass_touchdown, interception,
rush_touchdown) are stored as `category` dtype with string labels
("0"/"1"), not plain ints/bools.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.ingest_ffopportunity import (  # noqa: E402
    FEATURE_COLUMNS,
    aggregate_passing,
    aggregate_receiving,
    aggregate_rushing,
    build_player_week_features,
)


def _cat(values):
    """Mimic ffopportunity's category-dtype string-flag columns."""
    return pd.Categorical([str(int(v)) for v in values], categories=["0", "1"])


def make_pass_df(rows):
    """Build a minimal ep_pbp_pass-shaped DataFrame from row dicts.

    Each row dict may set: passer_player_id, receiver_player_id, season,
    week, posteam, passer_position, receiver_position, complete_pass (0/1),
    pass_touchdown (0/1), interception (0/1), air_yards,
    yards_after_catch_exp, receiving_yards, pass_completion_exp,
    pass_touchdown_exp.
    """
    df = pd.DataFrame(rows)
    df["complete_pass"] = _cat(df["complete_pass"])
    df["pass_touchdown"] = _cat(df["pass_touchdown"])
    df["interception"] = _cat(df.get("interception", [0] * len(df)))
    df["pass_attempt"] = 1.0
    return df


def make_rush_df(rows):
    """Build a minimal ep_pbp_rush-shaped DataFrame from row dicts."""
    df = pd.DataFrame(rows)
    df["rush_touchdown"] = _cat(df["rush_touchdown"])
    df["rush_attempt"] = 1.0
    return df


def empty_pass_df():
    """A correctly-schema'd, zero-row ep_pbp_pass DataFrame.

    Real Bronze parquet always carries the full schema even for a 0-row
    file — this is distinct from a bare pd.DataFrame() with no columns at
    all, which represents "no data was provided" rather than "a season
    with zero pass attempts".
    """
    return pd.DataFrame(
        columns=[
            "passer_player_id",
            "receiver_player_id",
            "season",
            "week",
            "posteam",
            "passer_position",
            "receiver_position",
            "complete_pass",
            "pass_touchdown",
            "interception",
            "air_yards",
            "yards_after_catch_exp",
            "receiving_yards",
            "pass_completion_exp",
            "pass_touchdown_exp",
            "pass_attempt",
        ]
    )


# ---------------------------------------------------------------------------
# Aggregation math
# ---------------------------------------------------------------------------


def test_aggregate_passing_sums_across_plays():
    pass_df = make_pass_df(
        [
            {
                "passer_player_id": "00-0011111",
                "receiver_player_id": "00-0022222",
                "season": 2023,
                "week": 4,
                "posteam": "SF",
                "passer_position": "QB",
                "receiver_position": "WR",
                "complete_pass": 1,
                "pass_touchdown": 0,
                "interception": 0,
                "air_yards": 10.0,
                "yards_after_catch_exp": 2.0,
                "receiving_yards": 15.0,
                "pass_completion_exp": 0.6,
                "pass_touchdown_exp": 0.05,
            },
            {
                "passer_player_id": "00-0011111",
                "receiver_player_id": "00-0033333",
                "season": 2023,
                "week": 4,
                "posteam": "SF",
                "passer_position": "QB",
                "receiver_position": "TE",
                "complete_pass": 0,
                "pass_touchdown": 0,
                "interception": 1,
                "air_yards": 20.0,
                "yards_after_catch_exp": 3.0,
                "receiving_yards": None,
                "pass_completion_exp": 0.4,
                "pass_touchdown_exp": 0.10,
            },
        ]
    )
    out = aggregate_passing(pass_df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["player_id"] == "00-0011111"
    assert row["pass_attempts"] == 2
    assert row["completions"] == 1
    assert row["interceptions"] == 1
    assert row["pass_yards"] == pytest.approx(15.0)
    # exp_pass_yards = 0.6*(10+2) + 0.4*(20+3) = 7.2 + 9.2 = 16.4
    assert row["exp_pass_yards"] == pytest.approx(16.4)
    assert row["exp_pass_tds"] == pytest.approx(0.15)
    assert row["team"] == "SF"
    assert row["position"] == "QB"


def test_aggregate_receiving_excludes_null_receiver():
    pass_df = make_pass_df(
        [
            {
                "passer_player_id": "00-0011111",
                "receiver_player_id": "00-0022222",
                "season": 2023,
                "week": 4,
                "posteam": "SF",
                "passer_position": "QB",
                "receiver_position": "WR",
                "complete_pass": 1,
                "pass_touchdown": 1,
                "interception": 0,
                "air_yards": 5.0,
                "yards_after_catch_exp": 1.0,
                "receiving_yards": 6.0,
                "pass_completion_exp": 0.8,
                "pass_touchdown_exp": 0.3,
            },
            {
                # Spike / no target — receiver_player_id null
                "passer_player_id": "00-0011111",
                "receiver_player_id": None,
                "season": 2023,
                "week": 4,
                "posteam": "SF",
                "passer_position": "QB",
                "receiver_position": None,
                "complete_pass": 0,
                "pass_touchdown": 0,
                "interception": 0,
                "air_yards": 0.0,
                "yards_after_catch_exp": 0.0,
                "receiving_yards": None,
                "pass_completion_exp": 0.0,
                "pass_touchdown_exp": 0.0,
            },
        ]
    )
    out = aggregate_receiving(pass_df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["player_id"] == "00-0022222"
    assert row["targets"] == 1
    assert row["receptions"] == 1
    assert row["rec_yards"] == pytest.approx(6.0)
    assert row["rec_tds"] == 1


def test_aggregate_rushing_sums_across_plays():
    rush_df = make_rush_df(
        [
            {
                "rusher_player_id": "00-0044444",
                "season": 2023,
                "week": 8,
                "posteam": "SF",
                "position": "RB",
                "rush_touchdown": 0,
                "rushing_yards": 4.0,
                "rushing_yards_exp": 3.5,
                "rushing_td_exp": 0.02,
            },
            {
                "rusher_player_id": "00-0044444",
                "season": 2023,
                "week": 8,
                "posteam": "SF",
                "position": "RB",
                "rush_touchdown": 1,
                "rushing_yards": 8.0,
                "rushing_yards_exp": 4.1,
                "rushing_td_exp": 0.06,
            },
        ]
    )
    out = aggregate_rushing(rush_df)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["player_id"] == "00-0044444"
    assert row["carries"] == 2
    assert row["rush_yards"] == pytest.approx(12.0)
    assert row["rush_tds"] == 1
    assert row["exp_rush_yards"] == pytest.approx(7.6)
    assert row["exp_rush_tds"] == pytest.approx(0.08)


# ---------------------------------------------------------------------------
# id passthrough + merged dual-role player
# ---------------------------------------------------------------------------


def test_id_passthrough_and_dual_role_merge():
    """An RB (rusher + receiver in the same week) gets one merged row; gsis
    ids flow through unchanged."""
    gsis_id = "00-0033280"  # real Christian McCaffrey gsis id, used as a realistic fixture value
    pass_df = make_pass_df(
        [
            {
                "passer_player_id": "00-0099999",
                "receiver_player_id": gsis_id,
                "season": 2023,
                "week": 8,
                "posteam": "SF",
                "passer_position": "QB",
                "receiver_position": "RB",
                "complete_pass": 1,
                "pass_touchdown": 0,
                "interception": 0,
                "air_yards": 2.0,
                "yards_after_catch_exp": 4.0,
                "receiving_yards": 9.0,
                "pass_completion_exp": 0.75,
                "pass_touchdown_exp": 0.01,
            },
        ]
    )
    rush_df = make_rush_df(
        [
            {
                "rusher_player_id": gsis_id,
                "season": 2023,
                "week": 8,
                "posteam": "SF",
                "position": "RB",
                "rush_touchdown": 0,
                "rushing_yards": 12.0,
                "rushing_yards_exp": 5.0,
                "rushing_td_exp": 0.03,
            },
        ]
    )
    feats = build_player_week_features(pass_df, rush_df)

    cmc_rows = feats[feats["player_id"] == gsis_id]
    assert len(cmc_rows) == 1
    row = cmc_rows.iloc[0]
    assert row["player_id"] == gsis_id  # unchanged, not truncated/reformatted
    assert row["carries"] == 1
    assert row["rush_yards"] == pytest.approx(12.0)
    assert row["targets"] == 1
    assert row["receptions"] == 1
    assert row["rec_yards"] == pytest.approx(9.0)
    assert row["team"] == "SF"
    assert row["position"] == "RB"

    # Also verify the passer's own row exists independently, id untouched.
    passer_rows = feats[feats["player_id"] == "00-0099999"]
    assert len(passer_rows) == 1
    assert passer_rows.iloc[0]["pass_attempts"] == 1


def test_fantasy_points_residual_math():
    gsis_id = "00-0055555"
    rush_df = make_rush_df(
        [
            {
                "rusher_player_id": gsis_id,
                "season": 2023,
                "week": 8,
                "posteam": "SF",
                "position": "RB",
                "rush_touchdown": 1,
                "rushing_yards": 50.0,
                "rushing_yards_exp": 30.0,
                "rushing_td_exp": 0.10,
            },
        ]
    )
    feats = build_player_week_features(empty_pass_df(), rush_df)
    row = feats[feats["player_id"] == gsis_id].iloc[0]

    # exp_rush_fantasy_points = 30.0*0.1 + 0.10*6.0 = 3.0 + 0.6 = 3.6
    assert row["exp_rush_fantasy_points"] == pytest.approx(3.6)
    assert row["exp_fantasy_points_total"] == pytest.approx(3.6)
    # actual = 50.0*0.1 + 1*6.0 = 5.0 + 6.0 = 11.0
    assert row["actual_fantasy_points_total"] == pytest.approx(11.0)
    assert row["fantasy_points_over_expected"] == pytest.approx(11.0 - 3.6)


# ---------------------------------------------------------------------------
# Empty-season fail-loud
# ---------------------------------------------------------------------------


def test_empty_season_raises():
    with pytest.raises(ValueError, match="empty"):
        build_player_week_features(pd.DataFrame(), pd.DataFrame())


def test_none_inputs_also_raise():
    with pytest.raises(ValueError, match="empty"):
        build_player_week_features(None, None)


def test_partial_empty_still_works():
    """Only one of pass/rush having rows is NOT the empty-season case."""
    rush_df = make_rush_df(
        [
            {
                "rusher_player_id": "00-0066666",
                "season": 2023,
                "week": 1,
                "posteam": "KC",
                "position": "RB",
                "rush_touchdown": 0,
                "rushing_yards": 5.0,
                "rushing_yards_exp": 4.0,
                "rushing_td_exp": 0.01,
            },
        ]
    )
    feats = build_player_week_features(empty_pass_df(), rush_df)
    assert len(feats) == 1
    assert feats.iloc[0]["player_id"] == "00-0066666"


# ---------------------------------------------------------------------------
# Feature column contract
# ---------------------------------------------------------------------------


def test_feature_column_contract():
    rush_df = make_rush_df(
        [
            {
                "rusher_player_id": "00-0077777",
                "season": 2024,
                "week": 3,
                "posteam": "DAL",
                "position": "RB",
                "rush_touchdown": 0,
                "rushing_yards": 3.0,
                "rushing_yards_exp": 2.0,
                "rushing_td_exp": 0.01,
            },
        ]
    )
    feats = build_player_week_features(empty_pass_df(), rush_df)
    assert list(feats.columns) == FEATURE_COLUMNS
    assert feats["season"].dtype.kind == "i"
    assert feats["week"].dtype.kind == "i"
