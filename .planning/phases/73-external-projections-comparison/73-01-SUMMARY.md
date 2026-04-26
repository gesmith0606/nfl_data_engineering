---
plan: 73-01-bronze-ingesters
phase: 73-external-projections-comparison
status: complete
completed: 2026-04-25
requirements: [EXTP-01]
commits: 4
---

# Plan 73-01: Bronze Ingesters — SUMMARY

## What Was Built

3 Bronze ingesters for external projection sources (ESPN, Sleeper, Yahoo via FantasyPros proxy) plus the shared `src/sleeper_http.py` helper that owns all Sleeper public-API HTTP traffic per CONTEXT D-01.

### Code Changes

| File | Change |
|------|--------|
| `src/sleeper_http.py` | NEW — single source of truth for Sleeper public-API GETs. `fetch_sleeper_json(url, timeout=15)` returns parsed JSON or `{}` on any error (D-06 fail-open). Uses stdlib `urllib.request` (no third-party deps). |
| `scripts/ingest_sentiment_sleeper.py` | Refactored to import `fetch_sleeper_json` from the new shared helper (D-01 compliance). |
| `scripts/ingest_external_projections_espn.py` | NEW — fetches ESPN public fantasy projections, writes Bronze Parquet. |
| `scripts/ingest_external_projections_sleeper.py` | NEW — uses `fetch_sleeper_json` (no direct `import requests`). Maps `pts_half_ppr`/`pts_ppr`/`pts_std` based on scoring format. |
| `scripts/ingest_external_projections_yahoo.py` | NEW — Yahoo via FantasyPros consensus proxy. Source label `yahoo_proxy_fp` makes provenance transparent. Parses position-specific FP HTML pages (qb/rb/wr/te/k). |
| `src/config.py` | Added `sleeper_projections_url` to SENTIMENT_CONFIG. |

### Tests

| File | Change |
|------|--------|
| `tests/external_projections/test_ingest_espn.py` | NEW — fixture-driven tests for ESPN ingester. |
| `tests/external_projections/test_ingest_sleeper.py` | NEW — 3 tests including the **D-01 structural test** that greps for `import requests` and asserts absence (LOCKED contract enforced at test layer). |
| `tests/external_projections/test_ingest_yahoo.py` | NEW — 2 tests covering the FP HTML parser + fail-open empty fixture. |
| `tests/fixtures/external_projections/{espn,sleeper,fantasypros}_sample.json` | NEW — recorded sample payloads for hermetic tests. |

## Test Results

- `tests/external_projections/test_ingest_espn.py`: passing (Task 1 commit)
- `tests/external_projections/test_ingest_sleeper.py`: 3/3 passing
- `tests/external_projections/test_ingest_yahoo.py`: 2/2 passing
- D-01 enforcement: structural grep test passes — Sleeper ingester contains no `import requests` and explicitly imports `from src.sleeper_http import fetch_sleeper_json`.

## Bronze Layout (after running all 3 ingesters)

```
data/bronze/external_projections/
├── espn/season=2025/week=01/espn_20260425_HHMMSS.parquet
├── sleeper/season=2025/week=01/sleeper_20260425_HHMMSS.parquet
└── yahoo_proxy_fp/season=2025/week=01/yahoo_proxy_fp_20260425_HHMMSS.parquet
```

All 3 share the canonical Bronze schema:
`{player_name, player_id, team, position, projected_points, scoring_format, source, season, week, projected_at, raw_payload}`

## Commits

- `f30bcae` — `feat(73-01): ESPN Bronze projections ingester + fixture-driven tests`
- `(2nd commit)` — `feat(73-01): Sleeper Bronze projections ingester + sleeper_http shared helper (D-01)`
- `(3rd commit)` — `feat(73-01): Yahoo (FantasyPros consensus proxy) Bronze projections ingester`
- `(this commit)` — `docs(73-01): SUMMARY for Bronze ingesters wave`

## Self-Check: PASSED

- [x] 3 Bronze ingester scripts shipped (espn, sleeper, yahoo_proxy_fp)
- [x] `src/sleeper_http.py` shared helper extracted; existing sentiment ingester refactored to use it
- [x] D-01 LOCKED: Sleeper ingester contains no direct `import requests` (verified by structural test)
- [x] D-06 fail-open verified for all 3 ingesters (empty payload → no Parquet, exit 0)
- [x] All ingesters write Parquet at canonical season=YYYY/week=WW path
- [x] Source label `yahoo_proxy_fp` preserves provenance per CONTEXT D-03
- [x] Fixture-driven tests deterministic (no live HTTP in CI)

## Handoff to Plan 73-02

Plan 73-02 must:
1. Implement `SilverConsolidator` to merge 4 sources (ours + 3 external) into long-format Silver Parquet.
2. Use `PlayerNameResolver` for cross-source player_id resolution (Yahoo proxy has player_id=None — needs name→id).
3. Write to `data/silver/external_projections/season=YYYY/week=WW/`.
