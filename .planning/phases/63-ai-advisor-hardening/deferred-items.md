# Phase 63 Deferred Items

Items discovered during plan execution but intentionally left for a later plan.

## 63-04 discoveries

### 6 pre-existing test failures in `tests/web/test_external_rankings.py`

**Status:** Pre-existing failures, out of scope for 63-04.
**Discovered:** 2026-04-19 during Task 2 full-suite run.
**Owner:** 63-03 (plan_checker already staged this file; service layer missing envelope keys).

Failing tests (6):
- `test_live_fetch_happy_path` — envelope missing `last_updated`, `cache_age_hours`, `stale`
- `test_live_blocked_falls_back_to_cache` — same envelope mismatch
- `test_no_cache_no_live_returns_empty_stale` — same
- `test_rank_diff_math` — TypeError in rank_diff arithmetic
- `test_consensus_averages_three_sources` — consensus aggregation absent
- `test_response_envelope_keys_present_even_on_empty` — envelope mismatch

Root cause: `web/api/services/external_rankings_service.py` returns
`{source, scoring_format, position_filter, our_projections_available, players, compared_at}`
but the 63-03 tests expect `{last_updated, cache_age_hours, stale, ...}`.

Not in 63-04 scope (ADVR-02 is about `/api/projections` top-N grounding, not
the `compareExternalRankings` tool). Leave for a 63-03 wrap-up plan.
