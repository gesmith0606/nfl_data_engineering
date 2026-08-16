#!/usr/bin/env python3
"""Unit tests for weather ingestion/feature helpers (pure functions only, no disk I/O)."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from bronze_weather_ingestion import _game_utc_hour  # noqa: E402
from src.weather_features import _unpivot_schedules_teams, HIGH_WIND_THRESHOLD_MPH  # noqa: E402


class TestGameUtcHour:
    """nflverse gametime is posted in ET broadcast-slot convention regardless
    of venue timezone -- verified against real Denver/Seattle games where
    home teams in Mountain/Pacific still show ET slot times (16:05 = 4:05pm
    ET, not local kickoff)."""

    def test_1pm_et_slot_in_winter(self):
        # 2024-01-07 is EST (UTC-5): 13:00 ET -> 18:00 UTC
        assert _game_utc_hour("2024-01-07", "13:00") == "2024-01-07T18:00"

    def test_night_game_crosses_midnight_utc(self):
        # 8:20pm ET in EST -> 01:20 UTC next day, rounds to nearest hour (01:00)
        assert _game_utc_hour("2024-01-06", "20:20") == "2024-01-07T01:00"

    def test_summer_edt_offset(self):
        # Preseason August game: EDT is UTC-4. 13:00 ET -> 17:00 UTC
        assert _game_utc_hour("2024-08-10", "13:00") == "2024-08-10T17:00"

    def test_rounds_to_nearest_hour(self):
        # 16:35 ET rounds up to 17:00 ET before UTC conversion
        result = _game_utc_hour("2024-01-07", "16:35")
        assert result.endswith(":00")


class TestUnpivotSchedulesTeams:
    def test_produces_one_row_per_team_per_game(self):
        schedules = pd.DataFrame([
            {"game_id": "2024_01_KC_BAL", "season": 2024, "week": 1, "home_team": "BAL", "away_team": "KC"},
        ])
        result = _unpivot_schedules_teams(schedules)
        assert len(result) == 2
        assert set(result["team"]) == {"BAL", "KC"}
        assert set(result["game_id"]) == {"2024_01_KC_BAL"}

    def test_preserves_season_week(self):
        schedules = pd.DataFrame([
            {"game_id": "g1", "season": 2022, "week": 5, "home_team": "SEA", "away_team": "SF"},
        ])
        result = _unpivot_schedules_teams(schedules)
        assert (result["season"] == 2022).all()
        assert (result["week"] == 5).all()


def test_high_wind_threshold_matches_game_context_convention():
    # src/game_context.py uses > 15; this module uses >= 15 -- both defensible,
    # but the constant must exist and be exactly 15 so buckets/report numbers
    # in .planning/WEATHER_DATA_2026_08_16.md stay accurate if it's ever tuned.
    assert HIGH_WIND_THRESHOLD_MPH == 15.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
