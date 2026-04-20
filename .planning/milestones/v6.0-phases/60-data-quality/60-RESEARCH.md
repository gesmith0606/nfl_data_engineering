# Phase 60: Data Quality - Research

**Researched:** 2026-04-17
**Domain:** Data quality validation, roster management, sanity checking (Python/pandas/Sleeper API)
**Confidence:** HIGH

## Summary

Phase 60 addresses data quality issues visible to end users: stale rosters, position misclassifications, and projection sanity. The existing codebase already has substantial infrastructure for this work. `scripts/refresh_rosters.py` handles team updates from Sleeper API (but NOT position updates -- needs extension). `scripts/sanity_check_projections.py` has a comprehensive consensus comparison with hardcoded fallback and prediction validation. The daily-sentiment GHA workflow already calls `refresh_rosters.py` daily.

The primary gaps are: (1) `refresh_rosters.py` does not update `position` from Sleeper, only `recent_team`; (2) the sanity check script does not have local data freshness checks for Gold/Silver parquet files; (3) FantasyPros API returns 403 (requires auth token) so live ECR fetch will fail -- Sleeper rankings (which work reliably) should be the primary live consensus source, with hardcoded CONSENSUS_TOP_50 as fallback; (4) no CI gate exists to block deploys on sanity check failure.

**Primary recommendation:** Extend the existing scripts rather than building new ones. Add position update to `refresh_rosters.py`, add freshness checks to `sanity_check_projections.py`, wire sanity check as a CI gate in `deploy-web.yml`, and update the hardcoded CONSENSUS_TOP_50 for 2026 offseason moves.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Daily GHA cron runs `refresh_rosters.py` to pull Sleeper API data and commit updated Gold parquet. Zero manual effort, audit trail in git.
- **D-02:** When refresh finds a player on the wrong team, auto-fix the Gold parquet and log all changes to `roster_changes.log` for review.
- **D-03:** Roster refresh updates both `recent_team` and `position` from Sleeper API in a single pass (covers DQAL-01 and DQAL-02 together).
- **D-04:** Sleeper API is the canonical position source for all display and projection contexts. When Sleeper disagrees with nfl-data-py, Sleeper wins.
- **D-05:** Position fixes propagate to Gold layer only (projections + website display). Silver/Bronze keep original nfl-data-py positions for historical accuracy and model training stability.
- **D-06:** Critical issues (block deployment) = structural absurdities: backup QB in top 5, negative projections, player on wrong team in top 20, missing positions entirely from output.
- **D-07:** Sanity check runs as a CI gate before website deploys. 0 critical = deploy proceeds; any critical = deploy blocked with report.
- **D-08:** Add data freshness checks: Gold parquet age >7 days = warning, Silver data age >14 days = warning. Catches forgotten pipeline runs before they reach users.
- **D-09:** Live-fetch FantasyPros ECR at sanity check runtime for current consensus rankings (using fetch MCP or requests).
- **D-10:** If FantasyPros fetch fails (rate limit, site down), fall back to hardcoded `CONSENSUS_TOP_50` list. Log a warning that live data was unavailable.

### Claude's Discretion
- Warning threshold calibration (exact rank deviation that triggers warning vs info)
- Sanity check output format (JSON report vs text vs both)
- GHA cron schedule timing (time of day for roster refresh)
- Specific FantasyPros endpoint/scraping approach

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DQAL-01 | All player positions match Sleeper API with zero misclassifications | Extend `refresh_rosters.py` to also update `position` column from Sleeper; build_position_mapping() alongside build_team_mapping(); use Sleeper `position` field (verified via API probe) |
| DQAL-02 | Rosters reflect 2026 trades/FA via daily Sleeper refresh | Already partially implemented -- `refresh_rosters.py` updates `recent_team`, daily-sentiment GHA cron calls it; extend with position + roster_changes.log |
| DQAL-03 | Sanity check passes with <10 warnings and 0 critical issues | Enhance `sanity_check_projections.py` with freshness checks, live Sleeper consensus (FantasyPros API returns 403), structured JSON output, return code semantics |
| DQAL-04 | Preseason projections pass eye test (top 10 matches consensus structure) | Update hardcoded CONSENSUS_TOP_50 with 2026 offseason moves (Davante Adams to LAR, etc.); existing consensus comparison logic works well |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.x (installed) | DataFrame operations on Gold parquet | Already used throughout project [VERIFIED: codebase] |
| requests | 2.32.4 | Sleeper API HTTP calls | Already installed, no auth needed for Sleeper [VERIFIED: pip freeze] |
| pyarrow | installed | Parquet read/write | Already used for all data layer I/O [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy | installed | Spearman rank correlation in sanity checks | Already used in sanity_check_projections.py [VERIFIED: codebase] |
| beautifulsoup4 | 4.13.4 | Potential HTML scraping fallback | Only if FantasyPros HTML scraping attempted [VERIFIED: pip freeze] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FantasyPros ECR (D-09) | Sleeper search_rank as live consensus | FantasyPros API returns 403 without auth; Sleeper is free and reliable |
| Name-based matching | Sleeper player_id matching | Would require ID mapping table; name matching already works with normalization |

**Installation:**
No new packages needed. All dependencies already installed.

## Architecture Patterns

### Existing Code Structure (extend, do not rebuild)
```
scripts/
  refresh_rosters.py           # EXTEND: add position update, roster_changes.log
  sanity_check_projections.py  # EXTEND: add freshness checks, live consensus, JSON output
  refresh_external_rankings.py # EXISTS: already has Sleeper/FP/ESPN ranking fetchers
  check_pipeline_health.py     # REFERENCE: freshness check pattern to adapt for local files
web/api/services/
  external_rankings_service.py # EXISTS: has consensus fallback, cache logic, comparison engine
.github/workflows/
  daily-sentiment.yml          # EXISTS: already calls refresh_rosters.py daily (step 5)
  deploy-web.yml               # EXTEND: add sanity check CI gate step
```

### Pattern 1: Roster Refresh Extension
**What:** Extend `refresh_rosters.py` to update both `recent_team` and `position` from Sleeper API in a single pass.
**When to use:** Daily GHA cron run and manual pre-deploy.
**Key change:** The existing `build_team_mapping()` returns `Dict[str, str]` (name -> team). Extend to also return position, or create a parallel `build_position_mapping()`.

```python
# Current: only returns team
def build_team_mapping(players: dict) -> Dict[str, str]:
    mapping[name_key] = team

# Needed: return both team AND position
def build_roster_mapping(players: dict) -> Dict[str, Dict[str, str]]:
    mapping[name_key] = {'team': team, 'position': pos}
```

### Pattern 2: Sanity Check CI Gate
**What:** Run sanity check as a required step before deploy.
**When to use:** On push to main that touches web/ or src/ or data/.
**Integration point:** Add step to `deploy-web.yml` before the existing deploy steps.

```yaml
# In .github/workflows/deploy-web.yml
- name: Sanity check projections
  run: python scripts/sanity_check_projections.py --scoring half_ppr --season 2026
  # Exit code 1 = CRITICAL issues found -> blocks deploy
```

### Pattern 3: Freshness Check for Local Parquet
**What:** Check file modification time of Gold/Silver parquet files.
**When to use:** As part of sanity check run.
**Adapted from:** `check_pipeline_health.py` freshness pattern (but for local files, not S3).

```python
from pathlib import Path
from datetime import datetime, timedelta

def check_local_freshness(path: str, max_age_days: int) -> CheckResult:
    p = Path(path)
    files = sorted(p.glob('*.parquet'))
    if not files:
        return CheckResult('ERROR', 'freshness', f'No parquet files in {path}')
    latest = max(files, key=lambda f: f.stat().st_mtime)
    age_days = (datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)).days
    if age_days > max_age_days:
        return CheckResult('WARN', 'freshness', f'{path} is {age_days} days old')
    return CheckResult('OK', 'freshness', f'{path} is {age_days} days old')
```

### Anti-Patterns to Avoid
- **Do not rebuild what exists:** The sanity check script, roster refresh script, and external rankings service all exist and work. Extend them; do not rewrite from scratch.
- **Do not use FantasyPros as primary live source:** The API returns 403 (requires auth token). Use Sleeper search_rank as the reliable live consensus proxy.
- **Do not match players by name alone without normalization:** Name collisions exist in Sleeper (36 collisions found). Always use `_normalize_name()` and filter by active status + team.
- **Do not update Silver/Bronze positions:** Decision D-05 explicitly preserves original nfl-data-py positions in Silver/Bronze for model training stability.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Consensus rankings | Custom ranking aggregator | `scripts/refresh_external_rankings.py` + `web/api/services/external_rankings_service.py` | Already built with Sleeper/FP/ESPN sources, cache, and fallback |
| Name normalization | New fuzzy matcher | `_normalize_name()` in sanity_check_projections.py | Already handles suffixes (Jr., III), name variants, special chars |
| Team abbreviation mapping | Custom mapping | `SLEEPER_TO_NFLVERSE_TEAM` in refresh_rosters.py | Only one mismatch: LAR -> LA (verified via API probe) |
| Data freshness checks | Custom S3 scanner | Pattern from `check_pipeline_health.py` adapted for local files | Existing CheckResult pattern with OK/WARN/ERROR levels |

**Key insight:** This phase is almost entirely about extending and connecting existing code, not building new systems. The roster refresh, sanity check, external rankings, and health check scripts all exist and handle their individual domains well. The work is: (1) add position update to roster refresh, (2) add freshness checks to sanity check, (3) wire as CI gate, (4) update stale consensus data.

## Common Pitfalls

### Pitfall 1: Sleeper Name Collisions
**What goes wrong:** Multiple players share the same `full_name` in Sleeper (e.g., "Kenneth Walker" = WR on no team AND RB on KC; "Josh Allen" = OL and QB).
**Why it happens:** Sleeper's player database includes historical/inactive players alongside current ones.
**How to avoid:** Always filter by: (1) `team` is not None, (2) `status` is 'Active', (3) `position` is in FANTASY_POSITIONS. For name matching against Gold parquet, also filter by position to break ties.
**Warning signs:** A player's team or position changes to an unexpected value after roster refresh.
**Verified:** 36 name collisions found in Sleeper among fantasy-relevant positions [VERIFIED: Sleeper API probe].

### Pitfall 2: FantasyPros API Returns 403
**What goes wrong:** Decision D-09 specifies live-fetching FantasyPros ECR, but the API endpoint (`api.fantasypros.com/public/v2/json/nfl/2026/consensus-rankings.php`) returns HTTP 403 "Missing Authentication Token."
**Why it happens:** FantasyPros locked down their public API; it now requires authentication.
**How to avoid:** Use Sleeper `search_rank` as the reliable live consensus proxy (always available, no auth needed). Fall back to hardcoded CONSENSUS_TOP_50 only if Sleeper also fails. Document the FantasyPros 403 issue in the sanity check output.
**Warning signs:** `fetch_fantasypros()` returning empty results or exceptions.
**Verified:** HTTP 403 confirmed via direct API probe [VERIFIED: requests.get test].

### Pitfall 3: Sleeper LAR vs nflverse LA for Rams
**What goes wrong:** Sleeper uses "LAR" for the Los Angeles Rams; nflverse/Gold data uses "LA". Without mapping, players on the Rams appear to have changed teams.
**Why it happens:** Different data providers use different abbreviations.
**How to avoid:** Always apply `SLEEPER_TO_NFLVERSE_TEAM` mapping (already in refresh_rosters.py). Currently only one mismatch: LAR -> LA.
**Warning signs:** 22 Rams players flagged as team changes on every roster refresh.
**Verified:** Only "LAR" differs; all other 31 teams match [VERIFIED: Sleeper API probe].

### Pitfall 4: Stale Hardcoded CONSENSUS_TOP_50
**What goes wrong:** The consensus list in `sanity_check_projections.py` and `external_rankings_service.py` lists Davante Adams as "NYJ" but Sleeper shows him on "LAR" (Rams). Similar issues likely exist for other offseason moves.
**Why it happens:** The hardcoded list was compiled pre-2026 offseason.
**How to avoid:** Update the CONSENSUS_TOP_50 list to reflect 2026 offseason moves. Consider generating it from Sleeper search_rank data rather than maintaining it manually.
**Warning signs:** Large numbers of "MISSING PLAYER" or "RANK GAP" warnings in sanity check.
**Verified:** Davante Adams team mismatch confirmed -- Sleeper shows LAR, consensus shows NYJ [VERIFIED: API probe + Gold data inspection].

### Pitfall 5: Duplicate Parquet Files Accumulating
**What goes wrong:** Each roster refresh writes a new timestamped parquet file (`season_proj_YYYYMMDD_HHMMSS.parquet`). Daily runs mean 365 files per year accumulating in the Gold directory.
**Why it happens:** The write pattern appends rather than overwrites.
**How to avoid:** After writing the new file, optionally remove parquets older than 30 days. Or accept the accumulation since `download_latest_parquet()` always reads the latest anyway.
**Warning signs:** Gold directory grows continuously; git commits get large if data/ is tracked.

## Code Examples

### Example 1: Extended Roster Refresh with Position Update
```python
# Source: Extending scripts/refresh_rosters.py pattern
def build_roster_mapping(players: dict) -> Dict[str, Dict[str, str]]:
    """Build name -> {team, position} mapping from Sleeper."""
    mapping: Dict[str, Dict[str, str]] = {}
    for player_id, info in players.items():
        if not isinstance(info, dict):
            continue
        pos = info.get('position')
        if pos not in FANTASY_POSITIONS:
            continue
        team = info.get('team')
        if not team:
            continue
        full_name = info.get('full_name') or ''
        if not full_name:
            continue
        team = SLEEPER_TO_NFLVERSE_TEAM.get(team, team)
        name_key = full_name.lower().strip()
        # Prefer active players when name collision exists
        if name_key in mapping and info.get('status') != 'Active':
            continue
        mapping[name_key] = {'team': team, 'position': pos}
    return mapping
```

### Example 2: Local Freshness Check
```python
# Source: Adapted from scripts/check_pipeline_health.py pattern
def check_gold_freshness(season: int, max_age_days: int = 7) -> Tuple[str, str]:
    """Check Gold parquet freshness. Returns (level, message)."""
    gold_dir = Path(f'data/gold/projections/preseason/season={season}')
    if not gold_dir.exists():
        return ('ERROR', f'Gold directory not found: {gold_dir}')
    files = sorted(gold_dir.glob('*.parquet'))
    if not files:
        return ('ERROR', f'No parquet files in {gold_dir}')
    latest = max(files, key=lambda f: f.stat().st_mtime)
    age = datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
    if age.days > max_age_days:
        return ('WARN', f'Gold data is {age.days} days old (threshold: {max_age_days})')
    return ('OK', f'Gold data is {age.days} days old')
```

### Example 3: CI Gate in deploy-web.yml
```yaml
# Source: Pattern from weekly-pipeline.yml sanity check step
- name: Sanity check - validate data quality
  run: |
    python scripts/sanity_check_projections.py \
      --scoring half_ppr \
      --season 2026
  # Exit code 1 on CRITICAL -> blocks deployment
```

### Example 4: Roster Changes Log
```python
# Source: New addition to refresh_rosters.py
def log_changes(changes_df: pd.DataFrame, log_path: str = 'roster_changes.log'):
    """Append roster changes to a persistent log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_path, 'a') as f:
        f.write(f'\n--- Roster Refresh: {timestamp} ---\n')
        if changes_df.empty:
            f.write('No changes detected.\n')
        else:
            for _, row in changes_df.iterrows():
                f.write(
                    f"  {row['player_name']} ({row['position']}): "
                    f"{row.get('old_team', '?')} -> {row.get('new_team', '?')}"
                )
                if 'old_position' in row and 'new_position' in row:
                    f.write(f", pos: {row['old_position']} -> {row['new_position']}")
                f.write('\n')
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual roster updates | Daily Sleeper API refresh (D-01) | Existing in daily-sentiment.yml | Already implemented but only updates team, not position |
| FantasyPros public API | API now returns 403 | 2025-2026 | Must use Sleeper search_rank as primary live consensus source |
| Hardcoded consensus only | Live Sleeper + hardcoded fallback | This phase | More current consensus data for sanity checks |

**Deprecated/outdated:**
- FantasyPros public API endpoint (`api.fantasypros.com/public/v2/json/nfl/`) -- returns 403, requires auth token [VERIFIED: direct probe]
- CONSENSUS_TOP_50 in sanity_check_projections.py -- contains pre-2026-offseason team assignments (Davante Adams listed as NYJ, actually LAR) [VERIFIED: Sleeper API + Gold data]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FantasyPros API will continue to return 403 without auth | Common Pitfalls | If it starts working, the existing `fetch_fantasypros()` code would work immediately -- no code change needed, just a better data source |
| A2 | Sleeper search_rank is a reasonable proxy for expert consensus | Architecture Patterns | Could diverge significantly from ECR; mitigated by hardcoded CONSENSUS_TOP_50 fallback |
| A3 | The daily-sentiment.yml cron schedule (noon UTC) is adequate for roster refresh timing | Architecture Patterns | If rosters need to refresh at a different time, a separate cron could be added |

## Open Questions

1. **Should CONSENSUS_TOP_50 be auto-generated from Sleeper?**
   - What we know: The hardcoded list has stale team assignments. Sleeper search_rank is always current.
   - What's unclear: Whether Sleeper search_rank ordering matches actual expert consensus closely enough to serve as a replacement.
   - Recommendation: Keep hardcoded list as fallback (update manually for 2026 offseason), but use live Sleeper data as primary consensus source in sanity checks. Claude's discretion per CONTEXT.md.

2. **How to handle the FantasyPros 403 gracefully per D-09/D-10?**
   - What we know: D-09 says "live-fetch FantasyPros ECR." D-10 says fall back if fetch fails. The fetch will fail (403).
   - What's unclear: Whether the user expects us to find a workaround (e.g., HTML scraping with Selenium/Playwright) or just implement the fallback path.
   - Recommendation: Attempt the FantasyPros API call, catch the 403, log a warning, fall back to Sleeper live + hardcoded CONSENSUS_TOP_50. The existing `refresh_external_rankings.py` already has this pattern. Scraping would be fragile and ethically questionable.

3. **Should the CI gate be in deploy-web.yml or a separate workflow?**
   - What we know: D-07 says sanity check should be a CI gate before deploys. `deploy-web.yml` triggers on push to main with web/src paths.
   - What's unclear: Whether to add a step to the existing deploy workflow or create a separate "quality gate" workflow.
   - Recommendation: Add as an early step in `deploy-web.yml` -- simpler, fewer moving parts. Both deploy jobs (frontend and backend) should depend on the quality gate passing.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no config file; convention-based) |
| Config file | None -- pytest discovers tests/ automatically |
| Quick run command | `python -m pytest tests/test_data_quality.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DQAL-01 | Position update from Sleeper API | unit | `python -m pytest tests/test_data_quality.py::test_position_update -x` | Wave 0 |
| DQAL-01 | Name collision handling | unit | `python -m pytest tests/test_data_quality.py::test_name_collision_handling -x` | Wave 0 |
| DQAL-02 | Team update from Sleeper API | unit | `python -m pytest tests/test_data_quality.py::test_team_update -x` | Wave 0 |
| DQAL-02 | Roster changes logging | unit | `python -m pytest tests/test_data_quality.py::test_roster_changes_log -x` | Wave 0 |
| DQAL-03 | Sanity check <10 warnings | integration | `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` | Existing |
| DQAL-03 | Freshness check warns on stale data | unit | `python -m pytest tests/test_data_quality.py::test_freshness_check -x` | Wave 0 |
| DQAL-04 | Top 10 matches consensus structure | integration | `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` | Existing |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_data_quality.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green + sanity check script passes

### Wave 0 Gaps
- [ ] `tests/test_data_quality.py` -- covers DQAL-01, DQAL-02, DQAL-03 unit tests
- [ ] No conftest.py needed -- tests are self-contained with mock data

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Sleeper API is public, no auth needed |
| V3 Session Management | no | Batch scripts, no sessions |
| V4 Access Control | no | No user-facing access control changes |
| V5 Input Validation | yes | Validate Sleeper API response structure before applying changes |
| V6 Cryptography | no | No crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sleeper API returns corrupted data | Tampering | Validate response shape before writing to parquet; require all fantasy positions present |
| Malicious player name injection | Tampering | `_normalize_name()` strips special characters; parquet schema enforces column types |
| Stale cached rankings consumed as fresh | Information Disclosure | Cache age check (`_cache_is_fresh()` in external_rankings_service.py) |

## Sources

### Primary (HIGH confidence)
- Sleeper API (`https://api.sleeper.app/v1/players/nfl`) -- probed live; confirmed response format, position field, team abbreviations, name collision count [VERIFIED: API probe]
- `scripts/refresh_rosters.py` -- read full source; confirmed it only updates `recent_team`, not `position` [VERIFIED: codebase grep]
- `scripts/sanity_check_projections.py` -- read full source; confirmed CONSENSUS_TOP_50 structure, validation logic, exit code semantics [VERIFIED: codebase]
- `scripts/refresh_external_rankings.py` -- confirmed Sleeper/FP/ESPN fetcher with fallback pattern [VERIFIED: codebase]
- `web/api/services/external_rankings_service.py` -- confirmed cache logic, consensus fallback, comparison engine [VERIFIED: codebase]
- `.github/workflows/daily-sentiment.yml` -- confirmed roster refresh already runs daily as step 5 [VERIFIED: codebase]
- Gold parquet schema -- confirmed columns: player_id, position, player_name, recent_team, projected_season_points, overall_rank, position_rank (619 players, 19 columns) [VERIFIED: pandas read]

### Secondary (MEDIUM confidence)
- FantasyPros API status (403) -- confirmed via direct HTTP probe but could change [VERIFIED: requests.get probe]
- Sleeper team abbreviation mismatch (only LAR != LA) -- confirmed via full API scan [VERIFIED: API probe]
- Name collision count (36 among fantasy positions) -- confirmed via full API scan [VERIFIED: API probe]

### Tertiary (LOW confidence)
- None -- all findings verified via codebase or API probes.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and in use throughout the project
- Architecture: HIGH -- extending existing scripts with well-understood patterns
- Pitfalls: HIGH -- all pitfalls verified via direct API probes and codebase inspection

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (stable domain; Sleeper API unlikely to change significantly)
