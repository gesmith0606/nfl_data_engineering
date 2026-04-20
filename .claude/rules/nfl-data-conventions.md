---
paths:
  - "**/*.py"
---
# NFL Data Conventions

## Storage Layers (Medallion Architecture)

- **Bronze** (`data/bronze/` local, `s3://nfl-raw/` S3) — raw NFL data from nfl-data-py, Sleeper, FinnedAI. Warn-never-block validation.
- **Silver** (`data/silver/` local, `s3://nfl-refined/` S3) — cleaned, joined, partitioned by season/week. Validation errors fail the transformation.
- **Gold** (`data/gold/` local, `s3://nfl-trusted/` S3) — projections, predictions, ML outputs. Sanity checked via CI gate before deploy.

## S3 Key Pattern

Every file is timestamped and partitioned:

    {dataset}/season=YYYY/week=WW/{filename}_YYYYMMDD_HHMMSS.parquet

Example: `player_weekly/season=2025/week=10/player_weekly_20251113_094512.parquet`

## Read Rule — ALWAYS use `download_latest_parquet`

Every pipeline run appends a new timestamped file. DO NOT scan a full prefix.

```python
from src.utils import download_latest_parquet

df = download_latest_parquet(
    s3_client,
    bucket="nfl-refined",
    prefix="player_weekly/season=2025/week=10/",
)
```

Signature: `download_latest_parquet(s3_client, bucket: str, prefix: str, tmp_dir: str = "/tmp") -> pd.DataFrame`

Read prefixes MUST be week-scoped: `dataset/season=YYYY/week=WW/`. Season-only prefixes return multiple weeks and inflate the read.

Also available: `get_latest_s3_key(s3_client, bucket: str, prefix: str) -> str | None` — returns the key without downloading.

## Local-First Workflow

AWS credentials expired March 2026. Scripts auto-detect invalid credentials and fall back to `data/{bronze,silver,gold}/`. Use `--no-s3` flag to force local-only. The adapter pattern in `src/nfl_data_adapter.py` handles local-first reads with S3 fallback transparently.

## Season / Week Partitioning

- Partition columns: `season` (int, 4-digit), `week` (int, 1-18 regular season; 19-22 playoffs)
- Valid `PLAYER_DATA_SEASONS`: 2016–2025 (defined in `src/config.py`)
- Schedules go back to 1999; most Silver layers cover 2016–2025

## Adding New Data Types

Add new data types via the Bronze registry in `scripts/bronze_ingestion_simple.py`. Registry entries specify partition strategy (week-partitioned vs season-only). Follow the adapter pattern in `src/nfl_data_adapter.py` for all new data fetching.

## Common Schema Gotchas

- `snap_counts`: column is `offense_pct` (not `snap_pct`), player identified by `player` (not `player_id`) — mapped in Silver transformation
- `player_weekly`: column is `receiving_air_yards` (not `air_yards`) — mapped in prep functions
- `nfl-data-py`: use `import_seasonal_rosters` — `import_rosters` returns wrong data
- Write parquet: always specify `index=False` and partition `by=["season", "week"]`

## Reference

See `CLAUDE.md` "Architecture" section for full data flow diagram.
See `src/utils.py` for `download_latest_parquet` and `get_latest_s3_key`.
See `src/nfl_data_adapter.py` for the unified adapter pattern.
See `src/config.py` for `S3_BUCKET_BRONZE`, `S3_BUCKET_SILVER`, `S3_BUCKET_GOLD`, and `PLAYER_DATA_SEASONS`.
