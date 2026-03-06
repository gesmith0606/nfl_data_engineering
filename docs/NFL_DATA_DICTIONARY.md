# NFL Game Prediction Data Dictionary

**Version:** 1.0  
**Last Updated:** March 4, 2026  
**Purpose:** Detailed technical specifications for NFL game prediction data model  
**Related Document:** [NFL_GAME_PREDICTION_DATA_MODEL.md](./NFL_GAME_PREDICTION_DATA_MODEL.md)

## Table of Contents
- [Bronze Layer Tables](#bronze-layer-tables)
- [Silver Layer Tables](#silver-layer-tables)
- [Gold Layer Tables](#gold-layer-tables)
- [Data Types and Constraints](#data-types-and-constraints)
- [Business Rules](#business-rules)
- [Source System Mappings](#source-system-mappings)

---

## Bronze Layer Tables

### 1. Games (Current - Implemented)

**Table Name:** `games`  
**S3 Location:** `s3://nfl-raw/games/season=YYYY/week=WW/`  
**Partitioning:** `season`, `week`  
**File Format:** Parquet (Snappy compression)  
**Source System:** nfl-data-py API  
**Update Frequency:** Weekly during season  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| game_id | STRING | NO | Unique game identifier from nfl-data-py | Format: YYYY_WW_AWAY_HOME | "2023_01_KC_DET" |
| season | INT | NO | NFL season year | Range: 1999-2025 | 2023 |
| week | INT | NO | NFL week number | Range: 1-22 (1-18 regular, 19-22 playoffs) | 1 |
| home_team | STRING | NO | Home team abbreviation | Must exist in teams reference | "KC" |
| away_team | STRING | NO | Away team abbreviation | Must exist in teams reference | "DET" |
| gameday | DATE | YES | Game date | Must be valid date | "2023-09-07" |
| gametime | TIME | YES | Kickoff time | Eastern Time format | "20:20:00" |
| home_score | INT | YES | Final home team score | Range: 0-100 | 21 |
| away_score | INT | YES | Final away team score | Range: 0-100 | 20 |
| result | INT | YES | Home team margin (home_score - away_score) | Range: -100 to 100 | 1 |
| total | INT | YES | Combined final score (home_score + away_score) | Range: 0-200 | 41 |
| overtime | INT | YES | Overtime indicator | 0=No, 1=Yes | 0 |
| location | STRING | YES | Game location | "Home" or neutral site city | "Home" |
| spread_line | DECIMAL(4,1) | YES | Closing point spread | Negative favors home team | -3.5 |
| away_moneyline | INT | YES | Away team money line | Positive for underdogs | 150 |
| home_moneyline | INT | YES | Home team money line | Negative for favorites | -170 |
| total_line | DECIMAL(4,1) | YES | Over/under total | Points | 47.5 |
| under_odds | INT | YES | Under betting odds | Typically -110 | -110 |
| over_odds | INT | YES | Over betting odds | Typically -110 | -110 |
| away_rest | INT | YES | Away team days of rest | Range: 3-14 | 7 |
| home_rest | INT | YES | Home team days of rest | Range: 3-14 | 7 |
| div_game | BOOLEAN | YES | Division game indicator | TRUE/FALSE | FALSE |
| roof | STRING | YES | Stadium roof type | "dome", "outdoors", "closed", "open" | "outdoors" |
| away_qb_name | STRING | YES | Starting away quarterback | Player name | "Jared Goff" |
| home_qb_name | STRING | YES | Starting home quarterback | Player name | "Patrick Mahomes" |
| away_coach | STRING | YES | Away team head coach | Coach name | "Dan Campbell" |
| home_coach | STRING | YES | Home team head coach | Coach name | "Andy Reid" |
| referee | STRING | YES | Game referee | Official name | "Brad Allen" |
| stadium | STRING | YES | Stadium name | Official stadium name | "GEHA Field at Arrowhead Stadium" |
| data_source | STRING | NO | Data source identifier | Always "nfl-data-py" | "nfl-data-py" |
| ingestion_timestamp | TIMESTAMP | NO | ETL processing timestamp | UTC timestamp | "2023-09-08 12:30:15" |
| seasons_requested | STRING | YES | Original seasons parameter | JSON array format | "[2023]" |
| week_filter | INT | YES | Original week filter | Week number or null | 1 |

**Primary Key:** `game_id`  
**Foreign Keys:** None (reference table)  
**Indexes:** `season`, `week`, `home_team`, `away_team`

### 2. Plays (Current - Implemented)

**Table Name:** `plays`  
**S3 Location:** `s3://nfl-raw/plays/season=YYYY/week=WW/`  
**Partitioning:** `season`, `week`  
**File Format:** Parquet (Snappy compression)  
**Source System:** nfl-data-py API  
**Update Frequency:** Weekly during season  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| game_id | STRING | NO | Foreign key to games table | Must exist in games table | "2023_01_KC_DET" |
| play_id | STRING | NO | Unique play identifier within game | Incremental within game | "1" |
| season | INT | NO | NFL season year | Range: 1999-2025 | 2023 |
| week | INT | NO | NFL week number | Range: 1-22 | 1 |
| home_team | STRING | NO | Home team abbreviation | Must match games.home_team | "KC" |
| away_team | STRING | NO | Away team abbreviation | Must match games.away_team | "DET" |
| possession_team | STRING | YES | Team with possession | Must be home_team or away_team | "DET" |
| play_type | STRING | YES | Type of play | "pass", "run", "punt", "field_goal", etc. | "pass" |
| down | INT | YES | Down number | Range: 1-4 | 1 |
| ydstogo | INT | YES | Yards to go for first down | Range: 0-99 | 10 |
| yards_gained | INT | YES | Net yards gained on play | Range: -99 to 99 | 7 |
| quarter_seconds_remaining | INT | YES | Seconds remaining in quarter | Range: 0-900 | 894 |
| passer_player_name | STRING | YES | Quarterback name on pass plays | Player name or null | "Jared Goff" |
| receiver_player_name | STRING | YES | Target receiver name on pass plays | Player name or null | "Amon-Ra St. Brown" |
| offense_formation | STRING | YES | Offensive formation | Formation type | "SHOTGUN" |
| offense_personnel | STRING | YES | Offensive personnel grouping | Personnel notation | "11 PERSONNEL" |
| defense_personnel | STRING | YES | Defensive personnel grouping | Personnel notation | "NICKEL" |
| defenders_in_box | INT | YES | Number of defenders in box | Range: 0-11 | 7 |
| n_offense | INT | YES | Number of offensive players | Should be 11 | 11 |
| n_defense | INT | YES | Number of defensive players | Should be 11 | 11 |
| ngs_air_yards | DECIMAL(5,2) | YES | Next Gen Stats air yards | Can be negative | 8.5 |
| time_to_throw | DECIMAL(4,2) | YES | Time from snap to throw (seconds) | Range: 0-20 | 2.87 |
| was_pressure | BOOLEAN | YES | QB pressure indicator | TRUE/FALSE/null | FALSE |
| route | STRING | YES | Receiver route type | Route description | "SLANT" |
| defense_man_zone_type | STRING | YES | Coverage type | "Man", "Zone", "Mixed" | "Zone" |
| defense_coverage_type | STRING | YES | Specific coverage | Coverage description | "Cover 2" |
| data_source | STRING | NO | Data source identifier | Always "nfl-data-py" | "nfl-data-py" |
| ingestion_timestamp | TIMESTAMP | NO | ETL processing timestamp | UTC timestamp | "2023-09-08 12:35:22" |

**Primary Key:** `game_id`, `play_id`  
**Foreign Keys:** `game_id` → `games.game_id`  
**Indexes:** `season`, `week`, `possession_team`, `play_type`

### 3. Teams (Future - Planned)

**Table Name:** `teams`  
**S3 Location:** `s3://nfl-raw/teams/`  
**Partitioning:** None (reference table)  
**File Format:** Parquet (Snappy compression)  
**Source System:** nfl-data-py API  
**Update Frequency:** Annually or as needed  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| team_abbr | STRING | NO | Primary team abbreviation | 2-4 character code | "KC" |
| team_name | STRING | NO | Official team name | Full team name | "Kansas City Chiefs" |
| team_city | STRING | NO | Team city | City name | "Kansas City" |
| team_division | STRING | NO | Division identifier | AFC/NFC + EAST/WEST/NORTH/SOUTH | "AFC_WEST" |
| team_conference | STRING | NO | Conference identifier | "AFC" or "NFC" | "AFC" |
| team_logo_url | STRING | YES | Logo image URL | Valid URL or null | "https://..." |
| team_primary_color | STRING | YES | Primary color hex code | 6-character hex | "#E31837" |
| team_secondary_color | STRING | YES | Secondary color hex code | 6-character hex | "#FFB81C" |
| stadium_name | STRING | YES | Home stadium name | Official stadium name | "GEHA Field at Arrowhead Stadium" |
| stadium_capacity | INT | YES | Stadium capacity | Range: 50000-100000 | 76416 |
| stadium_surface | STRING | YES | Playing surface type | "Grass", "FieldTurf", etc. | "Grass" |
| stadium_roof_type | STRING | YES | Roof configuration | "Open", "Dome", "Retractable" | "Open" |
| data_source | STRING | NO | Data source identifier | Always "nfl-data-py" | "nfl-data-py" |
| ingestion_timestamp | TIMESTAMP | NO | ETL processing timestamp | UTC timestamp | "2023-08-15 10:00:00" |

**Primary Key:** `team_abbr`  
**Foreign Keys:** None (reference table)  
**Indexes:** `team_division`, `team_conference`

### 4. Players (Future - Planned)

**Table Name:** `players`  
**S3 Location:** `s3://nfl-raw/players/season=YYYY/`  
**Partitioning:** `season`  
**File Format:** Parquet (Snappy compression)  
**Source System:** nfl-data-py API  
**Update Frequency:** Weekly during season  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| player_id | STRING | NO | Unique player identifier | nfl-data-py player ID | "00-0019596" |
| season | INT | NO | NFL season year | Range: 1999-2025 | 2023 |
| player_name | STRING | NO | Full player name | First Last format | "Patrick Mahomes" |
| team | STRING | NO | Current team abbreviation | Must exist in teams table | "KC" |
| position | STRING | NO | Primary position | Standard position abbreviations | "QB" |
| jersey_number | INT | YES | Jersey number | Range: 0-99 | 15 |
| height | INT | YES | Height in inches | Range: 60-90 | 75 |
| weight | INT | YES | Weight in pounds | Range: 150-400 | 225 |
| birth_date | DATE | YES | Birth date | Valid date | "1995-09-17" |
| years_exp | INT | YES | Years of NFL experience | Range: 0-25 | 6 |
| college | STRING | YES | College attended | College name | "Texas Tech" |
| data_source | STRING | NO | Data source identifier | Always "nfl-data-py" | "nfl-data-py" |
| ingestion_timestamp | TIMESTAMP | NO | ETL processing timestamp | UTC timestamp | "2023-09-08 10:00:00" |

**Primary Key:** `player_id`, `season`  
**Foreign Keys:** `team` → `teams.team_abbr`  
**Indexes:** `season`, `team`, `position`

### 5. Weather (Future - Planned)

**Table Name:** `weather`  
**S3 Location:** `s3://nfl-raw/weather/season=YYYY/week=WW/`  
**Partitioning:** `season`, `week`  
**File Format:** Parquet (Snappy compression)  
**Source System:** Weather API (OpenWeatherMap, AccuWeather)  
**Update Frequency:** Game day + historical backfill  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| game_id | STRING | NO | Foreign key to games table | Must exist in games table | "2023_01_KC_DET" |
| temperature | INT | YES | Temperature at kickoff (Fahrenheit) | Range: -20 to 120 | 72 |
| humidity | INT | YES | Relative humidity percentage | Range: 0-100 | 65 |
| wind_speed | INT | YES | Wind speed in mph | Range: 0-50 | 8 |
| wind_direction | STRING | YES | Wind direction | Cardinal/ordinal directions | "SW" |
| precipitation | STRING | YES | Precipitation type | "None", "Rain", "Snow", "Mixed" | "None" |
| weather_detail | STRING | YES | Detailed weather description | Free text description | "Partly cloudy" |
| data_source | STRING | NO | Weather data source | API identifier | "OpenWeatherMap" |
| ingestion_timestamp | TIMESTAMP | NO | ETL processing timestamp | UTC timestamp | "2023-09-08 15:00:00" |

**Primary Key:** `game_id`  
**Foreign Keys:** `game_id` → `games.game_id`  
**Indexes:** `season`, `week`

---

## Silver Layer Tables

### 1. Games (Silver)

**Table Name:** `games_silver`  
**S3 Location:** `s3://nfl-refined/games/season=YYYY/week=WW/`  
**Partitioning:** `season`, `week`  
**File Format:** Delta Lake (Parquet + transaction log)  
**Source System:** Bronze games table + enrichments  
**Update Frequency:** Daily during season  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| game_id | STRING | NO | Primary key from bronze | Validated format | "2023_01_KC_DET" |
| season | INT | NO | Validated season year | Range: 1999-2025 | 2023 |
| week | INT | NO | Validated week number | Range: 1-22 | 1 |
| game_date | DATE | NO | Standardized game date | No nulls allowed | "2023-09-07" |
| game_time_et | TIME | YES | Eastern Time kickoff | Converted to ET | "20:20:00" |
| home_team_id | STRING | NO | Standardized home team ID | From teams reference | "KC" |
| away_team_id | STRING | NO | Standardized away team ID | From teams reference | "DET" |
| home_score | INT | NO | Validated home score | Range: 0-100, no nulls | 21 |
| away_score | INT | NO | Validated away score | Range: 0-100, no nulls | 20 |
| game_result | INT | NO | Home team margin | home_score - away_score | 1 |
| total_points | INT | NO | Total points scored | home_score + away_score | 41 |
| overtime_flag | BOOLEAN | NO | Overtime occurred | TRUE/FALSE, default FALSE | FALSE |
| neutral_site_flag | BOOLEAN | NO | Neutral site game | Derived from location | FALSE |
| dome_game_flag | BOOLEAN | NO | Indoor/dome game | From stadium reference | FALSE |
| division_game_flag | BOOLEAN | NO | Division matchup | From team divisions | FALSE |
| playoff_flag | BOOLEAN | NO | Playoff game | week > 18 | FALSE |
| prime_time_flag | BOOLEAN | NO | Prime time game | SNF/MNF/TNF | TRUE |
| game_type | STRING | NO | Game type category | "REG", "WC", "DIV", "CONF", "SB" | "REG" |
| season_type | STRING | NO | Season phase | "Regular", "Playoffs" | "Regular" |
| week_category | STRING | NO | Season timing | "Early", "Mid", "Late" | "Early" |
| home_rest_days | INT | NO | Home team rest | Default 7 if null | 7 |
| away_rest_days | INT | NO | Away team rest | Default 7 if null | 7 |
| rest_differential | INT | NO | Rest advantage | home_rest - away_rest | 0 |
| spread | DECIMAL(4,1) | YES | Closing point spread | Negative favors home | -3.5 |
| total_line | DECIMAL(4,1) | YES | Closing total | Points | 47.5 |
| home_favorite_flag | BOOLEAN | YES | Home team favored | spread < 0 | TRUE |
| spread_cover_result | STRING | YES | Spread outcome | "Home_Cover", "Away_Cover", "Push" | "Away_Cover" |
| total_result | STRING | YES | Total outcome | "Over", "Under", "Push" | "Under" |
| temperature | INT | YES | Game temperature | From weather table | 72 |
| wind_speed | INT | YES | Wind speed | From weather table | 8 |
| precipitation_flag | BOOLEAN | YES | Precipitation present | TRUE/FALSE/null | FALSE |
| weather_category | STRING | YES | Weather classification | "Good", "Fair", "Poor" | "Good" |
| data_quality_score | DECIMAL(3,2) | NO | Quality assessment | Range: 0.00-1.00 | 0.95 |
| validation_status | STRING | NO | Validation result | "PASSED", "WARNING", "FAILED" | "PASSED" |
| load_timestamp | TIMESTAMP | NO | Silver ETL timestamp | UTC timestamp | "2023-09-08 14:00:00" |

**Primary Key:** `game_id`  
**Foreign Keys:** `home_team_id`, `away_team_id` → `teams_silver.team_id`  
**Indexes:** `season`, `week`, `game_date`, `home_team_id`, `away_team_id`

### 2. Teams (Silver)

**Table Name:** `teams_silver`  
**S3 Location:** `s3://nfl-refined/teams/`  
**Partitioning:** None (reference table)  
**File Format:** Delta Lake (Parquet + transaction log)  
**Source System:** Bronze teams + external references  
**Update Frequency:** Weekly or as needed  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| team_id | STRING | NO | Primary standardized team ID | 2-4 character code | "KC" |
| team_abbr | STRING | NO | Official abbreviation | Alternative abbreviations | "KC" |
| team_name | STRING | NO | Standardized team name | Current official name | "Kansas City Chiefs" |
| team_city | STRING | NO | Team city | Current city | "Kansas City" |
| team_state | STRING | YES | State abbreviation | 2-character state code | "MO" |
| division_id | STRING | NO | Division identifier | AFC/NFC_EAST/WEST/NORTH/SOUTH | "AFC_WEST" |
| conference | STRING | NO | Conference | "AFC" or "NFC" | "AFC" |
| founded_year | INT | YES | Franchise founded year | Range: 1920-2025 | 1960 |
| stadium_id | STRING | YES | Stadium identifier | Unique stadium ID | "ARROWHEAD" |
| stadium_name | STRING | YES | Current stadium name | Official name | "GEHA Field at Arrowhead Stadium" |
| stadium_capacity | INT | YES | Stadium capacity | Range: 50000-100000 | 76416 |
| stadium_surface | STRING | YES | Playing surface | "Grass", "Turf" variations | "Grass" |
| stadium_roof_type | STRING | YES | Roof configuration | "Open", "Dome", "Retractable" | "Open" |
| stadium_elevation | INT | YES | Elevation in feet | Range: -300 to 6000 | 742 |
| time_zone | STRING | YES | Stadium time zone | Standard time zone | "America/Chicago" |
| stadium_lat | DECIMAL(8,6) | YES | Stadium latitude | Valid coordinates | 39.048889 |
| stadium_lng | DECIMAL(9,6) | YES | Stadium longitude | Valid coordinates | -94.484444 |
| stadium_city | STRING | YES | Stadium city | May differ from team city | "Kansas City" |
| stadium_state | STRING | YES | Stadium state | 2-character code | "MO" |
| primary_color | STRING | YES | Primary color hex | 6-character hex code | "#E31837" |
| secondary_color | STRING | YES | Secondary color hex | 6-character hex code | "#FFB81C" |
| logo_url | STRING | YES | Logo image URL | Valid URL | "https://..." |
| team_website | STRING | YES | Official website | Valid URL | "https://www.chiefs.com" |
| load_timestamp | TIMESTAMP | NO | Silver ETL timestamp | UTC timestamp | "2023-08-15 12:00:00" |

**Primary Key:** `team_id`  
**Foreign Keys:** None (reference table)  
**Indexes:** `division_id`, `conference`, `stadium_id`

### 3. Plays (Silver)

**Table Name:** `plays_silver`  
**S3 Location:** `s3://nfl-refined/plays/season=YYYY/week=WW/`  
**Partitioning:** `season`, `week`  
**File Format:** Delta Lake (Parquet + transaction log)  
**Source System:** Bronze plays + enrichments  
**Update Frequency:** Daily during season  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| game_id | STRING | NO | Foreign key to games | Validated reference | "2023_01_KC_DET" |
| play_id | STRING | NO | Primary key within game | Sequential within game | "43" |
| season | INT | NO | Season year | Validated range | 2023 |
| week | INT | NO | Week number | Validated range | 1 |
| drive_id | STRING | YES | Drive identifier | game_id + drive sequence | "2023_01_KC_DET_1" |
| sequence_number | INT | NO | Play sequence in drive | Sequential per drive | 1 |
| quarter | INT | NO | Quarter number | Range: 1-5 (5=OT) | 1 |
| game_seconds_remaining | INT | NO | Total game seconds left | Range: 0-3600 | 3534 |
| quarter_seconds_remaining | INT | NO | Quarter seconds left | Range: 0-900 | 894 |
| play_clock | DECIMAL(4,1) | YES | Play clock when snapped | Range: 0-40 | 23.5 |
| game_state | STRING | NO | Game situation | "Normal", "Two_Minute", "Overtime" | "Normal" |
| possession_team_id | STRING | NO | Team with possession | Validated team ID | "DET" |
| defense_team_id | STRING | NO | Defending team | Validated team ID | "KC" |
| home_team_id | STRING | NO | Home team | From games table | "KC" |
| away_team_id | STRING | NO | Away team | From games table | "DET" |
| yardline_100 | INT | NO | Yards from goal | Range: 0-100 | 75 |
| down | INT | NO | Down number | Range: 1-4 | 1 |
| ydstogo | INT | NO | Yards to go | Range: 0-99 | 10 |
| goal_to_go_flag | BOOLEAN | NO | Goal-to-go situation | yardline_100 <= ydstogo | FALSE |
| play_type | STRING | NO | Standardized play type | Controlled vocabulary | "pass" |
| play_type_detail | STRING | YES | Detailed play type | Extended classification | "short_pass" |
| rush_attempt | BOOLEAN | NO | Rush attempt flag | TRUE/FALSE | FALSE |
| pass_attempt | BOOLEAN | NO | Pass attempt flag | TRUE/FALSE | TRUE |
| penalty_flag | BOOLEAN | NO | Penalty occurred | TRUE/FALSE | FALSE |
| touchdown_flag | BOOLEAN | NO | Touchdown scored | TRUE/FALSE | FALSE |
| interception_flag | BOOLEAN | NO | Interception occurred | TRUE/FALSE | FALSE |
| fumble_flag | BOOLEAN | NO | Fumble occurred | TRUE/FALSE | FALSE |
| safety_flag | BOOLEAN | NO | Safety scored | TRUE/FALSE | FALSE |
| special_teams_flag | BOOLEAN | NO | Special teams play | TRUE/FALSE | FALSE |
| yards_gained | INT | NO | Net yards gained | Range: -99 to 99 | 7 |
| first_down_flag | BOOLEAN | NO | First down achieved | TRUE/FALSE | FALSE |
| field_goal_flag | BOOLEAN | NO | Field goal attempt | TRUE/FALSE | FALSE |
| punt_flag | BOOLEAN | NO | Punt occurred | TRUE/FALSE | FALSE |
| turnover_flag | BOOLEAN | NO | Turnover occurred | TRUE/FALSE | FALSE |
| penalty_yards | INT | NO | Penalty yards | Range: 0-50, default 0 | 0 |
| score_differential | INT | NO | Possession team advantage | pos_score - def_score | -3 |
| home_score | INT | NO | Home score after play | Range: 0-100 | 0 |
| away_score | INT | NO | Away score after play | Range: 0-100 | 0 |
| possession_score | INT | NO | Possession team score | Derived field | 0 |
| defense_score | INT | NO | Defense team score | Derived field | 0 |
| offense_formation | STRING | YES | Offensive formation | Controlled vocabulary | "SHOTGUN" |
| offense_personnel | STRING | YES | Offensive personnel | Standard notation | "11 PERSONNEL" |
| defense_personnel | STRING | YES | Defensive personnel | Standard notation | "BASE" |
| no_huddle_flag | BOOLEAN | NO | No huddle snap | TRUE/FALSE | FALSE |
| passer_id | STRING | YES | Quarterback player ID | From players reference | "00-0033873" |
| passer_name | STRING | YES | Standardized QB name | First Last format | "Jared Goff" |
| rusher_id | STRING | YES | Ball carrier player ID | From players reference | null |
| rusher_name | STRING | YES | Standardized rusher name | First Last format | null |
| receiver_id | STRING | YES | Target receiver player ID | From players reference | "00-0035228" |
| receiver_name | STRING | YES | Standardized receiver name | First Last format | "Amon-Ra St. Brown" |
| air_yards | INT | YES | Quarterback air yards | Range: -20 to 80 | 9 |
| yards_after_catch | INT | YES | YAC on reception | Range: -20 to 80 | -2 |
| time_to_throw | DECIMAL(4,2) | YES | Seconds to throw | Range: 0-20 | 2.87 |
| qb_hit_flag | BOOLEAN | YES | QB was hit | TRUE/FALSE/null | FALSE |
| qb_pressure_flag | BOOLEAN | YES | QB under pressure | TRUE/FALSE/null | FALSE |
| blitz_flag | BOOLEAN | YES | Defense blitzed | TRUE/FALSE/null | FALSE |
| expected_yards | DECIMAL(5,2) | YES | Expected yards for situation | Advanced metric | 6.2 |
| success_flag | BOOLEAN | YES | Successful play | 50% of expected yards | TRUE |
| load_timestamp | TIMESTAMP | NO | Silver ETL timestamp | UTC timestamp | "2023-09-08 14:30:00" |

**Primary Key:** `game_id`, `play_id`  
**Foreign Keys:** 
- `game_id` → `games_silver.game_id`
- `possession_team_id` → `teams_silver.team_id`
- `defense_team_id` → `teams_silver.team_id`
- `passer_id` → `players_silver.player_id`  

**Indexes:** `season`, `week`, `possession_team_id`, `play_type`

---

## Gold Layer Tables

### 1. Team_Performance_Metrics (Gold)

**Table Name:** `team_performance_metrics`  
**S3 Location:** `s3://nfl-trusted/team_performance/season=YYYY/metric_type=offense/`  
**Partitioning:** `season`, `metric_type`  
**File Format:** Delta Lake (Parquet + transaction log)  
**Source System:** Silver plays and games aggregated  
**Update Frequency:** Daily during season  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| team_id | STRING | NO | Team identifier | From teams reference | "KC" |
| season | INT | NO | Season year | Partition key | 2023 |
| metric_type | STRING | NO | Metric category | "offense", "defense", "special_teams" | "offense" |
| week_number | INT | NO | Through week number | 0=season, 1-22=through week | 17 |
| games_played | INT | NO | Games in calculation | Range: 1-22 | 16 |
| points_per_game | DECIMAL(5,2) | YES | Points scored per game | Range: 0-60 | 28.18 |
| yards_per_game | DECIMAL(6,2) | YES | Total yards per game | Range: 0-700 | 389.5 |
| passing_yards_per_game | DECIMAL(6,2) | YES | Passing yards per game | Range: 0-500 | 267.8 |
| rushing_yards_per_game | DECIMAL(6,2) | YES | Rushing yards per game | Range: 0-300 | 121.7 |
| turnovers_per_game | DECIMAL(4,2) | YES | Turnovers per game | Range: 0-5 | 1.2 |
| third_down_conversion_rate | DECIMAL(5,4) | YES | Third down success rate | Range: 0-1 | 0.4231 |
| red_zone_efficiency | DECIMAL(5,4) | YES | Red zone TD rate | Range: 0-1 | 0.6154 |
| time_of_possession | DECIMAL(5,2) | YES | Minutes per game | Range: 15-45 | 30.25 |
| epa_per_play | DECIMAL(6,4) | YES | Expected Points Added per play | Range: -1 to 1 | 0.0892 |
| success_rate | DECIMAL(5,4) | YES | Successful play percentage | Range: 0-1 | 0.4756 |
| explosive_play_rate | DECIMAL(5,4) | YES | 20+ yard play percentage | Range: 0-1 | 0.0821 |
| passing_epa_per_play | DECIMAL(6,4) | YES | EPA per pass attempt | Range: -1 to 1 | 0.1234 |
| rushing_epa_per_play | DECIMAL(6,4) | YES | EPA per rush attempt | Range: -1 to 1 | 0.0123 |
| neutral_script_epa | DECIMAL(6,4) | YES | EPA in neutral situations | Range: -1 to 1 | 0.0987 |
| pressure_rate_allowed | DECIMAL(5,4) | YES | QB pressure rate allowed | Range: 0-1 | 0.2340 |
| early_down_epa | DECIMAL(6,4) | YES | EPA on 1st/2nd down | Range: -1 to 1 | 0.0456 |
| late_down_epa | DECIMAL(6,4) | YES | EPA on 3rd/4th down | Range: -1 to 1 | 0.1234 |
| goal_to_go_epa | DECIMAL(6,4) | YES | Red zone EPA | Range: -1 to 1 | 0.2134 |
| two_minute_epa | DECIMAL(6,4) | YES | Two-minute drill EPA | Range: -1 to 1 | 0.1876 |
| comeback_win_rate | DECIMAL(5,4) | YES | Win rate when trailing | Range: 0-1 | 0.2500 |
| opp_avg_points_per_game | DECIMAL(5,2) | YES | Opponent average PPG | Strength of schedule | 22.3 |
| opp_avg_yards_per_game | DECIMAL(6,2) | YES | Opponent average YPG | Strength of schedule | 342.1 |
| schedule_difficulty | DECIMAL(5,4) | YES | SOS rating | Range: 0-1 | 0.5234 |
| load_timestamp | TIMESTAMP | NO | Gold ETL timestamp | UTC timestamp | "2023-12-31 08:00:00" |

**Primary Key:** `team_id`, `season`, `metric_type`, `week_number`  
**Foreign Keys:** `team_id` → `teams_silver.team_id`  
**Indexes:** `season`, `team_id`, `metric_type`, `week_number`

### 2. Game_Prediction_Features (Gold)

**Table Name:** `game_prediction_features`  
**S3 Location:** `s3://nfl-trusted/prediction_features/season=YYYY/week=WW/`  
**Partitioning:** `season`, `week`  
**File Format:** Delta Lake (Parquet + transaction log)  
**Source System:** Multiple Gold layer aggregations  
**Update Frequency:** Daily before games  

| Column Name | Data Type | Nullable | Description | Business Rules | Example |
|-------------|-----------|----------|-------------|---------------|---------|
| game_id | STRING | NO | Primary key | From games table | "2023_17_KC_LV" |
| season | INT | NO | Season year | Partition key | 2023 |
| week | INT | NO | Week number | Partition key | 17 |
| prediction_date | DATE | NO | Feature calculation date | Must be before game | "2023-12-25" |
| days_until_game | INT | NO | Days ahead prediction | Range: 0-7 | 0 |
| home_team_id | STRING | NO | Home team | From teams reference | "LV" |
| away_team_id | STRING | NO | Away team | From teams reference | "KC" |
| home_team_seed | INT | YES | Playoff seed | Range: 1-14 or null | null |
| away_team_seed | INT | YES | Playoff seed | Range: 1-14 or null | null |
| division_game_flag | BOOLEAN | NO | Division matchup | TRUE/FALSE | TRUE |
| conference_game_flag | BOOLEAN | NO | Conference matchup | TRUE/FALSE | TRUE |
| prime_time_flag | BOOLEAN | NO | Prime time game | TRUE/FALSE | TRUE |
| playoff_flag | BOOLEAN | NO | Playoff game | TRUE/FALSE | FALSE |
| dome_game_flag | BOOLEAN | NO | Indoor game | TRUE/FALSE | TRUE |
| home_field_advantage | DECIMAL(5,4) | NO | Historical home win rate | Range: 0-1 | 0.6250 |
| home_team_elo | INT | NO | Elo rating | Range: 1000-2000 | 1687 |
| away_team_elo | INT | NO | Elo rating | Range: 1000-2000 | 1743 |
| elo_differential | INT | NO | Home - Away Elo | Range: -1000 to 1000 | -56 |
| power_ranking_diff | INT | YES | Power ranking difference | Range: -31 to 31 | -3 |
| home_recent_record | DECIMAL(4,3) | NO | Last 4 games win % | Range: 0-1 | 0.750 |
| away_recent_record | DECIMAL(4,3) | NO | Last 4 games win % | Range: 0-1 | 1.000 |
| home_recent_ppg | DECIMAL(5,2) | NO | Last 4 games PPG | Range: 0-60 | 24.75 |
| away_recent_ppg | DECIMAL(5,2) | NO | Last 4 games PPG | Range: 0-60 | 31.50 |
| home_recent_papg | DECIMAL(5,2) | NO | Last 4 games PAPG | Range: 0-60 | 22.00 |
| away_recent_papg | DECIMAL(5,2) | NO | Last 4 games PAPG | Range: 0-60 | 15.25 |
| home_season_record | DECIMAL(5,4) | NO | Season win percentage | Range: 0-1 | 0.5625 |
| away_season_record | DECIMAL(5,4) | NO | Season win percentage | Range: 0-1 | 0.8750 |
| home_point_differential | DECIMAL(6,2) | NO | Season point differential | Range: -500 to 500 | 18.00 |
| away_point_differential | DECIMAL(6,2) | NO | Season point differential | Range: -500 to 500 | 156.00 |
| home_sos | DECIMAL(5,4) | NO | Strength of schedule | Range: 0-1 | 0.5234 |
| away_sos | DECIMAL(5,4) | NO | Strength of schedule | Range: 0-1 | 0.4876 |
| home_epa_per_play | DECIMAL(6,4) | NO | Season EPA/play | Range: -1 to 1 | 0.0234 |
| away_epa_per_play | DECIMAL(6,4) | NO | Season EPA/play | Range: -1 to 1 | 0.1456 |
| home_def_epa_per_play | DECIMAL(6,4) | NO | Defensive EPA/play | Range: -1 to 1 | -0.0123 |
| away_def_epa_per_play | DECIMAL(6,4) | NO | Defensive EPA/play | Range: -1 to 1 | -0.0876 |
| home_success_rate | DECIMAL(5,4) | NO | Offensive success rate | Range: 0-1 | 0.4523 |
| away_success_rate | DECIMAL(5,4) | NO | Offensive success rate | Range: 0-1 | 0.4987 |
| home_def_success_rate | DECIMAL(5,4) | NO | Defensive success rate | Range: 0-1 | 0.5123 |
| away_def_success_rate | DECIMAL(5,4) | NO | Defensive success rate | Range: 0-1 | 0.5456 |
| home_qb_epa_per_play | DECIMAL(6,4) | YES | Starting QB EPA | Range: -1 to 1 | 0.0456 |
| away_qb_epa_per_play | DECIMAL(6,4) | YES | Starting QB EPA | Range: -1 to 1 | 0.2134 |
| home_qb_cpoe | DECIMAL(6,4) | YES | QB CPOE | Range: -0.2 to 0.2 | 0.0234 |
| away_qb_cpoe | DECIMAL(6,4) | YES | QB CPOE | Range: -0.2 to 0.2 | 0.0567 |
| home_qb_pressure_rate | DECIMAL(5,4) | YES | QB pressure rate | Range: 0-1 | 0.2340 |
| away_qb_pressure_rate | DECIMAL(5,4) | YES | QB pressure rate | Range: 0-1 | 0.1987 |
| home_key_injuries | INT | NO | Key player injuries | Range: 0-10 | 2 |
| away_key_injuries | INT | NO | Key player injuries | Range: 0-10 | 1 |
| home_injury_cap_impact | DECIMAL(8,2) | YES | Injury cap impact ($M) | Range: 0-100 | 15.50 |
| away_injury_cap_impact | DECIMAL(8,2) | YES | Injury cap impact ($M) | Range: 0-100 | 8.25 |
| home_rest_days | INT | NO | Rest days | Range: 3-14 | 7 |
| away_rest_days | INT | NO | Rest days | Range: 3-14 | 7 |
| rest_advantage | INT | NO | Rest differential | Range: -11 to 11 | 0 |
| away_travel_distance | INT | YES | Travel miles | Range: 0-5000 | 1654 |
| h2h_home_wins | INT | YES | H2H home wins (last 5) | Range: 0-5 | 2 |
| h2h_away_wins | INT | YES | H2H away wins (last 5) | Range: 0-5 | 3 |
| h2h_avg_total | DECIMAL(5,2) | YES | H2H average total | Range: 10-80 | 48.6 |
| h2h_home_avg_margin | DECIMAL(5,2) | YES | H2H home margin | Range: -50 to 50 | -3.4 |
| home_coach_experience | INT | YES | HC years experience | Range: 0-50 | 11 |
| away_coach_experience | INT | YES | HC years experience | Range: 0-50 | 5 |
| coach_h2h_record | DECIMAL(4,3) | YES | HC H2H record | Range: 0-1 | 0.400 |
| temperature | INT | YES | Game temperature (F) | Range: -20 to 120 | 72 |
| wind_speed | INT | YES | Wind speed (mph) | Range: 0-50 | 8 |
| precipitation_flag | BOOLEAN | YES | Rain/snow expected | TRUE/FALSE/null | FALSE |
| weather_impact_score | DECIMAL(4,3) | YES | Weather impact | Range: 0-1 | 0.100 |
| closing_spread | DECIMAL(4,1) | YES | Vegas closing spread | Range: -28 to 28 | -3.5 |
| closing_total | DECIMAL(4,1) | YES | Vegas closing total | Range: 30-70 | 47.5 |
| market_movement | DECIMAL(4,1) | YES | Line movement | Range: -14 to 14 | 1.0 |
| public_betting_pct | DECIMAL(5,4) | YES | Public money % | Range: 0-1 | 0.6740 |
| actual_home_score | INT | YES | Actual home score | Post-game only | 31 |
| actual_away_score | INT | YES | Actual away score | Post-game only | 17 |
| actual_margin | INT | YES | Actual home margin | Post-game only | 14 |
| actual_total | INT | YES | Actual total score | Post-game only | 48 |
| spread_result | STRING | YES | Spread outcome | "Home_Cover", "Away_Cover", "Push" | "Home_Cover" |
| total_result | STRING | YES | Total outcome | "Over", "Under", "Push" | "Over" |
| home_win_flag | BOOLEAN | YES | Home team won | Post-game only | TRUE |
| load_timestamp | TIMESTAMP | NO | Gold ETL timestamp | UTC timestamp | "2023-12-25 12:00:00" |

**Primary Key:** `game_id`  
**Foreign Keys:** 
- `home_team_id` → `teams_silver.team_id`
- `away_team_id` → `teams_silver.team_id`  

**Indexes:** `season`, `week`, `prediction_date`, `home_team_id`, `away_team_id`

---

## Data Types and Constraints

### Standard Data Types

| Data Type | Description | Range/Format | Example |
|-----------|-------------|--------------|---------|
| STRING | Variable length text | UTF-8, max 65535 chars | "Kansas City Chiefs" |
| INT | 32-bit integer | -2,147,483,648 to 2,147,483,647 | 2023 |
| BIGINT | 64-bit integer | Large numbers | 1234567890 |
| DECIMAL(p,s) | Fixed precision decimal | p=precision, s=scale | DECIMAL(5,2) = 123.45 |
| BOOLEAN | True/false value | TRUE, FALSE, null | TRUE |
| DATE | Date only | YYYY-MM-DD | "2023-09-07" |
| TIME | Time only | HH:MM:SS | "20:20:00" |
| TIMESTAMP | Date and time | YYYY-MM-DD HH:MM:SS UTC | "2023-09-07 20:20:00" |

### Constraint Types

#### Primary Key Constraints
- **Single Column**: `game_id` (unique, not null)
- **Composite Key**: `game_id + play_id` (combination unique, both not null)

#### Foreign Key Constraints
- **Referential Integrity**: Child table column references parent table primary key
- **Cascade Options**: ON DELETE RESTRICT, ON UPDATE CASCADE

#### Check Constraints
```sql
-- Season validation
CHECK (season >= 1999 AND season <= 2025)

-- Week validation  
CHECK (week >= 1 AND week <= 22)

-- Score validation
CHECK (home_score >= 0 AND home_score <= 100)
CHECK (away_score >= 0 AND away_score <= 100)

-- Down validation
CHECK (down IN (1, 2, 3, 4))

-- Yards to go validation
CHECK (ydstogo >= 0 AND ydstogo <= 99)

-- Percentage validation
CHECK (success_rate >= 0 AND success_rate <= 1)

-- EPA validation
CHECK (epa_per_play >= -10 AND epa_per_play <= 10)
```

#### Unique Constraints
```sql
-- Games table
UNIQUE (season, week, home_team, away_team)

-- Teams table  
UNIQUE (team_abbr)
UNIQUE (team_name)

-- Players table
UNIQUE (player_id, season)
```

#### Not Null Constraints
- All primary key columns
- All foreign key columns
- Core business fields (scores, dates, team IDs)
- Calculated/derived fields in Gold layer

---

## Business Rules

### Data Quality Rules

#### Bronze Layer Rules
1. **Game ID Format**: Must match pattern `YYYY_WW_AWAY_HOME`
2. **Team Abbreviations**: Must exist in NFL team reference list
3. **Season Range**: 1999-2025 (nfl-data-py coverage)
4. **Week Range**: 1-18 regular season, 19-22 playoffs
5. **Score Logic**: Non-negative integers, realistic ranges

#### Silver Layer Rules
1. **Referential Integrity**: All foreign keys must have valid parent records
2. **Score Consistency**: `game_result = home_score - away_score`
3. **Total Consistency**: `total_points = home_score + away_score`
4. **Date Logic**: Game dates must be reasonable for season/week
5. **Team Logic**: Home team ≠ Away team

#### Gold Layer Rules
1. **Aggregation Consistency**: Team totals must match sum of individual games
2. **Percentage Bounds**: All rate/percentage fields between 0-1
3. **EPA Reasonableness**: EPA values typically between -2 and 2
4. **Temporal Logic**: Performance trends must be chronologically consistent

### NFL Business Rules

#### Game Rules
1. **Games per Week**: Regular season weeks have 16 games (with exceptions)
2. **Playoff Structure**: Wild Card (6 games), Divisional (4 games), Conference (2 games), Super Bowl (1 game)
3. **Division Games**: Teams play division opponents twice per season
4. **Bye Weeks**: Teams have one bye week during regular season

#### Team Rules
1. **Team Count**: 32 teams total (16 AFC, 16 NFC)
2. **Division Structure**: 8 divisions with 4 teams each
3. **Roster Limits**: 53 active players, specific position requirements
4. **Salary Cap**: Annual team salary limitations

#### Player Rules
1. **Position Groups**: QB, RB, WR, TE, OL, DL, LB, DB, ST
2. **Jersey Numbers**: Position-specific number ranges
3. **Eligibility**: Rookie eligibility, veteran status rules
4. **Contract Rules**: Salary cap implications, franchise tags

#### Scoring Rules
1. **Touchdown**: 6 points
2. **Extra Point**: 1 point (kick), 2 points (conversion)
3. **Field Goal**: 3 points
4. **Safety**: 2 points
5. **Maximum Realistic Score**: ~70 points per team

---

## Source System Mappings

### nfl-data-py API Mappings

#### Games Data Source
```python
# Source: nfl.import_schedules([season])
source_mapping = {
    'game_id': 'game_id',           # Direct mapping
    'season': 'season',             # Direct mapping  
    'week': 'week',                 # Direct mapping
    'gameday': 'gameday',           # Direct mapping
    'gametime': 'gametime',         # Direct mapping
    'away_team': 'away_team',       # Direct mapping
    'home_team': 'home_team',       # Direct mapping
    'away_score': 'away_score',     # Direct mapping
    'home_score': 'home_score',     # Direct mapping
    'result': 'result',             # Direct mapping
    'total': 'total',               # Direct mapping
    'overtime': 'overtime',         # Direct mapping
    'old_game_id': None,            # Ignore field
    'gsis': None,                   # Ignore field
    'nfl_detail_id': None,          # Ignore field
    'pfr': None,                    # Ignore field
    'pff': None,                    # Ignore field
    'espn': None                    # Ignore field
}
```

#### Plays Data Source
```python
# Source: nfl.import_pbp_data([season], columns=[...])
source_mapping = {
    'game_id': 'game_id',                           # Direct mapping
    'play_id': 'play_id',                           # Direct mapping
    'season': 'season',                             # Direct mapping
    'week': 'week',                                 # Direct mapping
    'home_team': 'home_team',                       # Direct mapping
    'away_team': 'away_team',                       # Direct mapping
    'posteam': 'possession_team',                   # Field rename
    'defteam': 'defense_team',                      # Field rename
    'quarter_seconds_remaining': 'quarter_seconds_remaining',  # Direct mapping
    'down': 'down',                                 # Direct mapping
    'ydstogo': 'ydstogo',                          # Direct mapping
    'yards_gained': 'yards_gained',                 # Direct mapping
    'play_type': 'play_type',                       # Direct mapping
    'passer_player_name': 'passer_player_name',     # Direct mapping
    'receiver_player_name': 'receiver_player_name', # Direct mapping
    'rusher_player_name': 'rusher_player_name',     # Add to schema
    'interception': 'interception_flag',            # Type conversion
    'fumble': 'fumble_flag',                        # Type conversion
    'touchdown': 'touchdown_flag',                  # Type conversion
    'penalty': 'penalty_flag',                      # Type conversion
    'epa': 'epa',                                   # Add to schema
    'wpa': 'wpa',                                   # Add to schema
    'air_yards': 'air_yards',                       # Direct mapping
    'yards_after_catch': 'yards_after_catch',       # Direct mapping
    'qb_hit': 'qb_hit_flag',                        # Type conversion
    'pass_attempt': 'pass_attempt',                 # Direct mapping
    'rush_attempt': 'rush_attempt',                 # Direct mapping
}
```

#### Teams Data Source
```python
# Source: nfl.import_team_desc()
source_mapping = {
    'team_abbr': 'team_abbr',       # Direct mapping
    'team_name': 'team_name',       # Direct mapping
    'team_id': 'team_id',           # Direct mapping
    'team_color': 'primary_color',  # Field rename
    'team_color2': 'secondary_color', # Field rename
    'team_logo_wikipedia': 'logo_url', # Field rename
    'team_logo_espn': None,         # Alternative logo source
    'team_wordmark': None,          # Ignore field
    'team_conference': 'conference', # Field rename
    'team_division': 'division'     # Field rename
}
```

### External Data Sources

#### Weather API Integration
```python
# Source: OpenWeatherMap API
weather_api_mapping = {
    'game_id': lambda x: generate_game_id(x),  # Derived field
    'temp': 'temperature',                      # Field mapping
    'humidity': 'humidity',                     # Direct mapping  
    'wind_speed': 'wind_speed',                 # Direct mapping
    'wind_deg': 'wind_direction',               # Convert degrees to cardinal
    'weather.main': 'precipitation',            # Weather condition mapping
    'weather.description': 'weather_detail',   # Detailed description
    'dt': 'weather_timestamp'                  # Unix timestamp conversion
}

# Weather condition mapping
weather_condition_map = {
    'Clear': 'None',
    'Clouds': 'None', 
    'Rain': 'Rain',
    'Drizzle': 'Rain',
    'Thunderstorm': 'Rain',
    'Snow': 'Snow',
    'Mist': 'None',
    'Fog': 'None'
}
```

#### Betting Lines Integration
```python
# Source: Vegas Insider, Action Network
betting_lines_mapping = {
    'game_id': lambda x: map_to_game_id(x),    # External ID mapping
    'spread': 'closing_spread',                 # Point spread
    'total': 'closing_total',                   # Over/under
    'home_ml': 'home_moneyline',               # Money line
    'away_ml': 'away_moneyline',               # Money line
    'consensus_spread': 'market_movement',      # Line movement
    'public_bets_pct': 'public_betting_pct'    # Public betting percentage
}
```

#### Player Tracking Data
```python
# Source: NFL Next Gen Stats
ngs_mapping = {
    'gameId': 'game_id',                       # Game identifier mapping
    'playId': 'play_id',                       # Play identifier mapping
    'nflId': 'player_id',                      # Player identifier mapping
    'frameId': 'tracking_frame',               # Frame sequence
    'time': 'tracking_timestamp',              # Timestamp
    'x': 'field_x_coordinate',                 # Field X position
    'y': 'field_y_coordinate',                 # Field Y position  
    'speed': 'player_speed',                   # Speed (yards/second)
    'acceleration': 'player_acceleration',      # Acceleration
    'direction': 'player_direction',           # Direction (degrees)
    'orientation': 'player_orientation',       # Body orientation
    'event': 'play_event'                      # Play event marker
}
```

### Data Transformation Rules

#### Team Name Standardization
```python
team_name_mapping = {
    'ARI': {'abbr': 'ARI', 'name': 'Arizona Cardinals', 'city': 'Arizona'},
    'ATL': {'abbr': 'ATL', 'name': 'Atlanta Falcons', 'city': 'Atlanta'},
    'BAL': {'abbr': 'BAL', 'name': 'Baltimore Ravens', 'city': 'Baltimore'},
    'BUF': {'abbr': 'BUF', 'name': 'Buffalo Bills', 'city': 'Buffalo'},
    'CAR': {'abbr': 'CAR', 'name': 'Carolina Panthers', 'city': 'Carolina'},
    'CHI': {'abbr': 'CHI', 'name': 'Chicago Bears', 'city': 'Chicago'},
    'CIN': {'abbr': 'CIN', 'name': 'Cincinnati Bengals', 'city': 'Cincinnati'},
    'CLE': {'abbr': 'CLE', 'name': 'Cleveland Browns', 'city': 'Cleveland'},
    'DAL': {'abbr': 'DAL', 'name': 'Dallas Cowboys', 'city': 'Dallas'},
    'DEN': {'abbr': 'DEN', 'name': 'Denver Broncos', 'city': 'Denver'},
    'DET': {'abbr': 'DET', 'name': 'Detroit Lions', 'city': 'Detroit'},
    'GB': {'abbr': 'GB', 'name': 'Green Bay Packers', 'city': 'Green Bay'},
    'HOU': {'abbr': 'HOU', 'name': 'Houston Texans', 'city': 'Houston'},
    'IND': {'abbr': 'IND', 'name': 'Indianapolis Colts', 'city': 'Indianapolis'},
    'JAX': {'abbr': 'JAX', 'name': 'Jacksonville Jaguars', 'city': 'Jacksonville'},
    'KC': {'abbr': 'KC', 'name': 'Kansas City Chiefs', 'city': 'Kansas City'},
    'LAC': {'abbr': 'LAC', 'name': 'Los Angeles Chargers', 'city': 'Los Angeles'},
    'LAR': {'abbr': 'LAR', 'name': 'Los Angeles Rams', 'city': 'Los Angeles'},
    'LV': {'abbr': 'LV', 'name': 'Las Vegas Raiders', 'city': 'Las Vegas'},
    'MIA': {'abbr': 'MIA', 'name': 'Miami Dolphins', 'city': 'Miami'},
    'MIN': {'abbr': 'MIN', 'name': 'Minnesota Vikings', 'city': 'Minnesota'},
    'NE': {'abbr': 'NE', 'name': 'New England Patriots', 'city': 'New England'},
    'NO': {'abbr': 'NO', 'name': 'New Orleans Saints', 'city': 'New Orleans'},
    'NYG': {'abbr': 'NYG', 'name': 'New York Giants', 'city': 'New York'},
    'NYJ': {'abbr': 'NYJ', 'name': 'New York Jets', 'city': 'New York'},
    'PHI': {'abbr': 'PHI', 'name': 'Philadelphia Eagles', 'city': 'Philadelphia'},
    'PIT': {'abbr': 'PIT', 'name': 'Pittsburgh Steelers', 'city': 'Pittsburgh'},
    'SEA': {'abbr': 'SEA', 'name': 'Seattle Seahawks', 'city': 'Seattle'},
    'SF': {'abbr': 'SF', 'name': 'San Francisco 49ers', 'city': 'San Francisco'},
    'TB': {'abbr': 'TB', 'name': 'Tampa Bay Buccaneers', 'city': 'Tampa Bay'},
    'TEN': {'abbr': 'TEN', 'name': 'Tennessee Titans', 'city': 'Tennessee'},
    'WAS': {'abbr': 'WAS', 'name': 'Washington Commanders', 'city': 'Washington'}
}
```

#### Play Type Standardization
```python
play_type_mapping = {
    'pass': 'pass',
    'run': 'run', 
    'punt': 'punt',
    'field_goal': 'field_goal',
    'extra_point': 'extra_point',
    'kickoff': 'kickoff',
    'qb_kneel': 'kneel',
    'qb_spike': 'spike',
    'no_play': 'penalty',
    None: 'unknown'
}
```

#### Formation Standardization
```python
formation_mapping = {
    'SHOTGUN': 'shotgun',
    'SINGLEBACK': 'singleback', 
    'I_FORM': 'i_formation',
    'PISTOL': 'pistol',
    'WILDCAT': 'wildcat',
    'JUMBO': 'jumbo',
    'EMPTY': 'empty_backfield',
    None: 'unknown'
}
```

---

**Document Control:**
- **Version**: 1.0
- **Last Modified**: March 4, 2026
- **Next Review**: June 4, 2026
- **Owner**: Data Engineering Team
- **Approvers**: Data Architecture, NFL Analytics Team

**Change Log:**
- v1.0 (2026-03-04): Initial comprehensive data dictionary created for NFL game prediction model