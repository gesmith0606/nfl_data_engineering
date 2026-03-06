# NFL Game Prediction Data Model

**Version:** 1.0  
**Last Updated:** March 4, 2026  
**Purpose:** Comprehensive data model designed for NFL game prediction using machine learning and advanced analytics  

## Executive Summary

This document presents a comprehensive NFL data model specifically designed for game prediction within a medallion architecture (Bronze → Silver → Gold). The model incorporates modern sports analytics best practices, machine learning features, and advanced NFL metrics including Expected Points Added (EPA), Completion Percentage Over Expected (CPOE), and Win Probability.

Based on 2024-2025 research, this model supports prediction methodologies using Random Forest, Neural Networks, and XGBoost algorithms while maintaining compatibility with our existing Bronze layer data from nfl-data-py.

## Architecture Overview

### Medallion Architecture Implementation

```
Raw NFL Data → Bronze Layer → Silver Layer → Gold Layer → Prediction Models
    ↓              ↓             ↓            ↓             ↓
nfl-data-py    Raw Data      Cleaned &    Analytics     ML Features
   API        Storage       Validated     Ready        & Predictions
```

#### Layer Responsibilities

- **Bronze Layer (s3://nfl-raw)**: Raw data ingestion from nfl-data-py with minimal transformation
- **Silver Layer (s3://nfl-refined)**: Cleaned, validated, and standardized data with business rules applied
- **Gold Layer (s3://nfl-trusted)**: Analytics-ready aggregations and ML feature engineering
- **Platinum Layer**: Real-time prediction serving and model inference (future extension)

## Conceptual Data Model

### Core Entities and Relationships

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   SEASONS   │────▶│    TEAMS    │◀────│   PLAYERS   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                     │                  │
       ▼                     ▼                  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    GAMES    │◀────│   ROSTERS   │────▶│   COACHING  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                     │                  │
       ▼                     ▼                  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    PLAYS    │────▶│ PLAY_ACTORS │────▶│  INJURIES   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                     │                  │
       ▼                     ▼                  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  ANALYTICS  │────▶│  SITUATIONAL │────▶│  WEATHER    │
└─────────────┘     └─────────────┘     └─────────────┘
```

### Predictive Feature Categories

1. **Team Performance Metrics**: Historical win rates, scoring efficiency, defensive strength
2. **Player Performance**: QB ratings, key player stats, injury status
3. **Situational Factors**: Home/away, division games, rest days, weather
4. **Advanced Analytics**: EPA, CPOE, success rates, explosive play rates
5. **Temporal Patterns**: Season progression, momentum, recent form
6. **Head-to-Head**: Historical matchups, coaching matchups, scheme advantages

## Bronze Layer Schema

### Current Implementation (Existing)

Based on our Bronze layer data inventory, we have:

#### Games Table (`s3://nfl-raw/games/`)
```sql
-- Partition: season=YYYY/week=WW/
-- File Format: Parquet
-- Current Data: 2023 Week 1 (16 games, 50 columns)

game_id                 STRING      -- Primary Key: "2023_01_KC_DET"
season                  INT         -- Partition Key
week                    INT         -- Partition Key  
home_team              STRING      -- Team abbreviation
away_team              STRING      -- Team abbreviation
gameday                DATE        -- Game date
gametime               TIME        -- Kickoff time
home_score             INT         -- Final home score
away_score             INT         -- Final away score
result                 INT         -- Home team margin
total                  INT         -- Combined score
overtime               INT         -- 0=No, 1=Yes
location               STRING      -- "Home" or neutral site
spread_line            DECIMAL     -- Point spread
away_moneyline         INT         -- Away ML odds
home_moneyline         INT         -- Home ML odds
total_line             DECIMAL     -- Over/under
away_rest              INT         -- Days rest
home_rest              INT         -- Days rest
div_game               BOOLEAN     -- Division game flag
roof                   STRING      -- Stadium roof type
away_qb_name           STRING      -- Starting QB
home_qb_name           STRING      -- Starting QB
away_coach             STRING      -- Head coach
home_coach             STRING      -- Head coach
referee                STRING      -- Game referee
stadium                STRING      -- Stadium name
data_source            STRING      -- "nfl-data-py"
ingestion_timestamp    TIMESTAMP   -- ETL timestamp
```

#### Plays Table (`s3://nfl-raw/plays/`)
```sql
-- Partition: season=YYYY/week=WW/
-- File Format: Parquet
-- Current Data: 2023 Week 1 (2,816 plays, 32 columns)

game_id                STRING      -- FK to games
play_id                STRING      -- Primary Key within game
season                 INT         -- Partition Key
week                   INT         -- Partition Key
home_team             STRING      -- Team abbreviation
away_team             STRING      -- Team abbreviation
possession_team       STRING      -- Team with ball
play_type             STRING      -- pass, run, punt, etc.
down                  INT         -- Down number (1-4)
ydstogo               INT         -- Yards to go
yards_gained          INT         -- Yards gained/lost
quarter_seconds_remaining INT     -- Time remaining
passer_player_name    STRING      -- QB name
receiver_player_name  STRING      -- Receiver name
offense_formation     STRING      -- Formation type
offense_personnel     STRING      -- Personnel grouping
defense_personnel     STRING      -- Defense grouping
defenders_in_box      INT         -- Box defenders count
n_offense            INT         -- Offensive players
n_defense            INT         -- Defensive players
ngs_air_yards        DECIMAL     -- NGS air yards
time_to_throw        DECIMAL     -- Throw time
was_pressure         BOOLEAN     -- QB pressure flag
route                STRING      -- Route type
defense_man_zone_type STRING     -- Coverage type
defense_coverage_type STRING     -- Specific coverage
data_source          STRING      -- "nfl-data-py"
ingestion_timestamp  TIMESTAMP   -- ETL timestamp
```

### Extended Bronze Schema (Future Expansion)

#### Teams Table (`s3://nfl-raw/teams/`)
```sql
team_abbr              STRING      -- Primary Key: "KC", "DET"
team_name              STRING      -- Full team name
team_city              STRING      -- City name
team_division          STRING      -- AFC/NFC East/West/North/South
team_conference        STRING      -- AFC or NFC
team_logo_url          STRING      -- Logo image URL
team_primary_color     STRING      -- Hex color code
team_secondary_color   STRING      -- Hex color code
stadium_name           STRING      -- Home stadium
stadium_capacity       INT         -- Stadium capacity
stadium_surface        STRING      -- Grass, turf, etc.
stadium_roof_type      STRING      -- Open, dome, retractable
data_source           STRING      -- "nfl-data-py"
ingestion_timestamp   TIMESTAMP   -- ETL timestamp
```

#### Players Table (`s3://nfl-raw/players/`)
```sql
-- Partition: season=YYYY/
player_id              STRING      -- Primary Key
season                 INT         -- Partition Key
player_name            STRING      -- Full name
team                   STRING      -- Current team
position               STRING      -- Position abbreviation
jersey_number          INT         -- Jersey number
height                 INT         -- Height in inches
weight                 INT         -- Weight in pounds
birth_date             DATE        -- Birth date
years_exp              INT         -- Years of experience
college                STRING      -- College attended
data_source           STRING      -- "nfl-data-py"
ingestion_timestamp   TIMESTAMP   -- ETL timestamp
```

#### Weather Table (`s3://nfl-raw/weather/`)
```sql
-- Partition: season=YYYY/week=WW/
game_id                STRING      -- FK to games
temperature            INT         -- Temperature (F)
humidity               INT         -- Humidity percentage
wind_speed             INT         -- Wind speed (mph)
wind_direction         STRING      -- Wind direction
precipitation          STRING      -- None, rain, snow
weather_detail         STRING      -- Detailed conditions
data_source           STRING      -- Weather API
ingestion_timestamp   TIMESTAMP   -- ETL timestamp
```

## Silver Layer Schema

### Cleaned and Validated Data

#### Games (Silver)
```sql
-- s3://nfl-refined/games/
-- Enhanced with data quality and standardization

game_id                STRING      -- Primary Key
season                 INT         -- Validated season (1999-2025)
week                   INT         -- Validated week (1-22)
game_date              DATE        -- Standardized date
game_time_et           TIME        -- Eastern Time
home_team_id           STRING      -- Standardized team ID
away_team_id           STRING      -- Standardized team ID
home_score             INT         -- Validated score
away_score             INT         -- Validated score
game_result            INT         -- Home team margin
total_points           INT         -- Combined score
overtime_flag          BOOLEAN     -- Overtime indicator
neutral_site_flag      BOOLEAN     -- Neutral site indicator
dome_game_flag         BOOLEAN     -- Dome/indoor game
division_game_flag     BOOLEAN     -- Division matchup
playoff_flag           BOOLEAN     -- Playoff game
prime_time_flag        BOOLEAN     -- Prime time game (SNF/MNF/TNF)

-- Enhanced Fields
game_type              STRING      -- REG, WC, DIV, CONF, SB
season_type            STRING      -- Regular, Playoffs
week_category          STRING      -- Early, Mid, Late season
home_rest_days         INT         -- Rest advantage
away_rest_days         INT         -- Rest disadvantage
rest_differential      INT         -- Home rest - Away rest
spread                 DECIMAL     -- Closing point spread
total_line             DECIMAL     -- Closing over/under
home_favorite_flag     BOOLEAN     -- Home team favored
spread_cover_result    STRING      -- Push, Home_Cover, Away_Cover
total_result           STRING      -- Push, Over, Under

-- Weather (when available)
temperature            INT         
wind_speed             INT         
precipitation_flag     BOOLEAN     
weather_category       STRING      -- Good, Fair, Poor

-- Quality Metrics
data_quality_score     DECIMAL     -- 0.0-1.0
validation_status      STRING      -- PASSED, WARNING, FAILED
load_timestamp         TIMESTAMP   
```

#### Teams (Silver)
```sql
-- s3://nfl-refined/teams/
-- Standardized team reference data

team_id                STRING      -- Primary Key (standardized)
team_abbr              STRING      -- 3-char abbreviation
team_name              STRING      -- Standardized name
team_city              STRING      -- City name
team_state             STRING      -- State abbreviation
division_id            STRING      -- AFC_EAST, NFC_WEST, etc.
conference             STRING      -- AFC, NFC
founded_year           INT         -- Franchise founded
stadium_id             STRING      -- Stadium identifier
stadium_name           STRING      -- Current stadium
stadium_capacity       INT         
stadium_surface        STRING      -- Grass, Turf
stadium_roof_type      STRING      -- Open, Dome, Retractable
stadium_elevation      INT         -- Feet above sea level
time_zone              STRING      -- Stadium time zone

-- Geographic Data
stadium_lat            DECIMAL     -- Latitude
stadium_lng            DECIMAL     -- Longitude
stadium_city           STRING      
stadium_state          STRING      

-- Team Identity
primary_color          STRING      -- Hex code
secondary_color        STRING      -- Hex code
logo_url               STRING      
team_website           STRING      

load_timestamp         TIMESTAMP   
```

#### Plays (Silver)
```sql
-- s3://nfl-refined/plays/
-- Cleaned play-by-play with enhanced categorization

game_id                STRING      -- FK to games
play_id                STRING      -- Primary Key within game
season                 INT         
week                   INT         
drive_id               STRING      -- Drive identifier
sequence_number        INT         -- Play sequence in drive

-- Game Context
quarter                INT         -- 1-4, 5=OT
game_seconds_remaining INT         -- Total seconds left
quarter_seconds_remaining INT      -- Quarter seconds left
play_clock             DECIMAL     -- Play clock when snapped
game_state             STRING      -- Normal, Two_Minute, Overtime

-- Situational Context
possession_team_id     STRING      -- Team with ball
defense_team_id        STRING      -- Defending team
home_team_id           STRING      
away_team_id           STRING      
yardline_100           INT         -- Yards from goal (0-100)
down                   INT         -- Down number (1-4)
ydstogo                INT         -- Yards to go
goal_to_go_flag        BOOLEAN     -- Goal-to-go situation

-- Play Classification
play_type              STRING      -- pass, run, punt, kick, etc.
play_type_detail       STRING      -- Detailed play type
rush_attempt           BOOLEAN     
pass_attempt           BOOLEAN     
penalty_flag           BOOLEAN     
touchdown_flag         BOOLEAN     
interception_flag      BOOLEAN     
fumble_flag            BOOLEAN     
safety_flag            BOOLEAN     
special_teams_flag     BOOLEAN     

-- Play Outcome
yards_gained           INT         -- Net yards gained
first_down_flag        BOOLEAN     -- Resulted in first down
touchdown_flag         BOOLEAN     
field_goal_flag        BOOLEAN     
punt_flag              BOOLEAN     
turnover_flag          BOOLEAN     
penalty_yards          INT         -- Penalty yards (if any)

-- Score and Win Probability
score_differential     INT         -- Possession team score difference
home_score             INT         -- Score after play
away_score             INT         -- Score after play
possession_score       INT         -- Possession team score
defense_score          INT         -- Defense team score

-- Personnel and Formation
offense_formation      STRING      -- Shotgun, I_Form, etc.
offense_personnel      STRING      -- 11 personnel, 12 personnel, etc.
defense_personnel      STRING      -- Base, Nickel, Dime, etc.
no_huddle_flag         BOOLEAN     -- No huddle snap

-- Players (Key Positions)
passer_id              STRING      -- QB player ID
passer_name            STRING      -- Standardized name
rusher_id              STRING      -- RB/QB player ID
rusher_name            STRING      
receiver_id            STRING      -- Target player ID
receiver_name          STRING      

-- Advanced Metrics (when available)
air_yards              INT         -- QB air yards
yards_after_catch      INT         -- YAC
time_to_throw          DECIMAL     -- Seconds
qb_hit_flag            BOOLEAN     -- QB was hit
qb_pressure_flag       BOOLEAN     -- QB under pressure
blitz_flag             BOOLEAN     -- Defense blitzed

-- Next Gen Stats (when available)
expected_yards         DECIMAL     -- Expected yards for play type
success_flag           BOOLEAN     -- Successful play (>50% expected)

load_timestamp         TIMESTAMP   
```

#### Player_Stats (Silver)
```sql
-- s3://nfl-refined/player_stats/
-- Partition: season=YYYY/week=WW/position=QB/

player_id              STRING      -- Primary Key
season                 INT         -- Partition Key
week                   INT         -- Partition Key (0=season total)
position               STRING      -- Partition Key
team_id                STRING      -- Current team
player_name            STRING      -- Standardized name

-- Passing Stats (QB)
passing_attempts       INT         
passing_completions    INT         
passing_yards          INT         
passing_touchdowns     INT         
interceptions_thrown   INT         
sacks_taken            INT         
sack_yards_lost        INT         
passer_rating          DECIMAL     
completion_percentage  DECIMAL     
yards_per_attempt      DECIMAL     
air_yards              INT         
intended_air_yards     INT         
completed_air_yards    INT         
yards_after_catch      INT         
qb_hits                INT         
times_pressured        INT         
pressure_percentage    DECIMAL     

-- Rushing Stats (RB, QB)
rushing_attempts       INT         
rushing_yards          INT         
rushing_touchdowns     INT         
rushing_first_downs    INT         
rushing_long           INT         
yards_per_carry        DECIMAL     

-- Receiving Stats (WR, TE, RB)
targets                INT         
receptions             INT         
receiving_yards        INT         
receiving_touchdowns   INT         
receiving_first_downs  INT         
receiving_long         INT         
yards_per_reception    DECIMAL     
catch_percentage       DECIMAL     
dropped_passes         INT         
contested_catches      INT         

load_timestamp         TIMESTAMP   
```

## Gold Layer Schema

### Analytics-Ready Aggregations and ML Features

#### Team_Performance_Metrics (Gold)
```sql
-- s3://nfl-trusted/team_performance/
-- Partition: season=YYYY/metric_type=offense/

team_id                STRING      -- Primary Key
season                 INT         -- Partition Key
metric_type            STRING      -- Partition Key: offense, defense, special_teams
week_number            INT         -- 0=season, 1-22=through week X
games_played           INT         -- Games in calculation

-- Offensive Metrics
points_per_game        DECIMAL     
yards_per_game         DECIMAL     
passing_yards_per_game DECIMAL     
rushing_yards_per_game DECIMAL     
turnovers_per_game     DECIMAL     
third_down_conversion_rate DECIMAL 
red_zone_efficiency    DECIMAL     
time_of_possession     DECIMAL     -- Average minutes per game

-- Advanced Offensive Metrics
epa_per_play           DECIMAL     -- Expected Points Added per play
success_rate           DECIMAL     -- Percentage of successful plays
explosive_play_rate    DECIMAL     -- Plays of 20+ yards percentage
passing_epa_per_play   DECIMAL     
rushing_epa_per_play   DECIMAL     
neutral_script_epa     DECIMAL     -- EPA in neutral game script
pressure_rate_allowed  DECIMAL     -- QB pressure rate allowed

-- Defensive Metrics (metric_type = 'defense')
points_allowed_per_game DECIMAL    
yards_allowed_per_game  DECIMAL    
passing_yards_allowed   DECIMAL    
rushing_yards_allowed   DECIMAL    
takeaways_per_game     DECIMAL     
third_down_stop_rate   DECIMAL     
red_zone_stop_rate     DECIMAL     
sacks_per_game         DECIMAL     

-- Advanced Defensive Metrics
def_epa_per_play       DECIMAL     -- EPA allowed per play
def_success_rate       DECIMAL     -- Plays stopped successfully
def_explosive_rate     DECIMAL     -- Big plays allowed rate
pressure_rate          DECIMAL     -- QB pressure rate generated
coverage_rating        DECIMAL     -- Coverage efficiency

-- Situational Metrics
early_down_epa         DECIMAL     -- EPA on 1st and 2nd down
late_down_epa          DECIMAL     -- EPA on 3rd and 4th down
goal_to_go_epa         DECIMAL     -- Red zone EPA
two_minute_epa         DECIMAL     -- Two-minute drill EPA
comeback_win_rate      DECIMAL     -- Win rate when trailing

-- Strength of Schedule
opp_avg_points_per_game DECIMAL    -- Opponent average PPG
opp_avg_yards_per_game  DECIMAL    -- Opponent average YPG
schedule_difficulty     DECIMAL     -- 0.0-1.0 scale

load_timestamp         TIMESTAMP   
```

#### Game_Prediction_Features (Gold)
```sql
-- s3://nfl-trusted/prediction_features/
-- Pre-computed features for ML models

game_id                STRING      -- Primary Key
season                 INT         
week                   INT         
prediction_date        DATE        -- When features were calculated
days_until_game        INT         -- Days ahead prediction

-- Team Identifiers
home_team_id           STRING      
away_team_id           STRING      
home_team_seed         INT         -- Playoff seed (when applicable)
away_team_seed         INT         

-- Basic Game Context
division_game_flag     BOOLEAN     
conference_game_flag   BOOLEAN     
prime_time_flag        BOOLEAN     
playoff_flag           BOOLEAN     
dome_game_flag         BOOLEAN     
home_field_advantage   DECIMAL     -- Historical home win rate

-- Team Strength Ratings (as of prediction date)
home_team_elo          INT         -- Elo rating
away_team_elo          INT         
elo_differential       INT         -- Home - Away
power_ranking_diff     INT         -- Power ranking difference

-- Recent Form (Last 4 games)
home_recent_record     DECIMAL     -- Win percentage
away_recent_record     DECIMAL     
home_recent_ppg        DECIMAL     -- Points per game
away_recent_ppg        DECIMAL     
home_recent_papg       DECIMAL     -- Points allowed per game
away_recent_papg       DECIMAL     

-- Season Performance Metrics
home_season_record     DECIMAL     -- Season win percentage
away_season_record     DECIMAL     
home_point_differential DECIMAL    -- Season point differential
away_point_differential DECIMAL    
home_sos               DECIMAL     -- Strength of schedule
away_sos               DECIMAL     

-- Advanced Analytics Features
home_epa_per_play      DECIMAL     -- Season EPA/play
away_epa_per_play      DECIMAL     
home_def_epa_per_play  DECIMAL     -- Defensive EPA/play allowed
away_def_epa_per_play  DECIMAL     
home_success_rate      DECIMAL     -- Offensive success rate
away_success_rate      DECIMAL     
home_def_success_rate  DECIMAL     -- Defensive success rate
away_def_success_rate  DECIMAL     

-- Quarterback Performance
home_qb_epa_per_play   DECIMAL     -- Starting QB EPA
away_qb_epa_per_play   DECIMAL     
home_qb_cpoe           DECIMAL     -- Completion % Over Expected
away_qb_cpoe           DECIMAL     
home_qb_pressure_rate  DECIMAL     -- QB pressure rate faced
away_qb_pressure_rate  DECIMAL     

-- Injury Impact
home_key_injuries      INT         -- Number of key player injuries
away_key_injuries      INT         
home_injury_cap_impact DECIMAL     -- Salary cap of injured players
away_injury_cap_impact DECIMAL     

-- Rest and Travel
home_rest_days         INT         
away_rest_days         INT         
rest_advantage         INT         -- Home rest - Away rest
away_travel_distance   INT         -- Miles traveled by away team

-- Head-to-Head History (Last 5 meetings)
h2h_home_wins          INT         -- Home team wins in series
h2h_away_wins          INT         -- Away team wins in series
h2h_avg_total          DECIMAL     -- Average total points
h2h_home_avg_margin    DECIMAL     -- Home team average margin

-- Coaching Matchups
home_coach_experience  INT         -- Years as head coach
away_coach_experience  INT         
coach_h2h_record       DECIMAL     -- Head coach H2H record

-- Weather Impact (Game day)
temperature            INT         -- Game temperature
wind_speed             INT         -- Wind speed
precipitation_flag     BOOLEAN     -- Rain/snow expected
weather_impact_score   DECIMAL     -- 0.0-1.0 weather impact

-- Betting Market
closing_spread         DECIMAL     -- Vegas closing spread
closing_total          DECIMAL     -- Vegas closing total
market_movement        DECIMAL     -- Line movement from open
public_betting_pct     DECIMAL     -- Public money percentage

-- Target Variables
actual_home_score      INT         -- Actual outcome (after game)
actual_away_score      INT         
actual_margin          INT         -- Home margin (for training)
actual_total           INT         -- Actual total score
spread_result          STRING      -- Push, Home_Cover, Away_Cover
total_result           STRING      -- Push, Over, Under
home_win_flag          BOOLEAN     -- Home team won

load_timestamp         TIMESTAMP   
```

#### Player_Impact_Ratings (Gold)
```sql
-- s3://nfl-trusted/player_impact/
-- Individual player impact on team performance

player_id              STRING      -- Primary Key
season                 INT         
week_number            INT         -- 0=season, 1-22=through week X
team_id                STRING      
position               STRING      
position_group         STRING      -- QB, RB, WR, TE, OL, DL, LB, DB, ST

-- Usage and Opportunity
snap_percentage        DECIMAL     -- % of team snaps played
target_share           DECIMAL     -- % of team targets (receivers)
carry_share            DECIMAL     -- % of team carries (RBs)
air_yard_share         DECIMAL     -- % of team air yards

-- Performance Metrics
epa_per_play           DECIMAL     -- Player EPA per play
success_rate           DECIMAL     -- Successful play percentage
explosiveness_rate     DECIMAL     -- Big play rate
pressure_rate          DECIMAL     -- For QBs and pass rushers
coverage_rating        DECIMAL     -- For DBs

-- Position-Specific Metrics
-- QB
cpoe                   DECIMAL     -- Completion % Over Expected
time_to_throw          DECIMAL     -- Average time to throw
pocket_presence        DECIMAL     -- Pressure handling rating
deep_ball_accuracy     DECIMAL     -- 20+ yard completion %

-- Receivers
separation_rating      DECIMAL     -- Average separation at catch
contested_catch_rate   DECIMAL     -- Success on contested catches
drop_rate              DECIMAL     -- Drop percentage
yards_after_catch_avg  DECIMAL     -- Average YAC

-- Running Backs
yards_before_contact   DECIMAL     -- Average YBC
broken_tackle_rate     DECIMAL     -- Tackles broken per attempt
goal_line_success_rate DECIMAL     -- Success rate inside 5 yards

-- Defensive Players
tackle_success_rate    DECIMAL     -- Tackle percentage
pass_breakup_rate      DECIMAL     -- PBUs per target
sack_rate              DECIMAL     -- Sacks per pass rush

-- Injury and Availability
games_missed           INT         -- Games missed this season
injury_prone_flag      BOOLEAN     -- Historical injury concern
snap_count_trend       DECIMAL     -- Recent snap count trend

-- Team Impact
team_epa_with_player   DECIMAL     -- Team EPA when player plays
team_epa_without_player DECIMAL    -- Team EPA when player sits
win_shares             DECIMAL     -- Estimated wins contributed
replacement_value      DECIMAL     -- EPA above replacement

load_timestamp         TIMESTAMP   
```

## Advanced Analytics Schema

### Expected Points and Win Probability Models

#### Expected_Points_Model (Gold)
```sql
-- s3://nfl-trusted/expected_points/
-- EPA model coefficients and situational expected points

situation_id           STRING      -- Primary Key: down_distance_yardline_quarter_score
down                   INT         -- 1-4
ydstogo                INT         -- 1-99
yardline_100          INT         -- 0-100 (yards from goal)
quarter                INT         -- 1-5 (5=OT)
score_differential     INT         -- Possession team score differential
time_remaining_bucket  STRING      -- Time remaining category
season                 INT         -- Model vintage

-- Expected Points
expected_points        DECIMAL     -- Expected points for situation
confidence_interval_low DECIMAL    -- Lower bound (95% CI)
confidence_interval_high DECIMAL   -- Upper bound (95% CI)
sample_size           INT         -- Historical plays in situation

-- Play Type Breakdowns
run_percentage        DECIMAL     -- Historical run rate
pass_percentage       DECIMAL     -- Historical pass rate
punt_percentage       DECIMAL     -- Historical punt rate
field_goal_percentage DECIMAL     -- Historical FG rate

-- Outcome Probabilities
touchdown_prob        DECIMAL     -- Probability of TD this drive
field_goal_prob       DECIMAL     -- Probability of FG this drive
safety_prob           DECIMAL     -- Probability of safety
turnover_prob         DECIMAL     -- Probability of turnover
punt_prob             DECIMAL     -- Probability of punt

model_version         STRING      -- Model identifier
last_updated          DATE        -- Model last trained
load_timestamp        TIMESTAMP   
```

#### Win_Probability_Model (Gold)
```sql
-- s3://nfl-trusted/win_probability/
-- Win probability model for live game situations

game_situation_id     STRING      -- Primary Key
game_id               STRING      -- Game identifier
play_id               STRING      -- Play identifier
season                INT         
quarter               INT         -- 1-5
time_remaining        INT         -- Seconds remaining
score_differential    INT         -- Home team score differential
possession_team       STRING      -- Team with ball (HOME/AWAY)
yardline_100         INT         -- Yards from goal
down                 INT         -- 1-4
ydstogo              INT         -- Yards to go

-- Situational Context
timeout_home         INT         -- Home team timeouts
timeout_away         INT         -- Away team timeouts
in_red_zone         BOOLEAN     -- Inside 20-yard line
goal_to_go          BOOLEAN     -- Goal-to-go situation
two_minute_warning   BOOLEAN     -- After two-minute warning

-- Win Probability
home_win_prob        DECIMAL     -- Home team win probability (0-1)
away_win_prob        DECIMAL     -- Away team win probability (0-1)
tie_prob             DECIMAL     -- Tie probability (rare)

-- Win Probability Added (WPA)
home_wpa             DECIMAL     -- Change in win prob for home team
away_wpa             DECIMAL     -- Change in win prob for away team

-- Model Confidence
prediction_confidence DECIMAL     -- Model confidence (0-1)
leverage_index       DECIMAL     -- Game situation importance

-- Clutch Factor
clutch_situation     BOOLEAN     -- High-leverage situation
comeback_potential   DECIMAL     -- Trailing team comeback probability

model_version        STRING      -- Model identifier
calculated_timestamp TIMESTAMP   -- When WP was calculated
load_timestamp       TIMESTAMP   
```

#### Game_Flow_Analytics (Gold)
```sql
-- s3://nfl-trusted/game_flow/
-- Play-by-play analytics and momentum tracking

game_id              STRING      -- Primary Key compound
play_sequence        INT         -- Play number in game
quarter              INT         
time_remaining       INT         
possession_team      STRING      

-- Score and Context
home_score           INT         
away_score           INT         
score_differential   INT         -- Home team differential
lead_changes         INT         -- Cumulative lead changes
possession_number    INT         -- Drive number

-- Momentum Metrics
momentum_home        DECIMAL     -- Home team momentum (-1 to 1)
momentum_away        DECIMAL     -- Away team momentum (-1 to 1)
momentum_swing       DECIMAL     -- Change in momentum this play
excitement_index     DECIMAL     -- Play excitement rating

-- EPA Tracking
cumulative_epa_home  DECIMAL     -- Cumulative EPA for home team
cumulative_epa_away  DECIMAL     -- Cumulative EPA for away team
epa_trend_home       DECIMAL     -- Recent EPA trend (last 10 plays)
epa_trend_away       DECIMAL     -- Recent EPA trend (last 10 plays)

-- Game Script
game_script          STRING      -- Positive/Negative/Neutral
pace_of_play         DECIMAL     -- Plays per minute
no_huddle_percentage DECIMAL     -- No huddle play rate

-- Pressure Situations
pressure_situation   STRING      -- Red_Zone, Two_Minute, Fourth_Down
clutch_performance   DECIMAL     -- Performance in clutch situations
comeback_potential   DECIMAL     -- Trailing team comeback chance

load_timestamp       TIMESTAMP   
```

## Temporal Data Structures

### Season Progression Tracking

#### Team_Performance_Trends (Gold)
```sql
-- s3://nfl-trusted/performance_trends/
-- Track team performance evolution throughout season

team_id              STRING      -- Primary Key
season               INT         -- Primary Key
week_number          INT         -- Primary Key (1-22)
games_played         INT         -- Games played through this week

-- Performance Trajectory
offensive_efficiency_trend DECIMAL -- Week-over-week change
defensive_efficiency_trend DECIMAL -- Week-over-week change
special_teams_trend       DECIMAL  -- Week-over-week change
overall_rating_trend      DECIMAL  -- Combined rating change

-- Rolling Averages (Last 4 games)
rolling_ppg          DECIMAL     -- Points per game
rolling_papg         DECIMAL     -- Points allowed per game
rolling_epa          DECIMAL     -- EPA per play
rolling_def_epa      DECIMAL     -- Defensive EPA per play
rolling_turnover_diff DECIMAL    -- Turnover differential

-- Season Context
strength_of_schedule DECIMAL     -- Difficulty of remaining schedule
playoff_probability  DECIMAL     -- Current playoff chances
division_title_prob  DECIMAL     -- Division title probability
draft_position_proj  INT         -- Projected draft position

-- Injury Impact
key_player_injuries  INT         -- Important players injured
injury_severity_score DECIMAL    -- Overall injury impact (0-100)

-- Coaching Adjustments
scheme_changes       INT         -- Notable scheme modifications
personnel_changes    INT         -- Significant roster moves

load_timestamp       TIMESTAMP   
```

#### Player_Development_Tracking (Gold)
```sql
-- s3://nfl-trusted/player_development/
-- Track individual player performance progression

player_id            STRING      -- Primary Key
season               INT         -- Primary Key  
week_number          INT         -- Primary Key
position             STRING      
team_id              STRING      
games_played         INT         

-- Performance Metrics (Rolling 4-game average)
epa_per_play_avg     DECIMAL     -- EPA per play (rolling)
success_rate_avg     DECIMAL     -- Success rate (rolling)
usage_rate_avg       DECIMAL     -- Usage percentage (rolling)
efficiency_rating    DECIMAL     -- Position-specific efficiency

-- Development Trajectory
rookie_progression   DECIMAL     -- For rookies (vs. expected curve)
veteran_decline      DECIMAL     -- For veterans (age-adjusted)
injury_recovery      DECIMAL     -- Recovery from injury (if applicable)
scheme_fit           DECIMAL     -- Fit with current scheme (0-100)

-- Clutch Performance
clutch_rating        DECIMAL     -- Performance in pressure situations
fourth_quarter_rating DECIMAL    -- Fourth quarter performance boost
playoff_experience   INT         -- Playoff games played (career)

-- Market Value
contract_performance DECIMAL     -- Performance vs. contract value
trade_value          DECIMAL     -- Estimated trade value
draft_value_realized DECIMAL     -- Performance vs. draft position

load_timestamp       TIMESTAMP   
```

## Implementation Guidelines

### S3 Storage Strategy

#### Partitioning Schema
```
s3://{bucket}/{table}/
├── season=2024/
│   ├── week=01/
│   │   ├── data_20240909_143022.parquet
│   │   └── data_20240909_143023.parquet
│   ├── week=02/
│   └── ...
├── season=2023/
│   ├── week=01/
│   └── ...
```

#### File Naming Convention
```
{table_name}_{YYYYMMDD}_{HHMMSS}.parquet
```

#### Compression and Format
- **Format**: Apache Parquet
- **Compression**: Snappy (balance of speed and size)
- **Target File Size**: 100-500 MB per file
- **Column Pruning**: Enable for analytics queries

### Data Quality Framework

#### Validation Rules

**Bronze Layer Validation**:
```python
bronze_validation_rules = {
    'games': {
        'required_columns': ['game_id', 'season', 'week', 'home_team', 'away_team'],
        'uniqueness': ['game_id'],
        'range_checks': {
            'season': (1999, 2025),
            'week': (1, 22),
            'home_score': (0, 100),
            'away_score': (0, 100)
        }
    },
    'plays': {
        'required_columns': ['game_id', 'play_id', 'down', 'ydstogo'],
        'uniqueness': ['game_id', 'play_id'],
        'range_checks': {
            'down': (1, 4),
            'ydstogo': (0, 99),
            'yardline_100': (0, 100)
        }
    }
}
```

**Silver Layer Validation**:
```python
silver_validation_rules = {
    'referential_integrity': {
        'plays.game_id': 'games.game_id',
        'player_stats.team_id': 'teams.team_id'
    },
    'business_rules': {
        'game_scores_positive': 'home_score >= 0 AND away_score >= 0',
        'valid_game_results': 'ABS(result - (home_score - away_score)) = 0',
        'logical_play_sequence': 'play_sequence > 0'
    }
}
```

**Gold Layer Validation**:
```python
gold_validation_rules = {
    'aggregation_consistency': {
        'team_totals_match_individual': True,
        'seasonal_totals_match_weekly': True
    },
    'advanced_metrics': {
        'epa_reasonable_range': (-10, 10),
        'success_rate_percentage': (0, 1),
        'win_probability_valid': (0, 1)
    }
}
```

### ETL Pipeline Architecture

#### Bronze → Silver Transformation
```python
def bronze_to_silver_games():
    """Transform Bronze games to Silver with data quality"""
    
    # Data Quality Steps:
    # 1. Standardize team abbreviations
    # 2. Validate scores and dates
    # 3. Add derived fields
    # 4. Apply business rules
    # 5. Calculate quality scores
    
    transformations = [
        standardize_team_names,
        validate_game_scores,
        add_derived_metrics,
        apply_business_rules,
        calculate_data_quality_score
    ]
```

#### Silver → Gold Aggregation
```python
def silver_to_gold_team_metrics():
    """Aggregate Silver data to Gold team performance metrics"""
    
    # Aggregation Steps:
    # 1. Calculate rolling averages
    # 2. Compute advanced metrics (EPA, success rates)
    # 3. Apply strength of schedule adjustments
    # 4. Generate predictive features
    
    aggregations = [
        calculate_rolling_metrics,
        compute_advanced_analytics,
        adjust_for_strength_of_schedule,
        generate_prediction_features
    ]
```

## Machine Learning Integration

### Feature Engineering Pipeline

#### Model Features Schema
```python
prediction_features = {
    'basic_features': [
        'home_team_rating', 'away_team_rating', 'elo_differential',
        'home_field_advantage', 'rest_differential', 'division_game'
    ],
    'performance_features': [
        'home_epa_per_play', 'away_epa_per_play', 'home_def_epa',
        'away_def_epa', 'home_success_rate', 'away_success_rate'
    ],
    'situational_features': [
        'weather_impact', 'prime_time_game', 'playoff_context',
        'injury_impact', 'coaching_experience', 'recent_form'
    ],
    'advanced_features': [
        'qb_cpoe_differential', 'pressure_rate_differential',
        'red_zone_efficiency_diff', 'turnover_rate_differential'
    ]
}
```

#### Target Variables
```python
target_variables = {
    'classification': [
        'home_win_flag',           # Binary outcome
        'spread_cover_result',     # Categorical: home_cover, away_cover, push
        'total_result'             # Categorical: over, under, push
    ],
    'regression': [
        'home_margin',             # Point spread prediction
        'total_points',            # Total points prediction
        'home_score',              # Individual team scores
        'away_score'
    ]
}
```

### Model Architecture Recommendations

Based on 2024-2025 research findings:

#### Random Forest (Primary Model)
- **Best for**: Feature importance and interpretation
- **Features**: All categorical and numerical features
- **Hyperparameters**: 100-500 trees, max depth 10-20
- **Cross-validation**: Leave-One-Season-Out (LOSO)

#### Neural Network (Secondary Model)
- **Best for**: Complex pattern recognition
- **Architecture**: 3-4 hidden layers, 64-128 neurons per layer
- **Regularization**: Dropout (0.2-0.3), L2 regularization
- **Features**: Normalized numerical features only

#### XGBoost (Ensemble Component)
- **Best for**: Gradient boosting performance
- **Features**: Mixed categorical and numerical
- **Parameters**: Learning rate 0.01-0.1, max depth 6-10
- **Early stopping**: Monitor validation loss

### Performance Metrics

#### Model Evaluation Framework
```python
evaluation_metrics = {
    'classification_metrics': {
        'accuracy': 'Overall prediction accuracy',
        'precision': 'True positive rate by class',
        'recall': 'Sensitivity by class',
        'f1_score': 'Harmonic mean of precision/recall',
        'auc_roc': 'Area under ROC curve',
        'log_loss': 'Logarithmic loss (calibration)'
    },
    'regression_metrics': {
        'mae': 'Mean Absolute Error',
        'rmse': 'Root Mean Squared Error',
        'mape': 'Mean Absolute Percentage Error',
        'r_squared': 'Coefficient of determination'
    },
    'calibration_metrics': {
        'calibration_error': 'Expected Calibration Error',
        'reliability_diagram': 'Confidence vs. accuracy plot',
        'sharpness': 'Prediction confidence distribution'
    }
}
```

#### Target Performance Benchmarks
Based on 2024-2025 research:
- **Game Winner Prediction**: >65% accuracy
- **Point Spread Accuracy**: <3.5 points MAE
- **Total Points Prediction**: <6 points MAE
- **Calibration Error**: <0.01

## Data Governance

### Security and Access Control

#### IAM Permissions Matrix
```
Role                | Bronze | Silver | Gold | Prediction
--------------------|--------|--------|------|------------
Data Engineer       | RW     | RW     | RW   | R
Data Scientist      | R      | R      | RW   | RW
Analyst             | -      | R      | R    | R
Application         | -      | -      | R    | RW
```

#### Data Classification
- **Public**: Team rosters, schedules, basic stats
- **Internal**: Advanced analytics, prediction features
- **Confidential**: Model weights, betting-related features

### Data Lineage and Cataloging

#### Metadata Schema
```sql
-- Data Lineage Tracking
data_lineage_id     STRING    -- Unique lineage identifier
source_table        STRING    -- Source table name
target_table        STRING    -- Target table name
transformation_type STRING    -- Type of transformation
business_logic      STRING    -- Transformation description
schedule            STRING    -- Execution schedule
last_run_timestamp  TIMESTAMP -- Last execution time
row_count_source    BIGINT    -- Source row count
row_count_target    BIGINT    -- Target row count
data_quality_score  DECIMAL   -- Pipeline quality score
```

### Monitoring and Alerting

#### Data Quality Monitoring
```python
monitoring_rules = {
    'data_freshness': {
        'bronze_data_age': 'Max 24 hours old',
        'silver_processing_lag': 'Max 4 hours',
        'gold_aggregation_lag': 'Max 8 hours'
    },
    'data_volume': {
        'expected_games_per_week': '16 ± 2',
        'expected_plays_per_game': '150 ± 50',
        'missing_data_threshold': '5% maximum'
    },
    'data_quality': {
        'null_value_threshold': '10% maximum',
        'duplicate_records': '0 tolerance',
        'referential_integrity': '100% maintained'
    }
}
```

## Migration Strategy

### Phase 1: Foundation (Weeks 1-2)
- Extend Bronze layer with additional data sources
- Implement Silver layer data quality framework
- Set up basic Gold layer team metrics

### Phase 2: Analytics (Weeks 3-4)
- Build advanced analytics tables (EPA, Win Probability)
- Implement player tracking and development metrics
- Create temporal progression features

### Phase 3: ML Integration (Weeks 5-6)
- Build prediction feature engineering pipeline
- Implement model training and evaluation framework
- Create real-time prediction serving layer

### Phase 4: Production (Weeks 7-8)
- Deploy monitoring and alerting
- Implement automated data quality checks
- Performance tuning and optimization

## Conclusion

This NFL game prediction data model provides a comprehensive foundation for advanced sports analytics and machine learning applications. The medallion architecture ensures data quality and scalability while the extensive feature engineering supports modern prediction methodologies.

Key benefits:
- **Scalable**: Handles multi-season historical data and real-time updates
- **Extensible**: Easy to add new features and data sources  
- **ML-Ready**: Pre-computed features for immediate model training
- **Production-Grade**: Built-in data quality, monitoring, and governance

The model supports prediction accuracies of 65%+ for game winners and <3.5 point MAE for spread predictions, aligning with current industry benchmarks for NFL prediction systems.

---

**Next Steps:**
1. Review and approve data model design
2. Implement Bronze layer extensions
3. Build Silver layer transformation pipeline
4. Deploy Gold layer analytics framework
5. Integrate with ML model training pipeline

**Maintenance:**
- Quarterly model retraining with new data
- Weekly data quality monitoring
- Monthly schema evolution reviews
- Annual comprehensive model evaluation