"""Tests for src/yahoo_league.py — Yahoo team roster + live lineup parsing.

The payload shape is the fragile part: Yahoo splits one logical player across
a list of small dicts and represents lists as numeric-keyed objects. These
fixtures mirror the real 2026 Feetball response.
"""

import pytest

from src.yahoo_league import (
    fetch_team_roster,
    normalize_position,
    normalize_slot,
    parse_team_roster,
    starters_by_slot,
    team_key,
)


def _player(key, name, position, team, slot):
    """Build one Yahoo-shaped fragmented player record."""
    return {
        "player": [
            [
                {"player_key": key},
                {"name": {"full": name, "first": name.split()[0]}},
                {"editorial_team_abbr": team},
                {"display_position": position},
            ],
            {
                "selected_position": [
                    {"coverage_type": "week"},
                    {"week": "8"},
                    {"position": slot},
                ]
            },
        ]
    }


@pytest.fixture
def roster_payload():
    players = {
        "0": _player("470.p.1", "Jordan Love", "QB", "GB", "QB"),
        "1": _player("470.p.2", "Luther Burden III", "WR", "CHI", "W/R/T"),
        "2": _player("470.p.3", "Brenton Strange", "TE", "JAX", "BN"),
        "3": _player("470.p.4", "Bengals", "DEF", "CIN", "BN"),
        "4": _player("470.p.5", "Jalen Hurts", "QB", "PHI", "IR"),
        "count": 5,
    }
    return {
        "fantasy_content": {
            "team": [
                [{"team_key": "470.l.658684.t.10"}, {"name": "The Oracle"}],
                {"roster": {"0": {"players": players}, "count": 1}},
            ]
        }
    }


class TestParseTeamRoster:
    def test_reads_every_player(self, roster_payload):
        assert len(parse_team_roster(roster_payload)) == 5

    def test_identity_fields(self, roster_payload):
        love = parse_team_roster(roster_payload)[0]
        assert love == {
            "player_key": "470.p.1",
            "name": "Jordan Love",
            "position": "QB",
            "team": "GB",
            "slot": "QB",
        }

    def test_yahoo_flex_label_becomes_our_flex(self, roster_payload):
        burden = parse_team_roster(roster_payload)[1]
        assert burden["slot"] == "FLEX"

    def test_defense_position_normalized(self, roster_payload):
        bengals = parse_team_roster(roster_payload)[3]
        assert bengals["position"] == "DEF"
        assert bengals["slot"] == "BN"

    def test_reserve_slots_preserved(self, roster_payload):
        hurts = parse_team_roster(roster_payload)[4]
        assert hurts["slot"] == "IR"

    def test_empty_payload_is_empty_list(self):
        assert parse_team_roster({}) == []
        assert parse_team_roster({"fantasy_content": {"team": []}}) == []

    def test_player_without_key_is_skipped(self):
        payload = {
            "players": {"0": {"player": [[{"name": {"full": "X"}}]]}, "count": 1}
        }
        assert parse_team_roster(payload) == []


class TestStartersBySlot:
    def test_groups_by_occupied_slot(self, roster_payload):
        roster = parse_team_roster(roster_payload)
        grouped = starters_by_slot(roster, ["QB", "FLEX", "DEF"])
        assert grouped["QB"] == ["Jordan Love"]
        assert grouped["FLEX"] == ["Luther Burden III"]

    def test_unoccupied_slot_is_visible_as_empty(self, roster_payload):
        """The week-8 2026 bug: DEF empty with the Bengals on the bench."""
        roster = parse_team_roster(roster_payload)
        grouped = starters_by_slot(roster, ["QB", "FLEX", "DEF"])
        assert grouped["DEF"] == []

    def test_bench_players_never_count_as_starters(self, roster_payload):
        roster = parse_team_roster(roster_payload)
        grouped = starters_by_slot(roster, ["TE"])
        assert grouped["TE"] == []


class TestNormalizers:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("W/R/T", "FLEX"),
            ("w/r/t", "FLEX"),
            ("Q/W/R/T", "SUPER_FLEX"),
            ("QB", "QB"),
            ("BN", "BN"),
            ("", ""),
        ],
    )
    def test_slot(self, raw, expected):
        assert normalize_slot(raw) == expected

    @pytest.mark.parametrize("raw", ["DEF", "D", "DST", "D/ST"])
    def test_defense_aliases(self, raw):
        assert normalize_position(raw) == "DEF"

    def test_team_key(self):
        assert team_key("658684", "10") == "nfl.l.658684.t.10"


class TestFetchFailsOpen:
    def test_no_credentials_returns_empty(self, monkeypatch):
        """D-06: a missing grant must degrade to the roster file, not crash."""
        monkeypatch.delenv("YAHOO_CLIENT_ID", raising=False)
        monkeypatch.delenv("YAHOO_CLIENT_SECRET", raising=False)
        from src.yahoo_oauth import YahooOAuth

        oauth = YahooOAuth(client_id="", client_secret="")
        assert fetch_team_roster("658684", "10", oauth=oauth) == []
