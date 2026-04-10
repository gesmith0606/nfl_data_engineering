# Phase S3 — Projection Engine Integration

**Status**: Implemented  
**Date**: 2026-04-07

---

## Overview

Phase S3 wires the Gold-layer sentiment multiplier produced by the S1/S2
sentiment pipeline directly into `projection_engine.py` as a final adjustment
layer applied after injury and Vegas multipliers.  The integration is
**opt-in** — existing projection runs are unaffected unless `--use-sentiment`
is explicitly passed.

---

## How Sentiment Adjustments Are Applied

The adjustment follows the same pattern as `apply_injury_adjustments()`:

1. **Join** — the Gold sentiment DataFrame is joined to the projections
   DataFrame on `player_id`.
2. **Skip injured-zeroed players** — players already at `projected_points=0`
   with `injury_multiplier=0` are skipped so a positive sentiment cannot
   accidentally restore an Out/IR player.
3. **Zero-out on ruling** — if `is_ruled_out` or `is_inactive` is `True`,
   all projection columns are set to 0.0 (overrides any positive multiplier).
4. **Scale** — `sentiment_multiplier` (clamped to `[0.70, 1.15]`) is applied
   to `projected_points`, `projected_floor`, and `projected_ceiling`.
5. **Transparency columns** — two columns are appended:
   - `sentiment_multiplier` — the applied multiplier (1.0 = neutral / no data)
   - `sentiment_events` — comma-separated list of active event flags

---

## Multiplier Range and Meaning

| Sentiment score | Multiplier | Interpretation |
|-----------------|-----------|----------------|
| +1.0 (very positive) | 1.15 | 15 % boost (e.g. "cleared to play, full practice") |
| 0.0 (neutral) | 1.00 | No adjustment |
| −1.0 (very negative) | 0.70 | 30 % reduction (e.g. "unlikely to play") |

The mapping is linear and piecewise:
- `[0, +1]` → `[1.00, 1.15]`
- `[-1, 0]` → `[0.70, 1.00]`

The aggregator enforces these bounds; `apply_sentiment_adjustments()` also
clamps as a defensive guard.

---

## Event Flag Handling

Flags are OR-aggregated across all signals for a player-week.

| Flag | Effect |
|------|--------|
| `is_ruled_out` | Zero all projections; `sentiment_multiplier = 0.0` |
| `is_inactive` | Zero all projections; `sentiment_multiplier = 0.0` |
| `is_questionable` | Recorded in `sentiment_events`; multiplier is applied normally (typically < 1.0 from negative sentiment) |
| `is_suspended` | Recorded in `sentiment_events`; multiplier applied normally |
| `is_returning` | Recorded in `sentiment_events`; multiplier applied normally (typically > 1.0) |

---

## Data Loading — `load_latest_sentiment()`

Located in `src/projection_engine.py`.

```python
def load_latest_sentiment(season: int, week: int) -> pd.DataFrame:
    ...
```

Resolution order:
1. Local `data/gold/sentiment/season=YYYY/week=WW/*.parquet` — picks the
   most recently modified file (same timestamped-file convention as all
   other Gold layers).
2. S3 `s3://nfl-trusted/sentiment/season=YYYY/week=WW/` via
   `download_latest_parquet()` — only attempted if AWS credentials are
   present.
3. Returns an **empty DataFrame** if neither source has data; callers must
   handle this gracefully (the pipeline does by logging a warning and
   continuing).

---

## How to Enable / Disable

### Enable (opt-in)

```bash
source venv/bin/activate
python scripts/generate_projections.py \
    --week 1 --season 2026 --scoring half_ppr \
    --use-sentiment
```

### Disable (default)

Omit `--use-sentiment`.  The projection pipeline runs exactly as before:

```bash
python scripts/generate_projections.py --week 1 --season 2026 --scoring half_ppr
```

### With ML router

The flag composes cleanly with `--ml`:

```bash
python scripts/generate_projections.py \
    --week 1 --season 2026 --scoring half_ppr \
    --ml --use-sentiment
```

Sentiment adjustments are applied after the ML router generates projections
and after injury adjustments, before floor/ceiling is added.

---

## Key Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `apply_sentiment_adjustments(projections_df, sentiment_df)` | `src/projection_engine.py` | Core multiplier application |
| `load_latest_sentiment(season, week)` | `src/projection_engine.py` | Local + S3 data loading |

---

## Output Columns Added

| Column | Type | Description |
|--------|------|-------------|
| `sentiment_multiplier` | float | Applied multiplier (1.0 = neutral or no data) |
| `sentiment_events` | str | Comma-separated active flags (e.g. `"is_questionable"`) |

---

## Example: Expected Log Output

```
Loading sentiment data for Season 2026 Week 1...
Loaded sentiment data: 142 players, computed at 2026-09-07T14:32:11+00:00
Sentiment adjustments applied: 38 players affected
```

When no sentiment data exists:

```
Loading sentiment data for Season 2026 Week 1...
WARN: No sentiment data available; skipping sentiment adjustments
```

---

## Prerequisite

Gold-layer sentiment Parquet files must exist at
`data/gold/sentiment/season=YYYY/week=WW/`.  These are produced by running
the S2 pipeline:

```bash
# Aggregate Silver signals → Gold Parquet
python -c "
from src.sentiment.aggregation.weekly import WeeklyAggregator
WeeklyAggregator().aggregate(season=2026, week=1)
"
```

---

## Tests

`tests/test_sentiment_integration.py` — 22 unit tests covering:
- Neutral multiplier (no change)
- Positive/negative scaling
- `is_ruled_out` / `is_inactive` zeroing
- Injury-zeroed player skip
- Multiplier range clamping
- Event flag transparency
- Missing/empty/malformed sentiment data handling
- Multi-player correctness
- Immutability of input DataFrame
