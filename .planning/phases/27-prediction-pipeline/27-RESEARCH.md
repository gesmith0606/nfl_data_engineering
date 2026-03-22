# Phase 27: Prediction Pipeline - Research

**Researched:** 2026-03-21
**Domain:** CLI script for weekly NFL game predictions with XGBoost models, edge detection, confidence tiers
**Confidence:** HIGH

## Summary

Phase 27 is a straightforward integration phase. All building blocks exist: feature assembly (`assemble_game_features`), model loading (`load_model`), Bronze schedules with Vegas lines (`spread_line`, `total_line`), and established CLI patterns from `backtest_predictions.py` and `train_prediction_model.py`. The work is connecting these components in a new `scripts/generate_predictions.py` that loads models, assembles features for a specific season/week, generates predictions, computes edges against Vegas, classifies tiers, prints a sorted table, and saves Gold Parquet.

The main technical consideration is that `assemble_game_features(season)` returns ALL games for a season. The prediction script must filter to the requested week after assembly. The feature columns must match the model's trained feature set (stored in `metadata["feature_names"]`). Vegas lines come from Bronze schedules, not the assembled features (Vegas was deliberately excluded from model inputs per STATE.md decisions).

**Primary recommendation:** Build a single script that reuses existing functions -- no new src/ modules needed. Follow the backtest_predictions.py CLI pattern exactly.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Compact output -- each game row shows: teams, model spread line, Vegas spread line, spread edge, spread tier, model total line, Vegas total line, total edge, total tier
- **D-02:** Combined table -- spread and total predictions in one row per game (not separate sections)
- **D-03:** Table sorted by edge magnitude (strongest edges first, best plays at top)
- **D-04:** Console + Gold Parquet -- print formatted table to console AND save as Gold-layer Parquet partitioned by season/week
- **D-05:** Fixed-point thresholds: High (|edge| >= 3 pts), Medium (1.5-3 pts), Low (< 1.5 pts)
- **D-06:** All games shown including tiny edges -- Low tier label, no "No edge" filter
- **D-07:** Independent tiers for spread and total -- each game has separate spread_tier and total_tier
- **D-08:** Vegas lines from schedules Bronze (spread_line, total_line columns from nfl-data-py) -- already ingested
- **D-09:** If Vegas lines are missing for a game, show model prediction but leave edge/tier columns as N/A
- **D-10:** Script name: `scripts/generate_predictions.py` (matches roadmap success criteria)
- **D-11:** Required flags: `--season` and `--week`
- **D-12:** `--model-dir` flag to override default MODEL_DIR
- **D-13:** Assumes data is pre-ingested -- script reads existing local Silver/Bronze data

### Claude's Discretion
- Gold Parquet filename convention and exact output path
- Console table formatting library (tabulate, pandas to_string, etc.)
- Edge sign convention (positive = model favors home cover, etc.)
- Whether to print a summary line count ("X games with high-confidence edges")
- Error handling for missing model files or Silver data

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PRED-01 | Weekly prediction pipeline generating model spread and total lines for upcoming games | `assemble_game_features(season)` + week filter + `load_model()` + `model.predict()` -- all building blocks exist |
| PRED-02 | Edge detection comparing model lines vs Vegas closing lines per game | `spread_line` and `total_line` available in Bronze schedules; edge = model_line - vegas_line |
| PRED-03 | Confidence scoring with tiers (high/medium/low edge) per game prediction | Fixed thresholds from D-05: High >= 3, Medium 1.5-3, Low < 1.5; classify based on abs(edge) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | DataFrame assembly, filtering, table formatting | Already used throughout project |
| xgboost | existing | Model loading and prediction | Models saved as XGBoost JSON |
| pyarrow | existing | Parquet output | Already used for Gold layer writes |
| argparse | stdlib | CLI argument parsing | Pattern from backtest_predictions.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tabulate | install if needed | Console table formatting | Optional; pandas `to_string()` is sufficient |

**No new dependencies required.** All needed libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
scripts/
  generate_predictions.py  # New CLI script (this phase)
src/
  feature_engineering.py   # Reuse assemble_game_features() -- no changes
  model_training.py        # Reuse load_model() -- no changes
  config.py                # Reuse MODEL_DIR -- no changes
data/
  gold/
    predictions/
      season=YYYY/
        week=WW/
          predictions_YYYYMMDD_HHMMSS.parquet  # Output
```

### Pattern 1: Prediction Pipeline Flow
**What:** Load models, assemble features, predict, merge Vegas, compute edges, classify tiers, output
**When to use:** This is the only pattern needed for this phase

```python
# 1. Load both models
spread_model, spread_meta = load_model("spread", model_dir=args.model_dir)
total_model, total_meta = load_model("total", model_dir=args.model_dir)

# 2. Assemble features for the full season, filter to requested week
game_df = assemble_game_features(args.season)
week_df = game_df[game_df["week"] == args.week].copy()

# 3. Get feature columns matching what model was trained on
spread_features = spread_meta["feature_names"]
total_features = total_meta["feature_names"]
available_spread = [c for c in spread_features if c in week_df.columns]
available_total = [c for c in total_features if c in week_df.columns]

# 4. Predict
week_df["model_spread"] = spread_model.predict(week_df[available_spread])
week_df["model_total"] = total_model.predict(week_df[available_total])

# 5. Vegas lines are already in week_df from assemble_game_features
#    (joined from Bronze schedules as spread_line, total_line)
week_df["vegas_spread"] = week_df["spread_line"]
week_df["vegas_total"] = week_df["total_line"]

# 6. Compute edges
week_df["spread_edge"] = week_df["model_spread"] - week_df["vegas_spread"]
week_df["total_edge"] = week_df["model_total"] - week_df["vegas_total"]

# 7. Classify tiers
def classify_tier(edge_abs):
    if pd.isna(edge_abs):
        return None
    if edge_abs >= 3.0:
        return "high"
    elif edge_abs >= 1.5:
        return "medium"
    return "low"

week_df["spread_tier"] = week_df["spread_edge"].abs().apply(classify_tier)
week_df["total_tier"] = week_df["total_edge"].abs().apply(classify_tier)
```

### Pattern 2: Gold Parquet Output (from generate_projections.py)
**What:** Save to local Gold layer with timestamp filename
**When to use:** Writing prediction output

```python
from datetime import datetime

timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
s3_key = f"predictions/season={season}/week={week:02d}/predictions_{timestamp}.parquet"
gold_path = os.path.join(GOLD_DIR, s3_key)
os.makedirs(os.path.dirname(gold_path), exist_ok=True)
output_df.to_parquet(gold_path, index=False)
```

### Pattern 3: Console Table Output
**What:** Print sorted table of predictions
**When to use:** Console display after prediction

```python
# Sort by max edge magnitude (strongest plays first)
output_df["max_edge"] = output_df[["spread_edge", "total_edge"]].abs().max(axis=1)
output_df = output_df.sort_values("max_edge", ascending=False)

display_cols = [
    "home_team", "away_team",
    "model_spread", "vegas_spread", "spread_edge", "spread_tier",
    "model_total", "vegas_total", "total_edge", "total_tier",
]
print(output_df[display_cols].to_string(index=False, float_format="%.1f"))
```

### Anti-Patterns to Avoid
- **Modifying feature_engineering.py:** Do not add week-filtering to `assemble_game_features()`. Filter in the script after calling it. The function's contract is season-level.
- **Using Vegas lines as features:** Vegas lines are excluded from model inputs by design (STATE.md). Only use them for edge comparison post-prediction.
- **Building a new src/ module:** This is a script-only phase. All reusable logic already exists in src/.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature assembly | Custom feature loading | `assemble_game_features(season)` | Handles 8 Silver sources, diff computation, schedule joins |
| Model loading | Custom XGBoost deserialization | `load_model(target_name, model_dir)` | Handles JSON model + metadata sidecar |
| Feature column selection | Manual column lists | `metadata["feature_names"]` from model sidecar | Guarantees feature alignment with training |
| Gold path construction | Ad-hoc paths | Follow `generate_projections.py` pattern with GOLD_DIR | Consistent partition convention |

## Common Pitfalls

### Pitfall 1: Feature Mismatch Between Training and Prediction
**What goes wrong:** Model was trained on N features, but assembled data for a different season has different columns.
**Why it happens:** Silver data availability varies by season; some columns may be missing.
**How to avoid:** Use `metadata["feature_names"]` to get the exact features the model expects. Filter to available columns and warn about missing ones (see backtest_predictions.py lines 162-166 for the pattern).
**Warning signs:** `ValueError` from XGBoost about feature count mismatch.

### Pitfall 2: Vegas Lines Already in Game Features as Labels
**What goes wrong:** `assemble_game_features()` joins Bronze schedules and includes `spread_line` and `total_line` as label columns. These are available directly in the assembled DataFrame.
**Why it matters:** No separate schedule read is needed for Vegas lines. They come through `assemble_game_features()` -> `_read_bronze_schedules()` merge.
**How to avoid:** Use `week_df["spread_line"]` and `week_df["total_line"]` directly after assembly. Rename to `vegas_spread` / `vegas_total` for the output schema.

### Pitfall 3: Future Games Missing Scores and Actual Results
**What goes wrong:** For future/unplayed games, `home_score`, `away_score`, `actual_margin`, `actual_total` will be NaN.
**Why it matters:** `assemble_game_features()` computes `actual_margin` and `actual_total` from scores, and filters to `game_type == "REG"`. For future games where scores are NaN, this is fine -- the function still returns rows.
**How to avoid:** Only select feature columns and Vegas lines for the output. Ignore label columns.

### Pitfall 4: Sorting by Edge Magnitude with NaN Vegas Lines
**What goes wrong:** When Vegas lines are missing (D-09), edges are NaN, and `sort_values` behavior with NaN needs handling.
**Why it happens:** Some games may lack Vegas lines (early schedule releases, special games).
**How to avoid:** Use `na_position="last"` in sort_values, or compute a sort key that handles NaN.

### Pitfall 5: Week Filtering Returns Empty DataFrame
**What goes wrong:** Requesting a week that has no Silver data or no schedule data.
**Why it happens:** Data not ingested, or week doesn't exist in that season.
**How to avoid:** Check `len(week_df) == 0` after filtering and print a clear error message.

### Pitfall 6: Model Files Not Found
**What goes wrong:** Script fails because models haven't been trained yet.
**Why it happens:** User runs generate_predictions.py before train_prediction_model.py.
**How to avoid:** Catch `FileNotFoundError` from `load_model()` and print a helpful message pointing to the training script. See backtest_predictions.py lines 152-155.

## Code Examples

### CLI Argument Pattern (from backtest_predictions.py)
```python
# Source: scripts/backtest_predictions.py
parser = argparse.ArgumentParser(
    description="Generate NFL game predictions with edge detection"
)
parser.add_argument("--season", type=int, required=True, help="NFL season year")
parser.add_argument("--week", type=int, required=True, help="NFL week number")
parser.add_argument("--model-dir", type=str, default=None,
                    help="Directory containing trained models (default: models/)")
```

### Model Loading with Feature Alignment (from backtest_predictions.py)
```python
# Source: scripts/backtest_predictions.py lines 151-168
model, metadata = load_model("spread", model_dir=model_dir)
model_features = metadata.get("feature_names", feature_cols)
available = [c for c in model_features if c in week_df.columns]
if len(available) < len(model_features):
    missing = set(model_features) - set(available)
    print(f"  WARNING: {len(missing)} features missing: {sorted(missing)[:5]}...")
predictions = model.predict(week_df[available])
```

### Gold Output Schema (from data dictionary)
```python
# Source: docs/NFL_DATA_DICTIONARY.md - Game Predictions schema
output_columns = {
    "game_id": "STRING",        # e.g., "2025_10_KC_BUF"
    "season": "INT",
    "week": "INT",
    "home_team": "STRING",
    "away_team": "STRING",
    "model_spread": "FLOAT",    # Model predicted spread (neg = home favored)
    "model_total": "FLOAT",     # Model predicted total
    "vegas_spread": "FLOAT",    # From schedules Bronze (nullable)
    "vegas_total": "FLOAT",     # From schedules Bronze (nullable)
    "spread_edge": "FLOAT",     # model_spread - vegas_spread (nullable)
    "total_edge": "FLOAT",      # model_total - vegas_total (nullable)
    "spread_confidence_tier": "STRING",  # high/medium/low (nullable)
    "total_confidence_tier": "STRING",   # high/medium/low (nullable)
    "model_version": "STRING",  # e.g., "v1.4.0"
    "prediction_timestamp": "TIMESTAMP",  # UTC
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No prediction pipeline | XGBoost spread + total models trained | Phase 25-26 | Models exist, need inference script |
| Manual feature assembly | `assemble_game_features()` automated | Phase 25 | Feature pipeline ready for reuse |

## Open Questions

1. **Edge sign convention**
   - What we know: `spread_line` in nfl-data-py is negative when home team is favored. `model_spread` predicts `actual_margin` = `home_score - away_score`.
   - What's unclear: The exact sign convention for edge. If model says -7 (home by 7) and Vegas says -3 (home by 3), edge = -7 - (-3) = -4, meaning model sees more home advantage.
   - Recommendation: Use `spread_edge = model_spread - vegas_spread`. Positive spread_edge means model sees MORE home team advantage than Vegas. Document this in the script's docstring. For totals: positive total_edge means model expects higher scoring than Vegas.

2. **Sort key for D-03 (strongest edges first)**
   - What we know: D-03 says sorted by edge magnitude, best plays at top.
   - What's unclear: Whether to sort by max of spread_edge and total_edge, or just one.
   - Recommendation: Sort by `max(abs(spread_edge), abs(total_edge))` descending. This surfaces games with the strongest edge in either market.

3. **Model version string**
   - What we know: Data dictionary schema includes `model_version` column.
   - Recommendation: Use `"v1.4.0"` as hardcoded string matching the milestone. Could also pull from metadata sidecar if a version field is added there.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `tests/` directory, standard pytest discovery |
| Quick run command | `python -m pytest tests/test_generate_predictions.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PRED-01 | Script generates model spread and total lines for each game in a week | unit | `python -m pytest tests/test_generate_predictions.py::test_predictions_generated -x` | Wave 0 |
| PRED-01 | Script handles missing model files gracefully | unit | `python -m pytest tests/test_generate_predictions.py::test_missing_model_error -x` | Wave 0 |
| PRED-02 | Edge computed as model_line minus vegas_line | unit | `python -m pytest tests/test_generate_predictions.py::test_edge_computation -x` | Wave 0 |
| PRED-02 | Missing Vegas lines produce NaN edges | unit | `python -m pytest tests/test_generate_predictions.py::test_missing_vegas_lines -x` | Wave 0 |
| PRED-03 | Tiers classified correctly at thresholds | unit | `python -m pytest tests/test_generate_predictions.py::test_tier_classification -x` | Wave 0 |
| PRED-03 | Independent tiers for spread and total | unit | `python -m pytest tests/test_generate_predictions.py::test_independent_tiers -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_generate_predictions.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_generate_predictions.py` -- covers PRED-01, PRED-02, PRED-03
- [ ] Test fixtures: mock models (XGBoost JSON + metadata sidecar), mock Silver/Bronze data

## Sources

### Primary (HIGH confidence)
- `src/feature_engineering.py` -- assemble_game_features(), get_feature_columns(), _read_bronze_schedules()
- `src/model_training.py` -- load_model() signature and behavior
- `src/config.py` -- MODEL_DIR, LABEL_COLUMNS, SILVER_TEAM_LOCAL_DIRS
- `scripts/backtest_predictions.py` -- CLI pattern, feature alignment, model loading
- `scripts/train_prediction_model.py` -- --model-dir flag pattern
- `scripts/generate_projections.py` -- Gold Parquet output pattern (GOLD_DIR, timestamp, to_parquet)
- `docs/NFL_DATA_DICTIONARY.md` -- Planned Game Predictions schema (15 columns)
- Bronze schedules data inspection -- confirmed `spread_line`, `total_line`, `home_team`, `away_team`, `game_id` columns present
- `data/bronze/schedules/season=2025/` -- confirmed 285 rows with non-null spread_line values

### Secondary (MEDIUM confidence)
- `.planning/phases/27-prediction-pipeline/27-CONTEXT.md` -- locked decisions D-01 through D-13

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- all building blocks exist, just need glue script
- Pitfalls: HIGH -- inspected actual code for edge cases (NaN handling, feature alignment, empty week)

**Research date:** 2026-03-21
**Valid until:** No expiration -- this is project-internal integration work
