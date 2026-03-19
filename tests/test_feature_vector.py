#!/usr/bin/env python3
"""Integration tests for full prediction feature vector assembly.

Validates that all Silver sources join cleanly into a complete feature vector,
checks null policy (Week 1 rolling NaN allowed, core cols non-null for weeks 2+),
and spot-checks standings against known 2023 NFL results.
"""

import glob
import os
import sys

import numpy as np
import pandas as pd
import pytest

# Project src/ on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "silver")

# Silver sources and their subdirectories
SILVER_SOURCES = {
    "pbp_metrics": "teams/pbp_metrics",
    "tendencies": "teams/tendencies",
    "sos": "teams/sos",
    "situational": "teams/situational",
    "pbp_derived": "teams/pbp_derived",
    "game_context": "teams/game_context",
    "referee_tendencies": "teams/referee_tendencies",
    "playoff_context": "teams/playoff_context",
}


def _read_latest_local(subdir: str, season: int) -> pd.DataFrame:
    """Read the latest Silver parquet file for a given subdirectory and season.

    Args:
        subdir: Relative path under data/silver/ (e.g. 'teams/pbp_metrics').
        season: NFL season year.

    Returns:
        DataFrame from latest parquet file, or empty DataFrame if not found.
    """
    pattern = os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _assemble_feature_vector(season: int) -> pd.DataFrame:
    """Assemble the full prediction feature vector from all Silver sources.

    Reads all Silver sources for the given season and left-joins them
    on [team, season, week]. Drops duplicate columns from joins.

    Args:
        season: NFL season year.

    Returns:
        Assembled DataFrame with all Silver features joined.
    """
    base = None
    for name, subdir in SILVER_SOURCES.items():
        df = _read_latest_local(subdir, season)
        if df.empty:
            continue
        if base is None:
            base = df
        else:
            base = base.merge(
                df, on=["team", "season", "week"], how="left",
                suffixes=("", f"_{name}"),
            )
            # Drop duplicate columns from join
            dup_cols = [c for c in base.columns if c.endswith(f"_{name}")]
            base = base.drop(columns=dup_cols)
    return base if base is not None else pd.DataFrame()


def _all_sources_available(season: int) -> bool:
    """Check if all Silver sources have data for the given season."""
    for subdir in SILVER_SOURCES.values():
        pattern = os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet")
        if not glob.glob(pattern):
            return False
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFeatureVectorAssembly:
    """Test full prediction feature vector from all Silver sources."""

    @pytest.fixture(autouse=True)
    def _skip_if_data_missing(self):
        """Skip tests if Silver data is not available."""
        if not _all_sources_available(2024):
            pytest.skip("Silver data for 2024 not available locally")

    def test_feature_vector_assembly(self):
        """Assembled feature vector has >= 300 columns, 32 teams, 500+ rows."""
        fv = _assemble_feature_vector(2024)
        actual_cols = len(fv.columns)
        print(f"Actual column count: {actual_cols}")
        assert actual_cols >= 300, (
            f"Expected >= 300 columns after join, got {actual_cols}"
        )
        assert fv["team"].nunique() == 32, (
            f"Expected 32 teams, got {fv['team'].nunique()}"
        )
        assert len(fv) >= 500, (
            f"Expected >= 500 rows (32 teams x ~17 weeks), got {len(fv)}"
        )

    def test_feature_vector_null_policy(self):
        """Core columns non-null for week >= 2; Week 1 allows rolling NaN."""
        fv = _assemble_feature_vector(2024)

        # Core columns must be non-null for weeks 2+
        core_cols = ["wins", "losses", "win_pct", "off_epa_per_play", "off_penalties"]
        wk2_plus = fv[fv["week"] >= 2]
        for col in core_cols:
            null_count = wk2_plus[col].isna().sum()
            assert null_count == 0, (
                f"Expected zero nulls in {col} for week >= 2, got {null_count}"
            )

        # Week 1: ref_penalties_per_game should be NaN (shift(1) with no prior)
        wk1 = fv[fv["week"] == 1]
        assert wk1["ref_penalties_per_game"].isna().all(), (
            "Expected all NaN for ref_penalties_per_game in Week 1"
        )

        # Week 1: wins should be 0 (entering-game record before any games)
        assert (wk1["wins"] == 0).all(), (
            "Expected wins == 0 for all teams in Week 1"
        )


class TestStandingsSpotCheck:
    """Spot-check standings against known NFL results."""

    def test_standings_spot_check_2023(self):
        """2023 final-week standings: BAL, KC, SF entering Week 18."""
        df = _read_latest_local("teams/playoff_context", 2023)
        if df.empty:
            pytest.skip("No 2023 playoff_context data")

        # Get entering-week-18 standings (shift(1) means these are after 16 games)
        wk18 = df[df["week"] == 18]

        # BAL: 13-4 final -> entering week 18: 13 wins, 3 losses
        bal = wk18[wk18["team"] == "BAL"]
        assert len(bal) == 1, "Expected 1 BAL row at week 18"
        assert bal["wins"].values[0] >= 12, (
            f"Expected BAL wins >= 12 entering week 18, got {bal['wins'].values[0]}"
        )

        # KC: 11-6 final -> entering week 18: 10 wins, 6 losses
        kc = wk18[wk18["team"] == "KC"]
        assert len(kc) == 1, "Expected 1 KC row at week 18"
        assert kc["wins"].values[0] >= 9, (
            f"Expected KC wins >= 9 entering week 18, got {kc['wins'].values[0]}"
        )

        # SF: 12-5 final -> entering week 18: 12 wins, 4 losses
        sf = wk18[wk18["team"] == "SF"]
        assert len(sf) == 1, "Expected 1 SF row at week 18"
        assert sf["wins"].values[0] >= 11, (
            f"Expected SF wins >= 11 entering week 18, got {sf['wins'].values[0]}"
        )

    def test_standings_spot_check_2024(self):
        """2024 standings have 32 teams with reasonable win totals."""
        df = _read_latest_local("teams/playoff_context", 2024)
        if df.empty:
            pytest.skip("No 2024 playoff_context data")

        # Basic sanity: 32 teams, reasonable row count
        assert df["team"].nunique() == 32
        assert len(df) >= 500  # 32 teams x ~17 weeks

        # Final week: at least some teams have wins >= 10
        max_week = df["week"].max()
        final = df[df["week"] == max_week]
        assert final["wins"].max() >= 10, (
            f"Expected at least one team with 10+ wins at week {max_week}"
        )


class TestRefereeTendencies:
    """Validate referee tendencies Silver data."""

    def test_referee_data_populated(self):
        """2024 referee tendencies has reasonable row count and non-null values."""
        df = _read_latest_local("teams/referee_tendencies", 2024)
        if df.empty:
            pytest.skip("No 2024 referee_tendencies data")

        # Should have ~570 rows (32 teams x ~17-18 weeks including playoffs)
        assert len(df) >= 500, (
            f"Expected >= 500 rows, got {len(df)}"
        )
        assert df["team"].nunique() == 32

        # After Week 1, ref_penalties_per_game should have non-null values
        wk2_plus = df[df["week"] >= 2]
        non_null_pct = wk2_plus["ref_penalties_per_game"].notna().mean()
        assert non_null_pct >= 0.9, (
            f"Expected >= 90% non-null ref_penalties_per_game for weeks 2+, "
            f"got {non_null_pct:.1%}"
        )
