"""Regression tests: RB snap-collapse must survive re-ingested snap snapshots.

Bug (2026-09-22): ``bronze_ingestion_simple.py --data-type snap_counts``
re-writes EVERY week of the season into its ``week=W/`` partition on each run,
with a new timestamped filename. After the second local ingest,
``season=2026/week=1/`` held two snapshots, and every snap loader globbed
``week=*/*.parquet`` and concatenated all of them — so each (player, week)
appeared twice. ``compute_snap_trend_signals`` then did
``float(all_weeks[w])`` on a duplicated index, got a Series back, and raised
``TypeError: cannot convert the series to <class 'float'>``. The engine caught
it and logged "RB snap-collapse correction failed; projecting without", so
the correction silently no-op'd on every local weekly run (the GHA cron starts
from a fresh checkout with one snapshot per week, so it was unaffected).
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from projection_engine import RB_SNAP_COLLAPSE_MULT, _apply_rb_snap_collapse
from rb_role_signals import compute_snap_trend_signals
from utils import latest_parquet_per_dir


def _collapsing_snaps() -> pd.DataFrame:
    """One RB whose snap share collapses from 0.80 to 0.15 by week 5."""
    pct = {1: 0.80, 2: 0.80, 3: 0.20, 4: 0.10, 5: 0.10}
    return pd.DataFrame(
        {
            "season": 2026,
            "week": list(pct),
            "team": "IND",
            "player": "Zack Moss",
            "position": "RB",
            "offense_pct": list(pct.values()),
        }
    )


def _twice_ingested(snaps: pd.DataFrame) -> pd.DataFrame:
    """Simulate two snapshots of the same weeks concatenated by the loader."""
    return pd.concat([snaps, snaps], ignore_index=True)


class TestSnapTrendSignalsDuplicates:
    def test_duplicated_player_weeks_do_not_raise(self):
        """Previously: TypeError 'cannot convert the series to float'."""
        result = compute_snap_trend_signals(_twice_ingested(_collapsing_snaps()))
        assert len(result) == 5  # one row per player-week, not two

    def test_duplicated_player_weeks_match_clean_signal(self):
        clean = compute_snap_trend_signals(_collapsing_snaps())
        dup = compute_snap_trend_signals(_twice_ingested(_collapsing_snaps()))
        pd.testing.assert_frame_equal(
            clean.reset_index(drop=True), dup.reset_index(drop=True)
        )
        assert dup.loc[dup["week"] == 5, "snap_share_collapsing"].iloc[0] == 1

    def test_latest_snapshot_wins_on_duplicate(self):
        """When two snapshots disagree, the later (last-concatenated) row wins."""
        old = _collapsing_snaps()
        new = old.copy()
        new.loc[new["week"] == 1, "offense_pct"] = 0.90
        result = compute_snap_trend_signals(pd.concat([old, new], ignore_index=True))
        w5 = result[result["week"] == 5].iloc[0]
        # prior window = weeks 1-2 = mean(0.90, 0.80)
        assert w5["prior_snap_pct"] == pytest.approx(0.85)


class TestApplyRbSnapCollapseDuplicates:
    def test_multiplier_applied_with_duplicated_snaps(self):
        combined = pd.DataFrame(
            {
                "player_id": ["00-0035000", "00-0036000"],
                "player_name": ["Zack Moss", "Jonathan Taylor"],
                "position": ["RB", "RB"],
                "recent_team": ["IND", "IND"],
                "proj_rush_yards": [60.0, 80.0],
                "projected_points": [10.0, 15.0],
            }
        )
        weekly = pd.DataFrame(
            {
                "player_id": ["00-0035000"],
                "player_name": ["Zack Moss"],
                "player_display_name": ["Zack Moss"],
                "position": ["RB"],
                "recent_team": ["IND"],
                "season": [2026],
                "week": [4],
            }
        )
        n = _apply_rb_snap_collapse(
            combined, _twice_ingested(_collapsing_snaps()), weekly, 2026, 5
        )
        assert n == 1
        assert combined.loc[0, "projected_points"] == pytest.approx(
            10.0 * RB_SNAP_COLLAPSE_MULT
        )
        assert combined.loc[0, "proj_rush_yards"] == pytest.approx(
            60.0 * RB_SNAP_COLLAPSE_MULT
        )
        assert combined.loc[1, "projected_points"] == 15.0  # untouched


class TestLatestParquetPerDir:
    def test_keeps_only_newest_file_per_partition(self, tmp_path):
        for week, stamps in {
            1: ["20260915_212515", "20260922_200652"],
            2: ["20260922_200652"],
        }.items():
            d = tmp_path / "season=2026" / f"week={week}"
            d.mkdir(parents=True)
            for s in stamps:
                (d / f"snap_counts_{s}.parquet").write_bytes(b"")
        files = latest_parquet_per_dir(
            str(tmp_path / "season=2026" / "week=*" / "*.parquet")
        )
        names = sorted(os.path.relpath(f, tmp_path).replace(os.sep, "/") for f in files)
        assert names == [
            "season=2026/week=1/snap_counts_20260922_200652.parquet",
            "season=2026/week=2/snap_counts_20260922_200652.parquet",
        ]

    def test_no_match_returns_empty(self, tmp_path):
        assert latest_parquet_per_dir(str(tmp_path / "nope" / "*.parquet")) == []
