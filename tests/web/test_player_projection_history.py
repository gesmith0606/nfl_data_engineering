"""Tests for GET /api/players/{player_id}/projection-history.

Projected points are read from real (temp) Gold weekly-projection Parquet
files -- following the ``silver_fixture`` pattern in
``test_projections_comparison.py`` -- since the merge/scan logic in
``projection_service.get_player_projection_weeks`` is new code that reads
Parquet directly. Actual points are supplied by monkeypatching
``projection_service.get_player_game_log`` (bound from ``game_archive`` at
import time), mirroring how ``test_lineups_projection_fallback.py``
monkeypatches a service-level function rather than faking Bronze Parquet on
disk -- game_archive's own Parquet-reading behavior is already covered by
``tests/test_game_archive.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from web.api.main import app  # noqa: E402
from web.api.services import projection_service  # noqa: E402

client = TestClient(app)

PLAYER_ID = "00-0033873"


def _write_week_projection(
    gold_dir: Path,
    season: int,
    week: int,
    scoring: str,
    player_id: str = PLAYER_ID,
    projected_points: float = 20.0,
    projected_floor: float = 12.0,
    projected_ceiling: float = 28.0,
) -> None:
    """Write a single-player Gold projection parquet for one week."""
    week_dir = gold_dir / f"season={season}" / f"week={week}"
    week_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "player_name": "Patrick Mahomes",
                "team": "KC",
                "position": "QB",
                "projected_points": projected_points,
                "projected_floor": projected_floor,
                "projected_ceiling": projected_ceiling,
            }
        ]
    )
    df.to_parquet(week_dir / f"projections_{scoring}_20260101_000000.parquet", index=False)


def _actuals_df(weeks_points: dict) -> pd.DataFrame:
    """Build a game_archive.get_player_game_log-shaped DataFrame."""
    if not weeks_points:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "week": wk,
                "opponent": "BAL",
                "home_away": "home",
                "fantasy_points": pts,
                "game_result": "W",
                "passing_yards": 250.0,
                "passing_tds": 2.0,
                "rushing_yards": 20.0,
                "rushing_tds": 0.0,
                "receptions": None,
                "receiving_yards": None,
                "receiving_tds": None,
                "targets": None,
                "carries": 3.0,
            }
            for wk, pts in weeks_points.items()
        ]
    )


@pytest.fixture
def gold_dir(tmp_path, monkeypatch):
    root = tmp_path / "gold" / "projections"
    monkeypatch.setattr(projection_service, "GOLD_PROJECTIONS_DIR", root)
    return root


def test_happy_path_both_sides_present(gold_dir, monkeypatch):
    """Weeks 1-2 have both a projection and an actual -- values line up."""
    _write_week_projection(gold_dir, 2025, 1, "half_ppr", projected_points=22.5)
    _write_week_projection(gold_dir, 2025, 2, "half_ppr", projected_points=19.0)

    monkeypatch.setattr(
        projection_service,
        "get_player_game_log",
        lambda player_id, season, scoring: _actuals_df({1: 24.1, 2: 15.3}),
    )

    resp = client.get(
        f"/api/players/{PLAYER_ID}/projection-history",
        params={"season": 2025, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["player_id"] == PLAYER_ID
    assert data["player_name"] == "Patrick Mahomes"
    assert data["team"] == "KC"
    assert data["position"] == "QB"
    assert data["season"] == 2025
    assert data["scoring_format"] == "half_ppr"
    assert data["reason"] is None
    assert len(data["weeks"]) == 2

    wk1 = next(w for w in data["weeks"] if w["week"] == 1)
    assert wk1["projected_points"] == 22.5
    assert wk1["actual_points"] == 24.1
    assert wk1["projected_floor"] == 12.0
    assert wk1["projected_ceiling"] == 28.0

    wk2 = next(w for w in data["weeks"] if w["week"] == 2)
    assert wk2["projected_points"] == 19.0
    assert wk2["actual_points"] == 15.3


def test_actuals_only_week(gold_dir, monkeypatch):
    """A week with an actual but no archived projection is included with a
    null projected_points -- the frontend decides how to render the gap."""
    _write_week_projection(gold_dir, 2025, 1, "half_ppr", projected_points=22.5)
    # Week 2 has an actual but the Gold pipeline never published a week=2
    # projection dir for this season (no _write_week_projection call).

    monkeypatch.setattr(
        projection_service,
        "get_player_game_log",
        lambda player_id, season, scoring: _actuals_df({1: 24.1, 2: 15.3}),
    )

    resp = client.get(
        f"/api/players/{PLAYER_ID}/projection-history",
        params={"season": 2025, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["weeks"]) == 2

    wk2 = next(w for w in data["weeks"] if w["week"] == 2)
    assert wk2["projected_points"] is None
    assert wk2["projected_floor"] is None
    assert wk2["projected_ceiling"] is None
    assert wk2["actual_points"] == 15.3


def test_empty_season_returns_200_with_reason(gold_dir, monkeypatch):
    """No archived projections dir and no Bronze actuals -> 200, weeks=[],
    reason set (mirrors the fail-open D-06 pattern used by the projections
    comparison endpoint for a never-ingested slice)."""
    # gold_dir fixture creates an empty root; no season=2025 subdir written.

    def _raise_not_found(player_id, season, scoring):
        raise FileNotFoundError(f"No player weekly data for season={season}.")

    monkeypatch.setattr(projection_service, "get_player_game_log", _raise_not_found)

    resp = client.get(
        f"/api/players/{PLAYER_ID}/projection-history",
        params={"season": 2025, "scoring": "half_ppr"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["weeks"] == []
    assert data["reason"] is not None
    assert "2025" in data["reason"]


def test_unknown_player_404(gold_dir, monkeypatch):
    """Season has archived data for someone, but not this player_id."""
    _write_week_projection(
        gold_dir, 2025, 1, "half_ppr", player_id="00-9999999"
    )

    monkeypatch.setattr(
        projection_service,
        "get_player_game_log",
        lambda player_id, season, scoring: pd.DataFrame(),
    )

    resp = client.get(
        f"/api/players/{PLAYER_ID}/projection-history",
        params={"season": 2025, "scoring": "half_ppr"},
    )
    assert resp.status_code == 404


def test_invalid_scoring_format_400(gold_dir):
    resp = client.get(
        f"/api/players/{PLAYER_ID}/projection-history",
        params={"season": 2025, "scoring": "bogus"},
    )
    assert resp.status_code == 400


def test_season_out_of_range_422(gold_dir):
    """Season below actuals coverage (< 2016) is rejected at the query-param
    level, same convention as /api/games/player-log/{id}."""
    resp = client.get(
        f"/api/players/{PLAYER_ID}/projection-history",
        params={"season": 2010, "scoring": "half_ppr"},
    )
    assert resp.status_code == 422
