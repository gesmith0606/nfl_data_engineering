# Phase 7: Tech Debt Cleanup - Research

**Researched:** 2026-03-08
**Domain:** Code hygiene / documentation gap closure
**Confidence:** HIGH

## Summary

Phase 7 addresses four independent, non-critical tech debt items surfaced by the v1.0 milestone audit. All four are small, well-scoped fixes with no architectural impact. The audit document (`.planning/v1.0-MILESTONE-AUDIT.md`) provides exact file paths, line numbers, and expected fixes for each item.

Every item has been verified by reading the actual source files. The fixes are straightforward single-file edits with no risk of regressions, and existing test infrastructure covers all affected code paths.

**Primary recommendation:** Execute all four fixes in a single plan with four tasks (one per item). Each task is a 1-3 line change in a single file.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PBP-01 | Full PBP ingested with ~80 curated columns including EPA, WPA, CPOE | Documentation gap only -- 02-01-SUMMARY.md already has `requirements-completed` frontmatter (line 43). Audit was wrong; this is already fixed. Verify and skip or ensure consistency. |
| PBP-02 | PBP processes one season at a time to manage memory | Same as PBP-01 -- documentation gap, frontmatter already present. |
| PBP-03 | PBP uses column subsetting via columns parameter | Same as PBP-01 -- documentation gap, frontmatter already present. |
| PBP-04 | PBP ingested for seasons 2010-2025 in Bronze layer | Same as PBP-01 -- documentation gap, frontmatter already present. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.9+ | Runtime | Project standard |
| pandas | installed | DataFrame operations | Already used everywhere |
| pyarrow | installed | Parquet I/O for test_generate_inventory.py | Already in venv (verified) |
| pytest | 8.4.1 | Test framework | Project standard |

No new dependencies needed. All fixes use existing project libraries.

## Architecture Patterns

### Fix Locations (4 independent items)

```
.planning/phases/02-core-pbp-ingestion/02-01-SUMMARY.md  # Item 1: frontmatter
src/nfl_data_integration.py:378                           # Item 2: hardcoded season
scripts/bronze_ingestion_simple.py:342-353                # Item 3: inline validation
tests/test_generate_inventory.py                          # Item 4: pyarrow dep
```

### Item 1: SUMMARY Frontmatter (ALREADY FIXED)

**Current state:** 02-01-SUMMARY.md line 43 already contains:
```yaml
requirements-completed: [PBP-01, PBP-02, PBP-03, PBP-04]
```

The audit flagged this as missing, but reading the file shows it is present. The audit's `completed_by_plans: []` field was the actual gap -- the audit metadata itself was stale, not the SUMMARY file.

**Action:** Verify the frontmatter is present (it is). If the planner wants to address the audit metadata, update the audit file's `completed_by_plans` fields. Otherwise, this item is a no-op.

**Confidence:** HIGH -- verified by reading the file directly.

### Item 2: Hardcoded Season Bound

**Current state:** `src/nfl_data_integration.py` line 378:
```python
invalid_seasons = [s for s in seasons if s < 1999 or s > 2025]
```

**Fix:** Import `get_max_season` from `src.config` and replace `2025` with `get_max_season()`:
```python
from src.config import get_max_season

# In validate_data(), line 378:
invalid_seasons = [s for s in seasons if s < 1999 or s > get_max_season()]
```

**Risk:** None. `get_max_season()` returns `datetime.now().year + 1` (currently 2027). The function already exists and is used throughout the project via `DATA_TYPE_SEASON_RANGES`.

**Confidence:** HIGH -- verified both the bug location and the fix function.

### Item 3: Unused format_validation_output()

**Current state:** `scripts/bronze_ingestion_simple.py` lines 342-353 inline validation formatting:
```python
val_result = adapter.validate_data(df, args.data_type)
if val_result:
    if val_result.get("issues"):
        for issue in val_result["issues"]:
            print(f"  Warning Validation: {issue}")
    else:
        col_count = val_result.get("column_count", len(df.columns))
        print(f"  Check Validation passed: {col_count}/{col_count} columns valid")
```

Meanwhile, `src/nfl_data_adapter.py` exports `format_validation_output()` (lines 18-38) which does exactly the same thing.

**Fix:** Replace the inline block with a call to `format_validation_output()`:
```python
from src.nfl_data_adapter import format_validation_output

# In main(), replace lines 345-352:
val_result = adapter.validate_data(df, args.data_type)
output = format_validation_output(val_result)
if output:
    print(output)
```

**Risk:** Very low. The function is already tested. The only difference is the function returns a single string vs printing line-by-line, but the output is identical.

**Confidence:** HIGH -- verified both the inline code and the helper function produce equivalent output.

### Item 4: pyarrow Test Collection

**Current state:** pyarrow IS installed in the venv (verified). The test file collects successfully (8 tests collected). This item appears to have been resolved already, possibly by a prior `pip install` or dependency pull.

**Action:** Verify pyarrow is in requirements/dependency files. If not, add it to ensure reproducibility. Run `pip freeze | grep pyarrow` to confirm version.

**Confidence:** HIGH -- verified by running `python -c "import pyarrow"` and `pytest --collect-only`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Season validation | Hardcoded year constants | `get_max_season()` from config.py | Already exists, dynamically computes current year + 1 |
| Validation output formatting | Inline print statements | `format_validation_output()` from nfl_data_adapter.py | Already exists, tested, DRY |

## Common Pitfalls

### Pitfall 1: Assuming Audit is Current
**What goes wrong:** The audit says SUMMARY frontmatter is missing, but it already exists in the file.
**Why it happens:** The audit was run at a point in time; the file may have been updated since.
**How to avoid:** Always verify the current file state before making changes. Read before writing.
**Warning signs:** Audit says "missing" but the file has the content.

### Pitfall 2: Import Cycle with get_max_season
**What goes wrong:** Adding `from src.config import get_max_season` to nfl_data_integration.py could create a circular import.
**Why it happens:** nfl_data_integration.py is imported by other modules that also import config.py.
**How to avoid:** Check existing imports in nfl_data_integration.py. The file already imports from `nfl_data_py` and `pandas` but not from `src.config`. Verify no circular dependency by running `python -c "from src.nfl_data_integration import NFLDataFetcher"` after the change.
**Warning signs:** ImportError at runtime.

### Pitfall 3: format_validation_output Import Path
**What goes wrong:** The CLI script uses `sys.path.insert` for imports. Need to ensure `format_validation_output` import works with that setup.
**How to avoid:** The script already imports from `src.nfl_data_adapter` (line 20: `from src.nfl_data_adapter import NFLDataAdapter`). Wait -- it actually imports `NFLDataAdapter` from the module. Just add `format_validation_output` to that import.
**Current import:** `from src.nfl_data_adapter import NFLDataAdapter` -- not present, adapter is instantiated directly. Check: the CLI uses `NFLDataAdapter()` on line 325 via `from src.nfl_data_adapter import NFLDataAdapter` on line 20.

## Code Examples

### Fix 2: Replace hardcoded season (nfl_data_integration.py)

```python
# At top of file, add import:
from src.config import get_max_season

# Line 378 change:
# Before:
invalid_seasons = [s for s in seasons if s < 1999 or s > 2025]
# After:
invalid_seasons = [s for s in seasons if s < 1999 or s > get_max_season()]
```

### Fix 3: Use format_validation_output (bronze_ingestion_simple.py)

```python
# Add to imports at top:
from src.nfl_data_adapter import format_validation_output

# Replace lines 343-353 with:
try:
    val_result = adapter.validate_data(df, args.data_type)
    output = format_validation_output(val_result)
    if output:
        print(output)
except Exception as e:
    print(f"  Warning Validation error: {e}")
```

## State of the Art

No technology changes relevant -- this is purely internal cleanup of existing code.

## Open Questions

1. **SUMMARY frontmatter already present -- is this a no-op?**
   - What we know: 02-01-SUMMARY.md line 43 already has `requirements-completed: [PBP-01, PBP-02, PBP-03, PBP-04]`
   - What's unclear: Whether the audit's `completed_by_plans: []` metadata also needs updating
   - Recommendation: Treat Item 1 as a verification step, not a code change. If the planner wants to update the audit file itself, that is optional cleanup.

2. **pyarrow already installed -- is this a no-op?**
   - What we know: `import pyarrow` succeeds, 8 tests collect fine
   - What's unclear: Whether pyarrow is in a requirements.txt or just installed ad-hoc
   - Recommendation: Verify it is in the project's dependency file. If not, add it.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.1 |
| Config file | pytest implicit (no pytest.ini found) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PBP-01 | SUMMARY frontmatter present | manual-only | Visual inspection of frontmatter YAML | N/A (already present) |
| PBP-02 | SUMMARY frontmatter present | manual-only | Visual inspection of frontmatter YAML | N/A (already present) |
| PBP-03 | SUMMARY frontmatter present | manual-only | Visual inspection of frontmatter YAML | N/A (already present) |
| PBP-04 | SUMMARY frontmatter present | manual-only | Visual inspection of frontmatter YAML | N/A (already present) |
| (INFRA-02) | Dynamic season bound | unit | `python -m pytest tests/test_infrastructure.py -x -q -k max_season` | Yes |
| (VAL-01) | format_validation_output used | unit | `python -m pytest tests/test_bronze_validation.py -x -q` | Yes |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. The format_validation_output function already has tests in test_bronze_validation.py. The get_max_season function already has tests in test_infrastructure.py. No new test files needed.

## Sources

### Primary (HIGH confidence)
- Direct file reads of all 4 affected files (verified current state)
- `.planning/v1.0-MILESTONE-AUDIT.md` (defines the 4 tech debt items)
- `src/config.py:180` (get_max_season function definition)
- `src/nfl_data_adapter.py:18-38` (format_validation_output function)
- `scripts/bronze_ingestion_simple.py:342-353` (inline validation logic)
- `src/nfl_data_integration.py:378` (hardcoded season bound)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing
- Architecture: HIGH - all fixes are 1-5 line changes in known files
- Pitfalls: HIGH - circular import is only real risk, easily verified

**Research date:** 2026-03-08
**Valid until:** Indefinite (internal code cleanup, no external dependencies)
