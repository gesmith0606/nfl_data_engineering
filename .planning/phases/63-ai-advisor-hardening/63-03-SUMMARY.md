---
phase: 63-ai-advisor-hardening
plan: 03
subsystem: advisor-tools-external-rankings
tags: [advisor, rankings, cache, fallback, advr-03, live-data]

requires:
  - file: "web/api/services/external_rankings_service.py"
    provides: "Pre-63-03 skeleton: Sleeper/FantasyPros/ESPN fetcher with in-memory cache"
provides:
  - "Cache-first envelope resolution: live → cache → stale marker, never raises"
  - "data/external/sleeper_rankings.json: on-disk fallback for cold-start deploys"
  - "/api/rankings/external + /api/rankings/compare never return 502 — always a structured envelope with stale, cache_age_hours, last_updated"
affects:
  - "compareExternalRankings advisor tool now returns live data with graceful degradation"
  - "ADVR-03 requirement satisfied"

tech-stack:
  added: []
  patterns:
    - "Split concerns: _fetch_live / _load_cache / _save_cache / _resolve_source — testable in isolation"
    - "Canonical envelope: {source, fetched_at, players} with legacy bare-list tolerance"
    - "Stale-propagation: _resolve_consensus escalates any_stale when any sub-source served from cache"
    - "Live-first + cache fallback: every resolve attempts live so degradations surface; cache only covers for the failure"

key-files:
  created:
    - "tests/web/test_external_rankings_cache_fallback.py (7 contract tests)"
    - "data/external/sleeper_rankings.json (cold-start cache, committed per .gitignore allowlist)"
  modified:
    - "web/api/services/external_rankings_service.py (cache-first resolve, never raises)"
    - "web/api/routers/rankings.py (no more 502s from external failures)"
    - ".gitignore (added data/external/*.json allowlist)"
---

# Plan 63-03 — Live compareExternalRankings with cache-first fallback

## What shipped

1. **`_fetch_live()`** returns `None` on any failure (never raises). Isolates upstream flakiness.
2. **`_load_cache()`** tolerates both the canonical `{source, fetched_at, players}` envelope and legacy bare-list format (backward compat for pre-63-03 caches).
3. **`_save_cache()`** writes the canonical envelope with `fetched_at` timestamp.
4. **`_resolve_source()`** always tries live first (so external degradations surface in logs), then falls back to cached JSON with `stale=True` and `cache_age_hours`.
5. **`_resolve_consensus()`** averages `external_rank` across sources that returned data; escalates `any_stale` when any sub-source served from cache.
6. **`compare_rankings()`** always returns a full envelope with `stale`, `cache_age_hours`, `last_updated` — no more 502 paths reaching the router.
7. **Routers** (`/api/rankings/external`, `/api/rankings/compare`) no longer raise 502 on external failures — caller always gets a structured envelope.
8. **7 contract tests** in `tests/web/test_external_rankings_cache_fallback.py` pinning: happy-path, blocked-with-cache, blocked-without-cache, rank_diff math, position filter, consensus averaging, envelope invariants.
9. **`data/external/sleeper_rankings.json`** (32 KB) committed via `.gitignore` allowlist so cold-start Railway deploys have a fallback cache.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 (RED)   | `e895394` | Cache-first fallback contract tests |
| 1 (GREEN) | `c372d77` | Service + router rewrite |
| 2 (docs)  | (this commit) | SUMMARY + commit the Sleeper cache JSON |

## Requirements coverage

- **ADVR-03** ✓ — compareExternalRankings returns live data from Sleeper/FantasyPros/ESPN with graceful degradation to cached envelopes when upstream is blocked/down.

## Known gap (noted in c4c93eb)

`tests/web/test_external_rankings.py` has 6 failing tests that predate this plan — they encode an older service envelope format. Out of scope here. Can be addressed in a follow-up cleanup plan.

## Unblocks

- **63-06 (live re-audit)**: ADVR-03 is the 11th of 12 advisor tools; combined with ADVR-02 (63-04) and ADVR-04 (63-05), the re-audit gate can now target a likely-passing live stack.
