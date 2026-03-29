# Domain Pitfalls: ML-Based Player Fantasy Prediction System (v3.0)

**Domain:** ML player-level fantasy football projections added to existing game prediction platform
**Researched:** 2026-03-29
**Confidence:** HIGH (based on existing codebase analysis + domain research)

## Critical Pitfalls

Mistakes that cause rewrites, invalidate model evaluations, or produce unusable predictions.

### Pitfall 1: Same-Game Stat Leakage in Player Features

**What goes wrong:** The model trains on features derived from the same game it is predicting. For example, using a player's snap count, target share, or rushing attempts from week 10 to predict their week 10 fantasy points. The model learns "players who got 25 carries scored a lot" which is trivially true but useless for prediction.

**Why it happens:** The existing Silver layer computes usage metrics (target_share, carry_share, snap_pct) as same-week values in `player_analytics.py`. These are descriptive, not predictive. Reusing them directly as ML features leaks outcome information. The game prediction system avoided this by using lagged team-level rolling averages (shift(1)), but player features need the same treatment and it is easy to forget when porting patterns.

**Consequences:** Model appears to have MAE of 2-3 points during development (far better than the 4.91 baseline), creating false confidence. Deployed predictions revert to baseline or worse because same-game stats are unavailable at prediction time. Entire training pipeline must be rebuilt.

**Prevention:**
- Enforce a strict rule: every player feature must be computed from data available BEFORE the prediction week. Use `.shift(1)` on all rolling averages grouped by player.
- Create a `PlayerFeatureValidator` that checks no feature column has correlation > 0.90 with the target (fantasy_points). Same-game leakage features typically show r > 0.95.
- Test with a "feature availability audit": for each feature, ask "could I compute this on Tuesday before the Sunday game?"
- The existing `_PRE_GAME_CONTEXT` pattern in `feature_engineering.py` (which correctly uses opening lines, not closing lines) is the model to follow.

**Detection:** If any single-model MAE drops below 3.0 on walk-forward CV, investigate for leakage immediately. The heuristic baseline (4.91) is already quite good; ML should improve by 5-15%, not 40%.

**Phase to address:** Phase 1 (feature engineering). Must be right from the start; cannot be patched later.

---

### Pitfall 2: Treating Player Prediction Like Game Prediction (Wrong Unit of Analysis)

**What goes wrong:** Directly copying the game prediction architecture (differential features, game-level rows) for player prediction. Game prediction has ~270 games/season with stable team-level features. Player prediction has ~8,500 player-weeks/season but each individual player has only 10-17 games, with massive heterogeneity across positions and roles.

**Why it happens:** The existing ensemble training pipeline (`ensemble_training.py`) works well for games. It is tempting to reuse the same walk-forward CV, same model factories, same stacking approach. But the data characteristics are fundamentally different: player data is panel data (many individuals, few observations each) not cross-sectional time series.

**Consequences:** Models overfit to individual player histories. Walk-forward folds have too few examples per player to learn meaningful patterns. The model memorizes "Tyreek Hill averages 18 points" rather than learning transferable relationships between opportunity and production.

**Prevention:**
- Train position-specific models (QB, RB, WR, TE) that learn CROSS-PLAYER patterns (e.g., "WRs with >25% target share and opponent allowing top-10 WR points score X"), not per-player models.
- Pool all players of a position together. The unit of prediction is a player-week, but the model learns from the full population.
- Use player identity as context (via role features like draft capital, career games) rather than player identity itself. Never one-hot encode player_id.
- Walk-forward CV should split by week (all players in week N are in the same fold), not by player.

**Detection:** Check if removing player-identifying features (name, ID) changes model performance by more than 1%. If it does, the model is memorizing players, not learning patterns.

**Phase to address:** Phase 1 (architecture design). Determines the entire model structure.

---

### Pitfall 3: Aggregate Metrics Hiding Positional Failure

**What goes wrong:** Reporting overall MAE of 4.5 (beating the 4.91 baseline) while QB MAE is 7.0 (worse than baseline 6.58) and TE MAE is 3.2 (pulling the average down because TEs score fewer points). The model looks good in aggregate but is worse for the positions users care most about.

**Why it happens:** TE and low-volume players have low absolute scores (5-8 points), making their MAE naturally small. QB and high-volume RB scores are much higher (15-25 points), making their errors larger. Averaging across positions hides this. The current heuristic baseline already provides per-position benchmarks (QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77) which are the real targets.

**Consequences:** You ship a model that is worse for QBs and high-value WRs (the positions with the most fantasy value) while claiming improvement. Users lose faith in projections for their most important roster decisions.

**Prevention:**
- Primary evaluation metric: per-position MAE, not aggregate MAE. The v3.0 evaluation framework MUST report QB, RB, WR, TE separately.
- Secondary: per-position correlation (r) and bias.
- Ship criterion: ML model must beat the heuristic baseline on EACH position independently, or at minimum not regress on any position by more than 5% while improving others.
- Weight evaluation by fantasy relevance: QB/RB/WR errors matter more than K/DST.

**Detection:** Always run `backtest_projections.py`-style per-position breakdowns. Never look at aggregate MAE alone.

**Phase to address:** Phase 1 (evaluation framework design). Must define success criteria before training.

---

### Pitfall 4: Touchdown Variance Destroying Model Signal

**What goes wrong:** The model learns to predict touchdowns based on historical TD rates, but touchdowns are the most volatile component of fantasy scoring. A player averaging 0.8 TDs/game might score 0, 0, 3, 0, 1, 0 in consecutive weeks. The model predicts 0.8 every week and is systematically wrong in both directions.

**Why it happens:** Touchdowns are high-value, low-probability, high-variance events. In PPR scoring, a TD is worth 6 points but a reception is worth 1 point. A player who catches 6 balls for 50 yards with no TD scores 11 PPR points. The same player with 1 TD scores 17 points. This 6-point swing from a single binary event dominates prediction error. Research shows TDs explain the majority of fantasy point variance while being the least predictable component.

**Consequences:** Model MAE is dominated by TD variance that no model can predict. Effort spent on sophisticated features is wasted because the irreducible TD noise floor is ~3 points/week for skill positions. The model may also overfit to TD-lucky seasons (e.g., a WR who scored 14 TDs one year and 6 the next).

**Prevention:**
- Decompose predictions into opportunity (targets, carries, snap share) and efficiency (yards per target, yards per carry, TD rate) components. Predict opportunity first (more stable, r > 0.7 week-to-week), then apply regressed efficiency rates.
- Regress TD rates toward positional means. A WR's predicted TD rate should be pulled toward the WR average (roughly 1 TD per 11 targets), not their personal 6-game sample.
- Consider predicting yards + receptions (the stable components) with ML and applying expected TD rates as a post-processing step, similar to how the current heuristic applies shrinkage via `PROJECTION_CEILING_SHRINKAGE`.
- Report MAE both with and without TDs to understand the noise floor.

**Detection:** If week-to-week correlation of your TD predictions is below 0.15, the model is not meaningfully predicting TDs (the baseline of "predict the mean" is better). Check this explicitly.

**Phase to address:** Phase 2 (model design). The opportunity/efficiency decomposition is an architectural choice.

---

### Pitfall 5: Overfitting to Historical Usage Patterns That Do Not Persist

**What goes wrong:** The model learns "Player X had 28% target share last 3 weeks, predict high production." But Player X was the WR1 while the WR2 was injured. The WR2 returns, and Player X's target share drops to 18%. The model is 2 weeks behind reality because rolling averages smooth over regime changes.

**Why it happens:** NFL player roles change mid-season due to injuries, trades, depth chart changes, coaching staff turnover, and game script. A backup RB who inherits the starter role looks like a low-volume player in historical features but is about to get 20 carries. Rolling averages by design lag behind these changes. The existing heuristic already has this problem (RECENCY_WEIGHTS in `projection_engine.py` use 45% on last 3 weeks), and ML can make it worse by overfitting to the lagged signal.

**Consequences:** Model is systematically wrong during role transitions (the exact moments when accurate projections are most valuable for fantasy managers making start/sit decisions). Predictions lag reality by 1-3 weeks.

**Prevention:**
- Include snap_pct and depth_chart_position as features (these change immediately when roles change).
- Use short rolling windows (3-game) with higher weight, but also include the raw previous-week values as features (allowing the model to detect sudden changes).
- Add a "role change detector" feature: delta in snap_pct or target_share from week N-1 to week N-2. Large deltas signal regime changes.
- Do NOT try to predict role changes (that requires injury prediction). Instead, build the model to be responsive to new information: if last week's snap share was 90% (up from 40%), weight that heavily.

**Detection:** Evaluate MAE separately for "stable role" weeks (snap_pct change < 10%) vs "role change" weeks (snap_pct change > 20%). If the model is much worse on role-change weeks, it is too reliant on historical averages.

**Phase to address:** Phase 1 (feature engineering) and Phase 2 (model design).

---

### Pitfall 6: Player Projections That Do Not Sum to Reasonable Team Totals

**What goes wrong:** Individual player projections are generated independently, and when summed across a team's roster, they produce impossible totals. For example, all WRs on a team are projected for 80+ receiving yards, implying 350+ team passing yards when the team averages 220. Or total projected fantasy points for a team exceed the implied team total from Vegas.

**Why it happens:** Player-level models optimize for individual accuracy and have no awareness of the team-level budget constraint. Each prediction is made in isolation. This is the classic "coherence problem" in hierarchical forecasting. The existing projection engine does not enforce this constraint either (it applies a Vegas multiplier but does not reconcile player sums to team totals).

**Consequences:** Sophisticated users (DFS players, serious fantasy managers) lose trust when projections are internally inconsistent. Projections for backup players on a low-scoring team can be inflated because the model learned from league-wide averages.

**Prevention:**
- Use Vegas implied team totals (available via the existing market data pipeline) as a constraint.
- Post-processing approach: generate raw player projections, sum per team, then scale proportionally to match the implied team total. This is simpler and more robust than trying to bake the constraint into the model.
- Alternative: include team implied total as a feature, which lets the model learn the constraint implicitly. Both approaches can be combined.
- At minimum, add a validation check: flag any team where projected player points sum to more than 1.5x or less than 0.5x the implied team total.

**Detection:** For each week, sum projected fantasy points per team and compare to implied team totals. The correlation should be > 0.7 and no team should be more than 50% off.

**Phase to address:** Phase 3 (post-processing and integration). Requires individual models to be working first.

## Moderate Pitfalls

### Pitfall 7: Scoring Format Sensitivity (PPR vs Standard Changes Optimal Model)

**What goes wrong:** Training a single model to predict "fantasy points" across all scoring formats. The optimal features differ: PPR rewards volume (receptions), Standard rewards efficiency (yards per carry, TDs). A model optimized for Half-PPR will underperform on both PPR and Standard compared to format-specific models.

**Prevention:**
- Train separate models per scoring format, OR predict component stats (rushing yards, receiving yards, receptions, TDs) and compute fantasy points post-prediction using the existing `scoring_calculator.py`. The component approach is better because it naturally handles all formats from one model.
- If predicting components, the model does not need to know the scoring format at all. This eliminates the sensitivity entirely.
- The existing `SCORING_CONFIGS` in `config.py` already define the three formats; the component approach plugs directly into this.

**Phase to address:** Phase 2 (model design). The "predict components" decision is architectural.

### Pitfall 8: Small Sample Size Per Individual Player

**What goes wrong:** Attempting per-player models or heavy player-specific regularization with only 10-17 games per season per player. With 6 seasons of data (2020-2025), a veteran has ~100 data points. A second-year player has ~30. Rookies have 0.

**Prevention:**
- Never build per-player models. Always pool across all players of a position.
- Use player "type" features (draft round, career games played, position depth, body mass) rather than player identity.
- For rookies: use the existing rookie fallback pattern from `projection_engine.py` (conservative baselines by position) as a prior, or use combine/draft features to find similar historical players.
- Bayesian approaches (hierarchical models) handle this naturally by sharing information across players, but gradient boosting models can approximate this by learning from the population with player-type features.

**Phase to address:** Phase 1 (feature engineering) and Phase 2 (model architecture).

### Pitfall 9: Injury/Lineup Uncertainty at Prediction Time

**What goes wrong:** The model assumes the player will play, but at prediction time (typically Tuesday-Thursday for lineup decisions), injury status is uncertain. A "Questionable" player might get 0 points (DNP) or full points. The model has no mechanism to handle this uncertainty.

**Prevention:**
- The existing injury adjustment system in `projection_engine.py` (Questionable=0.85, Doubtful=0.50, Out=0.0) is a reasonable post-processing step. Keep this as a separate layer on top of ML predictions.
- Do NOT train the model with injury status as a feature (it changes between training time and game time). Instead, apply injury multipliers as a post-processing step, same as the heuristic does.
- Provide prediction intervals (not just point estimates) so users can see the uncertainty. A "Questionable" player's interval should be much wider than a healthy player's.
- For players expected to miss the game entirely, zero out the projection (this is already handled in the heuristic).

**Phase to address:** Phase 3 (post-processing and integration).

### Pitfall 10: Walk-Forward CV With Insufficient History for Early Folds

**What goes wrong:** The first walk-forward fold trains on season 2020 only and predicts 2021. With ~8,500 player-weeks per season, this seems like enough data, but many players in 2021 did not play in 2020 (rookies, free agents). The model has no history for them and performs poorly on the first fold, dragging down aggregate CV metrics.

**Prevention:**
- Start walk-forward CV from season 2021 (train on 2020-2021, predict 2022) to ensure at least 2 seasons of training data.
- Use an expanding window (not sliding) to maximize training data for each fold.
- Report per-fold metrics separately so you can see if early folds are dragging down the average.
- For new players in each fold, fall back to population-level predictions (the model should already do this if player identity is not a feature).

**Phase to address:** Phase 2 (evaluation framework).

### Pitfall 11: Complex Model That Does Not Beat the Heuristic Baseline

**What goes wrong:** After weeks of feature engineering, model tuning, and ensemble building, the ML model achieves MAE 4.85 versus the heuristic baseline of 4.91. A 1.2% improvement that may not be statistically significant. The complexity cost (maintenance, interpretability, compute) outweighs the marginal gain.

**Why it happens:** The heuristic baseline in `projection_engine.py` already captures the most important signals: recent performance (rolling averages), usage stability (snap/target share), opponent matchup, Vegas implied totals, and ceiling shrinkage. These are exactly the features an ML model would learn. The marginal gain from ML comes from learning non-linear interactions and position-specific patterns that the heuristic misses, but this gain is often small because the heuristic was manually tuned on backtests (MAE went from ~5.5 to 4.91).

**Prevention:**
- Set a minimum improvement threshold BEFORE building the model. Recommendation: ML must beat heuristic by at least 0.2 MAE points (4% improvement) on EACH position to justify the complexity.
- Run an honest ablation at the end: ML model vs heuristic on the same holdout weeks, same evaluation code. Use the existing `backtest_projections.py` framework.
- If the ML model does not clear the bar, consider a hybrid: use ML for positions where it helps (likely RB/WR with more data and clearer opportunity signals) and keep the heuristic for positions where ML does not help (likely TE/QB).
- The v2.0 game prediction lesson applies here: the ensemble improved from 50.0% to 53.0% ATS over the single XGBoost. A 3% improvement justified the complexity. Set a similar bar for player predictions.

**Phase to address:** Final phase (evaluation and ship/skip decision). But the bar must be defined in Phase 1.

## Minor Pitfalls

### Pitfall 12: Forgetting to Lag Opponent Features

**What goes wrong:** Using the opponent's defensive ranking from the current week (which includes the current game's result) instead of the prior week's ranking. The existing `player_analytics.py` computes `compute_opponent_rankings` but it must be shifted by one week for use as a predictive feature.

**Prevention:** Apply `.shift(1)` to all opponent ranking features, grouped by team and season. Verify that week 1 predictions have NaN opponent features (there is no week 0 data) and handle with imputation (league-average defense).

**Phase to address:** Phase 1 (feature engineering).

### Pitfall 13: Target Variable Inconsistency Across Scoring Formats

**What goes wrong:** Training on PPR fantasy points but evaluating on Half-PPR, or mixing scoring formats in the training data. This seems obvious but is easy to introduce when the same training pipeline serves multiple scoring formats.

**Prevention:** If predicting component stats (recommended), the target variables are scoring-format-agnostic (rushing_yards, receptions, TDs). Fantasy points are computed only at evaluation time using `scoring_calculator.py`. This sidesteps the issue entirely.

**Phase to address:** Phase 2 (model training pipeline).

### Pitfall 14: Ignoring the Bye Week Edge Case

**What goes wrong:** The model predicts non-zero points for players on bye weeks, or bye week rows corrupt rolling average calculations.

**Prevention:** The existing heuristic handles this (`is_bye_week=True` zeroes all stats). The ML pipeline must either exclude bye weeks from training entirely or include them with zero targets. Recommendation: exclude from training (bye weeks carry no signal), apply zero projection as a post-processing rule.

**Phase to address:** Phase 1 (data preparation).

### Pitfall 15: Breaking the 594 Existing Tests

**What goes wrong:** New ML player prediction code introduces imports, dependencies, or config changes that break existing game prediction tests, fantasy projection tests, or Bronze/Silver pipeline tests.

**Prevention:**
- New code goes in new modules (e.g., `src/player_prediction.py`, `src/player_feature_engineering.py`). Do not modify existing files except `config.py` (for new constants) and `scripts/` (for new CLIs).
- Run `python -m pytest tests/ -v` after every significant change.
- Add new tests in new files (e.g., `tests/test_player_prediction.py`). Do not modify existing test files.
- The game prediction ensemble, fantasy heuristic projections, and draft tools must continue to work exactly as before.

**Phase to address:** Every phase. Continuous integration discipline.

## Integration-Specific Pitfalls (Adding to Existing Platform)

### Pitfall 16: Conflicting Projection Outputs

**What goes wrong:** The ML model produces projections stored in the same Gold path (`data/gold/projections/`) as the heuristic, causing confusion about which projection is being used downstream by the draft tool and backtest scripts.

**Prevention:**
- Store ML projections in a separate path: `data/gold/ml_projections/` or `data/gold/projections_v3/`.
- Add a `model_version` column to projection DataFrames (e.g., "heuristic_v1" vs "ml_v3").
- Keep the heuristic running as a fallback. The draft tool should default to ML projections but fall back to heuristic if ML is unavailable (e.g., for positions where ML was not shipped).
- The generate_projections.py script should accept a `--model ml` flag, defaulting to the existing heuristic for backward compatibility.

**Phase to address:** Phase 3 (integration). Design the storage pattern early.

### Pitfall 17: Retraining Frequency and Staleness

**What goes wrong:** The ML model is trained once before the season and never updated, so by week 10 its player features are based on stale weights that do not reflect mid-season role changes, injuries, or team personnel moves.

**Prevention:**
- Design for weekly retraining (or at minimum, weekly feature recomputation with a pre-trained model).
- The existing `weekly-pipeline.yml` GitHub Action runs on Tuesdays. The ML prediction step should slot into this pipeline after Silver transformation.
- At minimum, features must be recomputed weekly (rolling averages update). Full model retraining can be monthly or when new data significantly changes the feature distribution.

**Phase to address:** Phase 3 (integration with pipeline).

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Feature engineering | Same-game stat leakage (#1) | Feature availability audit; shift(1) on everything |
| Feature engineering | Forgetting to lag opponent features (#12) | Automated leakage detection tests |
| Feature engineering | Historical usage overfitting (#5) | Include role-change detection features |
| Model architecture | Wrong unit of analysis (#2) | Position-pooled models, not per-player |
| Model architecture | Scoring format sensitivity (#7) | Predict components, not fantasy points |
| Model architecture | TD variance domination (#4) | Opportunity/efficiency decomposition |
| Model training | Small sample per player (#8) | Cross-player pooling, player-type features |
| Model training | Insufficient early CV folds (#10) | Expanding window, min 2 seasons training |
| Evaluation | Aggregate metrics hiding failure (#3) | Per-position benchmarks as primary metric |
| Evaluation | Not beating baseline (#11) | Set 4% improvement bar per position |
| Integration | Conflicting outputs (#16) | Separate Gold paths, model_version column |
| Integration | Team total incoherence (#6) | Post-processing scaling to implied totals |
| Integration | Breaking existing tests (#15) | New modules only, CI after every change |
| Integration | Injury uncertainty (#9) | Post-processing multipliers, not model features |

## Sources

- Existing codebase analysis: `src/projection_engine.py`, `src/player_analytics.py`, `src/player_advanced_analytics.py`, `src/feature_engineering.py`, `src/ensemble_training.py`
- [FanDuel: Touchdown Regression](https://www.fanduel.com/research/touchdown-regression-what-it-is-and-how-to-use-it-for-player-prop-bets-fantasy-football) — TD variance in fantasy scoring
- [Harvard Science Review: Model Validation in Sports Predictions](https://harvardsciencereview.org/2025/09/18/model-validation-how-to-ensure-your-sports-predictions-arent-just-lucky/) — overfitting and validation pitfalls
- [SMU Data Science Review: Predicting Fantasy Football](https://scholar.smu.edu/cgi/viewcontent.cgi?article=1279&context=datasciencereview) — ML approaches to fantasy prediction
- [MachineLearningMastery: Data Leakage](https://machinelearningmastery.com/data-leakage-machine-learning/) — leakage patterns and prevention
- [Towards Data Science: Seven Causes of Data Leakage](https://towardsdatascience.com/seven-common-causes-of-data-leakage-in-machine-learning-75f8a6243ea5/) — temporal leakage in time-series
- [RotoWire: PPR vs Standard](https://www.rotowire.com/football/article/ppr-vs-standard-scoring-explained-94844) — scoring format impact on player valuation
- [Footballguys: Expectation and Variance](https://www.footballguys.com/article/DFS_expectationvariance) — variance in fantasy point distributions
- [Frontiers in Sports: NFL Win Prediction with ML](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1638446/full) — overfitting in NFL ML models
