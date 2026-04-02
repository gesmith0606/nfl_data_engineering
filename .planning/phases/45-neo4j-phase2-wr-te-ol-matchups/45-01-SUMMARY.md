# Phase 45-01: WR/TE/OL Matchup Features - Summary

**Completed:** 2026-04-01
**Status:** Complete

## Delivered

### New Modules
- `src/graph_participation.py` — Parse 22-player-per-snap participation data, identify CBs, OL by position
- `src/graph_wr_matchup.py` — WR-vs-defense edges (TARGETED_AGAINST + ON_FIELD_WITH co-occurrence)
- `src/graph_ol_lineup.py` — OL lineup tracking with backup detection, RB rushing context
- `src/graph_te_matchup.py` — TE coverage mismatch (LB/Safety) + red zone target share edges

### Modified
- `src/config.py` — defenders_in_box (141 PBP cols) + PBP_PARTICIPATION_COLUMNS
- `scripts/bronze_ingestion_simple.py` — --include-participation flag
- `src/graph_feature_extraction.py` — WR matchup + OL/RB + TE features with pandas fallback
- `src/player_feature_engineering.py` — steps 12 (WR+OL) and 13 (TE) feature joins

### 18 Total Graph Features
| Position | Features |
|----------|----------|
| WR (4) | def_pass_epa_allowed, wr_epa_vs_defense_history, cb_cooccurrence_quality, similar_wr_vs_defense |
| RB (5) | ol_starters_active, ol_backup_insertions, rb_ypc_with_full_ol, rb_ypc_delta_backup_ol, ol_continuity_score |
| TE (4) | te_lb_coverage_rate, te_vs_defense_epa_history, te_red_zone_target_share, def_te_fantasy_pts_allowed |
| All (4) | injury_cascade_target_boost, injury_cascade_carry_boost, teammate_injured_starter, historical_absorption_rate |

### Tests
- 769 passing (698 → 739 from WR/OL, → 769 from TE)
- 71 new tests across test_graph_phase2.py and test_graph_te_matchup.py
