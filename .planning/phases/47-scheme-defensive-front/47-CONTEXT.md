# Phase 47: Scheme Classification + Defensive Front Proxy - Context

**Gathered:** 2026-04-02
**Status:** Active

<domain>
## Phase Boundary

Neo4j Phase 3: derive team run/pass scheme classifications from PBP tendencies and build defensive front quality proxies from PFR defensive stats. These features improve RB matchup modeling by capturing scheme-vs-scheme interactions (zone blocking vs. light box = RB gold; power scheme vs. elite interior DL = trouble).

All data is derivable from existing Bronze PBP and PFR defensive stats (no paid data needed).

</domain>

<requirements>
## Requirements

- R-01: Classify each team-season into run scheme type from PBP (run_gap, run_location distributions)
- R-02: Create Scheme nodes in Neo4j with scheme_type and tendency rates
- R-03: Build defensive front quality proxy from PFR defensive weekly stats (tackles, sacks, pressures, hurries)
- R-04: Create DEFENDS_RUN edges (DL/LB → opposing team) with per-game stats
- R-05: Compute scheme matchup features: how this team's run scheme historically performs vs this defensive front style
- R-06: Extract features with pure-pandas fallback
- R-07: Integrate into player feature engineering (step 14)
- R-08: Tests with temporal lag enforcement
</requirements>
