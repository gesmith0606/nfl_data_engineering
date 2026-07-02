"""
Tests for per-player defensive Madden ratings and the schedule-based matchup
endpoint (Matchups tab fix, 2026-07).

Covers:
- player_rating_service: name normalization, rating computation bounds,
  team/position disambiguation, nickname (last-name + team) fallback.
- team_roster_service.load_team_matchup: opponent resolution from Bronze
  schedules, team-code aliases (LAR -> LA), bye weeks.
- Roster API integration: defensive roster rows carry madden_rating /
  rating_detail; slotted starters are mostly rated.
- FastAPI integration for GET /api/teams/{team}/matchup.
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
from web.api.services import player_rating_service, team_roster_service  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


class TestNormalizePlayerName:
    def test_strips_punctuation_and_suffixes(self):
        assert (
            player_rating_service.normalize_player_name("Patrick Surtain II")
            == "patrick surtain"
        )
        assert (
            player_rating_service.normalize_player_name("T.J. Watt") == "tj watt"
        )
        assert (
            player_rating_service.normalize_player_name("Odafe Oweh Jr.")
            == "odafe oweh"
        )

    def test_hyphenated_names_collapse(self):
        assert (
            player_rating_service.normalize_player_name("Sean Murphy-Bunting")
            == "sean murphybunting"
        )


# ---------------------------------------------------------------------------
# Rating lookup semantics (synthetic records — no parquet dependency)
# ---------------------------------------------------------------------------


def _make_lookup():
    rush = {"team": "KC", "group": "RUSH", "rating": 90, "rating_detail": "rush"}
    db = {"team": "TEN", "group": "DB", "rating": 70, "rating_detail": "cover"}
    two_tm = {"team": "2TM", "group": "DB", "rating": 88, "rating_detail": "agg"}
    by_name = {
        "marcus harris": [rush, db],
        "ahmad gardner": [two_tm],
    }
    by_last_team = {
        ("harris", "KC"): [rush],
        ("harris", "TEN"): [db],
        ("gardner", "NYJ"): [two_tm],
        ("gardner", "IND"): [two_tm],
    }
    return player_rating_service.DefenseRatingLookup(by_name, by_last_team)


class TestDefenseRatingLookup:
    def test_team_disambiguation_on_name_collision(self):
        lookup = _make_lookup()
        rating, detail = lookup.rating_for("Marcus Harris", "KC")
        assert (rating, detail) == (90, "rush")
        rating, detail = lookup.rating_for("Marcus Harris", "TEN")
        assert (rating, detail) == (70, "cover")

    def test_position_guard_blocks_cross_group_match(self):
        """A roster DT must not inherit a same-named DB's rating."""
        lookup = _make_lookup()
        rating, _ = lookup.rating_for("Marcus Harris", "SF", depth_position="DT")
        assert rating == 90  # only the RUSH record is compatible
        rating, _ = lookup.rating_for("Marcus Harris", "SF", depth_position="CB")
        assert rating == 70  # only the DB record is compatible

    def test_nickname_falls_back_to_last_name_and_team(self):
        lookup = _make_lookup()
        rating, _ = lookup.rating_for("Sauce Gardner", "IND")
        assert rating == 88

    def test_unknown_player_returns_none(self):
        lookup = _make_lookup()
        assert lookup.rating_for("Nobody Nowhere", "KC") == (None, None)


# ---------------------------------------------------------------------------
# Rating computation from the real PFR parquet
# ---------------------------------------------------------------------------


class TestLoadDefenseRatings:
    def test_ratings_load_and_are_bounded(self):
        lookup, effective = player_rating_service.load_defense_ratings(2026)
        assert lookup, "expected a non-empty rating lookup"
        # 2026 hasn't been played — must walk back to a completed season.
        assert effective is not None and effective <= 2025

    def test_elite_edge_rusher_rates_highly(self):
        lookup, _ = player_rating_service.load_defense_ratings(2026)
        rating, detail = lookup.rating_for("Myles Garrett", "CLE", "DE")
        assert rating is not None and rating >= 90
        assert "sacks" in (detail or "")


# ---------------------------------------------------------------------------
# EA Madden live ratings (primary source)
# ---------------------------------------------------------------------------


class TestMaddenRatings:
    def test_madden_lookup_loads(self):
        lookup = player_rating_service.load_madden_lookup()
        assert lookup, "expected Madden ratings parquet to be ingested"

    def test_star_players_carry_ea_ovr(self):
        lookup = player_rating_service.load_madden_lookup()
        rating, detail = lookup.rating_for("Patrick Mahomes", "KC", "QB")
        assert rating is not None and rating >= 85
        assert "Madden" in (detail or "")

    def test_position_guard_applies_to_madden(self):
        """A defensive lookup must not match an offensive Madden record."""
        lookup = player_rating_service.load_madden_lookup()
        rating, _ = lookup.rating_for("Patrick Mahomes", "KC", "CB")
        assert rating is None

    def test_combined_prefers_ea_and_appends_pfr_detail(self):
        combined = player_rating_service.load_combined_ratings(2026)
        rating, detail = combined.rating_for("Chris Jones", "KC", "DT")
        assert rating is not None
        assert "Madden" in (detail or "")

    def test_combined_falls_back_to_pfr(self):
        """Players below EA's per-position top-100 keep PFR-derived ratings."""
        madden = player_rating_service.DefenseRatingLookup({}, {})
        pfr, _ = player_rating_service.load_defense_ratings(2026)
        combined = player_rating_service.CombinedRatingLookup(madden, pfr)
        rating, detail = combined.rating_for("Myles Garrett", "CLE", "DE")
        assert rating is not None
        assert "Madden" not in (detail or "")


# ---------------------------------------------------------------------------
# Schedule matchup resolution
# ---------------------------------------------------------------------------


class TestLoadTeamMatchup:
    def test_resolves_opponent_2026_week1(self):
        resp = team_roster_service.load_team_matchup("KC", 2026, 1)
        assert resp.is_bye is False
        assert resp.opponent is not None
        assert {resp.home_team, resp.away_team} == {"KC", resp.opponent}
        assert resp.spread_line is not None
        assert resp.total_line is not None

    def test_lar_alias_resolves_to_la(self):
        resp = team_roster_service.load_team_matchup("LAR", 2026, 1)
        assert resp.team == "LA"
        assert resp.opponent is not None

    def test_bye_week_detected(self):
        """Every team has exactly one bye in weeks 5-14 of a full season."""
        byes = [
            w
            for w in range(5, 15)
            if team_roster_service.load_team_matchup("KC", 2025, w).is_bye
        ]
        assert len(byes) == 1

    def test_unknown_team_raises(self):
        with pytest.raises(ValueError):
            team_roster_service.load_team_matchup("XXX", 2026, 1)


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


class TestMatchupEndpoint:
    def test_matchup_200_with_lines(self):
        r = client.get("/api/teams/KC/matchup", params={"season": 2026, "week": 1})
        assert r.status_code == 200
        body = r.json()
        assert body["opponent"]
        assert body["is_bye"] is False
        assert isinstance(body["spread_line"], float)

    def test_unknown_team_404(self):
        r = client.get("/api/teams/XXX/matchup", params={"season": 2026, "week": 1})
        assert r.status_code == 404

    def test_week_validation_422(self):
        r = client.get("/api/teams/KC/matchup", params={"season": 2026, "week": 99})
        assert r.status_code == 422


class TestRosterMaddenRatings:
    def test_defense_roster_carries_ratings(self):
        r = client.get(
            "/api/teams/KC/roster",
            params={"season": 2026, "week": 1, "side": "defense"},
        )
        assert r.status_code == 200
        roster = r.json()["roster"]
        assert roster
        assert all("madden_rating" in p and "rating_detail" in p for p in roster)
        rated = [p for p in roster if p["madden_rating"] is not None]
        assert rated, "expected at least some rated defenders"
        for p in rated:
            assert 50 <= p["madden_rating"] <= 99

    def test_slotted_starters_mostly_rated(self):
        """The 11 display slots should be filled mostly by players with real
        ratings (rating-aware ordering when preseason snap data is absent)."""
        r = client.get(
            "/api/teams/KC/roster",
            params={"season": 2026, "week": 1, "side": "defense"},
        )
        slotted = [p for p in r.json()["roster"] if p["slot_hint"]]
        assert len(slotted) >= 9
        rated = [p for p in slotted if p["madden_rating"] is not None]
        assert len(rated) / len(slotted) >= 0.7

    def test_safeties_slotted_from_saf_depth_code(self):
        """2026 rosters mark safeties as 'SAF' — FS/SS slots must still fill."""
        r = client.get(
            "/api/teams/DEN/roster",
            params={"season": 2026, "week": 1, "side": "defense"},
        )
        slots = {p["slot_hint"] for p in r.json()["roster"] if p["slot_hint"]}
        assert "SS" in slots and "FS" in slots

    def test_ol_slots_fill_from_ot_and_generic_ol(self):
        """2026 rosters use 'OT'/'OL' — all five OL slots must fill."""
        r = client.get(
            "/api/teams/KC/roster",
            params={"season": 2026, "week": 1, "side": "offense"},
        )
        slots = {p["slot_hint"] for p in r.json()["roster"] if p["slot_hint"]}
        assert {"LT", "LG", "C", "RG", "RT"} <= slots
