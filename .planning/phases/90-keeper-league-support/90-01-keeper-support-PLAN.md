---
phase: 90
plan: 90-01
title: Keeper-aware draft board + roster/drop optimizer
wave: 1
depends_on: [86-01, 87-01]
requirements: [KEEP-01, KEEP-02]
files_modified:
  - src/sleeper_http.py
  - src/draft_adapter.py
  - src/live_draft_engine.py
  - src/roster_optimizer.py
  - scripts/draft_live.py
  - tests/test_roster_optimizer.py
  - tests/test_sleeper_keepers.py
  - tests/fixtures/sleeper_draft/league_rosters.json
autonomous: true
---

# Plan 90-01: Keeper League Support

## Objective
Make the live co-pilot correct for keeper/rookie drafts and help the operator
manage their roster (who to drop to roster a rookie).

## Tasks
- **90-01-1 (KEEP-01):** `sleeper_http.get_league_rosters`; `SleeperAdapter.get_keepers`
  (kept players → PickEvents, `mine` subset); `LiveDraftEngine.preload_keepers` marks
  all kept players off the board (mine `by_me`) + `my_full_roster()`; `draft_live.py
  --league-id` preloads keepers once after the first poll.
- **90-01-2 (KEEP-02):** `src/roster_optimizer.py` — `optimal_lineup` (fill base slots
  + FLEX/SFLEX greedily by points) and `drop_candidates` (rank weakest bench, flag
  streamable K/DST + positional redundancy); `draft_live.py --roster-report`.
- **90-01-3 (tdd):** offline tests for both (fixtures + monkeypatched rosters).

## must_haves
1. Kept players across the league are removed from the recommendation pool; user's
   keepers load as their roster (`remaining_needs` correct). (KEEP-01)
2. Optimal starting lineup + ranked drop candidates from keepers + drafted. (KEEP-02)
3. Offline tests pass; no network in CI.
