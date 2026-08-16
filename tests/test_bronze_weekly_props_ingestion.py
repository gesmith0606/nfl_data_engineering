"""
Tests for scripts/bronze_weekly_props_ingestion.py

Fixtures for the DK "Anytime TD Scorer" market and the DK/FD Over/Under
selection shape (``points``/``handicap`` field + ``outcomeType``) are modeled
directly on real payloads captured live against DraftKings/FanDuel on
2026-08-16 (see .planning/PROPS_DATA_PLAN.md Phase 2 dated section) — Anytime
TD Scorer had real Week 1 2026 markets posted; the five yardage/reception
markets did not yet, so those fixtures are constructed from the SAME
confirmed-live selection shape (DK's "Total" game market, which already uses
``points``/``outcomeType``) rather than captured directly. Flagged
needs-week-1-verification in the plan doc, not claimed as a live capture.

Covers:
  - parse_american_odds: unicode minus, plus prefix, numeric passthrough, bad input
  - parse_line_from_label: happy path, no match
  - discover_dk_weekly_category_ids: excludes known season/futures ids, keeps unknowns
  - normalize_dk_category: anytime TD binary rows
  - normalize_dk_category: over/under rows via `points` field
  - normalize_dk_category: over/under line fallback via label parsing
  - normalize_dk_category: unrelated market/subcategory skipped
  - normalize_dk_category: DK Rams "LAR"->"LA" abbreviation fixup applied
  - discover_fanduel_game_events: game regex match, placeholder exclusion, window filter
  - normalize_fanduel_event_markets: anytime TD binary rows
  - normalize_fanduel_event_markets: over/under rows via `handicap` field
  - normalize_fanduel_event_markets: unrelated market skipped
  - resolve_week: single match, no match, divisional-rematch disambiguation
  - finish_rows: schema columns, window filter, season inference, week attach
  - finish_rows: unresolvable week rows dropped, not mis-partitioned
  - write_weekly_props_parquet: dry run, real write, season/week partition path
  - write_weekly_props_parquet: book-tagged filename does not start with a digit
  - run_weekly_props: zero rows overall -> exit 1
  - run_weekly_props: fail-open per book -> exit 0 when one book succeeds
"""

import os
import sys
from datetime import datetime, timezone
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_weekly_props_ingestion import (  # noqa: E402
    DK_NON_WEEKLY_CATEGORY_IDS,
    PROPS_SCHEMA_COLS,
    discover_dk_weekly_category_ids,
    discover_fanduel_game_events,
    finish_rows,
    normalize_dk_category,
    normalize_fanduel_event_markets,
    parse_american_odds,
    parse_line_from_label,
    resolve_week,
    run_weekly_props,
    write_weekly_props_parquet,
)

SNAPSHOT_TS = "2026-08-16T12:00:00+00:00"


# ---------------------------------------------------------------------------
# parse_american_odds / parse_line_from_label
# ---------------------------------------------------------------------------


class TestParseAmericanOdds:
    def test_unicode_minus(self):
        assert parse_american_odds("−105") == -105

    def test_plus_prefix(self):
        assert parse_american_odds("+320") == 320

    def test_numeric_passthrough(self):
        assert parse_american_odds(-110) == -110
        assert parse_american_odds(150.0) == 150

    def test_none_and_unparseable(self):
        assert parse_american_odds(None) is None
        assert parse_american_odds("EVEN") is None


class TestParseLineFromLabel:
    def test_happy_path(self):
        assert parse_line_from_label("Over 74.5") == 74.5
        assert parse_line_from_label("Under 1,024.5") == 1024.5

    def test_no_match(self):
        assert parse_line_from_label("Yes") is None
        assert parse_line_from_label("") is None


# ---------------------------------------------------------------------------
# discover_dk_weekly_category_ids
# ---------------------------------------------------------------------------


class TestDiscoverDkWeeklyCategoryIds:
    def test_excludes_known_non_weekly_ids(self):
        league_doc = {
            "categories": [
                {"id": cid, "name": "x"} for cid in DK_NON_WEEKLY_CATEGORY_IDS
            ]
        }
        assert discover_dk_weekly_category_ids(league_doc) == []

    def test_keeps_unknown_ids(self):
        league_doc = {
            "categories": [
                {"id": 1003, "name": "TD Scorers"},
                {"id": 492, "name": "Game Lines"},
                {"id": 9999, "name": "Passing Props"},
            ]
        }
        assert sorted(discover_dk_weekly_category_ids(league_doc)) == [1003, 9999]

    def test_empty_categories(self):
        assert discover_dk_weekly_category_ids({}) == []


# ---------------------------------------------------------------------------
# normalize_dk_category — real-shape fixtures (see module docstring)
# ---------------------------------------------------------------------------


def _dk_event(event_id="34118042", home_short="SEA", away_short="NE"):
    return {
        "id": event_id,
        "name": f"{away_short} @ {home_short}",
        "startEventDate": "2026-09-10T00:15:00.0000000Z",
        "participants": [
            {
                "venueRole": "Home",
                "name": f"{home_short} Home",
                "metadata": {"shortName": home_short},
            },
            {
                "venueRole": "Away",
                "name": f"{away_short} Away",
                "metadata": {"shortName": away_short},
            },
        ],
    }


def _dk_anytime_td_category(event_id="34118042"):
    """Real-shape fixture: DK category 1003, market "Anytime TD Scorer" +
    a sibling "First TD Scorer" market that must be skipped."""
    return {
        "events": [_dk_event(event_id)],
        "categories": [{"id": 1003, "name": "TD Scorers"}],
        "subcategories": [{"id": 12438, "categoryId": 1003, "name": "TD Scorer"}],
        "markets": [
            {
                "id": "m-atd",
                "eventId": event_id,
                "name": "Anytime TD Scorer",
                "subcategoryId": 12438,
            },
            {
                "id": "m-first",
                "eventId": event_id,
                "name": "First TD Scorer",
                "subcategoryId": 12438,
            },
        ],
        "selections": [
            {
                "marketId": "m-atd",
                "label": "Jaxon Smith-Njigba",
                "outcomeType": "Anytime Scorer",
                "displayOdds": {"american": "−105"},
                "participants": [{"name": "Jaxon Smith-Njigba", "type": "Player"}],
            },
            {
                "marketId": "m-atd",
                "label": "Kenneth Walker III",
                "outcomeType": "Anytime Scorer",
                "displayOdds": {"american": "+150"},
                "participants": [{"name": "Kenneth Walker III", "type": "Player"}],
            },
            {
                "marketId": "m-first",
                "label": "Jaxon Smith-Njigba",
                "outcomeType": "First Scorer",
                "displayOdds": {"american": "+500"},
                "participants": [{"name": "Jaxon Smith-Njigba", "type": "Player"}],
            },
        ],
    }


def _dk_over_under_category(
    event_id="34118042", subcategory_name="Passing Yards", use_points=True
):
    """Constructed fixture for a weekly yardage O/U market, modeled on DK's
    confirmed-live "Total" game-market selection shape (`points` field +
    `outcomeType`) — see module docstring; not yet observed live for a
    player-level weekly market. NEEDS-WEEK-1-VERIFICATION."""
    over_sel = {
        "marketId": "m-yds",
        "label": "Over" if use_points else "Over 254.5",
        "outcomeType": "Over",
        "displayOdds": {"american": "−115"},
        "participants": [{"name": "Sam Darnold", "type": "Player"}],
    }
    under_sel = {
        "marketId": "m-yds",
        "label": "Under" if use_points else "Under 254.5",
        "outcomeType": "Under",
        "displayOdds": {"american": "−105"},
        "participants": [{"name": "Sam Darnold", "type": "Player"}],
    }
    if use_points:
        over_sel["points"] = 254.5
        under_sel["points"] = 254.5

    return {
        "events": [_dk_event(event_id)],
        "categories": [{"id": 9999, "name": "Passing Props"}],
        "subcategories": [{"id": 88001, "categoryId": 9999, "name": subcategory_name}],
        "markets": [
            {
                "id": "m-yds",
                "eventId": event_id,
                "name": "Passing Yards",
                "subcategoryId": 88001,
            }
        ],
        "selections": [over_sel, under_sel],
    }


class TestNormalizeDkCategoryAnytimeTd:
    def test_two_rows_for_anytime_td_market(self):
        rows = normalize_dk_category(_dk_anytime_td_category(), SNAPSHOT_TS)
        atd_rows = [r for r in rows if r["market"] == "player_anytime_td"]
        assert len(atd_rows) == 2

    def test_price_and_no_under_no_line(self):
        rows = normalize_dk_category(_dk_anytime_td_category(), SNAPSHOT_TS)
        row = next(r for r in rows if r["player_name"] == "Jaxon Smith-Njigba")
        assert row["price_over"] == -105
        assert row["price_under"] is None
        assert row["line"] is None

    def test_first_td_scorer_market_skipped(self):
        rows = normalize_dk_category(_dk_anytime_td_category(), SNAPSHOT_TS)
        assert all(r["market"] != "First TD Scorer" for r in rows)
        assert len(rows) == 2  # only the 2 Anytime Scorer selections

    def test_team_info_attached(self):
        rows = normalize_dk_category(_dk_anytime_td_category(), SNAPSHOT_TS)
        row = rows[0]
        assert row["home_team_nfl"] == "SEA"
        assert row["away_team_nfl"] == "NE"
        assert row["bookmaker"] == "draftkings"

    def test_lar_fixed_up_to_la(self):
        # Build a Rams-home fixture explicitly to exercise the fixup.
        data = _dk_anytime_td_category("evX")
        data["events"][0]["participants"][0]["metadata"]["shortName"] = "LAR"
        rows = normalize_dk_category(data, SNAPSHOT_TS)
        assert rows[0]["home_team_nfl"] == "LA"


class TestNormalizeDkCategoryOverUnder:
    def test_one_row_per_player_via_points_field(self):
        rows = normalize_dk_category(
            _dk_over_under_category(use_points=True), SNAPSHOT_TS
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["market"] == "player_pass_yds"
        assert row["player_name"] == "Sam Darnold"
        assert row["line"] == 254.5
        assert row["price_over"] == -115
        assert row["price_under"] == -105

    def test_line_fallback_from_label(self):
        rows = normalize_dk_category(
            _dk_over_under_category(use_points=False), SNAPSHOT_TS
        )
        assert len(rows) == 1
        assert rows[0]["line"] == 254.5

    def test_subcategory_name_maps_to_market_key(self):
        for subcat, expected in [
            ("Passing Yards", "player_pass_yds"),
            ("Passing TDs", "player_pass_tds"),
            ("Rushing Yards", "player_rush_yds"),
            ("Receiving Yards", "player_reception_yds"),
            ("Receptions", "player_receptions"),
        ]:
            rows = normalize_dk_category(
                _dk_over_under_category(subcategory_name=subcat), SNAPSHOT_TS
            )
            assert rows[0]["market"] == expected

    def test_unmapped_subcategory_skipped(self):
        rows = normalize_dk_category(
            _dk_over_under_category(subcategory_name="Something Else"), SNAPSHOT_TS
        )
        assert rows == []

    def test_empty_payload(self):
        assert normalize_dk_category({}, SNAPSHOT_TS) == []


# ---------------------------------------------------------------------------
# FanDuel discovery + normalize
# ---------------------------------------------------------------------------


def _fd_nfl_page(events):
    return {"attachments": {"events": events}}


class TestDiscoverFanduelGameEvents:
    def test_game_event_matched_and_mapped(self):
        events = {
            "111": {
                "name": "Seattle Seahawks @ San Francisco 49ers",
                "openDate": "2026-09-11T00:35:00.000Z",
            }
        }
        games = discover_fanduel_game_events(
            _fd_nfl_page(events),
            days_ahead=30,
            now=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )
        assert len(games) == 1
        assert games[0]["away_nfl"] == "SEA"
        assert games[0]["home_nfl"] == "SF"

    def test_placeholder_events_excluded(self):
        events = {
            "1": {"name": "NFL Futures", "openDate": "2026-09-11T00:35:00.000Z"},
            "2": {"name": "NFL Draft", "openDate": "2026-09-11T00:35:00.000Z"},
            "3": {"name": "NFL Player Awards", "openDate": "2030-12-30T12:00:00.000Z"},
        }
        games = discover_fanduel_game_events(
            _fd_nfl_page(events),
            days_ahead=365,
            now=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )
        assert games == []

    def test_outside_window_excluded(self):
        events = {
            "1": {
                "name": "Dallas Cowboys @ New York Giants",
                "openDate": "2026-12-25T00:00:00.000Z",
            }
        }
        games = discover_fanduel_game_events(
            _fd_nfl_page(events),
            days_ahead=8,
            now=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )
        assert games == []

    def test_malformed_open_date_skipped(self):
        events = {"1": {"name": "Dallas Cowboys @ New York Giants", "openDate": "bad"}}
        games = discover_fanduel_game_events(
            _fd_nfl_page(events),
            days_ahead=30,
            now=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )
        assert games == []


_FD_GAME = {
    "event_id": "999",
    "away_team": "New England Patriots",
    "home_team": "Seattle Seahawks",
    "away_nfl": "NE",
    "home_nfl": "SEA",
    "commence_time": "2026-09-10T00:15:00.000Z",
}


def _fd_event_page_anytime_td():
    """Real-shape fixture: FANDUEL_ANYTIME_TD_MARKET_TYPE is confirmed present
    in FanDuel's live market-blurb catalog (2026-08-16 probe) though not yet
    a live selectable market — see module docstring."""
    return {
        "attachments": {
            "markets": {
                "1": {
                    "marketName": "Anytime Touchdown Scorer",
                    "marketType": "ANY_TIME_TOUCHDOWN_SCORER",
                    "runners": [
                        {
                            "runnerName": "Kenneth Walker III",
                            "winRunnerOdds": {
                                "americanDisplayOdds": {"americanOdds": 150}
                            },
                        }
                    ],
                }
            }
        }
    }


def _fd_event_page_over_under():
    """Constructed fixture modeled on FanDuel's confirmed-live "Total Match
    Points" selection shape (`handicap` field + Over/Under runnerName).
    NEEDS-WEEK-1-VERIFICATION for the exact per-player marketName format."""
    return {
        "attachments": {
            "markets": {
                "1": {
                    "marketName": "Sam Darnold Passing Yards",
                    "marketType": "PLAYER_PASSING_YARDS_(OVER/UNDER)",
                    "runners": [
                        {
                            "runnerName": "Over",
                            "handicap": 254.5,
                            "winRunnerOdds": {
                                "americanDisplayOdds": {"americanOdds": -115}
                            },
                        },
                        {
                            "runnerName": "Under",
                            "handicap": 254.5,
                            "winRunnerOdds": {
                                "americanDisplayOdds": {"americanOdds": -105}
                            },
                        },
                    ],
                },
                "2": {
                    "marketName": "Moneyline",
                    "marketType": "MONEY_LINE",
                    "runners": [{"runnerName": "Seattle Seahawks", "handicap": 0}],
                },
            }
        }
    }


class TestNormalizeFanduelEventMarkets:
    def test_anytime_td_row(self):
        rows = normalize_fanduel_event_markets(
            _fd_event_page_anytime_td(), _FD_GAME, SNAPSHOT_TS
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["market"] == "player_anytime_td"
        assert row["player_name"] == "Kenneth Walker III"
        assert row["price_over"] == 150
        assert row["price_under"] is None
        assert row["line"] is None
        assert row["bookmaker"] == "fanduel"

    def test_over_under_row(self):
        rows = normalize_fanduel_event_markets(
            _fd_event_page_over_under(), _FD_GAME, SNAPSHOT_TS
        )
        pass_rows = [r for r in rows if r["market"] == "player_pass_yds"]
        assert len(pass_rows) == 1
        row = pass_rows[0]
        assert row["player_name"] == "Sam Darnold"
        assert row["line"] == 254.5
        assert row["price_over"] == -115
        assert row["price_under"] == -105

    def test_moneyline_market_skipped(self):
        rows = normalize_fanduel_event_markets(
            _fd_event_page_over_under(), _FD_GAME, SNAPSHOT_TS
        )
        assert all(r["market"] != "MONEY_LINE" for r in rows)

    def test_empty_payload(self):
        assert normalize_fanduel_event_markets({}, _FD_GAME, SNAPSHOT_TS) == []


# ---------------------------------------------------------------------------
# resolve_week
# ---------------------------------------------------------------------------


class TestResolveWeek:
    def _schedule(self):
        return pd.DataFrame(
            [
                {
                    "week": 1,
                    "gameday": "2026-09-10",
                    "home_team": "SEA",
                    "away_team": "NE",
                },
                {
                    "week": 3,
                    "gameday": "2026-09-24",
                    "home_team": "SEA",
                    "away_team": "ARI",
                },
                {
                    "week": 15,
                    "gameday": "2026-12-14",
                    "home_team": "ARI",
                    "away_team": "SEA",
                },
            ]
        )

    def test_single_match(self):
        wk = resolve_week(self._schedule(), "SEA", "NE", "2026-09-10T00:15:00Z")
        assert wk == 1

    def test_home_away_swap_still_matches(self):
        wk = resolve_week(self._schedule(), "NE", "SEA", "2026-09-10T00:15:00Z")
        assert wk == 1

    def test_no_match_returns_none(self):
        wk = resolve_week(self._schedule(), "KC", "BUF", "2026-09-10T00:15:00Z")
        assert wk is None

    def test_missing_team_returns_none(self):
        assert (
            resolve_week(self._schedule(), None, "NE", "2026-09-10T00:15:00Z") is None
        )

    def test_empty_schedule_returns_none(self):
        empty = pd.DataFrame(columns=["week", "gameday", "home_team", "away_team"])
        assert resolve_week(empty, "SEA", "NE", "2026-09-10T00:15:00Z") is None

    def test_divisional_rematch_disambiguated_by_nearest_date(self):
        wk_early = resolve_week(self._schedule(), "SEA", "ARI", "2026-09-25T00:00:00Z")
        wk_late = resolve_week(self._schedule(), "ARI", "SEA", "2026-12-15T00:00:00Z")
        assert wk_early == 3
        assert wk_late == 15


# ---------------------------------------------------------------------------
# finish_rows
# ---------------------------------------------------------------------------


def _raw_row(commence_time="2026-09-10T00:15:00Z", home="SEA", away="NE"):
    return {
        "snapshot_ts": SNAPSHOT_TS,
        "event_id": "e1",
        "commence_time": commence_time,
        "home_team": f"{home} Home",
        "away_team": f"{away} Away",
        "home_team_nfl": home,
        "away_team_nfl": away,
        "bookmaker": "draftkings",
        "market": "player_anytime_td",
        "player_name": "Test Player",
        "line": None,
        "price_over": -110,
        "price_under": None,
    }


class TestFinishRows:
    def _fake_schedule(self, monkeypatch):
        df = pd.DataFrame(
            [
                {
                    "week": 1,
                    "gameday": "2026-09-10",
                    "home_team": "SEA",
                    "away_team": "NE",
                }
            ]
        )
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.load_schedule_lookup",
            lambda season: df,
        )

    def test_schema_columns(self, monkeypatch):
        self._fake_schedule(monkeypatch)
        out = finish_rows(
            [_raw_row()], days_ahead=30, now=datetime(2026, 8, 16, tzinfo=timezone.utc)
        )
        assert list(out.columns) == PROPS_SCHEMA_COLS + ["week"]

    def test_season_and_week_attached(self, monkeypatch):
        self._fake_schedule(monkeypatch)
        out = finish_rows(
            [_raw_row()], days_ahead=30, now=datetime(2026, 8, 16, tzinfo=timezone.utc)
        )
        assert out.iloc[0]["season"] == 2026
        assert out.iloc[0]["week"] == 1

    def test_outside_window_dropped(self, monkeypatch):
        self._fake_schedule(monkeypatch)
        out = finish_rows(
            [_raw_row()], days_ahead=2, now=datetime(2026, 8, 16, tzinfo=timezone.utc)
        )
        assert out.empty

    def test_unresolvable_week_dropped(self, monkeypatch):
        empty_df = pd.DataFrame(columns=["week", "gameday", "home_team", "away_team"])
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.load_schedule_lookup",
            lambda season: empty_df,
        )
        out = finish_rows(
            [_raw_row()], days_ahead=30, now=datetime(2026, 8, 16, tzinfo=timezone.utc)
        )
        assert out.empty

    def test_empty_input(self, monkeypatch):
        self._fake_schedule(monkeypatch)
        out = finish_rows([], days_ahead=30)
        assert out.empty
        assert list(out.columns) == PROPS_SCHEMA_COLS + ["week"]


# ---------------------------------------------------------------------------
# write_weekly_props_parquet
# ---------------------------------------------------------------------------


class TestWriteWeeklyPropsParquet:
    def _df(self):
        return pd.DataFrame(
            [_raw_row()] * 2, columns=list(_raw_row().keys()) + ["season"]
        ).assign(season=2026)[PROPS_SCHEMA_COLS]

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.BRONZE_WEEKLY_PROPS_DIR",
            str(tmp_path / "props"),
        )
        write_weekly_props_parquet(self._df(), 2026, 1, "dk", dry_run=True)
        assert list(tmp_path.rglob("*.parquet")) == []

    def test_writes_file_with_season_week_partition(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.BRONZE_WEEKLY_PROPS_DIR",
            str(tmp_path / "props"),
        )
        out_path = write_weekly_props_parquet(self._df(), 2026, 1, "dk", dry_run=False)
        assert os.path.exists(out_path)
        assert os.path.join("season=2026", "week=1") in out_path
        loaded = pd.read_parquet(out_path)
        assert list(loaded.columns) == PROPS_SCHEMA_COLS

    def test_book_tagged_filename_does_not_start_with_digit(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.BRONZE_WEEKLY_PROPS_DIR",
            str(tmp_path / "props"),
        )
        out_path = write_weekly_props_parquet(self._df(), 2026, 1, "fd", dry_run=False)
        fname = os.path.basename(out_path)
        assert fname.startswith("props_fd_")
        assert not fname.split("props_")[1][0].isdigit()

    def test_filename_never_matches_archive_ignore_pattern(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.BRONZE_WEEKLY_PROPS_DIR",
            str(tmp_path / "props"),
        )
        out_path = write_weekly_props_parquet(self._df(), 2026, 1, "dk", dry_run=False)
        assert not os.path.basename(out_path).startswith("props_archive_")


# ---------------------------------------------------------------------------
# run_weekly_props — exit code contract
# ---------------------------------------------------------------------------


class TestRunWeeklyPropsExitCode:
    def test_zero_rows_overall_exits_1(self, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.run_draftkings", lambda *a, **kw: []
        )
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.run_fanduel", lambda *a, **kw: []
        )
        assert run_weekly_props(dry_run=True) == 1

    def test_one_book_succeeding_exits_0(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.BRONZE_WEEKLY_PROPS_DIR",
            str(tmp_path / "props"),
        )
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.run_draftkings",
            lambda *a, **kw: [_raw_row()],
        )
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.run_fanduel", lambda *a, **kw: []
        )
        schedule_df = pd.DataFrame(
            [
                {
                    "week": 1,
                    "gameday": "2026-09-10",
                    "home_team": "SEA",
                    "away_team": "NE",
                }
            ]
        )
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.load_schedule_lookup",
            lambda season: schedule_df,
        )
        assert run_weekly_props(days_ahead=365, dry_run=True) == 0

    def test_skip_flags_short_circuit_book(self, monkeypatch):
        calls = {"dk": 0, "fd": 0}

        def fake_dk(*a, **kw):
            calls["dk"] += 1
            return []

        def fake_fd(*a, **kw):
            calls["fd"] += 1
            return []

        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.run_draftkings", fake_dk
        )
        monkeypatch.setattr(
            "scripts.bronze_weekly_props_ingestion.run_fanduel", fake_fd
        )
        run_weekly_props(dry_run=True, skip_draftkings=True, skip_fanduel=True)
        assert calls == {"dk": 0, "fd": 0}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
