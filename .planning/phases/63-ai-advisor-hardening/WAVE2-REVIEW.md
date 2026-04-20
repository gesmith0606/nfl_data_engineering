# Phase 63 Wave 2 — Automated Code Review

**Commits reviewed**: b365f16 back to 440865f (14 commits)
**Reviewer**: git-code-reviewer (Sonnet)
**Date**: 2026-04-18

---

## CRITICAL

None.

---

## HIGH

### H1 — `_project_relative` path resolution is fragile and wrong for Docker
**File**: `web/api/services/projection_service.py:53`

```python
root = GOLD_PROJECTIONS_DIR.resolve().parents[1].parent  # .../<project>/
```

`GOLD_PROJECTIONS_DIR` resolves to `<project>/data/gold/projections`, whose `.parents` are:
- `[0]` = `<project>/data/gold`
- `[1]` = `<project>/data`
- `.parent` of that = `<project>`

So the math is correct on a dev machine. But inside the Docker container the WORKDIR is `/app`, and `data/gold/projections` resolves to `/app/data/gold/projections`. The `.parents[1].parent` chain will yield `/app`, not the project root, so `source_path` values will look like `data/gold/projections/...` (relative to `/app`) — not wrong, but the comment says "project root" and the IndexError guard is misleading. More importantly, if `GOLD_PROJECTIONS_DIR` is ever changed to a deeper or shallower path, this hard-coded `[1].parent` silently produces a garbage path. Use `Path(__file__).resolve().parents[N]` for a stable anchor instead.

**Risk**: `source_path` field is informational only; no production failure, but misleading in Railway logs.

### H2 — `get_latest_week` reads `best_mtime` only from the first matched week, not the highest
**File**: `web/api/services/projection_service.py:106-137`

```python
if best_week is None or week_num > best_week:
    best_week = week_num
    best_path = parquet_path
    best_mtime = parquet_path.stat().st_mtime
```

`best_mtime` is updated only when `week_num > best_week`, which is correct. However, `best_mtime` is initialised to `-1.0` and the `stat()` call is inside the loop without error handling. If the parquet file is deleted between the `glob` and the `stat()` call (race condition), the entire function raises `FileNotFoundError` rather than returning the graceful null envelope. Wrap `parquet_path.stat()` in a try/except.

**Risk**: Low probability but breaks the "never raises" contract documented in the docstring.

### H3 — `resolveDefaultWeek` cache is module-level and shared across Next.js hot-reloads
**File**: `web/frontend/src/lib/week-context.ts:31`

```ts
const cache = new Map<number, CacheEntry>();
```

In Next.js dev mode, hot-reloads do not clear module-level state, so the 60-second TTL persists across code changes. In production (Railway serverless edge), multiple isolates may each hold their own cache, causing cache misses more often than expected. This is a minor annoyance in dev and benign in prod, but the 60-second TTL may be too short to protect against tool-call fan-out from a single chat turn that fires the tool multiple times. Consider 5 minutes.

---

## MEDIUM

### M1 — `_scalar` detection heuristic is incorrect for string subclasses
**File**: `web/api/routers/players.py:37-40`

```python
if hasattr(val, "iloc") and not hasattr(val, "lower"):
```

A `pandas.Series` of dtype `object` containing strings passes `hasattr(val, "iloc")` and lacks `.lower()` — correct. But `pd.Series` of dtype `str` also lacks `.lower()`, so the guard works. The inverse case (a custom object with `.iloc` but not a Series) could slip through, but this is not a realistic concern in this codebase. The comment should note that `.lower` is used as a proxy for "this is already a plain string", which is fragile. A more robust check is `isinstance(val, pd.Series)`.

### M2 — `usePersistentChat` write debounce fires after unmount if component unmounts mid-debounce
**File**: `web/frontend/src/hooks/use-persistent-chat.ts:168-182`

The cleanup function in the debounce `useEffect` cancels the timer, which is correct. However, `latestMessagesRef.current` is captured in the closure at timer creation time but is actually read at timeout execution time (correct — it reads the ref). The implementation is sound. However, the truncation `useEffect` at line 185 calls `setMessages` inside an effect that depends on `messages`, creating an update loop for any conversation that hits `maxMessages`. Each `setMessages` triggers a re-render and a new `messages` reference, which re-fires the effect. This will loop until `messages.length <= maxMessages`, which happens immediately on the second fire — so it converges, but it fires two extra renders per message beyond the limit. Low impact at 100-message cap.

### M3 — `compare_rankings` silently resets unknown `source` to "sleeper"
**File**: `web/api/services/external_rankings_service.py:640`

```python
if source not in VALID_SOURCES:
    source = "sleeper"
```

The router already validates `source` before calling the service, so this never fires in practice. But the silent reset could mask a bug during testing if someone calls the service directly with a bad source. Better to raise `ValueError` at the service boundary and let the router's validation be the single gate.

### M4 — Sentiment data baked into Docker image grows unboundedly
**File**: `web/Dockerfile:29-32`

`COPY data/bronze/sentiment/` and `COPY data/silver/sentiment/` bake all historical sentiment files into the image. Each new week of data adds JSON files. The comment acknowledges this is a stopgap "until the daily cron writes to a persistent volume or S3." This is acceptable short-term but the image size will grow with each weekly pipeline run. Flag for Phase 65/66 when Railway persistent volumes or S3 reads are wired.

### M5 — `/api/version` endpoint leaks internal routing metadata without auth
**File**: `web/api/main.py:104-117`

The `has_team_events_route` and `has_player_badges_route` fields advertise which endpoints exist, which is low-risk for a public fantasy API but inconsistent with principle of least exposure. More practically, this introspection uses `getattr(r, "path", "")` on `news.router.routes` — if `news` is ever replaced with a different router object, this silently returns `False` rather than raising. Acceptable for a deploy-verification probe, but document that this endpoint is debug-only and consider gating it behind an env var (`DEBUG=true`).

---

## INFO / PASSED

- **requests dep fix (440865f)**: Correct root-cause fix. `requests` was always needed by `external_rankings_service.py`; adding it to `serverless/requirements.txt` resolves the container startup failure cleanly.
- **Series→int bug fix (7944c0a)**: The `_scalar` + `_sf`/`_ss`/`_si` helper chain is the right approach to handle duplicate-column DataFrames. The fix correctly propagates through all field extractions.
- **cache-first fallback (c372d77)**: The live-first, cache-on-failure, empty-list-on-dual-failure chain is correct and the `stale`/`cache_age_hours` envelope gives the advisor actionable data freshness signals.
- **no-502 change**: Removing the `try/except → 502` and letting the service return an empty list is correct; 502 is appropriate for upstream dependency failures the client cannot handle, not for graceful degradation with stale data.
- **usePersistentChat (a460dc1)**: SSR-safe, quota-safe, corrupt-safe. The shared storage key between widget and advisor page is intentional and correctly documented.
- **week-context.ts**: Null-safe, error-safe, 60s cache with explicit invalidation API. `cache: 'no-store'` is correct to bypass the Next.js fetch cache for live week resolution.
- **Contract tests**: Both test files encode the correct contracts. The `pytest.skip` guards for missing Gold data are the right approach rather than conditional asserts.

---

## Summary

No blocking issues. Two HIGH findings (H1 fragile path math, H2 missing stat() guard) should be addressed before the Railway deploy goes into heavy rotation. M2 (truncation loop) and M4 (image growth) are deferred-acceptable. All other changes are solid.
