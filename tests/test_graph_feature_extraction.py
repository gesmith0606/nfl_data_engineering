#!/usr/bin/env python3
"""Tests for src/graph_feature_extraction.py.

Covers:
- compute_ol_rb_features: rb_ypc_delta_backup_ol must be NaN (not a fabricated
  delta) when only one side (full-OL or backup-OL) was actually observed.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_feature_extraction import compute_ol_rb_features


def _make_player_weekly(player_id="RB-001", season=2022, weeks=(1, 2, 3)):
    return pd.DataFrame(
        [
            {
                "player_id": player_id,
                "season": season,
                "week": w,
                "position": "RB",
                "recent_team": "KC",
            }
            for w in weeks
        ]
    )


def _make_pbp(player_id="RB-001", season=2022, week=1):
    """One rush play by player_id in the given (season, week)."""
    return pd.DataFrame(
        [
            {
                "game_id": f"{season}_{week:02d}_KC_BUF",
                "play_id": 1.0,
                "season": season,
                "week": week,
                "play_type": "run",
                "posteam": "KC",
                "rusher_player_id": player_id,
                "yards_gained": 4.0,
            }
        ]
    )


def _make_participation(pbp_row, ol_count):
    """Offense OL rows for a single play, ol_count OL players."""
    rows = []
    for i in range(ol_count):
        rows.append(
            {
                "game_id": pbp_row["game_id"],
                "play_id": pbp_row["play_id"],
                "player_gsis_id": f"OL-{i}",
                "side": "offense",
                "position": "G",
            }
        )
    return pd.DataFrame(rows)


class TestRbYpcDeltaBackupOl:
    def test_nan_when_only_full_ol_observed(self):
        """RB with only full-OL (5 starters) rushes should have NaN delta,
        not a fabricated (ypc_full - 0) delta."""
        pbp = _make_pbp(week=2)
        part = _make_participation(pbp.iloc[0], ol_count=5)
        pw = _make_player_weekly(weeks=(1, 2, 3))

        result = compute_ol_rb_features(
            pbp_df=pbp,
            participation_parsed_df=part,
            player_weekly_df=pw,
            target_season=2022,
            target_week=3,
        )
        assert not result.empty
        row = result[result["player_id"] == "RB-001"].iloc[0]
        assert pd.isna(row["rb_ypc_delta_backup_ol"]), (
            "Delta must be NaN when the backup-OL side was never observed, "
            "not fillna(0)-based fabricated value"
        )
        # The full-OL side itself should still be populated.
        assert row["rb_ypc_with_full_ol"] == pytest.approx(4.0)

    def test_nan_when_only_backup_ol_observed(self):
        """RB with only backup-OL (<5 starters) rushes should have NaN delta."""
        pbp = _make_pbp(week=2)
        part = _make_participation(pbp.iloc[0], ol_count=4)
        pw = _make_player_weekly(weeks=(1, 2, 3))

        result = compute_ol_rb_features(
            pbp_df=pbp,
            participation_parsed_df=part,
            player_weekly_df=pw,
            target_season=2022,
            target_week=3,
        )
        assert not result.empty
        row = result[result["player_id"] == "RB-001"].iloc[0]
        assert pd.isna(row["rb_ypc_delta_backup_ol"])

    def test_real_delta_when_both_sides_observed(self):
        """When both full-OL and backup-OL plays exist, delta should be the
        actual arithmetic difference, not NaN."""
        pbp_full = _make_pbp(week=2)
        pbp_full["play_id"] = 1.0
        pbp_full["yards_gained"] = 6.0
        pbp_backup = _make_pbp(week=2)
        pbp_backup["play_id"] = 2.0
        pbp_backup["yards_gained"] = 2.0
        pbp = pd.concat([pbp_full, pbp_backup], ignore_index=True)

        part_full = _make_participation(pbp_full.iloc[0], ol_count=5)
        part_backup = _make_participation(pbp_backup.iloc[0], ol_count=4)
        part = pd.concat([part_full, part_backup], ignore_index=True)

        pw = _make_player_weekly(weeks=(1, 2, 3))

        result = compute_ol_rb_features(
            pbp_df=pbp,
            participation_parsed_df=part,
            player_weekly_df=pw,
            target_season=2022,
            target_week=3,
        )
        row = result[result["player_id"] == "RB-001"].iloc[0]
        assert row["rb_ypc_delta_backup_ol"] == pytest.approx(6.0 - 2.0)
