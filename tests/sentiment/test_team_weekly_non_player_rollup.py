"""Tests for TeamWeeklyAggregator EVT-02 non-player rollup (Phase 72)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.sentiment.aggregation.team_weekly import TeamWeeklyAggregator


@pytest.fixture
def hermetic_root(tmp_path):
    """Set up a tmp_path tree mirroring the project's data layout."""
    (tmp_path / "data" / "gold" / "sentiment").mkdir(parents=True)
    (tmp_path / "data" / "gold" / "sentiment" / "team_sentiment").mkdir(parents=True)
    (tmp_path / "data" / "silver" / "sentiment" / "non_player_pending").mkdir(parents=True)
    return tmp_path


def _write_player_gold(root: Path, season: int, week: int, players: list) -> Path:
    week_dir = root / "data" / "gold" / "sentiment" / f"season={season}" / f"week={week:02d}"
    week_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(players)
    out = week_dir / "player_sentiment.parquet"
    df.to_parquet(out, index=False)
    return out


def _write_non_player_silver(
    root: Path, season: int, week: int, items: list, name: str
) -> Path:
    week_dir = (
        root / "data" / "silver" / "sentiment" / "non_player_pending"
        / f"season={season}" / f"week={week:02d}"
    )
    week_dir.mkdir(parents=True, exist_ok=True)
    out = week_dir / name
    out.write_text(json.dumps({"items": items}), encoding="utf-8")
    return out


class TestNonPlayerRollup:
    def test_coach_team_counts_aggregate(self, hermetic_root):
        """3 coach + 2 team + 1 reporter → KC row has coach=3, team=2 (reporter excluded)."""
        _write_player_gold(
            hermetic_root, 2025, 17,
            [
                {"player_id": "00-001", "team": "KC", "sentiment_score_avg": 0.5},
                {"player_id": "00-002", "team": "KC", "sentiment_score_avg": 0.3},
                {"player_id": "00-003", "team": "DAL", "sentiment_score_avg": -0.2},
            ],
        )

        items = [
            {"team_abbr": "KC", "subject_type": "coach", "summary": "Reid extension"},
            {"team_abbr": "KC", "subject_type": "coach", "summary": "OC departure"},
            {"team_abbr": "KC", "subject_type": "coach", "summary": "DC hire"},
            {"team_abbr": "KC", "subject_type": "team", "summary": "Schedule release"},
            {"team_abbr": "KC", "subject_type": "team", "summary": "Stadium news"},
            {"team_abbr": "KC", "subject_type": "reporter", "summary": "Schefter scoop"},
            {"team_abbr": "DAL", "subject_type": "coach", "summary": "McCarthy"},
        ]
        _write_non_player_silver(hermetic_root, 2025, 17, items, "items.json")

        agg = TeamWeeklyAggregator(project_root=hermetic_root)
        df = agg.aggregate(season=2025, week=17, dry_run=True)

        kc_row = df[df["team"] == "KC"].iloc[0]
        assert kc_row["coach_news_count"] == 3
        assert kc_row["team_news_count"] == 2
        assert kc_row["staff_news_count"] == 0

        dal_row = df[df["team"] == "DAL"].iloc[0]
        assert dal_row["coach_news_count"] == 1
        assert dal_row["team_news_count"] == 0

    def test_no_non_player_data_zero_counts(self, hermetic_root):
        """No non_player_pending data → all rollup counts 0."""
        _write_player_gold(
            hermetic_root, 2025, 18,
            [{"player_id": "00-001", "team": "KC", "sentiment_score_avg": 0.5}],
        )

        agg = TeamWeeklyAggregator(project_root=hermetic_root)
        df = agg.aggregate(season=2025, week=18, dry_run=True)

        kc_row = df[df["team"] == "KC"].iloc[0]
        assert kc_row["coach_news_count"] == 0
        assert kc_row["team_news_count"] == 0
        assert kc_row["staff_news_count"] == 0

    def test_reporter_items_never_counted_in_team_rollup(self, hermetic_root):
        """A team with ONLY reporter items has all rollup counts = 0."""
        _write_player_gold(
            hermetic_root, 2025, 17,
            [{"player_id": "00-001", "team": "PHI", "sentiment_score_avg": 0.4}],
        )

        items = [
            {"team_abbr": "PHI", "subject_type": "reporter", "summary": "byline"},
            {"team_abbr": "PHI", "subject_type": "reporter", "summary": "byline2"},
        ]
        _write_non_player_silver(hermetic_root, 2025, 17, items, "items.json")

        agg = TeamWeeklyAggregator(project_root=hermetic_root)
        df = agg.aggregate(season=2025, week=17, dry_run=True)

        phi_row = df[df["team"] == "PHI"].iloc[0]
        assert phi_row["coach_news_count"] == 0
        assert phi_row["team_news_count"] == 0
