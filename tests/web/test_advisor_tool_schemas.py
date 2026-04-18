"""Advisor tool schema contract tests (plan 63-02).

These tests encode the contract between the FastAPI backend and the
``web/frontend/src/app/api/chat/route.ts`` AI advisor tool schemas.

Every failure flagged in TOOL-AUDIT.md is covered here so a future schema
drift fails fast in CI instead of silently breaking the advisor widget.

The two fixes landed by 63-02:

* ``getDraftBoard`` — backend now exposes the available-player list under the
  ``board`` key (alongside the legacy ``players`` key). Each board entry
  carries the advisor-facing fields ``adp``, ``bye_week``, ``value_tier``.

* ``getSentimentSummary`` — backend now emits ``total_articles``,
  ``bullish_players``, ``bearish_players``, ``average_sentiment`` (alongside
  the existing ``total_docs``, ``top_positive``, ``top_negative``) and
  reshapes ``sources`` into the advisor-friendly
  ``[{source, count}]`` array.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
from typing import Any, Dict

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Ensure project root is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from web.api.main import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_draft_projections() -> pd.DataFrame:
    """Synthetic projection DataFrame with the columns draft_optimizer needs."""
    rows = [
        ("P001", "Patrick Mahomes", "QB", "KC", 380.0, 7),
        ("P002", "Josh Allen", "QB", "BUF", 370.0, 12),
        ("P003", "Jalen Hurts", "QB", "PHI", 350.0, 5),
        ("P004", "Christian McCaffrey", "RB", "SF", 320.0, 9),
        ("P005", "Breece Hall", "RB", "NYJ", 280.0, 12),
        ("P006", "Bijan Robinson", "RB", "ATL", 275.0, 12),
        ("P007", "Jahmyr Gibbs", "RB", "DET", 260.0, 5),
        ("P008", "Ja'Marr Chase", "WR", "CIN", 300.0, 12),
        ("P009", "Tyreek Hill", "WR", "MIA", 290.0, 6),
        ("P010", "Justin Jefferson", "WR", "MIN", 285.0, 6),
        ("P011", "CeeDee Lamb", "WR", "DAL", 280.0, 7),
        ("P012", "A.J. Brown", "WR", "PHI", 270.0, 5),
        ("P013", "Amon-Ra St. Brown", "WR", "DET", 265.0, 5),
        ("P014", "Travis Kelce", "TE", "KC", 230.0, 7),
        ("P015", "Sam LaPorta", "TE", "DET", 180.0, 5),
        ("P016", "Mark Andrews", "TE", "BAL", 175.0, 14),
        ("P017", "Saquon Barkley", "RB", "PHI", 255.0, 5),
        ("P018", "Derrick Henry", "RB", "BAL", 245.0, 14),
        ("P019", "De'Von Achane", "RB", "MIA", 240.0, 6),
        ("P020", "Puka Nacua", "WR", "LAR", 260.0, 6),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "player_id",
            "player_name",
            "position",
            "recent_team",
            "projected_season_points",
            "bye_week",
        ],
    )
    df["season"] = 2026
    df["projected_points"] = df["projected_season_points"]
    return df


def _mock_load_draft_data(scoring: str, season: int) -> pd.DataFrame:
    """Patch target for ``web.api.routers.draft._load_draft_data``."""
    from draft_optimizer import compute_value_scores

    return compute_value_scores(_make_mock_projections_padded())


def _make_mock_projections_padded() -> pd.DataFrame:
    """60-row projection DataFrame — enough to satisfy any ≥50 assertion."""
    base = _make_mock_draft_projections()
    # Replicate QB/RB/WR/TE rows with suffixed ids so the draft board has ≥50
    extra = []
    for i in range(4):
        for _, row in base.iterrows():
            new = row.to_dict()
            new["player_id"] = f"{new['player_id']}_{i}"
            new["player_name"] = f"{new['player_name']}_{i}"
            new["projected_season_points"] = float(
                new["projected_season_points"]
            ) * (0.9 - 0.05 * i)
            new["projected_points"] = new["projected_season_points"]
            extra.append(new)
    padded = pd.concat([base, pd.DataFrame(extra)], ignore_index=True)
    return padded


# ---------------------------------------------------------------------------
# getDraftBoard — schema contract
# ---------------------------------------------------------------------------


class TestDraftBoardSchema:
    """Encodes the advisor-tool contract for ``GET /api/draft/board``."""

    def test_board_key_is_present_and_populated(self) -> None:
        """Response MUST carry a ``board`` array (advisor-facing alias)."""
        with patch(
            "web.api.routers.draft._load_draft_data",
            side_effect=_mock_load_draft_data,
        ):
            resp = client.get("/api/draft/board", params={"scoring": "half_ppr"})
        assert resp.status_code == 200
        body = resp.json()
        assert "board" in body, "advisor contract requires top-level 'board' key"
        assert isinstance(body["board"], list)
        assert len(body["board"]) > 0

    def test_board_and_players_both_present_for_backward_compat(self) -> None:
        """``players`` (draft page) and ``board`` (advisor) both present.

        The draft page at ``web/frontend/src/features/draft/components/draft-tool-view.tsx``
        destructures ``data.players``; the advisor tool destructures ``data.board``.
        Both must work off the same response.
        """
        with patch(
            "web.api.routers.draft._load_draft_data",
            side_effect=_mock_load_draft_data,
        ):
            resp = client.get("/api/draft/board", params={"scoring": "half_ppr"})
        assert resp.status_code == 200
        body = resp.json()
        assert "players" in body, "draft page still consumes 'players'"
        assert "board" in body, "advisor consumes 'board'"
        assert len(body["board"]) == len(body["players"])

    def test_board_entry_fields_match_advisor_schema(self) -> None:
        """Each ``board`` entry carries the advisor-expected fields.

        Advisor schema (web/frontend/src/app/api/chat/route.ts, line 705-715):
            { player_name, player_id, team, position, adp, projected_points,
              vorp, value_tier, bye_week }
        """
        with patch(
            "web.api.routers.draft._load_draft_data",
            side_effect=_mock_load_draft_data,
        ):
            resp = client.get("/api/draft/board", params={"scoring": "half_ppr"})
        assert resp.status_code == 200
        entry = resp.json()["board"][0]

        required = {
            "player_name",
            "player_id",
            "team",
            "position",
            "adp",
            "projected_points",
            "vorp",
            "value_tier",
            "bye_week",
        }
        missing = required - set(entry.keys())
        assert not missing, f"board entry missing advisor fields: {missing}"

        # Type sanity
        assert isinstance(entry["player_name"], str)
        assert isinstance(entry["player_id"], str)
        assert isinstance(entry["position"], str)
        # adp + bye_week may be None when ADP file is absent / unknown player
        assert entry["adp"] is None or isinstance(entry["adp"], (int, float))
        assert entry["bye_week"] is None or isinstance(entry["bye_week"], int)
        assert isinstance(entry["projected_points"], (int, float))
        assert isinstance(entry["vorp"], (int, float))
        assert isinstance(entry["value_tier"], str)


# ---------------------------------------------------------------------------
# getSentimentSummary — schema contract
# ---------------------------------------------------------------------------


def _mock_gold_sentiment_df() -> pd.DataFrame:
    """Synthetic Gold sentiment DataFrame for ``news/summary`` tests."""
    return pd.DataFrame(
        {
            "player_id": [f"00-{i:05d}" for i in range(10)],
            "player_name": [f"Player {i}" for i in range(10)],
            "team": ["KC", "BUF", "SF", "DAL", "PHI", "CIN", "MIA", "DET", "BAL", "GB"],
            "sentiment_multiplier": [1.20, 1.15, 1.05, 1.00, 1.00, 0.98, 0.85, 0.80, 0.70, 1.25],
            "sentiment_score_avg": [0.6, 0.4, 0.2, 0.0, -0.05, -0.2, -0.3, -0.5, -0.7, 0.8],
            "doc_count": [15, 10, 8, 6, 5, 4, 7, 9, 12, 20],
            "rss_doc_count": [10, 6, 5, 3, 3, 2, 4, 5, 8, 12],
            "sleeper_doc_count": [5, 4, 3, 3, 2, 2, 3, 4, 4, 8],
            "is_ruled_out": [False] * 10,
            "is_inactive": [False] * 10,
            "is_questionable": [False] * 10,
            "is_suspended": [False] * 10,
            "is_returning": [False] * 10,
            "latest_signal_at": ["2026-04-10T12:00:00Z"] * 10,
        }
    )


class TestSentimentSummarySchema:
    """Encodes advisor-tool contract for ``GET /api/news/summary``."""

    def test_advisor_fields_present_when_data_exists(self) -> None:
        """Response MUST include advisor-facing keys.

        Advisor schema (web/frontend/src/app/api/chat/route.ts, line 821-827):
            { total_articles, sources, bullish_players, bearish_players,
              average_sentiment }
        """
        with patch(
            "web.api.services.news_service._load_gold_sentiment",
            return_value=_mock_gold_sentiment_df(),
        ):
            resp = client.get(
                "/api/news/summary", params={"season": 2026, "week": 1}
            )
        assert resp.status_code == 200
        body = resp.json()

        required = {
            "total_articles",
            "sources",
            "bullish_players",
            "bearish_players",
            "average_sentiment",
        }
        missing = required - set(body.keys())
        assert not missing, f"summary missing advisor fields: {missing}"

        # Advisor expects sources as a list of {source, count}
        assert isinstance(body["sources"], list), "sources must be a list for advisor"
        for entry in body["sources"]:
            assert isinstance(entry, dict)
            assert "source" in entry
            assert "count" in entry

        # bullish/bearish must be lists of {player_name, team, sentiment_score}
        assert isinstance(body["bullish_players"], list)
        assert isinstance(body["bearish_players"], list)
        for p in body["bullish_players"] + body["bearish_players"]:
            assert "player_name" in p
            assert "team" in p
            assert "sentiment_score" in p

        # Numeric sanity
        assert isinstance(body["total_articles"], int)
        assert isinstance(body["average_sentiment"], (int, float))

    def test_legacy_fields_still_present(self) -> None:
        """``total_docs``, ``top_positive``, ``top_negative`` preserved for news-feed."""
        with patch(
            "web.api.services.news_service._load_gold_sentiment",
            return_value=_mock_gold_sentiment_df(),
        ):
            resp = client.get(
                "/api/news/summary", params={"season": 2026, "week": 1}
            )
        assert resp.status_code == 200
        body = resp.json()
        for legacy_key in (
            "total_docs",
            "top_positive",
            "top_negative",
            "total_players",
            "sentiment_distribution",
        ):
            assert legacy_key in body, (
                f"legacy key '{legacy_key}' removed — breaks news-feed.tsx"
            )

    def test_empty_data_returns_zero_envelope(self) -> None:
        """When no Gold sentiment data exists, envelope is zero-shaped, not 500."""
        with patch(
            "web.api.services.news_service._load_gold_sentiment",
            return_value=pd.DataFrame(),
        ):
            resp = client.get(
                "/api/news/summary", params={"season": 2026, "week": 1}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_articles"] == 0
        assert body["bullish_players"] == []
        assert body["bearish_players"] == []
        assert body["sources"] == []
        assert body["average_sentiment"] == 0
        # Legacy keys still zero
        assert body["total_docs"] == 0
        assert body["top_positive"] == []
        assert body["top_negative"] == []

    def test_bullish_bearish_ordering(self) -> None:
        """Most bullish players come first; most bearish come first in their list."""
        with patch(
            "web.api.services.news_service._load_gold_sentiment",
            return_value=_mock_gold_sentiment_df(),
        ):
            resp = client.get(
                "/api/news/summary", params={"season": 2026, "week": 1}
            )
        body = resp.json()
        bullish = body["bullish_players"]
        bearish = body["bearish_players"]
        assert len(bullish) > 0
        assert len(bearish) > 0
        # Bullish descending by sentiment_score
        for prev, curr in zip(bullish, bullish[1:]):
            assert prev["sentiment_score"] >= curr["sentiment_score"]
        # Bearish ascending by sentiment_score
        for prev, curr in zip(bearish, bearish[1:]):
            assert prev["sentiment_score"] <= curr["sentiment_score"]

    def test_sources_array_has_expected_entries(self) -> None:
        """``sources`` array lists each source with its doc count."""
        with patch(
            "web.api.services.news_service._load_gold_sentiment",
            return_value=_mock_gold_sentiment_df(),
        ):
            resp = client.get(
                "/api/news/summary", params={"season": 2026, "week": 1}
            )
        body = resp.json()
        source_names = {s["source"] for s in body["sources"]}
        # rss + sleeper appear in the mock
        assert "rss" in source_names
        assert "sleeper" in source_names
        # Counts match the mock DataFrame sums
        by_name: Dict[str, int] = {s["source"]: s["count"] for s in body["sources"]}
        assert by_name["rss"] == 58  # sum of rss_doc_count in mock
        assert by_name["sleeper"] == 38  # sum of sleeper_doc_count in mock
