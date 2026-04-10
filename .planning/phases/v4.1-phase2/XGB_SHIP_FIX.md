# v4.1 Phase 2: XGB SHIP Path Fix

**Date:** 2026-04-07
**Status:** COMPLETE

## Root Cause

The QB and RB XGBoost SHIP path was silently falling back to heuristic in
production because `_generate_ml_for_position` fed `silver_df` (the raw
Silver usage layer) as the feature source to `predict_player_stats`, but the
trained QB/RB models expect an 80-column feature vector assembled from 9+
Silver sources — including QBR fields absent from `silver_df`.

Specifically, QB models require these QBR columns (confirmed via model
`_meta.json` files):

```
qbr_epa_total, qbr_epa_total_roll3, qbr_epa_total_roll6, qbr_epa_total_std
qbr_pts_added, qbr_pts_added_roll3, qbr_pts_added_roll6, qbr_pts_added_std
qbr_qb_plays, qbr_qb_plays_roll3, qbr_qb_plays_roll6, qbr_qb_plays_std
qbr_qbr_total, qbr_qbr_total_roll3, qbr_qbr_total_roll6, qbr_qbr_total_std
```

These columns are already present in Silver advanced data
(`data/silver/players/advanced/`) and flow through `assemble_player_features()`
into the full assembled feature vector. The Bronze QBR data covers 2006-2023.

The QBR rolling features use `shift(1)` in `player_advanced_analytics.py`
(line 131: `s.shift(1).rolling(window, min_periods=3).mean()`), so temporal
integrity is fully maintained — no leakage.

## What Was Added

### 1. `src/ml_projection_router.py` — `_generate_ml_for_position`

Added optional `feature_df` parameter. When provided, it replaces `silver_df`
as the ML feature source while `silver_df` continues to be used for heuristic
fallback routing (which requires the Silver usage schema).

The week-1 filter (prior week as feature source) is applied to whichever
source is used, preserving temporal integrity.

### 2. `src/ml_projection_router.py` — `generate_ml_projections` SHIP loop

Removed the stale comment explaining why SHIP was broken. Now passes
`feature_df` through to `_generate_ml_for_position` for all SHIP positions.
The `feature_df` parameter already existed on `generate_ml_projections` (used
by HYBRID positions); it is now also wired to the SHIP branch.

### 3. `scripts/generate_projections.py` — `--ml` branch

Calls `assemble_player_features(season=args.season)` before invoking
`generate_ml_projections`, then passes the result as `feature_df`. Assembly
failures are caught and logged as warnings; the SHIP path gracefully degrades
to `silver_df` in that case.

## Verification Results

### Feature coverage (2023, week 5 prediction using week 4 features)

```
yardage features: 80/80 available in target_df
td features:      80/80 available in target_df
volume features:  80/80 available in target_df
turnover features: 80/80 available in target_df
```

### QB passing_yards predictions (week 5, 2023 season)

```
J.Allen:       308.3 yds  (ml)
J.Hurts:       252.8 yds  (ml)
J.Fields:      139.3 yds  (ml)
```

### Projection sources after fix (2023, week 5)

```
ml:     118 rows  (QB + RB)
hybrid: 197 rows  (WR + TE)
```

Before the fix, all 315 rows would have been `heuristic` for QB/RB.

### Temporal integrity

QBR rolling averages at week N use data from weeks 1..N-1 (shift(1) applied
in `player_advanced_analytics.apply_player_rolling`). Confirmed by inspecting
J.Goff 2023: week 4 `qbr_qb_plays_roll3 = 43.3` uses weeks 1-3 values only.

## Production Routing After Fix

```
QB  -> XGB ML (SHIP) via assembled feature vector with QBR  [NOW ACTIVE]
RB  -> XGB ML (SHIP) via assembled feature vector           [NOW ACTIVE]
WR  -> Heuristic + LGB residual correction (HYBRID)
TE  -> Heuristic + LGB residual correction (HYBRID)
```

## QBR Data Coverage Note

Bronze QBR data covers seasons 2006-2023 (ESPN coverage). Season 2024 and
beyond will have `NaN` for QBR raw and rolling columns for most QBs. XGBoost
handles NaN natively (routing rows to default branches), so this is
gracefully tolerated. Coverage for QBs with 2024+ data will improve once
`bronze_ingestion_simple.py --data-type qbr --season 2024` is run.

## Files Changed

- `src/ml_projection_router.py` — `_generate_ml_for_position` + SHIP loop
- `scripts/generate_projections.py` — `--ml` branch assembles feature_df
