"""Board choice and the ESPN writer in scripts/set_lineups.py.

2026 replay findings this pins: the tool picked the board by file mtime (a
checkout rewrites it, so it read a board that was not the newest for weeks 4-7)
and fell back to preseason points / 17 whenever the weekly board was thin.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def sl(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "set_lineups_board", REPO / "scripts" / "set_lineups.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules["set_lineups_board"] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "GOLD", tmp_path / "gold")
    return m


def _board(n: int, ppg: float = 10.0) -> pd.DataFrame:
    pos = ["QB", "RB", "WR", "TE"]
    return pd.DataFrame(
        {
            "player_id": [f"p{i}" for i in range(n)],
            "player_name": [f"Player {i}" for i in range(n)],
            "position": [pos[i % 4] for i in range(n)],
            "recent_team": ["BUF"] * n,
            "proj_receptions": [4.0] * n,
            "proj_receiving_yards": [ppg * 5] * n,
        }
    )


def _write(sl, season, week, name, df):
    d = sl.GOLD / f"season={season}" / f"week={week}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    df.to_parquet(p, index=False)
    return p


def test_the_newest_board_by_filename_wins_even_when_mtime_says_otherwise(sl):
    old = _write(
        sl, 2026, 5, "projections_half_ppr_20261008_120000.parquet", _board(200, 8.0)
    )
    new = _write(
        sl, 2026, 5, "projections_half_ppr_20261011_165300.parquet", _board(200, 12.0)
    )
    os.utime(new, (1_000_000, 1_000_000))  # a checkout rewrote the newer file's mtime
    os.utime(old, (2_000_000_000, 2_000_000_000))
    df, label = sl.load_ours(2026, 5)
    assert "20261011_165300" in label
    assert df["receiving_yards"].iloc[0] == 60.0  # the 12-ppg board, not the 8-ppg one


def test_a_derived_board_is_never_read(sl):
    _write(sl, 2026, 5, "projections_half_ppr_20261008_120000.parquet", _board(200))
    _write(
        sl, 2026, 5, "projections_derived_20261012_120000.parquet", _board(200, 99.0)
    )
    _df, label = sl.load_ours(2026, 5)
    assert "derived" not in label


def test_a_missing_weekly_board_is_consensus_only_not_a_silent_preseason_fallback(sl):
    df, label = sl.load_ours(2026, 11, allow_preseason=False)
    assert label.startswith(sl.CONSENSUS_ONLY) and "no weekly board" in label
    assert df.empty  # NO numbers of ours, so nothing is blended into the advice


def test_a_thin_weekly_board_is_consensus_only_and_says_why(sl, capsys):
    _write(sl, 2026, 8, "projections_half_ppr_20261025_165121.parquet", _board(40))
    df, label = sl.load_ours(2026, 8, allow_preseason=False)
    assert label.startswith(sl.CONSENSUS_ONLY) and "only 40 skill rows" in label
    assert df.empty and "WARN" in capsys.readouterr().out


def test_the_waiver_tools_keep_the_preseason_fallback_and_the_return_shape(sl):
    """scripts/waiver_wire.py imports load_ours: (DataFrame, label), unchanged default."""
    pre = sl.GOLD / "preseason" / "season=2026"
    pre.mkdir(parents=True)
    df17 = _board(200).rename(
        columns={
            "proj_receptions": "receptions",
            "proj_receiving_yards": "receiving_yards",
        }
    )
    df17 = df17.assign(receptions=68.0, receiving_yards=850.0)
    df17.to_parquet(pre / "season_proj_half_ppr_20260901_120000.parquet", index=False)
    df, label = sl.load_ours(2026, 3)
    assert label.startswith("preseason pace") and len(df) == 200
    assert df["receptions"].iloc[0] == pytest.approx(4.0)  # season / 17


def test_a_healthy_board_is_labelled_weekly_with_its_age(sl):
    _write(sl, 2026, 5, "projections_half_ppr_20261011_165300.parquet", _board(200))
    _df, label = sl.load_ours(2026, 5, allow_preseason=False)
    assert (
        label.startswith("weekly Gold projections_half_ppr_20261011_165300")
        and "h old" in label
    )


def test_filename_stamp_orders_before_unstamped_files(sl, tmp_path):
    a, b = tmp_path / "a_20260101_000000.parquet", tmp_path / "b.parquet"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    assert sl._stamp(str(a)) > sl._stamp(str(b))


# --- ESPN writer: MUST FIX moves are filed like SWAPs, empty slots are not ---------------------


def _espn_payload():
    def entry(pid, name, slot, pos):
        return {
            "playerId": pid,
            "lineupSlotId": slot,
            "playerPoolEntry": {
                "id": pid,
                "player": {"fullName": name, "defaultPositionId": pos},
            },
        }

    # slot ids: 0 QB, 2 RB, 4 WR, 20 bench
    return {"teams": [{"id": 1, "roster": {"entries": [
        entry(10, "Bye Week QB", 0, 1), entry(11, "Bench QB", 20, 1), entry(12, "Some Runner", 2, 2),
    ]}}]}  # fmt: skip


def test_espn_write_dry_run_includes_a_must_fix_move(sl, capsys):
    from src.lineup_setter import MustFix, PlayerRow

    out_p = PlayerRow(
        "a", "Bye Week QB", "QB", "SF", ours=20, sleeper=20, slot="QB", bye=True
    )
    in_p = PlayerRow("b", "Bench QB", "QB", "BUF", ours=12, sleeper=12)
    fix = MustFix("QB", out_p, "BYE", in_p)
    delta = fix.as_delta()
    assert delta.verdict == "MUST FIX" and delta.in_player is in_p
    assert (
        MustFix("RB", None, "empty", in_p).as_delta() is None
    )  # nothing to read the slot from

    rc = sl.espn_write(
        preset={"league_id": "123"},
        deltas=[delta],
        espn_live={"team_id": 1, "payload": _espn_payload()},
        season=2026,
        week=11,
        apply_changes=False,
    )
    out = capsys.readouterr().out
    assert rc == 0 and "DRY RUN" in out and "not filing" not in out
    assert "Bye Week QB" in out and "Bench QB" in out
