"""Week-1 prior-season seed is gated on the CURRENT depth chart.

Regression for the 2026 Week 1 board (``.planning/SEASON_2026_WEEKS_1_2_RETRO.md``):
the prior-season seed (PR #109) gave every player his final 2025 row, so
backups whose last rows came from a starting stretch inherited starter
projections (Fields 18.1 as KC's QB2, Winston 16.3, a retired Rivers 13.8,
Jacobs 11.6 as GB's RB4 while commissioner-exempt, an unsigned Tyreek Hill).
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from seed_depth_gate import (  # noqa: E402
    BACKUP_SCALE,
    STARTER_DEPTH,
    apply_week1_seed_depth_gate,
    depth_chart_snapshot,
)


def _dc_row(dt, team, gsis, pos, rank):
    return {
        "dt": dt,
        "team": team,
        "player_name": gsis,
        "gsis_id": gsis,
        "pos_abb": pos,
        "pos_rank": rank,
    }


@pytest.fixture
def depth_chart():
    old = "2026-09-01T12:00:00Z"
    new = "2026-09-09T12:00:00Z"
    later = "2026-09-20T12:00:00Z"
    rows = [
        # Sept 1: Fields is still KC's listed QB1 (stale); Sept 9: Mahomes.
        _dc_row(old, "KC", "fields", "QB", 1),
        _dc_row(old, "KC", "mahomes", "QB", 2),
        _dc_row(new, "KC", "mahomes", "QB", 1),
        _dc_row(new, "KC", "fields", "QB", 2),
        _dc_row(new, "GB", "love", "QB", 1),
        _dc_row(new, "GB", "lloyd", "RB", 1),
        _dc_row(new, "GB", "brooks", "RB", 2),
        _dc_row(new, "GB", "jacobs", "RB", 4),
        _dc_row(new, "GB", "watson", "WR", 1),
        _dc_row(new, "GB", "golden", "WR", 3),
        _dc_row(new, "GB", "melton", "WR", 4),
        _dc_row(new, "GB", "kraft", "TE", 1),
        # Same player listed twice (two formations) — best rank wins.
        _dc_row(new, "GB", "kraft", "TE", 3),
        _dc_row(new, "GB", "musgrave", "TE", 5),
        # IND / MIA are covered by the snapshot, just without Rivers / Hill.
        _dc_row(new, "IND", "jones", "QB", 1),
        _dc_row(new, "MIA", "waddle", "WR", 1),
        # Non-fantasy position rows are ignored.
        _dc_row(new, "GB", "someone", "LT", 1),
        # After the projection date: must not leak into a Week 1 run.
        _dc_row(later, "KC", "fields", "QB", 1),
        _dc_row(later, "KC", "mahomes", "QB", 2),
        _dc_row(later, "GB", "love", "QB", 1),
    ]
    return pd.DataFrame(rows)


def _proj(pid, pos, team, pts):
    return {
        "player_id": pid,
        "player_name": pid,
        "position": pos,
        "recent_team": team,
        "proj_season": 2026,
        "proj_week": 1,
        "proj_passing_yards": 250.0 if pos == "QB" else 0.0,
        "proj_receiving_yards": 60.0 if pos != "QB" else 0.0,
        "projected_points": pts,
        "projected_floor": pts * 0.6,
        "projected_ceiling": pts * 1.4,
    }


@pytest.fixture
def board():
    return pd.DataFrame(
        [
            _proj("mahomes", "QB", "KC", 20.0),
            _proj("fields", "QB", "KC", 18.0),
            _proj("love", "QB", "GB", 17.0),
            _proj("rivers", "QB", "IND", 13.8),  # retired: on no depth chart
            _proj("hill", "WR", "MIA", 11.7),  # unsigned: on no depth chart
            _proj("lloyd", "RB", "GB", 12.0),
            _proj("brooks", "RB", "GB", 6.0),
            _proj("jacobs", "RB", "GB", 11.6),  # RB4, commissioner-exempt
            _proj("watson", "WR", "GB", 10.0),
            _proj("golden", "WR", "GB", 8.0),
            _proj("melton", "WR", "GB", 5.0),
            _proj("kraft", "TE", "GB", 9.0),
            _proj("musgrave", "TE", "GB", 4.0),
        ]
    )


AS_OF = pd.Timestamp("2026-09-10", tz="UTC")


def _row(df, pid):
    return df.set_index("player_id").loc[pid]


def test_snapshot_uses_latest_dt_at_or_before_as_of(depth_chart):
    snap = depth_chart_snapshot(depth_chart, as_of=AS_OF)
    kc_qb = snap[(snap["team"] == "KC")].set_index("player_id")["pos_rank"]
    assert kc_qb["mahomes"] == 1 and kc_qb["fields"] == 2
    # Best rank per player; non-fantasy positions dropped.
    assert _row(snap, "kraft")["pos_rank"] == 1
    assert "someone" not in set(snap["player_id"])


def test_snapshot_default_as_of_is_latest(depth_chart):
    snap = depth_chart_snapshot(depth_chart)
    kc_qb = snap[(snap["team"] == "KC")].set_index("player_id")["pos_rank"]
    assert kc_qb["fields"] == 1


def test_snapshot_empty_when_nothing_before_as_of(depth_chart):
    snap = depth_chart_snapshot(depth_chart, as_of=pd.Timestamp("2026-01-01", tz="UTC"))
    assert snap.empty


def test_only_current_qb1_keeps_seeded_starter_projection(depth_chart, board):
    out = apply_week1_seed_depth_gate(board, depth_chart, week=1, as_of=AS_OF)
    assert _row(out, "mahomes")["projected_points"] == 20.0
    assert _row(out, "love")["projected_points"] == 17.0
    fields = _row(out, "fields")
    assert fields["projected_points"] == pytest.approx(18.0 * BACKUP_SCALE)
    assert fields["proj_passing_yards"] == pytest.approx(250.0 * BACKUP_SCALE)
    assert fields["projected_ceiling"] == pytest.approx(18.0 * 1.4 * BACKUP_SCALE)
    assert fields["seed_depth_gate"] == "backup_depth"
    assert pd.isna(_row(out, "mahomes")["seed_depth_gate"])


def test_players_on_no_depth_chart_are_zeroed(depth_chart, board):
    out = apply_week1_seed_depth_gate(board, depth_chart, week=1, as_of=AS_OF)
    for pid in ("rivers", "hill"):
        r = _row(out, pid)
        assert r["projected_points"] == 0.0
        assert r["projected_ceiling"] == 0.0
        assert r["proj_receiving_yards"] == 0.0
        assert r["seed_depth_gate"] == "off_depth_chart"


def test_non_qb_beyond_starter_depth_get_backup_scale(depth_chart, board):
    out = apply_week1_seed_depth_gate(board, depth_chart, week=1, as_of=AS_OF)
    assert STARTER_DEPTH["RB"] == 2 and STARTER_DEPTH["WR"] == 3
    # Within starter depth: untouched.
    for pid, pts in (("lloyd", 12.0), ("brooks", 6.0), ("golden", 8.0), ("kraft", 9.0)):
        assert _row(out, pid)["projected_points"] == pts
    # Beyond: backup scale (Jacobs as RB4, WR4, TE5).
    for pid, pts in (("jacobs", 11.6), ("melton", 5.0), ("musgrave", 4.0)):
        assert _row(out, pid)["projected_points"] == pytest.approx(pts * BACKUP_SCALE)
        assert _row(out, pid)["seed_depth_gate"] == "backup_depth"


def test_ranks_rederived_after_gate(depth_chart, board):
    ranked = board.assign(
        overall_rank=range(1, len(board) + 1),
        position_rank=board.groupby("position")["projected_points"]
        .rank(ascending=False, method="first")
        .astype(int),
    )
    out = apply_week1_seed_depth_gate(ranked, depth_chart, week=1, as_of=AS_OF)
    assert list(out["overall_rank"]) == list(range(1, len(out) + 1))
    assert out["projected_points"].is_monotonic_decreasing
    qbs = out[out["position"] == "QB"].set_index("player_id")["position_rank"]
    assert qbs["mahomes"] == 1 and qbs["love"] == 2 and qbs["fields"] == 3


def test_mid_season_weeks_untouched(depth_chart, board):
    out = apply_week1_seed_depth_gate(board, depth_chart, week=2, as_of=AS_OF)
    pd.testing.assert_series_equal(out["projected_points"], board["projected_points"])


def test_no_depth_chart_is_noop(board):
    for dc in (None, pd.DataFrame()):
        out = apply_week1_seed_depth_gate(board, dc, week=1, as_of=AS_OF)
        pd.testing.assert_series_equal(
            out["projected_points"], board["projected_points"]
        )


def test_team_missing_from_snapshot_is_not_zeroed(depth_chart, board):
    # A partial scrape without KC must not zero KC's players.
    dc = depth_chart[depth_chart["team"] != "KC"]
    out = apply_week1_seed_depth_gate(board, dc, week=1, as_of=AS_OF)
    assert _row(out, "fields")["projected_points"] == 18.0
    assert _row(out, "mahomes")["projected_points"] == 20.0


def test_low_join_coverage_skips_gate(board):
    # IDs in a different format (e.g. Sleeper ids) -> almost nothing joins.
    dc = pd.DataFrame(
        [
            _dc_row("2026-09-09T12:00:00Z", t, f"x{i}", "QB", 1)
            for i, t in enumerate(["KC", "GB", "IND", "MIA"])
        ]
    )
    out = apply_week1_seed_depth_gate(board, dc, week=1, as_of=AS_OF)
    pd.testing.assert_series_equal(out["projected_points"], board["projected_points"])
