# Phase 45: Neo4j Phase 2 — WR/TE/OL Matchup Features - Context

**Gathered:** 2026-04-01
**Status:** Complete

<domain>
## Phase Boundary

Build graph-based matchup features for WR, TE, and RB using PBP participation data. WR-CB co-occurrence edges, TE-LB/Safety coverage mismatch, OL lineup tracking with backup detection, and red zone target networks. All features have pure-pandas fallback when Neo4j/participation data unavailable.

</domain>

<decisions>
## Implementation Decisions

### Participation Data
- **D-01:** PBP participation stored separately (`data/bronze/pbp_participation/`) to avoid breaking existing PBP consumers
- **D-02:** `--include-participation` CLI flag added to bronze_ingestion_simple.py
- **D-03:** `defenders_in_box` added to PBP_COLUMNS (now 141 columns)

### WR Matchup
- **D-04:** TARGETED_AGAINST edges (WR→Team defense) with per-game stats
- **D-05:** ON_FIELD_WITH edges (WR↔CB co-occurrence) — best available proxy for coverage without PFF
- **D-06:** 4 WR features: def_pass_epa_allowed, wr_epa_vs_defense_history, cb_cooccurrence_quality, similar_wr_vs_defense

### OL/RB
- **D-07:** BLOCKS_FOR edges (OL→Team) with starter/backup detection from depth charts
- **D-08:** RUSHES_BEHIND edges (RB→Team) with OL context
- **D-09:** 5 OL/RB features: ol_starters_active, ol_backup_insertions, rb_ypc_with_full_ol, rb_ypc_delta_backup_ol, ol_continuity_score

### TE Matchup
- **D-10:** TE_TARGETED_AGAINST edges with LB/Safety coverage breakdown
- **D-11:** RED_ZONE_ROLE edges capturing TE's share of team RZ targets
- **D-12:** 4 TE features: te_lb_coverage_rate, te_vs_defense_epa_history, te_red_zone_target_share, def_te_fantasy_pts_allowed

### Integration
- **D-13:** Features wired into player_feature_engineering.py as steps 12 (WR+OL) and 13 (TE)
- **D-14:** All features have pure-pandas fallback — Neo4j is optional
</decisions>
