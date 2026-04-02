# Phase 44: Neo4j Phase 1 — Infrastructure + Injury Cascade - Context

**Gathered:** 2026-04-01
**Status:** Complete

<domain>
## Phase Boundary

v3.1 Neo4j foundation, starting with the highest-ROI use case: injury cascade and target redistribution. When a starter is injured, teammates absorb additional volume — this is a relational signal that a graph database captures naturally. All required data (injuries, rosters, player stats) is already available in existing Bronze layer. This phase establishes the Neo4j infrastructure and builds the first graph-derived features.

</domain>

<decisions>
## Implementation Decisions

### Infrastructure
- **D-01:** Neo4j 5 Community Edition via Docker Compose — no paid license required
- **D-02:** `src/graph_db.py` connection manager with retry logic and graceful degradation (features work without Neo4j running)
- **D-03:** Dual-path architecture: Neo4j for graph queries when available, pure-pandas fallback when not

### Graph Model
- **D-04:** Player nodes with team/position/status properties; TEAMMATES_WITH edges between same-team players; INJURED_REPLACING edges when a starter goes down
- **D-05:** Bronze ingestion script (`scripts/graph_ingestion.py`) loads rosters, injuries, and player stats into Neo4j
- **D-06:** Injury cascade computation: `identify_significant_injuries()` finds starters who miss games, `compute_redistribution()` calculates how targets/carries shift to teammates

### Feature Extraction
- **D-07:** 4 graph features: `injury_cascade_target_boost`, `injury_cascade_carry_boost`, `teammate_injured_starter`, `historical_absorption_rate`
- **D-08:** Features integrated into `player_feature_engineering.py` as step 11, with graceful fallback returning zeros when Neo4j is unavailable
- **D-09:** Pure-pandas fallback computes the same 4 features using DataFrame operations instead of Cypher queries

### Claude's Discretion
- Neo4j Docker resource limits (memory, CPU)
- Cypher query optimization and indexing strategy
- Historical absorption rate lookback window
- Pandas fallback performance optimization

</decisions>

<specifics>
## Specific Ideas

- Neo4j browser available at localhost:7474 for visual graph exploration
- Graph ingestion is idempotent — re-running merges nodes rather than duplicating
- Injury significance threshold: player must have been a starter (snap_pct > 50%) in the week before injury
- Historical absorption rate: how much of an injured player's volume a specific teammate has historically absorbed in prior injury windows

</specifics>

<canonical_refs>
## Canonical References

### Data sources (Bronze)
- `data/bronze/injuries/` — injury reports with player status (Out, IR, Questionable, etc.)
- `data/bronze/rosters/` — team rosters with depth chart position
- `data/bronze/player_weekly/` — weekly stats including targets, carries, snap counts
- `data/bronze/snap_counts/` — detailed snap count data

### Integration target
- `src/player_feature_engineering.py` — `assemble_player_features()` feature vector assembly
- `src/projection_engine.py` — downstream consumer of player features

### Prior context
- `.planning/phases/42-pipeline-integration-and-extensions/42-CONTEXT.md` — ML pipeline integration
- `.planning/phases/43-game-level-constraints/43-CONTEXT.md` — team-level constraints

</canonical_refs>

<deferred>
## Deferred Ideas

- WR-CB matchup graph (requires PFF/paid data for coverage assignments)
- OL grade nodes (requires PFF/paid data)
- PBP participation data ingestion (available free but not yet in Bronze — Phase 2)
- Target network visualization (Neo4j Bloom or custom UI)
- Graph-enhanced game predictions (after graph features prove value in fantasy backtest)

</deferred>

---

*Phase: 44-neo4j-phase1-injury-cascade*
*Context gathered: 2026-04-01*
