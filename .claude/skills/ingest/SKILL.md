---
name: ingest
description: Ingest NFL data into the Bronze S3 layer. Use when the user wants to fetch or load NFL data for a season, week, or data type. Accepts arguments like "2024 week 5 player_weekly" or "2024 all player_seasonal". Also supports "sleeper" as a data-type to pull roster/ADP data from the Sleeper API.
argument-hint: "[season] [week] [data-type]"
allowed-tools: Bash, Read, mcp__sleeper__*
---

Ingest NFL data into the Bronze layer (S3: nfl-raw).

## Arguments
- `$ARGUMENTS` — parsed as: `[season] [week] [data-type]`
- Supported data types: `schedules`, `pbp`, `teams`, `player_weekly`, `snap_counts`, `injuries`, `rosters`, `player_seasonal`, `sleeper_adp`, `sleeper_rosters`
- Use `all` as data-type to ingest all player data types for that season/week

## Current project state
!`cd /Users/georgesmith/repos/nfl_data_engineering && ls scripts/bronze_ingestion_simple.py src/nfl_data_integration.py 2>/dev/null && echo "Scripts present"`

## Steps

1. Parse `$ARGUMENTS` to extract season, week, and data-type (default: season=2024, week=1, data-type=schedules)

2. **If data-type is `sleeper_adp`** — use the Sleeper MCP directly:
   - Call the Sleeper MCP to fetch current ADP rankings for the season
   - Save the result as `data/sleeper_adp_SEASON.csv` (columns: player_name, player_id, position, adp_rank, team)
   - Confirm row count and show top 10

3. **If data-type is `sleeper_rosters`** — use the Sleeper MCP directly:
   - Call the Sleeper MCP to fetch current rosters and player pool
   - Save to `data/sleeper_rosters_SEASON.csv`

4. **If data-type is `all`**, run all nfl-data-py player types in sequence:
   ```bash
   source venv/bin/activate
   python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type player_weekly
   python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type snap_counts
   python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type injuries
   python scripts/bronze_ingestion_simple.py --season SEASON --data-type rosters
   python scripts/bronze_ingestion_simple.py --season SEASON --data-type player_seasonal
   ```

5. **Otherwise**, run the single ingestion command:
   ```bash
   source venv/bin/activate && python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type DATA_TYPE
   ```

6. After ingestion, show a summary:
   - Records ingested
   - S3 location (or local file for Sleeper data)
   - Any validation issues

7. If ingestion fails, diagnose the error — check AWS credentials in .env, verify nfl-data-py API availability, and suggest fixes.

## Notes
- Always activate venv before running Python commands
- Seasons supported: 1999–2026
- Weeks supported: 1–22 (includes playoffs)
- `rosters` and `player_seasonal` do not use the `--week` flag (season-level data)
- Sleeper MCP data types save locally to `data/` — no S3 upload needed for ADP
