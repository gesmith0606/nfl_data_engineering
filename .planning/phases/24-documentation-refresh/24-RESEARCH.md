# Phase 24: Documentation Refresh - Research

**Researched:** 2026-03-20
**Domain:** Documentation updates (Markdown, Parquet schema introspection, project reference files)
**Confidence:** HIGH

## Summary

Phase 24 is a documentation-only phase requiring updates to five files: the data dictionary (Silver + Gold schemas), Bronze inventory, implementation guide, CLAUDE.md, and optionally the prediction data model doc. The primary technical challenge is auto-generating Silver schemas from 12 local Parquet directories using pyarrow, then hand-writing column descriptions. There is no code to build -- only markdown to produce and an existing inventory script to re-run.

The existing `scripts/generate_inventory.py` already handles Bronze inventory generation and was last run on 2026-03-11. It needs to be re-run to pick up the officials data type (ingested 2026-03-16) and the updated PBP column count (now 140, up from 103). The data dictionary currently has only 2 Silver tables documented (Games Silver and Teams Silver, both aspirational/planned content) and needs expansion to cover all 12 actual Silver output paths. CLAUDE.md is significantly stale -- it references "8 data types", "71 tests", and pre-v1.2 status.

**Primary recommendation:** Use pyarrow.parquet.read_schema() to auto-generate Silver/Gold column tables, re-run generate_inventory.py for Bronze, and manually update CLAUDE.md and the implementation guide with current v1.3 facts.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Auto-generate Silver schemas from local parquet files (DuckDB/pandas to extract column names, types, sample values), then add brief hand-written descriptions per column
- D-02: Add Silver schemas to the existing NFL_DATA_DICTIONARY.md after the Bronze section -- one source of truth for all layer schemas
- D-03: Replace the existing planned "Games (Silver)" schema section with real auto-generated schemas from actual parquet files -- remove planned/aspirational content
- D-04: Document planned prediction output columns based on REQUIREMENTS.md (spread prediction, total prediction, edge, confidence tier) -- mark as "Planned" with version badges
- D-05: Also document the existing fantasy projection output schema (weekly/preseason projections) -- complete Gold layer reference covering both existing and planned outputs
- D-06: Write or update a script that scans data/bronze/ and auto-generates the inventory table from parquet metadata (file counts, sizes, column counts) -- ensures PBP shows 140 columns and officials data type is included
- D-07: Full refresh of CLAUDE.md -- update test count to 360, add all 11 Silver paths to architecture diagram, add prediction feature vector, refresh status section with v1.3 completion
- D-08: Add new v1.2/v1.3 modules to key files table (team_analytics.py, game_context.py, prediction_features.py, and any other new src files)
- D-09: Full update of implementation guide -- add phases 20-23 as completed with dates, add v1.4 phases 24-27 as planned with status badges

### Claude's Discretion
- Column description wording and formatting for auto-generated Silver schemas
- Exact layout of Gold "Planned" schema badges
- How to handle the prediction data model doc (NFL_GAME_PREDICTION_DATA_MODEL.md) -- update if stale, or leave as-is if still accurate

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DOCS-01 | Data dictionary updated with all 11 Silver layer table schemas and column definitions | 12 Silver paths identified with column counts; pyarrow schema extraction verified working; existing 2 aspirational Silver tables must be replaced |
| DOCS-02 | Data dictionary updated with Gold layer prediction output schemas | Existing fantasy projection schema (25 columns) extracted; planned prediction schema defined in REQUIREMENTS.md (spread, total, edge, confidence) |
| DOCS-03 | CLAUDE.md refreshed with current architecture, key files, test counts, and status | Current CLAUDE.md audited -- stale on test count (says 71, actual 360), data types (says 8, actual 15+), Silver description, status section, key files table missing 6+ modules |
| DOCS-04 | Implementation guide updated with v1.3 phases and current prediction model status badges | Implementation guide ends at Phase 17 with "v1.2 in progress"; needs phases 18-23 as completed and v1.4 phases 24-27 as planned; test count says 274, actual 360; milestone table says v1.2 in progress |
| DOCS-05 | Bronze inventory regenerated showing PBP 140 columns and officials data type | Existing generate_inventory.py script confirmed working; PBP verified at 140 columns; officials data type exists with 5 columns across 2016-2025 |
</phase_requirements>

## Standard Stack

### Core Tools
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| pyarrow | installed in venv | Parquet schema introspection via `pq.read_schema()` | Already used by generate_inventory.py; zero overhead |
| DuckDB MCP | available | Alternative for SQL-based schema queries on parquet | Available but pyarrow is simpler for column listing |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `scripts/generate_inventory.py` | Auto-generate Bronze inventory markdown table | Re-run for DOCS-05 |
| `glob` + `pyarrow.parquet` | Find latest parquet per Silver path, extract schema | Silver schema generation for DOCS-01 |

### No New Dependencies
This phase requires no new libraries or installations. All tools are already available in the project venv.

## Architecture Patterns

### Documentation File Map
```
docs/
  NFL_DATA_DICTIONARY.md          # DOCS-01, DOCS-02: Silver + Gold schemas
  BRONZE_LAYER_DATA_INVENTORY.md  # DOCS-05: Regenerated inventory
  NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md  # DOCS-04: Phase history + status
  NFL_GAME_PREDICTION_DATA_MODEL.md       # Discretionary: review for accuracy
CLAUDE.md                          # DOCS-03: Project reference refresh
```

### Silver Path Inventory (12 actual paths)

**IMPORTANT FINDING:** The success criteria says "11 Silver output paths" but there are actually **12** distinct Silver output directories on disk:

| # | Path | Column Count | Source Module |
|---|------|-------------|---------------|
| 1 | `defense/positional` | 6 | game_context.py |
| 2 | `players/advanced` | 119 | player_advanced_analytics.py |
| 3 | `players/historical` | 63 | historical_profiles.py |
| 4 | `players/usage` | 173 | player_analytics.py |
| 5 | `teams/game_context` | 22 | game_context.py |
| 6 | `teams/pbp_derived` | 164 | team_analytics.py (v1.3) |
| 7 | `teams/pbp_metrics` | 63 | team_analytics.py |
| 8 | `teams/playoff_context` | 10 | game_context.py |
| 9 | `teams/referee_tendencies` | 4 | game_context.py |
| 10 | `teams/situational` | 51 | team_analytics.py |
| 11 | `teams/sos` | 21 | team_analytics.py |
| 12 | `teams/tendencies` | 23 | team_analytics.py |

The planner should document all 12. The "11" in the success criteria likely excluded `defense/positional` or counted paths before v1.3 added new ones. Document the reality.

### Gold Layer Schemas

**Existing (fantasy projections) -- 25 columns:**
`player_id, player_name, position, recent_team, proj_season, proj_week, proj_passing_yards, proj_passing_tds, proj_interceptions, proj_rushing_yards, proj_rushing_tds, proj_carries, proj_receptions, proj_receiving_yards, proj_receiving_tds, proj_targets, projected_points, is_bye_week, is_rookie_projection, vegas_multiplier, position_rank, injury_status, injury_multiplier, projected_floor, projected_ceiling`

**Planned (game predictions) -- derive from REQUIREMENTS.md:**
- `game_id, season, week, home_team, away_team`
- `model_spread, model_total` (PRED-01)
- `vegas_spread, vegas_total` (PRED-02 -- for edge computation)
- `spread_edge, total_edge` (PRED-02)
- `spread_confidence_tier, total_confidence_tier` (PRED-03 -- high/medium/low)
- `model_version, prediction_timestamp`

### Data Dictionary Structure Pattern
The existing Bronze section uses this format per table:
```markdown
### [Table Name]
**Source:** [origin]
**S3 Path:** [path]
**Local Path:** [path]

| Column | Type | Nullable | Description | Example |
|--------|------|----------|-------------|---------|
```

Silver sections should follow the same pattern. The two existing Silver tables (Games Silver, Teams Silver) are aspirational/planned and do NOT reflect actual parquet files. They must be replaced entirely (decision D-03).

### CLAUDE.md Gaps Identified

Current vs actual state:

| Section | Current (Stale) | Actual |
|---------|----------------|--------|
| Architecture diagram | "raw game, player, snap, injury, roster data" | 15+ Bronze types, 12 Silver paths, prediction features |
| Key Files table | 15 entries, missing 6+ modules | Needs: nfl_data_adapter.py, team_analytics.py, player_advanced_analytics.py, game_context.py, historical_profiles.py, silver scripts |
| data-types comment | "schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal" (8) | 15+ types including ngs, pfr, qbr, depth_charts, draft_picks, combine, officials |
| Status "Done" | "71 unit tests passing" | 360 tests passing |
| Status "In progress" | "Weekly pipeline cron tuning" | v1.4 ML Game Prediction |
| Status "Planned" | "Neo4j Phase 5, ML upgrade" | v1.4 in progress; Neo4j deferred |
| Silver description | "usage metrics, rolling averages, opp rankings (1-32)" | + team PBP metrics, tendencies, SOS, situational, advanced profiles, game context, referee, playoff context |
| nfl_data_integration.py | "all 8 fetch methods" | NFLDataAdapter now handles fetching; integration.py is legacy |

### Implementation Guide Gaps

| Area | Current | Needs |
|------|---------|-------|
| Last documented phase | Phase 17 (v1.2) | Add phases 18-23 (v1.2-v1.3) |
| Milestone table | "v1.2 in progress" | v1.2 shipped 2026-03-15, v1.3 shipped 2026-03-19, v1.4 in progress |
| Test count | 274 | 360 |
| ML section | "XGBoost, LightGBM" planned | LightGBM dropped (v1.4 decision); XGBoost only |
| Upcoming phases | Phase 18-19 as upcoming | Phases 18-23 completed; 24-27 as upcoming |
| Silver data paths listed | "players/ (usage, advanced), teams/ (pbp_metrics, tendencies, sos, situational)" | Add: defense/positional, teams/game_context, teams/pbp_derived, teams/playoff_context, teams/referee_tendencies, players/historical |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bronze inventory | Manual markdown table | `scripts/generate_inventory.py` | Already handles file counting, sizing, column counting, season ranges |
| Parquet schema extraction | Manual column listing | `pyarrow.parquet.read_schema(path)` | Returns exact column names and types from file metadata |
| Latest file selection | Scan directories manually | `sorted(glob.glob(pattern))[-1]` | Consistent with existing codebase pattern |

## Common Pitfalls

### Pitfall 1: Documenting aspirational schemas instead of actual ones
**What goes wrong:** The existing Silver section has "Games (Silver)" and "Teams (Silver)" tables that describe a planned schema that does not match any actual parquet file.
**Why it happens:** Documentation written before implementation, never updated.
**How to avoid:** Decision D-03 explicitly says to replace planned content with auto-generated schemas from actual parquet files. Always verify against `pq.read_schema()` output.

### Pitfall 2: Stale column counts
**What goes wrong:** Documenting column counts that don't match the parquet files (e.g., PBP was 103, now 140).
**How to avoid:** Extract column counts programmatically. The research already verified: PBP=140, officials=5, and all 12 Silver paths have verified column counts above.

### Pitfall 3: Missing the `defense/positional` Silver path
**What goes wrong:** The success criteria says "11 Silver output paths" but there are 12 on disk.
**How to avoid:** Document all 12 paths. The planner should note this discrepancy and document reality.

### Pitfall 4: CLAUDE.md becoming too verbose
**What goes wrong:** Adding all 12 Silver paths and 15+ Bronze types makes CLAUDE.md bloated.
**Why it matters:** CLAUDE.md is loaded into every Claude Code session and affects token usage.
**How to avoid:** Keep CLAUDE.md concise. Use summary lines in architecture diagram (e.g., "12 Silver paths: team metrics, player profiles, game context, defense"). Full details belong in the data dictionary and implementation guide.

### Pitfall 5: prediction_features.py does not exist
**What goes wrong:** CONTEXT.md decision D-08 mentions `prediction_features.py` as a new v1.3 module to add to CLAUDE.md key files table, but this file does not exist on disk.
**How to avoid:** The v1.3 feature assembly is likely done within `game_context.py` or as a script. The actual new v1.3 src modules are: `game_context.py` (confirmed on disk). Check for feature vector assembly in scripts or existing modules rather than assuming a separate file exists.

## Code Examples

### Silver Schema Extraction Pattern
```python
# Source: verified against existing generate_inventory.py pattern
import pyarrow.parquet as pq
import glob

def get_silver_schema(path: str) -> list:
    """Get column schema from latest parquet file in a Silver path."""
    files = sorted(glob.glob(f"{path}/**/*.parquet", recursive=True))
    if not files:
        return []
    schema = pq.read_schema(files[-1])
    return [(name, str(schema.field(name).type)) for name in schema.names]
```

### Bronze Inventory Regeneration
```bash
# Re-run existing script to pick up officials + updated PBP columns
source venv/bin/activate
python scripts/generate_inventory.py --output docs/BRONZE_LAYER_DATA_INVENTORY.md
```

## State of the Art

| Old State | Current State | When Changed | Impact on Docs |
|-----------|--------------|--------------|----------------|
| 8 Bronze data types | 15+ Bronze types | v1.1 (2026-03-13) | CLAUDE.md data-types list, architecture |
| 103 PBP columns | 140 PBP columns | v1.3 Phase 20 (2026-03-16) | Bronze inventory, data dictionary |
| No officials data | Officials ingested (5 cols, 2016-2025) | v1.3 Phase 20 (2026-03-16) | Bronze inventory |
| 2 Silver tables (aspirational) | 12 Silver paths (actual) | v1.2-v1.3 (2026-03-14 to 2026-03-19) | Data dictionary Silver section |
| 71 tests | 360 tests | v1.3 (2026-03-19) | CLAUDE.md, impl guide |
| No game prediction features | 337-column feature vector from 8 Silver sources | v1.3 Phase 23 (2026-03-19) | CLAUDE.md architecture, status |
| LightGBM + XGBoost planned | XGBoost only (v1.4 decision) | v1.4 planning (2026-03-20) | Implementation guide ML section |

## Open Questions

1. **"11 Silver output paths" vs 12 actual paths**
   - What we know: 12 distinct directories exist under data/silver/
   - What's unclear: Whether the "11" in success criteria was intentional (excluding one path) or a miscount
   - Recommendation: Document all 12 paths. The planner should note this and document reality.

2. **prediction_features.py does not exist**
   - What we know: CONTEXT.md D-08 mentions it; `src/prediction_features.py` is not on disk
   - What's unclear: Whether feature assembly code lives in game_context.py or a script
   - Recommendation: Check `scripts/` and `src/game_context.py` for feature vector assembly logic during implementation. Add whatever actually exists to the key files table.

3. **NFL_GAME_PREDICTION_DATA_MODEL.md accuracy**
   - What we know: v3.0, last updated March 15; mentions LightGBM (now dropped), says "v1.2 in progress" for Silver
   - Recommendation: Update stale references (LightGBM -> XGBoost only, Silver status, v1.3 completion) as part of discretionary cleanup

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed in venv) |
| Config file | implicit (no pytest.ini, uses defaults) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOCS-01 | Silver schemas in data dictionary | manual-only | N/A -- documentation content review | N/A |
| DOCS-02 | Gold schemas in data dictionary | manual-only | N/A -- documentation content review | N/A |
| DOCS-03 | CLAUDE.md accuracy | manual-only | N/A -- documentation content review | N/A |
| DOCS-04 | Implementation guide updated | manual-only | N/A -- documentation content review | N/A |
| DOCS-05 | Bronze inventory regenerated | smoke | `python scripts/generate_inventory.py --output /dev/null` | generate_inventory.py exists |

**Justification for manual-only:** DOCS-01 through DOCS-04 are pure markdown documentation updates. There is no behavioral code to test. DOCS-05 can be smoke-tested by running the inventory script and verifying it produces output containing "pbp" with "140" columns and "officials" as a row.

### Sampling Rate
- **Per task commit:** `python scripts/generate_inventory.py --output /dev/null` (for DOCS-05 only)
- **Per wave merge:** Visual review of all 5 documents against success criteria
- **Phase gate:** All 5 success criteria manually verified before `/gsd:verify-work`

### Wave 0 Gaps
None -- this is a documentation-only phase. No test infrastructure needed. The existing `scripts/generate_inventory.py` serves as the only automated verification tool and already exists.

## Sources

### Primary (HIGH confidence)
- Local filesystem inspection: `data/silver/`, `data/bronze/`, `data/gold/` directories
- `pyarrow.parquet.read_schema()` output for all Silver/Gold/Bronze column counts
- `docs/NFL_DATA_DICTIONARY.md` (1274 lines) -- current state audited
- `docs/BRONZE_LAYER_DATA_INVENTORY.md` (34 lines) -- current state audited
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` (627 lines) -- current state audited
- `CLAUDE.md` (137 lines) -- current state audited
- `scripts/generate_inventory.py` -- confirmed functional, uses pyarrow
- `.planning/MILESTONES.md` -- v1.3 shipped details
- `.planning/ROADMAP.md` -- phase completion history
- `python -m pytest tests/ --co -q` -- 360 tests collected

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` -- Gold prediction schema derived from PRED-01/02/03 requirement descriptions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new tools needed, all verified on disk
- Architecture: HIGH -- all Silver/Gold paths inspected, column counts verified via pyarrow
- Pitfalls: HIGH -- based on direct comparison of current docs vs actual state

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (documentation refresh -- stable until next milestone ships)
