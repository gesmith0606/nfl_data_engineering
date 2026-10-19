"""fill_lines_from_odds_snapshot: in-season lines from live odds snapshots."""

import numpy as np
import pandas as pd

from src.market_analytics import fill_lines_from_odds_snapshot

SNAP = "2026-10-20T13:00:00+00:00"  # Tuesday morning capture


def _snapshot(tmp_path, rows, name="odds_20261020_130000.parquet"):
    d = tmp_path / "season=2026"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / name)
    return str(tmp_path)


def _odds(home, away, home_spreads, totals, kick="2026-10-25T17:00:00Z", snap=SNAP):
    base = dict(home_team_nfl=home, away_team_nfl=away, commence_time=kick, snapshot_ts=snap)
    rows = [dict(base, market="spreads", home_spread=s, total_points=np.nan) for s in home_spreads]
    rows += [dict(base, market="totals", home_spread=np.nan, total_points=t) for t in totals]
    return rows


def test_fills_unposted_lines_with_nflverse_sign(tmp_path):
    root = _snapshot(
        tmp_path,
        _odds("CHI", "NE", [-3.0, -2.5, -3.5], [44.5, 45.5])
        + _odds("SEA", "KC", [2.0], [48.0]),
    )
    sched = pd.DataFrame({
        "home_team": ["CHI", "SEA", "DEN"],
        "away_team": ["NE", "KC", "SEA"],
        "result": [np.nan, np.nan, 7.0],
        "spread_line": [np.nan, np.nan, -3.0],
        "total_line": [np.nan, np.nan, 41.0],
    })
    out = fill_lines_from_odds_snapshot(sched, 2026, snapshot_dir=root)

    # Home favored by 3 in the books -> nflverse +3.0 (home favored positive).
    assert out.loc[0, "spread_line"] == 3.0
    assert out.loc[0, "total_line"] == 45.0
    assert out.loc[1, "spread_line"] == -2.0  # home dog
    assert out.loc[2, "spread_line"] == -3.0  # posted/played untouched
    assert list(out.columns) == list(sched.columns)


def test_never_fills_played_games_or_overwrites(tmp_path):
    root = _snapshot(tmp_path, _odds("CHI", "NE", [-7.0], [40.0]))
    sched = pd.DataFrame({
        "home_team": ["CHI", "CHI"],
        "away_team": ["NE", "NE"],
        "result": [3.0, np.nan],
        "spread_line": [np.nan, 1.5],
        "total_line": [np.nan, np.nan],
    })
    out = fill_lines_from_odds_snapshot(sched, 2026, snapshot_dir=root)
    assert np.isnan(out.loc[0, "spread_line"])  # played: left alone
    assert out.loc[1, "spread_line"] == 1.5  # posted line kept
    assert out.loc[1, "total_line"] == 40.0


def test_in_game_prices_ignored_in_favor_of_earlier_pregame(tmp_path):
    kick = "2026-10-25T17:00:00Z"
    _snapshot(tmp_path, _odds("CHI", "NE", [-3.0], [45.0], kick=kick))
    root = _snapshot(  # newer file, taken mid-game: live line must not win
        tmp_path,
        _odds("CHI", "NE", [-17.0], [60.0], kick=kick, snap="2026-10-25T18:30:00+00:00"),
        name="odds_20261025_183000.parquet",
    )
    sched = pd.DataFrame({
        "home_team": ["CHI"], "away_team": ["NE"], "result": [np.nan],
        "spread_line": [np.nan], "total_line": [np.nan],
    })
    out = fill_lines_from_odds_snapshot(sched, 2026, snapshot_dir=root)
    assert out.loc[0, "spread_line"] == 3.0
    assert out.loc[0, "total_line"] == 45.0


def test_gameday_must_match_when_available(tmp_path):
    # Sunday 00:20Z kickoff is Saturday night Eastern.
    root = _snapshot(tmp_path, _odds("KC", "LV", [-6.0], [47.0], kick="2026-10-25T00:20:00Z"))
    sched = pd.DataFrame({
        "home_team": ["KC", "KC"], "away_team": ["LV", "LV"],
        "gameday": ["2026-10-24", "2026-12-20"],  # same pair, two dates
        "result": [np.nan, np.nan],
        "spread_line": [np.nan, np.nan], "total_line": [np.nan, np.nan],
    })
    out = fill_lines_from_odds_snapshot(sched, 2026, snapshot_dir=root)
    assert out.loc[0, "spread_line"] == 6.0
    assert np.isnan(out.loc[1, "spread_line"])  # other meeting untouched
    assert "_date" not in out.columns


def test_no_snapshot_is_noop(tmp_path):
    sched = pd.DataFrame({
        "home_team": ["CHI"], "away_team": ["NE"],
        "spread_line": [np.nan], "total_line": [np.nan],
    })
    out = fill_lines_from_odds_snapshot(sched, 2019, snapshot_dir=str(tmp_path))
    assert out.equals(sched)
