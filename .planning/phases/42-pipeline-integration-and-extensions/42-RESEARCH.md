# Phase 42: Pipeline Integration and Extensions - Research

**Researched:** 2026-03-31
**Domain:** ML projection pipeline integration, conformal prediction intervals, team constraints
**Confidence:** HIGH

## Summary

Phase 42 wires the Phase 40 QB ML model (SHIP, 75% holdout improvement) into the existing projection pipeline while preserving the heuristic engine for RB/WR/TE (all SKIP in ship gate). The integration is a routing layer on top of existing infrastructure -- not a rewrite. The `--ml` flag on `generate_projections.py` reads `ship_gate_report.json` to decide per-position routing, calls `predict_player_stats()` for shipped positions, and falls back to `generate_weekly_projections()` for the rest.

MAPIE 1.3.0 (conformal prediction intervals) is compatible with the project's Python 3.9 + scikit-learn 1.6.1 stack. It wraps existing XGBoost models via `MapieRegressor` with `method="plus"` (jackknife+) to produce player-specific prediction intervals for QB, replacing the heuristic variance bands. For RB/WR/TE, the existing `add_floor_ceiling()` remains unchanged.

Team-total constraints are soft (warnings only, no normalization) using the existing `compute_implied_team_totals()` formula from `player_analytics.py`. Preseason mode stays fully heuristic with an additive draft capital boost for rookies using the `draft_value` already in the Silver historical table.

**Primary recommendation:** Build a new `src/ml_projection_router.py` module that handles ship-gate reading, ML prediction, heuristic fallback, and MAPIE interval computation -- keeping `projection_engine.py` untouched as the heuristic engine.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: `--ml` flag routes per position based on `ship_gate_report.json`: QB -> ML, RB/WR/TE -> heuristic
- D-02: No blending -- pure routing. No ML+heuristic mix
- D-03: Output format identical to current projections (same columns). Draft assistant and weekly pipeline consume with zero code changes
- D-04: Default without `--ml` is unchanged (pure heuristic). `--ml` is opt-in
- D-05: Automatic fallback for: SKIP positions, rookies (all NaN), players with <3 games
- D-06: Silent fallback, only `projection_source` column ("ml"/"heuristic") differs
- D-07: Ship gate report read at runtime; if missing, full heuristic with warning
- D-08: Soft constraints only -- no forced normalization
- D-09: Per-team stat shares computed post-projection; flag teams >110% with log warning
- D-10: No adjustment to individual projections from team totals
- D-11: Implied totals from `(total/2) - (spread/2)` for home, `(total/2) + (spread/2)` for away
- D-12: Preseason stays fully heuristic -- ML needs rolling features
- D-13: Draft capital weighting for rookies using `draft_round`, `draft_pick` from Silver historical
- D-14: Draft capital boost is additive, not replacement. First-round > late-round
- D-15: MAPIE for QB only
- D-16: Heuristic floor/ceiling for RB/WR/TE unchanged
- D-17: `MapieRegressor` with `method="plus"` (jackknife+), 80% prediction interval
- D-18: MAPIE import failure -> graceful degradation to heuristic floor/ceiling

### Claude's Discretion
- How to structure the ML projection pipeline function (new module vs extending projection_engine.py)
- MAPIE integration details (which stat models get intervals, how to combine per-stat intervals into fantasy point intervals)
- Draft capital boost formula (linear decay by round, or categorical tiers)
- Soft constraint warning format and threshold tuning
- Weekly pipeline GHA workflow changes (if any)

### Deferred Ideas (OUT OF SCOPE)
- Hard team-total normalization
- ML preseason mode
- MAPIE for RB/WR/TE
- Live Sleeper integration for draft tool
- Automated model retraining at season start
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-02 | Team-total constraint ensuring player share projections sum to ~100% per team | Existing `compute_implied_team_totals()` in `player_analytics.py` provides the formula. Post-projection diagnostic only (D-08 through D-10) |
| PIPE-03 | Weekly pipeline wiring into generate_projections.py and draft_assistant.py | `--ml` flag on CLI, router module reads ship gate, draft_assistant already has `--projections-file` |
| PIPE-04 | Heuristic fallback for rookies, thin-data, and positions where ML doesn't beat baseline | Ship gate report drives position routing; rookie detection via all-NaN rolling columns (existing pattern in `project_position()`) |
| EXTD-01 | Preseason projection mode using prior-season aggregates + draft capital | Extend `generate_preseason_projections()` with `draft_value` from Silver historical table |
| EXTD-02 | ML-derived confidence intervals (MAPIE) for player-specific floor/ceiling bands | MAPIE 1.3.0 compatible with Python 3.9 + sklearn 1.6.1; `MapieRegressor(method="plus")` wraps XGBoost |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mapie | 1.3.0 | Conformal prediction intervals for QB models | scikit-learn-compatible; jackknife+ method provides player-specific intervals with coverage guarantees |

### Supporting (already installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| xgboost | 2.1.4 | QB stat models (already trained) | Loaded via `load_player_model()` |
| scikit-learn | 1.6.1 | MAPIE dependency, model pipeline | Already installed |
| pandas | (installed) | DataFrame processing throughout | All projection logic |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| MAPIE jackknife+ | Quantile regression | Quantile needs retraining; MAPIE wraps existing models |
| New router module | Extend projection_engine.py | Separate module keeps heuristic engine clean and testable independently |

**Installation:**
```bash
pip install mapie==1.3.0
```

**Version verification:** MAPIE 1.3.0 released 2026-02-03. Requires Python >=3.9 (project uses 3.9), scikit-learn >=1.4 (project has 1.6.1). Compatible.

## Architecture Patterns

### Recommended Project Structure
```
src/
  ml_projection_router.py    # NEW: ML/heuristic routing, MAPIE intervals, team constraints
  projection_engine.py       # UNCHANGED: heuristic projection engine
  player_model_training.py   # UNCHANGED: model training, predict_player_stats()
  scoring_calculator.py      # UNCHANGED: fantasy point calculation

scripts/
  generate_projections.py    # MODIFIED: add --ml flag, call router when flag set

models/player/
  ship_gate_report.json      # EXISTING: runtime routing config
  qb/                        # EXISTING: 5 trained XGBoost models
```

### Pattern 1: ML Projection Router
**What:** A new module `ml_projection_router.py` that orchestrates per-position routing based on ship gate verdicts.
**When to use:** When `--ml` flag is set on `generate_projections.py`.
**Example:**
```python
# src/ml_projection_router.py

def generate_ml_projections(
    silver_df: pd.DataFrame,
    opp_rankings: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    schedules_df: Optional[pd.DataFrame] = None,
    implied_totals: Optional[Dict[str, float]] = None,
    model_dir: str = "models/player",
) -> pd.DataFrame:
    """Route per-position to ML or heuristic based on ship gate report."""

    # 1. Read ship gate report
    ship_gate = _load_ship_gate(model_dir)  # returns dict {position: "SHIP"/"SKIP"}

    # 2. For each position:
    #    - If SHIP: load models, predict via predict_player_stats(), apply MAPIE
    #    - If SKIP or missing: call project_position() from projection_engine

    # 3. Combine all positions into single DataFrame
    # 4. Add projection_source column ("ml" / "heuristic")
    # 5. Apply injury adjustments, Vegas multiplier, bye zeroing (same as heuristic)
    # 6. Run team-total constraint check (log warnings only)
    # 7. Return unified DataFrame with identical columns to heuristic output
```

### Pattern 2: Ship Gate Reader
**What:** Read `ship_gate_report.json` at runtime to determine which positions use ML.
**When to use:** Every `--ml` projection run.
**Key detail:** The current report only has RB/WR/TE entries (all SKIP). QB is absent because Phase 40 shipped QB before Phase 41 added ensemble evaluation. The router must treat any position absent from the report with a SHIP verdict if its model files exist in `models/player/{position}/`.
```python
def _load_ship_gate(model_dir: str) -> Dict[str, str]:
    """Load ship gate and infer QB SHIP from model existence."""
    report_path = os.path.join(model_dir, "ship_gate_report.json")
    if not os.path.exists(report_path):
        logger.warning("No ship gate report found; falling back to full heuristic")
        return {}

    with open(report_path) as f:
        report = json.load(f)

    verdicts = {p["position"]: p["verdict"] for p in report.get("positions", [])}

    # QB shipped in Phase 40 but may not appear in Phase 41's report
    # Infer SHIP if QB models exist on disk
    if "QB" not in verdicts:
        qb_model = os.path.join(model_dir, "qb", "passing_yards.json")
        if os.path.exists(qb_model):
            verdicts["QB"] = "SHIP"

    return verdicts
```

### Pattern 3: MAPIE Confidence Intervals for QB
**What:** Wrap trained XGBoost models with `MapieRegressor` to produce per-stat prediction intervals, then combine into fantasy point floor/ceiling.
**When to use:** QB projections when MAPIE is available.
**Key design:** Per-stat intervals (e.g., passing_yards floor/ceiling) are propagated through the scoring formula to get fantasy point floor/ceiling.
```python
try:
    from mapie.regression import MapieRegressor
    HAS_MAPIE = True
except ImportError:
    HAS_MAPIE = False

def compute_mapie_intervals(
    model: xgb.XGBRegressor,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_predict: pd.DataFrame,
    alpha: float = 0.20,  # 80% interval -> alpha=0.20
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wrap XGBoost model with MAPIE for prediction intervals.

    Returns: (point_pred, lower_bound, upper_bound)
    """
    mapie = MapieRegressor(estimator=model, method="plus", cv="prefit")
    mapie.fit(X_train, y_train)  # calibration on training residuals
    y_pred, y_pis = mapie.predict(X_predict, alpha=alpha)
    return y_pred, y_pis[:, 0, 0], y_pis[:, 1, 0]
```

### Pattern 4: Fantasy Point Interval Propagation
**What:** Convert per-stat intervals into fantasy point floor/ceiling.
**When to use:** After MAPIE generates per-stat bounds for QB.
**Approach:** Floor = apply scoring formula to all stat floors (min yards, min TDs, max INTs). Ceiling = apply to all stat ceilings (max yards, max TDs, min INTs).
```python
def compute_fantasy_intervals(
    stat_intervals: Dict[str, Tuple[float, float, float]],  # stat -> (pred, lower, upper)
    scoring_format: str,
) -> Tuple[float, float, float]:
    """Convert per-stat intervals to fantasy point intervals.

    Floor: use lower bounds for positive stats, upper for negative (INTs).
    Ceiling: use upper bounds for positive stats, lower for negative.
    """
    floor_stats = {}
    ceiling_stats = {}
    for stat, (pred, lower, upper) in stat_intervals.items():
        if stat == "interceptions":
            floor_stats[stat] = upper    # more INTs = lower floor
            ceiling_stats[stat] = lower  # fewer INTs = higher ceiling
        else:
            floor_stats[stat] = max(0, lower)
            ceiling_stats[stat] = upper

    # Score each scenario
    floor_pts = _score_single_row(floor_stats, scoring_format)
    ceiling_pts = _score_single_row(ceiling_stats, scoring_format)
    pred_pts = _score_single_row(
        {s: v[0] for s, v in stat_intervals.items()}, scoring_format
    )
    return pred_pts, max(0, floor_pts), ceiling_pts
```

### Pattern 5: Draft Capital Boost for Preseason
**What:** Additive boost to rookie preseason projections based on draft position.
**When to use:** `generate_preseason_projections()` when `--ml` flag is set (but still heuristic).
**Formula recommendation:** Linear decay by overall pick, capped at 20% boost for pick 1.
```python
def draft_capital_boost(draft_ovr: float, position: str) -> float:
    """Additive multiplier for rookie preseason projections.

    Pick 1: 1.20 (20% boost)
    Pick 32: 1.06 (6% boost)
    Pick 64+: 1.00 (no boost)
    Undrafted/NaN: 1.00
    """
    if pd.isna(draft_ovr) or draft_ovr >= 64:
        return 1.0
    # Linear from 1.20 at pick 1 to 1.00 at pick 64
    boost = 1.20 - (draft_ovr - 1) * (0.20 / 63)
    return round(max(1.0, boost), 3)
```

### Pattern 6: Team-Total Constraint Check
**What:** Post-projection diagnostic computing per-team stat shares vs implied totals.
**When to use:** After all projections are assembled (both ML and heuristic).
```python
def check_team_total_coherence(
    projections: pd.DataFrame,
    implied_totals: Dict[str, float],
    threshold: float = 1.10,  # 110% warning threshold
) -> List[str]:
    """Log warnings for teams whose projected player shares exceed threshold."""
    warnings = []
    for team, team_total in implied_totals.items():
        team_players = projections[projections["recent_team"] == team]
        # Check rushing share
        proj_rush_yds = team_players["proj_rushing_yards"].sum()
        # Rough rushing share: ~40% of team total in yards
        # Check receiving share, passing share, etc.
        total_proj_pts = team_players["projected_points"].sum()
        if total_proj_pts > team_total * threshold:
            warnings.append(
                f"WARN: {team} projected {total_proj_pts:.1f} pts "
                f"vs implied {team_total:.1f} ({total_proj_pts/team_total:.0%})"
            )
    return warnings
```

### Anti-Patterns to Avoid
- **Modifying projection_engine.py for ML logic:** The heuristic engine is battle-tested with 571+ tests. Keep it as-is; build ML routing alongside it.
- **Blending ML + heuristic predictions:** D-02 explicitly forbids this. Pure routing per position.
- **Hard-coding QB as the shipped position:** Read from ship gate report at runtime so future positions can ship without code changes.
- **Normalizing player projections to team totals:** D-08/D-10 explicitly forbid adjustment. Warnings only.
- **Training MAPIE from scratch:** Use `cv="prefit"` to wrap existing trained models. Do not retrain.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prediction intervals | Custom quantile/bootstrap | MAPIE `MapieRegressor` | Conformal guarantees, wraps existing models, well-tested |
| Implied team totals | Custom formula | `compute_implied_team_totals()` from `player_analytics.py` | Already implemented and tested |
| Fantasy point calculation | Custom scoring | `calculate_fantasy_points_df()` from `scoring_calculator.py` | Handles all 3 scoring formats |
| Model loading | Custom JSON parsing | `load_player_model()` from `player_model_training.py` | Already handles XGBoost JSON format |
| Ship gate reading | Hardcoded position checks | `ship_gate_report.json` runtime read | Future-proof for when more positions ship |

## Common Pitfalls

### Pitfall 1: Ship Gate Report Missing QB
**What goes wrong:** The current `ship_gate_report.json` only contains RB/WR/TE (all SKIP) because Phase 41 ran the ensemble evaluation which only tests positions that were candidates for improvement. QB shipped in Phase 40 and is not in the Phase 41 report.
**Why it happens:** Two-stage evaluation in Phase 41 -- features-only then ensemble. QB already shipped, so Phase 41 skipped it.
**How to avoid:** The router must check for QB model files on disk as a SHIP signal when QB is absent from the report. The `models/player/qb/` directory contains 5 trained models (passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds).
**Warning signs:** QB getting heuristic projections when `--ml` is used even though models exist.

### Pitfall 2: MAPIE cv="prefit" Requires Training Data
**What goes wrong:** `MapieRegressor(cv="prefit")` still needs `fit(X_train, y_train)` to compute conformity scores (residuals). You cannot skip the fit step even though the underlying model is already trained.
**Why it happens:** MAPIE needs training set residuals to calibrate prediction intervals. It does not retrain the model but needs the training data to compute the conformity scores.
**How to avoid:** Load the training data (from player feature assembly for the appropriate seasons) when computing MAPIE intervals. Cache the calibrated MAPIE wrapper if performance is a concern.
**Warning signs:** Empty prediction intervals or MAPIE raising errors about unfitted estimator.

### Pitfall 3: Per-Stat Intervals to Fantasy Point Intervals
**What goes wrong:** Naively adding per-stat intervals produces unrealistically wide fantasy point ranges because stat errors are correlated (a QB having a bad passing day likely has fewer TDs too).
**Why it happens:** Independence assumption between stat intervals is violated.
**How to avoid:** Use the floor/ceiling approach (all floors for bad scenario, all ceilings for good scenario) rather than trying to compute exact joint intervals. This deliberately produces conservative bounds that are intuitive to users.
**Warning signs:** QB floor at 0 or ceiling at 60+ fantasy points.

### Pitfall 4: Feature Column Mismatch at Prediction Time
**What goes wrong:** ML models were trained on specific SHAP-selected feature sets (stored in `feature_selection/*.json`). If the prediction-time feature assembly produces different columns, predictions fail.
**Why it happens:** Feature assembly from Silver data at prediction time may have missing columns if data sources are unavailable.
**How to avoid:** Load the feature columns from the model metadata (`_meta.json` sidecar) and ensure prediction-time data includes all required features. Fill missing features with 0 or NaN and let XGBoost handle missing values natively.
**Warning signs:** KeyError on feature columns or shape mismatch in model.predict().

### Pitfall 5: Rookie Detection Conflict Between ML and Heuristic
**What goes wrong:** ML fallback for rookies (D-05: all NaN rolling features) must produce output in the same format as ML predictions, not heuristic format.
**Why it happens:** ML output has `pred_{stat}` columns; heuristic has `proj_{stat}` columns. Both need to end up with the same final columns.
**How to avoid:** Standardize all output to `proj_{stat}` + `projected_points` + `projection_source` + `floor` + `ceiling` regardless of source. The router handles column renaming.
**Warning signs:** Draft assistant or weekly pipeline breaking on column name differences.

## Code Examples

### Loading Ship Gate and QB Models
```python
# From models/player/qb/passing_yards_meta.json:
# - 80 features per model
# - Training seasons: 2020-2024
# - Features stored in feature_selection/{group}.json

import json
import os
from player_model_training import load_player_model, predict_player_stats, POSITION_STAT_PROFILE

def load_shipped_models(model_dir: str, position: str) -> dict:
    """Load all stat models for a shipped position."""
    models = {}
    for stat in POSITION_STAT_PROFILE[position]:
        try:
            model = load_player_model(position, stat, model_dir)
            models[stat] = {"model": model}
        except Exception as e:
            logger.warning(f"Could not load {position}/{stat}: {e}")
    return models
```

### MAPIE Integration (QB Only)
```python
from mapie.regression import MapieRegressor

# For each QB stat model:
model = load_player_model("QB", "passing_yards", "models/player")
mapie_model = MapieRegressor(estimator=model, method="plus", cv="prefit")

# Calibrate on training data (needed for conformity scores)
mapie_model.fit(X_train, y_train)

# Predict with intervals
y_pred, y_pis = mapie_model.predict(X_new, alpha=0.20)  # 80% interval
# y_pred shape: (n_samples,)
# y_pis shape: (n_samples, 2, 1) -> [:, 0, 0] = lower, [:, 1, 0] = upper
```

### CLI Integration Point
```python
# In scripts/generate_projections.py main():
parser.add_argument('--ml', action='store_true',
                    help='Use ML models for shipped positions (QB)')

# In weekly mode:
if args.ml:
    from ml_projection_router import generate_ml_projections
    projections = generate_ml_projections(
        silver_df, opp_rankings,
        season=args.season, week=args.week,
        scoring_format=args.scoring,
        schedules_df=schedules_df,
        implied_totals=implied_totals,
    )
else:
    projections = generate_weekly_projections(...)  # existing path unchanged
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Heuristic-only projections | ML routing per position | Phase 42 (new) | QB gets 75% MAE improvement |
| Fixed variance floor/ceiling | MAPIE conformal intervals | Phase 42 (new) | Player-specific prediction bands for QB |
| No team coherence check | Soft constraint warnings | Phase 42 (new) | Diagnostic for over-projection |
| Rookie baseline only | Draft capital boost in preseason | Phase 42 (new) | Better preseason rookie rankings |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via `python -m pytest`) |
| Config file | None (uses defaults) |
| Quick run command | `python -m pytest tests/test_ml_projection_router.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-02 | Team-total constraint warnings logged for >110% share teams | unit | `python -m pytest tests/test_ml_projection_router.py::TestTeamTotalConstraints -x` | Wave 0 |
| PIPE-03 | `--ml` flag routes QB to ML, RB/WR/TE to heuristic; output format matches | unit + integration | `python -m pytest tests/test_ml_projection_router.py::TestMLRouting -x` | Wave 0 |
| PIPE-04 | Rookies/thin-data/SKIP positions fall back to heuristic silently | unit | `python -m pytest tests/test_ml_projection_router.py::TestHeuristicFallback -x` | Wave 0 |
| EXTD-01 | Preseason mode with draft capital boost produces ranked projections | unit | `python -m pytest tests/test_ml_projection_router.py::TestPreseasonDraftCapital -x` | Wave 0 |
| EXTD-02 | MAPIE intervals for QB produce floor/ceiling; graceful degradation if missing | unit | `python -m pytest tests/test_ml_projection_router.py::TestMAPIEIntervals -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_ml_projection_router.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ml_projection_router.py` -- covers PIPE-02, PIPE-03, PIPE-04, EXTD-01, EXTD-02
- [ ] MAPIE install: `pip install mapie==1.3.0` -- not currently installed
- [ ] Feature selection JSON fixtures for test mocking (feature_selection/*.json already exist on disk)

## Open Questions

1. **MAPIE calibration data loading**
   - What we know: `MapieRegressor(cv="prefit")` requires `fit(X_train, y_train)` for conformity scores. The training data is assembled by `assemble_player_features()` for seasons 2020-2024.
   - What's unclear: Whether to re-assemble training data at prediction time or cache it. Re-assembly takes ~10-15 seconds.
   - Recommendation: Cache the calibrated MAPIE wrapper alongside the model files. If cache miss, re-assemble from Silver data. This avoids slow prediction runs.

2. **QB ship gate entry**
   - What we know: Current `ship_gate_report.json` only has RB/WR/TE. QB shipped in Phase 40 before Phase 41's ensemble evaluation.
   - What's unclear: Whether to retroactively add QB to the report or handle at runtime.
   - Recommendation: Handle at runtime in the router (check model files on disk). No manual editing of the report needed.

## Sources

### Primary (HIGH confidence)
- `src/projection_engine.py` -- Full heuristic pipeline: `generate_weekly_projections()`, `add_floor_ceiling()`, `project_position()`
- `src/player_model_training.py` -- `predict_player_stats()`, `load_player_model()`, `ship_gate_verdict()`
- `scripts/generate_projections.py` -- CLI entry point, `--ml` integration target
- `models/player/ship_gate_report.json` -- Runtime config (RB SKIP, WR SKIP, TE SKIP; QB absent)
- `models/player/qb/*.json` -- 5 trained XGBoost stat models
- `src/player_analytics.py` -- `compute_implied_team_totals()` formula
- `scripts/draft_assistant.py` -- `--projections-file` flag already supports external projections

### Secondary (MEDIUM confidence)
- [MAPIE PyPI](https://pypi.org/project/MAPIE/) -- v1.3.0, Python >=3.9, sklearn >=1.4
- [MAPIE docs](https://mapie.readthedocs.io/) -- `MapieRegressor`, `method="plus"`, `cv="prefit"`

### Tertiary (LOW confidence)
- MAPIE `cv="prefit"` behavior with XGBoost specifically -- verified via docs but not tested in this codebase yet

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- MAPIE version/compat verified, all other libs already installed
- Architecture: HIGH -- all integration points examined in source code
- Pitfalls: HIGH -- ship gate report structure confirmed, MAPIE API verified against docs

**Research date:** 2026-03-31
**Valid until:** 2026-04-30 (stable libraries, no fast-moving APIs)
