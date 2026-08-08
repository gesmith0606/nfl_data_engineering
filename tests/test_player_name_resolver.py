"""Tests for PlayerNameResolver's index construction and source-priority sort.

Covers the regression where `_build_index` sorted the combined depth_chart /
roster / player_weekly rows by season using the default (unstable) quicksort,
which can reorder same-season rows across sources and break the documented
source-priority ordering (depth_charts > rosters > player_weekly) that
`drop_duplicates(keep="first")` relies on.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from player_name_resolver import PlayerNameResolver


def _write_parquet(path, df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)


@pytest.fixture
def bronze_root(tmp_path):
    """Build a minimal Bronze layer with the SAME player_id/season present
    in all three sources but with conflicting `team` values, so we can tell
    which source's row won the de-dup.
    """
    root = tmp_path / "bronze"

    depth_charts = pd.DataFrame(
        {
            "player_id": ["00-0099999"],
            "full_name": ["Test Player"],
            "football_name": ["Test"],
            "team": ["AAA"],
            "position": ["WR"],
            "season": [2024],
        }
    )
    rosters = pd.DataFrame(
        {
            "player_id": ["00-0099999"],
            "full_name": ["Test Player"],
            "football_name": ["Test"],
            "team": ["BBB"],
            "position": ["WR"],
            "season": [2024],
        }
    )
    player_weekly = pd.DataFrame(
        {
            "player_id": ["00-0099999"],
            "full_name": ["Test Player"],
            "football_name": ["Test"],
            "team": ["CCC"],
            "position": ["WR"],
            "season": [2024],
        }
    )

    _write_parquet(
        root / "depth_charts" / "season=2024" / "depth_charts_20240101.parquet",
        depth_charts,
    )
    _write_parquet(
        root / "players" / "rosters" / "season=2024" / "rosters_20240101.parquet",
        rosters,
    )
    _write_parquet(
        root / "players" / "weekly" / "season=2024" / "player_weekly_20240101.parquet",
        player_weekly,
    )
    return root


class TestSourcePriorityOrdering:
    """depth_charts must win over rosters/player_weekly for same-season ties."""

    def test_depth_chart_wins_same_season_conflict(self, bronze_root):
        resolver = PlayerNameResolver(bronze_root=bronze_root)
        entries = [e for e in resolver.index if e.player_id == "00-0099999"]
        assert len(entries) == 1, "de-dup should keep exactly one entry per player_id"
        assert entries[0].team == "AAA", (
            "depth_charts (highest priority source) should win the "
            "same-season conflict, but got team=%r" % entries[0].team
        )

    def test_sort_values_uses_stable_kind(self, bronze_root, monkeypatch):
        """Regression test pinned to the root cause: the season sort in
        _build_index must request a stable sort, not the default (unstable)
        quicksort, since ties in season carry meaningful source-priority
        ordering from the pre-sort concat order.
        """
        captured_kinds = []
        real_sort_values = pd.DataFrame.sort_values

        def spy_sort_values(self, *args, **kwargs):
            by = kwargs.get("by", args[0] if args else None)
            if by == "season":
                captured_kinds.append(kwargs.get("kind", "quicksort"))
            return real_sort_values(self, *args, **kwargs)

        monkeypatch.setattr(pd.DataFrame, "sort_values", spy_sort_values)

        PlayerNameResolver(bronze_root=bronze_root)

        assert captured_kinds, "expected a sort_values(by='season', ...) call"
        assert all(k == "stable" for k in captured_kinds), (
            f"season sort must use kind='stable' to preserve source-priority "
            f"ordering on ties; got kind values {captured_kinds}"
        )
