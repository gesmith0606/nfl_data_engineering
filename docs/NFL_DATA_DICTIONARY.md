# NFL Data Dictionary

**Version:** 2.0
**Last Updated:** March 8, 2026
**Purpose:** Complete schema reference for all Bronze data types in the NFL Data Engineering pipeline
**Related:** [src/config.py](../src/config.py) | [src/nfl_data_adapter.py](../src/nfl_data_adapter.py) | [scripts/bronze_ingestion_simple.py](../scripts/bronze_ingestion_simple.py)

This document is the single source of truth for Bronze layer schemas. Column specs for locally available data types are auto-generated from Parquet files. For data types requiring API ingestion, representative columns are documented from test mocks, config constants, and adapter method signatures.

---

## Table of Contents

- [Bronze Layer -- Locally Verified](#bronze-layer----locally-verified)
  - [Schedules (Games)](#schedules-games)
  - [Player Weekly Stats](#player-weekly-stats)
  - [Player Seasonal Stats](#player-seasonal-stats)
  - [Snap Counts](#snap-counts)
  - [Injuries](#injuries)
  - [Rosters](#rosters)
- [Bronze Layer -- From Config/Tests](#bronze-layer----from-configtests)
  - [Play-by-Play (PBP)](#play-by-play-pbp)
  - [NGS Passing](#ngs-passing)
  - [NGS Rushing](#ngs-rushing)
  - [NGS Receiving](#ngs-receiving)
  - [PFR Weekly Passing](#pfr-weekly-passing)
  - [PFR Weekly Rushing](#pfr-weekly-rushing)
  - [PFR Weekly Receiving](#pfr-weekly-receiving)
  - [PFR Weekly Defense](#pfr-weekly-defense)
  - [PFR Seasonal Passing](#pfr-seasonal-passing)
  - [PFR Seasonal Rushing](#pfr-seasonal-rushing)
  - [PFR Seasonal Receiving](#pfr-seasonal-receiving)
  - [PFR Seasonal Defense](#pfr-seasonal-defense)
  - [QBR Weekly](#qbr-weekly)
  - [QBR Seasonal](#qbr-seasonal)
  - [Depth Charts](#depth-charts)
  - [Draft Picks](#draft-picks)
  - [Combine](#combine)
  - [Teams](#teams)
- [Silver Layer Tables](#silver-layer-tables)
- [Gold Layer Tables](#gold-layer-tables)
- [Data Types and Constraints](#data-types-and-constraints)
- [Business Rules](#business-rules)

---

## DATA_TYPE_SEASON_RANGES Quick Reference

The following table summarizes the valid season ranges for each data type, as defined in `src/config.py`:

| Data Type | Min Season | Max Season | nfl-data-py Function | Adapter Method |
|-----------|-----------|-----------|---------------------|----------------|
| schedules | 1999 | dynamic | `import_schedules()` | `fetch_schedules()` |
| pbp | 1999 | dynamic | `import_pbp_data()` | `fetch_pbp()` |
| player_weekly | 2002 | dynamic | `import_weekly_data()` | `fetch_weekly_data()` |
| player_seasonal | 2002 | dynamic | `import_seasonal_data()` | `fetch_seasonal_data()` |
| snap_counts | 2012 | dynamic | `import_snap_counts()` | `fetch_snap_counts()` |
| injuries | 2009 | dynamic | `import_injuries()` | `fetch_injuries()` |
| rosters | 2002 | dynamic | `import_seasonal_rosters()` | `fetch_rosters()` |
| teams | 1999 | dynamic | `import_team_desc()` | `fetch_team_descriptions()` |
| ngs | 2016 | dynamic | `import_ngs_data()` | `fetch_ngs()` |
| pfr_weekly | 2018 | dynamic | `import_weekly_pfr()` | `fetch_pfr_weekly()` |
| pfr_seasonal | 2018 | dynamic | `import_seasonal_pfr()` | `fetch_pfr_seasonal()` |
| qbr | 2006 | dynamic | `import_qbr()` | `fetch_qbr()` |
| depth_charts | 2001 | dynamic | `import_depth_charts()` | `fetch_depth_charts()` |
| draft_picks | 2000 | dynamic | `import_draft_picks()` | `fetch_draft_picks()` |
| combine | 2000 | dynamic | `import_combine_data()` | `fetch_combine()` |

**Note:** "dynamic" max season = `datetime.date.today().year + 1` (currently 2027). This allows referencing next year's draft/combine data without hardcoding.

---

## Bronze Layer -- Locally Verified

These data types have complete column specs auto-generated from local Parquet files in `data/bronze/`.

---

### Schedules (Games)

**Source:** `nfl-data-py` function `import_schedules()` via `NFLDataAdapter.fetch_schedules()`
**Seasons:** 1999-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/schedules/season=YYYY/`
**Local Path:** `data/bronze/schedules/season=YYYY/` (also `data/bronze/games/season=YYYY/` for legacy ingestion)
**Known Quirks:** The `NFLDataFetcher.fetch_game_schedules()` in `nfl_data_integration.py` adds metadata columns (`data_source`, `ingestion_timestamp`, `seasons_requested`, `week_filter`) that are not part of the upstream schema.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| game_id | string | Yes | Unique game identifier (YYYY_WW_AWAY_HOME) | "2021_01_TB_DAL" |
| season | int64 | Yes | NFL season year | 2021 |
| game_type | string | Yes | Game type (REG, WC, DIV, CON, SB) | "REG" |
| week | int64 | Yes | NFL week number (1-18 regular, 19-22 playoffs) | 1 |
| gameday | string | Yes | Game date string | "2021-09-09" |
| weekday | string | Yes | Day of the week | "Thursday" |
| gametime | string | Yes | Kickoff time (Eastern) | "20:20" |
| away_team | string | Yes | Away team abbreviation | "TB" |
| away_score | int64 | Yes | Final away team score | 31 |
| home_team | string | Yes | Home team abbreviation | "DAL" |
| home_score | int64 | Yes | Final home team score | 29 |
| location | string | Yes | Game location indicator | "Home" |
| result | int64 | Yes | Home team margin (home_score - away_score) | -2 |
| total | int64 | Yes | Combined score (home + away) | 60 |
| overtime | int64 | Yes | Overtime flag (1 = OT, 0 = regulation) | 0 |
| old_game_id | int64 | Yes | Legacy game ID from older data sources | 2021091000 |
| gsis | int64 | Yes | NFL GSIS game identifier | 5844 |
| nfl_detail_id | string | Yes | NFL detail API identifier | "..." |
| pfr | string | Yes | Pro Football Reference game ID | "202109090dal" |
| pff | double | Yes | Pro Football Focus game ID | NaN |
| espn | int64 | Yes | ESPN game identifier | 401326313 |
| ftn | double | Yes | FTN game identifier | NaN |
| away_rest | int64 | Yes | Days rest for away team | 7 |
| home_rest | int64 | Yes | Days rest for home team | 7 |
| away_moneyline | double | Yes | Away team moneyline odds | -200 |
| home_moneyline | double | Yes | Home team moneyline odds | 170 |
| spread_line | double | Yes | Point spread (negative = home favored) | -7.5 |
| away_spread_odds | double | Yes | Away spread odds | -110 |
| home_spread_odds | double | Yes | Home spread odds | -110 |
| total_line | double | Yes | Over/under line | 51.5 |
| under_odds | double | Yes | Under odds | -110 |
| over_odds | double | Yes | Over odds | -110 |
| div_game | int64 | Yes | Division game flag (1 = divisional) | 0 |
| roof | string | Yes | Roof type (outdoors, dome, closed, open) | "outdoors" |
| surface | string | Yes | Playing surface type | "grass" |
| temp | double | Yes | Temperature in Fahrenheit | 82.0 |
| wind | double | Yes | Wind speed in mph | 7.0 |
| away_qb_id | string | Yes | Away starting QB GSIS ID | "00-0034857" |
| home_qb_id | string | Yes | Home starting QB GSIS ID | "00-0033873" |
| away_qb_name | string | Yes | Away starting QB name | "Tom Brady" |
| home_qb_name | string | Yes | Home starting QB name | "Dak Prescott" |
| away_coach | string | Yes | Away head coach | "Bruce Arians" |
| home_coach | string | Yes | Home head coach | "Mike McCarthy" |
| referee | string | Yes | Referee name | "Scott Novak" |
| stadium_id | string | Yes | Stadium identifier | "DAL00" |
| stadium | string | Yes | Stadium name | "AT&T Stadium" |
| data_source | string | Yes | Ingestion source tag | "nfl-data-py" |
| ingestion_timestamp | timestamp[ns] | Yes | When data was ingested | 2026-03-06 22:37:34 |
| seasons_requested | string | Yes | Seasons requested in API call | "[2021]" |
| week_filter | null | Yes | Week filter applied (null if none) | null |

---

### Player Weekly Stats

**Source:** `nfl-data-py` function `import_weekly_data()` via `NFLDataAdapter.fetch_weekly_data()`
**Seasons:** 2002-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/players/weekly/season=YYYY/week=WW/`
**Local Path:** `data/bronze/players/weekly/season=YYYY/week=WW/`
**Known Quirks:** Column `receiving_air_yards` (not `air_yards`) -- mapped to `air_yards` in Silver layer prep functions. The `wopr` column becomes `wopr_x`/`wopr_y` in seasonal data due to merge artifacts.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| player_id | string | Yes | Player GSIS identifier | "00-0033873" |
| player_name | string | Yes | Short player name | "P.Mahomes" |
| player_display_name | string | Yes | Full display name | "Patrick Mahomes" |
| position | string | Yes | Player position | "QB" |
| position_group | string | Yes | Position group (QB, RB, WR, TE) | "QB" |
| headshot_url | string | Yes | URL to player headshot image | "https://..." |
| recent_team | string | Yes | Most recent team abbreviation | "KC" |
| season | int32 | Yes | NFL season year | 2021 |
| week | int32 | Yes | NFL week number | 1 |
| season_type | string | Yes | Season type (REG, POST) | "REG" |
| opponent_team | string | Yes | Opponent team abbreviation | "CLE" |
| completions | int32 | Yes | Passing completions | 27 |
| attempts | int32 | Yes | Passing attempts | 36 |
| passing_yards | float | Yes | Total passing yards | 337.0 |
| passing_tds | int32 | Yes | Passing touchdowns | 3 |
| interceptions | float | Yes | Interceptions thrown | 0.0 |
| sacks | float | Yes | Times sacked | 1.0 |
| sack_yards | float | Yes | Yards lost to sacks | -8.0 |
| sack_fumbles | int32 | Yes | Fumbles on sacks | 0 |
| sack_fumbles_lost | int32 | Yes | Sack fumbles lost to defense | 0 |
| passing_air_yards | float | Yes | Total air yards on pass attempts | 180.0 |
| passing_yards_after_catch | float | Yes | Total YAC on completions | 157.0 |
| passing_first_downs | float | Yes | First downs via passing | 18.0 |
| passing_epa | float | Yes | Expected points added on pass plays | 12.5 |
| passing_2pt_conversions | int32 | Yes | Successful 2-point passing conversions | 0 |
| pacr | float | Yes | Passer Air Conversion Ratio | 1.87 |
| dakota | float | Yes | DAKOTA completion model metric | 0.75 |
| carries | int32 | Yes | Rushing attempts | 5 |
| rushing_yards | float | Yes | Total rushing yards | 18.0 |
| rushing_tds | int32 | Yes | Rushing touchdowns | 0 |
| rushing_fumbles | float | Yes | Fumbles on rushing plays | 0.0 |
| rushing_fumbles_lost | float | Yes | Rushing fumbles lost | 0.0 |
| rushing_first_downs | float | Yes | First downs via rushing | 1.0 |
| rushing_epa | float | Yes | Expected points added on rush plays | -1.2 |
| rushing_2pt_conversions | int32 | Yes | Successful 2-point rushing conversions | 0 |
| receptions | int32 | Yes | Total receptions | 0 |
| targets | int32 | Yes | Times targeted as receiver | 0 |
| receiving_yards | float | Yes | Total receiving yards | 0.0 |
| receiving_tds | int32 | Yes | Receiving touchdowns | 0 |
| receiving_fumbles | float | Yes | Fumbles after reception | 0.0 |
| receiving_fumbles_lost | float | Yes | Receiving fumbles lost | 0.0 |
| receiving_air_yards | float | Yes | Air yards on targets received | 0.0 |
| receiving_yards_after_catch | float | Yes | YAC on receptions | 0.0 |
| receiving_first_downs | float | Yes | First downs via receiving | 0.0 |
| receiving_epa | float | Yes | Expected points added on receiving plays | 0.0 |
| receiving_2pt_conversions | int32 | Yes | Successful 2-point receiving conversions | 0 |
| racr | float | Yes | Receiver Air Conversion Ratio | NaN |
| target_share | float | Yes | Share of team targets | 0.0 |
| air_yards_share | float | Yes | Share of team air yards | 0.0 |
| wopr | float | Yes | Weighted Opportunity Rating | 0.0 |
| special_teams_tds | float | Yes | Special teams touchdowns | 0.0 |
| fantasy_points | float | Yes | Standard scoring fantasy points | 18.2 |
| fantasy_points_ppr | float | Yes | PPR scoring fantasy points | 18.2 |
| data_source | string | Yes | Ingestion source tag | "nfl-data-py" |
| ingestion_timestamp | timestamp[ns] | Yes | When data was ingested | 2026-03-06 22:37:34 |

---

### Player Seasonal Stats

**Source:** `nfl-data-py` function `import_seasonal_data()` via `NFLDataAdapter.fetch_seasonal_data()`
**Seasons:** 2002-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/players/seasonal/season=YYYY/`
**Local Path:** `data/bronze/players/seasonal/season=YYYY/`
**Known Quirks:** Contains `wopr_x` and `wopr_y` columns (merge artifact from nfl-data-py joining weekly and seasonal shares). Additional seasonal share columns (`tgt_sh`, `ay_sh`, `yac_sh`, `ry_sh`, etc.) are seasonal-only aggregates not present in weekly data.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| player_id | string | Yes | Player GSIS identifier | "00-0033873" |
| season | int64 | Yes | NFL season year | 2021 |
| season_type | string | Yes | Season type (REG, POST) | "REG" |
| completions | int32 | Yes | Season total completions | 436 |
| attempts | int32 | Yes | Season total passing attempts | 658 |
| passing_yards | double | Yes | Season total passing yards | 4839.0 |
| passing_tds | int32 | Yes | Season total passing TDs | 37 |
| interceptions | double | Yes | Season total interceptions | 13.0 |
| sacks | double | Yes | Season total sacks taken | 28.0 |
| sack_yards | double | Yes | Season total sack yards lost | -180.0 |
| sack_fumbles | int32 | Yes | Season total sack fumbles | 3 |
| sack_fumbles_lost | int32 | Yes | Season total sack fumbles lost | 1 |
| passing_air_yards | double | Yes | Season total air yards | 3200.0 |
| passing_yards_after_catch | double | Yes | Season total YAC | 1639.0 |
| passing_first_downs | double | Yes | Season total passing first downs | 230.0 |
| passing_epa | double | Yes | Season total passing EPA | 120.5 |
| passing_2pt_conversions | int32 | Yes | Season total passing 2pt conversions | 1 |
| pacr | double | Yes | Season PACR | 1.51 |
| dakota | double | Yes | Season DAKOTA metric | 0.68 |
| carries | int32 | Yes | Season total carries | 66 |
| rushing_yards | double | Yes | Season total rushing yards | 381.0 |
| rushing_tds | int32 | Yes | Season total rushing TDs | 2 |
| rushing_fumbles | double | Yes | Season total rushing fumbles | 2.0 |
| rushing_fumbles_lost | double | Yes | Season total rushing fumbles lost | 1.0 |
| rushing_first_downs | double | Yes | Season total rushing first downs | 20.0 |
| rushing_epa | double | Yes | Season total rushing EPA | 5.3 |
| rushing_2pt_conversions | int32 | Yes | Season total rushing 2pt conversions | 0 |
| receptions | int32 | Yes | Season total receptions | 0 |
| targets | int32 | Yes | Season total targets | 0 |
| receiving_yards | double | Yes | Season total receiving yards | 0.0 |
| receiving_tds | int32 | Yes | Season total receiving TDs | 0 |
| receiving_fumbles | double | Yes | Season total receiving fumbles | 0.0 |
| receiving_fumbles_lost | double | Yes | Season total receiving fumbles lost | 0.0 |
| receiving_air_yards | double | Yes | Season total receiving air yards | 0.0 |
| receiving_yards_after_catch | double | Yes | Season total receiving YAC | 0.0 |
| receiving_first_downs | double | Yes | Season total receiving first downs | 0.0 |
| receiving_epa | double | Yes | Season total receiving EPA | 0.0 |
| receiving_2pt_conversions | int32 | Yes | Season total receiving 2pt conversions | 0 |
| racr | double | Yes | Season RACR | NaN |
| target_share | double | Yes | Season average target share | 0.0 |
| air_yards_share | double | Yes | Season average air yards share | 0.0 |
| wopr_x | double | Yes | WOPR from weekly data merge | 0.0 |
| special_teams_tds | double | Yes | Season total special teams TDs | 0.0 |
| fantasy_points | double | Yes | Season total standard fantasy points | 350.2 |
| fantasy_points_ppr | double | Yes | Season total PPR fantasy points | 350.2 |
| games | int64 | Yes | Games played in season | 17 |
| tgt_sh | double | Yes | Seasonal target share | 0.0 |
| ay_sh | double | Yes | Seasonal air yards share | 0.0 |
| yac_sh | double | Yes | Seasonal YAC share | 0.0 |
| wopr_y | double | Yes | WOPR from seasonal data merge | 0.0 |
| ry_sh | double | Yes | Seasonal rushing yards share | 0.15 |
| rtd_sh | double | Yes | Seasonal rushing TD share | 0.08 |
| rfd_sh | double | Yes | Seasonal rushing first down share | 0.10 |
| rtdfd_sh | double | Yes | Seasonal rushing TD + first down share | 0.09 |
| dom | double | Yes | Dominator rating (target share + rushing share) | 0.15 |
| w8dom | double | Yes | Weighted dominator rating | 0.12 |
| yptmpa | double | Yes | Yards per team pass attempt | 0.0 |
| ppr_sh | double | Yes | PPR fantasy points share | 0.05 |
| data_source | string | Yes | Ingestion source tag | "nfl-data-py" |
| ingestion_timestamp | timestamp[ns] | Yes | When data was ingested | 2026-03-06 22:37:34 |

---

### Snap Counts

**Source:** `nfl-data-py` function `import_snap_counts()` via `NFLDataAdapter.fetch_snap_counts()`
**Seasons:** 2012-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/players/snaps/season=YYYY/week=WW/`
**Local Path:** `data/bronze/players/snaps/season=YYYY/week=WW/`
**Known Quirks:** Uses `offense_pct` (not `snap_pct`) and `player` (not `player_id`) -- column name mapping handled in `silver_player_transformation.py`. The adapter method signature is `fetch_snap_counts(season, week)` taking positional args, not `seasons` list.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| game_id | string | Yes | Unique game identifier | "2021_01_TB_DAL" |
| pfr_game_id | string | Yes | Pro Football Reference game ID | "202109090dal" |
| season | int32 | Yes | NFL season year | 2021 |
| game_type | string | Yes | Game type (REG, POST) | "REG" |
| week | int32 | Yes | NFL week number | 1 |
| player | string | Yes | Player name | "Dak Prescott" |
| pfr_player_id | string | Yes | PFR player identifier | "PresDa01" |
| position | string | Yes | Player position | "QB" |
| team | string | Yes | Team abbreviation | "DAL" |
| opponent | string | Yes | Opponent team abbreviation | "TB" |
| offense_snaps | double | Yes | Number of offensive snaps played | 72.0 |
| offense_pct | double | Yes | Percentage of offensive snaps (0-100) | 100.0 |
| defense_snaps | double | Yes | Number of defensive snaps played | 0.0 |
| defense_pct | double | Yes | Percentage of defensive snaps (0-100) | 0.0 |
| st_snaps | double | Yes | Number of special teams snaps played | 0.0 |
| st_pct | double | Yes | Percentage of special teams snaps (0-100) | 0.0 |
| data_source | string | Yes | Ingestion source tag | "nfl-data-py" |
| ingestion_timestamp | timestamp[ns] | Yes | When data was ingested | 2026-03-06 22:37:34 |

---

### Injuries

**Source:** `nfl-data-py` function `import_injuries()` via `NFLDataAdapter.fetch_injuries()`
**Seasons:** 2009-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/players/injuries/season=YYYY/`
**Local Path:** `data/bronze/players/injuries/season=YYYY/`
**Known Quirks:** Injury status multipliers used in projection engine: Active=1.0, Questionable=0.85, Doubtful=0.50, Out/IR/PUP=0.0. The `report_status` column contains the game-day designation used for these multipliers.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int32 | Yes | NFL season year | 2021 |
| game_type | string | Yes | Game type (REG, POST) | "REG" |
| team | string | Yes | Team abbreviation | "KC" |
| week | int32 | Yes | NFL week number | 1 |
| gsis_id | string | Yes | Player GSIS identifier | "00-0033873" |
| position | string | Yes | Player position | "QB" |
| full_name | string | Yes | Player full name | "Patrick Mahomes" |
| first_name | string | Yes | Player first name | "Patrick" |
| last_name | string | Yes | Player last name | "Mahomes" |
| report_primary_injury | string | Yes | Primary injury from game report | "Knee" |
| report_secondary_injury | string | Yes | Secondary injury from game report | null |
| report_status | string | Yes | Game report status (Questionable, Doubtful, Out) | "Questionable" |
| practice_primary_injury | string | Yes | Primary injury from practice report | "Knee" |
| practice_secondary_injury | string | Yes | Secondary injury from practice report | null |
| practice_status | string | Yes | Practice participation status | "Limited Participation" |
| date_modified | timestamp[ns, tz=UTC] | Yes | When injury record was last modified | 2021-09-08T18:00:00Z |
| data_source | string | Yes | Ingestion source tag | "nfl-data-py" |
| ingestion_timestamp | timestamp[ns] | Yes | When data was ingested | 2026-03-06 22:37:34 |

---

### Rosters

**Source:** `nfl-data-py` function `import_seasonal_rosters()` via `NFLDataAdapter.fetch_rosters()`
**Seasons:** 2002-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/players/rosters/season=YYYY/`
**Local Path:** `data/bronze/players/rosters/season=YYYY/`
**Known Quirks:** MUST use `import_seasonal_rosters` (not `import_rosters`) -- the latter returns a different schema. Contains cross-platform IDs (ESPN, Yahoo, Sleeper, PFR, PFF, Rotowire, etc.) for player matching across data sources.

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int32 | Yes | NFL season year | 2021 |
| team | string | Yes | Team abbreviation | "KC" |
| position | string | Yes | Primary position | "QB" |
| depth_chart_position | string | Yes | Depth chart position designation | "QB" |
| jersey_number | double | Yes | Jersey number | 15.0 |
| status | string | Yes | Roster status (ACT, RES, CUT, etc.) | "ACT" |
| player_name | string | Yes | Player name | "Patrick Mahomes" |
| first_name | string | Yes | First name | "Patrick" |
| last_name | string | Yes | Last name | "Mahomes" |
| birth_date | timestamp[ns] | Yes | Date of birth | 1995-09-17 |
| height | double | Yes | Height in inches | 75.0 |
| weight | int32 | Yes | Weight in pounds | 225 |
| college | string | Yes | College attended | "Texas Tech" |
| player_id | string | Yes | GSIS player identifier | "00-0033873" |
| espn_id | string | Yes | ESPN player ID | "3139477" |
| sportradar_id | string | Yes | Sportradar UUID | "..." |
| yahoo_id | string | Yes | Yahoo player ID | "30123" |
| rotowire_id | string | Yes | Rotowire player ID | "12110" |
| pff_id | string | Yes | PFF player ID | "46088" |
| pfr_id | string | Yes | PFR player ID | "MahoPa00" |
| fantasy_data_id | string | Yes | FantasyData player ID | "17870" |
| sleeper_id | string | Yes | Sleeper app player ID | "4046" |
| years_exp | int32 | Yes | Years of NFL experience | 4 |
| headshot_url | string | Yes | URL to player headshot | "https://..." |
| ngs_position | string | Yes | Next Gen Stats position classification | "QUARTERBACK" |
| week | int32 | Yes | Roster week snapshot | 1 |
| game_type | string | Yes | Game type for roster snapshot | "REG" |
| status_description_abbr | string | Yes | Status description abbreviation | "A01" |
| football_name | string | Yes | Football-specific name | "Patrick" |
| esb_id | string | Yes | Elias Sports Bureau ID | "MAH687290" |
| gsis_it_id | string | Yes | GSIS IT system ID | "47218" |
| smart_id | string | Yes | NFL SMART ID | "3200..." |
| entry_year | int32 | Yes | Year entered NFL | 2017 |
| rookie_year | double | Yes | Rookie season year | 2017.0 |
| draft_club | string | Yes | Team that drafted the player | "KC" |
| draft_number | double | Yes | Overall draft pick number | 10.0 |
| age | double | Yes | Player age at time of season | 26.0 |
| data_source | string | Yes | Ingestion source tag | "nfl-data-py" |
| ingestion_timestamp | timestamp[ns] | Yes | When data was ingested | 2026-03-06 22:37:34 |

---

## Bronze Layer -- From Config/Tests

These data types require API ingestion to get full Parquet schemas. Representative columns are documented from test mocks (`tests/test_advanced_ingestion.py`, `tests/test_pbp_ingestion.py`), config constants (`PBP_COLUMNS` in `src/config.py`), and `validate_data()` required columns in `src/nfl_data_integration.py`.

> **Note:** Full schemas are available after running `python scripts/bronze_ingestion_simple.py --data-type [type] --season YYYY`

---

### Play-by-Play (PBP)

**Source:** `nfl-data-py` function `import_pbp_data()` via `NFLDataAdapter.fetch_pbp()`
**Seasons:** 1999-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pbp/season=YYYY/`
**Local Path:** `data/bronze/pbp/season=YYYY/`
**Known Quirks:** Full PBP data has 300+ columns; we curate to 103 via `PBP_COLUMNS` in `src/config.py`. Always use `include_participation=False` (default) to avoid column merge issues. Processed one season at a time for memory safety. `downcast=True` reduces numeric precision for ~40% memory savings.

The following 103 columns are curated via `PBP_COLUMNS` in `src/config.py`:

| Column | Category | Description | Example |
|--------|----------|-------------|---------|
| game_id | Game/play ID | Unique game identifier | "2023_01_KC_DET" |
| play_id | Game/play ID | Unique play identifier within game | 43 |
| season | Game/play ID | NFL season year | 2023 |
| week | Game/play ID | NFL week number | 1 |
| season_type | Game/play ID | Season type (REG, POST) | "REG" |
| game_date | Game/play ID | Date of game | "2023-09-07" |
| posteam | Game/play ID | Possession team abbreviation | "DET" |
| defteam | Game/play ID | Defending team abbreviation | "KC" |
| home_team | Game/play ID | Home team abbreviation | "KC" |
| away_team | Game/play ID | Away team abbreviation | "DET" |
| home_score | Score context | Home team score at time of play | 0 |
| away_score | Score context | Away team score at time of play | 0 |
| posteam_score | Score context | Possession team score | 0 |
| defteam_score | Score context | Defending team score | 0 |
| posteam_score_post | Score context | Possession team score after play | 0 |
| defteam_score_post | Score context | Defending team score after play | 0 |
| score_differential | Score context | Score difference (posteam - defteam) | 0 |
| score_differential_post | Score context | Score difference after play | 0 |
| down | Play situation | Down number (1-4) | 1 |
| ydstogo | Play situation | Yards to go for first down | 10 |
| yardline_100 | Play situation | Yards from opponent end zone (0-100) | 75 |
| goal_to_go | Play situation | Goal-to-go situation flag | 0 |
| qtr | Play situation | Quarter (1-5, 5=OT) | 1 |
| quarter_seconds_remaining | Play situation | Seconds remaining in quarter | 894 |
| half_seconds_remaining | Play situation | Seconds remaining in half | 1794 |
| game_seconds_remaining | Play situation | Seconds remaining in game | 3594 |
| drive | Play situation | Drive number within game | 1 |
| posteam_timeouts_remaining | Play situation | Possession team timeouts left | 3 |
| defteam_timeouts_remaining | Play situation | Defending team timeouts left | 3 |
| play_type | Play type/result | Type of play (pass, run, punt, etc.) | "pass" |
| yards_gained | Play type/result | Net yards gained on play | 7 |
| shotgun | Play type/result | Shotgun formation flag | 1 |
| no_huddle | Play type/result | No huddle flag | 0 |
| qb_dropback | Play type/result | QB dropback flag | 1 |
| qb_scramble | Play type/result | QB scramble flag | 0 |
| qb_kneel | Play type/result | QB kneel flag | 0 |
| qb_spike | Play type/result | QB spike flag | 0 |
| pass_attempt | Play type/result | Pass attempt flag | 1 |
| rush_attempt | Play type/result | Rush attempt flag | 0 |
| pass_length | Play type/result | Pass length category (short, deep) | "short" |
| pass_location | Play type/result | Pass location (left, middle, right) | "middle" |
| run_location | Play type/result | Run location (left, middle, right) | null |
| run_gap | Play type/result | Run gap (end, tackle, guard) | null |
| complete_pass | Play type/result | Complete pass flag | 1 |
| incomplete_pass | Play type/result | Incomplete pass flag | 0 |
| interception | Play type/result | Interception flag | 0 |
| sack | Play type/result | Sack flag | 0 |
| fumble | Play type/result | Fumble flag | 0 |
| fumble_lost | Play type/result | Fumble lost flag | 0 |
| penalty | Play type/result | Penalty flag | 0 |
| first_down | Play type/result | First down achieved flag | 0 |
| third_down_converted | Play type/result | Third down converted flag | 0 |
| third_down_failed | Play type/result | Third down failed flag | 0 |
| fourth_down_converted | Play type/result | Fourth down converted flag | 0 |
| fourth_down_failed | Play type/result | Fourth down failed flag | 0 |
| touchdown | Play type/result | Touchdown scored flag | 0 |
| pass_touchdown | Play type/result | Passing touchdown flag | 0 |
| rush_touchdown | Play type/result | Rushing touchdown flag | 0 |
| safety | Play type/result | Safety flag | 0 |
| epa | EPA metrics | Expected Points Added for play | 0.52 |
| ep | EPA metrics | Expected Points before play | 1.23 |
| air_epa | EPA metrics | EPA from air yards component | 0.31 |
| yac_epa | EPA metrics | EPA from yards after catch component | 0.21 |
| comp_air_epa | EPA metrics | Completed pass air EPA | 0.31 |
| comp_yac_epa | EPA metrics | Completed pass YAC EPA | 0.21 |
| qb_epa | EPA metrics | EPA attributed to quarterback | 0.52 |
| wpa | WPA metrics | Win Probability Added | 0.012 |
| vegas_wpa | WPA metrics | Vegas-adjusted WPA | 0.010 |
| air_wpa | WPA metrics | WPA from air yards | 0.008 |
| yac_wpa | WPA metrics | WPA from YAC | 0.004 |
| comp_air_wpa | WPA metrics | Completed pass air WPA | 0.008 |
| comp_yac_wpa | WPA metrics | Completed pass YAC WPA | 0.004 |
| wp | WPA metrics | Win probability before play | 0.52 |
| def_wp | WPA metrics | Defensive win probability | 0.48 |
| home_wp | WPA metrics | Home team win probability | 0.52 |
| away_wp | WPA metrics | Away team win probability | 0.48 |
| home_wp_post | WPA metrics | Home win probability after play | 0.53 |
| away_wp_post | WPA metrics | Away win probability after play | 0.47 |
| cpoe | Completion metrics | Completion Percentage Over Expected | 5.2 |
| cp | Completion metrics | Completion probability | 0.72 |
| xpass | Completion metrics | Expected pass rate | 0.55 |
| pass_oe | Completion metrics | Pass rate over expected | 0.05 |
| air_yards | Yardage | Air yards on pass attempt | 9 |
| yards_after_catch | Yardage | Yards after catch | -2 |
| passing_yards | Yardage | Passing yards on play | 7 |
| receiving_yards | Yardage | Receiving yards on play | 7 |
| rushing_yards | Yardage | Rushing yards on play | 0 |
| success | Success | Successful play flag (EPA > 0) | 1 |
| passer_player_id | Player IDs | Passer GSIS ID | "00-0033873" |
| passer_player_name | Player IDs | Passer name | "P.Mahomes" |
| receiver_player_id | Player IDs | Receiver GSIS ID | "00-0035228" |
| receiver_player_name | Player IDs | Receiver name | "T.Kelce" |
| rusher_player_id | Player IDs | Rusher GSIS ID | null |
| rusher_player_name | Player IDs | Rusher name | null |
| spread_line | Vegas lines | Point spread for game | -3.5 |
| total_line | Vegas lines | Over/under line | 51.5 |
| series | Series | Series number within game | 1 |
| series_success | Series | Series resulted in first down or TD | 1 |
| series_result | Series | Series outcome | "First down" |
| temp | Weather/venue | Temperature (Fahrenheit) | 72 |
| wind | Weather/venue | Wind speed (mph) | 8 |
| roof | Weather/venue | Roof type | "outdoors" |
| surface | Weather/venue | Playing surface | "grass" |

---

### NGS Passing

**Source:** `nfl-data-py` function `import_ngs_data(stat_type='passing')` via `NFLDataAdapter.fetch_ngs(stat_type='passing')`
**Seasons:** 2016-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/ngs/passing/season=YYYY/`
**Local Path:** `data/bronze/ngs/passing/season=YYYY/`
**Known Quirks:** NGS data is only available from 2016 onward (when tracking chips were introduced). All three NGS stat types share common identification columns but have stat-type-specific metrics. Full schema includes ~20 additional passing-specific columns available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | NFL season year | 2024 |
| season_type | string | Yes | Season type (REG, POST) | "REG" |
| week | int64 | Yes | NFL week number | 1 |
| player_display_name | string | Yes | Player full display name | "Patrick Mahomes" |
| player_position | string | Yes | Player position | "QB" |
| team_abbr | string | Yes | Team abbreviation | "KC" |
| player_gsis_id | string | Yes | GSIS player identifier | "00-0033873" |

Additional columns available after ingestion (passing-specific):

| Column | Description |
|--------|-------------|
| avg_time_to_throw | Average time from snap to throw (seconds) |
| avg_completed_air_yards | Average air yards on completions |
| avg_intended_air_yards | Average air yards on all attempts |
| avg_air_yards_differential | Difference between intended and completed air yards |
| aggressiveness | Percentage of tight-window throws |
| max_completed_air_distance | Longest completed pass (air distance) |
| avg_air_yards_to_sticks | Average air yards relative to first-down marker |
| attempts | Total pass attempts |
| pass_yards | Total passing yards |
| pass_touchdowns | Total passing touchdowns |
| interceptions | Total interceptions thrown |
| passer_rating | NFL passer rating |
| completions | Total completions |
| completion_percentage | Completion rate |
| expected_completion_percentage | xComp from NGS model |
| completion_percentage_above_expectation | CPOE metric |
| avg_air_distance | Average distance ball travels in air |
| max_air_distance | Maximum air distance on any attempt |

---

### NGS Rushing

**Source:** `nfl-data-py` function `import_ngs_data(stat_type='rushing')` via `NFLDataAdapter.fetch_ngs(stat_type='rushing')`
**Seasons:** 2016-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/ngs/rushing/season=YYYY/`
**Local Path:** `data/bronze/ngs/rushing/season=YYYY/`
**Known Quirks:** Full schema includes rushing-specific metrics available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | NFL season year | 2024 |
| season_type | string | Yes | Season type (REG, POST) | "REG" |
| week | int64 | Yes | NFL week number | 1 |
| player_display_name | string | Yes | Player full display name | "Derrick Henry" |
| player_position | string | Yes | Player position | "RB" |
| team_abbr | string | Yes | Team abbreviation | "BAL" |
| player_gsis_id | string | Yes | GSIS player identifier | "00-0033923" |

Additional columns available after ingestion (rushing-specific):

| Column | Description |
|--------|-------------|
| rush_attempts | Total rushing attempts |
| rush_yards | Total rushing yards |
| avg_rush_yards | Average rushing yards per attempt |
| rush_touchdowns | Total rushing touchdowns |
| efficiency | Rushing efficiency metric |
| percent_attempts_gte_eight_defenders | Percentage of rushes vs 8+ defenders in box |
| avg_time_to_los | Average time to reach line of scrimmage |
| rush_yards_over_expected | Yards gained vs expected (RYOE) |
| avg_rush_yards_over_expected | Average RYOE per carry |
| rush_pct_over_expected | Rush yards over expected as percentage |
| expected_rush_yards | Expected yards based on situation |

---

### NGS Receiving

**Source:** `nfl-data-py` function `import_ngs_data(stat_type='receiving')` via `NFLDataAdapter.fetch_ngs(stat_type='receiving')`
**Seasons:** 2016-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/ngs/receiving/season=YYYY/`
**Local Path:** `data/bronze/ngs/receiving/season=YYYY/`
**Known Quirks:** Full schema includes receiving-specific metrics available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | NFL season year | 2024 |
| season_type | string | Yes | Season type (REG, POST) | "REG" |
| week | int64 | Yes | NFL week number | 1 |
| player_display_name | string | Yes | Player full display name | "Tyreek Hill" |
| player_position | string | Yes | Player position | "WR" |
| team_abbr | string | Yes | Team abbreviation | "MIA" |
| player_gsis_id | string | Yes | GSIS player identifier | "00-0033040" |

Additional columns available after ingestion (receiving-specific):

| Column | Description |
|--------|-------------|
| avg_cushion | Average cushion (yards between receiver and nearest defender at snap) |
| avg_separation | Average separation from nearest defender at catch point |
| avg_intended_air_yards | Average intended air yards on targets |
| catch_percentage | Percentage of targets caught |
| avg_yac | Average yards after catch |
| avg_expected_yac | Expected yards after catch from NGS model |
| avg_yac_above_expectation | YAC over expected |
| targets | Total targets |
| receptions | Total receptions |
| yards | Total receiving yards |
| rec_touchdowns | Total receiving touchdowns |
| avg_air_yards_differential | Difference between intended and actual air yards |
| percent_share_of_intended_air_yards | Share of team intended air yards |

---

### PFR Weekly Passing

**Source:** `nfl-data-py` function `import_weekly_pfr(s_type='pass')` via `NFLDataAdapter.fetch_pfr_weekly(s_type='pass')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/weekly/pass/season=YYYY/`
**Local Path:** `data/bronze/pfr/weekly/pass/season=YYYY/`
**Known Quirks:** PFR weekly data uses `pfr_player_name` and `pfr_player_id` (not GSIS IDs). Requires cross-referencing with rosters via PFR ID for player matching. Full schema includes passing-specific columns (e.g., `passing_bad_throws`, `times_sacked`, `times_blitzed`, `times_hurried`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| game_id | string | Yes | Unique game identifier | "2024_01_KC_BAL" |
| season | int64 | Yes | NFL season year | 2024 |
| week | int64 | Yes | NFL week number | 1 |
| team | string | Yes | Team abbreviation | "KC" |
| pfr_player_name | string | Yes | PFR player name | "Patrick Mahomes" |
| pfr_player_id | string | Yes | PFR player identifier | "MahoPa00" |

---

### PFR Weekly Rushing

**Source:** `nfl-data-py` function `import_weekly_pfr(s_type='rush')` via `NFLDataAdapter.fetch_pfr_weekly(s_type='rush')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/weekly/rush/season=YYYY/`
**Local Path:** `data/bronze/pfr/weekly/rush/season=YYYY/`
**Known Quirks:** Same identification columns as PFR passing. Full schema includes rushing-specific columns (e.g., `carries`, `rushing_yards`, `rushing_tds`, `broken_tackles`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| game_id | string | Yes | Unique game identifier | "2024_01_KC_BAL" |
| season | int64 | Yes | NFL season year | 2024 |
| week | int64 | Yes | NFL week number | 1 |
| team | string | Yes | Team abbreviation | "KC" |
| pfr_player_name | string | Yes | PFR player name | "Isiah Pacheco" |
| pfr_player_id | string | Yes | PFR player identifier | "PachIs00" |

---

### PFR Weekly Receiving

**Source:** `nfl-data-py` function `import_weekly_pfr(s_type='rec')` via `NFLDataAdapter.fetch_pfr_weekly(s_type='rec')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/weekly/rec/season=YYYY/`
**Local Path:** `data/bronze/pfr/weekly/rec/season=YYYY/`
**Known Quirks:** Same identification columns as PFR passing. Full schema includes receiving-specific columns (e.g., `targets`, `receptions`, `receiving_yards`, `yards_before_contact`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| game_id | string | Yes | Unique game identifier | "2024_01_KC_BAL" |
| season | int64 | Yes | NFL season year | 2024 |
| week | int64 | Yes | NFL week number | 1 |
| team | string | Yes | Team abbreviation | "KC" |
| pfr_player_name | string | Yes | PFR player name | "Travis Kelce" |
| pfr_player_id | string | Yes | PFR player identifier | "KelcTr00" |

---

### PFR Weekly Defense

**Source:** `nfl-data-py` function `import_weekly_pfr(s_type='def')` via `NFLDataAdapter.fetch_pfr_weekly(s_type='def')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/weekly/def/season=YYYY/`
**Local Path:** `data/bronze/pfr/weekly/def/season=YYYY/`
**Known Quirks:** Same identification columns as PFR passing. Full schema includes defensive columns (e.g., `tackles_solo`, `tackles_assists`, `sacks`, `interceptions`, `passes_defended`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| game_id | string | Yes | Unique game identifier | "2024_01_KC_BAL" |
| season | int64 | Yes | NFL season year | 2024 |
| week | int64 | Yes | NFL week number | 1 |
| team | string | Yes | Team abbreviation | "KC" |
| pfr_player_name | string | Yes | PFR player name | "Chris Jones" |
| pfr_player_id | string | Yes | PFR player identifier | "JoneCh05" |

---

### PFR Seasonal Passing

**Source:** `nfl-data-py` function `import_seasonal_pfr(s_type='pass')` via `NFLDataAdapter.fetch_pfr_seasonal(s_type='pass')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/seasonal/pass/season=YYYY/`
**Local Path:** `data/bronze/pfr/seasonal/pass/season=YYYY/`
**Known Quirks:** PFR seasonal uses `player` and `pfr_id` as identifiers (different from weekly which uses `pfr_player_name` and `pfr_player_id`). Full schema includes season-aggregated passing metrics available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| player | string | Yes | Player name | "Patrick Mahomes" |
| team | string | Yes | Team abbreviation | "KC" |
| season | int64 | Yes | NFL season year | 2024 |
| pfr_id | string | Yes | PFR player identifier | "MahoPa00" |

---

### PFR Seasonal Rushing

**Source:** `nfl-data-py` function `import_seasonal_pfr(s_type='rush')` via `NFLDataAdapter.fetch_pfr_seasonal(s_type='rush')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/seasonal/rush/season=YYYY/`
**Local Path:** `data/bronze/pfr/seasonal/rush/season=YYYY/`
**Known Quirks:** Same identification columns as PFR seasonal passing. Full schema includes season-aggregated rushing metrics available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| player | string | Yes | Player name | "Derrick Henry" |
| team | string | Yes | Team abbreviation | "BAL" |
| season | int64 | Yes | NFL season year | 2024 |
| pfr_id | string | Yes | PFR player identifier | "HenrDe00" |

---

### PFR Seasonal Receiving

**Source:** `nfl-data-py` function `import_seasonal_pfr(s_type='rec')` via `NFLDataAdapter.fetch_pfr_seasonal(s_type='rec')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/seasonal/rec/season=YYYY/`
**Local Path:** `data/bronze/pfr/seasonal/rec/season=YYYY/`
**Known Quirks:** Same identification columns as PFR seasonal passing. Full schema includes season-aggregated receiving metrics available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| player | string | Yes | Player name | "Tyreek Hill" |
| team | string | Yes | Team abbreviation | "MIA" |
| season | int64 | Yes | NFL season year | 2024 |
| pfr_id | string | Yes | PFR player identifier | "HillTy00" |

---

### PFR Seasonal Defense

**Source:** `nfl-data-py` function `import_seasonal_pfr(s_type='def')` via `NFLDataAdapter.fetch_pfr_seasonal(s_type='def')`
**Seasons:** 2018-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/pfr/seasonal/def/season=YYYY/`
**Local Path:** `data/bronze/pfr/seasonal/def/season=YYYY/`
**Known Quirks:** Same identification columns as PFR seasonal passing. Full schema includes season-aggregated defensive metrics available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| player | string | Yes | Player name | "Chris Jones" |
| team | string | Yes | Team abbreviation | "KC" |
| season | int64 | Yes | NFL season year | 2024 |
| pfr_id | string | Yes | PFR player identifier | "JoneCh05" |

---

### QBR Weekly

**Source:** `nfl-data-py` function `import_qbr(frequency='weekly')` via `NFLDataAdapter.fetch_qbr(frequency='weekly')`
**Seasons:** 2006-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/qbr/season=YYYY/`
**Local Path:** `data/bronze/qbr/season=YYYY/`
**Known Quirks:** QBR filenames use frequency prefix (`qbr_weekly_*.parquet` vs `qbr_seasonal_*.parquet`) to prevent weekly/seasonal file collisions in the same directory. The `frequency` parameter must be passed to the adapter. Full schema includes additional QB metrics (e.g., `qbr_raw`, `sack_adj_epa`, `pass_epa`, `rush_epa`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | NFL season year | 2024 |
| season_type | string | Yes | Season type | "Regular" |
| qbr_total | double | Yes | Total QBR (0-100 scale) | 72.5 |
| pts_added | double | Yes | Points added by QB play | 45.3 |
| epa_total | double | Yes | Total EPA for QB | 120.1 |
| qb_plays | int64 | Yes | Total QB plays | 580 |

---

### QBR Seasonal

**Source:** `nfl-data-py` function `import_qbr(frequency='season')` via `NFLDataAdapter.fetch_qbr(frequency='season')`
**Seasons:** 2006-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/qbr/season=YYYY/`
**Local Path:** `data/bronze/qbr/season=YYYY/`
**Known Quirks:** Same S3/local path as QBR weekly but with `qbr_seasonal_` filename prefix. Same column structure as weekly but values are season-aggregated.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | NFL season year | 2024 |
| season_type | string | Yes | Season type | "Regular" |
| qbr_total | double | Yes | Season total QBR (0-100 scale) | 72.5 |
| pts_added | double | Yes | Season total points added | 45.3 |
| epa_total | double | Yes | Season total EPA | 120.1 |
| qb_plays | int64 | Yes | Season total QB plays | 580 |

---

### Depth Charts

**Source:** `nfl-data-py` function `import_depth_charts()` via `NFLDataAdapter.fetch_depth_charts()`
**Seasons:** 2001-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/depth_charts/season=YYYY/`
**Local Path:** `data/bronze/depth_charts/season=YYYY/`
**Known Quirks:** Depth charts are published weekly and can change throughout the season. Contains `club_code` (not `team` or `team_abbr`). Full schema includes additional columns (e.g., `depth_team`, `last_name`, `first_name`, `formation`, `jersey_number`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | NFL season year | 2024 |
| club_code | string | Yes | Team abbreviation | "KC" |
| week | int64 | Yes | NFL week number | 1 |
| position | string | Yes | Position on depth chart | "QB" |
| full_name | string | Yes | Player full name | "Patrick Mahomes" |
| gsis_id | string | Yes | GSIS player identifier | "00-0033873" |

---

### Draft Picks

**Source:** `nfl-data-py` function `import_draft_picks()` via `NFLDataAdapter.fetch_draft_picks()`
**Seasons:** 2000-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/draft_picks/season=YYYY/`
**Local Path:** `data/bronze/draft_picks/season=YYYY/`
**Known Quirks:** Uses `pfr_player_name` for player identification (same as PFR weekly). Full schema includes additional columns (e.g., `pfr_player_id`, `college`, `age`, `to`, `ap1`, `pb`, `st`, `wAV`, `drAV`, `g`, `cmp`, `pass_att`, `pass_yds`, `pass_td`, `pass_int`, `rush_att`, `rush_yds`, `rush_td`, `rec`, `rec_yds`, `rec_td`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | Draft year | 2024 |
| round | int64 | Yes | Draft round (1-7) | 1 |
| pick | int64 | Yes | Overall pick number | 10 |
| team | string | Yes | Team that made the pick | "KC" |
| pfr_player_name | string | Yes | Player name (PFR format) | "Xavier Worthy" |
| position | string | Yes | Player position | "WR" |

---

### Combine

**Source:** `nfl-data-py` function `import_combine_data()` via `NFLDataAdapter.fetch_combine()`
**Seasons:** 2000-2027 (from DATA_TYPE_SEASON_RANGES)
**S3 Path:** `s3://nfl-raw/combine/season=YYYY/`
**Local Path:** `data/bronze/combine/season=YYYY/`
**Known Quirks:** Height is stored as string in `X-YY` format (feet-inches). Weight is integer (pounds). Full schema includes additional drill columns (e.g., `forty`, `bench`, `vertical`, `broad_jump`, `cone`, `shuttle`, `pfr_id`, `draft_team`, `draft_round`, `draft_pick`, `draft_ovr`) available after ingestion.

Representative columns (from test mocks and validate_data):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| season | int64 | Yes | Combine year | 2024 |
| player_name | string | Yes | Player name | "Xavier Worthy" |
| pos | string | Yes | Player position | "WR" |
| school | string | Yes | College/university | "Texas" |
| ht | string | Yes | Height (feet-inches format) | "5-11" |
| wt | int64 | Yes | Weight in pounds | 165 |

---

### Teams

**Source:** `nfl-data-py` function `import_team_desc()` via `NFLDataAdapter.fetch_team_descriptions()`
**Seasons:** 1999-2027 (from DATA_TYPE_SEASON_RANGES; static reference data)
**S3 Path:** `s3://nfl-raw/teams/`
**Local Path:** `data/bronze/teams/`
**Known Quirks:** This is a static reference table (no season/week partitioning). The adapter method takes no arguments (`fetch_team_descriptions()`). Returns all 32 current NFL teams. Full schema includes columns like `team_abbr`, `team_name`, `team_id`, `team_nick`, `team_conf`, `team_division`, `team_color`, `team_color2`, `team_color3`, `team_color4`, `team_logo_wikipedia`, `team_logo_espn`, `team_wordmark`, `team_conference_logo`, `team_league_logo`, `team_logo_squared`, `team_logo_espn_dark`.

Representative columns (from validate_data required columns):

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
| team_abbr | string | Yes | Team abbreviation (2-3 chars) | "KC" |
| team_name | string | Yes | Full team name | "Kansas City Chiefs" |

---

## Silver Layer Tables

### 1. Games (Silver)

**Table Name:** `games_silver`
**S3 Location:** `s3://nfl-refined/games/season=YYYY/week=WW/`
**Partitioning:** `season`, `week`
**Source System:** Bronze games table + enrichments
**Update Frequency:** Daily during season

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| game_id | STRING | NO | Primary key from bronze | "2023_01_KC_DET" |
| season | INT | NO | Validated season year | 2023 |
| week | INT | NO | Validated week number | 1 |
| game_date | DATE | NO | Standardized game date | "2023-09-07" |
| game_time_et | TIME | YES | Eastern Time kickoff | "20:20:00" |
| home_team_id | STRING | NO | Standardized home team ID | "KC" |
| away_team_id | STRING | NO | Standardized away team ID | "DET" |
| home_score | INT | NO | Validated home score | 21 |
| away_score | INT | NO | Validated away score | 20 |
| game_result | INT | NO | Home team margin | 1 |
| total_points | INT | NO | Total points scored | 41 |
| overtime_flag | BOOLEAN | NO | Overtime occurred | FALSE |
| neutral_site_flag | BOOLEAN | NO | Neutral site game | FALSE |
| dome_game_flag | BOOLEAN | NO | Indoor/dome game | FALSE |
| division_game_flag | BOOLEAN | NO | Division matchup | FALSE |
| playoff_flag | BOOLEAN | NO | Playoff game | FALSE |
| prime_time_flag | BOOLEAN | NO | Prime time game | TRUE |
| game_type | STRING | NO | Game type category | "REG" |
| season_type | STRING | NO | Season phase | "Regular" |
| week_category | STRING | NO | Season timing | "Early" |
| home_rest_days | INT | NO | Home team rest | 7 |
| away_rest_days | INT | NO | Away team rest | 7 |
| rest_differential | INT | NO | Rest advantage | 0 |
| spread | DECIMAL(4,1) | YES | Closing point spread | -3.5 |
| total_line | DECIMAL(4,1) | YES | Closing total | 47.5 |
| home_favorite_flag | BOOLEAN | YES | Home team favored | TRUE |
| spread_cover_result | STRING | YES | Spread outcome | "Away_Cover" |
| total_result | STRING | YES | Total outcome | "Under" |
| temperature | INT | YES | Game temperature | 72 |
| wind_speed | INT | YES | Wind speed | 8 |
| precipitation_flag | BOOLEAN | YES | Precipitation present | FALSE |
| weather_category | STRING | YES | Weather classification | "Good" |
| data_quality_score | DECIMAL(3,2) | NO | Quality assessment | 0.95 |
| validation_status | STRING | NO | Validation result | "PASSED" |
| load_timestamp | TIMESTAMP | NO | Silver ETL timestamp | "2023-09-08 14:00:00" |

### 2. Teams (Silver)

**Table Name:** `teams_silver`
**S3 Location:** `s3://nfl-refined/teams/`
**Source System:** Bronze teams + external references

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| team_id | STRING | NO | Primary standardized team ID | "KC" |
| team_abbr | STRING | NO | Official abbreviation | "KC" |
| team_name | STRING | NO | Standardized team name | "Kansas City Chiefs" |
| team_city | STRING | NO | Team city | "Kansas City" |
| division_id | STRING | NO | Division identifier | "AFC_WEST" |
| conference | STRING | NO | Conference | "AFC" |
| stadium_name | STRING | YES | Current stadium name | "GEHA Field at Arrowhead Stadium" |
| stadium_surface | STRING | YES | Playing surface | "Grass" |
| stadium_roof_type | STRING | YES | Roof configuration | "Open" |
| load_timestamp | TIMESTAMP | NO | Silver ETL timestamp | "2023-08-15 12:00:00" |

### 3. Player Usage Metrics (Silver)

**S3 Location:** `s3://nfl-refined/players/usage/season=YYYY/week=WW/`
**Source:** Bronze player_weekly + snap_counts
**Produced by:** `scripts/silver_player_transformation.py`

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| player_id | STRING | NO | GSIS player identifier | "00-0033873" |
| player_name | STRING | NO | Player display name | "Patrick Mahomes" |
| position | STRING | NO | Player position | "QB" |
| team | STRING | NO | Team abbreviation | "KC" |
| season | INT | NO | NFL season year | 2024 |
| week | INT | NO | NFL week number | 1 |
| target_share | FLOAT | YES | Percentage of team targets | 0.0 |
| air_yards_share | FLOAT | YES | Percentage of team air yards | 0.0 |
| rush_share | FLOAT | YES | Percentage of team carries | 0.0 |
| snap_pct | FLOAT | YES | Percentage of offensive snaps played | 100.0 |
| usage_score | FLOAT | YES | Composite usage metric (weighted combination) | 0.85 |
| opportunity_score | FLOAT | YES | Target + carry opportunity metric | 25.0 |

### 4. Opponent Rankings (Silver)

**S3 Location:** `s3://nfl-refined/defense/positional/season=YYYY/week=WW/`
**Source:** Bronze player_weekly aggregated by opponent defense
**Produced by:** `scripts/silver_player_transformation.py`

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| team | STRING | NO | Defensive team abbreviation | "KC" |
| position | STRING | NO | Offensive position ranked against | "QB" |
| season | INT | NO | NFL season year | 2024 |
| week | INT | NO | Through-week for ranking calculation | 10 |
| opp_rank | INT | NO | Positional ranking (1=toughest, 32=easiest) | 5 |
| points_allowed_avg | FLOAT | YES | Average fantasy points allowed to position | 15.2 |
| games_counted | INT | YES | Number of games in ranking calculation | 10 |

### 5. Rolling Averages (Silver)

**S3 Location:** `s3://nfl-refined/players/rolling/season=YYYY/week=WW/`
**Source:** Bronze player_weekly with 3-week and 6-week rolling windows
**Produced by:** `scripts/silver_player_transformation.py`

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| player_id | STRING | NO | GSIS player identifier | "00-0033873" |
| season | INT | NO | NFL season year | 2024 |
| week | INT | NO | NFL week number | 10 |
| roll3_passing_yards | FLOAT | YES | 3-week rolling avg passing yards | 285.3 |
| roll3_rushing_yards | FLOAT | YES | 3-week rolling avg rushing yards | 22.7 |
| roll3_receiving_yards | FLOAT | YES | 3-week rolling avg receiving yards | 0.0 |
| roll3_passing_tds | FLOAT | YES | 3-week rolling avg passing TDs | 2.33 |
| roll3_rushing_tds | FLOAT | YES | 3-week rolling avg rushing TDs | 0.33 |
| roll3_receiving_tds | FLOAT | YES | 3-week rolling avg receiving TDs | 0.0 |
| roll3_fantasy_points | FLOAT | YES | 3-week rolling avg fantasy points | 22.5 |
| roll6_passing_yards | FLOAT | YES | 6-week rolling avg passing yards | 275.8 |
| roll6_rushing_yards | FLOAT | YES | 6-week rolling avg rushing yards | 20.1 |
| roll6_receiving_yards | FLOAT | YES | 6-week rolling avg receiving yards | 0.0 |
| roll6_passing_tds | FLOAT | YES | 6-week rolling avg passing TDs | 2.17 |
| roll6_rushing_tds | FLOAT | YES | 6-week rolling avg rushing TDs | 0.17 |
| roll6_receiving_tds | FLOAT | YES | 6-week rolling avg receiving TDs | 0.0 |
| roll6_fantasy_points | FLOAT | YES | 6-week rolling avg fantasy points | 21.8 |
| std_passing_yards | FLOAT | YES | Std deviation of passing yards | 45.2 |
| std_rushing_yards | FLOAT | YES | Std deviation of rushing yards | 12.3 |
| std_receiving_yards | FLOAT | YES | Std deviation of receiving yards | 0.0 |
| std_fantasy_points | FLOAT | YES | Std deviation of fantasy points | 5.8 |

---

## Gold Layer Tables

### 1. Weekly Projections (Gold)

**S3 Location:** `s3://nfl-trusted/projections/season=YYYY/week=WW/`
**Source:** Silver usage + rolling averages + opponent rankings + injuries
**Produced by:** `scripts/generate_projections.py --week W --season YYYY --scoring [ppr|half_ppr|standard]`

**Projection Model:** `roll3(50%) + roll6(30%) + STD(20%) x usage_mult [0.7-1.3] x matchup [0.85-1.15] x vegas [0.80-1.20]`

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| player_id | STRING | NO | GSIS player identifier | "00-0033873" |
| player_name | STRING | NO | Player display name | "Patrick Mahomes" |
| position | STRING | NO | Player position (QB/RB/WR/TE) | "QB" |
| team | STRING | NO | Team abbreviation | "KC" |
| season | INT | NO | NFL season year | 2024 |
| week | INT | NO | NFL week number | 10 |
| projected_points | FLOAT | NO | Projected fantasy points (always >= 0) | 22.5 |
| floor | FLOAT | YES | Low-end projection estimate | 15.2 |
| ceiling | FLOAT | YES | High-end projection estimate | 32.1 |
| is_bye_week | BOOLEAN | NO | True if player is on bye | FALSE |
| injury_status | STRING | YES | Injury designation (Active/Questionable/Doubtful/Out) | "Active" |
| injury_multiplier | FLOAT | YES | Projection adjustment for injury (0.0-1.0) | 1.0 |
| usage_multiplier | FLOAT | YES | Usage-based projection adjustment (0.7-1.3) | 1.05 |
| matchup_multiplier | FLOAT | YES | Opponent-based adjustment (0.85-1.15) | 0.95 |
| vegas_multiplier | FLOAT | YES | Vegas implied total adjustment (0.80-1.20) | 1.02 |
| scoring_format | STRING | NO | Scoring format used | "half_ppr" |
| opponent | STRING | YES | Opponent team abbreviation | "BUF" |
| opp_rank | INT | YES | Opponent positional rank (1-32) | 8 |

### 2. Preseason Projections (Gold)

**S3 Location:** `s3://nfl-trusted/projections/preseason/season=YYYY/`
**Source:** Silver historical data + rookie baselines
**Produced by:** `scripts/generate_projections.py --preseason --season YYYY --scoring [ppr|half_ppr|standard]`

| Column Name | Data Type | Nullable | Description | Example |
|-------------|-----------|----------|-------------|---------|
| player_id | STRING | NO | GSIS player identifier | "00-0033873" |
| player_name | STRING | NO | Player display name | "Patrick Mahomes" |
| position | STRING | NO | Player position (QB/RB/WR/TE) | "QB" |
| team | STRING | NO | Team abbreviation | "KC" |
| season | INT | NO | NFL season year | 2026 |
| projected_points_total | FLOAT | NO | Full-season projected points | 380.5 |
| games_projected | INT | NO | Expected games to play | 17 |
| per_game_projection | FLOAT | NO | Per-game projected points | 22.4 |
| is_rookie | BOOLEAN | NO | Rookie flag | FALSE |
| scoring_format | STRING | NO | Scoring format used | "half_ppr" |
| tier | STRING | YES | Draft tier classification | "Elite" |

---

## Data Types and Constraints

### Standard Data Types

| Data Type | Description | Example |
|-----------|-------------|---------|
| string | Variable length text (UTF-8) | "Kansas City Chiefs" |
| int32 | 32-bit integer | 2023 |
| int64 | 64-bit integer | 1234567890 |
| float | 32-bit floating point | 12.5 |
| double | 64-bit floating point | 123.456789 |
| timestamp[ns] | Nanosecond timestamp | 2023-09-07 20:20:00 |
| timestamp[ns, tz=UTC] | Timezone-aware timestamp | 2023-09-08T18:00:00Z |
| null | Null-only column (no data) | null |

### Key Constraints

- **Season Range:** 1999-2027 (varies by data type; see DATA_TYPE_SEASON_RANGES in `src/config.py`)
- **Week Range:** 1-18 regular season, 19-22 playoffs
- **Team Count:** 32 NFL teams
- **Down Range:** 1-4
- **Distance Range:** 1-99 yards
- **Yard Line Range:** 0-100

---

## Business Rules

### Bronze Layer Validation

Validation is performed by `NFLDataFetcher.validate_data()` in `src/nfl_data_integration.py`. Each data type has required columns that are checked on ingestion:

| Data Type | Required Columns |
|-----------|-----------------|
| schedules | game_id, season, week, home_team, away_team |
| pbp | game_id, play_id, season, week |
| teams | team_abbr, team_name |
| player_weekly | player_id, season, week |
| snap_counts | player_id, season, week |
| injuries | season, week |
| rosters | player_id, season |
| player_seasonal | player_id, season |
| ngs | season, season_type, week, player_display_name, player_position, team_abbr, player_gsis_id |
| pfr_weekly | game_id, season, week, team, pfr_player_name, pfr_player_id |
| pfr_seasonal | player, team, season, pfr_id |
| qbr | season, season_type, qbr_total, pts_added, epa_total, qb_plays |
| depth_charts | season, club_code, week, position, full_name, gsis_id |
| draft_picks | season, round, pick, team, pfr_player_name, position |
| combine | season, player_name, pos, school, ht, wt |

### Fantasy Scoring Rules

| Metric | PPR | Half-PPR | Standard |
|--------|-----|----------|----------|
| Reception | 1.0 | 0.5 | 0.0 |
| Rush/Rec Yard | 0.1 | 0.1 | 0.1 |
| Rush/Rec TD | 6.0 | 6.0 | 6.0 |
| Pass Yard | 0.04 | 0.04 | 0.04 |
| Pass TD | 4.0 | 4.0 | 4.0 |
| Interception | -2.0 | -2.0 | -2.0 |
| Fumble Lost | -2.0 | -2.0 | -2.0 |
| 2pt Conversion | 2.0 | 2.0 | 2.0 |

### Injury Status Multipliers

| Status | Multiplier | Effect on Projections |
|--------|------------|----------------------|
| Active | 1.0 | Full projection |
| Questionable | 0.85 | 15% reduction |
| Doubtful | 0.50 | 50% reduction |
| Out | 0.0 | Zero projection |
| IR | 0.0 | Zero projection |
| PUP | 0.0 | Zero projection |

---

**Document Control:**
- **Version**: 2.0
- **Last Modified**: March 8, 2026
- **Owner**: Data Engineering Team

**Change Log:**
- v2.0 (2026-03-08): Comprehensive rewrite covering all 15 Bronze data types (24+ with sub-types). Auto-generated column specs from local Parquet files. Added representative columns for API-only types from test mocks and config.
- v1.0 (2026-03-04): Initial data dictionary with Games, Plays, and stub entries.
