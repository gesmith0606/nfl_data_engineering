#!/usr/bin/env python3
"""Unit tests for game_context schedule-derived feature computation functions."""

import pandas as pd
import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.game_context import (
    _haversine_miles,
    _timezone_diff_hours,
    _unpivot_schedules,
    compute_weather_features,
    compute_rest_features,
    compute_travel_features,
    compute_coaching_features,
    compute_game_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_schedules_df():
    """4-game schedule: dome, cold+windy outdoor, neutral London, normal outdoor."""
    return pd.DataFrame([
        {
            "game_id": "2024_01_KC_BAL",
            "season": 2024,
            "week": 1,
            "home_team": "BAL",
            "away_team": "KC",
            "home_coach": "John Harbaugh",
            "away_coach": "Andy Reid",
            "home_rest": 7,
            "away_rest": 7,
            "temp": None,
            "wind": None,
            "roof": "dome",
            "surface": "fieldturf",
            "stadium_id": "BAL00",
            "stadium": "M&T Bank Stadium",
            "game_type": "REG",
            "gameday": "2024-09-05",
            "location": "Home",
        },
        {
            "game_id": "2024_14_GB_CHI",
            "season": 2024,
            "week": 14,
            "home_team": "CHI",
            "away_team": "GB",
            "home_coach": "Matt Eberflus",
            "away_coach": "Matt LaFleur",
            "home_rest": 4,
            "away_rest": 7,
            "temp": 25.0,
            "wind": 18.0,
            "roof": "outdoors",
            "surface": "grass",
            "stadium_id": "CHI98",
            "stadium": "Soldier Field",
            "game_type": "REG",
            "gameday": "2024-12-05",
            "location": "Home",
        },
        {
            "game_id": "2024_05_JAX_BUF",
            "season": 2024,
            "week": 5,
            "home_team": "JAX",
            "away_team": "BUF",
            "home_coach": "Doug Pederson",
            "away_coach": "Sean McDermott",
            "home_rest": 7,
            "away_rest": 7,
            "temp": 60.0,
            "wind": 5.0,
            "roof": "outdoors",
            "surface": "grass",
            "stadium_id": "LON02",
            "stadium": "Tottenham Stadium",
            "game_type": "REG",
            "gameday": "2024-10-06",
            "location": "Neutral",
        },
        {
            "game_id": "2024_08_NYG_SEA",
            "season": 2024,
            "week": 8,
            "home_team": "SEA",
            "away_team": "NYG",
            "home_coach": "Mike Macdonald",
            "away_coach": "Brian Daboll",
            "home_rest": 13,
            "away_rest": 7,
            "temp": 55.0,
            "wind": 8.0,
            "roof": "outdoors",
            "surface": "fieldturf",
            "stadium_id": "SEA00",
            "stadium": "Lumen Field",
            "game_type": "REG",
            "gameday": "2024-10-27",
            "location": "Home",
        },
    ])


@pytest.fixture
def unpivoted_df(sample_schedules_df):
    """8 per-team rows from 4 games."""
    return _unpivot_schedules(sample_schedules_df)


@pytest.fixture
def prior_season_coaches():
    """Prior season final-week coaches for coaching change tests."""
    return {
        "KC": "Andy Reid",
        "BUF": "Sean McDermott",
        "NYG": "Brian Daboll",
        "NYJ": "Robert Saleh",
        "BAL": "John Harbaugh",
        "CHI": "Matt Eberflus",
        "GB": "Matt LaFleur",
        "JAX": "Doug Pederson",
        "SEA": "Mike Macdonald",
    }


# ---------------------------------------------------------------------------
# Unpivot tests
# ---------------------------------------------------------------------------

def test_unpivot_doubles_rows(sample_schedules_df):
    """3 or 4 game input produces 2x per-team rows."""
    result = _unpivot_schedules(sample_schedules_df)
    assert len(result) == 2 * len(sample_schedules_df)


def test_unpivot_columns(sample_schedules_df):
    """Output has all required columns."""
    result = _unpivot_schedules(sample_schedules_df)
    required = [
        "game_id", "season", "week", "team", "opponent", "head_coach",
        "rest_days", "is_home", "temp", "wind", "roof", "surface",
        "stadium_id", "gameday",
    ]
    for col in required:
        assert col in result.columns, f"Missing column: {col}"


def test_unpivot_team_opponent(sample_schedules_df):
    """Home row has team=home_team; away row has team=away_team."""
    result = _unpivot_schedules(sample_schedules_df)
    # BAL should appear as home team in game_id 2024_01_KC_BAL
    bal_home = result[(result["game_id"] == "2024_01_KC_BAL") & (result["team"] == "BAL")]
    assert len(bal_home) == 1
    assert bal_home.iloc[0]["is_home"] is True or bal_home.iloc[0]["is_home"] == True
    assert bal_home.iloc[0]["opponent"] == "KC"

    kc_away = result[(result["game_id"] == "2024_01_KC_BAL") & (result["team"] == "KC")]
    assert len(kc_away) == 1
    assert kc_away.iloc[0]["is_home"] is False or kc_away.iloc[0]["is_home"] == False


# ---------------------------------------------------------------------------
# Weather tests
# ---------------------------------------------------------------------------

def test_weather_dome(unpivoted_df):
    """Dome game -> temperature=72, wind_speed=0, is_dome=True."""
    weather = compute_weather_features(unpivoted_df)
    # BAL00 is a dome game (roof='dome')
    bal_w1 = weather[(weather["team"] == "BAL") & (weather["week"] == 1)]
    assert len(bal_w1) == 1
    row = bal_w1.iloc[0]
    assert row["is_dome"] is True or row["is_dome"] == True
    assert row["temperature"] == 72.0
    assert row["wind_speed"] == 0.0
    assert row["is_high_wind"] is False or row["is_high_wind"] == False
    assert row["is_cold"] is False or row["is_cold"] == False


def test_weather_outdoor_cold_wind(unpivoted_df):
    """Cold windy outdoor game -> is_cold=True, is_high_wind=True."""
    weather = compute_weather_features(unpivoted_df)
    chi_w14 = weather[(weather["team"] == "CHI") & (weather["week"] == 14)]
    assert len(chi_w14) == 1
    row = chi_w14.iloc[0]
    assert row["is_dome"] is False or row["is_dome"] == False
    assert row["temperature"] == 25.0
    assert row["wind_speed"] == 18.0
    assert row["is_cold"] is True or row["is_cold"] == True
    assert row["is_high_wind"] is True or row["is_high_wind"] == True


def test_weather_nan_flags(sample_schedules_df):
    """NaN temp/wind with outdoors roof -> flags are False, is_dome=False."""
    # Create a row with NaN temp/wind but outdoors roof
    nan_df = pd.DataFrame([{
        "game_id": "2024_02_test",
        "season": 2024,
        "week": 2,
        "home_team": "MIA",
        "away_team": "NE",
        "home_coach": "Mike McDaniel",
        "away_coach": "Jerod Mayo",
        "home_rest": 7,
        "away_rest": 7,
        "temp": np.nan,
        "wind": np.nan,
        "roof": "outdoors",
        "surface": "grass",
        "stadium_id": "MIA00",
        "stadium": "Hard Rock Stadium",
        "game_type": "REG",
        "gameday": "2024-09-12",
        "location": "Home",
    }])
    unpivoted = _unpivot_schedules(nan_df)
    weather = compute_weather_features(unpivoted)
    for _, row in weather.iterrows():
        assert row["is_dome"] is False or row["is_dome"] == False
        assert row["is_high_wind"] is False or row["is_high_wind"] == False
        assert row["is_cold"] is False or row["is_cold"] == False


# ---------------------------------------------------------------------------
# Rest tests
# ---------------------------------------------------------------------------

def test_rest_capping():
    """Rest days > 14 should be clipped to 14."""
    df = pd.DataFrame([{
        "game_id": "test", "season": 2024, "week": 1,
        "home_team": "KC", "away_team": "BUF",
        "home_coach": "Andy Reid", "away_coach": "Sean McDermott",
        "home_rest": 16, "away_rest": 7,
        "temp": 70.0, "wind": 5.0, "roof": "outdoors",
        "surface": "grass", "stadium_id": "KAN00",
        "stadium": "Arrowhead", "game_type": "REG",
        "gameday": "2024-09-05", "location": "Home",
    }])
    unpivoted = _unpivot_schedules(df)
    rest = compute_rest_features(unpivoted)
    kc_rest = rest[rest["team"] == "KC"].iloc[0]["rest_days"]
    assert kc_rest == 14


def test_rest_short(unpivoted_df):
    """rest_days=4 -> is_short_rest=True, is_post_bye=False."""
    rest = compute_rest_features(unpivoted_df)
    # CHI has home_rest=4 in week 14
    chi = rest[(rest["team"] == "CHI") & (rest["week"] == 14)]
    assert len(chi) == 1
    assert chi.iloc[0]["is_short_rest"] is True or chi.iloc[0]["is_short_rest"] == True
    assert chi.iloc[0]["is_post_bye"] is False or chi.iloc[0]["is_post_bye"] == False


def test_rest_bye(unpivoted_df):
    """rest_days=13 -> is_post_bye=True, is_short_rest=False."""
    rest = compute_rest_features(unpivoted_df)
    # SEA has home_rest=13 in week 8
    sea = rest[(rest["team"] == "SEA") & (rest["week"] == 8)]
    assert len(sea) == 1
    assert sea.iloc[0]["is_post_bye"] is True or sea.iloc[0]["is_post_bye"] == True
    assert sea.iloc[0]["is_short_rest"] is False or sea.iloc[0]["is_short_rest"] == False


def test_rest_advantage(unpivoted_df):
    """CHI rest=4, GB rest=7 -> CHI advantage = -3."""
    rest = compute_rest_features(unpivoted_df)
    chi = rest[(rest["team"] == "CHI") & (rest["week"] == 14)]
    assert chi.iloc[0]["rest_advantage"] == -3  # 4 - 7


# ---------------------------------------------------------------------------
# Travel tests
# ---------------------------------------------------------------------------

def test_travel_home(unpivoted_df):
    """Home game with location=Home -> travel_miles=0."""
    travel = compute_travel_features(unpivoted_df)
    # BAL at home in week 1
    bal = travel[(travel["team"] == "BAL") & (travel["week"] == 1)]
    assert bal.iloc[0]["travel_miles"] == 0.0


def test_travel_away(unpivoted_df):
    """KC at BAL -> nonzero travel miles approximately 1040 miles."""
    travel = compute_travel_features(unpivoted_df)
    kc = travel[(travel["team"] == "KC") & (travel["week"] == 1)]
    miles = kc.iloc[0]["travel_miles"]
    assert miles > 900  # KC to BAL is roughly 1040 miles
    assert miles < 1200


def test_travel_neutral(unpivoted_df):
    """Neutral site London -> both teams get nonzero travel distance."""
    travel = compute_travel_features(unpivoted_df)
    # Week 5 JAX vs BUF at Tottenham (LON02) -- neutral site
    jax = travel[(travel["team"] == "JAX") & (travel["week"] == 5)]
    buf = travel[(travel["team"] == "BUF") & (travel["week"] == 5)]
    assert jax.iloc[0]["travel_miles"] > 3000  # JAX to London ~4200 miles
    assert buf.iloc[0]["travel_miles"] > 3000  # BUF to London ~3400 miles


# ---------------------------------------------------------------------------
# Haversine tests
# ---------------------------------------------------------------------------

def test_haversine_known():
    """NYJ (MetLife 40.81,-74.07) to LA (SoFi 33.95,-118.34) ~ 2450 miles."""
    dist = _haversine_miles(40.8128, -74.0742, 33.9534, -118.3390)
    assert dist == pytest.approx(2450, abs=50)


# ---------------------------------------------------------------------------
# Timezone tests
# ---------------------------------------------------------------------------

def test_timezone_diff_dst():
    """NY vs LA on 2024-09-08 (both DST) -> 3.0 hours."""
    diff = _timezone_diff_hours("America/New_York", "America/Los_Angeles", "2024-09-08")
    assert diff == pytest.approx(3.0)


def test_timezone_diff_arizona():
    """Phoenix vs LA in summer -> 0.0 hours (AZ MST=UTC-7, LA PDT=UTC-7).
    In November after fall-back, LA is PST=UTC-8 vs AZ MST=UTC-7 -> 1.0 hour."""
    # Summer: both UTC-7
    diff_summer = _timezone_diff_hours("America/Phoenix", "America/Los_Angeles", "2024-07-15")
    assert diff_summer == pytest.approx(0.0)
    # Winter: AZ UTC-7, LA UTC-8
    diff_winter = _timezone_diff_hours("America/Phoenix", "America/Los_Angeles", "2024-11-10")
    assert diff_winter == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Coaching tests
# ---------------------------------------------------------------------------

def test_coaching_no_change(prior_season_coaches):
    """Same coach all season -> coaching_change=False, tenure increments."""
    df = pd.DataFrame([
        {"game_id": f"g{w}", "season": 2024, "week": w,
         "home_team": "KC", "away_team": "BUF",
         "home_coach": "Andy Reid", "away_coach": "Sean McDermott",
         "home_rest": 7, "away_rest": 7, "temp": 70.0, "wind": 5.0,
         "roof": "outdoors", "surface": "grass", "stadium_id": "KAN00",
         "stadium": "Arrowhead", "game_type": "REG",
         "gameday": f"2024-09-{8+w:02d}", "location": "Home"}
        for w in range(1, 5)
    ])
    unpivoted = _unpivot_schedules(df)
    coaching = compute_coaching_features(unpivoted, prior_season_coaches)
    kc = coaching[coaching["team"] == "KC"].sort_values("week")
    assert all(kc["coaching_change"] == False)
    assert list(kc["coaching_tenure"]) == [1, 2, 3, 4]


def test_coaching_offseason_change():
    """Different coach from prior season -> coaching_change=True all weeks."""
    prior = {"NYG": "Joe Judge"}  # Different from Brian Daboll
    df = pd.DataFrame([
        {"game_id": f"g{w}", "season": 2024, "week": w,
         "home_team": "NYG", "away_team": "DAL",
         "home_coach": "Brian Daboll", "away_coach": "Mike McCarthy",
         "home_rest": 7, "away_rest": 7, "temp": 70.0, "wind": 5.0,
         "roof": "outdoors", "surface": "fieldturf", "stadium_id": "NYC01",
         "stadium": "MetLife", "game_type": "REG",
         "gameday": f"2024-09-{8+w:02d}", "location": "Home"}
        for w in range(1, 4)
    ])
    unpivoted = _unpivot_schedules(df)
    coaching = compute_coaching_features(unpivoted, prior)
    nyg = coaching[coaching["team"] == "NYG"].sort_values("week")
    assert all(nyg["coaching_change"] == True)
    assert nyg.iloc[0]["coaching_tenure"] == 1


def test_coaching_midseason_change():
    """Coach changes at week 5 -> False weeks 1-4, True weeks 5+, tenure resets."""
    prior = {"PIT": "Mike Tomlin"}  # Same as initial
    rows = []
    for w in range(1, 9):
        coach = "Mike Tomlin" if w < 5 else "New Coach"
        rows.append({
            "game_id": f"g{w}", "season": 2024, "week": w,
            "home_team": "PIT", "away_team": "CLE",
            "home_coach": coach, "away_coach": "Kevin Stefanski",
            "home_rest": 7, "away_rest": 7, "temp": 55.0, "wind": 5.0,
            "roof": "outdoors", "surface": "grass", "stadium_id": "PIT00",
            "stadium": "Acrisure", "game_type": "REG",
            "gameday": f"2024-09-{8+w:02d}", "location": "Home",
        })
    df = pd.DataFrame(rows)
    unpivoted = _unpivot_schedules(df)
    coaching = compute_coaching_features(unpivoted, prior)
    pit = coaching[coaching["team"] == "PIT"].sort_values("week")
    # Weeks 1-4: same coach, no change
    assert all(pit[pit["week"] <= 4]["coaching_change"] == False)
    # Weeks 5+: new coach, change=True
    assert all(pit[pit["week"] >= 5]["coaching_change"] == True)
    # Tenure resets at week 5
    assert pit[pit["week"] == 5].iloc[0]["coaching_tenure"] == 1
    assert pit[pit["week"] == 6].iloc[0]["coaching_tenure"] == 2


def test_coaching_first_season():
    """No prior data (first season) -> coaching_change=False for all teams."""
    df = pd.DataFrame([{
        "game_id": "g1", "season": 2016, "week": 1,
        "home_team": "KC", "away_team": "BUF",
        "home_coach": "Andy Reid", "away_coach": "Rex Ryan",
        "home_rest": 7, "away_rest": 7, "temp": 70.0, "wind": 5.0,
        "roof": "outdoors", "surface": "grass", "stadium_id": "KAN00",
        "stadium": "Arrowhead", "game_type": "REG",
        "gameday": "2016-09-08", "location": "Home",
    }])
    unpivoted = _unpivot_schedules(df)
    coaching = compute_coaching_features(unpivoted, prior_season_coaches=None)
    assert all(coaching["coaching_change"] == False)


# ---------------------------------------------------------------------------
# End-to-end test
# ---------------------------------------------------------------------------

def test_game_context_e2e(sample_schedules_df):
    """Full pipeline produces correct shape and all expected columns."""
    result = compute_game_context(sample_schedules_df)

    # Row count = 2 * input
    assert len(result) == 2 * len(sample_schedules_df)

    # All expected columns present
    expected_cols = [
        "team", "season", "week", "is_home", "game_type",
        "is_dome", "temperature", "wind_speed", "is_high_wind", "is_cold", "surface",
        "rest_days", "opponent_rest", "is_short_rest", "is_post_bye", "rest_advantage",
        "travel_miles", "tz_diff",
        "head_coach", "coaching_change", "coaching_tenure",
    ]
    for col in expected_cols:
        assert col in result.columns, f"Missing column: {col}"

    # Joinable on [team, season, week] -- no duplicates
    dup_check = result.groupby(["team", "season", "week"]).size()
    assert dup_check.max() == 1, "Duplicate [team, season, week] rows found"


def test_game_context_with_prior_season(sample_schedules_df):
    """compute_game_context with prior_season_df extracts coaches correctly."""
    prior = pd.DataFrame([{
        "game_id": "2023_18_KC_BAL",
        "season": 2023, "week": 18,
        "home_team": "BAL", "away_team": "KC",
        "home_coach": "John Harbaugh", "away_coach": "Andy Reid",
        "home_rest": 7, "away_rest": 7,
        "temp": 40.0, "wind": 10.0, "roof": "outdoors",
        "surface": "grass", "stadium_id": "BAL00", "stadium": "M&T Bank",
        "game_type": "REG", "gameday": "2024-01-07", "location": "Home",
    }])
    result = compute_game_context(sample_schedules_df, prior_season_df=prior)
    assert len(result) == 2 * len(sample_schedules_df)
    # BAL and KC should have coaching_change based on prior season comparison
    assert "coaching_change" in result.columns
