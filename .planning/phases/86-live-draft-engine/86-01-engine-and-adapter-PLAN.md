---
phase: 86
plan: 86-01
title: DraftAdapter protocol + SleeperAdapter + LiveDraftEngine
wave: 1
depends_on: [85-01, 85-02]
requirements: [ENG-01, ENG-02, ENG-03, ENG-04, ENG-05]
files_modified:
  - src/draft_adapter.py
  - src/live_draft_engine.py
  - tests/test_live_draft_engine.py
autonomous: true
---

# Plan 86-01: Live Draft Engine + Adapter

## Objective
Platform-agnostic live draft engine. Define a `DraftAdapter` protocol, implement
`SleeperAdapter` over Phase 85, and a `LiveDraftEngine` that diffs picks, syncs the
board + every roster, computes snake/linear slot + on-the-clock + the user's next pick,
surfaces recommendations on the user's turn, and detects key moments + pick grades. The
engine touches ONLY the adapter interface (ENG-05 / D-08) so Yahoo/ESPN slot in later.

## Tasks
- **86-01-1 (ENG-05):** `src/draft_adapter.py` — `DraftAdapter` Protocol
  (`platform`, `resolve_draft`, `load_state`, `map_picks`) + `SleeperAdapter` wrapping
  `sleeper_draft` + `sleeper_player_map`.
- **86-01-2 (ENG-01/02):** `LiveDraftEngine.update(state)` — diff new picks by `pick_no`,
  mark board availability, reconstruct rosters by slot, snake/linear slot math,
  on-the-clock + user-slot + next-user-pick detection.
- **86-01-3 (ENG-03/04):** `recommendations()` via `DraftAdvisor`; `key_moments()` for
  new picks (value drop, positional run, reach/steal vs ADP, pick grade).
- **86-01-4 (tdd):** Replay the Phase 85 fixture draft pick-by-pick; assert rosters,
  on-the-clock slot, recommendations on the user's turn, and key-moment flags.

## must_haves
1. Engine consumes only `DraftAdapter` (no Sleeper import in engine core). (ENG-05)
2. Idempotent diff — re-feeding the same state emits no duplicate picks. (ENG-01)
3. Correct rosters + on-the-clock + user next pick on a snake fixture. (ENG-02)
4. Recommendations on the user's turn + key-moment flags fire. (ENG-03, ENG-04)
