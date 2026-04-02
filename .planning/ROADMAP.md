# Roadmap: NFL Data Engineering Platform

## Milestones

- v1.0 Bronze Expansion -- Phases 1-7 (shipped 2026-03-08)
- v1.1 Bronze Backfill -- Phases 8-14 (shipped 2026-03-13)
- v1.2 Silver Expansion -- Phases 15-19 (shipped 2026-03-15)
- v1.3 Prediction Data Foundation -- Phases 20-23 (shipped 2026-03-19)
- v1.4 ML Game Prediction -- Phases 24-27 (shipped 2026-03-22)
- v2.0 Prediction Model Improvement -- Phases 28-31 (shipped 2026-03-27)
- v2.1 Market Data -- Phases 32-34 (shipped 2026-03-28)
- v2.2 Full Odds + Holdout Reset -- Phases 35-38 (shipped 2026-03-29)
- v3.0 Player Fantasy Prediction System -- Phases 39-48 (shipped 2026-04-01)
- **v3.1 Graph-Enhanced Fantasy Projections -- Phases 49-52 (current)**

---

## v3.1 Graph-Enhanced Fantasy Projections

**Goal:** Use Neo4j graph features to beat the heuristic baseline for WR/RB/TE fantasy projections, plus add kicker support.

**Note:** Much of the infrastructure was built in v3.0 phases 43-48. This milestone focuses on populating the features with real data, running the ship/skip gate, and finalizing kicker projections.

### Phase 49: PBP Participation Data Ingestion
**Goal:** Ingest PBP participation data (22 player IDs per snap) for all training seasons, unlocking 18/22 graph features.
**Requirements:** INGEST-01, INGEST-02, INGEST-03
**Dependencies:** None (ingestion already running)
**Success criteria:**
1. `data/bronze/pbp_participation/` contains parquet files for 2016-2025
2. Each season file has game_id, play_id, offense_players, defense_players columns
3. Re-running ingestion does not create duplicates
4. Ingestion script handles nfl-data-py API failures gracefully

### Phase 50: Populate Graph Features from Participation Data
**Goal:** Compute all WR/RB/TE graph features using the participation data and cache as Silver parquet.
**Requirements:** WR-01, WR-02, WR-03, WR-04, RB-01, RB-02, RB-03, RB-04, RB-05, TE-01, TE-02, TE-03, TE-04, INFRA-02, INFRA-03
**Dependencies:** Phase 49 (participation data must exist)
**Success criteria:**
1. WR features (4) populated with non-null values for 60%+ of WR player-weeks
2. RB features (5+4 scheme) populated with non-null values for 60%+ of RB player-weeks
3. TE features (4) populated with non-null values for 60%+ of TE player-weeks
4. All features respect temporal lag (shift(1), no future data)
5. Features cached in `data/silver/graph_features/` per season

### Phase 51: Ship/Skip Gate — Graph-Enhanced Models
**Goal:** Retrain per-position player models with all 22 graph features and determine which positions beat the heuristic baseline.
**Requirements:** MODEL-01, MODEL-02, MODEL-03, MODEL-04, INFRA-01
**Dependencies:** Phase 50 (features must be populated)
**Success criteria:**
1. Walk-forward CV retraining completed for all 4 positions (QB/RB/WR/TE)
2. SHAP feature selection identifies which graph features survive
3. Per-position holdout MAE compared to baseline (QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77)
4. ML projection router updated for any position that ships
5. At least one position (target: WR) shows statistically significant improvement
6. 841+ tests passing after any routing changes

### Phase 52: Kicker Backtesting + Final Validation
**Goal:** Validate kicker projections against historical data and run full-system backtest.
**Requirements:** KICK-01, KICK-02, KICK-03, INFRA-01
**Dependencies:** Phase 51 (final model state must be known)
**Success criteria:**
1. Kicker projections backtested against 2022-2024 actuals
2. Kicker MAE reported (baseline to be established)
3. Full-system backtest run with final v3.1 model configuration
4. Overall fantasy MAE reported (target: < 4.91)
5. All tests passing, docs updated

---

## Requirement Coverage

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| INGEST-01 | 49 | PBP participation 2020-2025 |
| INGEST-02 | 49 | Extended to 2016-2019 |
| INGEST-03 | 49 | Idempotent ingestion |
| WR-01 | 50 | WR-defense EPA features |
| WR-02 | 50 | WR-CB co-occurrence |
| WR-03 | 50 | Similar-WR traversal |
| WR-04 | 50 | WR Silver cache |
| RB-01 | 50 | OL starter count |
| RB-02 | 50 | OL continuity score |
| RB-03 | 50 | Scheme matchup |
| RB-04 | 50 | Gap-specific YPC |
| RB-05 | 50 | RB Silver cache |
| TE-01 | 50 | TE-LB/Safety coverage |
| TE-02 | 50 | Def TE pts allowed |
| TE-03 | 50 | RZ target share |
| TE-04 | 50 | TE Silver cache |
| MODEL-01 | 51 | Ship/skip gate rerun |
| MODEL-02 | 51 | Per-position MAE |
| MODEL-03 | 51 | Router update |
| MODEL-04 | 51 | Beat heuristic |
| KICK-01 | 52 | Kicker in weekly output |
| KICK-02 | 52 | Kicker in draft optimizer |
| KICK-03 | 52 | Kicker backtest |
| INFRA-01 | all | Tests passing |
| INFRA-02 | 50 | Neo4j optional |
| INFRA-03 | 50 | Silver caching |

**Coverage: 26/26 requirements mapped (100%)**
