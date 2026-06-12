"""
Tests for scripts/bronze_props_ingestion.py

Covers:
  - estimate_credits: zero events, one market, five markets
  - filter_events_by_window: within window, outside window, boundary, past event
  - filter_events_by_window: missing/malformed commence_time
  - normalize_event_props: binary market (player_anytime_td) row shape
  - normalize_event_props: binary market — player_name from description
  - normalize_event_props: binary market — price_under is None
  - normalize_event_props: over/under market — paired rows, line extracted
  - normalize_event_props: over/under market — unpaired (only Over) outcome
  - normalize_event_props: missing bookmakers returns empty list
  - normalize_event_props: unmapped team name sets None + emits WARNING
  - normalize_event_props: season correctly inferred from commence_time
  - normalize_event_props: multiple bookmakers produce correct row count
  - normalize_event_props: multiple markets in one event
  - normalize_props_response: returns DataFrame with PROPS_SCHEMA_COLS
  - normalize_props_response: empty event (no bookmakers) → empty DataFrame with schema
  - normalize_props_response: unmapped team warning logged
  - write_props_parquet: dry_run does not create file
  - write_props_parquet: writes Parquet with correct columns and row count
  - write_props_parquet: season partition directory name
  - run_props: credit budget guard — aborts when estimated > max_credits
  - run_props: credit budget guard — passes when estimated == max_credits
  - run_props: mid-run reserve guard stops when remaining <= threshold
  - run_props: fail-open on events fetch error (returns 0)
  - run_props: fail-open on per-event props HTTP error (skips event, continues)
  - run_props: no events in window returns 0 without props fetch
  - run_props: dry_run makes no per-event calls and writes no files
  - run_props: full round-trip writes Parquet for anytime_td
  - run_props: full round-trip writes Parquet for over/under market
  - run_props: January game partitioned into prior season
  - run_props: empty bookmakers (no props posted yet) returns 0, no file
"""

import logging
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_props_ingestion import (
    BINARY_MARKETS,
    CREDIT_RESERVE_THRESHOLD,
    DEFAULT_MARKETS,
    PROPS_SCHEMA_COLS,
    estimate_credits,
    fetch_event_props,
    filter_events_by_window,
    normalize_event_props,
    normalize_props_response,
    run_props,
    write_props_parquet,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Regular-season game: SEA vs NE, 2026 season
SAMPLE_EVENT_META: dict = {
    "id": "8c94552d022acec4a0458d70c19d3da9",
    "sport_key": "americanfootball_nfl",
    "sport_title": "NFL",
    "commence_time": "2026-09-10T00:15:00Z",
    "home_team": "Seattle Seahawks",
    "away_team": "New England Patriots",
}

# Full event dict with anytime_td bookmakers (matching live API shape)
SAMPLE_EVENT_ANYTIME_TD: dict = {
    **SAMPLE_EVENT_META,
    "bookmakers": [
        {
            "key": "draftkings",
            "title": "DraftKings",
            "markets": [
                {
                    "key": "player_anytime_td",
                    "last_update": "2026-06-12T16:28:21Z",
                    "outcomes": [
                        {
                            "name": "Yes",
                            "description": "Jaxon Smith-Njigba",
                            "price": -110,
                        },
                        {
                            "name": "Yes",
                            "description": "Rhamondre Stevenson",
                            "price": 130,
                        },
                        {
                            "name": "Yes",
                            "description": "TreVeyon Henderson",
                            "price": 170,
                        },
                    ],
                }
            ],
        }
    ],
}

# Full event dict with over/under market (reception_yds structure)
SAMPLE_EVENT_RECEPTION_YDS: dict = {
    **SAMPLE_EVENT_META,
    "bookmakers": [
        {
            "key": "fanduel",
            "title": "FanDuel",
            "markets": [
                {
                    "key": "player_reception_yds",
                    "last_update": "2026-09-09T18:00:00Z",
                    "outcomes": [
                        {
                            "name": "Over",
                            "description": "Jaxon Smith-Njigba",
                            "point": 74.5,
                            "price": -115,
                        },
                        {
                            "name": "Under",
                            "description": "Jaxon Smith-Njigba",
                            "point": 74.5,
                            "price": -105,
                        },
                        {
                            "name": "Over",
                            "description": "DK Metcalf",
                            "point": 62.5,
                            "price": -110,
                        },
                        {
                            "name": "Under",
                            "description": "DK Metcalf",
                            "point": 62.5,
                            "price": -110,
                        },
                    ],
                }
            ],
        }
    ],
}

# Event with no bookmakers posted yet
SAMPLE_EVENT_NO_BOOKMAKERS: dict = {
    **SAMPLE_EVENT_META,
    "bookmakers": [],
}

SNAPSHOT_TS = "2026-09-09T12:00:00+00:00"

# Reference "now" for window-filter tests: just before the SEA/NE kickoff
NOW_BEFORE_GAME = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# estimate_credits
# ---------------------------------------------------------------------------


class TestEstimateCredits:
    def test_zero_events_costs_zero(self):
        assert estimate_credits(0, ["player_anytime_td"]) == 0

    def test_one_event_one_market(self):
        assert estimate_credits(1, ["player_anytime_td"]) == 1

    def test_five_events_five_markets(self):
        assert estimate_credits(5, DEFAULT_MARKETS) == 25

    def test_regions_multiplier(self):
        assert estimate_credits(2, ["player_rush_yds"], regions=2) == 4

    def test_matches_event_times_market_times_region(self):
        assert estimate_credits(3, ["a", "b", "c"], regions=1) == 9


# ---------------------------------------------------------------------------
# filter_events_by_window
# ---------------------------------------------------------------------------


class TestFilterEventsByWindow:
    def _make_event(self, commence_time: str, event_id: str = "x") -> dict:
        return {"id": event_id, "commence_time": commence_time}

    def test_event_within_window_is_included(self):
        events = [self._make_event("2026-09-10T00:15:00Z")]
        result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 1

    def test_event_outside_window_is_excluded(self):
        # 30 days away from reference now
        events = [self._make_event("2026-10-09T20:00:00Z")]
        result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 0

    def test_past_event_is_excluded(self):
        events = [self._make_event("2026-09-01T20:00:00Z")]
        result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 0

    def test_event_at_boundary_is_included(self):
        # Exactly 7 days from now
        events = [self._make_event("2026-09-16T12:00:00Z")]
        result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 1

    def test_missing_commence_time_skipped(self, caplog):
        events = [{"id": "bad", "commence_time": ""}]
        with caplog.at_level(logging.WARNING):
            result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 0
        assert any("missing" in m.lower() for m in caplog.messages)

    def test_malformed_commence_time_skipped(self, caplog):
        events = [{"id": "bad2", "commence_time": "not-a-date"}]
        with caplog.at_level(logging.WARNING):
            result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 0

    def test_multiple_events_mixed(self):
        events = [
            self._make_event("2026-09-10T00:15:00Z", "in1"),
            self._make_event("2026-09-11T17:00:00Z", "in2"),
            self._make_event("2026-10-01T20:00:00Z", "out1"),
        ]
        result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert len(result) == 2
        ids = [e["id"] for e in result]
        assert "in1" in ids and "in2" in ids

    def test_results_sorted_by_commence_time(self):
        events = [
            self._make_event("2026-09-14T20:00:00Z", "later"),
            self._make_event("2026-09-10T00:15:00Z", "earlier"),
        ]
        result = filter_events_by_window(events, days_ahead=7, now=NOW_BEFORE_GAME)
        assert result[0]["id"] == "earlier"
        assert result[1]["id"] == "later"


# ---------------------------------------------------------------------------
# normalize_event_props — binary markets (player_anytime_td)
# ---------------------------------------------------------------------------


class TestNormalizeEventPropsBinaryMarket:
    def test_returns_one_row_per_player(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert len(rows) == 3

    def test_player_name_from_description(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        names = {r["player_name"] for r in rows}
        assert "Jaxon Smith-Njigba" in names
        assert "Rhamondre Stevenson" in names
        assert "TreVeyon Henderson" in names

    def test_price_under_is_none(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["price_under"] is None for r in rows)

    def test_line_is_none(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["line"] is None for r in rows)

    def test_price_over_matches_api(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        jsn_row = next(r for r in rows if r["player_name"] == "Jaxon Smith-Njigba")
        assert jsn_row["price_over"] == -110

    def test_market_key_set(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["market"] == "player_anytime_td" for r in rows)

    def test_bookmaker_key_set(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["bookmaker"] == "draftkings" for r in rows)

    def test_team_abbreviations_set(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["home_team_nfl"] == "SEA" for r in rows)
        assert all(r["away_team_nfl"] == "NE" for r in rows)

    def test_season_inferred(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["season"] == 2026 for r in rows)

    def test_snapshot_ts_propagated(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["snapshot_ts"] == SNAPSHOT_TS for r in rows)

    def test_event_id_set(self):
        rows = normalize_event_props(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert all(r["event_id"] == SAMPLE_EVENT_META["id"] for r in rows)


# ---------------------------------------------------------------------------
# normalize_event_props — over/under markets (player_reception_yds)
# ---------------------------------------------------------------------------


class TestNormalizeEventPropsOverUnderMarket:
    def test_one_row_per_player(self):
        # 2 players × 1 bookmaker = 2 rows
        rows = normalize_event_props(SAMPLE_EVENT_RECEPTION_YDS, SNAPSHOT_TS)
        assert len(rows) == 2

    def test_line_extracted(self):
        rows = normalize_event_props(SAMPLE_EVENT_RECEPTION_YDS, SNAPSHOT_TS)
        jsn = next(r for r in rows if r["player_name"] == "Jaxon Smith-Njigba")
        assert jsn["line"] == 74.5

    def test_price_over_and_under_set(self):
        rows = normalize_event_props(SAMPLE_EVENT_RECEPTION_YDS, SNAPSHOT_TS)
        jsn = next(r for r in rows if r["player_name"] == "Jaxon Smith-Njigba")
        assert jsn["price_over"] == -115
        assert jsn["price_under"] == -105

    def test_unpaired_outcome_only_over(self):
        """If only an Over outcome exists for a player, price_under stays None."""
        event = {
            **SAMPLE_EVENT_META,
            "bookmakers": [
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "player_reception_yds",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Solo Player",
                                    "point": 50.5,
                                    "price": -110,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        rows = normalize_event_props(event, SNAPSHOT_TS)
        assert len(rows) == 1
        assert rows[0]["price_over"] == -110
        assert rows[0]["price_under"] is None
        assert rows[0]["line"] == 50.5

    def test_market_key_set(self):
        rows = normalize_event_props(SAMPLE_EVENT_RECEPTION_YDS, SNAPSHOT_TS)
        assert all(r["market"] == "player_reception_yds" for r in rows)


# ---------------------------------------------------------------------------
# normalize_event_props — edge cases
# ---------------------------------------------------------------------------


class TestNormalizeEventPropsEdgeCases:
    def test_empty_bookmakers_returns_empty_list(self):
        rows = normalize_event_props(SAMPLE_EVENT_NO_BOOKMAKERS, SNAPSHOT_TS)
        assert rows == []

    def test_unmapped_home_team_sets_none(self, caplog):
        event = {
            **SAMPLE_EVENT_ANYTIME_TD,
            "home_team": "Springfield Isotopes",
        }
        with caplog.at_level(logging.WARNING):
            rows = normalize_event_props(event, SNAPSHOT_TS)
        assert all(r["home_team_nfl"] is None for r in rows)
        assert any("Springfield Isotopes" in m for m in caplog.messages)

    def test_unmapped_away_team_sets_none(self, caplog):
        event = {
            **SAMPLE_EVENT_ANYTIME_TD,
            "away_team": "Unknown Team",
        }
        with caplog.at_level(logging.WARNING):
            rows = normalize_event_props(event, SNAPSHOT_TS)
        assert all(r["away_team_nfl"] is None for r in rows)

    def test_january_playoff_game_season(self):
        event = {
            "id": "playoff1",
            "commence_time": "2027-01-15T21:00:00Z",
            "home_team": "Kansas City Chiefs",
            "away_team": "Buffalo Bills",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "player_anytime_td",
                            "outcomes": [
                                {
                                    "name": "Yes",
                                    "description": "Patrick Mahomes",
                                    "price": 280,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        rows = normalize_event_props(event, SNAPSHOT_TS)
        assert all(r["season"] == 2026 for r in rows)

    def test_multiple_bookmakers_gives_rows_per_book(self):
        event = {
            **SAMPLE_EVENT_META,
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "player_anytime_td",
                            "outcomes": [
                                {"name": "Yes", "description": "Player A", "price": -110}
                            ],
                        }
                    ],
                },
                {
                    "key": "fanduel",
                    "markets": [
                        {
                            "key": "player_anytime_td",
                            "outcomes": [
                                {"name": "Yes", "description": "Player A", "price": -115}
                            ],
                        }
                    ],
                },
            ],
        }
        rows = normalize_event_props(event, SNAPSHOT_TS)
        assert len(rows) == 2
        bookmakers = {r["bookmaker"] for r in rows}
        assert bookmakers == {"draftkings", "fanduel"}

    def test_multiple_markets_in_one_event(self):
        event = {
            **SAMPLE_EVENT_META,
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "player_anytime_td",
                            "outcomes": [
                                {"name": "Yes", "description": "Player A", "price": -110}
                            ],
                        },
                        {
                            "key": "player_rush_yds",
                            "outcomes": [
                                {
                                    "name": "Over",
                                    "description": "Player B",
                                    "point": 45.5,
                                    "price": -115,
                                },
                                {
                                    "name": "Under",
                                    "description": "Player B",
                                    "point": 45.5,
                                    "price": -105,
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        rows = normalize_event_props(event, SNAPSHOT_TS)
        markets = {r["market"] for r in rows}
        assert "player_anytime_td" in markets
        assert "player_rush_yds" in markets
        # 1 TD row + 1 rush row = 2 total
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# normalize_props_response
# ---------------------------------------------------------------------------


class TestNormalizePropsResponse:
    def test_returns_dataframe(self):
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert isinstance(df, pd.DataFrame)

    def test_schema_columns_present(self):
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert set(df.columns) == set(PROPS_SCHEMA_COLS)

    def test_correct_row_count_anytime_td(self):
        # 3 outcomes × 1 bookmaker = 3 rows
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        assert len(df) == 3

    def test_empty_event_returns_empty_df_with_schema(self):
        df = normalize_props_response(SAMPLE_EVENT_NO_BOOKMAKERS, SNAPSHOT_TS)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert set(df.columns) == set(PROPS_SCHEMA_COLS)

    def test_unmapped_team_warning_in_response(self, caplog):
        event = {
            **SAMPLE_EVENT_ANYTIME_TD,
            "away_team": "Springfield Isotopes",
        }
        with caplog.at_level(logging.WARNING):
            normalize_props_response(event, SNAPSHOT_TS)
        assert any("Springfield Isotopes" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# write_props_parquet
# ---------------------------------------------------------------------------


class TestWritePropsParquet:
    def test_dry_run_does_not_write_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR",
            str(tmp_path / "props"),
        )
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        write_props_parquet(df, season=2026, dry_run=True)
        assert list(tmp_path.rglob("*.parquet")) == []

    def test_writes_parquet_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR",
            str(tmp_path / "props"),
        )
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        out_path = write_props_parquet(df, season=2026, dry_run=False)
        assert os.path.exists(out_path)
        loaded = pd.read_parquet(out_path)
        assert len(loaded) == len(df)

    def test_season_partition_in_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR",
            str(tmp_path / "props"),
        )
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        out_path = write_props_parquet(df, season=2026, dry_run=False)
        assert "season=2026" in out_path

    def test_parquet_filename_starts_with_props(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR",
            str(tmp_path / "props"),
        )
        df = normalize_props_response(SAMPLE_EVENT_ANYTIME_TD, SNAPSHOT_TS)
        out_path = write_props_parquet(df, season=2026, dry_run=False)
        assert os.path.basename(out_path).startswith("props_")


# ---------------------------------------------------------------------------
# run_props — credit budget guard
# ---------------------------------------------------------------------------


class TestRunPropsCreditGuard:
    def _make_events_response(self, event_count: int = 5) -> list:
        """Generate a list of upcoming events within default window."""
        events = []
        for i in range(event_count):
            events.append(
                {
                    "id": f"event{i}",
                    "commence_time": "2026-09-10T17:00:00Z",
                    "home_team": "Kansas City Chiefs",
                    "away_team": "Baltimore Ravens",
                }
            )
        return events

    def _mock_events_fetch(self, monkeypatch, events: list) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = events
        mock_resp.headers = {"x-requests-remaining": "400", "x-requests-used": "100"}
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.requests.get",
            lambda *a, **kw: mock_resp,
        )

    def test_aborts_when_estimated_over_budget(self, monkeypatch):
        """12 events × 5 markets = 60 credits; budget is 59 → abort."""
        events = self._make_events_response(12)
        self._mock_events_fetch(monkeypatch, events)
        exit_code = run_props(
            api_key="test_key",
            markets=DEFAULT_MARKETS,
            days_ahead=365,  # wide window so all 12 events pass filter
            max_credits=59,
        )
        assert exit_code == 1

    def test_passes_when_estimated_equals_budget(self, monkeypatch, tmp_path):
        """12 events × 5 markets = 60 credits; budget is 60 → proceed."""
        events = self._make_events_response(12)

        # Need per-event props mock too
        call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            # First call = events list; subsequent = per-event props
            if call_count["n"] == 0:
                mock_resp.json.return_value = events
            else:
                mock_resp.json.return_value = {
                    **SAMPLE_EVENT_ANYTIME_TD,
                    "id": f"event{call_count['n']}",
                }
            mock_resp.headers = {
                "x-requests-remaining": "300",
                "x-requests-used": "200",
            }
            call_count["n"] += 1
            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        exit_code = run_props(
            api_key="test_key",
            markets=DEFAULT_MARKETS,
            days_ahead=365,  # wide window — this test is about budget, not time filter
            max_credits=60,
        )
        assert exit_code == 0

    def test_no_events_in_window_returns_zero_no_props_call(self, monkeypatch):
        """If no events match the window, no per-event calls are made."""
        # Use events far in the future (365 days) with default 7-day window
        far_events = [
            {
                "id": "future1",
                "commence_time": "2027-09-10T17:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Baltimore Ravens",
            }
        ]

        get_call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            get_call_count["n"] += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = far_events
            mock_resp.headers = {"x-requests-remaining": "400"}
            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)
        exit_code = run_props(api_key="test_key", days_ahead=7)
        assert exit_code == 0
        # Only the events-list fetch should have been made
        assert get_call_count["n"] == 1


# ---------------------------------------------------------------------------
# run_props — mid-run reserve guard
# ---------------------------------------------------------------------------


class TestRunPropsMidRunReserveGuard:
    def test_stops_when_remaining_at_threshold(self, monkeypatch, tmp_path):
        """If x-requests-remaining drops to CREDIT_RESERVE_THRESHOLD, stop."""
        events_list = [
            {
                "id": f"ev{i}",
                "commence_time": "2026-09-10T17:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Baltimore Ravens",
            }
            for i in range(3)
        ]

        call_idx = {"n": 0}

        def fake_get(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            idx = call_idx["n"]
            call_idx["n"] += 1

            if idx == 0:
                # events list
                mock_resp.json.return_value = events_list
                mock_resp.headers = {"x-requests-remaining": "200"}
            elif idx == 1:
                # first event props — plenty remaining
                mock_resp.json.return_value = {
                    **SAMPLE_EVENT_ANYTIME_TD,
                    "id": "ev0",
                }
                mock_resp.headers = {
                    "x-requests-remaining": str(CREDIT_RESERVE_THRESHOLD),
                    "x-requests-used": "50",
                }
            else:
                # should never be called — guard should have stopped
                raise AssertionError("Should not have called beyond reserve threshold")

            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        exit_code = run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=365,  # wide window — this test is about the reserve guard, not time filter
            max_credits=200,
        )
        # Should succeed (data from first event was written) but stopped early
        assert exit_code == 0
        # Only 2 HTTP calls should have been made (events list + 1 event)
        assert call_idx["n"] == 2


# ---------------------------------------------------------------------------
# run_props — fail-open scenarios
# ---------------------------------------------------------------------------


class TestRunPropsFailOpen:
    def test_events_fetch_network_error_returns_zero(self, monkeypatch):
        import requests as req_module

        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.requests.get",
            lambda *a, **kw: (_ for _ in ()).throw(
                req_module.ConnectionError("timeout")
            ),
        )
        exit_code = run_props(api_key="test_key")
        assert exit_code == 0

    def test_per_event_http_error_skips_event_continues(self, monkeypatch, tmp_path):
        """A 404 on one event should skip it and continue to the next."""
        import requests as req_module

        events = [
            {
                "id": "good_event",
                "commence_time": "2026-09-10T17:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Baltimore Ravens",
            },
            {
                "id": "bad_event",
                "commence_time": "2026-09-10T20:00:00Z",
                "home_team": "Seattle Seahawks",
                "away_team": "New England Patriots",
            },
        ]

        call_idx = {"n": 0}

        def fake_get(*args, **kwargs):
            idx = call_idx["n"]
            call_idx["n"] += 1
            mock_resp = MagicMock()
            mock_resp.headers = {"x-requests-remaining": "300"}

            if idx == 0:
                # events list
                mock_resp.raise_for_status.return_value = None
                mock_resp.json.return_value = events
            elif idx == 1:
                # first event (good) — raise HTTP error
                mock_resp.raise_for_status.side_effect = req_module.HTTPError("404")
            elif idx == 2:
                # second event (also fails, different reason)
                mock_resp.raise_for_status.side_effect = req_module.HTTPError("500")
            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        exit_code = run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=365,  # wide window — this test is about HTTP error handling
            max_credits=200,
        )
        # Fail-open: all events had errors but the run returns 0 (no hard crash)
        assert exit_code == 0

    def test_empty_bookmakers_no_props_posted_returns_zero(self, monkeypatch, tmp_path):
        """When all events return empty bookmakers (no props posted yet), exit 0."""
        events = [
            {
                "id": "ev1",
                "commence_time": "2026-09-10T17:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Baltimore Ravens",
            }
        ]

        call_idx = {"n": 0}

        def fake_get(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.headers = {"x-requests-remaining": "400"}
            if call_idx["n"] == 0:
                mock_resp.json.return_value = events
            else:
                # No bookmakers posted
                mock_resp.json.return_value = {**SAMPLE_EVENT_NO_BOOKMAKERS}
            call_idx["n"] += 1
            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        exit_code = run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=365,  # wide window — this test is about empty bookmakers, not time filter
            max_credits=200,
        )
        assert exit_code == 0
        assert list(tmp_path.rglob("*.parquet")) == []


# ---------------------------------------------------------------------------
# run_props — dry_run
# ---------------------------------------------------------------------------


class TestRunPropsDryRun:
    def test_dry_run_makes_no_per_event_calls(self, monkeypatch):
        events = [
            {
                "id": "ev1",
                "commence_time": "2026-09-10T17:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Baltimore Ravens",
            }
        ]
        call_count = {"n": 0}

        def fake_get(*args, **kwargs):
            call_count["n"] += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = events
            mock_resp.headers = {"x-requests-remaining": "400"}
            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)

        run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=365,  # wide window — dry_run test, not time filter test
            max_credits=200,
            dry_run=True,
        )
        # Only the events-list call should have been made (not per-event)
        assert call_count["n"] == 1

    def test_dry_run_writes_no_files(self, monkeypatch, tmp_path):
        events = [
            {
                "id": "ev1",
                "commence_time": "2026-09-10T17:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Baltimore Ravens",
            }
        ]

        def fake_get(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = events
            mock_resp.headers = {"x-requests-remaining": "400"}
            return mock_resp

        monkeypatch.setattr("scripts.bronze_props_ingestion.requests.get", fake_get)
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=365,  # wide window — dry_run test, not time filter test
            dry_run=True,
        )
        assert list(tmp_path.rglob("*.parquet")) == []


# ---------------------------------------------------------------------------
# run_props — full round-trip tests
# ---------------------------------------------------------------------------


class TestRunPropsRoundTrip:
    def _make_get_mock(self, events: list, event_data: dict, remaining: str = "400"):
        call_idx = {"n": 0}

        def fake_get(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.headers = {
                "x-requests-remaining": remaining,
                "x-requests-used": "10",
            }
            if call_idx["n"] == 0:
                mock_resp.json.return_value = events
            else:
                mock_resp.json.return_value = event_data
            call_idx["n"] += 1
            return mock_resp

        return fake_get

    def test_round_trip_anytime_td_writes_parquet(self, monkeypatch, tmp_path):
        events = [
            {
                "id": SAMPLE_EVENT_META["id"],
                "commence_time": "2026-09-10T00:15:00Z",
                "home_team": "Seattle Seahawks",
                "away_team": "New England Patriots",
            }
        ]
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.requests.get",
            self._make_get_mock(events, SAMPLE_EVENT_ANYTIME_TD),
        )
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        exit_code = run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=365,  # wide window — round-trip test, not time filter test
            max_credits=200,
        )
        assert exit_code == 0

        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) == 1
        df = pd.read_parquet(parquet_files[0])
        assert len(df) == 3  # 3 players from SAMPLE_EVENT_ANYTIME_TD
        assert set(df.columns) == set(PROPS_SCHEMA_COLS)

    def test_round_trip_over_under_writes_parquet(self, monkeypatch, tmp_path):
        events = [
            {
                "id": SAMPLE_EVENT_META["id"],
                "commence_time": "2026-09-10T00:15:00Z",
                "home_team": "Seattle Seahawks",
                "away_team": "New England Patriots",
            }
        ]
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.requests.get",
            self._make_get_mock(events, SAMPLE_EVENT_RECEPTION_YDS),
        )
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        exit_code = run_props(
            api_key="test_key",
            markets=["player_reception_yds"],
            days_ahead=365,  # wide window — round-trip test, not time filter test
            max_credits=200,
        )
        assert exit_code == 0

        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) == 1
        df = pd.read_parquet(parquet_files[0])
        # 2 players from SAMPLE_EVENT_RECEPTION_YDS
        assert len(df) == 2

    def test_january_game_partitioned_into_prior_season(self, monkeypatch, tmp_path):
        jan_events = [
            {
                "id": "playoff1",
                "commence_time": "2027-01-15T21:00:00Z",
                "home_team": "Kansas City Chiefs",
                "away_team": "Buffalo Bills",
            }
        ]
        jan_event_data = {
            "id": "playoff1",
            "commence_time": "2027-01-15T21:00:00Z",
            "home_team": "Kansas City Chiefs",
            "away_team": "Buffalo Bills",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "player_anytime_td",
                            "outcomes": [
                                {
                                    "name": "Yes",
                                    "description": "Patrick Mahomes",
                                    "price": 280,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.requests.get",
            self._make_get_mock(jan_events, jan_event_data),
        )
        monkeypatch.setattr(
            "scripts.bronze_props_ingestion.BRONZE_PROPS_DIR", str(tmp_path / "props")
        )

        run_props(
            api_key="test_key",
            markets=["player_anytime_td"],
            days_ahead=300,
            max_credits=500,
        )

        parquet_files = list(tmp_path.rglob("*.parquet"))
        assert len(parquet_files) == 1
        # Jan 2027 playoff game → season=2026
        assert "season=2026" in str(parquet_files[0])
