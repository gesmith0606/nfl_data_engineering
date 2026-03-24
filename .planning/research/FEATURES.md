# Feature Research

**Domain:** NFL game prediction model improvement (player-level features, ensembles, feature selection, advanced signals)
**Researched:** 2026-03-24
**Confidence:** MEDIUM-HIGH (existing system well-understood; new feature categories verified via academic papers and open-source model analysis; ensemble gains are domain-agnostic and HIGH confidence)

---

## Context: What Already Exists (v1.4 Baseline)

This is a SUBSEQUENT milestone. Do not re-build what exists.

| Already Built | Status |
|---------------|--------|
| 283 leakage-free game-level features (227 rolling team metrics + 56 pre-game context) | Done |
| Team EPA, success rate, CPOE, tendencies, SOS, situational splits (rolling 3/6-game) | Done |
| Game context: weather, rest, travel, dome, coaching tenure, surface | Done |
| Referee tendencies, playoff context, W-L record | Done |
| XGBoost spread + O/U models with walk-forward CV, Optuna tuning | Done |
| Sealed 2024 holdout (53.2% ATS overall, 50.0% holdout) | Done |
| Edge detection vs Vegas closing lines, confidence tiers | Done |

**Gap:** The 50.0% holdout result is essentially coin-flip. The existing 283 features are all team-level aggregates. Player-level signal (QB quality, injury replacement quality) is captured only indirectly through team EPA rolling averages, which react slowly to roster changes.

---

## Feature Landscape

### Table Stakes (Required for This Milestone)

Features the improved model must have. Missing these means leaving the most impactful signal on the table.

| Feature | Why Required | Complexity | Dependency on Existing |
|---------|--------------|------------|------------------------|
| Starting QB quality differential | QB injuries cause 8-12 point power ranking drops; team EPA lags 2-3 weeks before reflecting starter change; a direct QB metric captures this immediately | MEDIUM | Requires Bronze `player_weekly` (passing EPA) + `injuries` + `depth_charts` + `rosters` — all in Bronze |
| Backup QB detection flag + quality drop | When a team's starting QB is injured or benched, current team EPA still reflects the previous starter; a "backup playing" flag + backup tier dramatically reduces this ghost signal | MEDIUM | Requires `depth_charts` Bronze + `injuries` Bronze + `player_weekly` for backup's rolling EPA |
| Feature importance analysis (SHAP or gain) | Model currently a black box; must understand which of 283 features actually drive predictions before adding 30-50 more | LOW | XGBoost gain importance already available via `model.feature_importances_`; SHAP adds finer granularity |
| Correlation-based redundancy filtering | 283 features likely contain high collinearity (e.g., EPA rolling_3 and EPA rolling_6 are r>0.9); removing redundant features reduces overfitting on 2,100-game dataset | LOW | Requires pandas `.corr()` on assembled game features |
| SHAP-based feature selection | Identifies features with near-zero contribution to predictions; more robust than gain importance alone because it accounts for interaction effects | MEDIUM | Requires `shap` library (not yet a project dependency); works on existing XGBoost models |

### Differentiators (Competitive Advantage)

Features that meaningfully separate this model from the v1.4 baseline and from Elo-based competitors like nfelo.

| Feature | Value Proposition | Complexity | Dependency |
|---------|-------------------|------------|------------|
| XGBoost + LightGBM ensemble (Ridge meta-learner) | LightGBM's leaf-wise splitting finds different patterns than XGBoost's depth-wise splitting; stacking their out-of-fold predictions via Ridge adds ~0.5-1.5% ATS accuracy on tabular sports data | HIGH | LightGBM is new dependency; requires out-of-fold (OOF) prediction assembly within walk-forward CV |
| Adaptive rolling windows (3/6/10 game) | Current model uses fixed 3 and 6-game windows; teams vary in how quickly they stabilize — a rookie OC team should use shorter window than a veteran system team; adding a 10-game window for "regime" and exponential decay variant captures multi-speed trends | MEDIUM | Builds on existing `team_analytics.py` rolling logic; new columns added to Silver team metrics |
| Team momentum signal | Winning streak direction (momentum_streak: +3 = won last 3, -2 = lost last 2) and points-vs-spread trend (ATS_streak) are leading indicators before EPA rolling catches up; shown to be statistically significant in sports prediction literature | MEDIUM | Requires schedule results + spread_line from Bronze `schedules`; new derived column, no new Bronze sources needed |
| Regime detection via performance stability | Identify when a team is in a "regime change" (new coach, QB injury, trade deadline addition) by detecting sudden shifts in rolling EPA standard deviation; flag these games as uncertain and reduce confidence tier | HIGH | Requires rolling std of EPA differential; changepoint detection (via simple threshold on rolling_std delta, no exotic libraries required) |
| CatBoost as third ensemble base learner | CatBoost uses symmetric trees and ordered boosting that reduces overfitting on small N datasets; adding it as a third base learner in the stacking ensemble provides independent error variance, improving ensemble stability | HIGH | New dependency: `catboost`; structurally parallel to LightGBM addition |
| Quantile regression for prediction intervals | Instead of point estimate only, produce a confidence interval for each spread prediction (e.g., "model: -3.5 ± 4.2"); games where interval is narrow deserve higher edge confidence | MEDIUM | XGBoost supports quantile regression natively via `objective="reg:quantileerror"`; no new library needed |
| Depth chart delta features | Week-over-week change in a team's depth chart at QB, WR1, OL (composite) positions signals roster flux before it shows up in EPA; especially powerful for detecting mid-season trade deadline impacts | HIGH | Requires Bronze `depth_charts` + `rosters`; needs player-level aggregation logic, new Silver path |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full 53-man roster player features | "Individual skill matters" | Combinatorial explosion: 53 players x 2 teams x multiple metrics = 300+ new columns; extreme sparsity for non-starters; negligible improvement over team EPA aggregates for the 90% of players who aren't QB | Limit player features to QB only (highest individual impact) and key-player injury flags at other positions |
| Raw injury count as feature | "More injuries = worse team" | Raw count treats a backup LB injury identically to a QB injury; noisy signal; positional importance varies 10x | Use position-weighted injury score (QB weight=5, OL weight=2, skill positions weight=1.5, LB/DB weight=1.0) |
| Neural network for game prediction | "Deep learning beats tree models" | NFL game dataset is ~2,100 games (2016-2025); neural nets require 10x-100x more data to generalize; consistently underperform gradient boosting on tabular sports data at this scale per 2025 Frontiers paper | XGBoost + LightGBM + CatBoost stacking achieves equivalent or better performance with interpretability |
| Player-to-player matchup features (WR vs CB) | "Mahomes vs Sauce Gardner matters" | Requires Neo4j graph model (deferred to v3.1); dense matrix of 50+ WR vs 50+ CB combinations is mostly empty; confounds game-level prediction with position matchup prediction | Team-level passing EPA vs opponent's coverage EPA differential is a sufficient proxy at this granularity |
| Line movement as input feature | "Sharp money knows more" | Model learns to track market rather than find independent signal; at best achieves 52.4% ATS (break-even) by echoing the closing line | Use Vegas closing line ONLY as evaluation benchmark (ATS accuracy, CLV), never as input |
| Automated weekly model retraining | "Fresh model every week" | With only 2,100 games in training, adding 16 new games each week produces tiny marginal improvement; risk of overfitting to small recent sample; operational complexity high | Retrain seasonally (once/year before season start); monitor drift with ATS rolling 8-week window |
| Player sentiment / Twitter data | "Media narrative has signal" | Unstructured data; requires NLP pipeline; signal is noise at weekly aggregation; not reproducible from free data sources | Focus on structured depth chart changes and injury reports, which capture the same information more reliably |

---

## Feature Dependencies

```
Existing 283 game-level features (v1.4)
    |
    +---> [TABLE STAKES] SHAP / gain importance analysis
    |         Requires: existing XGBoost models + shap library
    |         Output: ranked feature importance, drop bottom 30%
    |
    +---> [TABLE STAKES] Correlation redundancy filter
    |         Requires: assembled game features DataFrame
    |         Output: reduced feature set (target: 80-120 features)
    |
    v
Reduced feature set (80-120 features)
    |
    +---> [TABLE STAKES] Starting QB quality differential
    |         Requires: Bronze player_weekly (pass_epa) + depth_charts + injuries
    |         Output: home_qb_epa_roll3, away_qb_epa_roll3, qb_epa_diff,
    |                  home_qb_backup_flag, qb_quality_tier_diff
    |
    +---> [TABLE STAKES] Backup QB detection + quality drop
    |         Requires: Bronze injuries (Doubtful/Out status) + depth_charts + player_weekly
    |         Output: home_backup_qb (0/1), away_backup_qb (0/1), qb_replacement_quality_diff
    |
    +---> [DIFFERENTIATOR] Adaptive rolling windows (10-game + exp decay)
    |         Requires: existing team_analytics.py rolling logic
    |         Output: new columns in Silver teams/pbp_metrics (roll10 variants)
    |
    +---> [DIFFERENTIATOR] Momentum signal (winning streak, ATS streak)
    |         Requires: Bronze schedules (results + spread_line, no new sources)
    |         Output: home_momentum_streak, away_momentum_streak, home_ats_streak
    |
    v
Enriched feature set (~100-150 features with player + momentum signals)
    |
    +---> [DIFFERENTIATOR] XGBoost base model (already exists, retrain on reduced features)
    |
    +---> [DIFFERENTIATOR] LightGBM base model (new dependency)
    |         Requires: lightgbm library + OOF prediction assembly within walk-forward CV
    |
    +---> [DIFFERENTIATOR] CatBoost base model (new dependency)
    |         Requires: catboost library
    |
    v
OOF predictions from 3 base models
    |
    v
[DIFFERENTIATOR] Ridge meta-learner
    Requires: sklearn Ridge (already a transitive dep via scipy)
    Output: final ensemble spread / total predictions
    |
    v
[DIFFERENTIATOR] Quantile regression intervals (XGBoost quantile objective)
    Requires: no new library; XGBoost native
    Output: prediction_interval_width per game
    |
    v
Updated edge detection + confidence tiers
    |
    v
Weekly prediction pipeline (already exists, update inputs)
```

### Dependency Notes

- **QB features depend on Bronze depth_charts + injuries:** These Bronze sources are already ingested for 2016-2025 (v1.1). The work is aggregation logic, not new data ingestion.
- **Feature selection must precede ensemble:** Adding 3 base learners to 283 noisy features compounds overfitting; reduce first, then ensemble.
- **Momentum signal requires no new Bronze sources:** Computed from existing Bronze `schedules` which already has `result` and `spread_line`.
- **Adaptive windows enhance, not replace, existing windows:** Add roll_10 and exp_decay variants alongside existing roll_3/roll_6; do not remove existing columns until feature selection confirms they are inferior.
- **Regime detection depends on adaptive windows:** Rolling std of EPA requires longer history (10-game window) to detect meaningful regime shifts.
- **OOF stacking requires modified CV loop:** The existing `walk_forward_cv` in `model_training.py` must be extended to collect out-of-fold predictions for each fold, not just MAE scores.

---

## MVP Definition

### Launch With (v2.0 — this milestone)

Minimum viable product to validate whether player-level + ensemble changes move holdout ATS from 50% toward 53%+.

- [ ] Feature importance analysis (SHAP + gain) — identify which of 283 features contribute signal
- [ ] Correlation/redundancy filter — reduce to 80-120 feature subset, retrain XGBoost, verify no regression
- [ ] Starting QB quality differential — EPA-based rolling metric with backup detection flag
- [ ] LightGBM base model — second learner with Ridge stacking over XGBoost + LightGBM OOF predictions
- [ ] Momentum signal (win streak + ATS trend) — simple derived column from existing schedules data
- [ ] Holdout evaluation on 2024 season — compare 2024 ATS accuracy before and after each change

### Add After Validation (v2.x)

Features to add once the v2.0 changes show measurable improvement in holdout accuracy.

- [ ] CatBoost as third base learner — adds independent error variance; only worth the complexity if LightGBM stacking already shows uplift
- [ ] Adaptive rolling windows (10-game) — extend existing Silver team metrics; test whether 10-game window adds signal over 3/6
- [ ] Quantile regression intervals — once spread model is stable, add prediction intervals for edge confidence refinement
- [ ] Regime detection flag — experimental; adds complexity, test whether it reduces false positives on regime-change games
- [ ] Depth chart delta features — requires new Silver path; high complexity; defer until base improvements are validated

### Future Consideration (v3+)

Features to defer to later milestones.

- [ ] WR-CB matchup graph (Neo4j) — requires v3.1 infrastructure; not available from flat Parquet
- [ ] Live in-season model updates — requires production infra (v3.0 milestone)
- [ ] Market data / line movement — requires paid data feed (v2.3 milestone)
- [ ] News NLP / practice reports — unstructured data pipeline (v3.1 milestone)

---

## Feature Prioritization Matrix

| Feature | Model Value | Implementation Cost | Priority |
|---------|-------------|---------------------|----------|
| SHAP feature selection / redundancy filter | HIGH | LOW | P1 |
| Starting QB EPA differential | HIGH | MEDIUM | P1 |
| Backup QB detection flag | HIGH | MEDIUM | P1 |
| LightGBM + Ridge stacking (2-model) | HIGH | MEDIUM | P1 |
| Momentum signal (win/ATS streak) | MEDIUM | LOW | P1 |
| CatBoost (3rd base learner) | MEDIUM | MEDIUM | P2 |
| Adaptive 10-game rolling windows | MEDIUM | MEDIUM | P2 |
| Quantile regression intervals | MEDIUM | LOW | P2 |
| Regime detection flag | LOW | HIGH | P3 |
| Depth chart delta features | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Core v2.0 milestone deliverable
- P2: Add if P1 shows improvement and capacity permits
- P3: Defer to future milestone; requires validation that earlier features are working

---

## Realistic Improvement Expectations

Based on research and the existing 50.0% holdout baseline:

| Change | Expected ATS Lift | Confidence | Rationale |
|--------|-------------------|------------|-----------|
| Feature selection (reduce noise) | +0.5-1.5% | MEDIUM | Established result: removing noisy features reduces overfitting on small N; sports prediction papers consistently show this |
| Starting QB differential | +0.5-1.5% | MEDIUM | nfelo's QB adjustment is their largest single signal; FiveThirtyEight's QB VALUE metric provides 2-3 point line adjustment; this is the single highest-impact player feature |
| Backup QB detection flag | +0.5-1.0% | MEDIUM | QB injuries cause 8-12 point power ranking shifts; current model is blind to this for 2-3 weeks post-injury |
| LightGBM + stacking | +0.3-0.8% | MEDIUM-LOW | Literature shows 0.5-1.5% gains for stacking gradient boosting models on tabular data; sports-specific evidence is thinner |
| Momentum signals | +0.2-0.5% | LOW | Statistical significance in sports literature but effect size is small after controlling for team quality |
| Combined (all P1 features) | +1.5-4.0% | MEDIUM | Non-additive due to overlap; realistic target is 52-54% holdout ATS |

**Key reality check:** Moving from 50% to 53%+ on a sealed holdout is ambitious. Each 1% improvement requires finding a systematic market inefficiency. The QB signal is the most likely source. If feature selection alone moves holdout from 50% to 51.5%, that validates the approach and justifies adding ensemble complexity.

---

## Competitor Feature Analysis

| Feature | nfelo | FiveThirtyEight | Our v1.4 | Our v2.0 Target |
|---------|-------|-----------------|----------|-----------------|
| QB quality metric | Dedicated QB Elo model (nfeloqb) — rolling offensive/defensive passing performance | QB VALUE (rolling EPA/CPOE) — ±2-3 point line adjustment | Indirect via team EPA | Direct QB EPA differential + backup flag |
| Team quality metric | Custom Elo (game-by-game update) | Elo rating (season-long) | 283 Silver features | 80-120 selected Silver features |
| Player injury handling | QB game-day probability model | Manual adjustment | Bronze injury status → team Silver (lagged) | Backup QB flag (immediate signal) |
| Model architecture | Single Elo formula with QB overlay | Single Elo with QB/HFA adjustments | Single XGBoost | XGBoost + LightGBM stacked via Ridge |
| Feature count | ~15 (Elo + adjustments) | ~12 | 283 | ~100-150 (selected) |
| ATS accuracy | 53.7% vs closing (2009-2025) | Not published vs closing | 53.2% overall, 50.0% holdout | Target: 53%+ holdout |

**Observation:** nfelo achieves 53.7% ATS with just ~15 features including a dedicated QB model. This strongly validates that QB adjustment is the highest-leverage player feature to add. Our richer team-level context (weather, refs, situational splits) should complement the QB signal rather than duplicate it.

---

## Sources

- [Advancing NFL Win Prediction: Pythagorean to ML (Frontiers 2025)](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1638446/full) — SHAP feature importance, RF vs NN vs traditional; HIGH confidence
- [nfelo Model Performance](https://www.nfeloapp.com/games/nfl-model-performance/) — 53.7% ATS, QB adjustment methodology; HIGH confidence
- [nfeloqb GitHub](https://github.com/greerreNFL/nfeloqb) — QB Elo adjustment implementation reference; HIGH confidence
- [nfelo: Best NFL Game Grade](https://www.nfeloapp.com/analysis/whats-the-best-nfl-game-grade/) — 60% point differential + 20% WEPA + 20% PFF; 1.6x offensive EPA weight; HIGH confidence
- [BorutaSHAP Feature Selection](https://github.com/Ekeany/Boruta-Shap) — Boruta + SHAP combined feature selection for tree models; HIGH confidence
- [SHAP vs Permutation Importance Comparison (Springer 2024)](https://link.springer.com/article/10.1186/s40537-024-00905-w) — Permutation importance yields less consistent improvements than SHAP; MEDIUM confidence
- [Stacking Ensembles XGBoost+LightGBM+CatBoost (2025)](https://johal.in/ensemble-learning-methods-xgboost-and-lightgbm-stacking-for-improved-predictive-accuracy-2025/) — 6.3% accuracy lift over best single model on general tabular data; MEDIUM confidence (not sports-specific)
- [Stacking Ensemble Research Square 2025](https://www.researchsquare.com/article/rs-7944070/v1) — XGBoost + LightGBM + CatBoost + AdaBoost stacking methodology; MEDIUM confidence
- [Hidden Markov Model Regime Detection (Medium)](https://pyquantlab.medium.com/hidden-markov-model-regime-adaptive-momentum-strategy-with-dynamic-lookbacks-and-trailing-stops-be1aae8b73f1) — HMM for regime detection in time series; LOW confidence (financial, not sports-specific)
- [Impact of Injuries on NFL Power Rankings (WalterFootball)](https://walterfootball.com/impactinjuriespowerrankings.php) — QB injury causes 8-12 position drop; MEDIUM confidence
- [Sports Injury Central 2024 Team Health Analysis](https://sicscore.com/news/most-and-least-injured-nfl-teams-in-2024-key-insights-and-2025-projections/) — team health vs win correlation 2024 season; MEDIUM confidence
- Existing codebase: `src/feature_engineering.py`, `src/model_training.py`, `src/player_advanced_analytics.py` — current feature assembly and model architecture; HIGH confidence

---
*Feature research for: NFL game prediction model improvement (v2.0 milestone)*
*Researched: 2026-03-24*
