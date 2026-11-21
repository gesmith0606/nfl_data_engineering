"""Unpublished weeks must never serve preseason season totals as weekly rows."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.api.routers import projections as projections_router  # noqa: E402
from web.api.services import projection_service as ps  # noqa: E402

SEASON = datetime.now(tz=timezone.utc).year


def _weekly(season: int, week: int) -> pd.DataFrame:
    # Mirrors the real Gold weekly schema: proj_-prefixed stats plus BOTH
    # season/week and proj_season/proj_week.
    return pd.DataFrame(
        {
            "player_id": ["00-1", "00-2"],
            "player_name": ["Weekly QB", "Weekly RB"],
            "position": ["QB", "RB"],
            "recent_team": ["KC", "SF"],
            "proj_season": [season] * 2,
            "proj_week": [week] * 2,
            "proj_passing_yards": [280.0, None],
            "proj_receptions": [None, 4.4],
            "projected_points": [22.5, 16.8],
            "projected_floor": [14.0, 10.0],
            "projected_ceiling": [31.0, 25.0],
            "season": [season] * 2,
            "week": [week] * 2,
        }
    )


def _write_weekly(root: Path, week: int) -> None:
    d = root / f"season={SEASON}" / f"week={week}"
    d.mkdir(parents=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    _weekly(SEASON, week).to_parquet(
        d / f"projections_half_ppr_{ts}.parquet", index=False
    )


def _write_preseason(root: Path) -> None:
    d = root / "preseason" / f"season={SEASON}"
    d.mkdir(parents=True)
    pd.DataFrame(
        {
            "player_id": ["00-9"],
            "player_name": ["Season QB"],
            "position": ["QB"],
            "recent_team": ["BUF"],
            "projected_season_points": [393.7],
        }
    ).to_parquet(d / "season_proj_20260612_152045.parquet", index=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "GOLD_PROJECTIONS_DIR", tmp_path)
    monkeypatch.setattr(ps, "is_db_enabled", lambda: False)
    app = FastAPI()
    app.include_router(projections_router.router, prefix="/api")
    c = TestClient(app)
    c.root = tmp_path
    return c


def _get(client, week):
    return client.get(f"/api/projections?season={SEASON}&week={week}&limit=400")


def test_unpublished_week_after_season_start_is_empty_not_season_totals(client):
    for wk in (1, 2, 3):
        _write_weekly(client.root, wk)
    _write_preseason(client.root)

    r = _get(client, 5)

    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["source"] == "not_published"
    assert body["latest_available_week"] == 3
    assert body["projections"] == []
    assert "week 3" in body["message"]
    assert body["meta"]["source"] == "not_published"
    assert not [p for p in body["projections"] if p["projected_points"] > 100]


def test_no_weekly_boards_keeps_preseason_fallback_with_top_level_marker(client):
    _write_preseason(client.root)

    body = _get(client, 1).json()

    assert body["available"] is True
    assert body["source"] == "preseason_fallback"
    assert body["is_season_total"] is True
    assert "TOTALS" in body["message"]
    assert body["projections"][0]["projected_points"] == pytest.approx(393.7)


def test_published_week_unchanged_and_stats_populated(client):
    for wk in (1, 2):
        _write_weekly(client.root, wk)
    _write_preseason(client.root)

    body = _get(client, 2).json()

    assert body["available"] is True
    assert body["source"] == "weekly"
    assert body["is_season_total"] is False
    assert body["message"] is None
    qb = next(p for p in body["projections"] if p["position"] == "QB")
    rb = next(p for p in body["projections"] if p["position"] == "RB")
    assert qb["projected_points"] == 22.5
    # Regression: season/week were 0 and per-stat columns null on weekly rows.
    assert (qb["season"], qb["week"]) == (SEASON, 2)
    assert qb["proj_pass_yards"] == 280.0
    assert rb["proj_rec"] == 4.4


def test_old_board_in_started_season_is_served_not_replaced_by_totals(client):
    # Week-1 board is old, but week 2 is fresh => season started; week 1 must
    # serve its own board rather than the preseason totals.
    for wk in (1, 2):
        _write_weekly(client.root, wk)
    _write_preseason(client.root)
    (old,) = (client.root / f"season={SEASON}" / "week=1").glob("*.parquet")
    old.rename(old.with_name("projections_half_ppr_20200101_000000.parquet"))

    body = _get(client, 1).json()

    assert body["source"] == "weekly"
    assert max(p["projected_points"] for p in body["projections"]) < 100


def test_explicit_preseason_board_is_labelled_season_total(client):
    for wk in (1, 2):
        _write_weekly(client.root, wk)
    _write_preseason(client.root)

    body = client.get(f"/api/projections?season={SEASON}&week=1&board=preseason").json()

    assert body["is_season_total"] is True
    assert body["projections"][0]["projected_points"] == pytest.approx(393.7)
