---
name: validate-data
description: Validate NFL data against business rules and check data quality. Use after ingestion runs, when debugging data issues, or before running projections. Checks AWS connectivity, S3 layer contents, and NFL business rule compliance.
argument-hint: "[season] [week]"
allowed-tools: Bash, Read, Grep, mcp__duckdb__query
---

Validate NFL data quality and business rule compliance across all pipeline layers.

## Arguments
`$ARGUMENTS` — parsed as `[season] [week]` (defaults: current season / all weeks)

## Environment check
!`cd /Users/georgesmith/repos/nfl_data_engineering && ls scripts/validate_project.py scripts/list_bronze_contents.py 2>/dev/null`

## Validation Steps

### 1. Environment & connectivity
```bash
source venv/bin/activate && python scripts/validate_project.py
```

### 2. Check Bronze layer contents for the season/week
```bash
source venv/bin/activate && python scripts/list_bronze_contents.py
```

### 3. NFL Business Rule Checks
Run inline validation checks:
```bash
source venv/bin/activate && python -c "
import sys
sys.path.insert(0, 'src')
from nfl_data_integration import NFLDataFetcher
fetcher = NFLDataFetcher()

# Validate schedules
schedules = fetcher.fetch_game_schedules([SEASON], week=WEEK)
result = fetcher.validate_data(schedules, 'schedules')
print('Schedules:', result)

# Validate player weekly if available
try:
    weekly = fetcher.fetch_player_weekly([SEASON], week=WEEK)
    result = fetcher.validate_data(weekly, 'player_weekly')
    print('Player weekly:', result)
except Exception as e:
    print(f'Player weekly unavailable: {e}')
"
```

### 4. DuckDB SQL validation of local Parquet files
Use the **duckdb MCP** to run SQL directly against any Parquet files in `data/` or downloaded from S3.
This is faster than loading into pandas for large datasets.

Example queries to run via the duckdb MCP:
```sql
-- Row counts per data type
SELECT 'player_weekly' AS dataset, COUNT(*) AS rows
FROM read_parquet('data/**/*.parquet')
WHERE filename LIKE '%player_weekly%';

-- Null check on key columns
SELECT
  COUNT(*) AS total,
  COUNT(player_id) AS has_player_id,
  COUNT(week) AS has_week,
  ROUND(100.0 * SUM(CASE WHEN player_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_null_player_id
FROM read_parquet('data/**/*.parquet');

-- NFL business rule: downs must be 1-4
SELECT down, COUNT(*) FROM read_parquet('data/**/pbp*.parquet')
WHERE down NOT BETWEEN 1 AND 4
GROUP BY down;

-- Freshness: most recent ingestion timestamp
SELECT MAX(ingestion_timestamp) AS latest_ingest
FROM read_parquet('data/**/*.parquet');
```

### 5. Business Rules to verify
- Games per regular season week: 14–16
- Valid downs: 1–4
- Valid yard lines: 0–100
- Valid season range: 1999–2026
- 32 NFL teams with consistent abbreviations
- Player positions limited to: QB, RB, WR, TE, K, OL, DL, LB, DB, ST
- Fantasy scoring: non-negative projected points for skill positions

### 6. Report findings
Summarize:
- Total records per data type (from DuckDB queries)
- Null percentage for key columns
- Any failed business rule checks
- Data freshness (ingestion timestamps)
- Recommendations for any issues found
