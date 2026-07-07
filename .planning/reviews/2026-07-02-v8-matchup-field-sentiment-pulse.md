# Code Review — feat/v8-live-draft-copilot
## Commits: ed1009a (matchups: field-formation + EA Madden ratings) · 4cbd68c (news: season sentiment pulse)
## Date: 2026-07-02  |  Reviewer: git-code-reviewer agent

---

## Status: WARN — No blockers. Five findings require attention before merge; three are low-effort fixes.

---

## Quality Metrics

| Axis | Result |
|------|--------|
| Security | No credential exposure; EA scraping is ToS risk (see F-04) |
| Correctness | One silent bad-output bug (F-01); one redundant double-lookup (F-02) |
| Performance | _load_recent_signal_records benchmarks at 18ms / 230 records — acceptable |
| NFL domain logic | MATCHUP_PAIRS WR3→SS pairing is semantically imprecise (F-07) |
| Architecture | Follows medallion Bronze→Silver→Gold; S3-path conventions correct |
| Test coverage | Two new test files (437 lines); all 171 backend tests pass; tsc clean |

---

## Findings

---

### F-01 — NaN stat values produce "nan" tooltip text in defensive ratings  [MEDIUM · player_rating_service.py]

**File:** `web/api/services/player_rating_service.py`

`_detail_for_row` formats raw PFR columns directly:

```python
# RUSH group
f"{int(row['prss'])} pressures"
# DB group
f"{row['rat']:.0f} rating allowed"
```

The `rat` column is null for 183 rows in the current PFR parquet (players below `_MIN_COVERAGE_TARGETS` who appear in the DB group). Python 3 formats `float('nan')` via `:.0f` as the string `"nan"`, not an exception, so the service does not crash — but the UI tooltip displays "nan rating allowed, 0 INT, nan% completions in 5 games" for those players.

`prss`, `comb`, and `int` happen to be zero-NaN in the current parquets, but older or future PFR snapshots may differ, and `int(float('nan'))` raises `ValueError`, which would produce a 500 error on roster load.

**Fix:**
```python
def _safe_int(v, default=0):
    try:
        return int(v) if pd.notna(v) else default
    except (TypeError, ValueError):
        return default

def _safe_float(v, default=0.0):
    return float(v) if pd.notna(v) else default

# In _detail_for_row (RUSH):
f"{_safe_float(row['sk']):.1f} sacks, {_safe_int(row['prss'])} pressures, "
f"{_safe_int(row['comb'])} tackles in {g} games"
# In _detail_for_row (DB):
f"{_safe_float(row['rat']):.0f} rating allowed, {_safe_int(row['int'])} INT, ..."
```

---

### F-02 — Double rating lookup per player: _add_rating_column + _row_to_player  [LOW · team_roster_service.py]

**File:** `web/api/services/team_roster_service.py`

`_add_rating_column` populates `df["_madden_rating"]` by calling `rating_lookup.rating_for()` for each player (used by `_assign_offense/defense_slot_hints` for rating-aware depth ordering). Then `_row_to_player` calls `rating_lookup.rating_for()` again to set `RosterPlayer.madden_rating`. The result is two dict lookups per player — the column value from the first pass is ignored.

The lookup is O(1) and rosters are small (50-60 players), so this is not a performance issue today. The concern is clarity: `_row_to_player` already receives the full `row` including `_madden_rating`, but doesn't use it. If the lookup logic ever becomes expensive or is guarded by side effects, the double call would be a latent bug.

**Fix:** Pass the pre-computed column value into `_row_to_player` instead of re-calling the lookup:

```python
def _row_to_player(row, slot_hint, rating_lookup=None):
    # Use the value already set by _add_rating_column when available
    madden_rating = _nan_to_none(row.get("_madden_rating"))
    rating_detail: Optional[str] = None
    if madden_rating is None and rating_lookup:
        madden_rating, rating_detail = rating_lookup.rating_for(...)
    elif rating_lookup:
        _, rating_detail = rating_lookup.rating_for(...)  # fetch detail only
    ...
```

Or, simpler: have `_add_rating_column` also store the detail string as `_rating_detail`.

---

### F-03 — lru_cache on Madden and team-map lookups has no TTL; process restart required after ingest  [MEDIUM · player_rating_service.py / news_service.py]

**Files:**
- `web/api/services/player_rating_service.py` — `load_madden_lookup()` and `load_combined_ratings()`
- `web/api/services/news_service.py` — `_player_id_team_map()`

All three are `@lru_cache` with no expiry. Running `scripts/refresh_madden_ratings.py` while the API is serving will not update the in-process cache until the process restarts. During the season, EA re-rates players weekly; the cache will serve stale ratings for the entire week between restarts.

Similarly `_player_id_team_map()` won't reflect a roster move until restart.

This is acceptable if deploy restarts the server, but it should be documented in the function docstrings so operators know what triggers a refresh. A lightweight workaround is to expose a `POST /admin/clear-cache` endpoint or use `functools.lru_cache` with a file-mtime sentinel:

```python
import os, functools
_madden_mtime: float = 0.0

def _madden_file_mtime() -> float:
    matches = sorted(glob.glob(str(_MADDEN_ROOT / "madden_ratings_*.parquet")))
    return os.path.getmtime(matches[-1]) if matches else 0.0

def load_madden_lookup():
    global _madden_mtime
    current = _madden_file_mtime()
    if current != _madden_mtime:
        load_madden_lookup.cache_clear()  # or use an explicit cache dict
        _madden_mtime = current
    return _load_madden_lookup_impl()
```

**Minimum fix:** Add a docstring note to each cached function: "Cache is process-scoped; restart the API after running `refresh_madden_ratings.py` to pick up new ratings."

---

### F-04 — EA Next.js scraping: bare dict access in fetch_positions will KeyError on schema change  [LOW · scripts/refresh_madden_ratings.py]

**File:** `scripts/refresh_madden_ratings.py`

```python
def fetch_positions(build_id: str) -> List[Tuple[str, str]]:
    ...
    positions = data["pageProps"]["ratingsFilters"]["positions"]
    return [(_slugify(p["label"]), p["id"]) for p in positions]
```

If EA restructures the JSON (which happens with each major Madden release when the Next.js app is rebuilt), this raises `KeyError: 'ratingsFilters'` with no context. `fetch_position_items` correctly uses `.get()`. This path should match:

```python
page_props = data.get("pageProps") or {}
filters = page_props.get("ratingsFilters") or {}
positions = filters.get("positions") or []
if not positions:
    raise RuntimeError(
        f"ratingsFilters.positions missing from EA JSON — "
        f"schema may have changed. Keys: {list(page_props.keys())}"
    )
```

**Secondary note:** The User-Agent specifies `Chrome/149.0.0.0`. No released Chrome version reaches 149 as of mid-2026 (latest public stable is ~127). EA's CDN may flag this as an invalid agent. Use a current version (e.g., `Chrome/127.0.0.0`).

---

### F-05 — Duplicate `from typing import Literal` import in news router  [LOW · web/api/routers/news.py]

**File:** `web/api/routers/news.py`, lines 10 and 14

```python
from typing import List, Optional    # line 10 (existing)
...
from typing import Literal           # line 14 (added in 4cbd68c)
```

`Literal` should be added to the existing import. Flake8's default config doesn't flag this, but it is unnecessary and would be caught by isort or ruff:

```python
from typing import List, Literal, Optional
```

---

### F-06 — `window` state variable shadows the browser global in sentiment-pulse.tsx  [LOW · sentiment-pulse.tsx]

**File:** `web/frontend/src/features/nfl/components/sentiment-pulse.tsx`, line 246

```typescript
const [window, setWindow] = useState<SentimentWindow>('week');
```

This shadows the browser's `window` global. The component currently has no usage of the browser `window`, but any future addition of DOM API calls (e.g., `window.location`, `window.scrollTo`) would silently get the state value instead. TypeScript does not warn on this shadow.

**Fix:** Rename to `activeWindow` / `setActiveWindow`.

---

### F-07 — WR3→SS matchup pairing in MATCHUP_PAIRS is semantically imprecise  [LOW · matchup-field.tsx — domain logic]

**File:** `web/frontend/src/features/nfl/components/matchup-field.tsx`

```typescript
const MATCHUP_PAIRS: { off: string; def: string }[] = [
  ...
  { off: 'WR3', def: 'SS' },   // slot receiver vs strong safety
  ...
];
```

In modern NFL, the slot receiver (WR3) is primarily covered by the nickel CB, not the SS. The SS's primary responsibility is run support and over-the-top help. Pairing WR3 vs SS will generate green "attack" badges on matchups where the nickel CB is the actual cover man and may have a much higher rating — producing a misleading signal for the user.

A more accurate default: pair WR3 vs LB3 (the most interior LB who often covers the slot) or leave WR3 unmatched with a comment that it depends on the defensive alignment. This is a design/UX judgment call, not a code correctness bug, but it directly affects the feature's analytical value.

---

## Summary

| # | Severity | File | Issue |
|---|----------|------|-------|
| F-01 | MEDIUM | player_rating_service.py | NaN stat values produce "nan" in rating detail tooltip text |
| F-02 | LOW | team_roster_service.py | Double rating_for() call per player (clarity, not perf) |
| F-03 | MEDIUM | player_rating_service.py / news_service.py | lru_cache without TTL; stale post-ingest ratings until restart |
| F-04 | LOW | refresh_madden_ratings.py | fetch_positions() bare dict access; bad Chrome version in UA |
| F-05 | LOW | web/api/routers/news.py | Duplicate from typing import Literal |
| F-06 | LOW | sentiment-pulse.tsx | `window` state variable shadows browser global |
| F-07 | LOW | matchup-field.tsx | WR3→SS pairing is inaccurate for slot coverage in modern NFL |

**No BLOCKING issues. F-01 and F-03 should be fixed before merge. F-02 through F-07 are minor cleanup.**

---

## What Is Working Well

- Team alias table (`_TEAM_ALIASES`) and `canonical_team()` correctly bridges LAR/JAC/WSH/OAK/SD/STL to nflverse codes.
- The LAR→LA fix in `DIVISIONS` is correct and consistent with how rosters/schedules/projections are stored.
- `DefenseRatingLookup.rating_for()` position-guard logic correctly prevents cross-group collisions (a DT never gets a same-named DB's rating).
- `_compute_ratings` shrinks small-sample players toward the median before ranking — sound statistical practice.
- EA Madden / PFR fallback priority in `CombinedRatingLookup` is cleanly implemented.
- `load_team_matchup` gracefully handles: alias inputs, missing seasons (fallback), bye weeks (`is_bye=True`), unknown teams (ValueError → 404).
- `get_sentiment_rankings` correctly filters out records with no `player_id`, preventing "The Lions", coaches, and other entity noise from the player rankings.
- Confidence-weighted average sentiment is mathematically correct and the test covers it with an exact assertion.
- `topStoriesQueryOptions` and `sentimentRankingsQueryOptions` use `staleTime: 5 * 60 * 1000` with matching `refetchInterval` — correct pattern for a live-polling feed.
- `MatchupFieldView` is hidden on mobile (`hidden md:block`) with a list-panel fallback — responsive design maintained.

---

## Verification Pass — commit 35ee35c (2026-07-02)

**Commit claim:** resolves F-01..F-07 from the prior review.
**Files touched:** `player_rating_service.py`, `team_roster_service.py`, `news_service.py`, `news.py`, `refresh_madden_ratings.py`, `sentiment-pulse.tsx`, `matchup-field.tsx` (7 files, +120 / -60 lines).

---

### F-01 — NaN tooltip text: RESOLVED

A `_stat()` helper is introduced in `player_rating_service.py`:

```python
def _stat(row, col, fmt="{:.0f}", scale=1.0) -> str:
    val = row.get(col)
    if val is None or pd.isna(val):
        return "—"
    return fmt.format(float(val) * scale)
```

Every previously unsafe column access in `_detail_for_row` (`sk`, `prss`, `comb`, `rat`, `int`, `cmp_percent`) now routes through `_stat()`. The `g` field also switches from `row["g"]` to `row.get("g")` with `pd.notna()` guard. The `scale=100` usage for `cmp_percent` is correct (PFR stores the value as a decimal; the original code multiplied by 100 inline). The `'{:.0f}%'` format string produces "65%" for 0.65, which is the intended output. No regression introduced.

---

### F-02 — Double rating_for() call per player: RESOLVED

Note: the commit message labels this fix as F-03 and the lru_cache fix as F-02 — the labels are transposed relative to the original review. The code itself is correct regardless of the label.

`_add_rating_column` in `team_roster_service.py` now calls `rating_lookup.rating_for()` once via `df.apply()` and unpacks both the rating and detail into `df["_madden_rating"]` and `df["_rating_detail"]`. `_row_to_player` reads both pre-computed columns from the row via `"_madden_rating" in row.index`. The `elif rating_lookup` fallback branch is preserved for callers that skip `_add_rating_column`, so the change is non-breaking. No regression introduced.

---

### F-03 — lru_cache without TTL: RESOLVED

Note: commit message labels this as F-02 (labels transposed relative to original review, as noted above).

All three process-scoped `@lru_cache` decorators are replaced with the (file-path, mtime)-keyed delegation pattern:

- `load_defense_ratings` resolves the parquet path via `_resolve_pfr_def_path()`, then delegates to `@lru_cache _load_defense_ratings_cached(path_str, mtime, effective_season, season)`.
- `load_madden_lookup` resolves the latest Madden parquet path, then delegates to `@lru_cache _load_madden_lookup_cached(path_str, mtime)`.
- `_player_id_team_map` in `news_service.py` resolves the latest roster parquet path, then delegates to `@lru_cache _player_id_team_map_cached(path_str, mtime)`.

`load_combined_ratings` loses its own `@lru_cache` (now uncached), relying on both child lookups being mtime-keyed. The wrapper object is re-allocated on each call but is effectively free — this is correct.

One observation worth noting: `_load_defense_ratings_cached` includes `season: int` (the originally requested season) in the cache key alongside `effective_season`. Two different requested seasons that walk back to the same parquet will produce two identical cache entries rather than sharing one. This is harmless with `maxsize=8` for a 32-team API, but a future optimization could key only on `(path_str, mtime, effective_season)`. Not a regression.

---

### F-04 — fetch_positions bare dict access + Chrome UA: RESOLVED

`fetch_positions` in `refresh_madden_ratings.py` replaces the bare `data["pageProps"]["ratingsFilters"]["positions"]` chain with:

```python
positions = (
    data.get("pageProps", {}).get("ratingsFilters", {}).get("positions") or []
)
if not positions:
    raise RuntimeError(
        "No positions in ratings.json — EA payload shape changed? "
        f"pageProps keys: {sorted(data.get('pageProps', {}).keys())}"
    )
```

The diagnostic `pageProps keys` message in the RuntimeError is genuinely useful when debugging an EA schema change. The User-Agent is updated from `Chrome/149.0.0.0` to `Chrome/127.0.0.0`. No regression introduced.

---

### F-05 — Duplicate typing import: RESOLVED

`web/api/routers/news.py` now has a single consolidated import:

```python
from typing import List, Literal, Optional
```

The duplicate `from typing import Literal` line is removed. No regression introduced.

---

### F-06 — activeWindow rename: PARTIALLY RESOLVED — REGRESSION INTRODUCED

The state variable rename from `window` to `activeWindow` is correct, and all JSX variable references (`topStoriesQueryOptions(activeWindow)`, `onClick={() => setActiveWindow(w.id)}`, template literals `past ${activeWindow}`) are properly updated.

However, the rename was applied too broadly via what appears to be a global find-and-replace, capturing occurrences of the word "window" in plain English string literals and JSDoc prose. Six user-visible or documentation strings now read incorrectly:

| Location | Before | After (incorrect) |
|----------|--------|-------------------|
| JSDoc header comment | `trailing-window view` | `trailing-activeWindow view` |
| JSDoc panel description | `stories in the window` | `stories in the activeWindow` |
| EmptyState `title` prop | `No stories in this window` | `No stories in this activeWindow` |
| EmptyState `description` prop | `Try a wider window —` | `Try a wider activeWindow —` |
| RankingsColumn `empty` prop | `No positive player signals in this window.` | `No positive player signals in this activeWindow.` |
| RankingsColumn `empty` prop | `No negative player signals in this window.` | `No negative player signals in this activeWindow.` |

The four `empty` and `title`/`description` values are rendered directly to the user when no sentiment data is available. Displaying "No stories in this activeWindow" and "Try a wider activeWindow" exposes a camelCase variable name as English prose, which is a UI correctness bug. The JSDoc comment damage is documentation-only but also incorrect.

The template literal interpolations (`past ${activeWindow}`, `Sentiment Risers — past ${activeWindow}`) are correct — they display the runtime value of the variable ("week", "month", "day"), not the variable name.

**Required follow-up fix** (three targeted edits to `sentiment-pulse.tsx`):
1. JSDoc comment lines: restore `trailing-window view` and `stories in the window`.
2. `EmptyState` `title` and `description`: restore `No stories in this window` and `Try a wider window`.
3. `RankingsColumn` `empty` props: restore `No positive player signals in this window.` and `No negative player signals in this window.`

---

### F-07 — WR3→SS pairing removed: RESOLVED

`{ off: 'WR3', def: 'SS' }` is deleted from `MATCHUP_PAIRS` in `matchup-field.tsx`. An explanatory block comment is added above the constant documenting the rationale (slot coverage belongs to the nickel CB, which the 11-man display does not slot). WR3 is now unmatched, which prevents the misleading attack-badge generation identified in the original review. No regression introduced.

---

### Verification Summary

| Finding | Verdict | Notes |
|---------|---------|-------|
| F-01 | RESOLVED | `_stat()` helper covers all NaN-prone PFR columns; `g` field guarded |
| F-02 | RESOLVED | `_rating_detail` column added; `_row_to_player` reads from row, single lookup per player |
| F-03 | RESOLVED | (file, mtime)-keyed cache delegation in all three services |
| F-04 | RESOLVED | Defensive `.get()` chain + RuntimeError with diagnostics; Chrome/127 UA |
| F-05 | RESOLVED | Single consolidated `from typing import List, Literal, Optional` |
| F-06 | PARTIALLY RESOLVED | Variable rename correct; 6 user-facing strings and JSDoc lines incorrectly contain "activeWindow" as English prose — UI correctness regression, requires follow-up |
| F-07 | RESOLVED | WR3→SS pair removed with explanatory comment |

**Note:** the commit message has F-02 and F-03 labels transposed relative to the original review. The underlying code changes are correct for both findings; only the commit-message attribution is swapped.

**Merge recommendation:** Block on F-06 regression (UI strings display camelCase variable name to users) before merging to main. All other findings are cleanly resolved.

---

### F-06 Follow-up — commit de0177b (2026-07-02): FULLY RESOLVED

Commit `de0177b` ("fix(news): restore 'window' as English in sentiment-pulse prose strings") corrects exactly the six strings identified in the regression note above — the two JSDoc comment lines, the `EmptyState` `title` and `description` props, and both `RankingsColumn` `empty` props — all now read as normal English ("window", not "activeWindow"). Code identifiers are confirmed untouched: both surviving `activeWindow` references (`key={activeWindow}` and the `past ${activeWindow}` template literal) appear as unchanged context in the diff. The commit is scoped to a single file with no structural changes and no collateral modifications. F-06 is closed; no further action required on this finding.

---

## CI Fix Addendum — commit 2bfff30 (2026-07-02, branch fix/ci-backend-web-deps)

**Commit:** "ci: install web API deps for backend tests" (PR #11)
**Scope:** `.github/workflows/ci.yml` only — two hunks in the Backend Tests job.

### Verdict: PASS — correct and safe to merge as-is, with two minor observations noted below.

---

### Check 1 — YAML validity: PASS

The full workflow file is well-formed YAML. Indentation is consistent (2-space) throughout; no tabs are present. The two added hunks integrate cleanly into the surrounding structure with no syntax anomalies.

---

### Check 2 — Multi-line cache-dependency-path syntax: PASS

The actions/setup-python@v5 `cache-dependency-path` input accepts either a single-line string or a YAML literal block scalar with one path per line. The commit uses:

```yaml
cache-dependency-path: |
  requirements.txt
  web/requirements.txt
```

This is the documented multi-path form for this action. Both paths are correctly indented relative to the key, and neither contains spaces that would require quoting. `web/requirements.txt` is confirmed present on the branch (file contains 5 entries: fastapi, uvicorn, pydantic, psycopg2-binary, mangum).

---

### Check 3 — pip install line syntax: PASS

```
pip install -r requirements.txt -r web/requirements.txt httpx
```

Multiple `-r`/`--requirement` flags in a single `pip install` invocation are valid pip syntax and have been supported since pip 1.x. The explicit trailing `httpx` is necessary: `httpx` does not appear in `requirements.txt` or `web/requirements.txt`, and FastAPI's `TestClient` (used by `tests/test_api_*.py` and `tests/web/`) requires it at collection time. The fix is correctly targeted.

---

### Check 4 — No other jobs or triggers altered: PASS

The diff is surgically limited to two step definitions inside the `backend-tests` job: the `Setup Python` step's `with:` block and the `Install dependencies` step's `run:` line. Verified against the full post-merge ci.yml:

- `on:` triggers (pull_request, push, workflow_dispatch) — unchanged
- `concurrency:` block — unchanged
- `frontend-build` job — unchanged
- `backend-tests` job: `runs-on`, `Detect changes` step, `paths-filter` block, `Run pytest` step — all unchanged
- `deploy-drift-check` job — unchanged

---

### Observation A — httpx not pinned in any requirements file (minor)

`httpx` is installed as a bare package name with no version constraint. The pip cache key is built from the two requirements files, so a new PyPI release of httpx will not invalidate the cache — the cached environment will keep the version that was resolved on the last cache-miss run. This is unlikely to cause a problem in practice (httpx follows semver and TestClient usage is stable across minor versions), but if the team ever needs to pin httpx (e.g., to avoid a breaking change), the correct fix is to add `httpx>=X,<Y` to `web/requirements.txt` and let the cache key pick it up automatically. Not a blocking concern for this PR.

---

### Observation B — web/requirements.txt absent from the paths-filter trigger list (pre-existing, not introduced here)

The `Detect changes` step's `python:` filter covers `requirements.txt` but not `web/requirements.txt`:

```yaml
filters: |
  python:
    - 'src/**'
    - 'web/api/**'
    - 'scripts/**'
    - 'tests/**'
    - 'requirements.txt'
    - '.github/workflows/ci.yml'
```

A PR that only modifies `web/requirements.txt` (e.g., adding `httpx` or bumping `fastapi`) will not trigger the Backend Tests job unless another tracked path also changes. This is a pre-existing gap that predates commit 2bfff30; the commit does not worsen it. The natural follow-up is to add `web/requirements.txt` to the filter list, but that is out of scope for this CI-fix PR.

---

### Summary

| Check | Result |
|-------|--------|
| Valid YAML | PASS |
| Multi-line cache-dependency-path syntax (actions/setup-python@v5) | PASS |
| pip install line syntax | PASS |
| No other jobs or triggers altered | PASS |
| Obs A: httpx unpinned (minor, not blocking) | NOTE |
| Obs B: web/requirements.txt absent from paths-filter (pre-existing, not blocking) | NOTE |

The commit achieves exactly what the message describes — both blocking classes of missing imports (fastapi and httpx) are now installed in CI — and touches nothing else. Safe to merge.

---

## CI Fix Addendum — commit 5fb70a4 (2026-07-02, branch fix/ci-skip-local-lake-tests)

**Commit:** "test: skip BRNZ-03 data-lake audit when local Bronze lake absent"
**Scope:** `tests/test_bronze_2025.py` only — 12-line insertion before `TestBronze2025Completeness`.

### Verdict: PASS — correct on all three verification points.

---

### Check 1 — Skip condition correctness and false-positive risk in CI: PASS

The condition is:

```python
_FULL_LAKE_PRESENT = os.path.isdir(os.path.join(BRONZE_DIR, "pbp"))
```

`data/bronze/pbp/` is absent in CI for two independent reasons that must both change before a false-positive is possible:

First, the `.gitignore` default rule `data/*` blocks the entire `data/` subtree. The allowlisted Bronze paths via `!data/bronze/...` rules are: `sentiment/`, `players/rosters/`, `players/rosters_live/`, `players/rookies/`, `depth_charts/`, `external_projections/`, `schedules/`, `madden_ratings/`, `pfr/seasonal/def/`, and `odds_api/`. There is no `!data/bronze/pbp/` entry. This is consistent with the commit comment claim and with the CLAUDE.md architectural intent for TD-08 and TD-09 (only paths required at deploy or by GHA are allowlisted).

Second, the CI job (`backend-tests` in `ci.yml`) uses `actions/checkout@v4` with no extra parameters — a standard clean shallow checkout — and performs no Bronze ingestion step. There is no mechanism that could create `data/bronze/pbp/` in a CI runner environment.

The canary is well-chosen: PBP is the largest and most computation-intensive Bronze type and is the least likely candidate for a future gitignore allowlist. If the allowlist is ever extended to include pbp (which would require a TD-style architectural decision), the skip would correctly stop firing and the tests would run.

---

### Check 2 — `pytestmark` at module level is valid pytest usage and covers all tests in the class: PASS

`pytestmark = pytest.mark.skipif(...)` placed at module scope (outside any class, before the class definition) is the documented pytest mechanism for applying a mark to every test collected from that module. Pytest merges module-level, class-level, and function-level marks at collection time, so the mark applies to all 11 methods inside `TestBronze2025Completeness` without any per-method decoration or class-level `pytestmark` attribute. This is correct usage.

The variable is evaluated at module import time (during pytest collection). There is no timing issue: `os.path.isdir()` is called exactly once when the module is loaded, which is the correct point at which the decision must be made.

---

### Check 3 — "11 skipped without lake / 11 passed with lake" count: PASS

`TestBronze2025Completeness` contains exactly 11 test methods:

1. `test_schedules_exist`
2. `test_schedules_row_count`
3. `test_pbp_exists`
4. `test_pbp_row_count`
5. `test_player_weekly_exists`
6. `test_player_seasonal_exists`
7. `test_snap_counts_exist`
8. `test_rosters_exist`
9. `test_teams_exist`
10. `test_injuries_unavailable_for_2025`
11. `test_all_7_available_types_present`

When `data/bronze/pbp/` is absent, `not _FULL_LAKE_PRESENT` is `True` and `pytestmark` skips all 11. The "11 passed with lake" claim is structurally sound: each test probes a distinct Bronze path, and a full 2025 lake would satisfy every assertion. The `test_injuries_unavailable_for_2025` test performs no file I/O (it calls `validate_season_for_type()` from `src/config.py`) and is trivially correct under both conditions — but it is correctly included in the skip since the audit is designed as a holistic pass/fail.

The commit message claim that "the module failed 7 of its 11 tests on every CI run" is accurate. The 4 that would pass in CI on their own are the two `schedules` tests (allowlisted), `test_rosters_exist` (allowlisted), and `test_injuries_unavailable_for_2025` (no I/O). The 7 that would fail are `test_pbp_exists`, `test_pbp_row_count`, `test_player_weekly_exists`, `test_player_seasonal_exists`, `test_snap_counts_exist`, `test_teams_exist`, and `test_all_7_available_types_present`. The count is correct.

---

### Observation — Skip is slightly over-broad for 4 tests (informational, not a defect)

Four of the 11 tests do not require PBP data and would pass in CI independently. The module-level skip is therefore wider than strictly necessary. This is an intentional design choice: BRNZ-03 is a "completeness audit" whose value is the holistic verdict, not individual data-type verdicts. Allowing partial skips (e.g., via per-method `skipif` marks on the 7 failing tests) would let the audit report "9 passed, 0 failed" in CI while hiding the fact that the bronze lake is incomplete. The all-or-nothing approach preserves the audit's integrity and avoids misleading pass counts in the CI summary. The design choice is correct.

---

### Summary

| Check | Result |
|-------|--------|
| Skip condition cannot false-positive in CI (no pbp allowlist in .gitignore) | PASS |
| `pytestmark` at module level is valid pytest; covers all 11 tests in the class | PASS |
| 11-test count matches; "11 skipped / 11 passed" claims are accurate | PASS |
| Over-broad skip (4 tests pass without lake) — intentional design, not a defect | NOTE |

Safe to merge. Together with the sklearn pin (b1291ee) and the web-deps CI fix (PR #11), this completes the three-commit sequence that makes the Backend Tests job fully green.
