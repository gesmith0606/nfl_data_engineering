# Phase 25: Feature Assembly and Model Training - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-20
**Phase:** 25-feature-assembly-and-model-training
**Areas discussed:** Feature assembly pipeline, Walk-forward CV design, Model training & tuning, Training CLI & output

---

## Feature Assembly Pipeline

### Module placement

| Option | Description | Selected |
|--------|-------------|----------|
| New src/feature_engineering.py | Dedicated module for assembly, differentials, NaN handling. Clean separation. | |
| Extend src/team_analytics.py | Add alongside existing team metrics. Keeps team logic together. | |
| You decide | Claude picks based on codebase patterns. | ✓ |

**User's choice:** You decide
**Notes:** Claude has discretion on module placement.

### Weeks 1-3 NaN handling

| Option | Description | Selected |
|--------|-------------|----------|
| Fill with season-wide averages | League average per column. Neutral prior. | |
| Fill with zeros | Simple, fast. Risk: may look like worst performance. | |
| Drop early weeks | Exclude Weeks 1-3. Cleanest but loses ~18% of data. | |
| You decide | Claude picks based on ML best practices for tree models. | ✓ |

**User's choice:** You decide
**Notes:** Claude has discretion on NaN strategy.

### Feature scope

| Option | Description | Selected |
|--------|-------------|----------|
| Team-level only | Differential features from 8 Silver team sources only. | ✓ |
| Team + key player indicators | Add QB quality tier and injury-adjusted starter availability. | |

**User's choice:** Team-level only
**Notes:** Aligned with REQUIREMENTS.md Out of Scope.

### Differential feature mapping

| Option | Description | Selected |
|--------|-------------|----------|
| All numeric columns get differentials | Auto-compute home-away for every numeric column. ~170 features. | |
| Curated subset only | Hand-pick most predictive columns. ~50-80 features. | |
| You decide | Claude determines based on feature importance literature and overfitting risk. | ✓ |

**User's choice:** You decide
**Notes:** Claude has discretion.

---

## Walk-Forward CV Design

### CV strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Expanding window | Train on seasons 2016..N, validate on N+1. Standard for sports ML. | ✓ |
| Sliding window (3 seasons) | Train on 3 most recent, validate on next. Captures regime changes. | |
| You decide | Claude picks based on dataset size. | |

**User's choice:** Expanding window
**Notes:** Standard approach, maximizes training data per fold.

### Season range

| Option | Description | Selected |
|--------|-------------|----------|
| Train 2016-2023, holdout 2024 | 8 training seasons. 2024 sealed per BACK-02. | ✓ |
| Train 2018-2023, holdout 2024 | Skip pre-analytics era. 6 seasons. | |
| You decide | Claude determines optimal range. | |

**User's choice:** Train 2016-2023, holdout 2024
**Notes:** Full history, 2024 never touched during tuning.

### Fold count

| Option | Description | Selected |
|--------|-------------|----------|
| One fold per validation season | Each season is a validation fold. 4-5 folds. | |
| You decide | Claude determines fold count. | ✓ |

**User's choice:** You decide

### Intra-season splits

| Option | Description | Selected |
|--------|-------------|----------|
| Season-level only | Fold boundaries at full seasons. Avoids leakage. | ✓ |
| Add intra-season splits | Within-season splits to increase folds. Risk: temporal leakage. | |
| You decide | Claude picks. | |

**User's choice:** Season-level only

---

## Model Training & Tuning

### Optuna trial budget

| Option | Description | Selected |
|--------|-------------|----------|
| 50 trials | Good balance. ~10-15 min on laptop. | ✓ |
| 100 trials | More thorough. ~20-30 min. | |
| You decide | Claude picks. | |

**User's choice:** 50 trials

### Model split

| Option | Description | Selected |
|--------|-------------|----------|
| Separate models | Independent XGBoost per target. Different hyperparameters. | ✓ |
| Shared pipeline, separate heads | Common features, distinct model objects. | |
| You decide | Claude picks. | |

**User's choice:** Separate models

### Model artifacts

| Option | Description | Selected |
|--------|-------------|----------|
| JSON (XGBoost native) | Human-readable, version-controllable, portable. | |
| Pickle/joblib | Standard Python serialization. Full pipeline state. | |
| You decide | Claude picks based on portability and debugging needs. | ✓ |

**User's choice:** You decide

### Validation metric

| Option | Description | Selected |
|--------|-------------|----------|
| MAE | Interpretable: off by X points on average. Standard for spreads. | |
| RMSE | Penalizes large errors more. More conservative predictions. | |
| You decide | Claude picks based on edge detection use case. | ✓ |

**User's choice:** You decide

---

## Training CLI & Output

### Script name

| Option | Description | Selected |
|--------|-------------|----------|
| train_prediction_model.py | Matches roadmap success criteria exactly. | ✓ |
| train_model.py | Shorter. May conflict with future fantasy ML. | |
| You decide | Claude picks. | |

**User's choice:** train_prediction_model.py

### CLI flags

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: --target, --seasons, --tune | Simple flag set. | |
| Full: --target, --seasons, --tune, --trials, --holdout | More flexible. | |
| You decide | Claude designs flag set. | ✓ |

**User's choice:** You decide

### Output directory

| Option | Description | Selected |
|--------|-------------|----------|
| models/ | New top-level directory. | |
| data/gold/models/ | Under Gold layer. Follows medallion convention. | |
| You decide | Claude picks based on project structure. | ✓ |

**User's choice:** You decide

### Feature importance report

| Option | Description | Selected |
|--------|-------------|----------|
| Console table + CSV file | Print top-20 to console, save full ranking to CSV. | |
| Console only | Print top-20, no file. Simple. | |
| You decide | Claude picks based on downstream needs. | ✓ |

**User's choice:** You decide

---

## Claude's Discretion

- Module placement for feature assembly
- NaN handling strategy for early-season sparse data
- Differential feature selection scope
- Walk-forward fold count
- Model serialization format
- Optuna optimization metric
- CLI flag design beyond --target
- Model artifact storage location
- Feature importance output format

## Deferred Ideas

None — discussion stayed within phase scope
