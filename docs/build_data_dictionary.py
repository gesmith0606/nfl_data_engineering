#!/usr/bin/env python3
"""Build comprehensive data dictionary CSV from source code analysis."""

import csv
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "data_dictionary.csv")

HEADERS = [
    "Layer", "Dataset", "Column Name", "Data Type", "Description",
    "Source", "Nullable", "Example Value", "Business Rules", "Notes"
]

rows = []

def add(layer, dataset, col, dtype, desc, source, nullable, example, rules="", notes=""):
    rows.append([layer, dataset, col, dtype, desc, source, nullable, example, rules, notes])

# =============================================================================
# BRONZE LAYER
# =============================================================================

# --- PBP (140 columns) ---
pbp_cols = {
    # Game identifiers
    "game_id": ("string", "Unique game identifier", "nfl-data-py", "No", "2024_01_KC_DET", "Format: YYYY_WW_AWAY_HOME", ""),
    "play_id": ("int64", "Sequential play number within game", "nfl-data-py", "No", "42", "Starts at 1 per game", ""),
    "season": ("int64", "NFL season year", "nfl-data-py", "No", "2024", "Valid: 1999-2026", ""),
    "week": ("int64", "NFL week number", "nfl-data-py", "No", "1", "Regular season: 1-18", ""),
    "season_type": ("string", "Season phase", "nfl-data-py", "No", "REG", "REG or POST", ""),
    "game_date": ("string", "Date of game", "nfl-data-py", "No", "2024-09-05", "YYYY-MM-DD format", ""),
    "posteam": ("string", "Possessing team abbreviation", "nfl-data-py", "No", "KC", "Standard NFL abbrevs (32 teams)", ""),
    "defteam": ("string", "Defending team abbreviation", "nfl-data-py", "No", "DET", "Standard NFL abbrevs", ""),
    "home_team": ("string", "Home team abbreviation", "nfl-data-py", "No", "DET", "", ""),
    "away_team": ("string", "Away team abbreviation", "nfl-data-py", "No", "KC", "", ""),
    # Score context
    "home_score": ("int64", "Home team current score", "nfl-data-py", "No", "14", ">=0", ""),
    "away_score": ("int64", "Away team current score", "nfl-data-py", "No", "10", ">=0", ""),
    "score_differential": ("int64", "Possessing team score minus defending team score", "nfl-data-py", "No", "-3", "", ""),
    # Play situation
    "down": ("int64", "Current down", "nfl-data-py", "Yes", "3", "1-4; NaN on kickoffs/PATs", ""),
    "ydstogo": ("int64", "Yards to first down or goal", "nfl-data-py", "Yes", "7", "1-99", ""),
    "yardline_100": ("int64", "Yards from opponent end zone", "nfl-data-py", "Yes", "45", "0-100", "Red zone when <= 20"),
    "goal_to_go": ("int64", "Binary: is goal-to-go situation", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "qtr": ("int64", "Quarter of game", "nfl-data-py", "No", "2", "1-5 (5=OT)", ""),
    "game_seconds_remaining": ("float64", "Seconds remaining in game", "nfl-data-py", "Yes", "1800.0", "0-3600 (or more in OT)", ""),
    "drive": ("int64", "Drive number within game", "nfl-data-py", "Yes", "5", "Sequential per game", ""),
    # Play type and result
    "play_type": ("string", "Type of play", "nfl-data-py", "No", "pass", "pass/run/punt/kickoff/field_goal/etc.", ""),
    "yards_gained": ("int64", "Net yards gained on play", "nfl-data-py", "Yes", "12", "Can be negative", ""),
    "shotgun": ("int64", "Binary: shotgun formation", "nfl-data-py", "Yes", "1", "0 or 1", ""),
    "no_huddle": ("int64", "Binary: no-huddle snap", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "pass_attempt": ("int64", "Binary: pass attempt", "nfl-data-py", "Yes", "1", "0 or 1", ""),
    "rush_attempt": ("int64", "Binary: rush attempt", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "complete_pass": ("int64", "Binary: pass completed", "nfl-data-py", "Yes", "1", "0 or 1", ""),
    "interception": ("int64", "Binary: interception thrown", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "sack": ("int64", "Binary: quarterback sacked", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "fumble": ("int64", "Binary: fumble occurred", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "fumble_lost": ("int64", "Binary: fumble lost to defense", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "touchdown": ("int64", "Binary: touchdown scored", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "first_down": ("int64", "Binary: first down gained", "nfl-data-py", "Yes", "1", "0 or 1", ""),
    "penalty": ("int64", "Binary: penalty on play", "nfl-data-py", "Yes", "0", "0 or 1", ""),
    "success": ("int64", "Binary: successful play by EPA standard", "nfl-data-py", "Yes", "1", "0 or 1", "EPA > 0"),
    # EPA metrics
    "epa": ("float64", "Expected Points Added", "nfl-data-py", "Yes", "0.85", "Core efficiency metric", "NaN filtered in Silver"),
    "qb_epa": ("float64", "QB-attributed EPA", "nfl-data-py", "Yes", "1.2", "", ""),
    "air_epa": ("float64", "Air yards component of EPA", "nfl-data-py", "Yes", "0.5", "", ""),
    "yac_epa": ("float64", "Yards-after-catch component of EPA", "nfl-data-py", "Yes", "0.35", "", ""),
    # WPA metrics
    "wpa": ("float64", "Win Probability Added", "nfl-data-py", "Yes", "0.03", "", ""),
    "wp": ("float64", "Win probability before play", "nfl-data-py", "Yes", "0.52", "0-1 range", ""),
    # Completion metrics
    "cpoe": ("float64", "Completion Probability Over Expected", "nfl-data-py", "Yes", "5.2", "Positive = above expected", ""),
    "xpass": ("float64", "Expected pass rate for situation", "nfl-data-py", "Yes", "0.65", "0-1 range", ""),
    # Yardage
    "air_yards": ("float64", "Air yards on pass attempt", "nfl-data-py", "Yes", "12.5", "Can be negative (behind LOS)", ""),
    "yards_after_catch": ("float64", "YAC on completed pass", "nfl-data-py", "Yes", "8.0", "", ""),
    "passing_yards": ("float64", "Total passing yards on play", "nfl-data-py", "Yes", "20.5", "", ""),
    # Player IDs
    "passer_player_id": ("string", "GSIS ID of passer", "nfl-data-py", "Yes", "00-0033873", "", ""),
    "receiver_player_id": ("string", "GSIS ID of receiver", "nfl-data-py", "Yes", "00-0036212", "", ""),
    "rusher_player_id": ("string", "GSIS ID of rusher", "nfl-data-py", "Yes", "00-0035228", "", ""),
    # Vegas lines
    "spread_line": ("float64", "Spread (home team perspective)", "nfl-data-py", "Yes", "-3.0", "Negative = home favored", ""),
    "total_line": ("float64", "Over/under total", "nfl-data-py", "Yes", "47.5", "", ""),
    # Weather/venue
    "temp": ("float64", "Temperature (Fahrenheit)", "nfl-data-py", "Yes", "68.0", "NaN for dome games", ""),
    "wind": ("float64", "Wind speed (mph)", "nfl-data-py", "Yes", "8.0", "NaN for dome games", ""),
    "roof": ("string", "Roof type", "nfl-data-py", "Yes", "outdoors", "outdoors/dome/closed/open", ""),
    "surface": ("string", "Playing surface type", "nfl-data-py", "Yes", "grass", "grass/fieldturf/a_turf/etc.", ""),
    # Special teams
    "field_goal_result": ("string", "FG result", "nfl-data-py", "Yes", "made", "made/missed/blocked", ""),
    "kick_distance": ("float64", "Kick distance in yards", "nfl-data-py", "Yes", "45.0", "", ""),
    # Drive detail
    "drive_play_count": ("int64", "Number of plays in drive", "nfl-data-py", "Yes", "8", "", ""),
    "drive_time_of_possession": ("string", "Drive TOP in M:SS format", "nfl-data-py", "Yes", "4:23", "", "Parsed to seconds in Silver"),
    # Series
    "series": ("int64", "Series number within drive", "nfl-data-py", "Yes", "3", "", ""),
    "series_success": ("int64", "Binary: series resulted in first down/TD", "nfl-data-py", "Yes", "1", "0 or 1", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in pbp_cols.items():
    add("Bronze", "pbp", col, dtype, desc, src, null, ex, rules, notes)

# --- Player Weekly ---
player_weekly = {
    "player_id": ("string", "Unique player identifier (GSIS ID)", "nfl-data-py", "No", "00-0033873", "", ""),
    "player_name": ("string", "Player display name", "nfl-data-py", "No", "P.Mahomes", "", ""),
    "position": ("string", "Player position", "nfl-data-py", "No", "QB", "QB/RB/WR/TE", "Fantasy-relevant positions"),
    "recent_team": ("string", "Team abbreviation", "nfl-data-py", "No", "KC", "", ""),
    "season": ("int64", "NFL season year", "nfl-data-py", "No", "2024", "2002-2026", ""),
    "week": ("int64", "NFL week number", "nfl-data-py", "No", "5", "1-18", ""),
    "passing_yards": ("float64", "Total passing yards", "nfl-data-py", "Yes", "320.0", ">=0", ""),
    "passing_tds": ("float64", "Passing touchdowns", "nfl-data-py", "Yes", "3.0", ">=0", ""),
    "interceptions": ("float64", "Interceptions thrown", "nfl-data-py", "Yes", "1.0", ">=0", "Renamed from passing_interceptions in 2025+"),
    "rushing_yards": ("float64", "Total rushing yards", "nfl-data-py", "Yes", "45.0", "", "Can be negative"),
    "rushing_tds": ("float64", "Rushing touchdowns", "nfl-data-py", "Yes", "0.0", ">=0", ""),
    "carries": ("float64", "Rush attempts", "nfl-data-py", "Yes", "8.0", ">=0", ""),
    "targets": ("float64", "Receiving targets", "nfl-data-py", "Yes", "6.0", ">=0", ""),
    "receptions": ("float64", "Receptions", "nfl-data-py", "Yes", "4.0", ">=0", ""),
    "receiving_yards": ("float64", "Total receiving yards", "nfl-data-py", "Yes", "55.0", "", ""),
    "receiving_tds": ("float64", "Receiving touchdowns", "nfl-data-py", "Yes", "1.0", ">=0", ""),
    "air_yards": ("float64", "Total target air yards", "nfl-data-py", "Yes", "52.0", "", "Mapped from receiving_air_yards"),
    "wopr": ("float64", "Weighted Opportunity Rating", "nfl-data-py", "Yes", "0.42", "0-1 composite", ""),
    "fantasy_points_ppr": ("float64", "Fantasy points (PPR scoring)", "nfl-data-py", "Yes", "22.5", ">=0 for skill positions", ""),
    "sacks": ("float64", "Times sacked", "nfl-data-py", "Yes", "2.0", ">=0", "Renamed from sacks_suffered in 2025+"),
    "dakota": ("float64", "CPOE composite metric", "nfl-data-py", "Yes", "0.15", "", "Renamed from passing_cpoe in 2025+"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in player_weekly.items():
    add("Bronze", "player_weekly", col, dtype, desc, src, null, ex, rules, notes)

# --- Schedules ---
schedules = {
    "game_id": ("string", "Unique game identifier", "nfl-data-py", "No", "2024_01_KC_DET", "", ""),
    "season": ("int64", "NFL season year", "nfl-data-py", "No", "2024", "1999-2026", ""),
    "week": ("int64", "NFL week number", "nfl-data-py", "No", "1", "", ""),
    "game_type": ("string", "Game type", "nfl-data-py", "No", "REG", "REG/WC/DIV/CON/SB", ""),
    "home_team": ("string", "Home team abbreviation", "nfl-data-py", "No", "DET", "", ""),
    "away_team": ("string", "Away team abbreviation", "nfl-data-py", "No", "KC", "", ""),
    "home_score": ("float64", "Home team final score", "nfl-data-py", "Yes", "24.0", ">=0; NaN for future games", ""),
    "away_score": ("float64", "Away team final score", "nfl-data-py", "Yes", "21.0", ">=0", ""),
    "result": ("float64", "Home margin (home_score - away_score)", "nfl-data-py", "Yes", "3.0", "", ""),
    "spread_line": ("float64", "Vegas spread (home perspective)", "nfl-data-py", "Yes", "-3.0", "Negative = home favored", ""),
    "total_line": ("float64", "Vegas over/under", "nfl-data-py", "Yes", "47.5", "", ""),
    "home_rest": ("int64", "Days of rest for home team", "nfl-data-py", "Yes", "7", "", ""),
    "away_rest": ("int64", "Days of rest for away team", "nfl-data-py", "Yes", "7", "", ""),
    "home_coach": ("string", "Home head coach name", "nfl-data-py", "Yes", "Dan Campbell", "", ""),
    "away_coach": ("string", "Away head coach name", "nfl-data-py", "Yes", "Andy Reid", "", ""),
    "referee": ("string", "Game referee", "nfl-data-py", "Yes", "Brad Allen", "", ""),
    "stadium_id": ("string", "Stadium identifier code", "nfl-data-py", "Yes", "DET00", "", "Maps to STADIUM_ID_COORDS"),
    "div_game": ("bool", "Division rivalry game", "nfl-data-py", "Yes", "False", "", ""),
    "roof": ("string", "Stadium roof type", "nfl-data-py", "Yes", "dome", "outdoors/dome/closed/open", ""),
    "surface": ("string", "Playing surface", "nfl-data-py", "Yes", "fieldturf", "", ""),
    "temp": ("float64", "Game temperature (F)", "nfl-data-py", "Yes", "72.0", "", "NaN for domes"),
    "wind": ("float64", "Wind speed (mph)", "nfl-data-py", "Yes", "0.0", "", ""),
    "gameday": ("string", "Game date", "nfl-data-py", "No", "2024-09-05", "YYYY-MM-DD", ""),
    "location": ("string", "Game location type", "nfl-data-py", "Yes", "Home", "Home/Neutral", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in schedules.items():
    add("Bronze", "schedules", col, dtype, desc, src, null, ex, rules, notes)

# --- Snap Counts ---
snap_counts = {
    "player": ("string", "Player name", "nfl-data-py", "No", "Patrick Mahomes", "", "Not player_id; mapped in Silver"),
    "player_id": ("string", "GSIS player ID", "nfl-data-py", "Yes", "00-0033873", "", ""),
    "season": ("int64", "NFL season year", "nfl-data-py", "No", "2024", "2012-2026", ""),
    "week": ("int64", "NFL week number", "nfl-data-py", "No", "5", "", ""),
    "position": ("string", "Player position", "nfl-data-py", "No", "QB", "", ""),
    "team": ("string", "Team abbreviation", "nfl-data-py", "No", "KC", "", ""),
    "offense_pct": ("float64", "Offensive snap percentage", "nfl-data-py", "Yes", "0.98", "0-1; mapped to snap_pct in Silver", "Column name is offense_pct not snap_pct"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in snap_counts.items():
    add("Bronze", "snap_counts", col, dtype, desc, src, null, ex, rules, notes)

# --- Injuries ---
injuries = {
    "season": ("int64", "NFL season year", "nfl-data-py", "No", "2024", "2009-2024", "Discontinued after 2024"),
    "week": ("int64", "NFL week number", "nfl-data-py", "No", "5", "", ""),
    "gsis_id": ("string", "Player GSIS ID", "nfl-data-py", "Yes", "00-0033873", "", ""),
    "full_name": ("string", "Player full name", "nfl-data-py", "No", "Patrick Mahomes", "", ""),
    "team": ("string", "Team abbreviation", "nfl-data-py", "No", "KC", "", ""),
    "position": ("string", "Player position", "nfl-data-py", "No", "QB", "", ""),
    "report_status": ("string", "Injury report status", "nfl-data-py", "Yes", "Questionable", "Active/Questionable/Doubtful/Out/IR/PUP", "Maps to injury multipliers"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in injuries.items():
    add("Bronze", "injuries", col, dtype, desc, src, null, ex, rules, notes)

# --- Odds (FinnedAI) ---
odds = {
    "game_id": ("string", "Nflverse game identifier (joined)", "FinnedAI + nflverse", "No", "2020_01_KC_HOU", "", "r=0.997 join quality"),
    "season": ("int64", "NFL season year", "FinnedAI", "No", "2020", "2016-2021 only", "FinnedAI coverage limitation"),
    "week": ("int64", "NFL week number", "FinnedAI", "No", "1", "", ""),
    "home_team": ("string", "Home team abbreviation", "FinnedAI", "No", "KC", "", "45-entry team mapping applied"),
    "away_team": ("string", "Away team abbreviation", "FinnedAI", "No", "HOU", "", ""),
    "opening_spread": ("float64", "Opening spread (home perspective)", "FinnedAI", "Yes", "-10.0", "Negative = home favored", "PRE-GAME feature"),
    "closing_spread": ("float64", "Closing spread (home perspective)", "FinnedAI", "Yes", "-9.5", "", "RETROSPECTIVE only"),
    "opening_total": ("float64", "Opening over/under total", "FinnedAI", "Yes", "53.5", "", "PRE-GAME feature"),
    "closing_total": ("float64", "Closing over/under total", "FinnedAI", "Yes", "54.0", "", "RETROSPECTIVE only"),
    "home_moneyline": ("int64", "Home team moneyline", "FinnedAI", "Yes", "-450", "", ""),
    "away_moneyline": ("int64", "Away team moneyline", "FinnedAI", "Yes", "+350", "", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in odds.items():
    add("Bronze", "odds", col, dtype, desc, src, null, ex, rules, notes)

# --- Other Bronze datasets (summary rows) ---
add("Bronze", "rosters", "player_id", "string", "Player GSIS ID", "nfl-data-py", "No", "00-0033873", "2002-2026", "Use import_seasonal_rosters not import_rosters")
add("Bronze", "rosters", "position", "string", "Player position", "nfl-data-py", "No", "QB", "", "")
add("Bronze", "rosters", "team", "string", "Team abbreviation", "nfl-data-py", "No", "KC", "", "")
add("Bronze", "rosters", "full_name", "string", "Player full name", "nfl-data-py", "No", "Patrick Mahomes", "", "")
add("Bronze", "rosters", "status", "string", "Roster status", "nfl-data-py", "Yes", "ACT", "ACT/RES/IR/etc.", "")

add("Bronze", "teams", "team_abbr", "string", "Team abbreviation", "nfl-data-py", "No", "KC", "", "")
add("Bronze", "teams", "team_name", "string", "Full team name", "nfl-data-py", "No", "Kansas City Chiefs", "", "")
add("Bronze", "teams", "team_conf", "string", "Conference", "nfl-data-py", "No", "AFC", "AFC/NFC", "")
add("Bronze", "teams", "team_division", "string", "Division", "nfl-data-py", "No", "AFC West", "", "")

add("Bronze", "ngs", "player_gsis_id", "string", "Player GSIS ID", "nfl-data-py", "No", "00-0036212", "2016+", "Next Gen Stats")
add("Bronze", "ngs", "avg_separation", "float64", "Average separation on routes (yards)", "nfl-data-py", "Yes", "2.8", "", "WR/TE metric")
add("Bronze", "ngs", "avg_time_to_throw", "float64", "Average time to throw (seconds)", "nfl-data-py", "Yes", "2.65", "", "QB metric")
add("Bronze", "ngs", "rush_yards_over_expected", "float64", "Rush yards over expected", "nfl-data-py", "Yes", "12.0", "", "RB metric")

add("Bronze", "pfr_weekly", "times_pressured_pct", "float64", "Pressure rate percentage", "nfl-data-py (PFR)", "Yes", "25.3", "2018+", "Pro Football Reference")
add("Bronze", "pfr_weekly", "passing_bad_throw_pct", "float64", "Bad throw percentage", "nfl-data-py (PFR)", "Yes", "18.5", "", "")

add("Bronze", "qbr", "qbr_total", "float64", "ESPN Total QBR", "nfl-data-py (ESPN)", "Yes", "72.5", "2006+; 0-100 scale", "")
add("Bronze", "qbr", "pts_added", "float64", "Points added by QB", "nfl-data-py (ESPN)", "Yes", "8.3", "", "")

add("Bronze", "combine", "ht", "string", "Height in feet-inches format", "nfl-data-py", "Yes", "6-2", "2000+", "Parsed to inches in Silver")
add("Bronze", "combine", "wt", "float64", "Weight in pounds", "nfl-data-py", "Yes", "230.0", "", "")
add("Bronze", "combine", "forty", "float64", "40-yard dash time (seconds)", "nfl-data-py", "Yes", "4.45", "", "")
add("Bronze", "combine", "vertical", "float64", "Vertical jump (inches)", "nfl-data-py", "Yes", "36.0", "", "")
add("Bronze", "combine", "broad_jump", "float64", "Broad jump (inches)", "nfl-data-py", "Yes", "124.0", "", "")

add("Bronze", "draft_picks", "pick", "int64", "Overall draft pick number", "nfl-data-py", "No", "10", "1-262", "")
add("Bronze", "draft_picks", "round", "int64", "Draft round", "nfl-data-py", "No", "1", "1-7", "")
add("Bronze", "draft_picks", "pfr_id", "string", "Pro Football Reference player ID", "nfl-data-py", "Yes", "MahoPa00", "", "")

add("Bronze", "depth_charts", "position", "string", "Position on depth chart", "nfl-data-py", "No", "QB", "2001+", "")
add("Bronze", "depth_charts", "depth_team", "int64", "Depth chart rank", "nfl-data-py", "Yes", "1", "1=starter", "")

add("Bronze", "officials", "game_id", "string", "Game identifier", "nfl-data-py", "No", "2024_01_KC_DET", "2015+", "")
add("Bronze", "officials", "official_name", "string", "Official name", "nfl-data-py", "No", "Brad Allen", "", "")
add("Bronze", "officials", "official_position", "string", "Official position (referee/umpire/etc.)", "nfl-data-py", "No", "Referee", "", "")

add("Bronze", "player_seasonal", "player_id", "string", "Player GSIS ID", "nfl-data-py", "No", "00-0033873", "2002+; season-level aggregates", "")
add("Bronze", "player_seasonal", "season", "int64", "NFL season year", "nfl-data-py", "No", "2024", "", "")
add("Bronze", "player_seasonal", "completions", "float64", "Season total completions", "nfl-data-py", "Yes", "401.0", "", "")
add("Bronze", "player_seasonal", "attempts", "float64", "Season total pass attempts", "nfl-data-py", "Yes", "588.0", "", "")

# =============================================================================
# SILVER LAYER
# =============================================================================

# --- Player Usage Metrics (player_analytics.py) ---
usage_cols = {
    "target_share": ("float64", "Fraction of team targets received", "Derived (targets / team_targets)", "Yes", "0.22", "0-1", ""),
    "air_yards_share": ("float64", "Fraction of team air yards", "Derived (air_yards / team_air_yards)", "Yes", "0.28", "0-1", ""),
    "carry_share": ("float64", "Fraction of team carries", "Derived (carries / team_carries)", "Yes", "0.45", "0-1", ""),
    "rz_target_share": ("float64", "Red zone target share (or WOPR proxy)", "Derived", "Yes", "0.15", "0-1", "Falls back to WOPR if available"),
    "snap_pct": ("float64", "Offensive snap percentage", "Derived from snap_counts", "Yes", "0.92", "0-1", "Mapped from offense_pct"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in usage_cols.items():
    add("Silver", "player_usage", col, dtype, desc, src, null, ex, rules, notes)

# --- Rolling Averages (player_analytics.py) ---
rolling_stats = ["passing_yards", "passing_tds", "interceptions", "rushing_yards", "rushing_tds",
                  "carries", "receiving_yards", "receiving_tds", "receptions", "targets",
                  "air_yards", "target_share", "carry_share", "snap_pct", "fantasy_points_ppr"]
for stat in rolling_stats:
    add("Silver", "player_rolling", f"{stat}_roll3", "float64", f"3-game rolling average of {stat}", "Derived (shift(1) + rolling mean)", "Yes", "", "shift(1) prevents look-ahead", "")
    add("Silver", "player_rolling", f"{stat}_roll6", "float64", f"6-game rolling average of {stat}", "Derived (shift(1) + rolling mean)", "Yes", "", "shift(1) prevents look-ahead", "")
    add("Silver", "player_rolling", f"{stat}_std", "float64", f"Season-to-date expanding average of {stat}", "Derived (shift(1) + expanding mean)", "Yes", "", "", "")

# --- Opponent Rankings (player_analytics.py) ---
add("Silver", "opponent_rankings", "team", "string", "Defensive team abbreviation", "Derived", "No", "KC", "", "")
add("Silver", "opponent_rankings", "position", "string", "Fantasy position (QB/RB/WR/TE)", "Derived", "No", "WR", "", "")
add("Silver", "opponent_rankings", "avg_pts_allowed", "float64", "Average fantasy points allowed to position", "Derived", "Yes", "18.5", "", "Higher = easier matchup")
add("Silver", "opponent_rankings", "rank", "int64", "Positional defensive rank (1=easiest)", "Derived", "No", "5", "1-32", "")

# --- Team PBP Metrics (team_analytics.py) ---
pbp_metric_cols = {
    "off_epa_per_play": ("float64", "Offensive EPA per play", "Derived from PBP", "Yes", "0.12", "", "Core team efficiency"),
    "off_pass_epa": ("float64", "Passing EPA per play", "Derived from PBP", "Yes", "0.18", "", ""),
    "off_rush_epa": ("float64", "Rushing EPA per play", "Derived from PBP", "Yes", "0.05", "", ""),
    "def_epa_per_play": ("float64", "Defensive EPA per play allowed", "Derived from PBP", "Yes", "-0.08", "Negative = good defense", ""),
    "off_success_rate": ("float64", "Offensive play success rate", "Derived from PBP", "Yes", "0.48", "0-1", ""),
    "def_success_rate": ("float64", "Defensive play success rate allowed", "Derived from PBP", "Yes", "0.42", "0-1", ""),
    "off_cpoe": ("float64", "Team offensive CPOE", "Derived from PBP", "Yes", "2.1", "", "Offense-only metric"),
    "off_rz_epa": ("float64", "Offensive red zone EPA", "Derived from PBP", "Yes", "0.35", "yardline_100 <= 20", ""),
    "off_rz_td_rate": ("float64", "Offensive red zone TD rate (per drive)", "Derived from PBP", "Yes", "0.62", "0-1", ""),
    "def_rz_td_rate": ("float64", "Defensive red zone TD rate allowed", "Derived from PBP", "Yes", "0.55", "0-1", ""),
    "rz_td_rate": ("float64", "Red zone TD conversion rate", "Derived from PBP", "Yes", "0.60", "0-1", "EWM target column"),
    "cpoe": ("float64", "Completion Probability Over Expected", "Derived from PBP", "Yes", "3.5", "", "EWM target column"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in pbp_metric_cols.items():
    add("Silver", "team_pbp_metrics", col, dtype, desc, src, null, ex, rules, notes)

# Note: all PBP metrics also get _roll3, _roll6, _std, and _ewm3 variants
add("Silver", "team_pbp_metrics", "*_roll3", "float64", "3-game rolling average (all PBP metrics)", "Derived", "Yes", "", "shift(1) lag applied", "12+ metrics x 3 windows = 36+ columns")
add("Silver", "team_pbp_metrics", "*_roll6", "float64", "6-game rolling average (all PBP metrics)", "Derived", "Yes", "", "shift(1) lag applied", "")
add("Silver", "team_pbp_metrics", "*_std", "float64", "Season-to-date expanding average (all PBP metrics)", "Derived", "Yes", "", "", "")
add("Silver", "team_pbp_metrics", "*_ewm3", "float64", "Exponentially weighted moving average (halflife=3 for core metrics)", "Derived", "Yes", "", "Applied to EWM_TARGET_COLS only", "off_epa, def_epa, success, cpoe, rz_td_rate")

# --- Team Tendencies (team_analytics.py) ---
tendency_cols = {
    "pace": ("float64", "Total plays per game (pass + run)", "Derived from PBP", "Yes", "65.0", "", ""),
    "proe": ("float64", "Pass Rate Over Expected (actual - xpass)", "Derived from PBP", "Yes", "0.03", "", ""),
    "fourth_down_go_rate": ("float64", "4th down go-for-it rate", "Derived from PBP", "Yes", "0.18", "0-1", ""),
    "fourth_down_success_rate": ("float64", "4th down conversion success rate", "Derived from PBP", "Yes", "0.55", "0-1", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in tendency_cols.items():
    add("Silver", "team_tendencies", col, dtype, desc, src, null, ex, rules, notes)

# --- SOS Metrics (team_analytics.py) ---
sos_cols = {
    "off_sos_score": ("float64", "Offensive strength of schedule (opponents' DEF EPA)", "Derived", "Yes", "-0.05", "Lagged; NaN for week 1", ""),
    "def_sos_score": ("float64", "Defensive strength of schedule (opponents' OFF EPA)", "Derived", "Yes", "0.08", "Lagged", ""),
    "adj_off_epa": ("float64", "SOS-adjusted offensive EPA", "Derived (raw_off - off_sos)", "Yes", "0.15", "", ""),
    "adj_def_epa": ("float64", "SOS-adjusted defensive EPA", "Derived (raw_def - def_sos)", "Yes", "-0.10", "", ""),
    "off_sos_rank": ("float64", "Offensive SOS rank (1=hardest)", "Derived", "Yes", "8.0", "1-32", ""),
    "def_sos_rank": ("float64", "Defensive SOS rank (1=hardest)", "Derived", "Yes", "12.0", "1-32", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in sos_cols.items():
    add("Silver", "team_sos", col, dtype, desc, src, null, ex, rules, notes)

# --- Situational Splits (team_analytics.py) ---
sit_cols = {
    "home_off_epa": ("float64", "Offensive EPA in home games", "Derived", "Yes", "0.15", "", "NaN for away games"),
    "away_off_epa": ("float64", "Offensive EPA in away games", "Derived", "Yes", "0.08", "", "NaN for home games"),
    "home_def_epa": ("float64", "Defensive EPA in home games", "Derived", "Yes", "-0.10", "", ""),
    "away_def_epa": ("float64", "Defensive EPA in away games", "Derived", "Yes", "-0.05", "", ""),
    "div_off_epa": ("float64", "Offensive EPA vs divisional opponents", "Derived", "Yes", "0.20", "", ""),
    "nondiv_off_epa": ("float64", "Offensive EPA vs non-divisional opponents", "Derived", "Yes", "0.10", "", ""),
    "leading_off_epa": ("float64", "Offensive EPA when leading by 7+", "Derived", "Yes", "-0.05", "", "Possible game script bias"),
    "trailing_off_epa": ("float64", "Offensive EPA when trailing by 7+", "Derived", "Yes", "0.25", "", "Pass-heavy trailing effect"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in sit_cols.items():
    add("Silver", "team_situational", col, dtype, desc, src, null, ex, rules, notes)

# --- PBP-Derived Metrics (team_analytics.py) ---
pbp_derived = {
    "off_penalties": ("float64", "Offensive penalties committed", "Derived from PBP", "Yes", "4.0", ">=0", ""),
    "off_penalty_yards": ("float64", "Offensive penalty yards", "Derived from PBP", "Yes", "35.0", ">=0", ""),
    "def_penalties": ("float64", "Defensive penalties committed", "Derived from PBP", "Yes", "3.0", ">=0", ""),
    "def_penalty_yards": ("float64", "Defensive penalty yards", "Derived from PBP", "Yes", "28.0", ">=0", ""),
    "off_three_and_out_rate": ("float64", "Offensive three-and-out rate", "Derived from PBP", "Yes", "0.18", "0-1", ""),
    "off_avg_drive_plays": ("float64", "Avg offensive plays per drive", "Derived from PBP", "Yes", "5.8", "", ""),
    "off_avg_drive_yards": ("float64", "Avg offensive yards per drive", "Derived from PBP", "Yes", "32.0", "", ""),
    "off_drives_per_game": ("float64", "Offensive drives per game", "Derived from PBP", "Yes", "11.0", "", ""),
    "off_top_seconds": ("float64", "Offensive time of possession (seconds)", "Derived from PBP", "Yes", "1800.0", "", "Parsed from M:SS format"),
    "off_explosive_pass_rate": ("float64", "Rate of explosive pass plays (20+ yards)", "Derived from PBP", "Yes", "0.08", "0-1", ""),
    "off_explosive_rush_rate": ("float64", "Rate of explosive rush plays (10+ yards)", "Derived from PBP", "Yes", "0.12", "0-1", ""),
    "off_sack_rate": ("float64", "Offensive sack rate (sacks / dropbacks)", "Derived from PBP", "Yes", "0.06", "0-1", ""),
    "def_sack_rate": ("float64", "Defensive sack rate", "Derived from PBP", "Yes", "0.08", "0-1", ""),
    "off_third_down_rate": ("float64", "Offensive 3rd down conversion rate", "Derived from PBP", "Yes", "0.42", "0-1", ""),
    "def_third_down_rate": ("float64", "Defensive 3rd down conversion rate allowed", "Derived from PBP", "Yes", "0.38", "0-1", ""),
    "off_rz_trips": ("float64", "Offensive red zone trips (unique drives)", "Derived from PBP", "Yes", "3.0", ">=0", "3-5 typical per game"),
    "fg_att": ("float64", "Field goal attempts", "Derived from PBP", "Yes", "2.0", ">=0", ""),
    "fg_pct": ("float64", "Field goal accuracy", "Derived from PBP", "Yes", "0.85", "0-1", ""),
    "ko_return_avg": ("float64", "Kickoff return average yards", "Derived from PBP", "Yes", "22.5", "", ""),
    "fumbles_lost": ("float64", "Fumbles lost (offensive)", "Derived from PBP", "Yes", "1.0", ">=0", "Expanding window internally"),
    "own_fumble_recovery_rate": ("float64", "Own fumble recovery rate", "Derived from PBP", "Yes", "0.55", "0-1", "Season-to-date expanding"),
    "is_turnover_lucky": ("int64", "Turnover luck flag (-1/0/1)", "Derived from PBP", "No", "0", "-1=unlucky, 0=neutral, 1=lucky", ">0.60 recovery = lucky"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in pbp_derived.items():
    add("Silver", "team_pbp_derived", col, dtype, desc, src, null, ex, rules, notes)

# --- Game Context (game_context.py) ---
gc_cols = {
    "team": ("string", "Team abbreviation", "Derived (unpivoted from schedules)", "No", "KC", "", "One row per team per game"),
    "opponent": ("string", "Opponent abbreviation", "Derived", "No", "DET", "", ""),
    "is_home": ("bool", "True if team is home", "Derived", "No", "True", "", ""),
    "is_dome": ("bool", "True if game is in dome/closed roof", "Derived", "No", "True", "", ""),
    "temperature": ("float64", "Game temperature (F); 72 for domes", "Derived", "Yes", "72.0", "", "Overridden to 72 for domes"),
    "wind_speed": ("float64", "Wind speed (mph); 0 for domes", "Derived", "Yes", "0.0", "", "Overridden to 0 for domes"),
    "is_high_wind": ("bool", "Wind > 15 mph", "Derived", "No", "False", "", ""),
    "is_cold": ("bool", "Temperature <= 32 F", "Derived", "No", "False", "", ""),
    "rest_days": ("int64", "Days of rest (clipped to 14)", "Derived", "Yes", "7", "Clipped at 14", ""),
    "opponent_rest": ("int64", "Opponent days of rest", "Derived", "Yes", "7", "", ""),
    "is_short_rest": ("bool", "Rest days <= 6", "Derived", "No", "False", "", "Thursday games typically"),
    "is_post_bye": ("bool", "Rest days >= 13", "Derived", "No", "False", "", ""),
    "rest_advantage": ("int64", "rest_days - opponent_rest", "Derived", "No", "0", "", "Positive = more rest"),
    "travel_miles": ("float64", "Travel distance to game venue (miles)", "Derived (Haversine)", "Yes", "1250.0", "0 for home games", "Uses STADIUM_ID_COORDS"),
    "tz_diff": ("float64", "Timezone differential (hours)", "Derived", "No", "3.0", "0-5 typical", "DST-aware via pytz"),
    "head_coach": ("string", "Head coach name", "Derived", "Yes", "Andy Reid", "", ""),
    "coaching_change": ("bool", "Coach changed from prior", "Derived", "No", "False", "", "Off-season or mid-season"),
    "coaching_tenure": ("int64", "Consecutive weeks with same coach", "Derived", "No", "52", ">=1", ""),
    "ref_penalties_per_game": ("float64", "Referee avg penalties per game (entering)", "Derived", "Yes", "14.2", "shift(1) expanding mean", "NaN for week 1"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in gc_cols.items():
    add("Silver", "game_context", col, dtype, desc, src, null, ex, rules, notes)

# --- Playoff Context (game_context.py) ---
playoff_cols = {
    "wins": ("int64", "Cumulative wins entering game", "Derived", "No", "5", "shift(1) cumsum", "Week 1 = 0"),
    "losses": ("int64", "Cumulative losses entering game", "Derived", "No", "3", "", ""),
    "ties": ("int64", "Cumulative ties entering game", "Derived", "No", "0", "", ""),
    "win_pct": ("float64", "Win percentage entering game", "Derived", "No", "0.625", "0-1", ""),
    "division_rank": ("int64", "Division standing (1-4)", "Derived", "No", "2", "1-4", "Tiebreak by wins"),
    "games_behind_division_leader": ("float64", "Games behind division leader in wins", "Derived", "No", "1.0", ">=0", ""),
    "late_season_contention": ("bool", "Win pct >= 0.4 and week >= 10", "Derived", "No", "True", "", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in playoff_cols.items():
    add("Silver", "playoff_context", col, dtype, desc, src, null, ex, rules, notes)

# --- Referee Tendencies ---
add("Silver", "referee_tendencies", "ref_penalties_per_game", "float64", "Referee season avg penalties per game (entering)", "Derived", "Yes", "14.2", "shift(1) expanding mean per referee-season", "")

# --- Player Advanced Profiles (player_advanced_analytics.py) ---
adv_cols_list = [
    ("avg_separation", "float64", "NGS average route separation (yards)", "nfl-data-py (NGS)", "Yes", "2.8", "", "WR/TE; 2016+"),
    ("catch_percentage", "float64", "NGS catch percentage", "nfl-data-py (NGS)", "Yes", "68.5", "", ""),
    ("avg_intended_air_yards", "float64", "NGS average intended air yards", "nfl-data-py (NGS)", "Yes", "9.2", "", ""),
    ("avg_yac_above_expectation", "float64", "NGS YAC above expectation", "nfl-data-py (NGS)", "Yes", "1.5", "", ""),
    ("avg_time_to_throw", "float64", "NGS average time to throw (seconds)", "nfl-data-py (NGS)", "Yes", "2.65", "", "QB metric"),
    ("aggressiveness", "float64", "NGS pass aggressiveness pct", "nfl-data-py (NGS)", "Yes", "18.2", "", "QB metric"),
    ("completion_percentage_above_expectation", "float64", "NGS CPAE", "nfl-data-py (NGS)", "Yes", "3.5", "", ""),
    ("rush_yards_over_expected", "float64", "NGS rush yards over expected", "nfl-data-py (NGS)", "Yes", "12.0", "", "RB metric"),
    ("rush_yards_over_expected_per_att", "float64", "NGS RYOE per attempt", "nfl-data-py (NGS)", "Yes", "0.8", "", ""),
    ("efficiency", "float64", "NGS rushing efficiency", "nfl-data-py (NGS)", "Yes", "4.2", "", ""),
    ("times_pressured_pct", "float64", "PFR pressure rate", "nfl-data-py (PFR)", "Yes", "25.3", "", "QB metric"),
    ("passing_bad_throw_pct", "float64", "PFR bad throw percentage", "nfl-data-py (PFR)", "Yes", "18.5", "", ""),
    ("qbr_total", "float64", "ESPN Total QBR", "nfl-data-py (ESPN)", "Yes", "72.5", "0-100", "QB metric"),
    ("pts_added", "float64", "ESPN points added by QB", "nfl-data-py (ESPN)", "Yes", "8.3", "", ""),
]
for col, dtype, desc, src, null, ex, rules, notes in adv_cols_list:
    add("Silver", "advanced_profiles", col, dtype, desc, src, null, ex, rules, notes)

# --- Historical Profiles (historical_profiles.py) ---
hist_cols = {
    "height_inches": ("float64", "Player height in inches", "Derived (parsed from ht)", "Yes", "74.0", "", ""),
    "speed_score": ("float64", "Bill Barnwell speed score: (wt * 200) / forty^4", "Derived", "Yes", "105.2", "Average RB ~100; elite > 110", ""),
    "bmi": ("float64", "BMI: weight / height_inches^2", "Derived", "Yes", "3.8", "", ""),
    "burst_score": ("float64", "Burst score: vertical + broad_jump", "Derived", "Yes", "160.0", "", ""),
    "catch_radius": ("float64", "Catch radius proxy (= height_inches)", "Derived", "Yes", "74.0", "", "WR/TE metric"),
    "draft_value": ("float64", "Jimmy Johnson draft trade value", "Derived (JJ chart)", "Yes", "1700.0", "Pick 1=3000; Pick 262=0.4", "Extended chart to 262 picks"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in hist_cols.items():
    add("Silver", "historical_profiles", col, dtype, desc, src, null, ex, rules, notes)

# --- Market Data (market_analytics.py) ---
mkt_cols = {
    "team": ("string", "Team abbreviation", "Derived (per-team reshape)", "No", "KC", "One row per team per week", ""),
    "opponent": ("string", "Opponent abbreviation", "Derived", "No", "HOU", "", ""),
    "is_home": ("bool", "True if home team", "Derived", "No", "True", "", ""),
    "opening_spread": ("float64", "Opening spread (team perspective)", "FinnedAI", "Yes", "-10.0", "Negated for away teams", "PRE-GAME safe"),
    "opening_total": ("float64", "Opening over/under total", "FinnedAI", "Yes", "53.5", "Symmetric (same for both teams)", "PRE-GAME safe"),
    "closing_spread": ("float64", "Closing spread (team perspective)", "FinnedAI", "Yes", "-9.5", "Negated for away teams", "RETROSPECTIVE only"),
    "spread_shift": ("float64", "Closing - opening spread", "Derived", "Yes", "0.5", "Negated for away teams", "RETROSPECTIVE"),
    "total_shift": ("float64", "Closing - opening total", "Derived", "Yes", "0.5", "Symmetric", "RETROSPECTIVE"),
    "spread_move_abs": ("float64", "Absolute spread movement", "Derived", "Yes", "0.5", ">=0", ""),
    "total_move_abs": ("float64", "Absolute total movement", "Derived", "Yes", "0.5", ">=0", ""),
    "spread_magnitude": ("float64", "Spread movement bucket (0-3)", "Derived", "Yes", "1.0", "0=none, 1=small, 2=medium, 3=large", "Ordinal"),
    "total_magnitude": ("float64", "Total movement bucket (0-3)", "Derived", "Yes", "1.0", "", ""),
    "crosses_key_spread": ("bool", "Spread crossed key number (3/7/10)", "Derived", "No", "False", "", ""),
    "crosses_key_total": ("bool", "Total crossed key number (41/44/47)", "Derived", "No", "False", "", ""),
    "is_steam_move": ("float64", "Steam move indicator (NaN placeholder)", "Derived", "Yes", "NaN", "Always NaN -- no timestamp data", "FinnedAI limitation"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in mkt_cols.items():
    add("Silver", "market_data", col, dtype, desc, src, null, ex, rules, notes)

# =============================================================================
# GOLD LAYER
# =============================================================================

# --- Fantasy Projections (projection_engine.py) ---
proj_cols = {
    "player_id": ("string", "Player GSIS ID", "Bronze player_weekly", "No", "00-0033873", "", ""),
    "player_name": ("string", "Player display name", "Bronze player_weekly", "No", "P.Mahomes", "", ""),
    "position": ("string", "Fantasy position", "Bronze player_weekly", "No", "QB", "QB/RB/WR/TE", ""),
    "recent_team": ("string", "Team abbreviation", "Bronze player_weekly", "No", "KC", "", ""),
    "proj_season": ("int64", "Projection target season", "Derived", "No", "2026", "", ""),
    "proj_week": ("int64", "Projection target week", "Derived", "No", "1", "", ""),
    "proj_passing_yards": ("float64", "Projected passing yards", "Derived (weighted baseline x usage x matchup)", "Yes", "275.0", ">=0", "QB only"),
    "proj_passing_tds": ("float64", "Projected passing TDs", "Derived", "Yes", "1.8", ">=0", "QB only"),
    "proj_interceptions": ("float64", "Projected interceptions", "Derived", "Yes", "0.7", ">=0", "QB only"),
    "proj_rushing_yards": ("float64", "Projected rushing yards", "Derived", "Yes", "55.0", ">=0", "QB/RB"),
    "proj_rushing_tds": ("float64", "Projected rushing TDs", "Derived", "Yes", "0.4", ">=0", "QB/RB"),
    "proj_carries": ("float64", "Projected rush attempts", "Derived", "Yes", "14.0", ">=0", "RB only"),
    "proj_receptions": ("float64", "Projected receptions", "Derived", "Yes", "4.5", ">=0", "RB/WR/TE"),
    "proj_receiving_yards": ("float64", "Projected receiving yards", "Derived", "Yes", "45.0", ">=0", "RB/WR/TE"),
    "proj_receiving_tds": ("float64", "Projected receiving TDs", "Derived", "Yes", "0.3", ">=0", "RB/WR/TE"),
    "proj_targets": ("float64", "Projected targets", "Derived", "Yes", "6.0", ">=0", "WR/TE"),
    "projected_points": ("float64", "Projected fantasy points (selected scoring)", "Derived (scoring_calculator)", "No", "18.5", ">=0 for skill positions", "Ceiling-shrunk at 15/20/25 thresholds"),
    "position_rank": ("int64", "Rank within position by projected_points", "Derived", "No", "3", "1-based", ""),
    "is_bye_week": ("bool", "True if player is on bye", "Derived", "No", "False", "All proj stats = 0 when True", ""),
    "is_rookie_projection": ("bool", "True if no rolling history (rookie baseline used)", "Derived", "No", "False", "", "Conservative baselines applied"),
    "vegas_multiplier": ("float64", "Vegas-adjusted output multiplier", "Derived (implied_total / 23.0)", "Yes", "1.08", "Clipped to [0.80, 1.20]", "RB run-heavy bonus up to 1.26"),
    "team_constraint_factor": ("float64", "Team-total coherence scaling factor", "Derived", "Yes", "0.95", "", "Phase 42: game-level constraints"),
    "projected_floor": ("float64", "Lower confidence bound", "Derived (position variance)", "Yes", "10.5", "", "Position multipliers: QB 45%, RB 40%, WR 38%, TE 35%"),
    "projected_ceiling": ("float64", "Upper confidence bound", "Derived", "Yes", "26.5", "", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in proj_cols.items():
    add("Gold", "fantasy_projections", col, dtype, desc, src, null, ex, rules, notes)

# --- Game Predictions (ensemble_training.py / feature_engineering.py) ---
pred_cols = {
    "game_id": ("string", "Unique game identifier", "Bronze schedules", "No", "2024_01_KC_DET", "", ""),
    "season": ("int64", "NFL season year", "Bronze schedules", "No", "2024", "", ""),
    "week": ("int64", "NFL week number", "Bronze schedules", "No", "1", "", ""),
    "team_home": ("string", "Home team abbreviation", "Bronze schedules", "No", "DET", "", ""),
    "team_away": ("string", "Away team abbreviation", "Bronze schedules", "No", "KC", "", ""),
    "predicted_spread": ("float64", "Model-predicted point spread (home perspective)", "Ensemble (XGB+LGB+CB+Ridge)", "No", "-2.5", "", ""),
    "predicted_total": ("float64", "Model-predicted game total", "Ensemble (XGB+LGB+CB+Ridge)", "No", "48.0", "", ""),
    "spread_line": ("float64", "Vegas spread line", "Bronze schedules", "Yes", "-3.0", "", ""),
    "total_line": ("float64", "Vegas over/under", "Bronze schedules", "Yes", "47.5", "", ""),
    "spread_edge": ("float64", "Model spread minus Vegas spread", "Derived", "No", "0.5", "", "Edge >= 3.0 = high confidence"),
    "total_edge": ("float64", "Model total minus Vegas total", "Derived", "No", "0.5", "", ""),
    "edge_tier": ("string", "Edge confidence tier", "Derived", "No", "medium", "high (>=3.0) / medium (>=1.5) / low", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in pred_cols.items():
    add("Gold", "game_predictions", col, dtype, desc, src, null, ex, rules, notes)

# --- Game Feature Vector (feature_engineering.py) ---
# Group these by category rather than listing all 1139
fv_groups = [
    ("game_feature_vector", "diff_off_epa_per_play_roll3 (+ 35 similar)", "float64", "Home-away differential of team PBP rolling metrics (12 base metrics x 3 windows = 36 diff columns)", "Derived (home - away)", "Yes", "0.08", "Core model features", ""),
    ("game_feature_vector", "diff_off_epa_per_play_ewm3 (+ 6 similar)", "float64", "Home-away differential of EWM metrics (7 EWM target cols)", "Derived", "Yes", "0.10", "", ""),
    ("game_feature_vector", "off_epa_per_play_roll3_home (+ ~240)", "float64", "Raw team features with _home/_away suffix (all PBP metrics x 3 windows per side)", "Derived", "Yes", "0.12", "", "Included alongside differentials"),
    ("game_feature_vector", "diff_pace_roll3 (+ ~15)", "float64", "Tendency differentials: pace, PROE, 4th down rates", "Derived", "Yes", "2.0", "", ""),
    ("game_feature_vector", "diff_off_sos_score_roll3 (+ ~18)", "float64", "SOS and adjusted EPA differentials", "Derived", "Yes", "-0.03", "", ""),
    ("game_feature_vector", "diff_home_off_epa_roll3 (+ ~35)", "float64", "Situational split differentials (12 splits x 3 windows)", "Derived", "Yes", "0.05", "", ""),
    ("game_feature_vector", "diff_off_penalties_roll3 (+ ~60)", "float64", "PBP-derived differentials: penalties, turnovers, explosive, drives, sacks, TOP, FG, returns", "Derived", "Yes", "0.5", "", ""),
    ("game_feature_vector", "is_dome_home / temperature_home / wind_speed_home (+ ~20)", "float64", "Pre-game context: weather, rest, travel, coaching per side", "Derived", "Yes", "72.0", "Knowable before kickoff", ""),
    ("game_feature_vector", "diff_wins / diff_win_pct / division_rank_home (+ ~10)", "float64", "Cumulative record and playoff context differentials", "Derived", "Yes", "2.0", "", ""),
    ("game_feature_vector", "ref_penalties_per_game_home/away", "float64", "Referee tendency features", "Derived", "Yes", "14.2", "", ""),
    ("game_feature_vector", "opening_spread_home / opening_total_home (+ 2)", "float64", "Market data pre-game features (opening lines only)", "FinnedAI via Silver", "Yes", "-3.0", "Only opening lines; closing excluded", "NaN for 2022-2024"),
    ("game_feature_vector", "diff_win_streak / diff_ats_cover_sum3 / diff_ats_margin_avg3", "float64", "Momentum/streak features (3 cols)", "Derived from Bronze schedules", "Yes", "2.0", "", "Exist but not in production P30 model"),
    ("game_feature_vector", "div_game", "int64", "Binary: division rivalry game", "Derived", "No", "1", "0 or 1", ""),
]
for dataset, col, dtype, desc, src, null, ex, rules, notes in fv_groups:
    add("Gold", dataset, col, dtype, desc, src, null, ex, rules, notes)

# --- Player Feature Vector (player_feature_engineering.py) ---
pf_groups = [
    ("player_feature_vector", "passing_yards_roll3 (+ ~44)", "float64", "Player rolling stats: 15 base stats x 3 windows (roll3/roll6/std) = 45 columns", "Silver player_rolling", "Yes", "260.0", "shift(1) lag applied", ""),
    ("player_feature_vector", "yards_per_carry_roll3 (+ 11)", "float64", "Efficiency ratios: 6 ratios x 2 windows (roll3/roll6) = 12 columns", "Derived", "Yes", "4.8", "Safe division (NaN for 0 denominator)", ""),
    ("player_feature_vector", "expected_td_pos_avg / expected_td_player", "float64", "TD regression features from red zone share x conversion rate", "Derived", "Yes", "0.35", "", ""),
    ("player_feature_vector", "snap_pct_delta / target_share_delta / carry_share_delta", "float64", "Momentum deltas: roll3 minus roll6 for usage metrics", "Derived", "Yes", "0.03", "Positive = trending up", ""),
    ("player_feature_vector", "implied_team_total", "float64", "Vegas implied team scoring total", "Derived from Bronze schedules", "Yes", "24.5", "Clipped to [5.0, 45.0]", ""),
    ("player_feature_vector", "off_epa_per_play_roll3 (+ ~30 team)", "float64", "Team-level PBP metrics joined on recent_team+season+week", "Silver team sources", "Yes", "0.12", "", "Subset of team features"),
    ("player_feature_vector", "backup_qb_start", "float64", "Binary: backup QB starting", "Silver player_quality", "Yes", "0.0", "", "Phase 28 player quality"),
    ("player_feature_vector", "graph_injury_cascade_* (planned)", "float64", "Graph-derived injury cascade features (Neo4j)", "Neo4j (deferred)", "Yes", "NaN", "NaN-filled when unavailable", "Phase 5 planned"),
]
for dataset, col, dtype, desc, src, null, ex, rules, notes in pf_groups:
    add("Gold", dataset, col, dtype, desc, src, null, ex, rules, notes)

# --- Player ML Predictions (player_model_training.py) ---
pml_cols = {
    "player_id": ("string", "Player GSIS ID", "Bronze", "No", "00-0033873", "", ""),
    "position": ("string", "Player position", "Bronze", "No", "QB", "QB only in v3.0 (SHIP); RB/WR/TE SKIP", ""),
    "stat": ("string", "Predicted stat name", "Config (POSITION_STAT_PROFILE)", "No", "passing_yards", "", ""),
    "predicted_value": ("float64", "ML-predicted stat value", "XGB+LGB+Ridge per-stat ensemble", "No", "265.0", ">=0", ""),
    "model_type": ("string", "Model source indicator", "Derived", "No", "ml", "ml or heuristic", "Ship gate determines routing"),
}
for col, (dtype, desc, src, null, ex, rules, notes) in pml_cols.items():
    add("Gold", "player_ml_predictions", col, dtype, desc, src, null, ex, rules, notes)

# --- ML Projection Router Output ---
router_cols = {
    "projection_source": ("string", "Which engine produced projection", "ML router", "No", "ml_qb", "ml_qb / heuristic_rb / etc.", ""),
    "confidence_lower": ("float64", "MAPIE lower confidence bound (optional)", "MAPIE", "Yes", "220.0", "", "Requires mapie package"),
    "confidence_upper": ("float64", "MAPIE upper confidence bound (optional)", "MAPIE", "Yes", "310.0", "", ""),
}
for col, (dtype, desc, src, null, ex, rules, notes) in router_cols.items():
    add("Gold", "ml_projection_router", col, dtype, desc, src, null, ex, rules, notes)


# =============================================================================
# Write CSV
# =============================================================================
with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow(row)

print(f"Data dictionary written to {OUTPUT_PATH} ({len(rows)} rows)")
