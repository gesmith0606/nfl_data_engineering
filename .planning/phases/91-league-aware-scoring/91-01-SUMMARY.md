# 91-01 Summary

Shipped (live dry-run driven): league-accurate advice.
- `src/league_scoring.py` — `score_with_settings` re-scores projections from per-stat
  columns under a league's raw Sleeper `scoring_settings` (full PPR, TE premium,
  6-pt pass TD); `unmodeled_offense_keys` discloses gaps (first downs, 2-pt, fumbles).
- `src/roster_optimizer.py` — `optimal_lineup`/`drop_candidates` accept exact Sleeper
  `roster_positions` (FLEX/SUPER_FLEX/WRRB_FLEX/REC_FLEX), not just 3 presets.
- `scripts/draft_live.py` — auto-pulls league scoring + slots (`sleeper_http.get_league`)
  when `--league-id` set; `--roster-report` works with no active draft.
Live-verified vs MANTIS TOBOGGAN DYNASTY (gforceee). 4 tests; 86 draft tests green.
Requirements: SCORE-01, SCORE-02. ✓
