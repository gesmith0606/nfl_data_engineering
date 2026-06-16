---
phase: 91
plan: 91-01
title: Custom league scoring + exact roster slots
wave: 1
depends_on: [90-01]
requirements: [SCORE-01, SCORE-02]
files_modified:
  - src/league_scoring.py
  - src/roster_optimizer.py
  - src/sleeper_http.py
  - scripts/draft_live.py
  - tests/test_league_scoring.py
autonomous: true
---

# Plan 91-01: League-Aware Scoring & Roster Slots

## Objective
Advise under the league's REAL rules. Surfaced by a live dry-run against a dynasty
league (full PPR + TE premium + 6-pt pass TD + superflex) that the generic
half-PPR/standard-slot defaults mis-ranked.

## Tasks
- **91-01-1 (SCORE-01):** `src/league_scoring.py` — `score_with_settings` re-scores
  projections from per-stat columns under a league's `scoring_settings`;
  `unmodeled_offense_keys` discloses what isn't modeled.
- **91-01-2 (SCORE-02):** `roster_optimizer` accepts exact Sleeper `roster_positions`
  (FLEX/SUPER_FLEX/WRRB_FLEX/REC_FLEX eligibility).
- **91-01-3:** `sleeper_http.get_league`; `draft_live.py` auto-applies league scoring +
  slots when `--league-id` set; `--roster-report` works with no active draft.
- **91-01-4 (tdd):** `tests/test_league_scoring.py` (custom scoring, TE premium,
  roster_positions lineup).

## must_haves
1. Projections re-scored under the league's custom rules; gaps disclosed. (SCORE-01)
2. Optimal lineup fills the league's exact starting slots. (SCORE-02)
3. Live-verified against the user's real dynasty league.
