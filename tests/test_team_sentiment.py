"""
Tests for team-level sentiment aggregation.

Covers:
- Team name / abbreviation detection
- Aggregation of player signals by team
- Team sentiment multiplier clamping [0.95, 1.05]
- Empty / missing data graceful handling
- Full aggregate() pipeline with synthetic data
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_silver_signals(
    records: List[Dict],
    season: int = 2026,
    week: int = 1,
    base_dir: Path | None = None,
) -> Path:
    """Write Silver signal JSON files and return the base directory."""
    if base_dir is None:
        base_dir = Path(tempfile.mkdtemp())
    week_dir = base_dir / "data" / "silver" / "sentiment" / "signals" / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    out = week_dir / "signals_test.json"
    out.write_text(json.dumps({"records": records}), encoding="utf-8")
    return base_dir


def _make_gold_player_sentiment(
    rows: List[Dict],
    season: int = 2026,
    week: int = 1,
    base_dir: Path | None = None,
) -> Path:
    """Write Gold player sentiment Parquet and return the base directory."""
    if base_dir is None:
        base_dir = Path(tempfile.mkdtemp())
    gold_dir = base_dir / "data" / "gold" / "sentiment" / f"season={season}" / f"week={week:02d}"
    gold_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(gold_dir / "sentiment_multipliers_20260101_000000.parquet", index=False)
    return base_dir


# ---------------------------------------------------------------------------
# Tests: Team name detection
# ---------------------------------------------------------------------------


class TestTeamNameDetection:
    """Test the team name/abbreviation lookup dictionary."""

    def test_abbreviation_lookup(self) -> None:
        from src.sentiment.aggregation.team_weekly import TEAM_NAME_TO_ABBR

        assert TEAM_NAME_TO_ABBR["BAL"] == "BAL"
        assert TEAM_NAME_TO_ABBR["Ravens"] == "BAL"
        assert TEAM_NAME_TO_ABBR["Baltimore"] == "BAL"

    def test_all_32_teams_present(self) -> None:
        from src.sentiment.aggregation.team_weekly import TEAM_NAME_TO_ABBR

        # All 32 NFL team abbreviations must appear as values
        unique_teams = set(TEAM_NAME_TO_ABBR.values())
        assert len(unique_teams) == 32

    def test_detect_teams_in_text(self) -> None:
        from src.sentiment.aggregation.team_weekly import detect_teams_in_text

        text = "The Ravens are looking strong this week against the Bengals"
        teams = detect_teams_in_text(text)
        assert "BAL" in teams
        assert "CIN" in teams

    def test_word_boundary_avoids_false_positives(self) -> None:
        from src.sentiment.aggregation.team_weekly import detect_teams_in_text

        # "car" should NOT match "CAR" (Panthers)
        text = "He drove his car to the stadium"
        teams = detect_teams_in_text(text)
        assert "CAR" not in teams

    def test_case_insensitive_team_names(self) -> None:
        from src.sentiment.aggregation.team_weekly import detect_teams_in_text

        text = "the ravens and the chiefs are playing"
        teams = detect_teams_in_text(text)
        assert "BAL" in teams
        assert "KC" in teams


# ---------------------------------------------------------------------------
# Tests: Sentiment → team multiplier
# ---------------------------------------------------------------------------


class TestTeamSentimentMultiplier:
    """Test team sentiment score → multiplier conversion."""

    def test_neutral_score_gives_neutral_multiplier(self) -> None:
        from src.sentiment.aggregation.team_weekly import team_sentiment_to_multiplier

        assert team_sentiment_to_multiplier(0.0) == 1.0

    def test_max_positive_gives_1_05(self) -> None:
        from src.sentiment.aggregation.team_weekly import team_sentiment_to_multiplier

        assert team_sentiment_to_multiplier(1.0) == 1.05

    def test_max_negative_gives_0_95(self) -> None:
        from src.sentiment.aggregation.team_weekly import team_sentiment_to_multiplier

        assert team_sentiment_to_multiplier(-1.0) == 0.95

    def test_clamping_beyond_bounds(self) -> None:
        from src.sentiment.aggregation.team_weekly import team_sentiment_to_multiplier

        assert team_sentiment_to_multiplier(2.0) == 1.05
        assert team_sentiment_to_multiplier(-5.0) == 0.95

    def test_partial_sentiment(self) -> None:
        from src.sentiment.aggregation.team_weekly import team_sentiment_to_multiplier

        result = team_sentiment_to_multiplier(0.5)
        assert 1.0 < result <= 1.05


# ---------------------------------------------------------------------------
# Tests: Team aggregation
# ---------------------------------------------------------------------------


class TestTeamWeeklyAggregator:
    """Test the full TeamWeeklyAggregator pipeline."""

    def test_aggregate_with_player_data(self, tmp_path: Path) -> None:
        """Player Gold sentiment grouped by team produces team scores."""
        from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

        # Create player-level Gold sentiment
        player_rows = [
            {"player_id": "p1", "player_name": "Lamar Jackson", "team": "BAL",
             "sentiment_score_avg": 0.6, "sentiment_multiplier": 1.1, "doc_count": 3},
            {"player_id": "p2", "player_name": "Mark Andrews", "team": "BAL",
             "sentiment_score_avg": 0.2, "sentiment_multiplier": 1.03, "doc_count": 2},
            {"player_id": "p3", "player_name": "Joe Burrow", "team": "CIN",
             "sentiment_score_avg": -0.3, "sentiment_multiplier": 0.91, "doc_count": 1},
        ]
        base = _make_gold_player_sentiment(player_rows, base_dir=tmp_path)

        agg = TeamWeeklyAggregator(project_root=base)
        df = agg.aggregate(season=2026, week=1, dry_run=True)

        assert not df.empty
        assert "team" in df.columns
        assert "team_sentiment_score" in df.columns
        assert "team_sentiment_multiplier" in df.columns

        bal_row = df[df["team"] == "BAL"]
        assert len(bal_row) == 1
        assert 0.95 <= float(bal_row["team_sentiment_multiplier"].iloc[0]) <= 1.05

    def test_empty_data_returns_neutral(self, tmp_path: Path) -> None:
        """No player data should still return an empty DataFrame gracefully."""
        from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

        agg = TeamWeeklyAggregator(project_root=tmp_path)
        df = agg.aggregate(season=2026, week=1, dry_run=True)
        assert df.empty

    def test_output_columns(self, tmp_path: Path) -> None:
        """Check all expected columns are present."""
        from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

        player_rows = [
            {"player_id": "p1", "player_name": "Josh Allen", "team": "BUF",
             "sentiment_score_avg": 0.4, "sentiment_multiplier": 1.06, "doc_count": 2},
        ]
        base = _make_gold_player_sentiment(player_rows, base_dir=tmp_path)

        agg = TeamWeeklyAggregator(project_root=base)
        df = agg.aggregate(season=2026, week=1, dry_run=True)

        expected_cols = {
            "team", "season", "week", "team_sentiment_score",
            "team_sentiment_multiplier", "player_signal_count",
            "positive_count", "negative_count", "net_sentiment",
        }
        assert expected_cols.issubset(set(df.columns))

    def test_multiplier_always_in_range(self, tmp_path: Path) -> None:
        """Multiplier must always be in [0.95, 1.05] regardless of input."""
        from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

        # Extreme positive sentiment
        player_rows = [
            {"player_id": f"p{i}", "player_name": f"Player {i}", "team": "KC",
             "sentiment_score_avg": 1.0, "sentiment_multiplier": 1.15, "doc_count": 10}
            for i in range(10)
        ]
        base = _make_gold_player_sentiment(player_rows, base_dir=tmp_path)

        agg = TeamWeeklyAggregator(project_root=base)
        df = agg.aggregate(season=2026, week=1, dry_run=True)

        assert not df.empty
        for _, row in df.iterrows():
            assert 0.95 <= row["team_sentiment_multiplier"] <= 1.05

    def test_writes_parquet_when_not_dry_run(self, tmp_path: Path) -> None:
        """aggregate() should write Parquet file when dry_run=False."""
        from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator

        player_rows = [
            {"player_id": "p1", "player_name": "Jalen Hurts", "team": "PHI",
             "sentiment_score_avg": 0.1, "sentiment_multiplier": 1.02, "doc_count": 1},
        ]
        base = _make_gold_player_sentiment(player_rows, base_dir=tmp_path)

        agg = TeamWeeklyAggregator(project_root=base)
        df = agg.aggregate(season=2026, week=1, dry_run=False)

        # Check Parquet was written
        team_dir = base / "data" / "gold" / "sentiment" / "team_sentiment" / "season=2026" / "week=01"
        parquets = list(team_dir.glob("*.parquet"))
        assert len(parquets) == 1


# ---------------------------------------------------------------------------
# Tests: Edge adjustment
# ---------------------------------------------------------------------------


class TestSentimentEdgeAdjustment:
    """Test the apply_team_sentiment_adjustment function."""

    def test_adjustment_bounded(self) -> None:
        from src.sentiment.aggregation.team_weekly import apply_team_sentiment_adjustment

        predictions = pd.DataFrame({
            "home_team": ["BAL", "KC"],
            "away_team": ["CIN", "LV"],
            "spread_edge": [2.0, -1.0],
            "total_edge": [3.0, 0.5],
        })
        sentiment = pd.DataFrame({
            "team": ["BAL", "CIN", "KC", "LV"],
            "team_sentiment_multiplier": [1.05, 0.95, 1.02, 1.00],
        })

        result = apply_team_sentiment_adjustment(predictions, sentiment)

        # Adjustment must be <= 0.15 in absolute value
        assert all(abs(result["sentiment_adjustment"]) <= 0.15 + 1e-9)

    def test_no_sentiment_data_no_change(self) -> None:
        from src.sentiment.aggregation.team_weekly import apply_team_sentiment_adjustment

        predictions = pd.DataFrame({
            "home_team": ["BAL"],
            "away_team": ["CIN"],
            "spread_edge": [2.0],
            "total_edge": [3.0],
        })
        sentiment = pd.DataFrame(columns=["team", "team_sentiment_multiplier"])

        result = apply_team_sentiment_adjustment(predictions, sentiment)
        assert result["sentiment_adjustment"].iloc[0] == 0.0
        assert result["adjusted_spread_edge"].iloc[0] == 2.0

    def test_positive_home_sentiment_adjusts_spread(self) -> None:
        from src.sentiment.aggregation.team_weekly import apply_team_sentiment_adjustment

        predictions = pd.DataFrame({
            "home_team": ["BAL"],
            "away_team": ["CIN"],
            "spread_edge": [0.0],
            "total_edge": [0.0],
        })
        # Home team very positive, away team neutral
        sentiment = pd.DataFrame({
            "team": ["BAL", "CIN"],
            "team_sentiment_multiplier": [1.05, 1.00],
        })

        result = apply_team_sentiment_adjustment(predictions, sentiment)
        # Positive home sentiment -> positive adjustment
        assert result["sentiment_adjustment"].iloc[0] > 0

    def test_columns_added(self) -> None:
        from src.sentiment.aggregation.team_weekly import apply_team_sentiment_adjustment

        predictions = pd.DataFrame({
            "home_team": ["BAL"],
            "away_team": ["CIN"],
            "spread_edge": [1.0],
            "total_edge": [2.0],
        })
        sentiment = pd.DataFrame({
            "team": ["BAL", "CIN"],
            "team_sentiment_multiplier": [1.02, 0.98],
        })

        result = apply_team_sentiment_adjustment(predictions, sentiment)
        assert "home_sentiment" in result.columns
        assert "away_sentiment" in result.columns
        assert "sentiment_adjustment" in result.columns
        assert "adjusted_spread_edge" in result.columns
