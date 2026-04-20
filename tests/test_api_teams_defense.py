"""
Tests for the team defense-metrics API (/api/teams/{team}/defense-metrics).

Covers:
- Rating bounds [50, 99] on overall + every positional rank.
- Full positional coverage (QB/RB/WR/TE) regardless of raw data gaps.
- Real SOS data surfacing (def_sos_rank, def_sos_score) for a team-week that
  definitely exists in silver.
- Season-walk-back fallback (2026 -> latest available season).
- Week-walk-back fallback when the requested week has no rows.
- Unknown team rejection (ValueError / HTTP 404).
- Monotone rating-vs-rank contract (lower rank = higher rating).
- FastAPI endpoint integration (200 / 404 / 422 / fallback 200).
"""

import sys
from pathlib import Path

import pytest

# Ensure project root importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from web.api.main import app  # noqa: E402
from web.api.services import team_defense_service  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------


class TestLoadDefenseMetrics:
    def test_rating_bounds(self):
        """overall_def_rating and every positional rating must be within [50, 99]."""
        result = team_defense_service.load_defense_metrics("BUF", 2024, 5)
        assert (
            50 <= result["overall_def_rating"] <= 99
        ), f"overall rating out of [50,99]: {result['overall_def_rating']}"
        assert result["positional"], "positional must be non-empty"
        for entry in result["positional"]:
            assert (
                50 <= entry["rating"] <= 99
            ), f"{entry['position']} rating out of [50,99]: {entry['rating']}"

    def test_positional_coverage(self):
        """load_defense_metrics must always return all 4 positions (QB/RB/WR/TE)."""
        result = team_defense_service.load_defense_metrics("BUF", 2024, 5)
        positions = {p["position"] for p in result["positional"]}
        assert positions == {
            "QB",
            "RB",
            "WR",
            "TE",
        }, f"expected {{QB,RB,WR,TE}}, got {positions}"

    def test_real_sos_not_none(self):
        """For a team-week with clear silver data, SOS fields are populated."""
        result = team_defense_service.load_defense_metrics("BUF", 2024, 5)
        assert result["def_sos_score"] is not None
        assert result["def_sos_rank"] is not None
        assert 1 <= result["def_sos_rank"] <= 32
        assert result["adj_def_epa"] is not None

    def test_season_fallback_2026(self):
        """Requesting 2026 (absent) must fall back to latest available season."""
        result = team_defense_service.load_defense_metrics("BUF", 2026, 1)
        assert result["fallback"] is True
        assert result["fallback_season"] is not None
        assert result["fallback_season"] < 2026
        # Positional coverage still holds on fallback.
        assert {p["position"] for p in result["positional"]} == {
            "QB",
            "RB",
            "WR",
            "TE",
        }

    def test_week_fallback_to_season_average(self):
        """A week beyond the season's last played week must walk back, not 500."""
        # 2024 silver/defense/positional has weeks 1..22. Use 99 (synthetic).
        result = team_defense_service.load_defense_metrics("BUF", 2024, 99)
        assert result["source_week"] != 99
        assert 1 <= result["source_week"] <= 22
        # Positional ranks still valid ints (or None for truly missing positions).
        for p in result["positional"]:
            if p["rank"] is not None:
                assert isinstance(p["rank"], int)
                assert 1 <= p["rank"] <= 32

    def test_unknown_team_raises(self):
        with pytest.raises(ValueError):
            team_defense_service.load_defense_metrics("ZZZ", 2024, 5)

    def test_rating_monotone_with_rank(self):
        """Across teams in the same week, lower def_sos_rank must map to higher overall rating."""
        week_results = []
        # Sample 3 teams whose week=5 data definitely exists.
        for team in ("BUF", "KC", "CAR"):
            r = team_defense_service.load_defense_metrics(team, 2024, 5)
            week_results.append((team, r["def_sos_rank"], r["overall_def_rating"]))
        # Filter to teams with a real def_sos_rank
        with_rank = [(t, rank, rating) for t, rank, rating in week_results if rank]
        assert len(with_rank) >= 2, "need at least two teams with def_sos_rank"
        # Sort by rank ascending, check ratings are descending (monotone decreasing)
        with_rank.sort(key=lambda tup: tup[1])
        ratings = [rating for _, _, rating in with_rank]
        assert ratings == sorted(
            ratings, reverse=True
        ), f"ratings must decrease as rank increases: {with_rank}"


# ---------------------------------------------------------------------------
# FastAPI endpoint integration tests
# ---------------------------------------------------------------------------


class TestDefenseMetricsEndpoint:
    def test_endpoint_returns_200_with_positional(self):
        resp = client.get("/api/teams/BUF/defense-metrics?season=2024&week=5")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["team"] == "BUF"
        assert len(body["positional"]) == 4
        assert {p["position"] for p in body["positional"]} == {
            "QB",
            "RB",
            "WR",
            "TE",
        }
        for p in body["positional"]:
            assert 50 <= p["rating"] <= 99
        assert 50 <= body["overall_def_rating"] <= 99

    def test_endpoint_unknown_team_404(self):
        resp = client.get("/api/teams/ZZZ/defense-metrics?season=2024&week=5")
        assert resp.status_code == 404

    def test_endpoint_invalid_week_422(self):
        resp = client.get("/api/teams/BUF/defense-metrics?season=2024&week=99")
        assert resp.status_code == 422

    def test_endpoint_fallback_for_2026(self):
        """2026 silver/defense absent at execution time → fallback=true."""
        resp = client.get("/api/teams/BUF/defense-metrics?season=2026&week=1")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fallback"] is True
        assert body["fallback_season"] is not None
