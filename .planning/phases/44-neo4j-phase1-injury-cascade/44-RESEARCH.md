# Phase 44: Neo4j Phase 1 — Infrastructure + Injury Cascade - Research

**Researched:** 2026-04-01
**Domain:** Graph database infrastructure, injury cascade modeling, target redistribution
**Confidence:** HIGH

## Summary

Phase 44 establishes the Neo4j foundation and builds the first graph-derived features targeting injury cascade / target redistribution. A data availability audit confirms that injury cascade and OL lineup tracking work with free data (nfl-data-py), while WR-CB matchup and OL grades require PFF or paid sources (deferred). PBP participation data is available free via nflverse but not yet ingested into Bronze — that becomes Phase 2.

The highest-ROI use case is injury cascade: when a starter misses time, their targets/carries redistribute to teammates. This is inherently a graph problem (player -> team -> teammates -> volume shift). Neo4j captures this naturally with TEAMMATES_WITH and INJURED_REPLACING edges. A pure-pandas fallback ensures the system works without Neo4j running, making graph features additive rather than a hard dependency.

**Primary recommendation:** Docker-based Neo4j 5 Community with a dual-path feature extraction layer (Neo4j Cypher + pandas fallback). Four initial features focused on injury-driven volume redistribution.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Neo4j 5 Community via Docker Compose
- D-02: Connection manager with retry + graceful degradation
- D-03: Dual-path: Neo4j + pandas fallback
- D-04: Player nodes, TEAMMATES_WITH edges, INJURED_REPLACING edges
- D-07: 4 features: injury_cascade_target_boost, injury_cascade_carry_boost, teammate_injured_starter, historical_absorption_rate
- D-08: Integrated into player_feature_engineering.py step 11 with fallback
- D-09: Pandas fallback computes same 4 features without Neo4j

### Deferred Ideas (OUT OF SCOPE)
- WR-CB matchup graph (needs PFF)
- OL grade nodes (needs PFF)
- PBP participation ingestion (Phase 2)
- Graph-enhanced game predictions
</user_constraints>

## Data Availability Audit

| Use Case | Data Needed | Source | Available? | Status |
|----------|-------------|--------|------------|--------|
| Injury cascade / target redistribution | Injuries, rosters, weekly stats | nfl-data-py (free) | Yes | Phase 1 (this phase) |
| OL lineup tracking | Roster + depth chart | nfl-data-py (free) | Yes | Phase 2 candidate |
| PBP participation (WR routes, snap details) | Play-by-play participation | nflverse (free) | Available but not ingested | Phase 2 |
| WR-CB matchup assignments | Coverage data | PFF (paid) | No | Deferred |
| OL pass/run blocking grades | Player grades | PFF (paid) | No | Deferred |

## Architecture Patterns

### Pattern 1: Docker Compose for Neo4j
**What:** Single-service docker-compose.yml running Neo4j 5 Community Edition with persistent volume.
**Config:** APOC plugin enabled, bolt on 7687, browser on 7474, 512MB heap (sufficient for NFL-scale graph).

### Pattern 2: Connection Manager with Graceful Degradation
**What:** `GraphDB` class wrapping the Neo4j Python driver with configurable retry, connection pooling, and a `is_available()` check.
**Pattern:** All callers check `is_available()` before executing Cypher; if False, fall through to pandas path.

### Pattern 3: Dual-Path Feature Extraction
**What:** `graph_feature_extraction.py` exposes a single API (`extract_graph_features(player_df, season, week)`) that internally dispatches to Neo4j Cypher or pandas depending on availability.
**Why:** Development and CI/CD environments may not have Neo4j running. Features must be computable either way.

### Pattern 4: Injury Cascade Computation
**What:** Two-step process:
1. `identify_significant_injuries(injuries_df, snap_df)` — find starters (snap_pct > 50%) with Out/IR status
2. `compute_redistribution(injured_players, weekly_stats, rosters)` — calculate how targets/carries shift to teammates in weeks after injury

### Anti-Patterns to Avoid
- **Hard dependency on Neo4j:** All features must have pandas fallback. Never fail a pipeline run because Neo4j is down.
- **Complex Cypher for simple joins:** Use Cypher only when the query is genuinely graph-shaped (multi-hop traversal). Simple lookups stay in pandas.
- **Loading full PBP into Neo4j:** PBP is too large for the graph. Only structured player/team/injury data goes into nodes.

## Common Pitfalls

### Pitfall 1: Neo4j Container Not Running in CI
**What goes wrong:** Tests fail because Neo4j isn't available in GitHub Actions.
**How to avoid:** All tests use the pandas fallback path. Neo4j integration tests are marked with `@pytest.mark.neo4j` and skipped in CI.

### Pitfall 2: Stale Graph Data
**What goes wrong:** Graph contains last week's roster but this week's injury report changed.
**How to avoid:** Graph ingestion is idempotent (MERGE, not CREATE). Re-run ingestion before feature extraction.

## Sources

### Primary (HIGH confidence)
- `data/bronze/injuries/` — existing injury data in Bronze layer
- `data/bronze/rosters/` — roster data with depth chart positions
- `data/bronze/player_weekly/` — weekly player stats
- `src/player_feature_engineering.py` — integration target for graph features
- Neo4j 5 Community docs — Docker setup, Python driver, Cypher syntax

### Secondary (MEDIUM confidence)
- nflverse PBP participation data — available but not yet evaluated for Bronze ingestion complexity

## Metadata

**Confidence breakdown:**
- Infrastructure: HIGH — Neo4j Docker is well-documented, Python driver is stable
- Injury cascade logic: HIGH — straightforward volume redistribution from historical data
- Data availability: HIGH — all Bronze data sources confirmed present
- Pandas fallback: HIGH — same computation, different execution engine

**Research date:** 2026-04-01
**Valid until:** 2026-05-01
