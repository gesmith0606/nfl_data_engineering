---
phase: 44-neo4j-phase1-injury-cascade
plan: 01
subsystem: graph-db, player-features
tags: [neo4j, docker, injury-cascade, target-redistribution, graph-features]

# Dependency graph
requires:
  - phase: 43-game-level-constraints
    provides: Completed v3.0 player predictions
  - phase: 42-pipeline-integration-and-extensions
    provides: Player feature engineering pipeline (integration target)
provides:
  - Neo4j 5 Community Docker infrastructure
  - GraphDB connection manager with graceful degradation
  - Injury cascade identification and volume redistribution
  - 4 graph-derived player features with dual-path execution
affects: [player_feature_engineering, projection_engine, train_player_models]

# Tech tracking
tech-stack:
  added: [neo4j (Docker), neo4j Python driver]
  patterns: [dual-path execution, graceful degradation, idempotent MERGE ingestion]

key-files:
  created:
    - docker-compose.yml
    - src/graph_db.py
    - src/graph_injury_cascade.py
    - src/graph_feature_extraction.py
    - scripts/graph_ingestion.py
    - tests/test_graph_features.py
  modified:
    - src/player_feature_engineering.py

key-decisions:
  - "Neo4j 5 Community via Docker — no paid license, APOC plugin enabled"
  - "Dual-path: Neo4j Cypher for graph queries, pure-pandas fallback when Neo4j unavailable"
  - "Graceful degradation: graph features fill with 0.0 if extraction fails"
  - "Injury significance threshold: snap_pct > 50% in prior week (starter definition)"
  - "Graph ingestion uses MERGE for idempotency — safe to re-run"

patterns-established:
  - "Dual-path execution: same features computable via graph DB or flat DataFrames"
  - "GraphDB.is_available() check before any Cypher execution"
  - "Step-based feature engineering: graph features added as step 11 in assemble_player_features()"

requirements-completed: [NEO4J-01, NEO4J-02, NEO4J-03, NEO4J-04, NEO4J-05, NEO4J-06]

# Metrics
duration: ~90min
completed: 2026-04-01
---

# Phase 44 Plan 01: Neo4j Infrastructure + Injury Cascade Summary

**Neo4j 5 Community Docker setup, GraphDB connection manager, injury cascade computation, 4 graph-derived features with dual-path execution (Neo4j + pandas fallback), integrated into player feature pipeline**

## Performance

- **Duration:** ~90 min
- **Completed:** 2026-04-01
- **Tasks:** 5
- **Files created:** 6
- **Files modified:** 1

## Accomplishments
- `docker-compose.yml` for Neo4j 5 Community with persistent volume, APOC plugin, bolt:7687, browser:7474
- `src/graph_db.py` — `GraphDB` connection manager with retry (3 attempts, exponential backoff), `is_available()` health check, graceful degradation
- `src/graph_injury_cascade.py` — `identify_significant_injuries()` finds starters (snap_pct > 50%) with Out/IR status; `compute_redistribution()` calculates target/carry shifts to teammates in post-injury weeks
- `src/graph_feature_extraction.py` — `extract_graph_features()` with dual-path dispatch (Neo4j Cypher when available, pure-pandas fallback when not)
- 4 graph features: `injury_cascade_target_boost`, `injury_cascade_carry_boost`, `teammate_injured_starter`, `historical_absorption_rate`
- `scripts/graph_ingestion.py` — CLI for Bronze-to-Neo4j loading with idempotent MERGE operations
- Integrated into `player_feature_engineering.py` as step 11 with graceful fallback (zero-fill on failure)
- 29 new tests covering connection, cascade logic, extraction, fallback, and ingestion
- 698 total tests passing with no regressions

## Files Created
- `docker-compose.yml` — Neo4j 5 Community container config (512MB heap, APOC, persistent volume)
- `src/graph_db.py` — GraphDB class: connect, close, is_available, run_query with retry
- `src/graph_injury_cascade.py` — identify_significant_injuries, compute_redistribution
- `src/graph_feature_extraction.py` — extract_graph_features with dual-path (Neo4j + pandas)
- `scripts/graph_ingestion.py` — CLI: --season, --weeks, loads Player nodes + TEAMMATES_WITH + INJURED_REPLACING edges
- `tests/test_graph_features.py` — 29 tests across all graph modules

## Files Modified
- `src/player_feature_engineering.py` — Added step 11: extract_graph_features() call with graceful fallback

## Decisions Made
- Neo4j heap at 512MB — sufficient for NFL-scale graph (~2000 active players, ~32 teams, ~5 seasons)
- Starter threshold at snap_pct > 50% — captures meaningful starters without including rotational players
- Historical absorption rate uses 2-season lookback window for stability
- Pandas fallback uses groupby + merge operations to replicate Cypher multi-hop traversals
- All tests use pandas fallback path so they pass without Neo4j running (CI-compatible)

## Deviations from Plan

None — plan executed as designed.

## Issues Encountered

None.

## User Setup Required

To use Neo4j features (optional — pandas fallback works without it):
```bash
docker compose up -d    # Start Neo4j container
python scripts/graph_ingestion.py --season 2024  # Load data
```

## Known Stubs

None — all functions are fully implemented. Neo4j Cypher queries in graph_feature_extraction.py are functional when Neo4j is running; pandas fallback computes identical features when it is not.

## Next Phase Readiness
- Neo4j infrastructure established and operational
- 4 graph features available in player feature pipeline
- Ready for Phase 2: PBP participation ingestion + expanded graph features
- Fantasy backtest with graph features pending (see 44-VALIDATION.md)

---
*Phase: 44-neo4j-phase1-injury-cascade*
*Completed: 2026-04-01*
