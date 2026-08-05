"""
Unit tests for ESPN cookie-based league import (src/espn_league.py).
"""

import os
import sys
import unittest
from unittest import mock

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.espn_league import (  # noqa: E402
    LINEUP_SLOT_MAP,
    POSITION_ID_MAP,
    PRO_TEAM_MAP,
    cookies_from_env,
    extract_draft_picks,
    extract_league_info,
    extract_rosters,
    extract_teams,
    find_my_team_id,
)

SWID = "{ABCD1234-EEEE-FFFF-0000-999888777666}"


def _player(pid, name, pos_id, pro_id, injury="ACTIVE"):
    return {
        "id": pid,
        "fullName": name,
        "defaultPositionId": pos_id,
        "proTeamId": pro_id,
        "injuryStatus": injury,
    }


def _league_payload(drafted=True):
    return {
        "id": 12345678,
        "seasonId": 2026,
        "scoringPeriodId": 1,
        "settings": {
            "name": "Test League",
            "size": 10,
            "scoringSettings": {
                "scoringType": "H2H_POINTS",
                "scoringItems": [{"statId": 53, "points": 0.5}],
            },
        },
        "members": [
            {"id": SWID, "displayName": "smithge"},
            {"id": "{OTHER-GUID}", "displayName": "rival"},
        ],
        "teams": [
            {
                "id": 1,
                "name": "Team Smith",
                "abbrev": "SMTH",
                "owners": [SWID],
                "record": {"overall": {"wins": 0, "losses": 0}},
                "roster": {
                    "entries": [
                        {
                            "lineupSlotId": 2,
                            "playerPoolEntry": {
                                "player": _player(101, "Jahmyr Gibbs", 2, 8)
                            },
                        },
                        {
                            "lineupSlotId": 20,
                            "playerPoolEntry": {
                                "player": _player(
                                    102, "Marvin Harrison Jr.", 3, 22, "QUESTIONABLE"
                                )
                            },
                        },
                    ]
                },
            },
            {
                "id": 2,
                "location": "Old",
                "nickname": "Style",
                "abbrev": "OLD",
                "owners": ["{OTHER-GUID}"],
                "record": {"overall": {"wins": 0, "losses": 0}},
                "roster": {
                    "entries": [
                        {
                            "lineupSlotId": 0,
                            "playerPoolEntry": {
                                "player": _player(103, "Josh Allen", 1, 2)
                            },
                        }
                    ]
                },
            },
        ],
        "draftDetail": {
            "drafted": drafted,
            "picks": [
                {
                    "overallPickNumber": 2,
                    "roundId": 1,
                    "roundPickNumber": 2,
                    "playerId": 103,
                    "teamId": 2,
                    "keeper": False,
                },
                {
                    "overallPickNumber": 1,
                    "roundId": 1,
                    "roundPickNumber": 1,
                    "playerId": 101,
                    "teamId": 1,
                    "keeper": True,
                },
                {
                    "overallPickNumber": 3,
                    "roundId": 1,
                    "roundPickNumber": 3,
                    "playerId": 999,  # drafted then dropped — not on a roster
                    "teamId": 2,
                    "keeper": False,
                },
            ],
        },
    }


class TestCookies(unittest.TestCase):
    def test_empty_env_returns_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cookies_from_env(), {})

    def test_swid_brace_normalisation(self):
        with mock.patch.dict(
            os.environ, {"ESPN_S2": "tok", "ESPN_SWID": "ABC-123"}, clear=True
        ):
            cookies = cookies_from_env()
        self.assertEqual(cookies["espn_s2"], "tok")
        self.assertEqual(cookies["SWID"], "{ABC-123}")

    def test_braced_swid_kept(self):
        with mock.patch.dict(os.environ, {"ESPN_SWID": "{ABC-123}"}, clear=True):
            self.assertEqual(cookies_from_env()["SWID"], "{ABC-123}")


class TestExtraction(unittest.TestCase):
    def test_league_info(self):
        info = extract_league_info(_league_payload())
        self.assertEqual(info["name"], "Test League")
        self.assertEqual(info["size"], 10)
        self.assertEqual(info["points_per_reception"], 0.5)
        self.assertTrue(info["draft_complete"])

    def test_teams_including_legacy_naming(self):
        teams = extract_teams(_league_payload())
        self.assertEqual(len(teams), 2)
        self.assertEqual(list(teams["team_name"]), ["Team Smith", "Old Style"])
        self.assertEqual(teams.iloc[0]["owner_name"], "smithge")

    def test_rosters(self):
        rosters = extract_rosters(_league_payload())
        self.assertEqual(len(rosters), 3)
        gibbs = rosters[rosters["player_name"] == "Jahmyr Gibbs"].iloc[0]
        self.assertEqual(gibbs["position"], "RB")
        self.assertEqual(gibbs["pro_team"], "DET")
        self.assertEqual(gibbs["lineup_slot"], "RB")
        self.assertTrue(gibbs["is_starter"])
        mhj = rosters[rosters["player_name"] == "Marvin Harrison Jr."].iloc[0]
        self.assertEqual(mhj["lineup_slot"], "BN")
        self.assertFalse(mhj["is_starter"])
        self.assertEqual(mhj["injury_status"], "QUESTIONABLE")

    def test_find_my_team(self):
        payload = _league_payload()
        self.assertEqual(find_my_team_id(payload, SWID), 1)
        # Bare/lowercase SWID still matches.
        self.assertEqual(find_my_team_id(payload, SWID.strip("{}").lower()), 1)
        self.assertIsNone(find_my_team_id(payload, "{NOT-A-MEMBER}"))
        self.assertIsNone(find_my_team_id(payload, ""))


class TestDraftPicks(unittest.TestCase):
    def test_picks_sorted_and_resolved(self):
        picks = extract_draft_picks(_league_payload())
        self.assertEqual([p.pick_no for p in picks], [1, 2, 3])
        first = picks[0]
        self.assertEqual(first.full_name, "Jahmyr Gibbs")
        self.assertEqual(first.position, "RB")
        self.assertEqual(first.team, "DET")
        self.assertTrue(first.is_keeper)

    def test_dropped_player_keeps_raw_id(self):
        picks = extract_draft_picks(_league_payload())
        dropped = picks[2]
        self.assertEqual(dropped.full_name, "999")
        self.assertEqual(dropped.position, "?")

    def test_undrafted_league_returns_empty(self):
        self.assertEqual(extract_draft_picks(_league_payload(drafted=False)), [])


class TestMaps(unittest.TestCase):
    def test_position_map_covers_fantasy_slots(self):
        self.assertEqual(
            set(POSITION_ID_MAP.values()), {"QB", "RB", "WR", "TE", "K", "DST"}
        )

    def test_pro_team_map_has_32_teams_plus_fa(self):
        teams = set(PRO_TEAM_MAP.values())
        self.assertIn("FA", teams)
        self.assertEqual(len(teams - {"FA"}), 32)

    def test_bench_and_ir_not_starters(self):
        self.assertEqual(LINEUP_SLOT_MAP[20], "BN")
        self.assertEqual(LINEUP_SLOT_MAP[21], "IR")


if __name__ == "__main__":
    unittest.main()
