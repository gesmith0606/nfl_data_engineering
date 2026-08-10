"""Smoke tests for /api/dynasty router (dynasty + rookie rankings).

The router is not wired into web/api/main.py yet (orchestrator's job), so
these tests build a throwaway FastAPI app that includes only this router —
same pattern used while other market-gap routers were being developed.
"""

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.api.routers import dynasty

app = FastAPI()
app.include_router(dynasty.router, prefix="/api")
client = TestClient(app)

SEASON = 2026  # only season with a committed preseason projections parquet


def _skip_if_no_data(resp):
    if resp.status_code in (404, 503):
        pytest.skip("gold/bronze parquet not on disk")


def test_rankings_sorted_desc_by_dynasty_points():
    resp = client.get(f"/api/dynasty/rankings?season={SEASON}&limit=50")
    _skip_if_no_data(resp)
    assert resp.status_code == 200
    players = resp.json()["players"]
    assert len(players) > 0
    pts = [p["dynasty_points"] for p in players]
    assert pts == sorted(pts, reverse=True)


def test_age_multiplier_table():
    assert dynasty.age_multiplier("RB", 24) == 1.1
    assert dynasty.age_multiplier("RB", 26) == 1.0
    assert dynasty.age_multiplier("RB", 28) == 0.85
    assert dynasty.age_multiplier("RB", 31) == 0.7
    assert dynasty.age_multiplier("WR", 25) == 1.1
    assert dynasty.age_multiplier("WR", 28) == 1.0
    assert dynasty.age_multiplier("TE", 30) == 0.9
    assert dynasty.age_multiplier("WR", 33) == 0.75
    assert dynasty.age_multiplier("QB", 29) == 1.05
    assert dynasty.age_multiplier("QB", 33) == 1.0
    assert dynasty.age_multiplier("QB", 37) == 0.85
    # Missing age / unmodeled position -> neutral multiplier.
    assert dynasty.age_multiplier("RB", None) == 1.0
    assert dynasty.age_multiplier("K", 30) == 1.0


def test_old_rb_ranks_below_equal_projection_young_rb():
    """An old RB should rank below a young RB with the same raw projection."""
    df = dynasty._with_dynasty_points(
        pd.DataFrame(
            [
                {
                    "player_id": "old",
                    "player_name": "Old Back",
                    "position": "RB",
                    "team": "AAA",
                    "projected_season_points": 200.0,
                    "vorp": 50.0,
                },
                {
                    "player_id": "young",
                    "player_name": "Young Back",
                    "position": "RB",
                    "team": "BBB",
                    "projected_season_points": 200.0,
                    "vorp": 50.0,
                },
            ]
        ),
        pd.DataFrame(
            [
                {"player_id": "old", "age": 31.0},
                {"player_id": "young", "age": 23.0},
            ]
        ),
    )
    old_row = df[df["player_id"] == "old"].iloc[0]
    young_row = df[df["player_id"] == "young"].iloc[0]
    assert old_row["dynasty_points"] < young_row["dynasty_points"]
    assert old_row["age_multiplier"] == 0.7
    assert young_row["age_multiplier"] == 1.1


def test_rookies_only_filter():
    resp = client.get(f"/api/dynasty/rookies?season={SEASON}&limit=50")
    _skip_if_no_data(resp)
    assert resp.status_code == 200
    players = resp.json()["players"]
    # Every returned player must actually be a rookie per the roster parquet.
    roster = dynasty._load_roster(SEASON)
    assert roster is not None
    rookie_ids = set(
        roster[(roster["entry_year"] == SEASON) | (roster["years_exp"] == 0)][
            "player_id"
        ]
    )
    for p in players:
        assert p["player_id"] in rookie_ids
    proj_pts = [p["projected_season_points"] for p in players]
    assert proj_pts == sorted(proj_pts, reverse=True)


def test_rankings_503_when_preseason_missing():
    # Roster data exists for 2020 but the committed preseason parquet only
    # covers 2026, so this must fail closed rather than silently returning
    # an empty/misleading ranking.
    resp = client.get("/api/dynasty/rankings?season=2020")
    assert resp.status_code == 503


def test_rookies_404_when_roster_missing():
    # No roster parquet is committed for 1999 — rookie detection is
    # impossible, so this must 404 rather than guessing.
    resp = client.get("/api/dynasty/rookies?season=1999")
    assert resp.status_code == 404


def test_rookies_503_when_preseason_missing_but_roster_present():
    # 2020 has roster data (rookie detection works) but no preseason
    # projections parquet, so the 503 (not the 404) should fire.
    resp = client.get("/api/dynasty/rookies?season=2020")
    assert resp.status_code == 503


def test_rookies_excludes_kickers(monkeypatch):
    """A rookie K (entry_year/years_exp match season) must not appear on the
    rookie board — bug observed on prod 2026-08-08: a kicker with a flat
    preseason baseline outranked every skill-position rookie because rookie
    WR/RB projections start near zero.
    """
    roster = pd.DataFrame(
        [
            {"player_id": "wr1", "age": 22.0, "years_exp": 0, "entry_year": SEASON},
            {"player_id": "k1", "age": 23.0, "years_exp": 0, "entry_year": SEASON},
        ]
    )
    preseason = pd.DataFrame(
        [
            {
                "player_id": "wr1",
                "player_name": "Rookie Receiver",
                "position": "WR",
                "team": "AAA",
                "projected_season_points": 45.0,
            },
            {
                "player_id": "k1",
                "player_name": "Rookie Kicker",
                "position": "K",
                "team": "BBB",
                "projected_season_points": 127.0,  # flat kicker baseline > any rookie WR
            },
        ]
    )
    monkeypatch.setattr(dynasty, "_load_roster", lambda season: roster)
    monkeypatch.setattr(dynasty, "_load_preseason", lambda season: preseason.copy())
    monkeypatch.setattr(dynasty, "_load_depth_chart_roles", lambda season: {})

    resp = client.get(f"/api/dynasty/rookies?season={SEASON}")
    assert resp.status_code == 200
    positions = [p["position"] for p in resp.json()["players"]]
    assert "K" not in positions
    assert positions == ["WR"]


def test_load_depth_chart_roles_drops_non_definitive_roles(tmp_path, monkeypatch):
    """Only 'starter'/'backup' survive; deeper-string and off-chart players
    are absent from the map so the caller shows nothing rather than the
    depth-chart resolver's internal 'unknown' bucket for most rookies.
    """
    monkeypatch.setattr(dynasty, "DATA_DIR", tmp_path)

    roster_dir = tmp_path / "bronze" / "players" / "rosters" / "season=2099"
    roster_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {"player_id": "00-1111", "team": "KC", "position": "WR"},
            {"player_id": "00-2222", "team": "KC", "position": "WR"},
            {"player_id": "00-3333", "team": "KC", "position": "WR"},
        ]
    ).to_parquet(roster_dir / "rosters.parquet", index=False)

    dc_dir = tmp_path / "bronze" / "depth_charts" / "season=2099"
    dc_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "dt": "2099-01-01T00:00:00Z",
                "team": "KC",
                "pos_abb": "WR",
                "pos_rank": 1,
                "gsis_id": "00-1111",
            },
            {
                "dt": "2099-01-01T00:00:00Z",
                "team": "KC",
                "pos_abb": "WR",
                "pos_rank": 2,
                "gsis_id": "00-2222",
            },
            {
                "dt": "2099-01-01T00:00:00Z",
                "team": "KC",
                "pos_abb": "WR",
                "pos_rank": 3,
                "gsis_id": "00-3333",
            },
        ]
    ).to_parquet(dc_dir / "depth_charts.parquet", index=False)

    roles = dynasty._load_depth_chart_roles(2099)
    assert roles.get("00-1111") == "starter"
    assert roles.get("00-2222") == "backup"
    # 3rd string resolves to "unknown" internally — must be dropped, not kept.
    assert "00-3333" not in roles


def test_load_depth_chart_roles_empty_when_no_bronze_data(tmp_path, monkeypatch):
    """Missing depth_charts or roster parquet fails open to {} — no 500."""
    monkeypatch.setattr(dynasty, "DATA_DIR", tmp_path)
    assert dynasty._load_depth_chart_roles(2099) == {}


def test_rookies_degrades_when_roster_missing_entry_year_and_years_exp(monkeypatch):
    """Roster schema drift: a season's roster parquet without entry_year/
    years_exp must not 500 (KeyError) — it should just find zero rookies.
    """
    roster = pd.DataFrame(
        [
            {"player_id": "1", "age": 24.0},
            {"player_id": "2", "age": 30.0},
        ]
    )
    preseason = pd.DataFrame(
        [
            {
                "player_id": "1",
                "player_name": "No Schema Rookie",
                "position": "WR",
                "team": "AAA",
                "projected_season_points": 150.0,
            },
            {
                "player_id": "2",
                "player_name": "No Schema Vet",
                "position": "WR",
                "team": "BBB",
                "projected_season_points": 100.0,
            },
        ]
    )
    monkeypatch.setattr(dynasty, "_load_roster", lambda season: roster)
    monkeypatch.setattr(dynasty, "_load_preseason", lambda season: preseason.copy())
    resp = client.get(f"/api/dynasty/rookies?season={SEASON}")
    assert resp.status_code == 200
    assert resp.json()["players"] == []
