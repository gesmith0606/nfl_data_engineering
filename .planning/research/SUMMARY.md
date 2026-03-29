# Project Research Summary

**Project:** v3.0 Player Fantasy Prediction System
**Domain:** ML-based per-player fantasy football projection (NFL, per-position QB/RB/WR/TE)
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Summary

This project replaces the current heuristic projection engine (MAE 4.91, RMSE 6.72) with a machine-learning ensemble that predicts raw player stats and derives fantasy points via the existing `scoring_calculator.py`. The established approach — gradient boosting ensembles (XGBoost + LightGBM + CatBoost + Ridge stacking) trained on position-specific player-week data with proper walk-forward cross-validation — transfers directly from the v2.0 game prediction system, which saw ATS accuracy improve from 50.0% to 53.0% using this exact pattern. Research confirms that approximately 80% of required features already exist in the Silver layer, making the primary build effort a player-level feature vector assembler and an adapted training pipeline, not new data infrastructure.

The recommended architecture is a two-stage hierarchical approach: predict opportunity volume (targets, carries, snap share) separately from per-touch efficiency (yards/target, TD rate, catch rate), then multiply to produce stat-level predictions. This decomposition is architecturally superior to direct fantasy points prediction because opportunity is 2-3x more stable week-to-week than raw production (target share r=0.70 year-over-year), the two stages have fundamentally different feature importances, and team-level coherence is more tractable at the opportunity stage. Raw stats rather than fantasy points should be the model target, enabling a single trained model to serve PPR, Half-PPR, and Standard scoring formats through the existing `scoring_calculator.py`.

The most significant risks are data leakage (using same-game stats as features) and failing to beat the heuristic baseline, which already captures the strongest signals (rolling averages, usage share, Vegas implied totals, opponent matchup). Research recommends a minimum 4% per-position MAE improvement as the ship-or-skip gate, applied independently to each position rather than aggregate MAE — which can hide QB/WR regression behind TE gains. Only two new library installs are needed: `statsmodels` (variance decomposition during research) and `MAPIE` (calibrated prediction intervals to replace heuristic floor/ceiling). Everything else is already installed and proven.

## Key Findings

### Recommended Stack

The existing stack covers 90% of requirements. The v2.0 game prediction ensemble architecture (XGB+LGB+CB+Ridge stacking, SHAP feature selection, Optuna tuning, walk-forward CV) is the exact pattern to replicate for player-level models. CatBoost should be used with `cat_features=['team', 'opponent']` for native categorical handling. Target encoding via `sklearn.preprocessing.TargetEncoder` (available since scikit-learn 1.3) handles player_id and team_id for XGBoost and LightGBM. No neural networks, no time-series forecasting libraries, no pandas replacement — the existing stack is sufficient.

**Core technologies:**
- XGBoost + LightGBM + CatBoost + Ridge: position-specific ensemble stacking — same proven v2.0 architecture, new player-level targets
- SHAP 0.49.1: per-fold importance + correlation filtering for player feature selection — already in `feature_selector.py`, reuse directly
- Optuna: hyperparameter tuning per position/target pair — already in `train_ensemble.py`, replicate pattern
- statsmodels 0.14.6 (NEW): MixedLM for understanding player vs team variance structure during research phase — not in production pipeline
- MAPIE 1.3.0 (NEW): conformal prediction intervals for floor/ceiling estimates — replaces heuristic `PROJECTION_CEILING_SHRINKAGE` with calibrated coverage guarantees

### Expected Features

Research confirms the feature landscape splits cleanly into what already exists in Silver and what must be assembled or derived. Approximately 80% of required features are already built; the primary work is joining them into a player-week feature vector (~160-165 columns before SHAP selection).

**Must have (table stakes):**
- Player-level feature vector assembler — joins Silver usage (113 cols) + advanced (119 cols) + historical (63 cols) + opponent rankings + team context per player-week
- Position-specific gradient boosting models — separate QB/RB/WR/TE models; different stat distributions and feature importances require separate training
- Walk-forward temporal CV — train on seasons 1..N, predict N+1; identical pattern to game predictions; holdout 2025
- Matchup features (lagged opponent defense vs position rank) — already in Silver `defense/positional`, needs proper shift(1)
- Vegas implied team totals as features — already in Bronze schedules + Silver market_data
- Per-position evaluation — QB/RB/WR/TE MAE reported independently; aggregate MAE alone is insufficient

**Should have (competitive advantage):**
- Opportunity-efficiency decomposition — predict targets/carries/snap% (stable, r~0.70) separately from yards/TD-rate (noisy); enables top-down coherence
- TD regression features — expected TDs from red zone share x historical conversion rate; raw TD rolling averages are the most volatile and least predictive component
- Role momentum features — `snap_pct_roll3 - snap_pct_roll6` as breakout/demotion signal; cheap to compute, high signal for role changes
- QB quality context for skill positions — Silver `player_quality` has QB EPA, backup_qb_start, injury impact; already built, just needs to be joined
- Rookie draft capital features — Silver `players/historical` has combine/draft profiles for 9,892 players; cold-start prior for first-year players
- Team-level top-down constraint — game prediction ensemble's implied team total as feature; light post-processing scaling as safety valve

**Defer (v3.1+):**
- WR-CB matchup graph features — requires Neo4j + snap-level alignment data; planned for v3.1
- Bayesian uncertainty quantification — overkill; MAPIE conformal intervals provide calibrated coverage without MCMC
- Cross-position interaction features — WR1 injury effect on WR2 target share; requires roster-level modeling
- Real-time in-game projections — completely different streaming architecture; v5+ territory

### Architecture Approach

The system extends the existing Medallion Architecture without modifying any existing Silver or Bronze pipelines. New code consists of four source modules and three CLI scripts, all net-new files except for `config.py` additions and a `--ml` flag on `generate_projections.py`. The heuristic `projection_engine.py` is preserved as a fallback for rookies, returning players, and new team acquisitions with fewer than 3 prior games of rolling history.

**Major components:**
1. `src/player_feature_engineering.py` — assembles player-week feature vectors from Silver sources; derives efficiency features during assembly; enforces temporal integrity via shift(1) validation
2. `src/player_model_training.py` — adapts `ensemble_training.py` for player-week data; trains one XGB+LGB+CB+Ridge ensemble per (position, target_stat) pair; saves to `models/player_ensemble/{position}/{target}/`
3. `src/player_prediction.py` — inference pipeline: features to models to raw stats to `scoring_calculator.py` to fantasy points; routes to ML or heuristic based on history check; applies injury multipliers as post-processing
4. `src/player_constraints.py` — converts game prediction ensemble's implied team totals into team stat budgets; applies proportional scaling only as a safety valve

### Critical Pitfalls

1. **Same-game stat leakage** — using Silver usage metrics from the prediction week as features causes artificial MAE of 2-3 during training that collapses at deployment. Prevention: feature availability audit for every column; `PlayerFeatureValidator` flagging features with r > 0.90 correlation to target; if any model achieves MAE below 3.0 in walk-forward CV, investigate immediately.

2. **Position-aggregated metrics hiding positional failure** — aggregate MAE of 4.5 can mask QB MAE of 7.0 (worse than baseline 6.58) when TE accuracy pulls the average down. Prevention: per-position MAE is the primary metric; ship gate requires each position independently to beat its own baseline.

3. **TD variance destroying model signal** — TDs are 6-point binary events with week-to-week correlation near zero; a player averaging 0.8 TDs/game generates ~3 points of irreducible noise. Prevention: opportunity-efficiency decomposition predicts TD rate from red zone opportunity share and historical conversion rates, not raw TD history; regress individual TD rates toward positional mean.

4. **Role change lag** — rolling averages are by design 2-3 weeks behind sudden role changes. Prevention: include `snap_pct_roll3 - snap_pct_roll6` as role momentum feature; include raw previous-week values alongside rolling windows to give the model sensitivity to sudden shifts.

5. **Not beating the heuristic after full build** — the existing heuristic already captures the strongest signals. Prevention: define the ship gate before building (>= 0.2 MAE improvement per position); if ML only reaches marginal improvement, consider a hybrid that uses ML for RB/WR and heuristic for QB/TE where data is thinner.

## Implications for Roadmap

Based on the dependency structure across all four research files, a four-phase build is recommended that mirrors the architecture's suggested build order exactly.

### Phase 1: Player Feature Vector Assembly and Evaluation Framework
**Rationale:** Feature engineering is the highest-risk phase because data leakage introduced here invalidates every downstream model evaluation. The ship gate criteria must also be defined before training so success is measured objectively. Getting both right first prevents rewrites.
**Delivers:** `src/player_feature_engineering.py` with validated temporal integrity, `PlayerFeatureValidator` leakage detection, per-position train/validation datasets (2020-2024), evaluation harness with per-position benchmarks vs heuristic baseline, and the ship-or-skip gate definition (>=0.2 MAE improvement per position, measured independently per position).
**Addresses:** Player-level feature vector assembly (P1), walk-forward CV framework (P1), per-position evaluation (P1), matchup features (P1), Vegas context (P1)
**Avoids:** Same-game stat leakage (Pitfall 1), forgot-to-lag opponent features (Pitfall 12), bye week data corruption (Pitfall 14), target variable inconsistency (Pitfall 13)

### Phase 2: Position-Specific Model Training
**Rationale:** Model training depends entirely on clean feature vectors from Phase 1. The architecture decision (separate models per position x target stat) and the opportunity-efficiency decomposition both get implemented here. TD regression features prevent variance domination.
**Delivers:** Trained ensembles in `models/player_ensemble/{QB,RB,WR,TE}/{target_stat}/` for all ~18 primary (position, target) pairs; SHAP-selected feature sets per position; per-fold CV metrics vs heuristic baseline.
**Addresses:** Position-specific models (P1), opportunity-efficiency decomposition (P2), TD regression features (P2), role momentum features (P2), ensemble stacking (P2)
**Avoids:** Wrong unit of analysis (Pitfall 2), TD variance domination (Pitfall 4), small sample per player (Pitfall 8), scoring format sensitivity (Pitfall 7 — predicting components not points), insufficient early CV folds (Pitfall 10)
**Uses:** statsmodels 0.14.6 (new, research phase only for variance decomposition)

### Phase 3: Prediction Pipeline, Constraints, and Evaluation
**Rationale:** Inference infrastructure and the ship-or-skip evaluation can only be built after trained models exist. This phase also handles the integration complexities (separate Gold output path, injury post-processing, team coherence constraints) that must be designed to avoid conflicting with the existing heuristic output.
**Delivers:** `src/player_prediction.py` (ML/heuristic routing), `src/player_constraints.py` (team budget allocation), `scripts/backtest_player_predictions.py` (per-position holdout evaluation), Gold path `data/gold/ml_projections/` with `model_version` column, validation that team-summed projections correlate >0.7 with implied team totals, final ship-or-skip decision on 2024 holdout data.
**Addresses:** Top-down team constraint (P2), floor/ceiling variance estimation (P3), per-stat sub-model evaluation
**Avoids:** Team total incoherence (Pitfall 6), conflicting projection outputs (Pitfall 16), injury uncertainty (Pitfall 9), aggregate metrics hiding failure (Pitfall 3), not beating baseline (Pitfall 11)
**Uses:** MAPIE 1.3.0 (new — calibrated floor/ceiling prediction intervals)

### Phase 4: Integration and Cutover
**Rationale:** Only after the ML model has cleared the ship gate should it be wired into the weekly pipeline and draft tool. This phase is the smallest in scope but highest in integration risk — it touches existing production scripts that serve the draft tool, backtest framework, and weekly GHA pipeline.
**Delivers:** `--ml` flag on `scripts/generate_projections.py` (ML as default, heuristic as fallback for rookies/thin history), `scripts/train_player_models.py` and `scripts/generate_player_predictions.py` CLI scripts, weekly pipeline slot in `weekly-pipeline.yml` after Silver transformation, `draft_assistant.py` updated to consume ML projections, zero regression on existing 571 tests.
**Addresses:** Heuristic-to-ML transition strategy, weekly retraining schedule, rookie/new team fallback routing
**Avoids:** Conflicting outputs (Pitfall 16), retraining staleness (Pitfall 17), breaking existing tests (Pitfall 15)

### Phase Ordering Rationale

- Feature engineering must precede training: player-week vectors are the training data; no model training is possible without them. Placing evaluation framework design in Phase 1 (alongside feature engineering) ensures success criteria exist before any model results are visible.
- Training before prediction pipeline: the inference modules are parameterized by trained model artifacts; they cannot be implemented or tested without them.
- Evaluation before cutover: the ship-or-skip gate must produce a clear signal before any existing production path is modified. Running both heuristic and ML in parallel through Phase 3 keeps the draft tool and weekly pipeline unaffected until the gate is cleared.
- Pitfall 1 (data leakage) is the existential risk: if same-game stats contaminate Phase 1, all downstream metrics are invalid. The `PlayerFeatureValidator` and the >3.0 MAE alert serve as early detection before it propagates.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (MAPIE integration):** Conformal prediction with an XGB+LGB+CB+Ridge stacking ensemble requires validating whether `MapieRegressor` wraps the final stacked model or each base model. The "plus" (Jackknife+) method requires the base model to support `predict` — Ridge does, but the interaction with multi-model stacking should be confirmed during plan-phase research.

Phases with standard patterns (skip additional research):
- **Phase 1:** Follows established `feature_engineering.py` pattern; all Silver schemas are documented and confirmed by direct inspection
- **Phase 2:** Directly adapts `ensemble_training.py`; same walk-forward CV, same model factories, same SHAP selection — well-understood from v2.0
- **Phase 4:** Wiring into existing CLI and GHA pipeline follows project conventions established across prior phases

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Two new installs (statsmodels, MAPIE) verified against Python 3.9 / numpy 1.26.4 / scikit-learn 1.5 constraints; existing stack confirmed sufficient for all other needs |
| Features | MEDIUM-HIGH | ~80% of features confirmed by Silver schema inspection; industry MAE benchmarks (FFA Avg ~4.3-4.5) are estimates, not publicly disclosed raw numbers; core feature importance rankings (target share r=0.70) from published research |
| Architecture | HIGH | Based on direct codebase inspection of all relevant source files and Silver schemas; two-stage architecture is well-documented; existing infrastructure maps directly to the new system |
| Pitfalls | HIGH | Sourced from existing codebase analysis plus academic ML literature on temporal leakage and sports prediction; v2.0 game prediction build provides direct precedent for several risks |

**Overall confidence:** HIGH

### Gaps to Address

- **Industry MAE benchmarks are estimates:** FFA Accuracy Analysis gives relative rankings but exact MAE numbers are not publicly disclosed. The per-position targets (QB <6.0, RB <4.8, WR <4.5, TE <3.5) are based on estimated industry best. Validate against FFA 2024-2025 accuracy reports at the start of Phase 1.
- **QB sample size risk:** Only ~300 QB player-weeks per season (~1,500 over five seasons). If QB MAE does not improve in CV, consider keeping the heuristic for QBs and shipping ML only for RB/WR/TE.
- **Red zone carry share availability:** TD regression for RBs requires red zone carry share (inside-20 carries), which may require Bronze PBP extraction not present in current Silver `players/usage`. Validate availability during Phase 1 before committing to this approach.
- **Game prediction ensemble dependency:** Phase 1 calls for Gold game predictions (implied team totals) as features in the player vector. The game prediction models must be trained and current before player features can be assembled. This pipeline sequencing dependency must be handled explicitly in Phase 4.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/feature_engineering.py`, `src/projection_engine.py`, `src/ensemble_training.py`, `src/player_analytics.py`, `src/player_advanced_analytics.py`, `src/config.py` — architecture and integration patterns
- Silver layer schema inspection: `data/silver/players/usage/` (113 cols), `data/silver/players/advanced/` (119 cols), `data/silver/players/historical/` (63 cols), `data/silver/defense/positional/` (6 cols), `data/silver/teams/player_quality/` (28 cols) — confirmed feature availability
- [MAPIE PyPI](https://pypi.org/project/MAPIE/) v1.3.0 — Python>=3.9, numpy>=1.23, scikit-learn>=1.4; confirmed Feb 2026
- [MAPIE Documentation](https://mapie.readthedocs.io/en/latest/) — conformal prediction intervals for regression
- [statsmodels PyPI](https://pypi.org/project/statsmodels/) v0.14.6 — Python>=3.9; confirmed Dec 2025
- [scikit-learn TargetEncoder](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.TargetEncoder.html) — available since sklearn 1.3

### Secondary (MEDIUM confidence)
- [SumerSports: Sticky Football Stats](https://sumersports.com/the-zone/sticky-football-stats-predictive-nfl-metrics/) — target share r=0.70 Y/Y, EPA/pass r=0.60
- [Fantasy Football Analytics: Most Accurate Projections](https://fantasyfootballanalytics.net/2024/12/which-fantasy-football-projections-are-most-accurate.html) — FFA Average consistency as top-tier consensus
- [FanDuel Research: Touchdown Regression](https://www.fanduel.com/research/touchdown-regression-what-it-is-and-how-to-use-it-for-player-prop-bets-fantasy-football) — only 11% of 10+ TD players repeat; average loss of 5.2 TDs
- [ESPN: Opportunity-Adjusted Fantasy Points](https://www.espn.com/fantasy/football/story/_/id/24318831/fantasy-football-introducing-ofp-opportunity-adjusted-fantasy-points-forp-fantasy-points-replacement-player) — opportunity vs efficiency decomposition methodology
- [FantasyPros: How to Use Vegas Odds](https://www.fantasypros.com/2023/08/how-to-use-vegas-odds-for-fantasy-football-2023/) — implied totals as strongest correlate of fantasy production

### Tertiary (LOW confidence)
- [Bayesian Hierarchical Modeling for Fantasy Football](https://srome.github.io/Bayesian-Hierarchical-Modeling-Applied-to-Fantasy-Football-Projections-for-Increased-Insight-and-Confidence/) — research context; blog post
- [Linear Mixed Effect Modeling for Fantasy Football](https://www.dennisgong.com/blog/fantasy_football/) — practical mixed-effects application; blog post
- Industry MAE benchmarks (~4.3-4.5 for FFA Average, ~4.5-5.0 for ESPN) — estimated from methodology descriptions, not published raw numbers

---
*Research completed: 2026-03-29*
*Ready for roadmap: yes*
