# Phase 27: Prediction Pipeline - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Weekly prediction script that loads trained XGBoost spread and total models, assembles features for a given season/week, generates model lines, compares against Vegas closing lines from schedules Bronze, and classifies edges into confidence tiers. Outputs a combined table to console and saves as Gold-layer Parquet. No new model training, no backtesting, no betting framework — those are other phases.

</domain>

<decisions>
## Implementation Decisions

### Output Format & Display
- **D-01:** Compact output — each game row shows: teams, model spread line, Vegas spread line, spread edge, spread tier, model total line, Vegas total line, total edge, total tier
- **D-02:** Combined table — spread and total predictions in one row per game (not separate sections)
- **D-03:** Table sorted by edge magnitude (strongest edges first, best plays at top)
- **D-04:** Console + Gold Parquet — print formatted table to console AND save as Gold-layer Parquet partitioned by season/week

### Confidence Tiers
- **D-05:** Fixed-point thresholds: High (|edge| >= 3 pts), Medium (1.5-3 pts), Low (< 1.5 pts)
- **D-06:** All games shown including tiny edges — Low tier label, no "No edge" filter
- **D-07:** Independent tiers for spread and total — each game has separate spread_tier and total_tier

### Vegas Line Source
- **D-08:** Vegas lines from schedules Bronze (spread_line, total_line columns from nfl-data-py) — already ingested
- **D-09:** If Vegas lines are missing for a game, show model prediction but leave edge/tier columns as N/A

### CLI Design
- **D-10:** Script name: `scripts/generate_predictions.py` (matches roadmap success criteria)
- **D-11:** Required flags: `--season` and `--week` (e.g., `python scripts/generate_predictions.py --season 2025 --week 10`)
- **D-12:** `--model-dir` flag to override default MODEL_DIR (consistent with train_prediction_model.py and backtest_predictions.py)
- **D-13:** Assumes data is pre-ingested — script reads existing local Silver/Bronze data, user runs /ingest first

### Claude's Discretion
- Gold Parquet filename convention and exact output path
- Console table formatting library (tabulate, pandas to_string, etc.)
- Edge sign convention (positive = model favors home cover, etc.)
- Whether to print a summary line count ("X games with high-confidence edges")
- Error handling for missing model files or Silver data

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — PRED-01 (weekly pipeline), PRED-02 (edge detection), PRED-03 (confidence scoring)
- `.planning/ROADMAP.md` — Phase 27 success criteria (4 items: generate_predictions.py CLI, edge with direction/magnitude, confidence tiers, Gold Parquet output)

### Prior Phase Context
- `.planning/phases/25-feature-assembly-and-model-training/25-CONTEXT.md` — Feature assembly decisions, model training approach, XGBoost-only decision, conservative hyperparameters

### Existing Code (must read before implementing)
- `src/feature_engineering.py` — `assemble_game_features()`, `assemble_multiyear_features()`, `get_feature_columns()` — core feature assembly pipeline
- `src/model_training.py` — `load_model()` — model loading with metadata sidecar
- `src/config.py` — `MODEL_DIR`, `HOLDOUT_SEASON`, `TRAINING_SEASONS`, `CONSERVATIVE_PARAMS`, `LABEL_COLUMNS`
- `scripts/backtest_predictions.py` — Reference CLI pattern for prediction model scripts (argparse, imports, report formatting)
- `scripts/train_prediction_model.py` — Model training CLI (--model-dir flag pattern)

### State & Decisions
- `.planning/STATE.md` — XGBoost only, differential features, Vegas excluded as inputs, realistic ATS 52-55%

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `assemble_game_features(season)` in `src/feature_engineering.py` — Builds per-game differential features for a single season; returns DataFrame with feature columns + labels
- `get_feature_columns(df)` in `src/feature_engineering.py` — Extracts valid feature column names (excludes identifiers and labels)
- `load_model(model_dir, target)` in `src/model_training.py` — Loads saved XGBoost model + metadata JSON sidecar
- `backtest_predictions.py` — Established CLI pattern: argparse, sys.path.insert, from-imports of feature_engineering and model_training

### Established Patterns
- Scripts use argparse with `--season`, `--week`, `--model-dir` flags
- Feature assembly reads local Silver parquet via `_read_latest_local()`
- Schedules Bronze provides `spread_line`, `total_line` for Vegas lines
- Gold output follows `data/gold/{dataset}/season=YYYY/week=WW/` partition convention

### Integration Points
- Silver team data (8 paths) → feature assembly input via `assemble_game_features()`
- Bronze schedules → Vegas lines (spread_line, total_line) and game matchups
- `models/` directory → trained XGBoost spread and total model artifacts
- `data/gold/predictions/` → new Gold output path for prediction Parquet files

</code_context>

<specifics>
## Specific Ideas

- Roadmap success criteria specifies exact CLI: `python scripts/generate_predictions.py --season 2025 --week 10`
- Edge = model line minus Vegas line — positive edge means model sees value
- Confidence tiers match the user-facing table in success criteria: "high/medium/low edge"

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 27-prediction-pipeline*
*Context gathered: 2026-03-21*
