"""Tests for src/streaming.py — DEF/K streaming signals."""

import pandas as pd
import pytest

from src.streaming import (
    implied_totals_from_odds,
    implied_totals_from_schedule,
    matchup_table,
    swap_verdict,
)


def test_implied_totals_from_odds_uses_home_spread_sign():
    # Home favored by 6 (home_spread -6) with total 44 -> home 25, away 19.
    odds = pd.DataFrame(
        {
            "home_team_nfl": ["BUF", "BUF", "BUF", "BUF"],
            "away_team_nfl": ["LAC", "LAC", "LAC", "LAC"],
            "bookmaker": ["dk", "dk", "fd", "fd"],
            "market": ["spreads", "totals", "spreads", "totals"],
            "home_spread": [-6.0, None, -6.0, None],
            "total_points": [None, 44.0, None, 44.0],
        }
    )
    out = implied_totals_from_odds(odds)
    assert out["BUF"] == pytest.approx(25.0)
    assert out["LAC"] == pytest.approx(19.0)


def test_implied_totals_from_schedule_nflverse_sign():
    # nflverse spread_line is from the HOME perspective: positive = home favored.
    sched = pd.DataFrame(
        {
            "week": [3],
            "home_team": ["BUF"],
            "away_team": ["LAC"],
            "spread_line": [6.0],
            "total_line": [44.0],
        }
    )
    out = implied_totals_from_schedule(sched, week=3)
    assert out["BUF"] == pytest.approx(25.0)
    assert out["LAC"] == pytest.approx(19.0)


def test_matchup_table_marks_byes_and_opponents():
    sched = pd.DataFrame(
        {
            "week": [3, 3, 4],
            "home_team": ["BUF", "PHI", "BUF"],
            "away_team": ["LAC", "CHI", "NE"],
            "spread_line": [6.0, 3.0, 2.0],
            "total_line": [44.0, 48.0, 40.0],
        }
    )
    t = matchup_table(sched, weeks=[3, 4], teams=["BUF", "PHI"])
    buf3 = t[(t.team == "BUF") & (t.week == 3)].iloc[0]
    assert buf3.opp == "LAC" and buf3.opp_implied == pytest.approx(19.0)
    phi4 = t[(t.team == "PHI") & (t.week == 4)].iloc[0]
    assert phi4.bye


def test_future_week_without_lines_falls_back_to_scoring_form():
    sched = pd.DataFrame(
        {
            "week": [1, 1, 2, 2, 3],
            "home_team": ["BUF", "PHI", "BUF", "PHI", "BUF"],
            "away_team": ["LAC", "CHI", "CHI", "LAC", "PHI"],
            "home_score": [30, 20, 24, 10, None],
            "away_score": [10, 14, 20, 17, None],
            "spread_line": [None, None, None, None, None],
            "total_line": [None, None, None, None, None],
        }
    )
    t = matchup_table(sched, weeks=[3], teams=["BUF"])
    row = t.iloc[0]
    # Implied = mean(team points scored/game, opponent points allowed/game).
    # BUF scored 30, 24 -> 27.0; PHI allowed 14, 17 -> 15.5  => BUF 21.25.
    # PHI scored 20, 10 -> 15.0; BUF allowed 10, 20 -> 15.0  => PHI 15.0.
    assert row.own_implied == pytest.approx(21.25)
    assert row.opp_implied == pytest.approx(15.0)
    assert row.line_source == "scoring_form"


def test_swap_verdict_requires_both_sources():
    # Candidate better on both platform projection and Vegas -> SWAP.
    assert (
        swap_verdict(proj_gain=2.0, vegas_gain=3.0, proj_min=1.5, vegas_min=2.0)
        == "SWAP"
    )
    # Only one source agrees -> SPLIT.
    assert (
        swap_verdict(proj_gain=2.0, vegas_gain=-1.0, proj_min=1.5, vegas_min=2.0)
        == "SPLIT"
    )
    # Both positive but small -> COIN FLIP.
    assert (
        swap_verdict(proj_gain=0.5, vegas_gain=0.5, proj_min=1.5, vegas_min=2.0)
        == "COIN FLIP"
    )
    # Both worse -> KEEP.
    assert (
        swap_verdict(proj_gain=-1.0, vegas_gain=-2.0, proj_min=1.5, vegas_min=2.0)
        == "KEEP"
    )
