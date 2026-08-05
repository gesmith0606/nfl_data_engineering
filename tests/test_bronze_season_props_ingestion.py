"""
Unit tests for Bronze season player props ingestion (DraftKings futures).
"""

import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bronze_season_props_ingestion import (  # noqa: E402
    FANDUEL_STAT_TO_MARKET,
    ROOKIE_MILESTONE_MARKETS,
    SEASON_MARKETS,
    SEASON_PROPS_SCHEMA_COLS,
    extract_team_nfl,
    normalize_fanduel_response,
    normalize_milestone_response,
    normalize_subcategory_response,
    parse_american_odds,
    parse_event_name,
    parse_line_from_label,
    parse_milestone_threshold,
)


def _dk_response(
    event_name="NFL 2026/27 - David Montgomery",
    over_label="Over 824.5",
    under_label="Under 824.5",
    include_under=True,
):
    """Build a minimal DraftKings subcategory payload for one player."""
    selections = [
        {
            "id": "sel-over",
            "marketId": "m1",
            "label": over_label,
            "outcomeType": "Over",
            "displayOdds": {"american": "−120"},
        }
    ]
    if include_under:
        selections.append(
            {
                "id": "sel-under",
                "marketId": "m1",
                "label": under_label,
                "outcomeType": "Under",
                "displayOdds": {"american": "+100"},
            }
        )
    return {
        "events": [
            {
                "id": "ev1",
                "name": event_name,
                "participants": [
                    {"type": "Team", "name": "David Montgomery", "metadata": {}},
                    {
                        "type": "Team",
                        "name": "DET Lions",
                        "metadata": {"shortName": "DET"},
                    },
                ],
            }
        ],
        "markets": [
            {
                "id": "m1",
                "eventId": "ev1",
                "name": "NFL 2026/27 - David Montgomery Regular Season Rushing Yards",
                "marketType": {"name": "Regular Season Rushing Yards OU"},
            }
        ],
        "selections": selections,
    }


class TestParsers(unittest.TestCase):
    def test_parse_american_odds_unicode_minus(self):
        self.assertEqual(parse_american_odds("−110"), -110)

    def test_parse_american_odds_plus(self):
        self.assertEqual(parse_american_odds("+150"), 150)

    def test_parse_american_odds_ascii_minus(self):
        self.assertEqual(parse_american_odds("-105"), -105)

    def test_parse_american_odds_missing(self):
        self.assertIsNone(parse_american_odds(None))
        self.assertIsNone(parse_american_odds(""))
        self.assertIsNone(parse_american_odds("EVEN"))

    def test_parse_event_name(self):
        season, player = parse_event_name("NFL 2026/27 - Mike Evans")
        self.assertEqual(season, 2026)
        self.assertEqual(player, "Mike Evans")

    def test_parse_event_name_bad(self):
        self.assertEqual(parse_event_name("Super Bowl Winner"), (None, None))
        self.assertEqual(parse_event_name(""), (None, None))

    def test_parse_line_from_label(self):
        self.assertEqual(parse_line_from_label("Over 824.5"), 824.5)
        self.assertEqual(parse_line_from_label("Under 3,949.5"), 3949.5)
        self.assertEqual(parse_line_from_label("Over 8"), 8.0)

    def test_parse_line_from_label_bad(self):
        self.assertIsNone(parse_line_from_label("Yes"))
        self.assertIsNone(parse_line_from_label(""))

    def test_extract_team_nfl(self):
        participants = [
            {"type": "Team", "name": "Jadarian Price", "metadata": {}},
            {"type": "Team", "name": "SEA Seahawks", "metadata": {"shortName": "SEA"}},
        ]
        self.assertEqual(extract_team_nfl(participants), "SEA")
        self.assertIsNone(extract_team_nfl([]))
        self.assertIsNone(extract_team_nfl(None))


class TestNormalize(unittest.TestCase):
    def test_happy_path(self):
        rows = normalize_subcategory_response(
            _dk_response(), "season_rush_yds", "2026-08-02T12:00:00+00:00"
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row.keys()), set(SEASON_PROPS_SCHEMA_COLS))
        self.assertEqual(row["market"], "season_rush_yds")
        self.assertEqual(row["player_name"], "David Montgomery")
        self.assertEqual(row["team_nfl"], "DET")
        self.assertEqual(row["line"], 824.5)
        self.assertEqual(row["price_over"], -120)
        self.assertEqual(row["price_under"], 100)
        self.assertEqual(row["season"], 2026)
        self.assertEqual(row["bookmaker"], "draftkings")

    def test_one_sided_market_kept(self):
        rows = normalize_subcategory_response(
            _dk_response(include_under=False),
            "season_rush_yds",
            "2026-08-02T12:00:00+00:00",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["price_over"], -120)
        self.assertIsNone(rows[0]["price_under"])

    def test_bad_event_name_skipped(self):
        rows = normalize_subcategory_response(
            _dk_response(event_name="Champion 2026"),
            "season_rush_yds",
            "2026-08-02T12:00:00+00:00",
        )
        self.assertEqual(rows, [])

    def test_unparseable_line_skipped(self):
        rows = normalize_subcategory_response(
            _dk_response(over_label="Yes", under_label="No"),
            "season_rush_yds",
            "2026-08-02T12:00:00+00:00",
        )
        self.assertEqual(rows, [])

    def test_empty_payload(self):
        rows = normalize_subcategory_response({}, "season_rush_yds", "ts")
        self.assertEqual(rows, [])


def _dk_milestone_response():
    """Minimal Rookie Watch Milestones payload for one player."""
    return {
        "events": [
            {
                "id": "ev1",
                "name": "NFL 2026/27 - Jeremiyah Love",
                "participants": [
                    {"type": "Team", "name": "Jeremiyah Love", "metadata": {}},
                    {
                        "type": "Team",
                        "name": "DEN Broncos",
                        "metadata": {"shortName": "DEN"},
                    },
                ],
            }
        ],
        "markets": [
            {
                "id": "m1",
                "eventId": "ev1",
                "name": (
                    "NFL 2026/27 - Jeremiyah Love Regular Season Rushing "
                    "Yards Milestones"
                ),
                "marketType": {
                    "name": "Rookie Regular Season Rushing Yards Milestones"
                },
            }
        ],
        "selections": [
            {
                "id": f"s{i}",
                "marketId": "m1",
                "label": label,
                "displayOdds": {"american": odds},
            }
            for i, (label, odds) in enumerate(
                [
                    ("750+", "−210"),
                    ("1,000+", "+200"),
                    ("1250+", "+700"),
                    ("1500+", "+2000"),
                ]
            )
        ],
    }


class TestMilestoneNormalize(unittest.TestCase):
    def test_parse_milestone_threshold(self):
        self.assertEqual(parse_milestone_threshold("750+"), 750.0)
        self.assertEqual(parse_milestone_threshold("1,000+"), 1000.0)
        self.assertIsNone(parse_milestone_threshold("Over 824.5"))
        self.assertIsNone(parse_milestone_threshold(""))

    def test_ladder_rows(self):
        rows = normalize_milestone_response(
            _dk_milestone_response(), "rookie_rush_yds", "ts"
        )
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["market"] for r in rows}, {"rookie_rush_yds"})
        self.assertEqual([r["line"] for r in rows], [750.0, 1000.0, 1250.0, 1500.0])
        self.assertEqual(rows[0]["price_over"], -210)
        self.assertIsNone(rows[0]["price_under"])
        self.assertEqual(rows[0]["player_name"], "Jeremiyah Love")
        self.assertEqual(rows[0]["team_nfl"], "DEN")
        self.assertEqual(set(rows[0].keys()), set(SEASON_PROPS_SCHEMA_COLS))

    def test_empty_payload(self):
        self.assertEqual(normalize_milestone_response({}, "rookie_rush_yds", "ts"), [])


def _fd_runner(name, odds):
    return {
        "runnerName": name,
        "runnerStatus": "ACTIVE",
        "winRunnerOdds": {"americanDisplayOdds": {"americanOdds": odds}},
    }


def _fd_response():
    return {
        "attachments": {
            "markets": {
                "734.1": {
                    "marketId": "734.1",
                    "eventId": 28297422,
                    "marketName": (
                        "Aaron Rodgers Regular Season Passing Yards 2026-27"
                    ),
                    "runners": [
                        _fd_runner("Aaron Rodgers Over 3050.5", -114),
                        _fd_runner("Aaron Rodgers Under 3050.5", -114),
                    ],
                },
                "734.2": {
                    "marketId": "734.2",
                    "eventId": 28297423,
                    "marketName": "Super Bowl Winner 2026-27",
                    "runners": [_fd_runner("Chiefs", 500)],
                },
            }
        }
    }


class TestFanduelNormalize(unittest.TestCase):
    def test_season_market_extracted(self):
        rows = normalize_fanduel_response(_fd_response(), "ts")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row.keys()), set(SEASON_PROPS_SCHEMA_COLS))
        self.assertEqual(row["bookmaker"], "fanduel")
        self.assertEqual(row["market"], "season_pass_yds")
        self.assertEqual(row["player_name"], "Aaron Rodgers")
        self.assertEqual(row["line"], 3050.5)
        self.assertEqual(row["price_over"], -114)
        self.assertEqual(row["price_under"], -114)
        self.assertEqual(row["season"], 2026)

    def test_non_player_markets_ignored(self):
        rows = normalize_fanduel_response(_fd_response(), "ts")
        self.assertEqual(
            {r["market_name"] for r in rows},
            {"Aaron Rodgers Regular Season Passing Yards 2026-27"},
        )

    def test_one_sided_market_kept(self):
        payload = _fd_response()
        payload["attachments"]["markets"]["734.1"]["runners"].pop()
        rows = normalize_fanduel_response(payload, "ts")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["price_under"])

    def test_empty_payload(self):
        self.assertEqual(normalize_fanduel_response({}, "ts"), [])

    def test_fd_stat_map_targets_are_canonical(self):
        for market_key in FANDUEL_STAT_TO_MARKET.values():
            self.assertIn(market_key, SEASON_MARKETS)


class TestMarketRegistry(unittest.TestCase):
    def test_all_markets_are_player_futures_category(self):
        for key, (category_id, subcategory_id) in SEASON_MARKETS.items():
            self.assertEqual(category_id, 1759, key)
            self.assertGreater(subcategory_id, 0, key)

    def test_market_keys_are_season_scoped(self):
        for key in SEASON_MARKETS:
            self.assertTrue(key.startswith("season_"), key)

    def test_rookie_markets_are_rookie_watch_category(self):
        for key, (category_id, _) in ROOKIE_MILESTONE_MARKETS.items():
            self.assertEqual(category_id, 1801, key)
            self.assertTrue(key.startswith("rookie_"), key)

    def test_no_key_collision_between_registries(self):
        self.assertFalse(set(SEASON_MARKETS) & set(ROOKIE_MILESTONE_MARKETS))


if __name__ == "__main__":
    unittest.main()
