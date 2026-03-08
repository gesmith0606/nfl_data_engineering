# Phase 6: Wire Bronze Validation - Research

**Researched:** 2026-03-08
**Domain:** Python DataFrame validation wiring / integration plumbing
**Confidence:** HIGH

## Summary

This phase is pure integration plumbing -- connecting an existing `validate_data()` method (in `NFLDataFetcher`, `src/nfl_data_integration.py:303`) to the bronze ingestion pipeline (`scripts/bronze_ingestion_simple.py`). The validator already has rules for all 15 data types with required column checks and null percentage analysis. The ingestion script already fetches data and saves it. The gap is that validation is never called between fetch and save.

The implementation is straightforward: add a `validate_data()` delegation method to `NFLDataAdapter` (the ingestion script's single interface), then call it in the ingestion script after fetch, before save. Output is print-based warnings matching the existing CLI style. No new libraries, no architectural changes, no CLI flags.

**Primary recommendation:** Add ~15 lines to `nfl_data_adapter.py` (delegation method) and ~15 lines to `bronze_ingestion_simple.py` (call site + output formatting). Write integration tests that verify the wiring end-to-end.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Add `validate_data()` method to `NFLDataAdapter` that delegates to `NFLDataFetcher.validate_data()`
- Adapter instantiates NFLDataFetcher internally (lazy import) -- no DI, no validator parameter
- Ingestion script calls `adapter.validate_data(df, data_type)` -- single import, single object
- Summary line after fetch: check-mark `Validation passed: N/N columns valid`
- On issues: warning `Validation: 2 missing columns (air_yards, snap_pct)` -- list specific column names
- Fits existing print-based output style in bronze_ingestion_simple.py
- No new CLI flags -- validation always runs
- Failure = warning only, never blocks save (Bronze layer accepts raw data)
- When validate_data() has no rules for a data type, skip silently -- no output

### Claude's Discretion
- Exact validate_data() return value parsing (dict structure may vary)
- How to format the summary line when validation returns partial results
- Integration test structure and assertions

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VAL-01 | validate_data() in NFLDataFetcher supports all new data types with required column checks | This phase wires the existing VAL-01 implementation into the ingestion pipeline. The validator already exists and passes tests; this phase closes the integration gap identified in the v1.0 audit. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | DataFrame operations | Already used throughout project |
| pytest | existing | Test framework | Already used for 71+ tests |
| unittest.mock | stdlib | Mocking for integration tests | Already used in test_infrastructure.py |

### Supporting
No new libraries needed. This phase uses only existing project code.

## Architecture Patterns

### Recommended Changes

```
src/nfl_data_adapter.py        # +1 method: validate_data(df, data_type)
scripts/bronze_ingestion_simple.py  # +1 call site after fetch, before save
tests/test_bronze_validation.py     # New test file for integration tests
```

### Pattern 1: Delegation Method on NFLDataAdapter

**What:** A thin method that lazily imports NFLDataFetcher and delegates to its validate_data().
**When to use:** This is the established pattern -- NFLDataAdapter is the sole interface for ingestion.

**Example:**
```python
# In NFLDataAdapter class
def validate_data(self, df: pd.DataFrame, data_type: str) -> dict:
    """Validate DataFrame against schema rules for data_type.

    Args:
        df: DataFrame to validate.
        data_type: Registry key (e.g., 'schedules', 'pbp', 'ngs').

    Returns:
        Dict with 'is_valid', 'row_count', 'column_count', 'issues' keys.
        Returns None if no rules exist for the data type.
    """
    from src.nfl_data_integration import NFLDataFetcher
    fetcher = NFLDataFetcher()
    return fetcher.validate_data(df, data_type)
```

### Pattern 2: Call Site in Ingestion Loop

**What:** Insert validation call after `df = method(**kwargs)` and before `save_local(df, local_path)`.
**Where:** `bronze_ingestion_simple.py`, approximately line 340 (after the `Records: N  Columns: M` print).

**Example:**
```python
# After: print(f"  Records: {len(df):,}  Columns: {len(df.columns)}")
# Before: save_local(df, local_path)

result = adapter.validate_data(df, args.data_type)
if result and not result.get("issues"):
    total_cols = result.get("column_count", len(df.columns))
    print(f"  \u2713 Validation passed: {total_cols}/{total_cols} columns valid")
elif result and result.get("issues"):
    # Parse issues for missing columns specifically
    missing = [i for i in result["issues"] if "Missing required columns" in i]
    other = [i for i in result["issues"] if "Missing required columns" not in i]
    if missing:
        # Extract column names from the issue string
        print(f"  \u26a0 Validation: {missing[0]}")
    for issue in other:
        print(f"  \u26a0 {issue}")
# If result is None or data_type has no rules: skip silently
```

### Pattern 3: Output Format Matching Existing Style

**What:** The ingestion script uses print-based indented output. Validation output must match.
**Existing pattern from bronze_ingestion_simple.py:**
```
NFL Bronze Layer Ingestion
Data Type: schedules, Seasons: [2024], Week: 1
============================================================
  Records: 285  Columns: 22
  Saved locally: data/bronze/schedules/season=2024/schedules_20260308_143000.parquet
  Ingestion complete: 285 records -> data/bronze/...
```

**Validation output should insert as:**
```
  Records: 285  Columns: 22
  \u2713 Validation passed: 22/22 columns valid       <-- NEW
  Saved locally: data/bronze/...
```

Or on issues:
```
  Records: 285  Columns: 22
  \u26a0 Validation: Missing required columns: ['air_yards', 'snap_pct']  <-- NEW
  Saved locally: data/bronze/...                                          <-- still saves
```

### Anti-Patterns to Avoid
- **Blocking save on validation failure:** Bronze layer accepts raw data. Validation is advisory only.
- **Adding CLI flags for validation:** User decision is "always run, no flags."
- **Instantiating NFLDataFetcher at module level:** Use lazy import inside the method, matching existing adapter pattern.
- **Duplicating validation rules:** Delegate to NFLDataFetcher, do not copy rules into the adapter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Column validation | Custom column checker | NFLDataFetcher.validate_data() | Already has rules for all 15 types |
| Output formatting | Logging framework | print() with 2-space indent | Matches existing ingestion CLI style |

## Common Pitfalls

### Pitfall 1: validate_data() Return Structure
**What goes wrong:** The return dict from `NFLDataFetcher.validate_data()` has specific keys. Parsing incorrectly causes crashes.
**Why it happens:** The method returns `{'is_valid': bool, 'row_count': int, 'column_count': int, 'null_percentage': {}, 'issues': []}`. The `issues` list contains free-text strings.
**How to avoid:** Check for the `issues` key being a non-empty list. Do not rely on `is_valid` alone -- an empty DataFrame returns `is_valid: False` with issues `["DataFrame is empty"]`, but the ingestion script already handles empty DataFrames with a `continue` before reaching the validation call.
**Warning signs:** Validation printing "DataFrame is empty" for data that was already skipped.

### Pitfall 2: Data Types Without Rules
**What goes wrong:** If a data_type is not in the `required_columns` dict inside validate_data(), no column checking occurs, but the method still returns a result dict (with empty issues).
**Why it happens:** The method checks `if data_type in required_columns` -- unrecognized types just skip column checks.
**How to avoid:** The user decision says "skip silently when no rules." However, all 15 current data types DO have rules. The silent-skip behavior handles future additions gracefully. The result dict will have `is_valid: True` and empty `issues` for types without rules -- treat this as a pass, not a skip.

### Pitfall 3: NFLDataFetcher Constructor Side Effects
**What goes wrong:** `NFLDataFetcher.__init__()` sets `self.available_seasons` and logs. It may attempt network calls or fail on missing config.
**How to avoid:** Review the constructor. If it has heavy init, the adapter's `validate_data()` method should cache the fetcher instance or handle init errors gracefully. From the code: the constructor sets `self.available_seasons = list(range(1999, 2026))` -- this is lightweight and safe.

### Pitfall 4: Hardcoded Season Range in NFLDataFetcher
**What goes wrong:** `NFLDataFetcher` has `range(1999, 2026)` hardcoded for season validation in schedules. The `validate_data()` method also hardcodes `2025` in its season check: `if s < 1999 or s > 2025`.
**Why it matters:** This is a pre-existing issue, not something this phase introduces. The validate_data() will flag 2026 season data as having "invalid seasons" even though the adapter and config allow it.
**How to avoid:** Document this as a known limitation. Do NOT fix it in this phase -- it is out of scope. The warning is non-blocking, so it will just print an advisory message.

## Code Examples

### NFLDataFetcher.validate_data() Return Value (from source)

```python
# Source: src/nfl_data_integration.py:303-389
# Returns:
{
    'is_valid': True,          # bool
    'row_count': 285,          # int
    'column_count': 22,        # int
    'null_percentage': {       # dict[str, float]
        'game_id': 0.0,
        'season': 0.0,
        # ...
    },
    'issues': []               # list[str] -- empty = all good
}

# Example with issues:
{
    'is_valid': False,
    'row_count': 285,
    'column_count': 20,
    'null_percentage': { ... },
    'issues': [
        "Missing required columns: ['air_yards', 'snap_pct']",
        "High null percentage in weather_detail: 78.2%",
    ]
}
```

### Required Columns per Data Type (from source)

All 15 types have rules in `NFLDataFetcher.validate_data()`:
- schedules: game_id, season, week, home_team, away_team
- pbp: game_id, play_id, season, week
- teams: team_abbr, team_name
- player_weekly: player_id, season, week
- snap_counts: player_id, season, week
- injuries: season, week
- rosters: player_id, season
- player_seasonal: player_id, season
- ngs: season, season_type, week, player_display_name, player_position, team_abbr, player_gsis_id
- pfr_weekly: game_id, season, week, team, pfr_player_name, pfr_player_id
- pfr_seasonal: player, team, season, pfr_id
- qbr: season, season_type, qbr_total, pts_added, epa_total, qb_plays
- depth_charts: season, club_code, week, position, full_name, gsis_id
- draft_picks: season, round, pick, team, pfr_player_name, position
- combine: season, player_name, pos, school, ht, wt

### Existing Ingestion Flow (insertion point)

```python
# bronze_ingestion_simple.py lines 332-357 (current)
method = getattr(adapter, entry["adapter_method"])
kwargs = _build_method_kwargs(entry, args)
df = method(**kwargs)

if df.empty:
    print(f"  No data returned for season {season}.")
    continue

print(f"  Records: {len(df):,}  Columns: {len(df.columns)}")

# >>> VALIDATION GOES HERE <<<

# --- Build local path ---
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
# ... path building ...
save_local(df, local_path)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | tests/ directory, no pytest.ini (uses defaults) |
| Quick run command | `python -m pytest tests/test_bronze_validation.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VAL-01-wire | NFLDataAdapter.validate_data() delegates to NFLDataFetcher | unit | `python -m pytest tests/test_bronze_validation.py::TestAdapterValidation -x` | No -- Wave 0 |
| VAL-01-call | Ingestion calls validate_data() after fetch | unit | `python -m pytest tests/test_bronze_validation.py::TestIngestionValidation -x` | No -- Wave 0 |
| VAL-01-output-pass | Pass output: check-mark + column count | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_pass_output -x` | No -- Wave 0 |
| VAL-01-output-warn | Warn output: warning + specific columns | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_warn_output -x` | No -- Wave 0 |
| VAL-01-no-block | Validation warning does not prevent save | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_save_after_warning -x` | No -- Wave 0 |
| VAL-01-silent | No output for types without rules | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_silent_skip -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_bronze_validation.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_bronze_validation.py` -- new test file covering all VAL-01-wire behaviors
- No framework install needed -- pytest already present and configured

## Sources

### Primary (HIGH confidence)
- `src/nfl_data_integration.py:303-389` -- validate_data() implementation, return structure, all 15 data type rules
- `src/nfl_data_adapter.py` -- full adapter class, delegation pattern, lazy import pattern
- `scripts/bronze_ingestion_simple.py` -- full ingestion flow, call site at line 334, print output style
- `tests/test_infrastructure.py` -- existing test patterns for adapter mocking
- `.planning/v1.0-MILESTONE-AUDIT.md` -- integration gap documentation

### Secondary (MEDIUM confidence)
- None needed -- this is pure internal wiring with no external dependencies

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing code
- Architecture: HIGH -- single insertion point, clear delegation pattern, code fully read
- Pitfalls: HIGH -- all source code examined, return structures verified from implementation

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable -- internal wiring, no external dependencies)
