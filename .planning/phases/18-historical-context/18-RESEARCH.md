# Phase 18: Historical Context - Research

**Researched:** 2026-03-15
**Domain:** NFL Combine measurables + Draft capital dimension table (Silver layer)
**Confidence:** HIGH

## Summary

Phase 18 creates a static Silver dimension table joining NFL Combine measurables (2000-2025) with draft capital via the Jimmy Johnson trade value chart. Both Bronze data sources already exist locally with 26 seasons each (8,649 combine rows, 6,644 draft pick rows). The join key is `pfr_id` (combine) to `pfr_player_id` (draft_picks), with 5,384 players overlapping, 1,771 combine-only (UDFAs who attended the combine), and 1,004 draft-only (drafted players who skipped the combine). The output is a single flat Parquet file at `data/silver/players/historical/combine_draft_profiles.parquet`.

The core technical challenges are: (1) handling 17 duplicate `pfr_id` values in the combine data (different players sharing the same PFR ID across different seasons), (2) extending the Jimmy Johnson chart beyond pick 224 to cover compensatory picks up to 262, and (3) computing position-percentile composites with proper NaN handling for sparse measurables (bench press is 77% null, cone/shuttle are 70%+ null).

**Primary recommendation:** Build a single `src/historical_profiles.py` module with pure-function compute logic, a CLI script `scripts/silver_historical_transformation.py` following the established silver_team_transformation.py pattern, and register the new Silver path in config.py.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Store BOTH raw combine measurables AND computed composite scores
- Raw columns preserved: forty, bench, vertical, broad_jump, cone, shuttle, ht, wt
- Composite scores: speed score (weight*200/forty^4), BMI (weight/height_inches^2), burst score (vertical+broad_jump, normalized by position), catch radius proxy (height in inches)
- All composite scores also stored as position-percentile columns
- Draft capital: Jimmy Johnson trade value chart hardcoded as dict (pick 1-262 to trade value points)
- Two-step join via pfr_id (combine pfr_id to draft_picks pfr_player_id)
- Result includes gsis_id from draft_picks for downstream player matching
- Undrafted combine attendees included (NaN draft capital); drafted without combine included (NaN measurables)
- Full outer join; one row per player; no duplicates
- Log match rates at INFO, unmatched at WARNING; never fail pipeline on match quality
- Season scope: ALL draft classes 2000-2025 (26 years)
- Position percentiles computed across all years (cross-era normalization)
- Single flat Parquet: `data/silver/players/historical/combine_draft_profiles.parquet`
- No season partitioning; full regeneration each run; timestamped filename
- New CLI: `scripts/silver_historical_transformation.py` with no --seasons flag
- Follows existing Silver CLI patterns (argparse, local Bronze read, transform, write, optional S3)

### Claude's Discretion
- Exact Jimmy Johnson chart values (researched -- see Code Examples section)
- Height string parsing logic (e.g., "5-11" -> 71 inches)
- Burst score position normalization approach
- Column naming for composite scores and percentiles
- How to handle missing/null measurables when computing composites (NaN propagation vs skip)
- Module organization: new src/historical_profiles.py or inline in CLI script

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HIST-01 | Combine measurables (speed score, burst score, catch radius) linked to player IDs via name+draft year join | Bronze data confirmed: 8,649 combine rows with pfr_id join key. Schema verified with forty/bench/vertical/broad_jump/cone/shuttle/ht/wt columns. Speed score formula confirmed. Position percentile approach documented. |
| HIST-02 | Draft capital (pick value via trade chart) linked to player IDs | Bronze data confirmed: 6,644 draft picks with pfr_player_id + gsis_id. Jimmy Johnson chart values verified (picks 1-224). Extension needed for compensatory picks 225-262. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | DataFrame operations, joins, percentile computation | Already in project; all Silver transformations use pandas |
| pyarrow | existing | Parquet read/write | Already in project; standard Parquet engine |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | existing | NaN handling, percentile rank computation | For scipy-free percentile ranking via pandas rank(pct=True) |
| argparse | stdlib | CLI argument parsing | Standard CLI pattern |
| logging | stdlib | Match rate and unmatched player logging | INFO/WARNING level logging per project pattern |

No new dependencies required. All libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
src/
  historical_profiles.py    # Pure compute functions (NEW)
scripts/
  silver_historical_transformation.py  # CLI script (NEW)
src/
  config.py                 # Add SILVER_PLAYER_S3_KEYS entry (MODIFY)
data/silver/players/historical/
  combine_draft_profiles_YYYYMMDD_HHMMSS.parquet  # Output (NEW)
```

### Pattern 1: Module + CLI Separation
**What:** All compute logic in `src/historical_profiles.py`, all I/O in the CLI script.
**When to use:** Always -- matches silver_team_transformation.py + team_analytics.py pattern.
**Example:**
```python
# src/historical_profiles.py - pure functions, no I/O
def parse_height_to_inches(ht_str: str) -> float:
    """Convert height string '5-11' to inches (71.0)."""
    ...

def compute_speed_score(wt: pd.Series, forty: pd.Series) -> pd.Series:
    """Bill Barnwell speed score: (weight * 200) / (forty^4)."""
    ...

def compute_composite_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add speed_score, bmi, burst_score, catch_radius columns."""
    ...

def compute_position_percentiles(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Add _pos_pctl suffix columns ranked within position group."""
    ...

def build_jimmy_johnson_chart() -> dict:
    """Return dict mapping pick number (1-262) to trade value."""
    ...

def join_combine_draft(combine_df, draft_df) -> pd.DataFrame:
    """Full outer join on pfr_id, dedup, attach trade value."""
    ...
```

### Pattern 2: Local Bronze Reader (Established)
**What:** `_read_local_bronze(subdir, season)` pattern from silver_advanced_transformation.py.
**When to use:** Reading Bronze parquet files by season directory.

### Pattern 3: Match Rate Logging (Established in Phase 17)
**What:** Log join match rates at INFO level; unmatched players at WARNING.
**When to use:** After every join operation.

### Anti-Patterns to Avoid
- **Joining on pfr_id alone without handling duplicates:** 17 pfr_ids appear in multiple combine seasons for different players. Must dedup combine data first (keep latest season entry per pfr_id, or join on pfr_id + season).
- **Assuming all picks are <= 224:** Draft data has picks up to 262 (compensatory picks). The Jimmy Johnson chart must be extended.
- **Computing percentiles before filtering NaN:** Position percentiles must use `rank(pct=True)` which already excludes NaN, but verify groupby behavior.
- **Row explosion from join:** Full outer join on pfr_id can explode if combine has duplicate pfr_ids. Must dedup combine by pfr_id first, keeping the row where season == draft_year (when available) or the latest season entry.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Percentile ranking | Custom percentile binning | `df.groupby('pos')[col].rank(pct=True)` | pandas rank handles NaN correctly, ties, and edge cases |
| Height parsing | Complex regex | Simple split on '-' with int conversion | Heights are consistently formatted as "X-Y" in the data |
| Trade value interpolation | Custom curve fitting | Hardcoded dict with linear extrapolation for 225-262 | The chart is a fixed reference, not a model |

## Common Pitfalls

### Pitfall 1: Duplicate pfr_id in Combine Data
**What goes wrong:** 17 pfr_ids appear in combine data across different seasons for different players (e.g., "BrowCh03" is Chris Brown OT in 2001 and Chris Brown RB in 2003). A full outer join without dedup produces extra rows.
**Why it happens:** PFR reuses ID patterns for different players with similar names.
**How to avoid:** Before joining, dedup combine data on pfr_id. Strategy: when pfr_id appears multiple times, keep the row where `season == draft_year` (if draft_year exists); otherwise keep the row with the latest season. For combine rows with null pfr_id (1,477 rows), keep all -- they will be combine-only entries in the output.
**Warning signs:** Row count after join exceeds expected ~8,600-9,600 range.

### Pitfall 2: Sparse Measurables
**What goes wrong:** Composite scores return NaN for most players because underlying measurables are null.
**Why it happens:** Bench press is 77% null across all combine data; cone and shuttle are 70%+ null. Even forty is ~12% null.
**How to avoid:** Let NaN propagate naturally in composite scores (speed_score is NaN when forty is NaN). For percentiles, rank(pct=True) excludes NaN automatically. Document null rates in output metadata.
**Warning signs:** Speed score is null for >15% of combine attendees; burst score for >12%.

### Pitfall 3: Compensatory Picks Beyond Chart Range
**What goes wrong:** ~820 draft picks (12% of all picks) have pick numbers 225-262, beyond the original Jimmy Johnson chart.
**Why it happens:** NFL compensatory pick system adds late-round picks beyond the standard 224.
**How to avoid:** Extend the chart with linear extrapolation from the round 7 decay rate (approximately 0.4 points per pick decrease). Minimum value = 0.4 for pick 262.
**Warning signs:** `draft_value` column has unexpected NaN for late-round picks.

### Pitfall 4: Height String Edge Cases
**What goes wrong:** Height parsing fails on unexpected formats.
**Why it happens:** The data is consistently "X-Y" format (e.g., "5-11", "6-4") across all 8,649 rows with 19 unique values, but defensive coding is still needed.
**How to avoid:** Parse with try/except; return NaN for any unparseable value. Log count of parse failures.

## Code Examples

### Height Parsing
```python
def parse_height_to_inches(ht_str: str) -> Optional[float]:
    """Convert '5-11' to 71.0 inches. Returns None on failure."""
    if pd.isna(ht_str):
        return None
    try:
        feet, inches = ht_str.split("-")
        return int(feet) * 12 + int(inches)
    except (ValueError, AttributeError):
        return None
```

### Speed Score
```python
# Source: Bill Barnwell (ESPN/Football Outsiders)
# Formula: (weight * 200) / (forty ^ 4)
# Average NFL RB speed score ~100; elite > 110
def compute_speed_score(wt: pd.Series, forty: pd.Series) -> pd.Series:
    return (wt * 200) / (forty ** 4)
```

### Position Percentiles
```python
def compute_position_percentiles(
    df: pd.DataFrame, score_cols: list
) -> pd.DataFrame:
    """Add {col}_pos_pctl columns ranked within position group."""
    result = df.copy()
    for col in score_cols:
        pctl_col = f"{col}_pos_pctl"
        result[pctl_col] = result.groupby("pos")[col].rank(pct=True)
    return result
```

### Jimmy Johnson Chart (Key Values)
```python
JIMMY_JOHNSON_CHART = {
    1: 3000, 2: 2600, 3: 2200, 4: 1800, 5: 1700,
    6: 1600, 7: 1500, 8: 1400, 9: 1350, 10: 1300,
    11: 1250, 12: 1200, 13: 1150, 14: 1100, 15: 1050,
    16: 1000, 17: 950, 18: 900, 19: 875, 20: 850,
    21: 800, 22: 780, 23: 760, 24: 740, 25: 720,
    26: 700, 27: 680, 28: 660, 29: 640, 30: 620,
    31: 600, 32: 590,
    # Round 2
    33: 580, 34: 560, 35: 550, 36: 540, 37: 530,
    38: 520, 39: 510, 40: 500, 41: 490, 42: 480,
    43: 470, 44: 460, 45: 450, 46: 440, 47: 430,
    48: 420, 49: 410, 50: 400, 51: 390, 52: 380,
    53: 370, 54: 360, 55: 350, 56: 340, 57: 330,
    58: 320, 59: 310, 60: 300, 61: 292, 62: 284,
    63: 276, 64: 270,
    # Round 3
    65: 265, 66: 260, 67: 255, 68: 250, 69: 245,
    70: 240, 71: 235, 72: 230, 73: 225, 74: 220,
    75: 215, 76: 210, 77: 205, 78: 200, 79: 195,
    80: 190, 81: 185, 82: 180, 83: 175, 84: 170,
    85: 165, 86: 160, 87: 155, 88: 150, 89: 145,
    90: 140, 91: 136, 92: 132, 93: 128, 94: 124,
    95: 120, 96: 116,
    # Round 4
    97: 112, 98: 108, 99: 104, 100: 100, 101: 96,
    102: 92, 103: 88, 104: 86, 105: 84, 106: 82,
    107: 80, 108: 78, 109: 76, 110: 74, 111: 72,
    112: 70, 113: 68, 114: 66, 115: 64, 116: 62,
    117: 60, 118: 58, 119: 56, 120: 54, 121: 52,
    122: 50, 123: 49, 124: 48, 125: 47, 126: 46,
    127: 45, 128: 44,
    # Round 5
    129: 43, 130: 42, 131: 41, 132: 40, 133: 39.5,
    134: 39, 135: 38.5, 136: 38, 137: 37.5, 138: 37,
    139: 36.5, 140: 36, 141: 35.5, 142: 35, 143: 34.5,
    144: 34, 145: 33.5, 146: 33, 147: 32.6, 148: 32.2,
    149: 31.8, 150: 31.4, 151: 31, 152: 30.6, 153: 30.2,
    154: 29.8, 155: 29.4, 156: 29, 157: 28.6, 158: 28.2,
    159: 27.8, 160: 27.4,
    # Round 6
    161: 27, 162: 26.6, 163: 26.2, 164: 25.8, 165: 25.4,
    166: 25, 167: 24.6, 168: 24.2, 169: 23.8, 170: 23.4,
    171: 23, 172: 22.6, 173: 22.2, 174: 21.8, 175: 21.4,
    176: 21, 177: 20.6, 178: 20.2, 179: 19.8, 180: 19.4,
    181: 19, 182: 18.6, 183: 18.2, 184: 17.8, 185: 17.4,
    186: 17, 187: 16.6, 188: 16.2, 189: 15.8, 190: 15.4,
    191: 15, 192: 14.6,
    # Round 7
    193: 14.2, 194: 13.8, 195: 13.4, 196: 13, 197: 12.6,
    198: 12.2, 199: 11.8, 200: 11.4, 201: 11, 202: 10.6,
    203: 10.2, 204: 9.8, 205: 9.4, 206: 9, 207: 8.6,
    208: 8.2, 209: 7.8, 210: 7.4, 211: 7, 212: 6.6,
    213: 6.2, 214: 5.8, 215: 5.4, 216: 5, 217: 4.6,
    218: 4.2, 219: 3.8, 220: 3.4, 221: 3, 222: 2.6,
    223: 2.3, 224: 2,
    # Compensatory (linear extrapolation: ~0.04 per pick from 2.0 down)
    # Minimum 0.4 for pick 262
    **{p: max(0.4, round(2.0 - (p - 224) * 0.042, 2)) for p in range(225, 263)},
}
```

### Combine Dedup Strategy
```python
def dedup_combine(combine_df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate pfr_ids, keeping best match."""
    # Separate null pfr_ids (keep all)
    null_mask = combine_df["pfr_id"].isna()
    nulls = combine_df[null_mask]
    non_nulls = combine_df[~null_mask]

    # For non-nulls with duplicate pfr_ids: prefer row where season == draft_year
    # Then fallback to latest season
    non_nulls = non_nulls.sort_values(
        ["pfr_id", "season"], ascending=[True, False]
    )
    # Mark rows where season matches draft_year (best match)
    non_nulls["_match_quality"] = (
        non_nulls["season"] == non_nulls["draft_year"]
    ).astype(int)
    non_nulls = non_nulls.sort_values(
        ["pfr_id", "_match_quality", "season"],
        ascending=[True, False, False],
    )
    deduped = non_nulls.drop_duplicates(subset="pfr_id", keep="first")
    deduped = deduped.drop(columns=["_match_quality"])

    return pd.concat([deduped, nulls], ignore_index=True)
```

### Full Outer Join
```python
def join_combine_draft(
    combine_df: pd.DataFrame, draft_df: pd.DataFrame
) -> pd.DataFrame:
    """Full outer join combine + draft on pfr_id."""
    merged = combine_df.merge(
        draft_df,
        left_on="pfr_id",
        right_on="pfr_player_id",
        how="outer",
        suffixes=("_combine", "_draft"),
    )
    # Coalesce overlapping columns (season, position, etc.)
    # Attach draft_value from Jimmy Johnson chart
    chart = build_jimmy_johnson_chart()
    merged["draft_value"] = merged["pick"].map(chart)
    return merged
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Name+draft year fuzzy matching | pfr_id join (deterministic) | nflverse standardized IDs | >95% match rate vs ~80% for name matching |
| Manual combine data collection | nfl-data-py import_combine_data | nflverse 2020+ | Automated 2000-2025 coverage |
| Speed score only for RBs | Speed score for all positions with positional percentiles | Modern analytics | Cross-position comparison via percentiles |

## Open Questions

1. **Burst score normalization approach**
   - What we know: burst_score = vertical + broad_jump (raw composite). Position percentile handles normalization.
   - What's unclear: Whether to also store a z-score normalized version within position group, or if percentile rank is sufficient.
   - Recommendation: Use percentile rank only (simpler, more interpretable). The raw burst_score value is already stored for custom analysis.

2. **Combine attendees with null pfr_id (1,477 rows)**
   - What we know: These are combine attendees who lack a PFR ID in the data. They cannot be joined to draft picks or downstream rosters.
   - What's unclear: Whether they are valuable for the dimension table or just noise.
   - Recommendation: Include them in the output (they have measurables and position data useful for percentile computation). Flag with `has_pfr_id = False` column.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, 71 tests passing) |
| Config file | tests/ directory with existing conftest patterns |
| Quick run command | `python -m pytest tests/test_historical_profiles.py -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HIST-01 | Speed score computation | unit | `python -m pytest tests/test_historical_profiles.py::test_compute_speed_score -x` | Wave 0 |
| HIST-01 | Height parsing | unit | `python -m pytest tests/test_historical_profiles.py::test_parse_height -x` | Wave 0 |
| HIST-01 | Burst score computation | unit | `python -m pytest tests/test_historical_profiles.py::test_compute_burst_score -x` | Wave 0 |
| HIST-01 | Position percentiles | unit | `python -m pytest tests/test_historical_profiles.py::test_position_percentiles -x` | Wave 0 |
| HIST-01 | Combine dedup (17 dupes resolved) | unit | `python -m pytest tests/test_historical_profiles.py::test_dedup_combine -x` | Wave 0 |
| HIST-02 | Jimmy Johnson chart completeness (1-262) | unit | `python -m pytest tests/test_historical_profiles.py::test_jimmy_johnson_chart -x` | Wave 0 |
| HIST-02 | Full outer join preserves row count | unit | `python -m pytest tests/test_historical_profiles.py::test_join_no_explosion -x` | Wave 0 |
| HIST-02 | Draft value mapping (NaN for UDFAs) | unit | `python -m pytest tests/test_historical_profiles.py::test_draft_value_mapping -x` | Wave 0 |
| HIST-01+02 | End-to-end pipeline produces valid parquet | integration | `python -m pytest tests/test_historical_profiles.py::test_end_to_end -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_historical_profiles.py -v -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_historical_profiles.py` -- covers HIST-01, HIST-02
- [ ] No new framework install needed (pytest already configured)

## Sources

### Primary (HIGH confidence)
- **Bronze data inspection** -- Direct parquet schema analysis of `data/bronze/combine/` and `data/bronze/draft_picks/` (8,649 combine rows, 6,644 draft rows, 26 seasons each)
- **nfl_data_adapter.py** -- Confirmed `fetch_combine()` and `fetch_draft_picks()` methods exist with season range 2000+
- **config.py** -- Confirmed `DATA_TYPE_SEASON_RANGES` covers combine and draft_picks from 2000

### Secondary (MEDIUM confidence)
- **Jimmy Johnson chart values** -- Verified via [WalterFootball draft chart](https://walterfootball.com/draftchart.php) (picks 1-224 with exact values)
- **Speed score formula** -- Confirmed as `(weight * 200) / (forty^4)` via [FTN Fantasy speed scores](https://ftnfantasy.com/nfl/speed-scores-2026-mike-washington-nears-the-record) and [Football Outsiders](https://www.footballoutsiders.com/stat-analysis/2020/speed-score-2020)

### Tertiary (LOW confidence)
- **Compensatory pick chart extension (225-262)** -- Linear extrapolation from round 7 decay rate. No official Jimmy Johnson values exist for these picks. The extrapolation is reasonable but arbitrary.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, follows established project patterns exactly
- Architecture: HIGH -- mirrors silver_team_transformation.py + team_analytics.py pattern (module + CLI)
- Pitfalls: HIGH -- discovered via direct Bronze data inspection (17 duplicate pfr_ids, 820 picks > 224, sparse measurables quantified)
- Join strategy: HIGH -- pfr_id overlap verified at 5,384 of 7,155 combine IDs (75% match rate)

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable -- combine/draft data structure unlikely to change)
