# Phase 25: Feature Assembly and Model Training - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Build XGBoost prediction models for point spreads and over/unders using game-level differential features assembled from 337-column Silver feature vector, with walk-forward cross-validation and Optuna hyperparameter tuning. This phase produces trained models and a training CLI — backtesting against Vegas lines and weekly prediction pipeline are separate phases (26 and 27).

</domain>

<decisions>
## Implementation Decisions

### Feature Assembly Pipeline
- **D-01:** Team-level features only — no player-level features. Aligned with REQUIREMENTS.md Out of Scope ("Player-level game prediction features")
- **D-02:** Module placement — Claude's discretion (new `src/feature_engineering.py` or extending existing module based on codebase patterns)
- **D-03:** NaN handling for Weeks 1-3 — Claude's discretion (fill with season-wide averages, zeros, or drop early weeks based on ML best practices for tree models)
- **D-04:** Differential feature selection (all numeric vs curated subset) — Claude's discretion based on feature importance literature and overfitting risk with ~1,900 games

### Walk-Forward CV Design
- **D-05:** Expanding window strategy — train on seasons 2016..N, validate on N+1
- **D-06:** Training seasons: 2016-2023. Holdout: 2024 (sealed, never touched during tuning per BACK-02)
- **D-07:** Season-level fold boundaries only — no intra-season splits to avoid data leakage
- **D-08:** Fold count — Claude's discretion based on training set size

### Model Training & Tuning
- **D-09:** 50 Optuna trials per target for hyperparameter tuning
- **D-10:** Separate XGBoost models for spread and over/under — independent hyperparameters per target
- **D-11:** Conservative default hyperparameters mandatory: shallow trees, strong regularization, early stopping (from STATE.md decisions)
- **D-12:** Model artifact format — Claude's discretion (JSON native vs pickle/joblib based on portability needs)
- **D-13:** Optuna optimization metric — Claude's discretion (MAE vs RMSE based on edge detection use case)
- **D-14:** Vegas lines excluded as input features (zero edge by definition — from REQUIREMENTS.md)

### Training CLI & Output
- **D-15:** Script name: `scripts/train_prediction_model.py` (matches roadmap success criteria exactly)
- **D-16:** CLI flag design — Claude's discretion (at minimum: `--target spread|total`)
- **D-17:** Model output directory — Claude's discretion (new `models/` or `data/gold/models/`)
- **D-18:** Feature importance report format — Claude's discretion (console + file vs console only)

### Claude's Discretion
- Module placement for feature assembly code
- NaN fill strategy for early-season sparse rolling features
- Which Silver columns get differential treatment (all numeric vs curated)
- Walk-forward fold count
- Model serialization format
- Optuna optimization metric
- CLI flag set beyond --target
- Model artifact storage location
- Feature importance output format

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — FEAT-01 through FEAT-04 (feature engineering), MODL-01 through MODL-05 (model training)
- `.planning/ROADMAP.md` — Phase 25 success criteria (5 items: spread model, total model, lag audit, early-season safety, feature importance)

### Prior Phase Context
- `.planning/phases/23-cross-source-features-and-integration/23-CONTEXT.md` — Feature vector assembly test (337 columns, 8 Silver sources, join on [team, season, week]), null policy, integration test patterns

### Data Model
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Prediction feature categories, Silver layer column specs, XGBoost-only decision rationale

### Existing Code (must read before implementing)
- `src/config.py` — `SILVER_TEAM_S3_KEYS` (8 team Silver paths), `SILVER_PLAYER_S3_KEYS` (5 player paths)
- `src/team_analytics.py` — PBP metrics, tendencies, SOS, situational, PBP-derived compute functions
- `src/game_context.py` — Weather, rest, travel, coaching; `_unpivot_schedules()` pattern
- `src/utils.py` — `download_latest_parquet()` read convention
- `tests/test_feature_vector.py` — Existing integration test for Silver feature vector assembly

### State & Decisions
- `.planning/STATE.md` — Accumulated decisions: XGBoost only, differential features, conservative hyperparameters, 2024 holdout, Vegas exclusion, overfitting concerns (~1,900 games with 180+ features)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `download_latest_parquet()` in `src/utils.py` — Standard read pattern for all Silver/Bronze sources; use for loading training data
- `SILVER_TEAM_S3_KEYS` in `src/config.py` — 8 team Silver paths to read for feature assembly
- `tests/test_feature_vector.py` — Existing integration test validates 337-column join works; reference for assembly logic
- `_unpivot_schedules()` in `src/game_context.py` — Produces per-team rows with game_id; pattern for game-level feature construction

### Established Patterns
- Silver data stored as per-season parquet under `data/silver/teams/{metric_type}/season=YYYY/`
- `download_latest_parquet()` resolves timestamped filenames to latest version
- Scripts follow CLI pattern: argparse with `--season`, `--week`, descriptive `--help`
- Test files: `tests/test_{module}.py` with pytest

### Integration Points
- Silver team data (8 paths) → feature assembly input
- Schedules Bronze (`home_score`/`away_score`, `spread_line`) → game labels (actual margin, actual total)
- New `models/` or `data/gold/models/` → model artifact output
- `src/config.py` → Add model-related config constants
- `scripts/` → New `train_prediction_model.py`

</code_context>

<specifics>
## Specific Ideas

- Realistic ATS accuracy expectation: 52-55%. Anything above 58% should trigger leakage investigation (from STATE.md blockers)
- Verify `spread_line` in schedules is closing line (not opening) before using as backtesting target (from STATE.md blockers)
- ~1,900 training games with 180+ features is high-dimensional for the sample size — regularization and feature selection critical

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 25-feature-assembly-and-model-training*
*Context gathered: 2026-03-20*
