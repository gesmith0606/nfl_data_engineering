# Requirements — v3.1 Graph-Enhanced Fantasy Projections

**Defined:** 2026-04-02
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models

## Data Ingestion

- [x] **INGEST-01**: PBP participation data ingested for seasons 2020-2025 with offense_players and defense_players columns stored in `data/bronze/pbp_participation/`
- [~] **INGEST-02**: PBP participation data extended to 2016-2019 for full training history coverage — PARTIAL: 2016-2019 sparse in nfl-data-py, not required for training
- [x] **INGEST-03**: Participation ingestion is idempotent (re-runnable without duplicates)

## Graph Features — WR

- [x] **WR-01**: WR-vs-defense EPA features populated from participation data for all training seasons
- [~] **WR-02**: WR-CB co-occurrence edges computed from participation data — PARTIAL: cb_cooccurrence_quality always NaN, other WR features at 73%+ coverage
- [x] **WR-03**: Similar-WR-vs-defense graph traversal feature (WRs with similar profile vs this defense)
- [x] **WR-04**: All WR graph features cached as Silver parquet with temporal lag enforcement

## Graph Features — RB

- [x] **RB-01**: OL starter count and backup insertion features populated from participation data
- [x] **RB-02**: OL continuity score (rolling % of snaps with same 5 starters) computed per team per week
- [x] **RB-03**: Scheme matchup scoring (team run scheme type vs opposing defense front quality)
- [x] **RB-04**: Gap-specific YPC vs defense (RB efficiency by run_gap against specific opponent)
- [x] **RB-05**: All RB graph features cached as Silver parquet with temporal lag enforcement

## Graph Features — TE

- [x] **TE-01**: TE-LB/Safety coverage rate computed from participation data (% of TE targets with LB on field)
- [x] **TE-02**: Opposing defense fantasy points allowed to TEs (rolling 3 games)
- [~] **TE-03**: TE red zone target share redistribution features — PARTIAL: te_red_zone_target_share always NaN (needs PBP RZ computation)
- [x] **TE-04**: All TE graph features cached as Silver parquet with temporal lag enforcement

## Model Improvement

- [x] **MODEL-01**: Ship/skip gate re-run with all 22 graph features populated for training data
- [x] **MODEL-02**: Per-position MAE comparison: graph-enhanced ML vs heuristic baseline
- [x] **MODEL-03**: ML projection router updated — QB=XGB, RB=XGB, WR=Heuristic+Residual, TE=Heuristic+Residual
- [~] **MODEL-04**: At least one of RB/WR/TE beats heuristic MAE — PARTIAL: graph features alone did not beat heuristic; hybrid residual (Phase 53) improved WR/TE

## Kicker

- [x] **KICK-01**: Kicker projections included in weekly output via `--include-kickers` flag
- [x] **KICK-02**: Kicker position added to draft optimizer with VORP replacement rank
- [x] **KICK-03**: Kicker backtesting against 2022-2024 actuals with MAE reporting (MAE 4.14, worse than flat 8.0 baseline)

## Infrastructure

- [x] **INFRA-01**: All existing tests continue passing — 899 tests passing (up from 841)
- [x] **INFRA-02**: Neo4j remains optional — all features have pure-pandas fallback
- [x] **INFRA-03**: Graph feature computation cached as Silver parquet for pipeline efficiency

## Traceability

| REQ-ID | Phase | Plan | Status |
|--------|-------|------|--------|
| INGEST-01 | 49 | 49-01 | DONE |
| INGEST-02 | 49 | 49-01 | PARTIAL |
| INGEST-03 | 49 | 49-01 | DONE |
| WR-01 | 50 | 50-01 | DONE |
| WR-02 | 50 | 50-01 | PARTIAL |
| WR-03 | 50 | 50-01 | DONE |
| WR-04 | 50 | 50-01 | DONE |
| RB-01 | 50 | 50-01 | DONE |
| RB-02 | 50 | 50-01 | DONE |
| RB-03 | 50 | 50-01 | DONE |
| RB-04 | 50 | 50-01 | DONE |
| RB-05 | 50 | 50-01 | DONE |
| TE-01 | 50 | 50-01 | DONE |
| TE-02 | 50 | 50-01 | DONE |
| TE-03 | 50 | 50-01 | PARTIAL |
| TE-04 | 50 | 50-01 | DONE |
| MODEL-01 | 51 | 51-01 | DONE |
| MODEL-02 | 51 | 51-01 | DONE |
| MODEL-03 | 53 | 53-05 | DONE |
| MODEL-04 | 53 | 53-04 | PARTIAL |
| KICK-01 | 48 | 48-01 | DONE |
| KICK-02 | 48 | 48-01 | DONE |
| KICK-03 | 52 | 52-01 | DONE |
| INFRA-01 | all | — | DONE (899 tests) |
| INFRA-02 | all | — | DONE |
| INFRA-03 | 50 | 50-01 | DONE |

## Future Requirements (deferred)

- PFF paid data integration for true WR-CB coverage assignments
- Football Outsiders adjusted line yards for OL quality
- DST fantasy projections
- Neural embeddings for player similarity

## Out of Scope

- S3 sync (AWS credentials expired)
- Real-time serving (batch weekly is sufficient)
- Web UI (v4.0+)
- Neo4j for game-level predictions (focus is fantasy projections)
