# Feature Research

**Domain:** ML-based player fantasy football projection system (per-position QB/RB/WR/TE)
**Researched:** 2026-03-29
**Confidence:** MEDIUM-HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any ML fantasy projection system must have to be considered credible. Missing these means the system underperforms basic heuristic approaches.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Position-specific models | QB/RB/WR/TE have fundamentally different stat profiles and volatility patterns; a single model cannot capture positional nuances | MEDIUM | Separate training pipelines per position. RB rushing vs receiving split; QB passing + rushing; WR/TE targets-driven. Already have `POSITION_STAT_PROFILE` dict in projection_engine.py |
| Rolling window features (3/6/season) | Recency weighting is the single most impactful projection technique; recent form dominates season-long averages | LOW | **Already built.** Silver usage layer has roll3/roll6/std for all key stats. Direct reuse. |
| Opportunity volume features | Opportunity (targets, carries, snap%) is far more predictive than efficiency (YPC, YPR). Target share r=0.70 Y/Y; snap share correlates better than raw touches for RBs | LOW | **Already built.** Silver usage has target_share, carry_share, snap_pct, air_yards_share, all with rolling windows |
| Matchup adjustment (defense vs position) | Opponent defensive quality creates 10-20% variance in player production; users expect matchup-aware projections | MEDIUM | Silver defense/positional has avg_pts_allowed and rank per position per week. Need to join to player rows and lag properly (week N-1 opponent stats) |
| Vegas implied team totals | Implied team total is the single strongest correlate of fantasy production across all positions. Higher implied total = more scoring opportunities | LOW | **Already built.** Bronze schedules have spread_line and total_line; Silver market_data has opening lines. Implied total = (total / 2) - (spread / 2) for home team |
| Injury status adjustments | Out/IR players score zero; Questionable players average ~85% production; ignoring injuries is a fatal flaw | LOW | **Already built.** projection_engine.py has injury multipliers (Active=1.0, Questionable=0.85, Doubtful=0.50, Out/IR=0.0) |
| Walk-forward temporal CV | Fantasy data is temporal; k-fold CV on shuffled data leaks future information and inflates metrics. Must train on weeks 1..N, predict N+1 | MEDIUM | Pattern exists in ensemble_training.py for game predictions. Adapt for player-level: same walk-forward approach, but group by player to avoid in-sample leakage |
| Bye week handling | Players on bye score exactly zero; projections must reflect this | LOW | **Already built.** projection_engine.py zeroes all stats and sets is_bye_week=True |
| Per-position evaluation metrics | MAE/RMSE/correlation per position is the standard accuracy benchmark; aggregate MAE hides positional strengths and weaknesses | LOW | **Already built.** backtest_projections.py reports per-position MAE/RMSE/bias/correlation. Reuse with new model output |
| Touchdown regression to mean | TDs are high-variance (only 11% of 10+ TD players repeat); models must not extrapolate hot TD streaks. Expected TDs based on red zone opportunity + historical TD rates are more stable | MEDIUM | Compute expected TDs from red zone target share and red zone carry share with historical conversion rates. Use as feature instead of raw TD counts |

### Differentiators (Competitive Advantage)

Features that separate top-tier projections from average ones. These are where accuracy gains live.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Opportunity-efficiency decomposition | Predict opportunity (targets, carries, snaps) and efficiency (YPC, YPR, catch%) separately, then multiply. Opportunity is sticky (r~0.70); efficiency is noisy. Decomposing prevents the model from anchoring on volatile efficiency stats | HIGH | This is the core architectural differentiator. Two-stage model: Stage 1 predicts share/volume, Stage 2 predicts per-touch efficiency, then combine. Existing Silver has all ingredients (usage metrics + advanced profiles) |
| Team-level constraint / top-down allocation | Start from team implied total, decompose to passing/rushing, then allocate to players by share. Ensures player projections sum to a plausible team total -- prevents the "every player has a great week" problem | HIGH | Requires a team-total model (or use Vegas implied totals) plus share allocation. This is how ESPN/Mike Clay projections work. Key constraint: target shares must sum to ~100%, carry shares must sum to ~100% |
| Game script modeling | Negative game script (trailing) increases passing volume; positive script increases rushing volume. Spread predicts script: big underdogs throw more, big favorites run more | MEDIUM | Silver game_context has spread data. Can model conditional target/carry volume shifts based on expected game script. Already have game_script column in usage data |
| NGS advanced efficiency features | Separation, YAC above expectation, CPOE, rush yards over expected -- these are "true talent" indicators that regress less than raw efficiency stats | MEDIUM | **Already built.** Silver advanced profiles have all NGS metrics with rolling windows. These are premium features that most projection systems lack |
| Red zone opportunity features | Red zone targets and carries are the primary TD driver. Red zone target share is more predictive of future TDs than raw TD counts | MEDIUM | Silver usage has rz_target_share. Need to add rz_carry_share (may need Bronze PBP extraction for inside-20 carries). TD regression feature = f(rz_share, historical_conversion_rate) |
| Snap share trajectory / role detection | Increasing snap share over 3 weeks signals role expansion (breakout); decreasing signals demotion. The derivative of snap share is as important as the level | LOW | Compute snap_pct_roll3 - snap_pct_roll6 as "role momentum" feature. Already have both rolling windows in Silver usage |
| Player quality context (QB for skill positions) | WR/TE/RB production is heavily influenced by QB quality. A backup QB starting tanks receiver projections by 20-30% | LOW | **Already built.** Silver player_quality has qb_passing_epa, backup_qb_start, qb_injury_impact with rolling windows. Join to player rows by team/week |
| Draft capital + combine for rookies | Rookies have no NFL history; draft capital is the strongest predictor of Year 1 opportunity. Higher picks get more snaps earlier | LOW | **Already built.** Silver historical has combine_draft_profiles for 9,892 players. Use draft round/pick as rookie baseline features |
| Scoring format awareness | PPR vs Half-PPR vs Standard changes optimal player rankings significantly; model should be format-aware or produce stat-level projections | LOW | Predict individual stats (yards, TDs, receptions) not total fantasy points. Then apply scoring formula downstream. This is already the pattern in projection_engine.py |
| Consistency/floor-ceiling estimation | Variance of projections matters for lineup decisions. A player projected at 15 with low variance (safe floor) differs from one at 15 with high variance (boom/bust) | LOW | Use rolling standard deviation of fantasy points (already in Silver as fantasy_points_ppr_std) plus positional variance baselines. Already partially built in projection_engine.py add_floor_ceiling() |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems at this project's scale and data availability.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Deep learning / LSTM sequence models | "Neural networks are better" | Tabular data with ~5,000 player-weeks per position per season is too small for deep learning to outperform gradient boosting. Academic research confirms GBMs dominate on tabular NFL data. Adds PyTorch dependency, GPU complexity, harder to debug | XGBoost/LightGBM/CatBoost ensemble (proven in v2.0 game prediction). Same stacking architecture, adapted for player-level |
| Weather features for player projections | "Rain/wind affects passing" | Weather effects are real but small (~2-5% variance) and already captured indirectly by Vegas lines (which incorporate weather). Adding weather directly creates feature noise at player level | Use Vegas implied totals which already price in weather. Silver game_context has weather if needed later |
| WR-CB matchup modeling | "Shadow coverage matters" | Requires snap-level alignment data (which CB covered which WR on each route). No reliable public data source at scale. Neo4j graph planned for v3.1 but needs its own data pipeline | Use team-level defense vs WR rank from Silver defense/positional as proxy. Reserve WR-CB for v3.1 graph-enhanced predictions |
| Injury prediction model | "Predict who gets hurt" | Injury occurrence is essentially random (low base rate, high variance). Predicting injuries is a separate research domain. Predicting injury *impact* (what happens when a player IS hurt) is tractable | Use injury status from Bronze injuries with existing multipliers. Focus on injury *impact* (backup QB effect, snap share redistribution) not injury *prediction* |
| Real-time in-game projections | "Update projections as game unfolds" | Requires streaming data infrastructure, sub-second latency, completely different architecture. Weekly batch projections serve 99% of fantasy use cases (lineup setting, waiver decisions, trade evaluation) | Batch weekly projections on Tuesday/Wednesday. Live projection is v5+ territory |
| Predict exact stat lines | "Tell me Mahomes throws for exactly 287 yards" | Point estimates of individual stats have enormous confidence intervals. Projecting yards to single-digit precision implies false confidence | Predict stat distributions (mean + variance). Present as ranges: "250-320 passing yards" with expected value. Already have floor/ceiling framework |
| Ensemble of 10+ models per position | "More models = better" | Diminishing returns past 3-4 diverse base learners. Adds training time, complexity, and overfitting risk without meaningful accuracy improvement | XGB + LGB + CatBoost + Ridge meta-learner (same proven v2.0 architecture). Four diverse learners is the sweet spot |

## Feature Dependencies

```
[Vegas Implied Team Totals]
    |
    +--requires--> [Bronze schedules + Silver market_data] (ALREADY BUILT)
    |
    +--enables---> [Top-Down Team Constraint]
                       |
                       +--requires--> [Player Share Models] (opportunity decomposition)
                                          |
                                          +--requires--> [Silver usage metrics] (ALREADY BUILT)

[Opportunity-Efficiency Decomposition]
    |
    +--requires--> [Silver usage: target_share, carry_share, snap_pct] (ALREADY BUILT)
    +--requires--> [Silver advanced: NGS efficiency metrics] (ALREADY BUILT)
    +--enables---> [TD Regression Features] (expected TDs from opportunity)
    +--enables---> [Game Script Adjustments] (conditional volume shifts)

[Position-Specific Models]
    |
    +--requires--> [Feature Engineering Pipeline] (player-level feature vector)
    +--requires--> [Walk-Forward CV Framework] (adapted from game prediction)
    +--requires--> [Per-Position Evaluation] (ALREADY BUILT in backtest_projections.py)

[Matchup Adjustments]
    |
    +--requires--> [Silver defense/positional] (ALREADY BUILT)
    +--requires--> [Proper lag (week N-1 opponent stats)] (standard pattern)

[Rookie Projections]
    |
    +--requires--> [Silver historical: combine_draft_profiles] (ALREADY BUILT)
    +--enhances--> [Position-Specific Models] (draft capital as cold-start feature)

[Player Quality Context]
    |
    +--requires--> [Silver player_quality: QB EPA, injury impact] (ALREADY BUILT)
    +--enhances--> [WR/TE/RB Models] (QB quality as context feature)
```

### Dependency Notes

- **Top-Down Constraint requires Share Models:** You need player share predictions before you can allocate a team total to individual players.
- **TD Regression requires Opportunity Decomposition:** Expected TDs are computed from red zone opportunity, not raw TD history. Build opportunity features first.
- **Rookie Projections enhance Position Models:** Draft capital provides cold-start features when no NFL history exists. Can be added as a feature to the main model, not a separate system.
- **Most Silver data is already built:** The existing Silver layer provides ~80% of the features needed. The main work is assembling a player-level feature vector (analogous to what feature_engineering.py does for game-level predictions).

## MVP Definition

### Launch With (v3.0 Phase 1-2)

Minimum viable ML projection system that must beat the current heuristic baseline (MAE 4.91).

- [ ] **Player-level feature vector assembly** -- Join Silver usage + advanced + defense/positional + player_quality + game_context + market_data into per-player-per-week rows with proper temporal lags. Analogous to feature_engineering.py but at player granularity
- [ ] **Position-specific gradient boosting models** -- Separate XGBoost models for QB/RB/WR/TE predicting next-week fantasy points. Start with direct point prediction (not decomposed) as baseline
- [ ] **Walk-forward temporal CV** -- Train on seasons 1..N weeks 1..W, validate on W+1. Holdout 2025 season entirely. Adapt ensemble_training.py pattern
- [ ] **Matchup features** -- Opponent defense vs position rank (lagged), opponent EPA allowed by position
- [ ] **Vegas context** -- Implied team total, spread (game script proxy)
- [ ] **Per-position evaluation** -- MAE/RMSE/correlation per position vs current heuristic baseline. Ship only if MAE < 4.91

### Add After Validation (v3.0 Phase 3-4)

Features to add once the baseline ML model is working and beating the heuristic.

- [ ] **Opportunity-efficiency decomposition** -- Predict target share/carry share/snap%, then predict per-touch efficiency, then combine. Only build if direct prediction doesn't sufficiently beat baseline
- [ ] **Top-down team constraint** -- Use implied team total to constrain player projections so they sum to a plausible team total. Helps prevent impossible projection sets
- [ ] **TD regression features** -- Expected TDs from red zone share * historical conversion rates. Replace raw TD rolling averages with expected TD features
- [ ] **Role momentum features** -- snap_pct_roll3 minus snap_pct_roll6 as breakout/demotion signal
- [ ] **Ensemble stacking** -- XGB + LGB + CatBoost + Ridge meta-learner per position (same v2.0 pattern). Only if single XGB leaves accuracy on the table

### Future Consideration (v3.1+)

Features to defer until ML projections are proven and stable.

- [ ] **WR-CB matchup graph features** -- Requires Neo4j + snap-level data pipeline (v3.1 milestone)
- [ ] **Bayesian uncertainty quantification** -- Replace point estimates with posterior distributions for true floor/ceiling
- [ ] **Cross-position interaction features** -- How does adding a WR1 injury affect WR2/TE1 target share? Requires roster-level modeling
- [ ] **Dynasty / multi-year projection** -- Aging curves, career trajectory modeling. Different problem than weekly projections

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Player-level feature vector | HIGH | MEDIUM | P1 |
| Position-specific XGBoost models | HIGH | MEDIUM | P1 |
| Walk-forward CV framework | HIGH | LOW | P1 |
| Matchup features (defense vs pos) | HIGH | LOW | P1 |
| Vegas implied team total | HIGH | LOW | P1 |
| Per-position evaluation vs baseline | HIGH | LOW | P1 |
| Opportunity-efficiency decomposition | HIGH | HIGH | P2 |
| Top-down team constraint | MEDIUM | HIGH | P2 |
| TD regression (expected TDs) | MEDIUM | MEDIUM | P2 |
| Role momentum (snap trajectory) | MEDIUM | LOW | P2 |
| Ensemble stacking (multi-model) | MEDIUM | MEDIUM | P2 |
| Rookie draft capital features | MEDIUM | LOW | P2 |
| Game script conditional volumes | MEDIUM | MEDIUM | P2 |
| Floor/ceiling variance estimation | LOW | LOW | P3 |
| WR-CB graph matchups | HIGH | HIGH | P3 (v3.1) |
| Bayesian uncertainty | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch -- core ML pipeline
- P2: Should have -- accuracy improvements after baseline works
- P3: Nice to have -- future milestones

## Competitor Feature Analysis

| Feature | ESPN (Mike Clay) | FantasyPros (consensus) | DraftSharks | Our Approach |
|---------|-----------------|------------------------|-------------|--------------|
| Projection method | Manual team-level decomposition: plays -> run/pass split -> player shares. Expert-adjusted, not pure ML | Aggregate of 10+ expert projections (wisdom of crowds) | ML + aging curves + draft capital, multi-year dynasty focus | ML gradient boosting on Silver feature vector. Automated, reproducible, position-specific |
| Stat decomposition | Top-down: team attempts -> player share -> per-touch efficiency | N/A (aggregation of others) | Bottom-up from player history | Hybrid: ML predicts stats directly, with team total as constraint feature |
| Matchup adjustment | Manual opponent analysis per game | Implicit in expert rankings | Defense vs position rankings | Automated: Silver defense/positional rank + opponent EPA as features |
| Recency weighting | Expert judgment on recent form | Varies by expert | Algorithmic rolling windows | Explicit roll3/roll6/STD features with model-learned weights |
| Accuracy (Half-PPR MAE) | ~4.5-5.0 (estimated from FFA analysis) | ~4.3-4.8 (FFA Average is consistently top-tier across positions) | Competitive, dynasty-focused | Current heuristic: 4.91. Target: <4.5 with ML |
| Rookie handling | Expert scouting + draft capital | Varies by expert | ML model with combine + draft capital | Draft capital features from Silver historical + positional baselines for cold start |
| TD modeling | Expert judgment, some regression | Varies | Expected TDs from opportunity | Red zone share * historical conversion as feature; model learns regression naturally |

## Accuracy Benchmarks and Targets

Based on research into the industry:

| Position | Current Heuristic MAE | Industry Best (FFA Avg) | Target ML MAE | Notes |
|----------|----------------------|------------------------|---------------|-------|
| QB | 6.58 | ~5.5-6.0 (est.) | <6.0 | QBs have highest variance; bias of -2.20 suggests systematic under-projection |
| RB | 5.06 | ~4.5-5.0 (est.) | <4.8 | RB snap share is stickiest predictor; opportunity decomposition should help most here |
| WR | 4.85 | ~4.3-4.8 (est.) | <4.5 | Target share (r=0.70 Y/Y) is strongest feature; NGS separation adds signal |
| TE | 3.77 | ~3.5-4.0 (est.) | <3.5 | Smallest pool; high concentration in top players. QB quality feature matters most |
| Overall | 4.91 | ~4.3-4.5 (est.) | <4.5 | Target is a ~10% improvement over current heuristic |

**Note on benchmarks:** Industry MAE numbers are estimates based on FFA accuracy analysis methodology (top 20 QBs/TEs, top 50 RBs/WRs, 2019-2023, Half-PPR). Exact numbers are not publicly disclosed as raw MAE values. Confidence: LOW on exact industry numbers, MEDIUM on relative ranking.

## Existing Silver Data Reuse Map

Critical for implementation planning: what already exists vs what must be built.

| Silver Source | Path | Key Features for Player Prediction | Status |
|--------------|------|-----------------------------------|--------|
| Player usage | players/usage/ | target_share, carry_share, snap_pct, air_yards_share, rz_target_share, all rolling windows (3/6/STD), game_script, is_home | READY -- 113 columns per player-week |
| Player advanced | players/advanced/ | NGS separation/YAC/CPOE, rushing efficiency (RYOE), PFR pressure rates, all with rolling windows | READY -- 119 columns per player-week |
| Player historical | players/historical/ | Combine measurables, draft round/pick (for rookies) | READY -- 9,892 player profiles |
| Defense positional | defense/positional/ | avg_pts_allowed and rank per position per team per week | READY -- join by opponent_team + week |
| Player quality | teams/player_quality/ | QB EPA, backup_qb_start, injury impact, rolling windows | READY -- 28 columns per team-week |
| Game context | teams/game_context/ | is_home, is_dome, temperature, wind, rest_days, travel_miles | READY -- 22 columns per team-week |
| Market data | teams/market_data/ | Opening spread, opening total (for implied team totals) | READY -- all 10 seasons |
| Team PBP metrics | teams/pbp_metrics/ | Team EPA, success rate, CPOE (for team offensive context) | READY -- per team-week |
| Team tendencies | teams/tendencies/ | Pace, PROE, early-down run rate (for volume context) | READY -- per team-week |

**Bottom line:** ~80% of features needed for ML player prediction already exist in the Silver layer. The primary build effort is (1) a player-level feature vector assembler that joins these sources, and (2) the model training/evaluation pipeline.

## Sources

- [SumerSports: Sticky Football Stats](https://sumersports.com/the-zone/sticky-football-stats-predictive-nfl-metrics/) -- Target share r=0.70, YRPR r>0.60, EPA/pass r=0.60
- [Fantasy Football Analytics: Most Accurate Projections](https://fantasyfootballanalytics.net/2024/12/which-fantasy-football-projections-are-most-accurate.html) -- FFA Average is top-tier across all positions
- [ESPN: Trust the Process (Mike Clay)](https://www.espn.com/fantasy/football/story/_/id/48276085/2026-fantasy-football-projections-draft-rankings-trends-carry-target-shares) -- Team-level decomposition methodology
- [Yards Per Fantasy: How to Build Projections](https://yardsperfantasy.com/build-fantasy-football-projections/) -- Top-down team allocation methodology
- [FanDuel Research: Touchdown Regression](https://www.fanduel.com/research/touchdown-regression-what-it-is-and-how-to-use-it-for-player-prop-bets-fantasy-football) -- Only 11% of 10+ TD players repeat; average loss of 5.2 TDs
- [ESPN: Opportunity-Adjusted Fantasy Points (OFP)](https://www.espn.com/fantasy/football/story/_/id/24318831/fantasy-football-introducing-ofp-opportunity-adjusted-fantasy-points-forp-fantasy-points-replacement-player) -- Opportunity vs efficiency decomposition
- [The Ringer: Stickiest Stats](https://theringer.com/nfl-preview/2019/8/15/20806716/fantasy-football-sticky-stats) -- Usage stats most predictive
- [Fantasy Football Analytics: Positional Bias in Projections](https://fantasyfootballanalytics.net/2025/07/fantasy-football-projections-exploring-positional-bias-in-projections.html) -- Position-specific accuracy patterns
- [The Fantasy Footballers: POP Method](https://www.thefantasyfootballers.com/analysis/players-who-pop-a-new-method-for-predicting-fantasy-football-scoring/) -- Random forest opportunity-based projection
- [PFF: 2026 Rookie RB Prospect Model](https://www.pff.com/news/fantasy-football-2026-rookie-running-back-prospect-model) -- Draft capital + combine for rookie projections
- [FantasyPros: How to Use Vegas Odds](https://www.fantasypros.com/2023/08/how-to-use-vegas-odds-for-fantasy-football-2023/) -- Implied totals as strongest correlate
- [SI: Game Script Impact on Fantasy](https://www.si.com/fantasy/2021/08/09/football-game-script-impact-quarterbacks) -- Negative script increases passing volume

---
*Feature research for: ML-based player fantasy projection system (v3.0)*
*Researched: 2026-03-29*
