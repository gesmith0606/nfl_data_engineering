# Requirements — v3.1 Graph-Enhanced Fantasy Projections

**Defined:** 2026-04-02
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models

## Data Ingestion

- [ ] **INGEST-01**: PBP participation data ingested for seasons 2020-2025 with offense_players and defense_players columns stored in `data/bronze/pbp_participation/`
- [ ] **INGEST-02**: PBP participation data extended to 2016-2019 for full training history coverage
- [ ] **INGEST-03**: Participation ingestion is idempotent (re-runnable without duplicates)

## Graph Features — WR

- [ ] **WR-01**: WR-vs-defense EPA features populated from participation data for all training seasons
- [ ] **WR-02**: WR-CB co-occurrence edges computed from participation data (snap counts where WR targeted while CB on field)
- [ ] **WR-03**: Similar-WR-vs-defense graph traversal feature (WRs with similar profile vs this defense)
- [ ] **WR-04**: All WR graph features cached as Silver parquet with temporal lag enforcement

## Graph Features — RB

- [ ] **RB-01**: OL starter count and backup insertion features populated from participation data
- [ ] **RB-02**: OL continuity score (rolling % of snaps with same 5 starters) computed per team per week
- [ ] **RB-03**: Scheme matchup scoring (team run scheme type vs opposing defense front quality)
- [ ] **RB-04**: Gap-specific YPC vs defense (RB efficiency by run_gap against specific opponent)
- [ ] **RB-05**: All RB graph features cached as Silver parquet with temporal lag enforcement

## Graph Features — TE

- [ ] **TE-01**: TE-LB/Safety coverage rate computed from participation data (% of TE targets with LB on field)
- [ ] **TE-02**: Opposing defense fantasy points allowed to TEs (rolling 3 games)
- [ ] **TE-03**: TE red zone target share redistribution features
- [ ] **TE-04**: All TE graph features cached as Silver parquet with temporal lag enforcement

## Model Improvement

- [ ] **MODEL-01**: Ship/skip gate re-run with all 22 graph features populated for training data
- [ ] **MODEL-02**: Per-position MAE comparison: graph-enhanced ML vs heuristic baseline
- [ ] **MODEL-03**: ML projection router updated for any position that passes ship gate
- [ ] **MODEL-04**: At least one of RB/WR/TE beats heuristic MAE with graph features

## Kicker

- [ ] **KICK-01**: Kicker projections included in weekly output via `--include-kickers` flag
- [ ] **KICK-02**: Kicker position added to draft optimizer with VORP replacement rank
- [ ] **KICK-03**: Kicker backtesting against 2022-2024 actuals with MAE reporting

## Infrastructure

- [ ] **INFRA-01**: All existing 841 tests continue passing
- [ ] **INFRA-02**: Neo4j remains optional — all features have pure-pandas fallback
- [ ] **INFRA-03**: Graph feature computation cached as Silver parquet for pipeline efficiency

## Traceability

| REQ-ID | Phase | Plan | Status |
|--------|-------|------|--------|
| INGEST-01 | 49 | — | — |
| INGEST-02 | 49 | — | — |
| INGEST-03 | 49 | — | — |
| WR-01 | 50 | — | — |
| WR-02 | 50 | — | — |
| WR-03 | 50 | — | — |
| WR-04 | 50 | — | — |
| RB-01 | 50 | — | — |
| RB-02 | 50 | — | — |
| RB-03 | 50 | — | — |
| RB-04 | 50 | — | — |
| RB-05 | 50 | — | — |
| TE-01 | 50 | — | — |
| TE-02 | 50 | — | — |
| TE-03 | 50 | — | — |
| TE-04 | 50 | — | — |
| MODEL-01 | 51 | — | — |
| MODEL-02 | 51 | — | — |
| MODEL-03 | 51 | — | — |
| MODEL-04 | 51 | — | — |
| KICK-01 | 52 | — | — |
| KICK-02 | 52 | — | — |
| KICK-03 | 52 | — | — |
| INFRA-01 | all | — | — |
| INFRA-02 | all | — | — |
| INFRA-03 | 50 | — | — |

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
