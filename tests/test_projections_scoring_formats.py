"""A format with no weekly board must say so, never borrow another format's points."""

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
TS = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _board(points: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": ["00-2"],
            "player_name": ["Weekly RB"],
            "position": ["RB"],
            "recent_team": ["SF"],
            "proj_receptions": [4.0],
            "projected_points": [points],
            "projected_floor": [points - 5],
            "projected_ceiling": [points + 8],
            "season": [SEASON],
            "week": [2],
        }
    )


def _write(root: Path, week: int, fmt: str, points: float) -> None:
    d = root / f"season={SEASON}" / f"week={week}"
    d.mkdir(parents=True, exist_ok=True)
    _board(points).to_parquet(d / f"projections_{fmt}_{TS}.parquet", index=False)


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
    ).to_parquet(d / "season_proj_ppr_20260612_152045.parquet", index=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "GOLD_PROJECTIONS_DIR", tmp_path)
    monkeypatch.setattr(ps, "is_db_enabled", lambda: False)
    app = FastAPI()
    app.include_router(projections_router.router, prefix="/api")
    c = TestClient(app)
    c.root = tmp_path
    return c


def _get(client, fmt, week=2):
    return client.get(
        f"/api/projections?season={SEASON}&week={week}&scoring={fmt}&limit=50"
    ).json()


def test_format_without_weekly_board_is_not_published_not_season_totals(client):
    for wk in (1, 2):
        _write(client.root, wk, "half_ppr", 12.0)
    _write_preseason(client.root)

    for fmt in ("ppr", "standard"):
        body = _get(client, fmt)
        assert body["available"] is False
        assert body["source"] == "not_published"
        assert body["is_season_total"] is False
        assert body["projections"] == []
        assert fmt in body["message"]
    half = _get(client, "half_ppr")
    assert half["available"] is True
    assert half["projections"][0]["projected_points"] == 12.0


def test_each_format_serves_its_own_board_and_meta_path(client):
    for wk in (1, 2):
        _write(client.root, wk, "half_ppr", 12.0)
        _write(client.root, wk, "ppr", 14.0)
        _write(client.root, wk, "standard", 10.0)

    for fmt, pts in (("half_ppr", 12.0), ("ppr", 14.0), ("standard", 10.0)):
        body = _get(client, fmt)
        assert body["available"] is True and body["source"] == "weekly"
        assert body["projections"][0]["projected_points"] == pts
        assert f"projections_{fmt}_" in body["meta"]["source_path"]


def test_started_is_decided_across_formats(client):
    # Only ppr has boards: the season has still started, so a missing week 5
    # is not_published (never the preseason totals) even for half_ppr.
    for wk in (1, 2):
        _write(client.root, wk, "ppr", 14.0)
    _write_preseason(client.root)

    body = _get(client, "half_ppr", week=5)
    assert body["source"] == "not_published"
    assert body["latest_available_week"] == 2


def test_legacy_unscoped_board_still_served_for_any_format(client):
    for wk in (1, 2):
        d = client.root / f"season={SEASON}" / f"week={wk}"
        d.mkdir(parents=True)
        _board(9.0).to_parquet(d / f"projections_{TS}.parquet", index=False)
    assert _get(client, "ppr")["projections"][0]["projected_points"] == 9.0
