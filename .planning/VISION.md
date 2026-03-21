# Long-Term Vision: State-of-the-Art NFL Prediction System

**Created:** 2026-03-21
**Context:** After completing v1.4 Phase 25 (feature assembly + model training), this document captures the full roadmap to build a prediction system capable of finding edges against Vegas closing lines.

## Current State (v1.4 in progress)

- 337-column team-level differential feature vector from 8 Silver sources
- Single XGBoost regressor per target (spread, total)
- Walk-forward CV with season boundaries, Optuna tuning
- 2016-2024 data (~272 REG games/season, ~2,400 total)
- Conservative hyperparameters, early stopping, holdout guard (2024 sealed)

## Gap Analysis

### What we have vs what beats Vegas

| Dimension | Current | State-of-the-Art |
|-----------|---------|-----------------|
| Features | Team-level aggregates only | Player-level + team + market data |
| Model | Single XGBoost per target | Ensemble of 4-5 diverse models, stacked |
| Output | Point estimate | Full probability distribution |
| Evaluation | MAE on holdout | CLV, ATS%, calibration, EV tracking |
| Temporal | Train once, predict forever | Weekly retraining, regime detection |
| Market data | None | Opening/closing lines, movement, sharp action |
| Betting | None | Kelly criterion, line shopping, shadow tracking |

---

## Future Milestones

### v2.0 — Player-Level Prediction Features

**Goal:** Add player-specific signal to game predictions — the single biggest gap.

**Rationale:** A backup QB starting swings a game 3-7 points. Our model can't see this. Team aggregates smooth over the most predictive information in football.

#### Planned Capabilities

1. **QB Quality Differential**
   - Individual passing EPA, CPOE, pressure rate, time-to-throw (from NGS)
   - Starter vs backup detection from depth charts + practice reports
   - QB rating differential as a standalone feature (historically one of the most predictive single features)

2. **Positional Replacement Quality**
   - Not binary injury status — measure the talent gap between starter and replacement
   - Weight by positional importance: QB >> LT > Edge > WR1 > RB
   - Use draft capital + career stats as proxy for replacement quality

3. **WR-CB Matchup Modeling (Neo4j)**
   - Target share networks: who gets targets vs which coverage scheme
   - Separation metrics by coverage type (man/zone, press/off)
   - Slot vs outside alignment efficiency
   - Requires Neo4j graph database (Phase 5, currently deferred)

4. **Depth Chart Delta Features**
   - Week-over-week roster changes as features
   - Number of new starters (instability signal)
   - Games started by current lineup (cohesion signal)

5. **Personnel & Formation Data**
   - 11 vs 12 vs 21 personnel grouping rates (among most predictive for totals)
   - Pre-snap motion rates
   - Formation tendency changes (signals scheme adjustments)

#### Data Sources Needed
- NGS player-level tracking (public via nfl-data-py, aggregated)
- Depth charts (already in Bronze)
- Practice reports (new — would need scraping or API)
- PFF grades (paid API, ~$200/yr for researcher tier)

---

### v2.1 — Model Architecture Upgrade

**Goal:** Replace single XGBoost with calibrated ensemble producing probability distributions.

**Rationale:** No single model captures all signal. Ensembles of diverse learners consistently outperform individual models on tabular data (see Kaggle meta-analysis). Probability distributions enable Kelly criterion betting.

#### Planned Capabilities

1. **Diverse Model Ensemble**
   - XGBoost (current) + LightGBM + CatBoost + Ridge Regression
   - Each trained with same walk-forward CV framework
   - Diversity is key — models must disagree on different games to add value

2. **Meta-Learner Stacking**
   - Train a simple model (logistic/linear) on out-of-fold predictions from base models
   - Learns optimal weighting per game context
   - Out-of-fold predictions prevent information leakage

3. **Probabilistic Output**
   - Predict P(home covers) rather than just "spread = -3.5"
   - Enables EV calculation: only bet when edge × payout > 1
   - Calibration plots to verify predicted probabilities match observed frequencies

4. **Quantile Regression**
   - Predict 10th/25th/50th/75th/90th percentile of outcomes
   - High-variance games (two bad defenses) have wider distributions
   - Useful for totals where distribution shape matters (overtime risk)

5. **Context-Specific Sub-Models**
   - Divisional games behave differently (familiarity effect)
   - Primetime games have different patterns (home field less valuable)
   - Weather games (wind > 20mph, cold < 20°F) compress totals
   - Playoff games (smaller sample, but distinct dynamics)

#### Technical Notes
- scikit-learn, LightGBM, CatBoost all support walk-forward — reuse existing framework
- Meta-learner trains on K-fold out-of-fold predictions (not validation predictions)
- Calibration via Platt scaling or isotonic regression

---

### v2.2 — Advanced Feature Engineering

**Goal:** Extract deeper signal from existing data through smarter feature construction.

**Rationale:** We have rich data but extract it with fixed rolling windows and simple aggregates. Adaptive windows, momentum features, and regime detection can substantially improve signal without new data sources.

#### Planned Capabilities

1. **Adaptive Rolling Windows**
   - Early season (Weeks 1-4): weight prior season heavily (exponential decay)
   - Mid season (Weeks 5-10): blend prior + current (transition period)
   - Late season (Weeks 11-18): weight recent games almost exclusively
   - Implement as exponentially weighted moving averages with season-aware decay

2. **Momentum / Trend Features**
   - First derivative: is team EPA trending up or down? (3-game slope)
   - Second derivative: is improvement accelerating or decelerating?
   - Historically, teams on upward trajectories in Weeks 12-16 outperform their season averages

3. **Situational Motivation**
   - Clinched playoff teams in Week 17-18 rest starters → underperform spread
   - Eliminated teams play with less discipline → higher variance
   - Teams fighting for last playoff spot → overperform (motivation edge)
   - Draft positioning motivation for eliminated teams

4. **Pace-Adjusted Metrics**
   - Normalize EPA, yards, turnovers per play rather than per game
   - A team running 80 plays/game looks inflated on per-game EPA
   - Pace adjustment reveals true efficiency independent of game script

5. **Revenge / Familiarity**
   - Second meeting in divisional matchups has different dynamics
   - Losing team from first meeting adjusts; market may not fully price this
   - Home/away split for rematch games

6. **Regime Detection**
   - Detect structural breaks in team performance (change-point analysis)
   - Coaching changes, QB changes, key injuries create regime shifts
   - CUSUM or Bayesian change-point algorithms
   - Current rolling windows smooth over regime changes instead of detecting them

7. **Bayesian Prior Integration**
   - Start with preseason power ratings as prior
   - Update beliefs each week with observed performance
   - Naturally handles early-season small sample problem
   - Empirical Bayes or conjugate priors for efficiency

---

### v2.3 — Market Data Integration

**Goal:** Ingest historical and live odds data to enable proper evaluation and market-aware features.

**Rationale:** You cannot evaluate a betting model without market data. CLV (Closing Line Value) is the gold standard — if your model consistently beats the closing line at bet time, you have an edge. Raw ATS% is noisy and misleading over small samples.

#### Planned Capabilities

1. **Historical Odds Database**
   - Opening and closing lines across multiple books (DraftKings, FanDuel, BetMGM, Pinnacle)
   - Line movement time series (hourly snapshots)
   - Source: the-odds-api.com ($20/mo), DonBest, or Pro-Football-Reference
   - Schema: game_id, book, timestamp, spread, total, moneyline, juice

2. **Line Movement Features**
   - Opening-to-closing movement magnitude and direction
   - Reverse line movement (line moves opposite to public betting %) = sharp money
   - Steam moves (rapid, large moves across multiple books simultaneously)
   - These are among the most predictive features for ATS outcomes

3. **Market Consensus as Feature**
   - Average spread across books as "market wisdom" feature
   - Disagreement across books (max-min spread) as uncertainty signal
   - Pinnacle closing line as "sharpest" market benchmark

4. **CLV Tracking (Evaluation)**
   - For each hypothetical bet: record the line at "bet time" vs closing line
   - Positive CLV = you're consistently getting +EV positions
   - Industry gold standard: profitable bettors show consistent positive CLV even when ATS% is near 50%

#### Infrastructure
- New Bronze data type: `odds` with ingestion script
- Daily/hourly scraping job during season
- the-odds-api has historical data back to 2019

---

### v2.4 — Betting Framework

**Goal:** Formalize bet selection, sizing, and tracking so model predictions translate to quantified edges.

**Rationale:** A good model is necessary but not sufficient. Without Kelly criterion sizing, line shopping, and rigorous tracking, even a profitable model will underperform or lose money through poor bankroll management.

#### Planned Capabilities

1. **Expected Value (EV) Calculation**
   - For each game: `EV = P(cover) × payout - P(not cover) × stake`
   - Only flag games where EV > threshold (typically > 2-3% after vig)
   - Vig calculation: convert American odds to implied probability, sum both sides

2. **Kelly Criterion Bankroll Management**
   - Optimal bet size = edge / odds for each game
   - Half-Kelly or quarter-Kelly for practical risk management
   - Maximum single-game exposure limit (e.g., 3% of bankroll)

3. **Line Shopping Optimization**
   - Compare available lines across books
   - Quantify value of each half-point (3 and 7 are key numbers in NFL)
   - Alert when a book is offering a significantly better number

4. **Shadow Betting Tracker**
   - Track hypothetical bets for 1-2 seasons before real money
   - Full accounting: bet amount, line taken, result, P&L, CLV
   - Statistical significance testing: how many bets needed to confirm edge?
   - Rule of thumb: ~1,000 bets at 53%+ needed to be confident (overcoming ~4.5% vig)

5. **Confidence Calibration**
   - Do games where the model shows large edge actually hit at higher rates?
   - Calibration plot: predicted probability vs observed frequency in bins
   - If poorly calibrated, the model's confidence signals are unreliable
   - Platt scaling or isotonic regression to recalibrate

6. **Niche Market Analysis**
   - Identify specific market segments where model has biggest edge
   - Examples: early-season games, weather games, specific line ranges (e.g., 3-7 point spreads)
   - Focus bets on highest-edge niches rather than betting everything

---

### v3.0 — Production Infrastructure

**Goal:** Fully automated weekly pipeline from data ingestion to bet recommendations.

**Rationale:** Manual weekly runs are error-prone and slow. A production system retrains weekly, monitors for drift, and delivers actionable output on schedule.

#### Planned Capabilities

1. **Automated Weekly Pipeline**
   - Tuesday: ingest new Bronze data (game results, player stats)
   - Wednesday: retrain Silver features, run model retraining
   - Thursday: generate predictions for upcoming week (lines open Thursday)
   - Friday: compare predictions vs Thursday opening lines, flag edges

2. **In-Season Model Retraining**
   - Retrain weekly as new data arrives
   - Walk-forward: add each completed week to training set
   - Compare retrained model vs static model to quantify value of weekly updates

3. **Model Monitoring & Drift Detection**
   - Track rolling ATS%, CLV, calibration per week
   - Alert when model accuracy degrades (concept drift)
   - NFL meta evolves: RPO revolution, 4th down revolution, rule changes all shift distributions
   - Automated reversion to conservative defaults if drift detected

4. **A/B Testing Framework**
   - Run multiple model versions in parallel
   - Compare CLV across versions over same games
   - Promote best-performing version automatically

5. **Notification System**
   - Slack/email alerts for high-confidence edges
   - Weekly summary report: model picks, results, P&L, rolling metrics

---

### v3.1 — Alternative Data Sources

**Goal:** Integrate non-traditional data sources for information edges the market prices slowly.

**Rationale:** By the time traditional stats are published, the market has already priced them. Alternative data — practice reports, news, tracking data — can provide information before the market adjusts.

#### Planned Capabilities

1. **Practice Report Parsing**
   - Wednesday/Thursday/Friday injury participation reports
   - Parse participation level (Full/Limited/DNP) trends across the week
   - Wednesday DNP → Thursday Limited → Friday Full = likely to play (bullish)
   - Automation: scrape from NFL.com or team websites

2. **Coaching Decision Modeling**
   - 4th down aggressiveness rates (persistent coach trait)
   - 2-point conversion tendencies
   - Clock management quality (timeouts, late-game decisions)
   - Coaching staff changes (new OC/DC mid-season impact)

3. **Player Tracking Data (Advanced)**
   - NFL Next Gen Stats public data is aggregated — limited value
   - Raw tracking data (if accessible) shows formation alignment, route trees, defender positioning
   - Focus on derived features: average separation, route win rate, pressure time

4. **News & Social NLP**
   - Contract disputes, locker room issues, off-field distractions
   - Not always predictive, but occasionally creates real edges
   - Sentiment scoring via LLM on beat reporter tweets
   - Low priority — high noise-to-signal ratio

---

## Milestone Sequencing

| Milestone | Priority | Dependency | Estimated Scope |
|-----------|----------|------------|----------------|
| v1.4 ML Game Prediction | **Current** | — | Phases 24-27 |
| v2.0 Player-Level Features | High | v1.4 complete | 4-5 phases |
| v2.1 Model Ensemble | High | v2.0 (richer features make ensemble more valuable) | 3-4 phases |
| v2.2 Advanced Features | Medium | v1.4 (can run parallel with v2.0) | 3-4 phases |
| v2.3 Market Data | High | v1.4 (needed for proper evaluation) | 2-3 phases |
| v2.4 Betting Framework | Medium | v2.3 (needs market data first) | 2-3 phases |
| v3.0 Production Infra | Medium | v2.1 + v2.3 | 3-4 phases |
| v3.1 Alternative Data | Low | v2.0 | 2-3 phases |

**Recommended order:** v1.4 → v2.3 (market data for evaluation) → v2.0 (player features) → v2.1 (ensemble) → v2.2 (advanced features) → v2.4 (betting) → v3.0 (production) → v3.1 (alt data)

**Why v2.3 before v2.0:** Without market data, you can't properly evaluate whether player-level features actually improve edge against Vegas. CLV tracking is the prerequisite for knowing if any improvement is real.

---

## Reality Check

Even with all of the above:

- **Vegas closing lines are the best prediction model in the world.** They incorporate all public information plus private information from sharp bettors who *are* the market.
- The closing line has a median error of ~10 points for spreads — beating it by even 0.5 points consistently is worth millions.
- **The realistic path to an edge is narrow:** find specific niches (early-season, weather, specific line ranges), beat the opening line (less efficient than closing), focus on totals (historically less efficient), and use player-level information the market prices slowly.
- **Statistical significance requires patience:** ~1,000 bets at 53%+ to confirm edge. That's 3+ full NFL seasons of every-game betting, or 6+ seasons of selective betting.
- **Shadow bet for 1-2 seasons minimum** before risking real money. Backtests are subject to look-ahead bias; only forward testing proves an edge.

---
*Created: 2026-03-21 after Phase 25 completion*
