---
phase: 73-external-projections-comparison
status: complete (code) / cron-pending-first-run
shipped: 2026-04-25
requirements: [EXTP-01, EXTP-02, EXTP-03, EXTP-04, EXTP-05]
plans_complete: 5
---

# Phase 73: External Projections Comparison — SUMMARY

## Goal Achieved

ESPN, Sleeper, and Yahoo (via FantasyPros consensus proxy) projections now ship side-by-side with our Gold projections via `/api/projections/comparison` and a new comparison section on the projections page. EXTP-01..05 all satisfied at the code level; EXTP-05 cron will validate on first scheduled run.

## What Shipped

| Plan | Wave | Deliverable |
|------|------|-------------|
| 73-01 | 1 | 3 Bronze ingesters (ESPN, Sleeper, Yahoo/FP) + `src/sleeper_http.py` shared helper. D-01 enforced via structural test. |
| 73-02 | 2 | `SilverConsolidator` + CLI merges 4 sources to long-format Silver Parquet. D-06 fail-open. |
| 73-03 | 3 | `/api/projections/comparison` endpoint with 4-source pivot, delta_vs_ours, source_labels (Yahoo provenance), data_as_of (per-source freshness). |
| 73-04 | 4 | Frontend `ProjectionComparisonTable` + comparison section on `/dashboard/projections`. EmptyState fallback. tsc clean. |
| 73-05 | 5 | `.github/workflows/weekly-external-projections.yml` — Tue 14:00 UTC + Sun 12:00 UTC cron with continue-on-error matrix + consolidation job. |

## Test Counts

- 3 Sleeper ingester tests + 2 Yahoo + (existing ESPN tests) = ingester layer
- 11 SilverConsolidator tests
- 5 comparison endpoint tests
- TypeScript check (tsc --noEmit): clean

Total new tests for Phase 73: ~22

## Requirements Coverage

| Req | Status | Evidence |
|-----|--------|----------|
| EXTP-01 (3 Bronze ingesters) | ✓ | scripts/ingest_external_projections_*.py + ingester tests |
| EXTP-02 (Silver merged 4-source) | ✓ | src/external_projections.py SilverConsolidator + 11 tests |
| EXTP-03 (API endpoint) | ✓ | /api/projections/comparison + 5 endpoint tests |
| EXTP-04 (Frontend comparison table) | ✓ | ProjectionComparisonTable on /dashboard/projections |
| EXTP-05 (Cron + freshness) | ⏳ pending first run | weekly-external-projections.yml committed; live verification on first scheduled run |

## Key Architectural Decisions Honored (per CONTEXT)

- **D-01 (LOCKED)**: Sleeper ingester uses `src/sleeper_http.py` exclusively — no direct `import requests`. Structural test enforces.
- **D-03 (LOCKED)**: Source label `yahoo_proxy_fp` preserved in Bronze; renamed to `yahoo` at API layer; provenance exposed via `source_labels.yahoo`.
- **D-04 (LOCKED)**: Long-format Silver schema (`{player_id, name, position, team, source, scoring_format, projected_points, projected_at}`); API pivots to wide on read.
- **D-06 (LOCKED, fail-open)**: Every layer — ingesters exit 0 on error; SilverConsolidator returns empty DF; API returns empty `rows` list; Frontend renders EmptyState; GHA `continue-on-error` matrix.
- **Bronze immutability**: No writes to existing Bronze paths.
- **Silver additive**: New path, no schema change to existing Silver layouts.
- **Python 3.9**: Optional/List/Dict throughout; no `|` union syntax.
- **Pydantic v2**: Additive (`ProjectionComparison` + `ProjectionComparisonRow` are new models; existing models untouched).
- **Frontend conventions**: Uses existing `FadeIn` motion primitive, design tokens, EmptyState pattern.

## Pending External Ops

1. **First cron run** validates EXTP-05 end-to-end. Once Tuesday 14:00 UTC runs, check that Bronze partitions populate for all 3 sources and Silver consolidates.
2. **Live Yahoo OAuth** — deferred to v8.0 per CONTEXT. Current `yahoo_proxy_fp` label keeps the door open for swap without API changes.

## Files Modified (key paths)

```
scripts/ingest_external_projections_espn.py        (NEW, ~200 lines)
scripts/ingest_external_projections_sleeper.py     (NEW, ~190 lines)
scripts/ingest_external_projections_yahoo.py       (NEW, ~200 lines)
scripts/silver_external_projections_transformation.py  (NEW)
scripts/ingest_sentiment_sleeper.py                (refactored to use sleeper_http)
src/sleeper_http.py                                (NEW, ~100 lines)
src/external_projections.py                        (NEW, ~210 lines)
src/config.py                                      (added sleeper_projections_url)
web/api/models/schemas.py                          (added ProjectionComparison + Row)
web/api/services/projection_service.py             (added get_comparison)
web/api/routers/projections.py                     (added /comparison endpoint)
web/frontend/src/lib/nfl/types.ts                  (ProjectionComparison TS types)
web/frontend/src/lib/nfl/api.ts                    (fetchProjectionsComparison)
web/frontend/src/features/nfl/components/projection-comparison-table.tsx  (NEW)
web/frontend/src/app/dashboard/projections/page.tsx  (new comparison section)
.github/workflows/weekly-external-projections.yml  (NEW cron)
tests/external_projections/*.py                    (NEW test suite)
tests/web/test_projections_comparison.py           (NEW)
tests/fixtures/external_projections/*.json         (NEW fixtures)
```

## Self-Check: PASSED

- [x] All 5 plans shipped
- [x] All 5 EXTP requirements covered (EXTP-05 pending first cron run)
- [x] Tests passing (ingester + Silver + API + tsc)
- [x] CONTEXT decisions honored (D-01, D-03, D-04, D-06)
- [x] Bronze immutable; Silver additive
- [x] Python 3.9 + Pydantic v2 compat
- [x] Frontend tsc clean
