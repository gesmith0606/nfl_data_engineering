"""Offline tests for the draft value engine (docs/DRAFT_DOCTRINE.md rules)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
import pytest

from src.draft_value import label_board, summarize, td_share


def _board():
    rows = [
        # name, pos, vorp, adp, age, exp, rush_td, rec_td, pass_td, pts, prior_rank, prior_tgt, prior_td, vac
        ("Value Back", "RB", 60.0, 40, 24, 3, 8, 2, 0, 220, 20, 30, 10, 0.0),
        ("Old Back", "RB", 55.0, 12, 28, 7, 12, 1, 0, 215, 3, 40, 13, 0.0),
        ("Fair WR", "WR", 40.0, 30, 26, 5, 0, 7, 0, 180, 15, 120, 7, 0.0),
        ("Young WR", "WR", 30.0, 60, 23, 2, 0, 3, 0, 165, 40, 80, 3, 0.25),
        ("Deep TE", "TE", 20.0, 130, 30, 8, 0, 6, 0, 130, 14, 70, 6, 0.0),
        ("Kicker", "K", 5.0, 140, 30, 8, 0, 0, 0, 120, 1, 0, 0, 0.0),
        ("Undrafted WR", "WR", -10.0, 350, 27, 4, 0, 1, 0, 90, 90, 10, 1, 0.0),
    ]
    df = pd.DataFrame(rows, columns=[
        "player_name", "position", "vorp", "adp_rank", "age", "years_exp", "rushing_tds", "receiving_tds",
        "passing_tds", "projected_season_points", "prior_pos_rank", "prior_targets", "prior_tds", "vacancy_absorbed_share",
    ])
    df["is_low_sample_projection"] = df["player_name"].eq("Old Back")
    df["model_rank"] = df["projected_season_points"].rank(ascending=False, method="first").astype(int)
    df["position_rank"] = df.groupby("position")["projected_season_points"].rank(ascending=False, method="first").astype(int)
    df["td_share"] = td_share(df)
    return df


@pytest.mark.unit
def test_value_is_positional_vbd_gap_not_raw_rank():
    out = label_board(_board()).set_index("player_name")
    # VBD rank: Value Back #1 (vorp 60) vs ADP 40 -> gap 39 -> value.
    assert bool(out.loc["Value Back", "flag_value"])
    assert "§10" in out.loc["Value Back", "reasons"]
    # Kicker never enters the VBD board.
    assert pd.isna(out.loc["Kicker", "vbd_rank"])
    assert not bool(out.loc["Kicker", "flag_value"])


@pytest.mark.unit
def test_bust_needs_inflation_plus_signal_or_three_signals():
    out = label_board(_board()).set_index("player_name")
    old = out.loc["Old Back"]
    # Age 28 RB + RB prior top-5 + low-sample projection -> 3 signals -> bust.
    # TD share (36%) is tagged for information only (back-test: no bust lift).
    assert bool(old["flag_bust"]) and old["bust_score"] >= 3
    assert "§20" in old["reasons"] and "§21" in old["reasons"] and "§28" in old["reasons"]
    assert "(info) TD-dependent" in old["reasons"]
    assert not bool(out.loc["Fair WR", "flag_bust"])
    # A WR with a prior top-5 finish is NOT penalised (RB-only signal).
    assert "§21" not in out.loc["Fair WR", "reasons"]


@pytest.mark.unit
def test_breakout_young_with_vacated_opportunity_and_td_regression():
    out = label_board(_board()).set_index("player_name")
    yw = out.loc["Young WR"]
    assert bool(yw["flag_breakout"])
    assert "§30/§31" in yw["reasons"] and "§34" in yw["reasons"]


@pytest.mark.unit
def test_deep_sleeper_requires_startable_rank_and_priced_adp():
    out = label_board(_board()).set_index("player_name")
    assert bool(out.loc["Deep TE", "flag_deep_sleeper"])  # TE1 by model, ADP 130
    assert not bool(out.loc["Undrafted WR", "flag_deep_sleeper"])  # ADP 350 = unpriced
    assert pd.isna(out.loc["Undrafted WR", "adp_gap"])


@pytest.mark.unit
def test_summarize_returns_all_sections():
    s = summarize(label_board(_board()), top=5)
    assert set(s) == {"values", "busts", "breakouts", "deep_sleepers"}
    assert "Value Back" in set(s["values"]["player_name"])
    assert "Old Back" in set(s["busts"]["player_name"])


@pytest.mark.unit
def test_market_faded_star_is_flagged_and_midtier_fade_is_info():
    df = _board()
    # Positional ADP rank is board-relative, so give the board enough RB/WR
    # depth for a >= 12-spot fade to exist at all.
    fillers = []
    for i in range(30):
        fillers.append(("Filler RB%d" % i, "RB", 20.0 - i, 10 + i * 6, 25, 4, 5, 1, 0, 150 - i, 40, 30, 5, 0.0))
        fillers.append(("Filler WR%d" % i, "WR", 18.0 - i, 12 + i * 6, 25, 4, 0, 4, 0, 140 - i, 40, 60, 4, 0.0))
    extra = pd.DataFrame(fillers, columns=[
        "player_name", "position", "vorp", "adp_rank", "age", "years_exp", "rushing_tds", "receiving_tds",
        "passing_tds", "projected_season_points", "prior_pos_rank", "prior_targets", "prior_tds", "vacancy_absorbed_share",
    ])
    extra["is_low_sample_projection"] = False
    df = pd.concat([df, extra], ignore_index=True)
    df["model_rank"] = df["projected_season_points"].rank(ascending=False, method="first").astype(int)
    df["position_rank"] = df.groupby("position")["projected_season_points"].rank(ascending=False, method="first").astype(int)
    # "Old Back": prior RB3 producer, market-dropped behind every filler RB.
    df.loc[df.player_name == "Old Back", "adp_rank"] = 190
    df.loc[df.player_name == "Old Back", "prior_pos_rank"] = 3
    # "Fair WR": prior WR15 producer with the same hard fade -> info only.
    df.loc[df.player_name == "Fair WR", "prior_pos_rank"] = 15
    df.loc[df.player_name == "Fair WR", "adp_rank"] = 195
    out = label_board(df).set_index("player_name")
    assert "§36" in out.loc["Old Back", "reasons"]
    assert "(info) faded mid-tier" in out.loc["Fair WR", "reasons"]
    assert "§36" not in out.loc["Fair WR", "reasons"]
