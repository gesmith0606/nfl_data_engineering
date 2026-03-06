---
name: weekly-pipeline
description: Run the full in-season weekly pipeline for a given NFL season and week. Chains Bronze ingestion → Silver transformation → Projection generation. Use when the user says "run the pipeline for week X" or "update projections for week N".
argument-hint: "[season] [week] [scoring]"
allowed-tools: Bash, Read
---

Run the complete weekly NFL data pipeline: Bronze → Silver → Gold (projections).

## Arguments
`$ARGUMENTS` — parsed as: `[season] [week] [scoring_format]`
- Defaults: season=2026, week=1, scoring=half_ppr
- Scoring options: ppr, half_ppr, standard

## Current environment
!`cd /Users/georgesmith/repos/nfl_data_engineering && python --version 2>/dev/null && ls .env 2>/dev/null && echo "env file present"`

## Pipeline Steps

### Step 1 — Bronze Ingestion (all player data types for the week)
Run these in order for the given season/week:
```bash
source venv/bin/activate
python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type player_weekly
python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type snap_counts
python scripts/bronze_ingestion_simple.py --season SEASON --week WEEK --data-type injuries
python scripts/bronze_ingestion_simple.py --season SEASON --data-type rosters
```

### Step 2 — Silver Transformation
```bash
source venv/bin/activate && python scripts/silver_player_transformation.py --season SEASON --week WEEK
```

### Step 3 — Generate Projections
```bash
source venv/bin/activate && python scripts/generate_projections.py --season SEASON --week WEEK --scoring SCORING --output both
```

### Step 4 — Summary
After all steps complete, report:
- Total records at each layer (Bronze → Silver → Gold)
- Top 10 projected players for the week
- Any errors or data quality issues encountered
- S3 URIs for each output

## Error handling
- If any step fails, stop the pipeline and report the specific failure
- Check .env for AWS credentials if S3 operations fail
- If nfl-data-py returns no data, check if the week exists for that season
