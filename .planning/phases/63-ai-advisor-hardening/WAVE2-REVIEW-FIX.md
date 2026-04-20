# Wave 2 Fix Verification — commit 090c0e9

**Reviewer**: git-code-reviewer (Sonnet)
**Date**: 2026-04-18
**Commit**: `090c0e9` — "fix(review): address Wave 2 review findings H1/H2/H3 + M1/M3"

---

## Verdict: All five fixes correct. No regressions.

### H1 — Path anchor (`projection_service.py`)

Fixed correctly. `_PROJECT_ROOT = Path(__file__).resolve().parents[3]` anchors off the service
file itself (`services → api → web → project`), which is stable regardless of `GOLD_PROJECTIONS_DIR`
changes or Docker WORKDIR. The old `IndexError` guard is gone; `ValueError` from `relative_to` is
the only expected exception, and it is caught.

### H2 — Stat race condition (`projection_service.py`)

Fixed correctly in two places:

1. `_latest_parquet` now filters out files whose `_mtime()` helper returns `-1` (OSError), then
   uses `max()` instead of the sorted-last approach. No more crash on mid-scan deletion.
2. `get_latest_week` wraps the `parquet_path.stat()` call in a try/except and `continue`s on
   OSError, preserving the "never raises" contract.

### H3 — Cache TTL (`week-context.ts`)

`CACHE_TTL_MS` raised from `60_000` to `5 * 60_000` (5 minutes). The constant and the updated
docstring are consistent. No other cache logic changed.

### M1 — `_scalar` isinstance check (`players.py`)

`isinstance(val, _pd.Series)` replaces the `hasattr / not hasattr` heuristic. The `import pandas
as _pd` is scoped inside `_scalar` to avoid a module-level import side effect; this is acceptable
here since the function is called infrequently. Fix is precise.

### M3 — Silent source reset (`external_rankings_service.py`)

`raise ValueError(...)` replaces the silent `source = "sleeper"` fallback in both
`get_external_rankings` and `compare_rankings`. Error message includes the valid source list.
Router-level validation remains the primary gate; the service-level raise is now a hard backstop
for direct callers. Correct.

---

## Deferred (unchanged, as agreed)

- **M2** — truncation loop in `usePersistentChat` (converges, low impact)
- **M4** — Docker image growth from sentiment data (Phase 65/66 work)
- **M5** — `/api/version` metadata exposure (debug-only, acceptable)
