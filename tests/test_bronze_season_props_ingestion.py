"""
Unit tests for Bronze season player props ingestion (DraftKings futures).
"""

import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bronze_season_props_ingestion import (  # noqa: E402
    SEASON_MARKETS,
    SEASON_PROPS_SCHEMA_COLS,
    extract_team_nfl,
    normalize_subcategory_response,
    parse_american_odds,
    parse_event_name,
    parse_line_from_label,
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


class TestMarketRegistry(unittest.TestCase):
    def test_all_markets_are_player_futures_category(self):
        for key, (category_id, subcategory_id) in SEASON_MARKETS.items():
            self.assertEqual(category_id, 1759, key)
            self.assertGreater(subcategory_id, 0, key)

    def test_market_keys_are_season_scoped(self):
        for key in SEASON_MARKETS:
            self.assertTrue(key.startswith("season_"), key)


if __name__ == "__main__":
    unittest.main()
