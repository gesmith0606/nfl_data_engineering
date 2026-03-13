# Phase 8: Pre-Backfill Guards - Research

**Researched:** 2026-03-09
**Domain:** Config hardening, dependency pinning, rate-limit protection
**Confidence:** HIGH

## Summary

Phase 8 is a small config/infrastructure phase with three requirements. Two are straightforward (SETUP-01 injury cap, SETUP-03 dependency pins). The third (SETUP-02 GITHUB_TOKEN) requires a nuanced approach because nfl-data-py v0.3.3 does NOT natively use GITHUB_TOKEN -- it calls `pandas.read_parquet()` and `pandas.read_csv()` with raw GitHub URLs, which make unauthenticated HTTP requests regardless of environment variables.

However, GitHub tightened rate limits for unauthenticated requests in May 2025, affecting `raw.githubusercontent.com` downloads. Since nfl-data-py fetches QBR, officials, and several CSV datasets from raw.githubusercontent.com, bulk backfill runs could hit rate limits. The practical solution is to set GITHUB_TOKEN in .env for other GitHub tooling (gh CLI, GitHub Actions) and document that nfl-data-py itself does not use it, but the token protects adjacent tooling during the backfill workflow.

**Primary recommendation:** Implement all three guards as config-only changes -- injury lambda cap, requirements.txt comments, and GITHUB_TOKEN in .env -- with a test for the injury cap. Document the GITHUB_TOKEN limitation honestly in a code comment.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Injury season cap: Static lambda in DATA_TYPE_SEASON_RANGES: `"injuries": (2009, lambda: 2024)` -- simple, explicit
- validate_season_for_type() already wired into bronze_ingestion_simple.py, so this automatically causes graceful skips
- GITHUB_TOKEN: Environment variable only -- set in .env (already gitignored)
- python-dotenv already a dependency and load_dotenv() already called
- No startup validation or hard blocking for GITHUB_TOKEN
- Dependency pinning: nfl_data_py==0.3.3 and numpy==1.26.4 are ALREADY pinned
- Verify pins exist and add inline comments explaining why
- No constraint file or lock file

### Claude's Discretion
- Whether to add a brief comment block at the top of requirements.txt explaining pinning strategy
- Test structure for verifying the injury season cap works as expected

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SETUP-01 | Config caps injury season range at 2024 | Change line 201 of config.py: replace `get_max_season` with `lambda: 2024`. Existing validate_season_for_type() + bronze_ingestion_simple.py wiring means this works immediately. |
| SETUP-02 | GITHUB_TOKEN configured for nfl-data-py downloads | Token goes in .env. CRITICAL FINDING: nfl-data-py v0.3.3 does NOT use GITHUB_TOKEN -- pandas HTTP calls are unauthenticated. Token protects gh CLI and GitHub Actions only. Document this limitation. |
| SETUP-03 | nfl-data-py version pinned in requirements | Already pinned at exact versions. Add inline comments explaining why (numpy 2.x breaks pandas 1.5.3, nfl-data-py archived Sept 2025). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nfl_data_py | 0.3.3 | NFL data fetching | Pinned -- archived Sept 2025, no newer version |
| numpy | 1.26.4 | Numeric operations | Pinned -- numpy 2.x breaks pandas 1.5.3 |
| pandas | 1.5.3 | DataFrame operations | Existing project dependency |
| python-dotenv | 1.1.1 | .env loading | Already used, load_dotenv() called in scripts |
| pytest | 8.4.1 | Testing | Existing test framework |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| nfl_data_py | nflreadpy 0.1.5 | Successor, but experimental, requires Python 3.10+, out of scope per REQUIREMENTS.md |

## Architecture Patterns

### Change Targets (3 files + .env)

```
src/config.py                  # Line 201: injuries lambda cap
requirements.txt               # Lines 38-39: add comments to existing pins
.env                           # Add GITHUB_TOKEN (already gitignored)
tests/test_infrastructure.py   # Add injury cap test
```

### Pattern: Static Lambda for Discontinued Data Source
**What:** Replace dynamic `get_max_season` callable with `lambda: 2024` for injury data
**When to use:** When a data source is permanently discontinued at a known date
**Example:**
```python
# Source: src/config.py line 195-211
DATA_TYPE_SEASON_RANGES: Dict[str, Tuple[int, Callable[[], int]]] = {
    # ... other types use get_max_season ...
    "injuries": (2009, lambda: 2024),  # nflverse discontinued injury data after 2024
}
```

**Why lambda, not literal int:** The tuple schema is `(int, Callable[[], int])`. All entries must return a callable for the max bound. Using `lambda: 2024` preserves the interface contract so `validate_season_for_type()` can call `max_season_fn()` uniformly.

### Pattern: Inline Pin Comments in requirements.txt
**What:** Add `# reason` comments after pinned versions
**Example:**
```
nfl_data_py==0.3.3    # pinned: archived Sept 2025, last stable release
numpy==1.26.4         # pinned: numpy 2.x breaks pandas 1.5.3 (ABI incompatibility)
```

### Anti-Patterns to Avoid
- **Do NOT add startup validation for GITHUB_TOKEN:** The context decision explicitly says no startup validation or hard blocking.
- **Do NOT modify nfl-data-py source code:** The library is archived. Accept its limitations.
- **Do NOT create a pip constraint file:** Context says exact pins are sufficient.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Season validation | Custom if/elif checks | `validate_season_for_type()` in config.py | Already wired into bronze_ingestion_simple.py |
| .env loading | Manual os.getenv wrappers | python-dotenv `load_dotenv()` | Already in use project-wide |

## Common Pitfalls

### Pitfall 1: Assuming GITHUB_TOKEN Helps nfl-data-py
**What goes wrong:** Setting GITHUB_TOKEN and believing nfl-data-py downloads are now authenticated.
**Why it happens:** nfl-data-py v0.3.3 calls `pandas.read_parquet(url)` and `pandas.read_csv(url)` directly. Pandas uses urllib/fsspec under the hood, which does NOT read GITHUB_TOKEN from the environment.
**How to avoid:** Document this limitation clearly. The token protects gh CLI usage and GitHub Actions workflows, not nfl-data-py bulk downloads. For bulk backfill, rate limiting risk is mitigated by nfl-data-py's one-season-at-a-time loop (natural throttling).
**Warning signs:** HTTP 429 errors during bulk downloads (especially QBR and other raw.githubusercontent.com sources).

### Pitfall 2: Breaking the Callable Interface
**What goes wrong:** Using `"injuries": (2009, 2024)` (int instead of callable).
**Why it happens:** Forgetting the tuple schema is `(int, Callable[[], int])`.
**How to avoid:** Use `lambda: 2024`. Test that `validate_season_for_type("injuries", 2025)` returns False.

### Pitfall 3: Forgetting the Existing Test for max_year Validation
**What goes wrong:** test_validate_edge_max_year in test_infrastructure.py asserts ALL types are valid at get_max_season(). After capping injuries at 2024, this test will FAIL for injuries if get_max_season() > 2024.
**Why it happens:** The test iterates all DATA_TYPE_SEASON_RANGES entries and checks max year.
**How to avoid:** Update test_validate_edge_max_year to handle types with static caps, or add an injury-specific test and exclude injuries from the generic max-year test.

### Pitfall 4: GITHUB_PERSONAL_ACCESS_TOKEN vs GITHUB_TOKEN
**What goes wrong:** The .env already has `GITHUB_PERSONAL_ACCESS_TOKEN` set, but the conventional name for GitHub API rate limits is `GITHUB_TOKEN`.
**How to avoid:** Add `GITHUB_TOKEN` as the canonical variable. Keep the existing `GITHUB_PERSONAL_ACCESS_TOKEN` for backward compatibility (used by some GitHub CLI configs).

## Code Examples

### Injury Season Cap (config.py line 201)

```python
# Current:
"injuries": (2009, get_max_season),

# Change to:
"injuries": (2009, lambda: 2024),  # nflverse discontinued injury data after 2024
```

### Requirements.txt Pin Comments (lines 38-39)

```
nfl_data_py==0.3.3    # pinned: archived Sept 2025, last stable release
numpy==1.26.4         # pinned: numpy 2.x breaks pandas 1.5.3 (ABI incompatibility)
```

### .env Addition

```bash
# GitHub token for API rate limits (5000 req/hr vs 60 unauthenticated)
# Note: nfl-data-py v0.3.3 does NOT use this token for its downloads
GITHUB_TOKEN=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
```

### Test for Injury Cap

```python
def test_injury_season_capped_at_2024(self):
    """Injuries data discontinued after 2024 -- seasons > 2024 should be invalid."""
    assert validate_season_for_type("injuries", 2024) is True
    assert validate_season_for_type("injuries", 2025) is False
    assert validate_season_for_type("injuries", 2009) is True
```

### Updating Existing Max-Year Test

```python
def test_validate_edge_max_year(self):
    """Max year (get_max_season()) should be valid for types with dynamic bounds."""
    max_s = get_max_season()
    # Types with static caps have their own dedicated tests
    static_cap_types = {"injuries"}
    for dtype in DATA_TYPE_SEASON_RANGES:
        if dtype in static_cap_types:
            continue
        assert validate_season_for_type(dtype, max_s) is True, (
            f"{dtype} should be valid at max year {max_s}"
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| nfl_data_py active | nfl_data_py archived | Sept 2025 | No new releases; pin at 0.3.3 |
| Unauthenticated GitHub OK | Rate limits tightened | May 2025 | raw.githubusercontent.com downloads may fail under bulk load |
| nflreadr (R) only | nflreadpy (Python) available | Nov 2025 | Future migration path, requires Python 3.10+ |

**Deprecated/outdated:**
- nfl_data_py: Archived Sept 2025. Pinned at 0.3.3. Successor is nflreadpy but requires Python 3.10+ (out of scope).

## Open Questions

1. **Rate limiting during bulk backfill**
   - What we know: nfl-data-py downloads from raw.githubusercontent.com are unauthenticated. GitHub tightened limits May 2025.
   - What's unclear: Exact rate limits for release asset downloads vs raw.githubusercontent.com. Release assets redirect to objects.githubusercontent.com CDN which may have separate limits.
   - Recommendation: During Phase 10 backfill, if HTTP 429 errors occur, add `time.sleep()` between season iterations. This is a Phase 10 concern, not Phase 8.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | none (uses defaults) |
| Quick run command | `python -m pytest tests/test_infrastructure.py -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETUP-01 | Injuries capped at 2024, season 2025 rejected | unit | `python -m pytest tests/test_infrastructure.py::TestDynamicSeasonValidation::test_injury_season_capped_at_2024 -x` | Wave 0 |
| SETUP-01 | Existing max-year test updated to exclude static-cap types | unit | `python -m pytest tests/test_infrastructure.py::TestDynamicSeasonValidation::test_validate_edge_max_year -x` | Exists (needs update) |
| SETUP-02 | GITHUB_TOKEN present in .env | manual-only | Manual: verify `grep GITHUB_TOKEN .env` | N/A (config file, not code) |
| SETUP-03 | nfl_data_py and numpy pins verified with comments | manual-only | Manual: verify `grep -E 'nfl_data_py|numpy' requirements.txt` | N/A (config file, not code) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_infrastructure.py -v -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_infrastructure.py::test_injury_season_capped_at_2024` -- covers SETUP-01
- [ ] Update `tests/test_infrastructure.py::test_validate_edge_max_year` -- exclude static-cap types to prevent false failure

## Sources

### Primary (HIGH confidence)
- nfl_data_py v0.3.3 source code at `venv/lib/python3.9/site-packages/nfl_data_py/__init__.py` -- verified no GITHUB_TOKEN usage, confirmed download URL patterns
- `src/config.py` lines 195-233 -- verified DATA_TYPE_SEASON_RANGES schema and validate_season_for_type() implementation
- `requirements.txt` lines 38-39 -- confirmed nfl_data_py==0.3.3 and numpy==1.26.4 already pinned
- `tests/test_infrastructure.py` -- verified existing test_validate_edge_max_year will break after injury cap
- `.env` -- confirmed GITHUB_PERSONAL_ACCESS_TOKEN exists but GITHUB_TOKEN does not

### Secondary (MEDIUM confidence)
- [GitHub changelog: Updated rate limits for unauthenticated requests (May 2025)](https://github.blog/changelog/2025-05-08-updated-rate-limits-for-unauthenticated-requests/) -- tightened limits on raw.githubusercontent.com
- [nfl_data_py archived Sept 2025](https://github.com/nflverse/nfl_data_py) -- confirmed repository is read-only
- [nflreadpy v0.1.5](https://github.com/nflverse/nflreadpy) -- experimental successor, Python 3.10+ required

### Tertiary (LOW confidence)
- GitHub release asset downloads (objects.githubusercontent.com CDN) may have different rate limits than raw.githubusercontent.com -- not officially documented

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - verified installed versions and pinned requirements directly
- Architecture: HIGH - read all change-target files, verified existing wiring
- Pitfalls: HIGH - discovered critical GITHUB_TOKEN non-usage through source code inspection and existing test breakage through test analysis

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable -- archived library, config-only changes)
