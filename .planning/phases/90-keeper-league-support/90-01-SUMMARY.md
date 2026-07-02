# 90-01 Summary

Shipped (commit 6daca4f): keeper-league support — `sleeper_http.get_league_rosters`,
`SleeperAdapter.get_keepers`, `LiveDraftEngine.preload_keepers` (mark all
league-rostered players off the board → recs only from the true draftable pool; your
keepers load as your roster, correct `remaining_needs`). `src/roster_optimizer.py`
(`optimal_lineup` + `drop_candidates`). CLI `draft_live.py --league-id` + `--roster-report`.
9 offline tests.
Requirements: KEEP-01, KEEP-02. ✓
