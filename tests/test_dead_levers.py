"""PR 3: levers that never fire on live 2026 inputs.

Found by reading the 2026 Tuesday runner logs and replaying weeks 1-9 with the
data truncated at W-1 (what a live run sees):

* RB snap-collapse looked its signal up at ``week == target week``, but the
  signal frame only has rows for weeks where the player has snaps, and the
  target week's snaps do not exist yet on a Tuesday: it never fired live.
* WR route-slope and WR TPRR collapses need route participation, which
  nflverse does not publish until after the postseason ("Route participation:
  0 rows" on every 2026 run): skipped live, yet applied in every historical
  backtest, so backtests overstated production.
* The graph ranking nudge logged ``nudged 0 / 376 players`` on the week-7 run.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import projection_engine as pe  # noqa: E402
import ranking_score as rs  # noqa: E402
from projection_engine import RB_SNAP_COLLAPSE_MULT, _apply_rb_snap_collapse  # noqa: E402


def _snaps(pct_by_week, player="Zack Moss", team="IND"):
    return pd.DataFrame(
        {
            "season": 2026,
            "week": list(pct_by_week),
            "team": team,
            "player": player,
            "position": "RB",
            "offense_pct": list(pct_by_week.values()),
        }
    )


def _board():
    return pd.DataFrame(
        {
            "player_id": ["00-0035000", "00-0036000"],
            "player_name": ["Zack Moss", "Jonathan Taylor"],
            "position": ["RB", "RB"],
            "recent_team": ["IND", "IND"],
            "proj_rush_yards": [60.0, 80.0],
            "projected_points": [10.0, 15.0],
        }
    )


def _weekly():
    return pd.DataFrame(
        {
            "player_id": ["00-0035000", "00-0036000"],
            "player_name": ["Zack Moss", "Jonathan Taylor"],
            "player_display_name": ["Zack Moss", "Jonathan Taylor"],
            "position": ["RB", "RB"],
            "recent_team": ["IND", "IND"],
            "season": [2026, 2026],
            "week": [4, 4],
        }
    )


def _two_backs(week_pcts_moss, week_pcts_taylor):
    return pd.concat(
        [_snaps(week_pcts_moss), _snaps(week_pcts_taylor, player="Jonathan Taylor")], ignore_index=True
    )


COLLAPSE_THROUGH_W4 = {1: 0.80, 2: 0.80, 3: 0.20, 4: 0.10}  # snaps exist only through week W-1 = 4
STEADY = {1: 0.60, 2: 0.60, 3: 0.60, 4: 0.60}


def test_rb_snap_collapse_fires_on_a_live_snap_frame_with_no_target_week_rows():
    """The 2026 bug: on a Tuesday the target week (5) has no snaps yet, so the
    old `signals.week == target week` lookup found nothing and never fired."""
    combined = _board()
    n = _apply_rb_snap_collapse(combined, _two_backs(COLLAPSE_THROUGH_W4, STEADY), _weekly(), 2026, 5)
    assert n == 1
    assert combined.loc[0, "projected_points"] == pytest.approx(10.0 * RB_SNAP_COLLAPSE_MULT)
    assert combined.loc[1, "projected_points"] == 15.0  # steady back untouched


def test_target_week_snaps_never_influence_the_signal():
    """A week-5 row in the frame (a backtest has it) must change nothing: the
    signal for week 5 is a function of weeks < 5 only."""
    live = _two_backs(COLLAPSE_THROUGH_W4, STEADY)
    with_w5 = pd.concat([live, _snaps({5: 0.95}, "Zack Moss"), _snaps({5: 0.0}, "Jonathan Taylor")], ignore_index=True)
    a, b = _board(), _board()
    na = _apply_rb_snap_collapse(a, live, _weekly(), 2026, 5)
    nb = _apply_rb_snap_collapse(b, with_w5, _weekly(), 2026, 5)
    assert na == nb == 1
    pd.testing.assert_frame_equal(a, b)


def test_a_back_who_sat_out_the_target_week_is_still_evaluated():
    """The old lookup could only flag players who HAD snaps in the target week,
    i.e. it conditioned on having played - not knowable on Tuesday."""
    snaps = _two_backs(COLLAPSE_THROUGH_W4, STEADY)  # nobody has week-5 snaps
    combined = _board()
    assert _apply_rb_snap_collapse(combined, snaps, _weekly(), 2026, 5) == 1


def test_no_signal_history_means_no_flag():
    combined = _board()
    short = _two_backs({3: 0.2, 4: 0.1}, {3: 0.6, 4: 0.6})  # < 4 weeks of history
    assert _apply_rb_snap_collapse(combined, short, _weekly(), 2026, 5) == 0


def test_prior_season_snaps_do_not_create_current_season_flags():
    old = _snaps(COLLAPSE_THROUGH_W4).assign(season=2025)
    combined = _board()
    assert _apply_rb_snap_collapse(combined, old, _weekly(), 2026, 5) == 0


# ---------------------------------------------------------------- levers that cannot fire live are off
def test_route_based_levers_are_off_by_default():
    """No route participation exists in-season (0 rows on every 2026 run)."""
    assert pe.USE_WR_ROUTE_SLOPE_COLLAPSE is False
    assert pe.USE_WR_TPRR_COLLAPSE is False


def test_route_levers_do_not_touch_a_board_even_with_route_data_when_off():
    combined = pd.DataFrame(
        {"player_id": ["w1"], "position": ["WR"], "projected_points": [12.0], "proj_receiving_yards": [80.0]}
    )
    route_df = pd.DataFrame({"player_id": ["w1"], "season": [2026], "week": [5], "route_rate_slope": [-0.2]})
    # the helper itself still works (kept for the offseason, when participation lands) ...
    assert pe._apply_wr_route_slope_collapse(combined.copy(), route_df, 2026, 5) == 1
    # ... but the engine never calls it while the flag is off.
    assert pe.USE_WR_ROUTE_SLOPE_COLLAPSE is False


def test_ranking_nudge_is_off_and_ranking_score_still_equals_points():
    assert rs.USE_RANKING_SCORE is False
    df = pd.DataFrame(
        {"player_id": ["a", "b"], "position": ["WR", "WR"], "projected_points": [10.0, 8.0], "season": 2026, "week": 5}
    )
    out = rs.apply_ranking_scores(df, None, season=2026, week=5)
    assert list(out["ranking_score"]) == [10.0, 8.0]
