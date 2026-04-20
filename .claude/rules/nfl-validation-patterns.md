---
paths:
  - "**/*.py"
---
# NFL Validation Patterns

## Philosophy: Warn-Never-Block at Bronze, Enforce at Silver

- **Bronze**: `validate_data()` emits warnings; ingestion always completes. Raw data preserved as-is.
- **Silver**: validation errors fail the transformation. Downstream must not consume malformed Silver.
- **Gold**: sanity checks (`scripts/sanity_check_projections.py`) run as CI gate in `deploy-web.yml`. Fewer than 10 warnings = deploy; any critical = block.

## Core Validator: `NFLDataFetcher.validate_data()`

Defined in `src/nfl_data_integration.py`. Call signature:

```python
from src.nfl_data_integration import NFLDataFetcher

fetcher = NFLDataFetcher()
report = fetcher.validate_data(df, data_type="player_weekly")
# report: Dict with keys warnings, errors, row_count
```

Supported `data_type` values: `"schedules"`, `"pbp"`, `"teams"`, `"player_weekly"`, `"snap_counts"`, `"injuries"`, `"rosters"`, `"player_seasonal"`, and all other Bronze types.

Wired into every Bronze ingestion script automatically. Do NOT duplicate validation logic elsewhere.

## Business Rules (MUST be enforced)

| Rule | Valid Range | Enforcement |
|------|-------------|-------------|
| Seasons | 1999-2026 | Hard error outside range |
| Regular season weeks | 1-18 | Warn if outside range |
| Teams | 32 distinct abbreviations | Error on unknown abbreviation |
| Down (PBP) | 1-4 | Error on PBP rows |
| Distance (PBP) | 1-99 | Error on PBP rows |
| Yard line (PBP) | 0-100 | Error on PBP rows |
| Projected points (skill positions) | >= 0 | Error on Gold output |

Team abbreviations: use nflverse convention (e.g., `LAR` for Rams, `JAX` for Jaguars). Derive the canonical 32-entry list from the latest `teams` Bronze parquet.

## Ad-Hoc Validation: DuckDB on Parquet

For one-off validation queries, use DuckDB MCP to query Parquet directly — no pandas import, no S3 round-trip:

```sql
-- Check for null player_ids in Silver
SELECT COUNT(*) AS null_rows
FROM read_parquet('data/silver/player_weekly/season=2025/week=*/*.parquet')
WHERE player_id IS NULL;

-- Verify season range
SELECT DISTINCT season FROM read_parquet('data/bronze/schedules/season=*/week=*/*.parquet')
ORDER BY season;
```

Use this pattern in the `/validate-data` skill. It is the fastest way to inspect any layer without loading everything into memory.

## Pipeline Health Check

```bash
python scripts/check_pipeline_health.py [--season YYYY] [--week WW] [--layer {bronze,silver,gold}]
```

Checks S3 freshness (file exists for the week) and file size (not suspiciously small). Run as part of the `/weekly-pipeline` skill after ingestion. Also callable standalone via `/health-check` skill.

## Common Edge Cases to Test

- **Bye weeks**: player_id present, all stats zero, `is_bye_week=True`
- **Rookies**: no prior NFL rows — projection engine uses positional fallback baselines
- **Missing columns**: Silver transformations must handle missing NGS/PFR/QBR columns gracefully (some seasons have gaps)
- **Empty DataFrames**: every function must handle `len(df) == 0` without raising

## Reference

See `src/nfl_data_integration.py` for `NFLDataFetcher.validate_data()` source.
See `scripts/check_pipeline_health.py` for pipeline freshness checks.
See `scripts/sanity_check_projections.py` for Gold-layer CI gate.
See `src/config.py` for `PLAYER_DATA_SEASONS` (valid training range: 2016-2025).
