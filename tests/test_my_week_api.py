"""Tests for GET /api/league/{league_id}/my-week (weekly command center).

All Sleeper HTTP + projection I/O is mocked — these tests NEVER hit the
network or read repo Gold parquets. The synthetic weekly frame mirrors the
real weekly Gold schema: GSIS ``player_id``, abbreviated ``player_name``
("J.Allen"), unprefixed stat columns (post-loader rename), floor/ceiling,
``injury_status``, and ``is_bye_week``.

Coverage:
    - weekly mode 200: optimal starters, full display names, floor/ceiling
    - start/sit deltas vs the currently-set Sleeper lineup (net gain)
    - bye-week and Out flags on affected players
    - league re-scoring (TE premium changes weekly TE points + bands)
    - abbreviated-name fallback join (player without gsis_id)
    - weekly waiver targets: exclusion of rostered players, sort, upgrades_over
    - preseason mode: no weekly parquet → 200 + message + empty payload
    - current-week resolution when week param omitted (match and mismatch)
    - 400 non-numeric league_id, 404 user not in league
    - unmatched player_ids surfaced
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from web.api.main import app
from web.api.models.schemas import CurrentWeekResponse

client = TestClient(app)

LEAGUE_ID = "1378522447686402048"
USER_ID = "997016529965223936"
SEASON = 2024
WEEK = 10

# ---------------------------------------------------------------------------
# Synthetic league — half-PPR baseline scoring, 7 starting slots
# ---------------------------------------------------------------------------

_HALF_PPR_SETTINGS: Dict[str, float] = {
    "rec": 0.5,
    "rec_yd": 0.1,
    "rec_td": 6.0,
    "rush_yd": 0.1,
    "rush_td": 6.0,
    "pass_yd": 0.04,
    "pass_td": 4.0,
    "pass_int": -2.0,
}

_LEAGUE: Dict[str, Any] = {
    "league_id": LEAGUE_ID,
    "name": "My Week Test League",
    "season": str(SEASON),
    "status": "in_season",
    "total_rosters": 2,
    "scoring_settings": dict(_HALF_PPR_SETTINGS),
    "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN", "BN", "BN"],
    "settings": {},
}

# ---------------------------------------------------------------------------
# Synthetic Sleeper registry (raw form — served by load_sleeper_players)
# ---------------------------------------------------------------------------


def _reg(name: str, pos: str, team: str, gsis: Optional[str]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"full_name": name, "position": pos, "team": team}
    if gsis:
        entry["gsis_id"] = gsis
    return entry


_REGISTRY: Dict[str, Any] = {
    # --- user roster ---------------------------------------------------------
    "S1": _reg("Josh Allen", "QB", "BUF", "00-0001"),
    "S2": _reg("Jalen Hurts", "QB", "PHI", "00-0002"),
    "S3": _reg("Christian McCaffrey", "RB", "SF", "00-0003"),
    "S4": _reg("Breece Hall", "RB", "NYJ", "00-0004"),
    "S5": _reg("Justin Jefferson", "WR", "MIN", "00-0005"),
    # No gsis_id — exercises the abbreviated-name fallback join.
    "S6": _reg("Amon-Ra St. Brown", "WR", "DET", None),
    "S7": _reg("Sam LaPorta", "TE", "DET", "00-0007"),
    "S8": _reg("Garrett Wilson", "WR", "NYJ", "00-0008"),  # on bye
    "S9": _reg("Nick Chubb", "RB", "CLE", "00-0009"),  # Out
    "S10": _reg("Taxi Rookie", "RB", "DAL", None),  # no weekly row → unmatched
    "S11": _reg("Tyjae Spears", "RB", "TEN", "00-0011"),
    # --- other team's roster -------------------------------------------------
    "S20": _reg("Patrick Mahomes", "QB", "KC", "00-0020"),
    # --- free agents ---------------------------------------------------------
    "F1": _reg("Jordan Love", "QB", "GB", "00-0101"),
    "F2": _reg("Rachaad White", "RB", "TB", "00-0102"),
    "F3": _reg("Romeo Doubs", "WR", "GB", "00-0103"),
}

# ---------------------------------------------------------------------------
# Synthetic rosters — user starts a deliberately suboptimal lineup:
#   QB Hurts (Allen benched), RB Chubb (Out), WR G.Wilson (bye).
# ---------------------------------------------------------------------------

_ROSTERS: List[Dict[str, Any]] = [
    {
        "roster_id": 1,
        "owner_id": USER_ID,
        "starters": ["S2", "S3", "S9", "S5", "S8", "S7", "S4"],
        "players": [
            "S1",
            "S2",
            "S3",
            "S4",
            "S5",
            "S6",
            "S7",
            "S8",
            "S9",
            "S10",
            "S11",
        ],
    },
    {
        "roster_id": 2,
        "owner_id": "OTHER_OWNER",
        "starters": ["S20"],
        "players": ["S20"],
    },
]

# ---------------------------------------------------------------------------
# Synthetic weekly Gold frame (post-loader shape: unprefixed stat columns).
# Points are driven by rushing_yards = 10 × points so re-scoring under the
# half-PPR settings reproduces the fixture points exactly; Sam LaPorta uses
# receiving stats so the TE-premium test has receptions to bonus.
# ---------------------------------------------------------------------------


def _wk(
    gsis: Optional[str],
    name: str,
    pos: str,
    team: str,
    pts: float,
    bye: bool = False,
    injury: str = "Active",
    receptions: float = 0.0,
    receiving_yards: float = 0.0,
    receiving_tds: float = 0.0,
) -> Dict[str, Any]:
    rush_pts = pts - (receptions * 0.5 + receiving_yards * 0.1 + receiving_tds * 6.0)
    return {
        "player_id": gsis or "",
        "player_name": name,
        "position": pos,
        "team": team,
        "passing_yards": 0.0,
        "passing_tds": 0.0,
        "interceptions": 0.0,
        "rushing_yards": rush_pts * 10.0,
        "rushing_tds": 0.0,
        "receptions": receptions,
        "receiving_yards": receiving_yards,
        "receiving_tds": receiving_tds,
        "projected_points": pts,
        "projected_floor": round(pts * 0.6, 1),
        "projected_ceiling": round(pts * 1.4, 1),
        "injury_status": injury,
        "is_bye_week": bye,
    }


_WEEKLY_ROWS: List[Dict[str, Any]] = [
    _wk("00-0001", "J.Allen", "QB", "BUF", 24.0),
    _wk("00-0002", "J.Hurts", "QB", "PHI", 18.0),
    _wk("00-0003", "C.McCaffrey", "RB", "SF", 20.0),
    _wk("00-0004", "B.Hall", "RB", "NYJ", 14.0),
    _wk("00-0005", "J.Jefferson", "WR", "MIN", 17.0),
    # Abbreviated multi-token surname — matched via the abbrev fallback.
    _wk("", "A.St. Brown", "WR", "DET", 15.0),
    _wk(
        "00-0007",
        "S.LaPorta",
        "TE",
        "DET",
        12.0,
        receptions=6.0,
        receiving_yards=60.0,
        receiving_tds=0.5,
    ),
    _wk("00-0008", "G.Wilson", "WR", "NYJ", 0.0, bye=True),
    _wk("00-0009", "N.Chubb", "RB", "CLE", 0.0, injury="Out"),
    _wk("00-0011", "T.Spears", "RB", "TEN", 8.0),
    _wk("00-0020", "P.Mahomes", "QB", "KC", 25.0),
    _wk("00-0101", "J.Love", "QB", "GB", 22.0),
    _wk("00-0102", "R.White", "RB", "TB", 16.0),
    _wk("00-0103", "R.Doubs", "WR", "GB", 9.0),
]


def _make_weekly_df() -> pd.DataFrame:
    return pd.DataFrame([dict(r) for r in _WEEKLY_ROWS])


# ---------------------------------------------------------------------------
# Fixtures / patch helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_league_cache() -> Any:
    """Clear the router's in-process TTL cache before and after each test."""
    import web.api.routers.sleeper_user as mod

    mod._CACHE.clear()
    yield
    mod._CACHE.clear()


def _patch_all(
    weekly_df: Optional[pd.DataFrame] = "default",  # type: ignore[assignment]
    league: Optional[Dict[str, Any]] = None,
):
    """Context managers patching all Sleeper + projection + ADP I/O."""
    if isinstance(weekly_df, str):
        weekly_df = _make_weekly_df()
    return (
        patch(
            "web.api.routers.sleeper_user.get_league",
            return_value=dict(league or _LEAGUE),
        ),
        patch(
            "web.api.routers.sleeper_user.get_league_rosters",
            return_value=[dict(r) for r in _ROSTERS],
        ),
        patch(
            "web.api.routers.sleeper_user.load_sleeper_players",
            return_value=dict(_REGISTRY),
        ),
        patch(
            "web.api.routers.sleeper_user._load_weekly_projections",
            return_value=weekly_df,
        ),
        patch("web.api.routers.sleeper_user._load_adp", return_value={}),
    )


def _get_my_week(params: Optional[Dict[str, Any]] = None, **patch_kwargs):
    """Call the endpoint with all I/O patched; returns the response."""
    merged = {"user_id": USER_ID, "season": SEASON, "week": WEEK}
    merged.update(params or {})
    merged = {k: v for k, v in merged.items() if v is not None}
    with ExitStack() as stack:
        for cm in _patch_all(**patch_kwargs):
            stack.enter_context(cm)
        return client.get(f"/api/league/{LEAGUE_ID}/my-week", params=merged)


# ---------------------------------------------------------------------------
# Weekly mode
# ---------------------------------------------------------------------------


class TestMyWeekWeeklyMode:
    def test_200_weekly_mode_with_starters(self):
        resp = _get_my_week()
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "weekly"
        assert data["season"] == SEASON
        assert data["week"] == WEEK
        assert data["message"] is None
        # 7 starting slots: QB, RB, RB, WR, WR, TE, FLEX
        assert len(data["optimal_starters"]) == 7

    def test_starters_show_full_names_not_abbreviated(self):
        data = _get_my_week().json()
        names = [s["player_name"] for s in data["optimal_starters"]]
        assert "Josh Allen" in names
        assert "J.Allen" not in names

    def test_starters_have_floor_ceiling_and_points(self):
        data = _get_my_week().json()
        qb = next(s for s in data["optimal_starters"] if s["slot"] == "QB")
        assert qb["player_name"] == "Josh Allen"
        assert qb["projected_points"] == pytest.approx(24.0)
        assert qb["floor"] == pytest.approx(14.4)
        assert qb["ceiling"] == pytest.approx(33.6)

    def test_abbrev_fallback_matches_multi_token_surname(self):
        """Amon-Ra St. Brown has no gsis_id; joins via 'astbrown' key."""
        data = _get_my_week().json()
        names = [s["player_name"] for s in data["optimal_starters"]]
        assert "Amon-Ra St. Brown" in names

    def test_unmatched_player_ids_surfaced(self):
        data = _get_my_week().json()
        assert data["unmatched_player_ids"] == ["S10"]

    def test_bench_has_weekly_points(self):
        data = _get_my_week().json()
        bench_names = {b["player_name"] for b in data["bench"]}
        # Hurts loses QB to Allen; Chubb (Out) and G.Wilson (bye) drop out.
        assert "Jalen Hurts" in bench_names
        hurts = next(b for b in data["bench"] if b["player_name"] == "Jalen Hurts")
        assert hurts["projected_points"] == pytest.approx(18.0)


# ---------------------------------------------------------------------------
# Start/sit deltas
# ---------------------------------------------------------------------------


class TestMyWeekChanges:
    def test_changes_net_gain(self):
        data = _get_my_week().json()
        changes = data["changes"]
        # Current: Hurts 18 + CMC 20 + Chubb 0 + JJ 17 + GWilson 0 + LaPorta 12
        #          + Hall 14 = 81
        # Optimal: Allen 24 + CMC 20 + Hall 14 + JJ 17 + ASB 15 + LaPorta 12
        #          + Spears 8 (FLEX) = 110
        assert changes["current_points"] == pytest.approx(81.0)
        assert changes["optimal_points"] == pytest.approx(110.0)
        assert changes["net_gain"] == pytest.approx(29.0)

    def test_to_start_lists_upgrades(self):
        data = _get_my_week().json()
        to_start = {p["player_name"] for p in data["changes"]["to_start"]}
        assert to_start == {"Josh Allen", "Amon-Ra St. Brown", "Tyjae Spears"}

    def test_to_bench_lists_downgrades_with_flags(self):
        data = _get_my_week().json()
        to_bench = data["changes"]["to_bench"]
        by_name = {p["player_name"]: p for p in to_bench}
        assert set(by_name) == {"Jalen Hurts", "Nick Chubb", "Garrett Wilson"}
        assert by_name["Nick Chubb"]["is_out"] is True
        assert by_name["Nick Chubb"]["injury_status"] == "Out"
        assert by_name["Garrett Wilson"]["is_bye_week"] is True

    def test_optimal_lineup_avoids_bye_and_out_players(self):
        data = _get_my_week().json()
        starter_names = {s["player_name"] for s in data["optimal_starters"]}
        assert "Nick Chubb" not in starter_names
        assert "Garrett Wilson" not in starter_names


# ---------------------------------------------------------------------------
# League re-scoring
# ---------------------------------------------------------------------------


class TestMyWeekLeagueScoring:
    def test_te_premium_raises_weekly_te_points(self):
        """Full PPR + TE premium: LaPorta 6 rec, 60 yd, 0.5 td →
        6×1.0 + 60×0.1 + 0.5×6 + 6×1.0 bonus = 21.0 (vs 12.0 half-PPR)."""
        league = dict(_LEAGUE)
        league["scoring_settings"] = {
            **_HALF_PPR_SETTINGS,
            "rec": 1.0,
            "bonus_rec_te": 1.0,
        }
        data = _get_my_week(league=league).json()
        te = next(s for s in data["optimal_starters"] if s["slot"] == "TE")
        assert te["player_name"] == "Sam LaPorta"
        assert te["projected_points"] == pytest.approx(21.0)

    def test_floor_ceiling_scale_with_rescoring(self):
        """Bands scale by the re-score ratio (21/12 for LaPorta)."""
        league = dict(_LEAGUE)
        league["scoring_settings"] = {
            **_HALF_PPR_SETTINGS,
            "rec": 1.0,
            "bonus_rec_te": 1.0,
        }
        data = _get_my_week(league=league).json()
        te = next(s for s in data["optimal_starters"] if s["slot"] == "TE")
        # Half-PPR bands were 7.2 / 16.8; ratio 21/12 = 1.75.
        assert te["floor"] == pytest.approx(12.6, abs=0.1)
        assert te["ceiling"] == pytest.approx(29.4, abs=0.1)


# ---------------------------------------------------------------------------
# Weekly waiver targets
# ---------------------------------------------------------------------------


class TestMyWeekWaivers:
    def test_targets_exclude_rostered_players(self):
        data = _get_my_week().json()
        target_names = {t["player_name"] for t in data["waiver_targets"]}
        assert "Patrick Mahomes" not in target_names  # other team's roster
        assert "Josh Allen" not in target_names  # user's roster
        assert target_names == {"Jordan Love", "Rachaad White", "Romeo Doubs"}

    def test_targets_sorted_by_weekly_points_desc(self):
        data = _get_my_week().json()
        pts = [t["projected_points"] for t in data["waiver_targets"]]
        assert pts == sorted(pts, reverse=True)
        assert data["waiver_targets"][0]["player_name"] == "Jordan Love"

    def test_upgrade_annotation(self):
        """Rachaad White (16.0) out-projects the weakest RB starter — Tyjae
        Spears (8.0) in the FLEX; Jordan Love (22.0) does not beat Josh
        Allen (24.0)."""
        data = _get_my_week().json()
        by_name = {t["player_name"]: t for t in data["waiver_targets"]}
        assert by_name["Rachaad White"]["upgrades_over"] == "Tyjae Spears"
        assert by_name["Rachaad White"]["upgrade_slot"] == "FLEX"
        assert by_name["Jordan Love"]["upgrades_over"] is None

    def test_targets_capped_at_ten(self):
        data = _get_my_week().json()
        assert len(data["waiver_targets"]) <= 10


# ---------------------------------------------------------------------------
# Preseason mode
# ---------------------------------------------------------------------------


class TestMyWeekPreseasonMode:
    def test_no_weekly_data_returns_200_preseason(self):
        resp = _get_my_week(weekly_df=None)
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "preseason"
        assert data["message"] is not None
        assert "Roster Report" in data["message"]
        assert data["optimal_starters"] == []
        assert data["bench"] == []
        assert data["waiver_targets"] == []
        assert data["changes"] is None

    def test_week_omitted_resolves_current_week(self):
        cw = CurrentWeekResponse(season=SEASON, week=WEEK, source="schedule")
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            stack.enter_context(
                patch(
                    "web.api.routers.sleeper_user._get_current_week",
                    return_value=cw,
                )
            )
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/my-week",
                params={"user_id": USER_ID, "season": SEASON},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "weekly"
        assert data["week"] == WEEK

    def test_week_omitted_offseason_mismatch_is_preseason(self):
        """Current week resolves to a different season → preseason mode."""
        cw = CurrentWeekResponse(season=2025, week=18, source="fallback")
        with ExitStack() as stack:
            for cm in _patch_all():
                stack.enter_context(cm)
            stack.enter_context(
                patch(
                    "web.api.routers.sleeper_user._get_current_week",
                    return_value=cw,
                )
            )
            resp = client.get(
                f"/api/league/{LEAGUE_ID}/my-week",
                params={"user_id": USER_ID, "season": SEASON},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "preseason"
        assert data["week"] is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestMyWeekErrors:
    def test_400_non_numeric_league_id(self):
        resp = client.get(
            "/api/league/not-a-number/my-week", params={"user_id": USER_ID}
        )
        assert resp.status_code == 400

    def test_404_user_not_in_league(self):
        resp = _get_my_week(params={"user_id": "NOBODY"})
        assert resp.status_code == 404

    def test_422_week_out_of_range(self):
        resp = _get_my_week(params={"week": 25})
        assert resp.status_code == 422
