# Architecture: ML-Based Player Fantasy Prediction System

**Domain:** Player-level fantasy football prediction integrated into existing Medallion Architecture
**Researched:** 2026-03-29
**Confidence:** HIGH (based on direct inspection of existing codebase: feature_engineering.py, projection_engine.py, ensemble_training.py, player_analytics.py, player_advanced_analytics.py, config.py, and all Silver/Bronze schemas)

## System Overview

```
Bronze (16 data types)
    |
    v
Silver Layer
    |
    +-- Player Sources (EXISTING)                Team Sources (EXISTING)
    |   - players/usage (113 cols)               - teams/pbp_metrics (63 cols)
    |   - players/advanced (119 cols)            - teams/tendencies
    |   - players/historical (63 cols)           - teams/sos
    |   - defense/positional (opp ranks)         - teams/situational
    |                                            - teams/player_quality (28 cols)
    |                                            - teams/game_context
    |                                            - teams/market_data
    |                                            + 3 more team sources
    |
    +-- NEW: Player Feature Vector Assembly  <--- player_feature_engineering.py
    |   (player-week rows, ~150-200 cols)
    |   Merges: usage + advanced + historical + opp_rankings + team context
    |
    v
Gold Layer
    |
    +-- Game Predictions (EXISTING)              Player Predictions (NEW)
    |   - game-level rows                        - player-week rows
    |   - XGB+LGB+CB+Ridge ensemble              - position-specific ensembles
    |   - spread + total targets                  - stat-level targets (yards, TDs, etc.)
    |   - 120 SHAP-selected features             - game-level constraints (implied totals)
    |
    +-- Fantasy Projections (EXISTING, later REPLACED)
        - projection_engine.py (heuristic)
        - roll3/roll6/std blending
        - usage mult, matchup factor, Vegas mult
```

## Recommended Architecture: Two-Stage Hierarchical Prediction

### Why Two-Stage Over Direct Fantasy Points Prediction

Predicting fantasy points directly is tempting but architecturally wrong for this system. The existing game prediction ensemble already produces implied team totals and game script signals. A two-stage approach -- (1) predict opportunity volume, then (2) predict efficiency given opportunity -- leverages the existing game model as a top-down constraint and decomposes the problem into more learnable sub-problems.

**Stage 1: Opportunity Models** predict volume metrics per player-week:
- QB: pass attempts, rush attempts
- RB: carries, targets
- WR: targets
- TE: targets

**Stage 2: Efficiency Models** predict per-unit production:
- QB: yards/attempt, TD rate, INT rate, rush yards/attempt, rush TD rate
- RB: yards/carry, TD rate, yards/reception, rec TD rate
- WR: catch rate, yards/reception, TD rate
- TE: catch rate, yards/reception, TD rate

**Fantasy points** = opportunity x efficiency, converted through `scoring_calculator.py`.

### Why Not a Single Fantasy Points Model

1. **Interpretability**: "He'll get 18 targets but only a 60% catch rate" is actionable for start/sit. A single number is not.
2. **Stability**: Opportunity (snap share, target share) is 2-3x more stable week-to-week than raw production. Separate models can weight stability differently.
3. **Game-level coherence**: Team target shares must sum to ~1.0. Opportunity models can be constrained; a single points model cannot.
4. **Existing infrastructure**: The game prediction ensemble already produces implied totals. Opportunity models naturally accept this as a constraint.

### Component Responsibilities

| Component | Responsibility | Status |
|-----------|----------------|--------|
| `src/player_feature_engineering.py` | Assemble player-week feature vectors from Silver sources | NEW |
| `src/player_model_training.py` | Position-specific model training with walk-forward CV | NEW |
| `src/player_prediction.py` | Inference: opportunity x efficiency -> stats -> fantasy points | NEW |
| `src/player_constraints.py` | Game-level allocation: implied totals -> team share budgets | NEW |
| `scripts/train_player_models.py` | CLI for training all position/target models | NEW |
| `scripts/generate_player_predictions.py` | CLI for weekly player predictions | NEW |
| `scripts/backtest_player_predictions.py` | CLI for per-position MAE/RMSE/correlation evaluation | NEW |
| `src/projection_engine.py` | Heuristic fallback (kept for rookies/thin data) | EXISTING, AUGMENTED |
| `src/feature_engineering.py` | Game-level feature assembly (unchanged) | EXISTING |
| `src/ensemble_training.py` | Game prediction ensemble (unchanged) | EXISTING |
| `src/scoring_calculator.py` | Fantasy point calculation (unchanged) | EXISTING |

## Player Feature Vector Assembly

### Data Flow: player_feature_engineering.py

```
Bronze player_weekly (per player-week, raw stats)
    |
    v
Silver players/usage (113 cols: rolling avgs, shares, snap_pct)
    +
Silver players/advanced (119 cols: NGS separation/RYOE/TTT, PFR pressure, QBR)
    +
Silver players/historical (63 cols: combine measurables, draft capital)
    +
Silver defense/positional (opp_rankings: per-position rank 1-32)
    +
Silver teams/game_context (weather, rest, dome, travel -- per team-week)
    +
Silver teams/player_quality (QB EPA, injury impact -- per team-week)
    +
Gold game predictions (implied team totals, game script -- per game)
    |
    v
Player Feature Vector (~150-200 cols per player-week)
    Grouped by: [player_id, season, week]
    Join keys: [recent_team, season, week] for team sources
               [player_id, season, week] for player sources
               [opponent, season, week] for defense/opp sources
```

### Key Join Strategy

The existing system joins team sources on `[team, season, week]` and computes home-away differentials for game-level rows. The player system is fundamentally different:

1. **Base table**: Silver `players/usage` -- one row per player per week (5,597 rows/season for all positions)
2. **Player advanced**: Left join on `[player_gsis_id, season, week]` (NGS/PFR/QBR rolling metrics)
3. **Historical profiles**: Left join on `gsis_id` (static: combine, draft capital, height/weight)
4. **Opponent rankings**: Left join on `[opponent_team, season, week, position]` (defensive rank)
5. **Team context**: Left join on `[recent_team, season, week]` (weather, rest, dome, travel)
6. **Team quality**: Left join on `[recent_team, season, week]` (QB EPA, injury impact)
7. **Game predictions**: Left join on `[recent_team, season, week]` (predicted team total, game script probability)

### Feature Categories

| Category | Source | Example Features | Count (est.) |
|----------|--------|------------------|--------------|
| Player volume rolling | usage | targets_roll3, carries_roll3, snap_pct_roll6 | ~45 |
| Player share rolling | usage | target_share_roll3, carry_share_roll6, air_yards_share_std | ~18 |
| Player efficiency rolling | usage | receiving_yards per target (derived), rushing_yards per carry (derived) | ~20 |
| Advanced metrics | advanced | ngs_avg_separation_roll3, pfr_times_pressured_pct_roll3, ngs_rush_yards_over_expected_roll3 | ~40 |
| Physical profile | historical | speed_score, bmi, burst_score, draft_round, draft_value | ~12 |
| Opponent defense | opp_rankings | opp_rank (1-32 by position) | ~1-3 |
| Team offense context | team quality + pbp | qb_passing_epa_roll3, off_epa_per_play_roll3 | ~10 |
| Game environment | game_context | is_dome, temperature, wind_speed, rest_days | ~8 |
| Game prediction | Gold game preds | predicted_team_total, predicted_game_total, predicted_spread | ~3 |
| Position indicator | derived | is_QB, is_RB, is_WR, is_TE (for shared models) or implicit per model | ~0-4 |

**Estimated total: ~160-165 columns** before SHAP selection.

### Derived Efficiency Features (Not in Current Silver)

These must be computed during feature assembly (not stored in Silver):

```python
# Per-target efficiency
receiving_yards_per_target_roll3 = receiving_yards_roll3 / targets_roll3
receiving_td_rate_roll3 = receiving_tds_roll3 / targets_roll3

# Per-carry efficiency
rushing_yards_per_carry_roll3 = rushing_yards_roll3 / carries_roll3
rushing_td_rate_roll3 = rushing_tds_roll3 / carries_roll3

# Per-attempt efficiency (QB)
passing_yards_per_attempt_roll3 = passing_yards_roll3 / attempts_roll3  # needs attempts in usage
passing_td_rate_roll3 = passing_tds_roll3 / attempts_roll3
int_rate_roll3 = interceptions_roll3 / attempts_roll3
```

Guard against division by zero with `np.where(denominator > 0, numerator/denominator, np.nan)`.

## Training Data Structure

### Unit of Observation: Player-Week

Unlike the game prediction system (one row per game, ~272 rows per season), the player prediction system operates at player-week granularity:

| Filter | Approximate Rows/Season | Total (2020-2024) |
|--------|------------------------|--------------------|
| All players, all weeks | ~5,600 | ~28,000 |
| QB only | ~300 | ~1,500 |
| RB only | ~1,200 | ~6,000 |
| WR only | ~1,800 | ~9,000 |
| TE only | ~800 | ~4,000 |

### Training Seasons

Use `PLAYER_DATA_SEASONS` (2020-2025) from config.py, not `PREDICTION_SEASONS` (2016-2025). Player weekly data quality before 2020 is inconsistent, and NGS/PFR advanced stats start at 2016-2018 with sparse early coverage. Using 2020+ gives 5 clean seasons of player data.

Holdout: 2025 (consistent with current game prediction holdout `HOLDOUT_SEASON`).

### Walk-Forward CV

Identical pattern to `ensemble_training.py`, adapted for player-weeks:

```
Fold 1: Train 2020, Validate 2021
Fold 2: Train 2020-2021, Validate 2022
Fold 3: Train 2020-2022, Validate 2023
Fold 4: Train 2020-2023, Validate 2024
Holdout: Train 2020-2024, Test 2025 (sealed)
```

### Target Variables

For each position, the models predict raw stat counts (not fantasy points):

| Position | Opportunity Targets | Efficiency Targets |
|----------|--------------------|--------------------|
| QB | attempts (pass), carries (rush) | passing_yards, passing_tds, interceptions, rushing_yards, rushing_tds |
| RB | carries, targets | rushing_yards, rushing_tds, receptions, receiving_yards, receiving_tds |
| WR | targets | receptions, receiving_yards, receiving_tds |
| TE | targets | receptions, receiving_yards, receiving_tds |

**Why predict stats, not fantasy points**: Stats are scoring-system-agnostic. One model serves PPR, Half-PPR, and Standard. `scoring_calculator.py` handles the conversion.

## Game-Level Constraints: Implied Totals

### How Game Predictions Feed Player Predictions

The existing game prediction ensemble produces `predicted_team_total` (implied points for each team). This is the most valuable top-down signal for player predictions:

```
Game Ensemble: KC predicted total = 27.5
    |
    v
Implied passing yards budget: ~270 (roughly 10 yards per team point for pass-heavy teams)
Implied rushing yards budget: ~110
    |
    v
Player share allocation: Mahomes gets ~95% of pass attempts,
    Isiah Pacheco gets ~55% of carries, etc.
```

### Implementation: player_constraints.py

```python
def allocate_team_budget(
    predicted_team_total: float,
    team: str,
    season: int,
    week: int,
    team_tendencies: pd.DataFrame,  # pass_rate, rush_rate from Silver
) -> dict:
    """Convert predicted team points into stat budgets.

    Returns:
        {
            'implied_pass_attempts': 35.2,
            'implied_rush_attempts': 25.1,
            'implied_targets': 35.2,  # ~= pass_attempts
            'implied_passing_yards': 268.0,
            'implied_rushing_yards': 112.0,
        }
    """
```

### Constraint Application Strategy

Use game-level constraints as **features**, not hard constraints. Let the model learn the relationship between implied team total and player volume. Hard post-hoc normalization (forcing shares to sum to 1.0) introduces bias. Instead:

1. Include `predicted_team_total` and `predicted_game_total` as features in opportunity models.
2. Include `team_pass_rate_roll3` and `team_rush_rate_roll3` as features.
3. **Optional post-hoc adjustment**: After prediction, if team targets sum to >110% of implied attempts, proportionally scale down. This is a light touch, not the primary mechanism.

## Model Architecture Per Position

### Recommended: Separate Models Per Position, Single Model Per Stat

Train one gradient boosting model per (position, target_stat) pair. This avoids the complexity of multi-output models while letting each stat have its own feature importance pattern.

```
Models to train (minimum viable):
    QB:  targets=5 (attempts, carries, pass_yds, pass_tds, rush_yds)  -- INTs and rush_tds secondary
    RB:  targets=5 (carries, targets, rush_yds, rush_tds, rec_yds)   -- receptions ~= f(targets, catch_rate)
    WR:  targets=4 (targets, receptions, rec_yds, rec_tds)
    TE:  targets=4 (targets, receptions, rec_yds, rec_tds)
    -------
    Total: ~18 models (2 targets x 18 = 36 with spread/total, but player is single-target)
```

### Why Not Multi-Output or Chained Models

1. **Multi-output regression**: XGBoost/LightGBM don't natively support correlated multi-output. Workarounds (MultiOutputRegressor) train independent models anyway.
2. **Chained models** (predict targets -> use predicted targets to predict yards): Cascading errors. If target prediction is off by 2, yards prediction inherits that error.
3. **Single-stat models with shared features**: Simple, independent training, each model gets SHAP selection independently, no error propagation.

### Model Framework

Use the same XGB+LGB+CB+Ridge stacking ensemble from `ensemble_training.py`. The infrastructure already exists. Adapt the training loop to:
- Accept player-week DataFrames instead of game-level
- Use position-filtered data (e.g., only WR rows for WR models)
- Save to `models/player_ensemble/{position}/{target}/` directory structure

```
models/
    ensemble/           # Existing game prediction models
    player_ensemble/    # NEW
        QB/
            pass_attempts/   xgb.json, lgb.txt, cb.cbm, ridge.pkl, metadata.json
            pass_yards/      ...
            ...
        RB/
            carries/         ...
            rush_yards/      ...
            targets/         ...
            ...
        WR/
            targets/         ...
            receptions/      ...
            rec_yards/       ...
            rec_tds/         ...
        TE/
            targets/         ...
            receptions/      ...
            rec_yards/       ...
            rec_tds/         ...
```

## Integration with Existing Code

### What Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `src/config.py` | MODIFY | Add PLAYER_MODEL_DIR, PLAYER_HOLDOUT_SEASON, position stat target configs |
| `src/player_feature_engineering.py` | NEW | Player-week feature vector assembly from Silver sources |
| `src/player_model_training.py` | NEW | Adapts ensemble_training pattern for player-week data |
| `src/player_prediction.py` | NEW | Inference pipeline: features -> models -> stats -> fantasy points |
| `src/player_constraints.py` | NEW | Game prediction -> team budget -> player share constraints |
| `scripts/train_player_models.py` | NEW | CLI: train all position/stat models |
| `scripts/generate_player_predictions.py` | NEW | CLI: weekly player predictions with game-level constraints |
| `scripts/backtest_player_predictions.py` | NEW | CLI: per-position MAE/RMSE/correlation evaluation |
| `scripts/generate_projections.py` | MODIFY | Add `--ml` flag to use ML predictions instead of heuristic |

### What Does NOT Change

| File | Reason |
|------|--------|
| `src/feature_engineering.py` | Game-level only; player system uses its own assembly |
| `src/ensemble_training.py` | Game prediction training unchanged; player system adapts the pattern |
| `src/scoring_calculator.py` | Fantasy point conversion is scoring-system math, unchanged |
| `src/player_analytics.py` | Silver transformation logic unchanged; still produces usage metrics |
| `src/player_advanced_analytics.py` | Silver transformation logic unchanged; still produces advanced profiles |
| All Silver transformation scripts | Silver layer produces the same outputs; player feature engineering reads them |

### Transition Strategy: Heuristic -> ML

Do NOT delete `projection_engine.py`. Instead:

1. **Phase 1**: Build player feature engineering and train models. Compare ML vs heuristic on holdout.
2. **Phase 2**: If ML beats heuristic (MAE < 4.91), `generate_projections.py` gets `--ml` flag.
3. **Phase 3**: ML becomes default. Heuristic becomes fallback for:
   - Rookies with no history (< 3 games played)
   - Players returning from long absence (> 6 weeks missed)
   - New team acquisitions with < 2 games on new team

The `player_prediction.py` module handles this routing:

```python
def predict_player_week(player_row, models, heuristic_fallback=True):
    """Generate prediction for a single player-week.

    Uses ML model if sufficient history exists (>= 3 prior games with valid rolling avgs).
    Falls back to projection_engine heuristic otherwise.
    """
    if _has_sufficient_history(player_row):
        return _ml_predict(player_row, models)
    elif heuristic_fallback:
        return _heuristic_predict(player_row)  # delegates to projection_engine
    else:
        return _rookie_baseline(player_row)
```

## Evaluation Framework

### Metrics (Per Position)

| Metric | What It Measures | Current Heuristic Baseline |
|--------|------------------|---------------------------|
| MAE | Average absolute error in fantasy points | 4.91 (all positions) |
| RMSE | Penalizes large misses | 6.72 |
| Correlation | Rank ordering accuracy | 0.510 |
| Bias | Systematic over/under prediction | -0.60 |
| Per-position MAE | Position-specific accuracy | QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77 |

### Ship-or-Skip Gate

Identical to game prediction ablation pattern:

```
IF ml_holdout_mae < heuristic_holdout_mae for >= 3 of 4 positions:
    SHIP (ML becomes default)
ELSE:
    SKIP (keep heuristic, investigate)
```

### Per-Stat Evaluation

In addition to fantasy point MAE, evaluate individual stat predictions:

```
QB passing_yards MAE, passing_tds MAE, rushing_yards MAE
RB carries MAE, rushing_yards MAE, targets MAE
WR targets MAE, receptions MAE, receiving_yards MAE
TE targets MAE, receptions MAE, receiving_yards MAE
```

This identifies which sub-models are working and which need improvement.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Predicting Fantasy Points Directly

**What people do:** Train a single model to predict PPR fantasy points.
**Why it's wrong:** Couples model to scoring system. Can't serve Standard/Half-PPR without retraining. Loses interpretability of what went wrong (was it volume or efficiency?).
**Do this instead:** Predict raw stats (yards, TDs, receptions), then convert via scoring_calculator.py.

### Anti-Pattern 2: Including Same-Game Stats as Features

**What people do:** Use a player's actual game stats as features (targets in current game to predict yards in current game).
**Why it's wrong:** Data leakage. These stats are unknowable before the game.
**Do this instead:** Only use `_roll3`, `_roll6`, `_std` (shifted) columns and pre-game context. The existing Silver layer already computes these with proper `shift(1)` lag.

### Anti-Pattern 3: Training One Giant Model Across All Positions

**What people do:** Pool all players into one model with position as a categorical feature.
**Why it's wrong:** QB and WR have fundamentally different stat distributions and feature importances. A pooled model compromises on all positions.
**Do this instead:** Separate models per position. The sample sizes (1,500+ per position over 5 seasons) are sufficient for gradient boosting.

### Anti-Pattern 4: Hard-Normalizing Player Shares to Sum to 1.0

**What people do:** After predicting individual player targets, force all players on a team to sum to the team's implied pass attempts.
**Why it's wrong:** Introduces systematic bias. If the model correctly predicts a low-target game for a WR, normalization inflates it back up.
**Do this instead:** Use team implied totals as features. Apply light proportional scaling only if team total exceeds 120% of implied budget (safety valve, not core mechanism).

### Anti-Pattern 5: Using Future Silver Data for Training Labels

**What people do:** Use the actual fantasy_points_ppr column from the same player_weekly row as both label and feature source.
**Why it's wrong:** Rolling averages from the same row already incorporate the target week's data.
**Do this instead:** Labels come from the raw stat columns (rushing_yards, receiving_tds, etc.) of the target week. Features come from `_roll3`, `_roll6`, `_std` columns which are pre-computed with `shift(1)` in Silver.

## Suggested Build Order

Based on dependencies in the existing codebase:

```
Phase 1: Player Feature Vector Assembly
    - Build player_feature_engineering.py
    - Merge Silver player + team + opponent + game prediction sources
    - Derive efficiency features (yards/target, TD rate, etc.)
    - Validate: correct join keys, no leakage, proper lagging
    - Depends on: existing Silver layer (no changes needed)

Phase 2: Model Training Infrastructure
    - Build player_model_training.py (adapt ensemble_training.py pattern)
    - Position-specific walk-forward CV
    - SHAP feature selection per position
    - Save/load model artifacts
    - Depends on: Phase 1 (feature vectors)

Phase 3: Prediction & Evaluation
    - Build player_prediction.py (inference pipeline)
    - Build player_constraints.py (game prediction integration)
    - Build backtest_player_predictions.py
    - Compare ML vs heuristic baseline (MAE 4.91)
    - Ship-or-skip gate
    - Depends on: Phase 2 (trained models)

Phase 4: Integration & Cutover
    - Add --ml flag to generate_projections.py
    - Implement ML/heuristic routing (sufficient history check)
    - Update draft_assistant.py to use ML predictions
    - Depends on: Phase 3 (validated predictions)
```

## Sources

- Direct codebase inspection: `src/feature_engineering.py`, `src/projection_engine.py`, `src/ensemble_training.py`, `src/player_analytics.py`, `src/player_advanced_analytics.py`, `src/config.py`
- Silver layer schema inspection: `data/silver/players/usage/` (113 cols), `data/silver/players/advanced/` (119 cols), `data/silver/players/historical/` (63 cols), `data/silver/defense/positional/` (6 cols), `data/silver/teams/player_quality/` (28 cols)
- [Building a Better Fantasy Football Prediction Model](https://medium.com/@ashimshock/building-a-better-fantasy-football-prediction-model-a-data-driven-approach-8730694ac40a)
- [Predicting Fantasy Football Points Using Machine Learning](https://github.com/zzhangusf/Predicting-Fantasy-Football-Points-Using-Machine-Learning)
- [Bayes-xG: Player and Position Correction using Bayesian Hierarchical Approach](https://pmc.ncbi.nlm.nih.gov/articles/PMC11214280/)
- [A Holistic Approach to Performance Prediction in Collegiate Athletics](https://www.nature.com/articles/s41598-024-51658-8)
- [Fantasy Football AI - Production ML System](https://github.com/cbratkovics/fantasy-football-ai)

---
*Architecture research for: ML-Based Player Fantasy Prediction System*
*Researched: 2026-03-29*
