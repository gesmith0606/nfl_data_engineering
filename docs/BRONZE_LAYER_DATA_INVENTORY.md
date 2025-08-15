# Bronze Layer Data Inventory

**Last Updated:** August 15, 2025  
**S3 Bucket:** `s3://nfl-raw`  
**Total Size:** 0.21 MB  
**Total Files:** 2

## 📊 Current Data Summary

| Data Type | Season | Week | Records | Columns | Size (MB) | Ingestion Date | File Path |
|-----------|--------|------|---------|---------|-----------|----------------|-----------|
| **Games** | 2023 | 1 | 16 games | 50 | 0.03 | 2025-08-15 19:35 | `games/season=2023/week=1/schedules_20250815_193556.parquet` |
| **Plays** | 2023 | 1 | 2,816 plays | 32 | 0.18 | 2025-08-15 19:36 | `plays/season=2023/week=1/pbp_20250815_193608.parquet` |

## 🏈 Game Data Details (2023 Week 1)

**File:** `games/season=2023/week=1/schedules_20250815_193556.parquet`

### Key Fields:
- **game_id**: Unique game identifier (e.g., "2023_01_KC_DET")
- **season**: NFL season year (2023)
- **week**: NFL week number (1)
- **home_team**: Home team abbreviation (e.g., "KC", "DET")
- **away_team**: Away team abbreviation
- **home_score**: Final home team score
- **away_score**: Final away team score
- **gameday**: Game date
- **gametime**: Kickoff time
- **location**: Game location ("Home" or specific city)
- **result**: Game outcome margin
- **total**: Combined score
- **overtime**: Overtime indicator (0 = No, 1 = Yes)

### Betting/Advanced Fields:
- **spread_line**: Point spread
- **away_moneyline**: Away team money line
- **home_moneyline**: Home team money line
- **total_line**: Over/under line
- **under_odds**: Under betting odds
- **over_odds**: Over betting odds

### Game Context:
- **away_rest**: Days of rest for away team
- **home_rest**: Days of rest for home team
- **div_game**: Division game indicator
- **roof**: Stadium roof type
- **away_qb_name**: Starting away quarterback
- **home_qb_name**: Starting home quarterback
- **away_coach**: Away team head coach
- **home_coach**: Home team head coach
- **referee**: Game referee
- **stadium**: Stadium name

### Data Quality Notes:
- **Complete Fields**: All core game data (teams, scores, dates)
- **High Null Fields**: `nfl_detail_id`, `pff`, `ftn`, `surface`, `temp`, `wind` (100% null - expected)
- **Source**: nfl-data-py API
- **Validation**: ✅ All required fields present

## 🎯 Play-by-Play Data Details (2023 Week 1)

**File:** `plays/season=2023/week=1/pbp_20250815_193608.parquet`

### Core Play Fields:
- **game_id**: Game identifier linking to games data
- **play_id**: Unique play identifier within game
- **season**: NFL season (2023)
- **week**: NFL week (1)
- **home_team**: Home team abbreviation
- **away_team**: Away team abbreviation
- **possession_team**: Team with possession
- **play_type**: Type of play (pass, run, punt, etc.)
- **down**: Down number (1-4)
- **ydstogo**: Yards to go for first down
- **yards_gained**: Yards gained/lost on play

### Formation & Personnel:
- **offense_formation**: Offensive formation
- **offense_personnel**: Offensive personnel grouping
- **defense_personnel**: Defensive personnel grouping
- **defenders_in_box**: Number of defenders in box
- **n_offense**: Number of offensive players
- **n_defense**: Number of defensive players

### Advanced Analytics (NGS):
- **ngs_air_yards**: Next Gen Stats air yards
- **time_to_throw**: Time from snap to throw
- **was_pressure**: Pressure on quarterback indicator
- **route**: Receiver route type
- **defense_man_zone_type**: Coverage type
- **defense_coverage_type**: Specific coverage

### Data Quality Notes:
- **Complete Fields**: All core play data (game_id, play_id, basic stats)
- **High Null Fields**: Advanced NGS fields (56-63% null - normal for NFL data)
- **Coverage**: 2,816 plays across 16 games (avg ~176 plays/game)
- **Source**: nfl-data-py API
- **Validation**: ✅ All required fields present

## 🔄 Data Ingestion Process

### Ingestion Commands Used:
```bash
# Game schedules
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type schedules

# Play-by-play data  
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type pbp
```

### Data Pipeline:
1. **Fetch**: NFL data from nfl-data-py API
2. **Validate**: Data quality and completeness checks
3. **Transform**: Add metadata (ingestion timestamp, data source)
4. **Store**: Upload to S3 in Parquet format with partitioning
5. **Verify**: Confirm successful upload and accessibility

## 🎯 Available for Silver Layer Processing

This Bronze layer data is ready for Silver layer transformation:

### Games Data → Silver Opportunities:
- Date/time standardization  
- Team name standardization
- Score validation and derived metrics
- Game outcome classification
- Weather data enrichment (when available)

### Plays Data → Silver Opportunities:
- Player name standardization
- Play classification and categorization
- Down/distance situational analysis
- Formation pattern recognition
- Advanced metric calculations

## 📈 Expansion Opportunities

### Additional Seasons Available:
- **Historical**: 1999-2023 (complete seasons)
- **Current**: 2024 (partial, as season progresses)

### Additional Data Types:
- **Team Statistics**: Team-level seasonal stats
- **Player Statistics**: Individual player performance
- **Injury Reports**: Player injury status
- **Weather Data**: Game weather conditions
- **Referee Data**: Official assignments and statistics

### Scaling Considerations:
- **Full Season**: ~285 games per season
- **Full Season Plays**: ~50,000 plays per season
- **Storage Estimate**: ~25-50 MB per season for current data types

---

**Data Freshness:** Current as of ingestion date  
**Update Frequency:** Manual (on-demand via CLI scripts)  
**Quality Status:** ✅ Validated and production-ready
