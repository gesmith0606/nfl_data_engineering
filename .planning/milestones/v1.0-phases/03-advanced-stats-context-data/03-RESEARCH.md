# Phase 3: Advanced Stats & Context Data - Research

**Researched:** 2026-03-08
**Domain:** Bronze ingestion of NGS, PFR, QBR, depth charts, draft picks, combine data via nfl-data-py
**Confidence:** HIGH

## Summary

Phase 3 is a straightforward extension of the existing Bronze ingestion infrastructure built in Phases 1-2. All 7 new adapter fetch methods already exist in `NFLDataAdapter`, all 7 registry entries exist in `DATA_TYPE_REGISTRY`, season validation ranges are configured, and the CLI dispatch works without code changes. The remaining work is: (1) add required-column validation entries to `NFLDataFetcher.validate_data()`, (2) fix a QBR frequency gap in `_build_method_kwargs`, and (3) write tests.

The actual nfl-data-py API signatures, column schemas, and season ranges have been verified by calling each function against 2024 data. Column schemas vary significantly across sub-types (NGS passing has 29 columns, NGS rushing has 22, PFR weekly pass has 24, etc.), so validation should use a common-column approach per data type family rather than per sub-type.

**Primary recommendation:** Execute the 7 ingestion runs (with sub-type loops for NGS and PFR), add validation rules to `validate_data()`, fix QBR frequency handling in `_build_method_kwargs`, and write one test file covering all new data types following the `test_pbp_ingestion.py` mock pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all decisions delegated to Claude's discretion.

### Claude's Discretion
All implementation decisions delegated to Claude. User trusts best judgment on:

**Season ranges:** Use requirements as-is (NGS: 2016-2025, PFR: 2018-2025, QBR: 2006-2025, depth charts: 2020-2025, draft picks: 2000-2025, combine: 2000-2025). Config already has correct min years. No need to go deeper than specified -- these ranges match data availability and ML training needs.

**QBR frequency:** Ingest both weekly and seasonal. Store as separate ingestion runs (same bronze path `qbr/season=YYYY/` but distinguish via filename: `qbr_weekly_{ts}.parquet` and `qbr_seasonal_{ts}.parquet`). Adapter already supports `frequency` param.

**Validation strictness:** Practical approach -- required column checks (must-have columns per type) + non-empty DataFrame check + season column presence. No row count thresholds or null % checks at Bronze level (that's Silver's job). Keep it simple and extensible.

**Ingestion order & batching:** No special ordering -- all types are independent. Use existing `--seasons` batch flag per type. A convenience wrapper script or `--data-type all` flag is nice-to-have but not required. Sequential runs are fine -- total data is small (~50MB across all types).

**Storage conventions:** Same as Phase 2 -- per-season files, timestamped, snappy compression. Sub-type data types (NGS, PFR) already have correct bronze_path patterns with `{sub_type}` in registry.

**Test coverage:** 1 test per data type minimum (VAL-03). Mock nfl-data-py calls to avoid API dependency. Test that adapter methods exist, accept correct params, and return DataFrames. Test that validate_data() catches missing required columns.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ADV-01 | NGS data ingested for 3 stat types (passing, rushing, receiving) for seasons 2016-2025 | Adapter `fetch_ngs` verified working; columns documented; registry entry with sub_types exists |
| ADV-02 | PFR weekly stats ingested for 4 sub-types (pass, rush, rec, def) for seasons 2018-2025 | Adapter `fetch_pfr_weekly` verified; all 4 sub-type column schemas documented |
| ADV-03 | PFR seasonal stats ingested for 4 sub-types for seasons 2018-2025 | Adapter `fetch_pfr_seasonal` verified; column schema documented |
| ADV-04 | QBR data ingested (weekly + seasonal) for seasons 2006-2025 | Adapter `fetch_qbr` verified; frequency param works; BUT `_build_method_kwargs` hardcodes `frequency="weekly"` -- needs fix for seasonal |
| ADV-05 | Depth charts ingested for seasons 2020-2025 | Adapter `fetch_depth_charts` verified; 15 columns documented; NOTE: config has min_season=2001 but requirement says 2020-2025 -- use requirement range |
| CTX-01 | Draft picks data ingested for seasons 2000-2025 | Adapter `fetch_draft_picks` verified; 35 columns with career stats |
| CTX-02 | Combine data ingested for seasons 2000-2025 | Adapter `fetch_combine` verified; 18 columns including physical measurements |
| VAL-01 | validate_data() supports all new data types with required column checks | Current `validate_data()` has 8 entries; needs 7 new entries with verified column names |
| VAL-02 | All new fetch methods have error handling for API timeouts and empty responses | Already handled by adapter `_safe_call()` wrapper -- returns empty DataFrame on any exception |
| VAL-03 | Tests added for new fetch methods (minimum 1 per data type) | Test pattern established in `test_pbp_ingestion.py` and `test_infrastructure.py`; mock `_import_nfl` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nfl-data-py | installed | Data source for all 7 new data types | Already the project's sole data provider; all import_* functions verified |
| pandas | installed | DataFrame processing | Already used throughout project |
| pyarrow | installed | Parquet serialization | Already used for Bronze storage |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | installed | Test framework | All new tests |
| unittest.mock | stdlib | Mock nfl-data-py calls | Test isolation from API |

### Alternatives Considered
None -- this phase uses the existing stack exclusively.

**Installation:** No new packages needed.

## Architecture Patterns

### Existing Structure (No Changes Needed)
```
src/
├── config.py                  # DATA_TYPE_SEASON_RANGES (already has all 15 types)
├── nfl_data_adapter.py        # NFLDataAdapter (already has all 15 fetch methods)
├── nfl_data_integration.py    # NFLDataFetcher.validate_data() (NEEDS 7 new entries)
scripts/
├── bronze_ingestion_simple.py # DATA_TYPE_REGISTRY (already has all 15 entries)
tests/
├── test_advanced_ingestion.py # NEW: tests for all 7 data types
data/bronze/
├── ngs/{stat_type}/season=YYYY/  # NEW directories
├── pfr/weekly/{sub_type}/season=YYYY/
├── pfr/seasonal/{sub_type}/season=YYYY/
├── qbr/season=YYYY/
├── depth_charts/season=YYYY/
├── draft_picks/season=YYYY/
├── combine/season=YYYY/
```

### Pattern 1: Registry Dispatch (Already Implemented)
**What:** CLI dispatches to adapter methods via DATA_TYPE_REGISTRY without if/elif
**When to use:** Every new data type ingestion
**Status:** Already works for all 7 new types -- no code changes needed for basic ingestion

### Pattern 2: Sub-type Iteration for NGS/PFR
**What:** For data types with sub_types, run one ingestion per sub-type
**When to use:** NGS (3 sub-types), PFR weekly (4), PFR seasonal (4)
**Example:**
```bash
# NGS: 3 stat types x seasons
python scripts/bronze_ingestion_simple.py --data-type ngs --sub-type passing --seasons 2016-2025
python scripts/bronze_ingestion_simple.py --data-type ngs --sub-type rushing --seasons 2016-2025
python scripts/bronze_ingestion_simple.py --data-type ngs --sub-type receiving --seasons 2016-2025
```

### Pattern 3: QBR Dual Frequency
**What:** QBR needs both weekly and seasonal ingestion runs
**Current gap:** `_build_method_kwargs` hardcodes `frequency="weekly"` -- needs a mechanism for seasonal
**Options:**
1. Add `--frequency` CLI arg (clean, explicit)
2. Store QBR weekly and seasonal as separate filenames in same directory per CONTEXT.md decision

### Anti-Patterns to Avoid
- **Fetching all seasons at once for large datasets:** Already handled -- CLI loops one season at a time
- **Custom column validation per sub-type:** Overkill for Bronze -- use common columns shared across sub-types (e.g., `season` appears in all NGS variants)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Season validation | Custom range checks | `validate_season_for_type()` from config.py | Already handles all 15 types with dynamic upper bound |
| Error handling | Custom try/except per fetch | `_safe_call()` in NFLDataAdapter | Catches all exceptions, logs, returns empty DataFrame |
| Sub-type dispatch | if/elif on sub-type names | Registry `sub_types` field + `_build_method_kwargs()` | Already dispatches stat_type/s_type correctly |
| Local file save | Custom os.makedirs + write | `save_local()` in bronze_ingestion_simple.py | Creates directories, writes parquet |

## Common Pitfalls

### Pitfall 1: QBR frequency hardcoded to "weekly"
**What goes wrong:** `_build_method_kwargs` always passes `frequency="weekly"` for QBR, so seasonal QBR can never be ingested via CLI
**Why it happens:** Phase 1 only implemented the default case
**How to avoid:** Add `--frequency` arg to CLI or use a QBR-specific sub-type mechanism
**Warning signs:** Only qbr_weekly files appear in data/bronze/qbr/

### Pitfall 2: Depth chart season range mismatch
**What goes wrong:** Config has `depth_charts` min_season=2001, but requirement ADV-05 says 2020-2025
**Why it happens:** Config reflects nfl-data-py data availability (2001+), requirement reflects what's needed for ML
**How to avoid:** Use `--seasons 2020-2025` when running ingestion (config allows it; no code change needed)
**Warning signs:** Not a code issue -- just a documentation/usage note

### Pitfall 3: QBR filename collision
**What goes wrong:** Weekly and seasonal QBR saved to same directory with same filename pattern `qbr_{ts}.parquet`
**Why it happens:** Registry has single `bronze_path: "qbr/season={season}"` for both frequencies
**How to avoid:** CONTEXT.md decision says use distinct filenames: `qbr_weekly_{ts}.parquet` and `qbr_seasonal_{ts}.parquet`
**Warning signs:** Files overwrite each other or can't distinguish weekly vs seasonal at read time

### Pitfall 4: PFR weekly columns differ significantly between sub-types
**What goes wrong:** Validation fails because pass-specific columns don't exist in rush data
**Why it happens:** PFR sub-types have very different schemas (pass: 24 cols, rush: 16 cols, rec: 17 cols, def: 29 cols)
**How to avoid:** Validate only common columns shared across all sub-types: `['season', 'week', 'pfr_player_id', 'team']`

## Code Examples

### Verified Column Schemas (from nfl-data-py 2024 data)

#### NGS Columns (common across all 3 stat types)
```python
# Common to passing, rushing, receiving:
NGS_REQUIRED_COLUMNS = ['season', 'season_type', 'week', 'player_display_name',
                        'player_position', 'team_abbr', 'player_gsis_id']
```

#### NGS Passing (29 columns)
```python
# Unique: avg_time_to_throw, avg_completed_air_yards, avg_intended_air_yards,
#         aggressiveness, completion_percentage_above_expectation, passer_rating, etc.
```

#### NGS Rushing (22 columns)
```python
# Unique: efficiency, avg_time_to_los, rush_yards_over_expected,
#         rush_yards_over_expected_per_att, expected_rush_yards, etc.
```

#### NGS Receiving (23 columns)
```python
# Unique: avg_cushion, avg_separation, catch_percentage,
#         avg_yac_above_expectation, percent_share_of_intended_air_yards, etc.
```

#### PFR Weekly Columns (common across all 4 sub-types)
```python
PFR_WEEKLY_REQUIRED_COLUMNS = ['game_id', 'season', 'week', 'team',
                                'pfr_player_name', 'pfr_player_id']
```

#### PFR Seasonal Columns (verified for pass sub-type)
```python
PFR_SEASONAL_REQUIRED_COLUMNS = ['player', 'team', 'season', 'pfr_id']
```

#### QBR Columns
```python
# Weekly (30 columns):
QBR_REQUIRED_COLUMNS = ['season', 'season_type', 'qbr_total', 'pts_added',
                        'epa_total', 'qb_plays']
# Note: weekly has 'game_id', 'game_week'; seasonal has 'game_week' only
```

#### Depth Charts (15 columns)
```python
DEPTH_CHARTS_REQUIRED_COLUMNS = ['season', 'club_code', 'week', 'position',
                                  'depth_team', 'full_name', 'gsis_id']
```

#### Draft Picks (35 columns)
```python
DRAFT_PICKS_REQUIRED_COLUMNS = ['season', 'round', 'pick', 'team',
                                 'pfr_player_name', 'position']
```

#### Combine (18 columns)
```python
COMBINE_REQUIRED_COLUMNS = ['season', 'player_name', 'pos', 'school',
                            'ht', 'wt']
```

### validate_data() Extension Pattern
```python
# In NFLDataFetcher.validate_data(), add to required_columns dict:
required_columns = {
    # ... existing 8 entries ...
    'ngs': ['season', 'season_type', 'week', 'player_display_name',
            'player_position', 'team_abbr', 'player_gsis_id'],
    'pfr_weekly': ['game_id', 'season', 'week', 'team',
                   'pfr_player_name', 'pfr_player_id'],
    'pfr_seasonal': ['player', 'team', 'season', 'pfr_id'],
    'qbr': ['season', 'season_type', 'qbr_total', 'pts_added',
            'epa_total', 'qb_plays'],
    'depth_charts': ['season', 'club_code', 'week', 'position',
                     'full_name', 'gsis_id'],
    'draft_picks': ['season', 'round', 'pick', 'team',
                    'pfr_player_name', 'position'],
    'combine': ['season', 'player_name', 'pos', 'school',
                'ht', 'wt'],
}
```

### Test Pattern (from test_pbp_ingestion.py)
```python
from unittest.mock import patch, MagicMock
import pandas as pd
from src.nfl_data_adapter import NFLDataAdapter

@patch.object(NFLDataAdapter, "_import_nfl")
def test_fetch_ngs_returns_dataframe(mock_import_nfl):
    mock_nfl = MagicMock()
    mock_nfl.import_ngs_data.return_value = pd.DataFrame({
        "season": [2024], "player_display_name": ["Player A"],
        "player_gsis_id": ["00-001"], "team_abbr": ["KC"],
    })
    mock_import_nfl.return_value = mock_nfl

    adapter = NFLDataAdapter()
    df = adapter.fetch_ngs([2024], stat_type="passing")
    assert not df.empty
    mock_nfl.import_ngs_data.assert_called_once()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| if/elif CLI dispatch | Registry dispatch | Phase 1 | Adding new types is config-only |
| Direct nfl-data-py imports | NFLDataAdapter isolation | Phase 1 | Future nflreadpy migration is single-module change |
| S3-first storage | Local-first with --s3 opt-in | Phase 1 | Works without AWS credentials |

**No deprecated/outdated items in this domain.**

## Open Questions

1. **QBR frequency CLI mechanism**
   - What we know: `_build_method_kwargs` hardcodes `frequency="weekly"`; adapter supports `frequency` param
   - What's unclear: Best CLI UX for dual frequency (new `--frequency` arg vs treating as sub-type)
   - Recommendation: Add `--frequency` arg to CLI; simpler than overloading sub-type. Also update filename to include frequency: `qbr_weekly_{ts}.parquet` / `qbr_seasonal_{ts}.parquet`

2. **PFR seasonal column schema for non-pass sub-types**
   - What we know: Verified pass sub-type columns. Rush/rec/def seasonal may differ.
   - What's unclear: Exact columns for pfr_seasonal rush/rec/def
   - Recommendation: Use conservative common columns (`player`, `team`, `season`, `pfr_id`) for validation. LOW risk -- these are clearly shared across all PFR data.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed) |
| Config file | None (default pytest discovery) |
| Quick run command | `python -m pytest tests/test_advanced_ingestion.py -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADV-01 | NGS fetch returns DataFrame for each stat_type | unit | `python -m pytest tests/test_advanced_ingestion.py::TestNGSIngestion -x` | No -- Wave 0 |
| ADV-02 | PFR weekly fetch returns DataFrame for each s_type | unit | `python -m pytest tests/test_advanced_ingestion.py::TestPFRWeeklyIngestion -x` | No -- Wave 0 |
| ADV-03 | PFR seasonal fetch returns DataFrame for each s_type | unit | `python -m pytest tests/test_advanced_ingestion.py::TestPFRSeasonalIngestion -x` | No -- Wave 0 |
| ADV-04 | QBR fetch works for both weekly and seasonal frequency | unit | `python -m pytest tests/test_advanced_ingestion.py::TestQBRIngestion -x` | No -- Wave 0 |
| ADV-05 | Depth charts fetch returns DataFrame | unit | `python -m pytest tests/test_advanced_ingestion.py::TestDepthChartsIngestion -x` | No -- Wave 0 |
| CTX-01 | Draft picks fetch returns DataFrame | unit | `python -m pytest tests/test_advanced_ingestion.py::TestDraftPicksIngestion -x` | No -- Wave 0 |
| CTX-02 | Combine fetch returns DataFrame | unit | `python -m pytest tests/test_advanced_ingestion.py::TestCombineIngestion -x` | No -- Wave 0 |
| VAL-01 | validate_data() accepts all 7 new types and catches missing columns | unit | `python -m pytest tests/test_advanced_ingestion.py::TestValidation -x` | No -- Wave 0 |
| VAL-02 | Adapter _safe_call handles errors gracefully | unit | Covered by existing `test_infrastructure.py` | Yes |
| VAL-03 | At least 1 test per new data type | unit | `python -m pytest tests/test_advanced_ingestion.py -v` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_advanced_ingestion.py -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_advanced_ingestion.py` -- covers ADV-01 through ADV-05, CTX-01, CTX-02, VAL-01, VAL-03
- No framework install needed -- pytest already available
- No conftest needed -- tests are self-contained with unittest.mock

## Sources

### Primary (HIGH confidence)
- nfl-data-py installed library -- all function signatures verified via `inspect.signature()` and `help()`
- nfl-data-py API calls -- all 7 data types fetched against 2024 data to verify column schemas
- Existing codebase -- `src/nfl_data_adapter.py`, `src/config.py`, `scripts/bronze_ingestion_simple.py`, `src/nfl_data_integration.py` read and analyzed
- Existing tests -- `tests/test_pbp_ingestion.py`, `tests/test_infrastructure.py` patterns documented

### Secondary (MEDIUM confidence)
- PFR seasonal columns verified only for pass sub-type; rush/rec/def assumed to share common columns (`player`, `team`, `season`, `pfr_id`)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all existing code verified
- Architecture: HIGH - no structural changes, extending existing patterns
- Pitfalls: HIGH - verified by reading actual code and testing API calls
- Column schemas: HIGH for 6/7 types (verified), MEDIUM for PFR seasonal non-pass sub-types

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable domain, nfl-data-py updates are seasonal)
