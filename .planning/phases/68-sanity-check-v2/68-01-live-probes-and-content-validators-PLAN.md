---
phase: 68-sanity-check-v2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - scripts/sanity_check_projections.py
  - tests/test_sanity_check_v2_probes.py
autonomous: true
requirements:
  - SANITY-01
  - SANITY-02
  - SANITY-03
  - SANITY-04
  - SANITY-06
tags:
  - sanity-check
  - quality-gate
  - live-probes
must_haves:
  truths:
    - "Running --check-live against pre-v7.0 production state surfaces a CRITICAL finding for /api/predictions returning HTTP 422"
    - "Running --check-live against pre-v7.0 production state surfaces a CRITICAL finding for /api/lineups returning HTTP 422"
    - "Running --check-live against pre-v7.0 production state surfaces a CRITICAL finding for /api/teams/{team}/roster returning HTTP 503 on top-10 sampled teams"
    - "Running --check-live surfaces a CRITICAL finding when /api/news/team-events returns 32 rows but fewer than 20 of them have total_articles > 0"
    - "Running --check-live surfaces a CRITICAL finding when latest Silver sentiment timestamp is older than 48h"
    - "Each new probe completes within 5 seconds (timeout enforced) so the full --check-live pass stays under 30 seconds total"
  artifacts:
    - path: "scripts/sanity_check_projections.py"
      provides: "_probe_predictions_endpoint, _probe_lineups_endpoint, _probe_team_rosters_sampled, _validate_team_events_content, _check_extractor_freshness functions invoked from run_live_site_check()"
      contains: "def _probe_predictions_endpoint"
    - path: "scripts/sanity_check_projections.py"
      provides: "_top_n_teams_by_snap_count helper that reads latest Silver team metrics parquet and returns top-10 team abbrs"
      contains: "def _top_n_teams_by_snap_count"
    - path: "tests/test_sanity_check_v2_probes.py"
      provides: "Unit tests covering each new probe and validator with regression-state fixtures (HTTP 422 mock, 32-but-empty payload mock, stale-timestamp mock)"
      min_lines: 120
  key_links:
    - from: "scripts/sanity_check_projections.py::run_live_site_check"
      to: "scripts/sanity_check_projections.py::_probe_predictions_endpoint"
      via: "direct function call inside the API probe loop"
      pattern: "_probe_predictions_endpoint\\("
    - from: "scripts/sanity_check_projections.py::run_live_site_check"
      to: "scripts/sanity_check_projections.py::_validate_team_events_content"
      via: "called after fetching /api/news/team-events to inspect total_articles distribution"
      pattern: "_validate_team_events_content\\("
    - from: "scripts/sanity_check_projections.py::_check_extractor_freshness"
      to: "data/silver/sentiment/signals/season=*/week=*/*.parquet"
      via: "glob + max mtime comparison against now() - 48h threshold"
      pattern: "data/silver/sentiment"
---

<objective>
Extend the existing `run_live_site_check()` in `scripts/sanity_check_projections.py` with five new probes/validators that close the audit-found blindspots: live probes for `/api/predictions`, `/api/lineups`, and `/api/teams/{team}/roster` (top-10 sample); a content validator for `/api/news/team-events` that asserts `total_articles > 0` for at least 20 of 32 teams; and an extractor-freshness check that fails CRITICAL when the latest Silver sentiment timestamp is older than 48h.

Purpose: Plug the holes that let HTTP 422/503 regressions and stalled-extractor (empty `event_flags`) ship to production on 2026-04-20. These are the runtime probes — not infra changes (Plan 68-03 promotes them to blocking).

Output: Updated `sanity_check_projections.py` with 5 new helper functions wired into `run_live_site_check()`, plus a new test file with regression-state fixtures.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/68-sanity-check-v2/68-CONTEXT.md
@scripts/sanity_check_projections.py
@web/api/routers/predictions.py
@web/api/routers/lineups.py
@web/api/routers/teams.py
@web/api/routers/news.py
@src/utils.py

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from existing codebase. -->

From scripts/sanity_check_projections.py (the file being extended):
```python
DEFAULT_LIVE_BACKEND = "https://nfldataengineering-production.up.railway.app"
DEFAULT_LIVE_FRONTEND = "https://frontend-jet-seven-33.vercel.app"

def run_live_site_check(
    backend_url: str,
    frontend_url: str,
    season: int,
) -> Tuple[List[str], List[str]]:
    """Returns (criticals, warnings). Empty criticals == PASS."""

# Existing api_probes list (lines ~973-988) currently tests:
#   /api/health, /api/projections, /api/projections/latest-week, /api/news/team-events (len==32 only)
# This plan ADDS to that list and ADDS post-loop content/freshness checks.
```

From web/api/routers/predictions.py:
```python
@router.get("", response_model=PredictionResponse)
def list_predictions(
    season: Optional[int] = Query(None, ge=1999, le=2030),  # OPTIONAL — defaults to latest
    week: Optional[int] = Query(None, ge=1, le=18),         # OPTIONAL
) -> PredictionResponse:
    # Returns PredictionResponse(season, week, predictions: List[GamePrediction], generated_at, data_as_of, defaulted)
    # Returns empty predictions list (HTTP 200) for offseason; NEVER 422 with valid params.
```

From web/api/routers/lineups.py:
```python
@router.get("", response_model=LineupResponse)
def get_lineups(
    season: Optional[int] = Query(None, ge=1999, le=2030),
    week: Optional[int] = Query(None, ge=1, le=22),
    team: Optional[str] = Query(None, min_length=2, max_length=3),
    scoring: str = Query("half_ppr", pattern="^(ppr|half_ppr|standard)$"),
) -> LineupResponse:
    # Returns LineupResponse(season, week, lineups: List[TeamLineup], generated_at, data_as_of, defaulted)
```

From web/api/routers/teams.py:
```python
@router.get("/{team}/roster", response_model=TeamRosterResponse)
# team must be a valid 2-3 char abbr (KC, ARI, etc.)
# 503 indicates Bronze rosters missing on Railway (the regression we are catching).
```

From web/api/routers/news.py:
```python
@router.get("/team-events", response_model=List[TeamEvents])
def get_team_events(season: int = Query(..., ge=1999, le=2030), week: int = Query(..., ge=1, le=18)):
    # Always returns exactly 32 rows (zero-filled on missing teams).
    # TeamEvents fields: team, negative_event_count, positive_event_count, neutral_event_count,
    #                    total_articles, sentiment_label, top_events
    # The regression: every row has total_articles=0 because extractor never ran.
```

From src/utils.py:
```python
def download_latest_parquet(s3_client, bucket: str, prefix: str, tmp_dir: str = "/tmp") -> pd.DataFrame
def get_latest_s3_key(s3_client, bucket: str, prefix: str) -> str | None
# For local-first reads use glob + sorted-by-mtime — see existing patterns in sanity_check_projections.py
# (e.g. _load_our_projections at line 162 already does local glob).
```

Local Silver sentiment path (read for SANITY-06 freshness):
- `data/silver/sentiment/signals/season=2025/week=*/`*.parquet`
- Use `os.path.getmtime()` of the latest file as the "extractor last ran" timestamp.

Local Silver team metrics path (read for SANITY-03 top-10 teams sample):
- `data/silver/team_metrics/season=2025/week=*/*.parquet` (or use snap_counts directly:
  `data/bronze/players/snaps/season=2025/week=*/*.parquet`)
- If team metrics aren't present, fall back to a hardcoded list of 10 high-snap teams
  (KC, BUF, PHI, DET, BAL, SF, MIA, CIN, GB, DAL) and emit a WARNING about fallback usage.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add live probes for /api/predictions, /api/lineups, and sampled /api/teams/{team}/roster</name>
  <files>scripts/sanity_check_projections.py, tests/test_sanity_check_v2_probes.py</files>
  <read_first>
    - scripts/sanity_check_projections.py lines 945-1072 (existing run_live_site_check, DEFAULT_LIVE_BACKEND/FRONTEND constants, api_probes list)
    - web/api/routers/predictions.py lines 46-117 (signature: season/week OPTIONAL, returns PredictionResponse with .predictions list)
    - web/api/routers/lineups.py lines 63-100 (signature: season/week/team OPTIONAL, returns LineupResponse with .lineups list)
    - web/api/routers/teams.py lines 21-50 (signature: GET /api/teams/{team}/roster, 503 on missing Bronze)
  </read_first>
  <behavior>
    - Test 1: _probe_predictions_endpoint returns ("CRITICAL", "non-200 422") when mocked requests.get yields status_code=422
    - Test 2: _probe_predictions_endpoint returns ("PASS", "") when mocked response is 200 with non-empty .predictions list
    - Test 3: _probe_predictions_endpoint returns ("PASS", "empty allowed in offseason") when 200 with empty list AND season is preseason (week 0 / no Bronze schedules) — distinguishes preseason from broken
    - Test 4: _probe_lineups_endpoint returns ("CRITICAL", "non-200 422") when status_code=422
    - Test 5: _probe_lineups_endpoint returns ("PASS", "") on 200 with .lineups list (any length, including empty for offseason)
    - Test 6: _probe_team_rosters_sampled returns ("CRITICAL", ["ARI 503", "BUF 503", ...]) when 5+ of 10 sampled teams 503
    - Test 7: _probe_team_rosters_sampled returns ("PASS", "") when all 10 sampled teams return 200 with non-empty .players
    - Test 8: _top_n_teams_by_snap_count returns 10 abbrs and falls back to hardcoded list ["KC","BUF","PHI","DET","BAL","SF","MIA","CIN","GB","DAL"] when no Silver team metrics parquet present
    - Test 9: 5-second timeout is enforced — when requests.get raises requests.exceptions.Timeout, probe returns CRITICAL with message containing "TIMEOUT"
  </behavior>
  <action>
Add the following functions to `scripts/sanity_check_projections.py` directly above `run_live_site_check()` (currently at line 949). Use Python `logging` module (not print) per CONTEXT D-Claude's-Discretion. Use `requests.get(url, timeout=5)` for every probe — 5 seconds per CONTEXT specifics. Match existing color-coded stdout style ("[PASS]" / "[FAIL]" / "[WARN]" with two-space indent) used by the surrounding code.

```python
import os
import glob as globmod

# Top-10 fallback list (used when Silver team_metrics parquet missing).
# Selected from 2024 W18 snap_count leaders to match CONTEXT sampling intent.
_TOP_10_TEAMS_FALLBACK: List[str] = [
    "KC", "BUF", "PHI", "DET", "BAL", "SF", "MIA", "CIN", "GB", "DAL",
]
_PROBE_TIMEOUT_SECONDS: int = 5


def _top_n_teams_by_snap_count(season: int, n: int = 10) -> Tuple[List[str], Optional[str]]:
    """Return (team_abbrs, warning_msg). warning_msg is non-empty when fallback used."""
    silver_glob = os.path.join(
        PROJECT_ROOT, "data", "silver", "team_metrics",
        f"season={season}", "week=*", "*.parquet",
    )
    parquet_files = sorted(globmod.glob(silver_glob))
    if not parquet_files:
        # Try snap_counts Bronze as fallback (also week-partitioned).
        snaps_glob = os.path.join(
            PROJECT_ROOT, "data", "bronze", "players", "snaps",
            f"season={season}", "week=*", "*.parquet",
        )
        snap_files = sorted(globmod.glob(snaps_glob))
        if not snap_files:
            return _TOP_10_TEAMS_FALLBACK[:n], (
                f"SAMPLING FALLBACK: no Silver team_metrics or Bronze snaps for season={season}; "
                f"using hardcoded top-{n} list"
            )
        # Aggregate latest snap file: sum offense_pct per team, take top-n.
        df = pd.read_parquet(snap_files[-1])
        if "team" not in df.columns or "offense_pct" not in df.columns:
            return _TOP_10_TEAMS_FALLBACK[:n], "SAMPLING FALLBACK: snaps schema unexpected"
        ranked = (
            df.groupby("team")["offense_pct"].sum().sort_values(ascending=False).head(n).index.tolist()
        )
        return [str(t) for t in ranked], None
    df = pd.read_parquet(parquet_files[-1])
    if "team" not in df.columns:
        return _TOP_10_TEAMS_FALLBACK[:n], "SAMPLING FALLBACK: team_metrics missing 'team' column"
    snap_col = next((c for c in ("total_offense_snaps", "offense_snaps", "snap_count") if c in df.columns), None)
    if snap_col is None:
        return _TOP_10_TEAMS_FALLBACK[:n], "SAMPLING FALLBACK: no snap-count column in team_metrics"
    ranked = df.groupby("team")[snap_col].sum().sort_values(ascending=False).head(n).index.tolist()
    return [str(t) for t in ranked], None


def _probe_predictions_endpoint(backend_url: str, season: int, week: int) -> Tuple[List[str], List[str]]:
    """Probe /api/predictions. CRITICAL on non-200 (esp. 422); PASS on 200 (empty allowed)."""
    criticals: List[str] = []
    warnings: List[str] = []
    path = f"/api/predictions?season={season}&week={week}"
    url = backend_url.rstrip("/") + path
    try:
        resp = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        criticals.append(f"LIVE API TIMEOUT (>{_PROBE_TIMEOUT_SECONDS}s): GET {path}")
        print(f"  [FAIL] {path}  (TIMEOUT)")
        return criticals, warnings
    except requests.RequestException as exc:
        criticals.append(f"LIVE API UNREACHABLE: GET {path} raised {type(exc).__name__}: {exc}")
        print(f"  [FAIL] {path}  (request error)")
        return criticals, warnings
    if resp.status_code != 200:
        criticals.append(f"LIVE API NON-200: GET {path} returned {resp.status_code}")
        print(f"  [FAIL] {path}  (HTTP {resp.status_code})")
        return criticals, warnings
    try:
        payload = resp.json()
    except ValueError:
        criticals.append(f"LIVE API INVALID JSON: GET {path}")
        return criticals, warnings
    if not isinstance(payload, dict) or "predictions" not in payload:
        criticals.append(f"LIVE API UNEXPECTED SHAPE: GET {path} missing 'predictions' key")
        return criticals, warnings
    print(f"  [PASS] {path}  ({len(payload.get('predictions', []))} rows)")
    return criticals, warnings


def _probe_lineups_endpoint(backend_url: str, season: int, week: int) -> Tuple[List[str], List[str]]:
    """Probe /api/lineups. CRITICAL on non-200; PASS on 200 with .lineups present."""
    criticals: List[str] = []
    warnings: List[str] = []
    path = f"/api/lineups?season={season}&week={week}&scoring=half_ppr"
    url = backend_url.rstrip("/") + path
    try:
        resp = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        criticals.append(f"LIVE API TIMEOUT (>{_PROBE_TIMEOUT_SECONDS}s): GET {path}")
        return criticals, warnings
    except requests.RequestException as exc:
        criticals.append(f"LIVE API UNREACHABLE: GET {path} raised {type(exc).__name__}: {exc}")
        return criticals, warnings
    if resp.status_code != 200:
        criticals.append(f"LIVE API NON-200: GET {path} returned {resp.status_code}")
        return criticals, warnings
    try:
        payload = resp.json()
    except ValueError:
        criticals.append(f"LIVE API INVALID JSON: GET {path}")
        return criticals, warnings
    if not isinstance(payload, dict) or "lineups" not in payload:
        criticals.append(f"LIVE API UNEXPECTED SHAPE: GET {path} missing 'lineups' key")
        return criticals, warnings
    print(f"  [PASS] {path}  ({len(payload.get('lineups', []))} teams)")
    return criticals, warnings


def _probe_team_rosters_sampled(backend_url: str, season: int) -> Tuple[List[str], List[str]]:
    """Probe /api/teams/{team}/roster for top-10 teams. CRITICAL on any 503."""
    criticals: List[str] = []
    warnings: List[str] = []
    teams, fallback_warning = _top_n_teams_by_snap_count(season, n=10)
    if fallback_warning:
        warnings.append(fallback_warning)
    failed_teams: List[str] = []
    for team in teams:
        path = f"/api/teams/{team}/roster"
        url = backend_url.rstrip("/") + path
        try:
            resp = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            failed_teams.append(f"{team} TIMEOUT")
            continue
        except requests.RequestException as exc:
            failed_teams.append(f"{team} {type(exc).__name__}")
            continue
        if resp.status_code != 200:
            failed_teams.append(f"{team} {resp.status_code}")
            continue
    if failed_teams:
        criticals.append(
            f"LIVE API ROSTER PROBE FAILED for {len(failed_teams)}/{len(teams)} sampled teams: "
            + ", ".join(failed_teams)
        )
        print(f"  [FAIL] /api/teams/*/roster  ({len(failed_teams)}/{len(teams)} failed)")
    else:
        print(f"  [PASS] /api/teams/*/roster  (all {len(teams)} sampled teams 200)")
    return criticals, warnings
```

Then modify `run_live_site_check()` (around line 988-989) to invoke the three new probes. Insert immediately after the existing `api_probes` for-loop:

```python
    # ---- v2 PROBES (Phase 68 SANITY-01/02/03): predictions, lineups, sampled rosters ----
    pred_crit, pred_warn = _probe_predictions_endpoint(backend_url, season, week=1)
    criticals.extend(pred_crit); warnings.extend(pred_warn)
    line_crit, line_warn = _probe_lineups_endpoint(backend_url, season, week=1)
    criticals.extend(line_crit); warnings.extend(line_warn)
    rost_crit, rost_warn = _probe_team_rosters_sampled(backend_url, season)
    criticals.extend(rost_crit); warnings.extend(rost_warn)
```

Then create `tests/test_sanity_check_v2_probes.py` with the 9 unit tests in the behavior block. Use `unittest.mock.patch('scripts.sanity_check_projections.requests.get')` to mock HTTP responses. Pattern after `tests/web/test_graceful_defaulting.py` for response mocking. Each test < 30 lines.

DO NOT remove or modify the existing `api_probes` loop (still needed for /api/health, /api/projections, /api/projections/latest-week). DO NOT change exit code behavior — just append to `criticals` / `warnings` lists.
  </action>
  <verify>
    <automated>source venv/bin/activate &amp;&amp; python -m pytest tests/test_sanity_check_v2_probes.py -v --tb=short 2&gt;&amp;1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "_probe_predictions_endpoint\|_probe_lineups_endpoint\|_probe_team_rosters_sampled\|_top_n_teams_by_snap_count" scripts/sanity_check_projections.py` returns at least 8 lines (4 def + 4 call sites)
    - `grep -c "timeout=_PROBE_TIMEOUT_SECONDS" scripts/sanity_check_projections.py` returns at least 4 (one per probe)
    - `grep -n "_TOP_10_TEAMS_FALLBACK" scripts/sanity_check_projections.py` shows the constant defined with all 10 of [KC, BUF, PHI, DET, BAL, SF, MIA, CIN, GB, DAL]
    - `python -m pytest tests/test_sanity_check_v2_probes.py -v` exits 0 with at least 9 tests collected and all passing
    - `python -c "from scripts.sanity_check_projections import _probe_predictions_endpoint, _probe_lineups_endpoint, _probe_team_rosters_sampled, _top_n_teams_by_snap_count; print('OK')"` prints "OK"
  </acceptance_criteria>
  <done>Three new live probes (predictions, lineups, sampled rosters) added to run_live_site_check() with 5s timeout and CRITICAL-on-non-200 semantics; top-10 sampling helper reads Silver team_metrics with documented fallback; 9 unit tests pass against regression-state mocks.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add /api/news/team-events content validator (SANITY-04) and extractor freshness check (SANITY-06)</name>
  <files>scripts/sanity_check_projections.py, tests/test_sanity_check_v2_probes.py</files>
  <read_first>
    - scripts/sanity_check_projections.py lines 985-988 (existing /api/news/team-events probe — currently only checks `len == 32`, this task replaces it)
    - web/api/routers/news.py lines 265-312 (TeamEvents schema fields: team, total_articles, sentiment_label, top_events)
    - data/silver/sentiment/signals/season=2025/week=01/ (verify a parquet file exists; use os.path.getmtime() pattern)
  </read_first>
  <behavior>
    - Test 1: _validate_team_events_content returns ([], []) when given 32 rows where ≥20 have total_articles > 0
    - Test 2: _validate_team_events_content returns (["NEWS CONTENT EMPTY: 0/32 teams..."], []) when given 32 rows all with total_articles=0
    - Test 3: _validate_team_events_content returns (["NEWS CONTENT THIN: 12/32 teams..."], []) when only 12 of 32 have total_articles > 0 (below threshold)
    - Test 4: _validate_team_events_content returns ([], ["NEWS CONTENT MARGINAL: 18/32..."]) when 18 of 32 are non-zero (warning band 17-19)
    - Test 5: _check_extractor_freshness returns ([], []) when latest sentiment parquet mtime is within 24h
    - Test 6: _check_extractor_freshness returns ([], ["EXTRACTOR STALE: ... 36h"]) when latest mtime is 36h old (warning band 24-48h per CONTEXT)
    - Test 7: _check_extractor_freshness returns (["EXTRACTOR STALE: ... 72h"], []) when latest mtime is 72h old (CRITICAL >48h per CONTEXT)
    - Test 8: _check_extractor_freshness returns (["EXTRACTOR DATA MISSING: no Silver sentiment parquet found"], []) when glob returns no files
  </behavior>
  <action>
Add two helpers to `scripts/sanity_check_projections.py` immediately after the probe functions added in Task 1:

```python
import time
from datetime import datetime, timezone

# SANITY-04 thresholds (from 68-CONTEXT.md "News Content Threshold")
_NEWS_CONTENT_MIN_TEAMS_OK: int = 20      # >=20 of 32 with total_articles > 0 = PASS
_NEWS_CONTENT_MIN_TEAMS_WARN: int = 17    # 17..19 = WARNING; <17 = CRITICAL

# SANITY-06 thresholds (from 68-CONTEXT.md "Extractor Freshness Window")
_EXTRACTOR_FRESH_HOURS: int = 24
_EXTRACTOR_STALE_CRITICAL_HOURS: int = 48


def _validate_team_events_content(payload: list) -> Tuple[List[str], List[str]]:
    """Validate /api/news/team-events content (not just len). CRITICAL when extractor stalled."""
    criticals: List[str] = []
    warnings: List[str] = []
    if not isinstance(payload, list) or len(payload) != 32:
        criticals.append(
            f"LIVE NEWS PAYLOAD SHAPE: expected list of 32 teams, got "
            f"{type(payload).__name__} len={len(payload) if hasattr(payload, '__len__') else 'n/a'}"
        )
        return criticals, warnings
    teams_with_articles = sum(
        1 for row in payload if isinstance(row, dict) and int(row.get("total_articles", 0)) > 0
    )
    if teams_with_articles >= _NEWS_CONTENT_MIN_TEAMS_OK:
        print(f"  [PASS] /api/news/team-events content  ({teams_with_articles}/32 teams have articles)")
    elif teams_with_articles >= _NEWS_CONTENT_MIN_TEAMS_WARN:
        warnings.append(
            f"NEWS CONTENT MARGINAL: {teams_with_articles}/32 teams have total_articles > 0 "
            f"(below target of {_NEWS_CONTENT_MIN_TEAMS_OK}; would have caught extractor degradation)"
        )
        print(f"  [WARN] /api/news/team-events content  ({teams_with_articles}/32 teams)")
    else:
        criticals.append(
            f"NEWS CONTENT EMPTY: {teams_with_articles}/32 teams have total_articles > 0 "
            f"(threshold {_NEWS_CONTENT_MIN_TEAMS_OK}). Extractor likely stalled — "
            f"this matches the 2026-04-20 audit regression."
        )
        print(f"  [FAIL] /api/news/team-events content  ({teams_with_articles}/32 teams — extractor stalled)")
    return criticals, warnings


def _check_extractor_freshness() -> Tuple[List[str], List[str]]:
    """Assert latest Silver sentiment parquet was written within last 48h (CRITICAL) / 24h (WARN)."""
    criticals: List[str] = []
    warnings: List[str] = []
    silver_glob = os.path.join(
        PROJECT_ROOT, "data", "silver", "sentiment", "signals",
        "season=*", "week=*", "*.parquet",
    )
    parquet_files = globmod.glob(silver_glob)
    if not parquet_files:
        criticals.append(
            "EXTRACTOR DATA MISSING: no Silver sentiment parquet found at "
            "data/silver/sentiment/signals/. Extractor has never run or output path changed."
        )
        print("  [FAIL] Silver sentiment freshness  (no parquet files found)")
        return criticals, warnings
    latest_mtime = max(os.path.getmtime(f) for f in parquet_files)
    age_hours = (time.time() - latest_mtime) / 3600.0
    age_str = f"{age_hours:.1f}h"
    if age_hours <= _EXTRACTOR_FRESH_HOURS:
        print(f"  [PASS] Silver sentiment freshness  (latest write {age_str} ago)")
    elif age_hours <= _EXTRACTOR_STALE_CRITICAL_HOURS:
        warnings.append(
            f"EXTRACTOR STALE: latest Silver sentiment write was {age_str} ago "
            f"(warning at {_EXTRACTOR_FRESH_HOURS}h, critical at {_EXTRACTOR_STALE_CRITICAL_HOURS}h)"
        )
        print(f"  [WARN] Silver sentiment freshness  (latest write {age_str} ago)")
    else:
        criticals.append(
            f"EXTRACTOR STALE: latest Silver sentiment write was {age_str} ago "
            f"(threshold {_EXTRACTOR_STALE_CRITICAL_HOURS}h). Daily cron has stopped or extractor is failing."
        )
        print(f"  [FAIL] Silver sentiment freshness  (latest write {age_str} ago)")
    return criticals, warnings
```

Now MODIFY `run_live_site_check()` to:

1. Replace the existing `/api/news/team-events` entry in `api_probes` (lines 985-988) with a *fetch-only* probe (status 200 + JSON), then call `_validate_team_events_content(payload)` on the parsed payload. Concretely:
   - Remove the `(("/api/news/team-events..."), lambda d: ... len == 32)` tuple from the `api_probes` list.
   - After the `api_probes` for-loop and after the v2 probes added in Task 1, fetch `/api/news/team-events?season=2025&week=1` once explicitly, then call `_validate_team_events_content(payload)` and extend `criticals` / `warnings` with the result.

2. After all API probes complete, call `_check_extractor_freshness()` and extend `criticals` / `warnings`. This runs against the local `data/silver/sentiment/` regardless of `--check-live` URL; it's a "is the daily cron still running" assertion.

Append these to `tests/test_sanity_check_v2_probes.py` — 8 new tests per behavior block. Use `tmp_path` and `monkeypatch` to construct fixture parquet files for freshness tests:
```python
def _make_fake_silver(tmp_path, age_hours):
    f = tmp_path / "season=2025" / "week=01" / "x.parquet"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"")
    target_mtime = time.time() - (age_hours * 3600)
    os.utime(f, (target_mtime, target_mtime))
    return f
```
Then `monkeypatch.setattr(sanity_check_projections, "PROJECT_ROOT", str(tmp_path.parent))` to redirect the glob.

DO NOT modify the existing `_NEWS_CONTENT_MIN_TEAMS_OK = 20` (matches Phase 69 SENT-01 success criterion exactly per CONTEXT D-decisions, "News Content Threshold" section).
  </action>
  <verify>
    <automated>source venv/bin/activate &amp;&amp; python -m pytest tests/test_sanity_check_v2_probes.py -v --tb=short 2&gt;&amp;1 | tail -40</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "_validate_team_events_content\|_check_extractor_freshness" scripts/sanity_check_projections.py` shows at least 4 lines (2 def + 2 call sites in run_live_site_check)
    - `grep -n "_NEWS_CONTENT_MIN_TEAMS_OK = 20" scripts/sanity_check_projections.py` confirms threshold matches CONTEXT decision verbatim (per D-04 / D-news-content)
    - `grep -n "_EXTRACTOR_STALE_CRITICAL_HOURS = 48" scripts/sanity_check_projections.py` confirms 48h CRITICAL threshold matches CONTEXT decision
    - `grep -c "len.*== 32" scripts/sanity_check_projections.py` should be 0 outside _validate_team_events_content (the v1 weak check is replaced)
    - `python -m pytest tests/test_sanity_check_v2_probes.py -v` exits 0 with all tests passing (Task 1 + Task 2 = at least 17 tests)
  </acceptance_criteria>
  <done>News content validator distinguishes empty/marginal/healthy at 17 and 20 thresholds; extractor freshness check fails CRITICAL >48h, WARN 24-48h, PASS <24h; v1 `len == 32` check is fully replaced by content-aware validation; tests cover 8 new cases.</done>
</task>

<task type="auto">
  <name>Task 3: Acceptance canary — replay --check-live against simulated pre-v7.0 production state</name>
  <files>tests/test_sanity_check_v2_canary.py</files>
  <read_first>
    - scripts/sanity_check_projections.py (the full file as updated by Tasks 1 + 2)
    - .planning/STATE.md "Production Audit Findings (2026-04-20)" table for the 6 regressions to assert detection of
    - tests/web/test_graceful_defaulting.py for the FastAPI mocking pattern with `requests_mock` or `unittest.mock.patch`
  </read_first>
  <action>
Create `tests/test_sanity_check_v2_canary.py` — a single integration-style test that simulates the pre-v7.0 production HTTP state and asserts `run_live_site_check()` returns at least 4 distinct CRITICAL findings naming the regressions we MUST catch. (The other 2 of the 6 regressions — Kyler Murray drift and stalled-extractor freshness — are validated in Plan 68-02. This canary covers the 4 endpoint regressions that Tasks 1+2 of this plan deliver.)

Use `unittest.mock.patch('scripts.sanity_check_projections.requests.get')` with a `side_effect` function that returns regression-shaped responses keyed off the URL path:

```python
import re
from unittest.mock import patch, MagicMock
import scripts.sanity_check_projections as sanity


def _pre_v7_response(url, *args, **kwargs):
    """Reproduce the 4 endpoint-class HTTP regressions from the 2026-04-20 audit.

    Maps regression -> mocked response so a single run_live_site_check() pass
    surfaces all 4 CRITICAL findings.
    """
    resp = MagicMock()
    if "/api/predictions" in url:
        resp.status_code = 422  # Audit finding #2: 422 on /api/predictions
        resp.text = '{"detail":[{"loc":["query","season"],"msg":"field required"}]}'
        resp.json.return_value = {"detail": [{"msg": "field required"}]}
    elif "/api/lineups" in url:
        resp.status_code = 422  # Audit finding #3: 422 on /api/lineups
        resp.json.return_value = {"detail": [{"msg": "field required"}]}
    elif re.search(r"/api/teams/[A-Z]{2,3}/roster", url):
        resp.status_code = 503  # Audit finding #3/#4: 503 on /api/teams/*/roster
        resp.json.return_value = {"detail": "Service temporarily unavailable"}
    elif "/api/news/team-events" in url:
        resp.status_code = 200  # Audit finding #5: stalled extractor → 32 rows but all empty
        resp.json.return_value = [
            {"team": t, "total_articles": 0, "negative_event_count": 0,
             "positive_event_count": 0, "neutral_event_count": 0,
             "sentiment_label": "neutral", "top_events": []}
            for t in ["ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
                      "DET","GB","HOU","IND","JAX","KC","LA","LAC","LV","MIA",
                      "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS"]
        ]
    elif "/api/health" in url:
        resp.status_code = 200
        resp.json.return_value = {"status": "ok", "llm_enrichment_ready": False}
    elif "/api/projections" in url:
        resp.status_code = 200
        resp.json.return_value = {
            "projections": [{"player_id": "x", "projected_points": 1.0}],
            "season": 2026, "week": 1,
        }
    else:
        resp.status_code = 200
        resp.text = "<html><body>NFL Analytics Projections</body></html>" * 30
        resp.json.return_value = {}
    return resp


def test_canary_detects_four_endpoint_regressions():
    """Re-running --check-live against pre-v7.0 prod state MUST emit ≥4 distinct CRITICALs."""
    with patch.object(sanity.requests, "get", side_effect=_pre_v7_response):
        criticals, warnings = sanity.run_live_site_check(
            backend_url="https://nfldataengineering-production.up.railway.app",
            frontend_url="https://frontend-jet-seven-33.vercel.app",
            season=2026,
        )

    # Must surface at least 4 CRITICALs naming each endpoint-class regression.
    crits_str = " | ".join(criticals)
    assert "/api/predictions" in crits_str and "422" in crits_str, \
        f"Missing /api/predictions 422 critical. Got: {crits_str}"
    assert "/api/lineups" in crits_str and "422" in crits_str, \
        f"Missing /api/lineups 422 critical. Got: {crits_str}"
    assert "ROSTER PROBE FAILED" in crits_str or "/api/teams" in crits_str, \
        f"Missing /api/teams/*/roster 503 critical. Got: {crits_str}"
    assert "NEWS CONTENT" in crits_str and ("EMPTY" in crits_str or "0/32" in crits_str), \
        f"Missing news content extractor-stalled critical. Got: {crits_str}"
    assert len(criticals) >= 4, \
        f"Expected ≥4 distinct CRITICAL findings; got {len(criticals)}: {criticals}"


def test_canary_passes_against_healthy_state():
    """Sanity: when all endpoints return healthy responses, no CRITICALs surface."""
    def healthy_response(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.text = "<html><body>NFL Analytics Projections lineup</body></html>" * 30
        if "/api/news/team-events" in url:
            resp.json.return_value = [
                {"team": t, "total_articles": 5, "negative_event_count": 1,
                 "positive_event_count": 1, "neutral_event_count": 3,
                 "sentiment_label": "neutral", "top_events": []}
                for t in ["ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
                          "DET","GB","HOU","IND","JAX","KC","LA","LAC","LV","MIA",
                          "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS"]
            ]
        elif "/api/predictions" in url:
            resp.json.return_value = {"predictions": [], "season": 2026, "week": 1}
        elif "/api/lineups" in url:
            resp.json.return_value = {"lineups": [], "season": 2026, "week": 1}
        elif "/api/projections" in url:
            resp.json.return_value = {
                "projections": [{"player_id": "x", "projected_points": 1.0}],
                "season": 2026, "week": 1,
            }
        elif "/api/health" in url:
            resp.json.return_value = {"status": "ok", "llm_enrichment_ready": True}
        else:
            resp.json.return_value = {}
        return resp

    with patch.object(sanity.requests, "get", side_effect=healthy_response):
        criticals, _ = sanity.run_live_site_check(
            backend_url="https://nfldataengineering-production.up.railway.app",
            frontend_url="https://frontend-jet-seven-33.vercel.app",
            season=2026,
        )

    # Endpoint criticals must all be absent (extractor freshness handled separately).
    endpoint_crits = [c for c in criticals if "/api/" in c or "ROSTER PROBE" in c or "NEWS CONTENT" in c]
    assert endpoint_crits == [], \
        f"Healthy state produced false-positive endpoint CRITICALs: {endpoint_crits}"
```

Note: this canary intentionally does NOT cover Kyler Murray roster drift (Plan 68-02 SANITY-05) or extractor freshness CRITICAL (which depends on local filesystem state). Plan 68-02 will add a second canary test verifying those last 2 of the 6 regressions. The acceptance gate (Plan 68-03 SANITY-09) verifies all 6 together end-to-end.
  </action>
  <verify>
    <automated>source venv/bin/activate &amp;&amp; python -m pytest tests/test_sanity_check_v2_canary.py -v --tb=long 2&gt;&amp;1 | tail -25</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/test_sanity_check_v2_canary.py` exists and contains exactly 2 test functions: `test_canary_detects_four_endpoint_regressions`, `test_canary_passes_against_healthy_state`
    - `python -m pytest tests/test_sanity_check_v2_canary.py::test_canary_detects_four_endpoint_regressions -v` passes (asserts ≥4 CRITICALs covering predictions/lineups/rosters/news)
    - `python -m pytest tests/test_sanity_check_v2_canary.py::test_canary_passes_against_healthy_state -v` passes (no endpoint CRITICALs on healthy mocks)
    - `grep -n "len(criticals) >= 4" tests/test_sanity_check_v2_canary.py` returns at least 1 line (acceptance assertion present)
    - `grep -n "/api/predictions\|/api/lineups\|/api/teams\|NEWS CONTENT" tests/test_sanity_check_v2_canary.py` returns at least 4 distinct match lines
  </acceptance_criteria>
  <done>Acceptance canary test proves the 4 endpoint-class regressions from the 2026-04-20 audit are caught by the v2 gate; healthy-state companion test proves no false positives. Plan 68-02 will extend this with the remaining 2 regressions (Kyler + extractor freshness CRITICAL).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Local CI runner → Railway backend | Public HTTP endpoints; sanity script mints no auth headers |
| Local CI runner → local Silver parquet filesystem | Trusted (read-only mtime check) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-68-01-01 | Information disclosure | _probe_team_rosters_sampled response logging | mitigate | Probes log only HTTP status code + team abbr; never log response body. `print(f"...{team} {resp.status_code}")` only — no `resp.text` or `resp.json()` echoed to stdout where GitHub Actions retains logs. |
| T-68-01-02 | Denial of service | Top-10 sequential roster probes against Railway | mitigate | 5s timeout per probe (CONTEXT specifics); top-10 cap (not 32); total budget ~50s worst case. Sequential (not threaded) to avoid burst. |
| T-68-01-03 | Tampering | Local Silver sentiment mtime spoofing for freshness check | accept | Local filesystem is the trust boundary; an attacker who can mutate `data/silver/sentiment/` already owns the runner. CI runs on ephemeral GitHub-hosted machines so persistence is impossible. |
| T-68-01-04 | Repudiation | Sanity script logs not being preserved on rollback | accept | GitHub Actions retains run logs by default for 90 days; rollback (Plan 68-03) preserves the failing run as the trigger. |
</threat_model>

<verification>
After all 3 tasks complete, run the full test suite filter to confirm no regressions:

```bash
source venv/bin/activate
python -m pytest tests/test_sanity_check_v2_probes.py tests/test_sanity_check_v2_canary.py -v --tb=short
python -m pytest tests/ -k "sanity" -v --tb=short
```

Both invocations exit 0 with at least 19 tests passing total (9 probe tests + 8 freshness/content tests + 2 canary tests).

Manual smoke (optional, requires live Railway): `python scripts/sanity_check_projections.py --check-live --season 2026` should now print `[PASS]` lines for /api/predictions, /api/lineups, /api/teams/*/roster sample, and content-aware news check (assuming Plan 67 daily cron has run).
</verification>

<success_criteria>
- `run_live_site_check()` invokes `_probe_predictions_endpoint`, `_probe_lineups_endpoint`, `_probe_team_rosters_sampled`, `_validate_team_events_content`, and `_check_extractor_freshness` exactly once each per call
- Mocked pre-v7.0 production state produces ≥4 CRITICAL findings naming each endpoint-class regression by URL path
- Mocked healthy production state produces zero endpoint-class CRITICALs (no false positives)
- Every probe enforces 5-second `requests.get` timeout
- News content validator uses thresholds 17 (WARN) / 20 (PASS) per CONTEXT D-news-content
- Extractor freshness check uses thresholds 24h (WARN) / 48h (CRITICAL) per CONTEXT D-extractor-freshness
- All 19+ new unit tests pass
</success_criteria>

<output>
After completion, create `.planning/phases/68-sanity-check-v2/68-01-SUMMARY.md` covering:
- Functions added (5 new probes/validators)
- Test count delta (+19 tests)
- Files modified (1 script + 2 new test files)
- Lines added (estimated ~250 to sanity_check_projections.py + ~200 to test files)
- Note for downstream: Plan 68-02 builds on these helpers (extends canary to include Kyler drift + extractor CRITICAL); Plan 68-03 promotes `--check-live` to blocking GHA step
</output>
