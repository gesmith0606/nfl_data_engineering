"""Regression tests: /api/lineups must source projections via the projection
service, not a direct weekly-parquet read.

2026-07-02 incident: the Lineups tab rendered rosters with every
``projected_points`` null on the deployed backend. ``lineup_builder``'s
default ``_load_projections`` reads ``data/gold/projections/season=S/week=W``
from local disk — a path that does not exist in deployments where only the
committed preseason parquet is present (HF Spaces bridge). The projections
endpoint worked because ``projection_service`` has a preseason/staleness
fallback; lineups did not use it.

The fix routes the lineups endpoint's projection load through
``projection_service.get_projections`` and passes the DataFrame into
``get_team_lineup_with_projections(projections_df=...)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import lineup_builder  # noqa: E402
from web.api.main import app  # noqa: E402
from web.api.services import projection_service  # noqa: E402

client = TestClient(app)


def _fake_starters() -> pd.DataFrame:
    """Minimal starters frame matching get_team_starters' output schema."""
    return pd.DataFrame(
        [
            {
                "team": "KC",
                "side": "offense",
                "position": "QB",
                "position_group": "QB",
                "field_position": "qb",
                "player_name": "Patrick Mahomes",
                "player_id": "00-0033873",
                "snap_pct": None,
                "depth_rank": 1,
                "is_starter": True,
                "starter_confidence": 0.7,
            }
        ]
    )


def _fake_service_projections() -> pd.DataFrame:
    """Preseason-fallback-shaped frame as returned by the projection service."""
    return pd.DataFrame(
        [
            {
                "player_id": "00-0033873",
                "player_name": "Patrick Mahomes",
                "team": "KC",
                "position": "QB",
                "projected_points": 327.1,
                "projected_floor": 179.91,
                "projected_ceiling": 474.3,
                "season": 2026,
                "week": 1,
            }
        ]
    )


def test_lineups_joins_projection_service_data(monkeypatch) -> None:
    """Points from the service's (fallback-capable) read reach the lineup."""
    monkeypatch.setattr(
        lineup_builder,
        "get_team_starters",
        lambda season, week, team=None: _fake_starters(),
    )
    calls = {}

    def fake_get_projections(**kwargs):
        calls.update(kwargs)
        return _fake_service_projections()

    monkeypatch.setattr(projection_service, "get_projections", fake_get_projections)

    resp = client.get(
        "/api/lineups", params={"season": 2026, "week": 1, "team": "KC"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert calls["season"] == 2026 and calls["week"] == 1
    assert calls["scoring_format"] == "half_ppr"
    qb = body["lineups"][0]["offense"][0]
    assert qb["projected_points"] == 327.1
    assert body["lineups"][0]["team_projected_total"] == 327.1


def test_lineups_survive_missing_projections(monkeypatch) -> None:
    """FileNotFoundError from the service degrades to null points, not 500."""
    monkeypatch.setattr(
        lineup_builder,
        "get_team_starters",
        lambda season, week, team=None: _fake_starters(),
    )

    def raise_not_found(**kwargs):
        raise FileNotFoundError("no projections anywhere")

    monkeypatch.setattr(projection_service, "get_projections", raise_not_found)

    resp = client.get(
        "/api/lineups", params={"season": 2026, "week": 1, "team": "KC"}
    )

    assert resp.status_code == 200
    qb = resp.json()["lineups"][0]["offense"][0]
    assert qb["projected_points"] is None
