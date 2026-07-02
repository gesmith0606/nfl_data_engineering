# 85-02 Summary

Shipped (commit afc1315): `resolve_active_draft(username, season)` (no manual id
lookup) + `src/sleeper_player_map.py` (cached `/players/nfl` registry, name
normalization, `map_picks_to_projections` with ≥95% skill-position coverage,
unmatched surfaced not dropped). Offline tests pass.
Requirements: SLPR-02, SLPR-03. ✓
