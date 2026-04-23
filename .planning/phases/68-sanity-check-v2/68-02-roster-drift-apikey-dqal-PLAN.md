---
phase: 68-sanity-check-v2
plan: 02
type: execute
wave: 2
depends_on:
  - 68-01
files_modified:
  - scripts/sanity_check_projections.py
  - tests/test_sanity_check_v2_drift.py
  - tests/test_sanity_check_v2_canary.py
autonomous: true
requirements:
  - SANITY-05
  - SANITY-07
  - SANITY-10
tags:
  - sanity-check
  - roster-drift
  - dqal
  - api-key-assertion
must_haves:
  truths:
    - "Running the gate with a top-50 PPR projection that still has Kyler Murray on ARI while Sleeper canonical shows him FA produces a CRITICAL finding naming 'Kyler Murray' and 'ARI' (the acceptance canary)"
    - "Running the gate when ENABLE_LLM_ENRICHMENT=true but ANTHROPIC_API_KEY is unset produces a CRITICAL finding naming both env-var names"
    - "Running the gate produces a CRITICAL finding when any player in latest Gold projections parquet has projected_points < 0 (DQAL-03 clamp)"
    - "Running the gate produces a CRITICAL finding when data/bronze/players/rookies/season=2025/ is missing or contains fewer than 50 rookies (DQAL-03 rookie ingestion)"
    - "Running the gate produces a CRITICAL finding when latest external rankings parquet has any consecutive rank gap > 25 (DQAL-03 rank-gap threshold)"
    - "Sleeper API responses are cached to data/.cache/sleeper_players_YYYYMMDD.json per day to avoid rate-limit abuse"
  artifacts:
    - path: "scripts/sanity_check_projections.py"
      provides: "_check_roster_drift_top50, _fetch_sleeper_canonical_cached, _assert_api_key_when_enrichment_enabled, _check_dqal_negative_projection, _check_dqal_rookie_ingestion, _check_dqal_rank_gap functions"
      contains: "def _check_roster_drift_top50"
    - path: "tests/test_sanity_check_v2_drift.py"
      provides: "Unit tests for 3 DQAL-03 assertions + API key assertion + roster drift with Sleeper-mock fixture (Kyler case)"
      min_lines: 180
  key_links:
    - from: "scripts/sanity_check_projections.py::_check_roster_drift_top50"
      to: "data/bronze/players/rosters_live/*.parquet"
      via: "glob + latest-mtime read of Phase 67 live roster output"
      pattern: "rosters_live"
    - from: "scripts/sanity_check_projections.py::_fetch_sleeper_canonical_cached"
      to: "https://api.sleeper.app/v1/players/nfl"
      via: "requests.get with per-day disk cache under data/.cache/"
      pattern: "api.sleeper.app/v1/players"
    - from: "scripts/sanity_check_projections.py::main"
      to: "new DQAL + drift + key-assertion checks"
      via: "called from run_sanity_check() (not --check-live) so they gate-block every deploy regardless of live flag"
      pattern: "_check_roster_drift_top50\\|_check_dqal"
---

<objective>
Deliver the 3 remaining regression classes from the 2026-04-20 audit: roster drift vs Sleeper canonical (Kyler Murray canary), ANTHROPIC_API_KEY assertion when LLM enrichment is enabled, and the 3 DQAL-03 carry-over assertions (negative-projection clamp, 2025 rookie ingestion presence, rank-gap threshold). Extend the canary test from Plan 68-01 to now cover all 6 regressions end-to-end.

Purpose: Close the remaining sanity blindspots. SANITY-05 is the Kyler Murray acceptance canary for this phase (STATE.md). SANITY-07 prevents the "API key unset, extractor silently no-ops" pattern from recurring. SANITY-10 absorbs the deferred v6.0 DQAL-03 work per CONTEXT D-07.

Output: 6 new check functions in `sanity_check_projections.py` (one per regression), a new drift test file, and an extended canary asserting all 6 distinct CRITICAL findings.
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
@.planning/phases/68-sanity-check-v2/68-01-live-probes-and-content-validators-PLAN.md
@scripts/sanity_check_projections.py
@scripts/refresh_rosters.py
@web/api/services/team_roster_service.py
@src/utils.py

<interfaces>
<!-- Key types and contracts the executor needs. -->

From scripts/sanity_check_projections.py (already updated by Plan 68-01):
```python
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")

# _load_our_projections already exists (line 162) — use it for Gold projections read.
def _load_our_projections(scoring: str, season: int) -> pd.DataFrame

# run_sanity_check(scoring, season) -> int is the entry point for all non-live checks.
# Phase 68-02 additions hook into run_sanity_check (NOT run_live_site_check) so they
# gate-block every deploy regardless of --check-live flag.
```

Sleeper API — reference scripts/refresh_rosters.py for the exact request pattern:
```python
# GET https://api.sleeper.app/v1/players/nfl
# Returns a HUGE JSON dict keyed by sleeper_player_id. Each value is a player dict:
#   {"full_name": "Kyler Murray", "team": "ARI" | None, "position": "QB",
#    "fantasy_positions": ["QB"], ...}
# team == None indicates Free Agent / Released / Retired.
# Cache locally because the payload is ~30MB and rate limits exist.
```

Phase 67 live roster output (SANITY-05 reads this to extract "the website's current truth"):
```
data/bronze/players/rosters_live/*.parquet
# Schema: season, team, player_id, player_name, position, status, updated_at
# This is what the website serves via /api/teams/{team}/roster.
```

Latest Gold projections (SANITY-10 negative clamp + top-50 source):
```
data/gold/projections/season=2026/*.parquet  (preseason — latest file wins)
# Schema includes: player_id, player_name, position, team, projected_points
```

External rankings parquet (SANITY-10 rank-gap):
```
data/gold/rankings/season=2026/*.parquet  OR
data/adp_latest.csv
# Check which exists; prefer parquet. Schema: rank, player_name, position, team.
```

2025 rookies Bronze (SANITY-10 ingestion presence):
```
data/bronze/players/rookies/season=2025/*.parquet  — may NOT exist yet
# If path missing entirely: CRITICAL (rookie ingestion never ran)
# If path exists with < 50 rows: CRITICAL (partial ingestion)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add roster drift check (SANITY-05 — Kyler Murray canary) + Sleeper cache helper</name>
  <files>scripts/sanity_check_projections.py, tests/test_sanity_check_v2_drift.py</files>
  <read_first>
    - scripts/sanity_check_projections.py lines 114-160 (_normalize_name + name mapping helpers — reuse for cross-source matching)
    - scripts/refresh_rosters.py lines 365-440 (Sleeper API pattern + team-null handling for released/FA players)
    - web/api/services/team_roster_service.py (Sleeper API call pattern reference)
    - .planning/STATE.md "Phase 67 Status" section — confirms rosters_live is the v7.0 source of truth
  </read_first>
  <behavior>
    - Test 1: _check_roster_drift_top50 returns ([], []) when all 50 top-PPR players have team matching Sleeper canonical
    - Test 2: _check_roster_drift_top50 returns (["ROSTER DRIFT: Kyler Murray Gold says ARI, Sleeper says FA"], []) when Kyler's team mismatches — this is the acceptance canary
    - Test 3: _check_roster_drift_top50 returns (["ROSTER DRIFT: <player> ..."], []) aggregating multiple mismatches into one CRITICAL per player (NOT one combined message)
    - Test 4: _fetch_sleeper_canonical_cached returns cached dict on same-day re-call (network.get should be called exactly once)
    - Test 5: _fetch_sleeper_canonical_cached returns ({}, warning) when Sleeper API raises ConnectionError; returns WARNING only (not CRITICAL) so we don't block deploy on upstream outage
    - Test 6: _fetch_sleeper_canonical_cached writes cache to data/.cache/sleeper_players_YYYYMMDD.json
  </behavior>
  <action>
Add to `scripts/sanity_check_projections.py`:

```python
import json
from datetime import datetime, timezone

_SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
_SLEEPER_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", ".cache")


def _fetch_sleeper_canonical_cached() -> Tuple[Dict[str, Dict], Optional[str]]:
    """Fetch Sleeper player universe with per-day disk cache. Returns (players_dict, warning).

    Cache key: data/.cache/sleeper_players_YYYYMMDD.json (UTC date).
    On network failure returns ({}, warning_msg); caller treats empty dict as "skip drift check".
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_path = os.path.join(_SLEEPER_CACHE_DIR, f"sleeper_players_{today}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as fh:
                return json.load(fh), None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Sleeper cache corrupt (%s); re-fetching", exc)
    try:
        resp = requests.get(_SLEEPER_PLAYERS_URL, timeout=30)
        resp.raise_for_status()
        players = resp.json()
    except requests.RequestException as exc:
        return {}, (
            f"SLEEPER API UNREACHABLE ({type(exc).__name__}: {exc}); "
            f"skipping roster drift check — this is a WARNING, not CRITICAL, "
            f"so upstream outages do not block deploy"
        )
    os.makedirs(_SLEEPER_CACHE_DIR, exist_ok=True)
    try:
        with open(cache_path, "w") as fh:
            json.dump(players, fh)
    except OSError as exc:
        logger.warning("Failed to write Sleeper cache to %s: %s", cache_path, exc)
    return players, None


def _check_roster_drift_top50(scoring: str, season: int) -> Tuple[List[str], List[str]]:
    """SANITY-05: compare top-50 PPR players' teams against Sleeper canonical. CRITICAL on mismatch."""
    criticals: List[str] = []
    warnings: List[str] = []
    try:
        our_df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(f"ROSTER DRIFT SKIPPED: no Gold projections for season={season} ({exc})")
        return criticals, warnings
    if our_df.empty or "projected_points" not in our_df.columns:
        warnings.append("ROSTER DRIFT SKIPPED: Gold projections empty or missing projected_points")
        return criticals, warnings
    top50 = our_df.sort_values("projected_points", ascending=False).head(50).copy()
    sleeper_players, fetch_warning = _fetch_sleeper_canonical_cached()
    if fetch_warning:
        warnings.append(fetch_warning)
        return criticals, warnings
    # Build Sleeper name->team lookup (None team = FA). Normalize using existing helper.
    sleeper_name_to_team: Dict[str, Optional[str]] = {}
    for pid, p in sleeper_players.items():
        name = p.get("full_name") or p.get("search_full_name") or ""
        if not name:
            continue
        team_raw = p.get("team")
        # Apply Sleeper→nflverse normalization (_SLEEPER_TO_NFLVERSE_TEAM already defined line 45)
        team = _SLEEPER_TO_NFLVERSE_TEAM.get(team_raw, team_raw) if team_raw else None
        sleeper_name_to_team[_normalize_name(name)] = team
    for _, row in top50.iterrows():
        our_name = str(row.get("player_name", ""))
        our_team = str(row.get("team", "")).upper()
        if not our_name or not our_team:
            continue
        sleeper_team = sleeper_name_to_team.get(_normalize_name(our_name))
        if sleeper_team is None and _normalize_name(our_name) in sleeper_name_to_team:
            # Explicitly a free agent per Sleeper.
            criticals.append(
                f"ROSTER DRIFT: {our_name} — Gold says {our_team}, "
                f"Sleeper says FA (free agent / released / retired)"
            )
            continue
        if sleeper_team is None:
            # Not found in Sleeper at all — warn, don't block.
            warnings.append(
                f"ROSTER DRIFT NOT-FOUND: {our_name} (Gold team={our_team}) "
                f"not present in Sleeper canonical"
            )
            continue
        if sleeper_team != our_team:
            criticals.append(
                f"ROSTER DRIFT: {our_name} — Gold says {our_team}, Sleeper says {sleeper_team}"
            )
    if not criticals:
        print(f"  [PASS] Roster drift vs Sleeper canonical  (top-50 all match)")
    else:
        print(f"  [FAIL] Roster drift vs Sleeper canonical  ({len(criticals)} mismatches)")
    return criticals, warnings
```

Create `tests/test_sanity_check_v2_drift.py`:
- Test 1-3: parametrize on fake top-50 DataFrames + fake Sleeper dicts. For the Kyler canary, construct `our_df` with `("Kyler Murray", "ARI", 280.5)` and Sleeper dict with `{"123": {"full_name": "Kyler Murray", "team": None, ...}}`; assert CRITICAL contains both "Kyler Murray" and "ARI".
- Test 4-6: use `tmp_path` + `monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path))`. Mock `requests.get` to count call count. First call hits network; second call (same day) reads cache file, network count stays at 1.

Also wire `_check_roster_drift_top50(scoring, season)` into `run_sanity_check()` immediately before its final return statement (find the return site around line 664+). Collect its criticals/warnings into the existing result accumulators that `run_sanity_check` returns via its exit code path.
  </action>
  <verify>
    <automated>source venv/bin/activate &amp;&amp; python -m pytest tests/test_sanity_check_v2_drift.py -v --tb=short 2&gt;&amp;1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def _check_roster_drift_top50\|def _fetch_sleeper_canonical_cached" scripts/sanity_check_projections.py` returns exactly 2 lines
    - `grep -n "_check_roster_drift_top50(" scripts/sanity_check_projections.py` shows at least 2 occurrences (def + call site inside run_sanity_check)
    - `grep -n "sleeper_players_" scripts/sanity_check_projections.py` shows the cache filename pattern `sleeper_players_{today}`
    - `grep -n "SLEEPER API UNREACHABLE" scripts/sanity_check_projections.py` returns at least 1 line (upstream-outage-as-WARNING semantic)
    - `python -m pytest tests/test_sanity_check_v2_drift.py::test_kyler_canary -v` (or equivalent name) passes with assertion on "Kyler Murray" + "ARI" in CRITICAL
    - `python -m pytest tests/test_sanity_check_v2_drift.py -v` exits 0 with all 6+ tests passing
  </acceptance_criteria>
  <done>Roster drift check compares top-50 PPR Gold projections against Sleeper canonical; Kyler Murray canary test proves the regression would have been caught; cache file prevents re-fetching 30MB payload; upstream outage emits WARNING (not CRITICAL) so Sleeper downtime doesn't block our deploys.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add ANTHROPIC_API_KEY assertion (SANITY-07) + DQAL-03 carry-over checks (SANITY-10)</name>
  <files>scripts/sanity_check_projections.py, tests/test_sanity_check_v2_drift.py</files>
  <read_first>
    - .planning/phases/68-sanity-check-v2/68-CONTEXT.md section "DQAL-03 Carry-Over Assertions" for the exact thresholds
    - scripts/sanity_check_projections.py::_load_our_projections (line 162) — reuse for negative-clamp read
    - data/bronze/players/rookies/ (may not exist — test both missing and present states)
    - data/gold/rankings/ OR data/adp_latest.csv (whichever exists — check both)
  </read_first>
  <behavior>
    - Test 1: _assert_api_key_when_enrichment_enabled returns (["API KEY MISSING: ENABLE_LLM_ENRICHMENT=true but ANTHROPIC_API_KEY is unset"], []) when env has ENABLE_LLM_ENRICHMENT=true and ANTHROPIC_API_KEY unset
    - Test 2: _assert_api_key_when_enrichment_enabled returns ([], []) when ENABLE_LLM_ENRICHMENT=false (regardless of ANTHROPIC_API_KEY)
    - Test 3: _assert_api_key_when_enrichment_enabled returns ([], []) when both env vars set
    - Test 4: _check_dqal_negative_projection returns (["NEGATIVE PROJECTION: Player X projected_points=-3.2"], []) when any row has projected_points < 0
    - Test 5: _check_dqal_negative_projection returns ([], []) when all rows >= 0
    - Test 6: _check_dqal_rookie_ingestion returns (["ROOKIE INGESTION MISSING: data/bronze/players/rookies/season=2025/ not found"], []) when path missing entirely
    - Test 7: _check_dqal_rookie_ingestion returns (["ROOKIE INGESTION THIN: found 23, need >= 50"], []) when rookies parquet has only 23 rows
    - Test 8: _check_dqal_rookie_ingestion returns ([], []) when rookies parquet has >= 50 rows
    - Test 9: _check_dqal_rank_gap returns (["RANK GAP: rank 12 → rank 45 (gap=33)"], []) when consecutive rankings jump > 25
    - Test 10: _check_dqal_rank_gap returns ([], []) when all consecutive gaps <= 25
  </behavior>
  <action>
Add to `scripts/sanity_check_projections.py`:

```python
# SANITY-10 thresholds (from 68-CONTEXT.md "DQAL-03 Carry-Over Assertions")
_DQAL_MIN_ROOKIES: int = 50
_DQAL_MAX_RANK_GAP: int = 25


def _assert_api_key_when_enrichment_enabled() -> Tuple[List[str], List[str]]:
    """SANITY-07: if ENABLE_LLM_ENRICHMENT=true, ANTHROPIC_API_KEY must be set."""
    criticals: List[str] = []
    warnings: List[str] = []
    enrichment_flag = os.environ.get("ENABLE_LLM_ENRICHMENT", "false").lower()
    if enrichment_flag not in ("true", "1", "yes"):
        print("  [PASS] LLM enrichment disabled — API key check skipped")
        return criticals, warnings
    if not os.environ.get("ANTHROPIC_API_KEY"):
        criticals.append(
            "API KEY MISSING: ENABLE_LLM_ENRICHMENT=true but ANTHROPIC_API_KEY is unset. "
            "This silently no-ops the news extractor (the 2026-04-20 audit regression)."
        )
        print("  [FAIL] ANTHROPIC_API_KEY unset while ENABLE_LLM_ENRICHMENT=true")
    else:
        print("  [PASS] ANTHROPIC_API_KEY is set (ENABLE_LLM_ENRICHMENT=true)")
    return criticals, warnings


def _check_dqal_negative_projection(scoring: str, season: int) -> Tuple[List[str], List[str]]:
    """SANITY-10: no player may have projected_points < 0 in latest Gold projections."""
    criticals: List[str] = []
    warnings: List[str] = []
    try:
        df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(f"DQAL NEGATIVE-CLAMP SKIPPED: {exc}")
        return criticals, warnings
    if df.empty or "projected_points" not in df.columns:
        warnings.append("DQAL NEGATIVE-CLAMP SKIPPED: Gold projections empty or missing column")
        return criticals, warnings
    negative = df[df["projected_points"] < 0]
    if len(negative) > 0:
        # Report up to first 5 offenders in one aggregated CRITICAL to keep output bounded.
        sample = ", ".join(
            f"{row.get('player_name', '?')} ({row['projected_points']:.2f})"
            for _, row in negative.head(5).iterrows()
        )
        criticals.append(
            f"NEGATIVE PROJECTION: {len(negative)} player(s) have projected_points < 0. "
            f"First {min(5, len(negative))}: {sample}. Clamp invariant violated."
        )
        print(f"  [FAIL] DQAL negative-clamp  ({len(negative)} violations)")
    else:
        print(f"  [PASS] DQAL negative-clamp  (all {len(df)} players projected_points >= 0)")
    return criticals, warnings


def _check_dqal_rookie_ingestion(season: int = 2025) -> Tuple[List[str], List[str]]:
    """SANITY-10: at least _DQAL_MIN_ROOKIES rookies present in Bronze for the target season."""
    criticals: List[str] = []
    warnings: List[str] = []
    rookies_dir = os.path.join(PROJECT_ROOT, "data", "bronze", "players", "rookies", f"season={season}")
    if not os.path.isdir(rookies_dir):
        criticals.append(
            f"ROOKIE INGESTION MISSING: {rookies_dir} not found. "
            f"2025 rookie ingestion has never run."
        )
        print(f"  [FAIL] DQAL rookie ingestion  (path missing: {rookies_dir})")
        return criticals, warnings
    parquet_files = sorted(globmod.glob(os.path.join(rookies_dir, "*.parquet")))
    if not parquet_files:
        criticals.append(
            f"ROOKIE INGESTION MISSING: no parquet files in {rookies_dir}. "
            f"Ingestion partially completed but produced no output."
        )
        print(f"  [FAIL] DQAL rookie ingestion  (no parquet in dir)")
        return criticals, warnings
    df = pd.read_parquet(parquet_files[-1])
    row_count = len(df)
    if row_count < _DQAL_MIN_ROOKIES:
        criticals.append(
            f"ROOKIE INGESTION THIN: found {row_count} rookies in {os.path.basename(parquet_files[-1])}, "
            f"need >= {_DQAL_MIN_ROOKIES}. Partial ingestion detected."
        )
        print(f"  [FAIL] DQAL rookie ingestion  ({row_count} < {_DQAL_MIN_ROOKIES})")
    else:
        print(f"  [PASS] DQAL rookie ingestion  ({row_count} rookies in season={season})")
    return criticals, warnings


def _check_dqal_rank_gap(season: int = 2026) -> Tuple[List[str], List[str]]:
    """SANITY-10: no consecutive rank gap > _DQAL_MAX_RANK_GAP in external rankings."""
    criticals: List[str] = []
    warnings: List[str] = []
    rank_glob = os.path.join(PROJECT_ROOT, "data", "gold", "rankings", f"season={season}", "*.parquet")
    rank_files = sorted(globmod.glob(rank_glob))
    rank_df: Optional[pd.DataFrame] = None
    if rank_files:
        rank_df = pd.read_parquet(rank_files[-1])
    else:
        # Fallback: data/adp_latest.csv
        adp_csv = os.path.join(PROJECT_ROOT, "data", "adp_latest.csv")
        if os.path.exists(adp_csv):
            rank_df = pd.read_csv(adp_csv)
    if rank_df is None or rank_df.empty:
        warnings.append(f"DQAL RANK-GAP SKIPPED: no external rankings file for season={season}")
        return criticals, warnings
    rank_col = next((c for c in ("rank", "overall_rank", "adp", "ecr") if c in rank_df.columns), None)
    if rank_col is None:
        warnings.append(f"DQAL RANK-GAP SKIPPED: no rank column in rankings schema")
        return criticals, warnings
    sorted_ranks = rank_df[rank_col].dropna().sort_values().astype(int).tolist()
    max_gap = 0
    gap_boundary = None
    for prev, curr in zip(sorted_ranks, sorted_ranks[1:]):
        gap = curr - prev
        if gap > max_gap:
            max_gap = gap
            gap_boundary = (prev, curr)
    if max_gap > _DQAL_MAX_RANK_GAP:
        assert gap_boundary is not None
        criticals.append(
            f"RANK GAP: rank {gap_boundary[0]} → rank {gap_boundary[1]} (gap={max_gap}, "
            f"threshold={_DQAL_MAX_RANK_GAP}). External rankings likely have missing players."
        )
        print(f"  [FAIL] DQAL rank-gap  (max gap {max_gap} > {_DQAL_MAX_RANK_GAP})")
    else:
        print(f"  [PASS] DQAL rank-gap  (max consecutive gap {max_gap} <= {_DQAL_MAX_RANK_GAP})")
    return criticals, warnings
```

Wire all 4 helpers (`_assert_api_key_when_enrichment_enabled`, `_check_dqal_negative_projection`, `_check_dqal_rookie_ingestion`, `_check_dqal_rank_gap`) into `run_sanity_check()` immediately before its final return. Accumulate their criticals/warnings into the same lists used by existing run_sanity_check logic. If the existing function uses print-style tracking rather than accumulators, add a section header `"  DQAL-03 CARRY-OVER ASSERTIONS"` before these calls and adjust the function's final CRITICAL count so the exit code reflects them (exit 2 when any new CRITICAL surfaces, per CONTEXT "Gate Severity & Exit Codes").

Append to `tests/test_sanity_check_v2_drift.py` 10 new tests per behavior block. Use `monkeypatch.setenv` for API key tests, `monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))` plus fixture parquet creation for DQAL tests.
  </action>
  <verify>
    <automated>source venv/bin/activate &amp;&amp; python -m pytest tests/test_sanity_check_v2_drift.py -v --tb=short 2&gt;&amp;1 | tail -40</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def _assert_api_key_when_enrichment_enabled\|def _check_dqal_negative_projection\|def _check_dqal_rookie_ingestion\|def _check_dqal_rank_gap" scripts/sanity_check_projections.py` returns exactly 4 lines
    - `grep -n "_DQAL_MIN_ROOKIES = 50\|_DQAL_MAX_RANK_GAP = 25" scripts/sanity_check_projections.py` confirms both thresholds match CONTEXT exactly
    - `grep -n "ENABLE_LLM_ENRICHMENT\|ANTHROPIC_API_KEY" scripts/sanity_check_projections.py` returns at least 3 lines (both env var names referenced)
    - `grep -n "_check_dqal_negative_projection(\|_check_dqal_rookie_ingestion(\|_check_dqal_rank_gap(\|_assert_api_key_when_enrichment_enabled(" scripts/sanity_check_projections.py` shows each called exactly once from run_sanity_check (in addition to each def line)
    - `python -m pytest tests/test_sanity_check_v2_drift.py -v` passes with at least 16 tests (6 from Task 1 + 10 from Task 2)
  </acceptance_criteria>
  <done>All 4 DQAL-10 and SANITY-07 checks wired into run_sanity_check(); negative-projection clamp uses projected_points < 0 comparator; rookie threshold is exactly 50; rank-gap threshold is exactly 25; API key check no-ops cleanly when ENABLE_LLM_ENRICHMENT=false.</done>
</task>

<task type="auto">
  <name>Task 3: Extend canary test to cover all 6 regressions end-to-end</name>
  <files>tests/test_sanity_check_v2_canary.py</files>
  <read_first>
    - tests/test_sanity_check_v2_canary.py (the file Plan 68-01 Task 3 created — extend it, don't rewrite)
    - .planning/STATE.md "Production Audit Findings" table (the 6 regressions)
    - scripts/sanity_check_projections.py (all functions added by Plans 68-01 + 68-02)
  </read_first>
  <action>
Add a third test function `test_canary_detects_all_six_regressions()` to `tests/test_sanity_check_v2_canary.py` that wires together:

1. Plan 68-01's HTTP mocks (`_pre_v7_response`) — covers regressions #2, #3, #4, #5
2. A mocked Sleeper API response with Kyler as FA — covers regression #1
3. A stale Silver sentiment fixture (> 48h) — covers regression #6

Concretely:

```python
def test_canary_detects_all_six_regressions(tmp_path, monkeypatch):
    """THE acceptance canary: all 6 regressions from 2026-04-20 audit produce CRITICALs."""
    import scripts.sanity_check_projections as sanity

    # --- Set up tmp_path as PROJECT_ROOT so DQAL + drift reads hit fixtures ---
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sanity, "GOLD_DIR", str(tmp_path / "data" / "gold"))
    monkeypatch.setattr(sanity, "_SLEEPER_CACHE_DIR", str(tmp_path / ".cache"))

    # Gold projections with Kyler still on ARI (the pre-v7.0 state)
    gold_dir = tmp_path / "data" / "gold" / "projections" / "preseason" / "season=2026"
    gold_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    proj_df = pd.DataFrame([
        {"player_name": "Kyler Murray", "team": "ARI", "position": "QB",
         "projected_points": 280.5, "scoring": "half_ppr"},
        # Fill out a realistic-ish top-50 that all match Sleeper so Kyler is the ONLY drift
        *[
            {"player_name": f"Player {i}", "team": "KC", "position": "WR",
             "projected_points": 200.0 - i, "scoring": "half_ppr"}
            for i in range(49)
        ],
    ])
    proj_df.to_parquet(gold_dir / "projections_20260420.parquet", index=False)

    # Stale Silver sentiment fixture — mtime 72h old
    silver_dir = tmp_path / "data" / "silver" / "sentiment" / "signals" / "season=2025" / "week=01"
    silver_dir.mkdir(parents=True, exist_ok=True)
    stale_file = silver_dir / "stale.parquet"
    stale_file.write_bytes(b"")
    stale_mtime = time.time() - (72 * 3600)
    os.utime(stale_file, (stale_mtime, stale_mtime))

    # --- Mock Sleeper response: Kyler is FA (team: None) ---
    fake_sleeper = {
        "kyler_id": {"full_name": "Kyler Murray", "team": None, "position": "QB"},
        **{f"p{i}": {"full_name": f"Player {i}", "team": "KC", "position": "WR"} for i in range(49)},
    }

    # --- Mock HTTP side_effect routing both Railway probes AND Sleeper ---
    from unittest.mock import MagicMock
    def combined_response(url, *args, **kwargs):
        if "api.sleeper.app" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = fake_sleeper
            return resp
        # Otherwise delegate to the Plan 68-01 regression mock
        return _pre_v7_response(url, *args, **kwargs)

    # --- Simulate ENABLE_LLM_ENRICHMENT=true without ANTHROPIC_API_KEY for regression #5 ---
    monkeypatch.setenv("ENABLE_LLM_ENRICHMENT", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch.object(sanity.requests, "get", side_effect=combined_response):
        # Live probe criticals (regressions #2, #3, #4, #5-news-content)
        live_crit, _ = sanity.run_live_site_check(
            backend_url="https://x.railway.app",
            frontend_url="https://x.vercel.app",
            season=2026,
        )
        # Non-live criticals (regressions #1 drift, #5 api key, #6 extractor freshness CRITICAL)
        drift_crit, _ = sanity._check_roster_drift_top50("half_ppr", 2026)
        key_crit, _ = sanity._assert_api_key_when_enrichment_enabled()
        fresh_crit, _ = sanity._check_extractor_freshness()

    all_criticals = live_crit + drift_crit + key_crit + fresh_crit
    crits_str = " || ".join(all_criticals)

    # Assert each of the 6 regressions surfaces a distinct CRITICAL
    assert "Kyler Murray" in crits_str and ("FA" in crits_str or "ARI" in crits_str), \
        f"Missing Kyler Murray roster drift CRITICAL (regression #1). Got: {crits_str}"
    assert "/api/predictions" in crits_str and "422" in crits_str, \
        f"Missing /api/predictions 422 CRITICAL (regression #2). Got: {crits_str}"
    assert "/api/lineups" in crits_str and "422" in crits_str, \
        f"Missing /api/lineups 422 CRITICAL (regression #3). Got: {crits_str}"
    assert ("/api/teams" in crits_str or "ROSTER PROBE" in crits_str) and "503" in crits_str, \
        f"Missing /api/teams/*/roster 503 CRITICAL (regression #4). Got: {crits_str}"
    assert ("NEWS CONTENT EMPTY" in crits_str or "API KEY MISSING" in crits_str), \
        f"Missing news extractor/API key CRITICAL (regression #5). Got: {crits_str}"
    assert "EXTRACTOR STALE" in crits_str and "72" in crits_str, \
        f"Missing stalled-extractor freshness CRITICAL (regression #6). Got: {crits_str}"

    # Aggregate cardinality: at least 6 distinct CRITICALs
    assert len(all_criticals) >= 6, \
        f"Expected >= 6 distinct CRITICAL findings for 6 audit regressions; got {len(all_criticals)}:\n" \
        + "\n".join(f"  - {c}" for c in all_criticals)
```

DO NOT modify the existing `test_canary_detects_four_endpoint_regressions` or `test_canary_passes_against_healthy_state` functions — those validate the Plan 68-01 boundary in isolation and the new test validates the full phase boundary.
  </action>
  <verify>
    <automated>source venv/bin/activate &amp;&amp; python -m pytest tests/test_sanity_check_v2_canary.py::test_canary_detects_all_six_regressions -v --tb=long 2&gt;&amp;1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def test_canary_detects_all_six_regressions" tests/test_sanity_check_v2_canary.py` returns exactly 1 line
    - `grep -c "Kyler Murray\|/api/predictions\|/api/lineups\|/api/teams\|NEWS CONTENT\|EXTRACTOR STALE\|API KEY MISSING" tests/test_sanity_check_v2_canary.py` returns at least 7 (each regression asserted)
    - `grep -n "len(all_criticals) >= 6" tests/test_sanity_check_v2_canary.py` confirms cardinality gate present
    - `python -m pytest tests/test_sanity_check_v2_canary.py::test_canary_detects_all_six_regressions -v` passes
    - Full `python -m pytest tests/test_sanity_check_v2_canary.py -v` passes with exactly 3 tests
  </acceptance_criteria>
  <done>Single end-to-end canary test proves the v2 gate surfaces a distinct CRITICAL for each of the 6 regressions from the 2026-04-20 audit — this IS the phase acceptance gate for success criterion #1 from the ROADMAP.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Local CI runner → Sleeper API | Public unauthenticated endpoint, rate-limited upstream |
| Local CI runner → disk cache | Trusted (ephemeral GHA VM) |
| Env vars (ENABLE_LLM_ENRICHMENT, ANTHROPIC_API_KEY) | Secret presence only — never value logged |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-68-02-01 | Information disclosure | ANTHROPIC_API_KEY logging | mitigate | `_assert_api_key_when_enrichment_enabled` checks presence via `os.environ.get("ANTHROPIC_API_KEY")` and asserts truthy — never echoes the value. CRITICAL message says only "ANTHROPIC_API_KEY is unset" — no surrounding context or partial keys. |
| T-68-02-02 | Denial of service | Sleeper API rate-limit abuse from per-deploy gate runs | mitigate | Per-day disk cache (`sleeper_players_YYYYMMDD.json`) means Sleeper is hit at most 1×/day per runner. Network failure degrades to WARNING so upstream outage never blocks our deploys. |
| T-68-02-03 | Tampering | Sleeper cache file injection | accept | GHA VMs are ephemeral; local dev cache is in `data/.cache/` (already in .gitignore patterns via `data/` exclusion). An attacker who can write `data/.cache/sleeper_players_*.json` can already modify the whole repo. |
| T-68-02-04 | Elevation of privilege | CRITICAL flood bypassing intended per-regression accounting | mitigate | Each regression class produces exactly 1 CRITICAL (drift: 1 per player; DQAL neg-clamp: 1 aggregated with up to 5 offenders; rank-gap: 1 aggregated). Canary test asserts `len(all_criticals) >= 6` so flooding with 20 drift mismatches doesn't mask a missing DQAL assertion. |
</threat_model>

<verification>
```bash
source venv/bin/activate
python -m pytest tests/test_sanity_check_v2_drift.py tests/test_sanity_check_v2_canary.py tests/test_sanity_check_v2_probes.py -v --tb=short
```

Expected: all tests pass (≥ 9 probe + 18 drift + 3 canary = ≥30 tests). The canary test `test_canary_detects_all_six_regressions` is the acceptance gate for success criterion #1 from the ROADMAP.

Additional smoke: running `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` (without --check-live) should now exit with a meaningful code reflecting DQAL + drift + API-key assertions; if the real 2026 Gold/Bronze state is healthy, exit 0.
</verification>

<success_criteria>
- `_check_roster_drift_top50` fails CRITICAL on Kyler Murray ARI→FA mismatch (acceptance canary)
- `_assert_api_key_when_enrichment_enabled` produces CRITICAL iff `ENABLE_LLM_ENRICHMENT=true` AND `ANTHROPIC_API_KEY` unset
- `_check_dqal_negative_projection` fails CRITICAL when any Gold row has projected_points < 0
- `_check_dqal_rookie_ingestion` fails CRITICAL when path missing OR < 50 rookies
- `_check_dqal_rank_gap` fails CRITICAL on any consecutive rank gap > 25
- Sleeper API cached per-day to prevent rate-limit abuse
- End-to-end canary `test_canary_detects_all_six_regressions` passes (all 6 audit regressions surface distinct CRITICALs)
- Combined test count: ≥ 30 new tests across 3 test files
</success_criteria>

<output>
After completion, create `.planning/phases/68-sanity-check-v2/68-02-SUMMARY.md` covering:
- Functions added (6 new: drift, Sleeper cache, API-key assertion, 3 DQAL checks)
- Test count delta (+16-20 new unit tests + 1 integration canary)
- Files modified (scripts/sanity_check_projections.py + 2 test files)
- Acceptance gate: `test_canary_detects_all_six_regressions` passes — this is success criterion #1 from ROADMAP
- Note for downstream: Plan 68-03 promotes `--check-live` to blocking GHA step; the gate is now complete, only the workflow wiring remains
</output>
