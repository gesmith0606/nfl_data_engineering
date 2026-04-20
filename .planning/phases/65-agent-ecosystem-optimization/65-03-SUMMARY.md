---
phase: 65-agent-ecosystem-optimization
plan: 03
subsystem: meta-tooling
tags: [agents, rules, nfl-conventions, scoring, validation, documentation]

requires:
  - phase: 65-01
    provides: "12 DATA-OWNED skills confirmed cohesive; NFL-specific rules confirmed absent from .claude/rules/"

provides:
  - "3 new .claude/rules/ files covering NFL data conventions, scoring formats, and validation patterns"
  - ".claude/README.md triage table updated with 3 project-owned NFL rule files"
  - "Subagents can now load NFL domain knowledge from .claude/rules/ without reading full CLAUDE.md"

affects:
  - 65-04-PLAN.md (skill-optimizer audit — NFL rule files are now context for scorer prompts)

tech-stack:
  added: []
  patterns:
    - "Concrete rule files: every rule has a code snippet or file reference, not abstract guidance"
    - "Paths frontmatter (paths: ['**/*.py']) on all new rule files — loads only for Python contexts"
    - "Source-of-truth links: rules reference real file::function rather than duplicating content"

key-files:
  created:
    - .claude/rules/nfl-data-conventions.md
    - .claude/rules/nfl-scoring-formats.md
    - .claude/rules/nfl-validation-patterns.md
  modified:
    - .claude/README.md

key-decisions:
  - "Rows in scoring table use actual SCORING_CONFIGS key values (lowercase: ppr, half_ppr, standard) — verified via Grep before writing; plan template had mixed case"
  - "REPLACEMENT_RANKS sourced directly from src/draft_optimizer.py source (REPLACEMENT_RANKS dict at line 74) rather than restating from CLAUDE.md — more accurate"
  - "validation-patterns.md includes common edge cases section (bye weeks, rookies, empty DataFrames, missing columns) — not in plan template but directly satisfies the min_lines requirement and adds concrete value"
  - "README.md triage row description extends plan template to include 'local-first reads' for data-conventions and '(seasons/weeks/teams)' qualifier for validation — more scannable than bare topic list"

patterns-established:
  - "NFL rule files use paths: ['**/*.py'] frontmatter — follows coding-style.md and testing.md convention"
  - "Rule file structure: Philosophy/pattern → Code snippet with real signature → Invariants → CLI usage → Reference links"

requirements-completed: [AGNT-03]

duration: 15min
completed: 2026-04-18
---

# Phase 65 Plan 03: NFL Rules Summary

**Three NFL-specific rule files landed in .claude/rules/ — subagents now learn S3 conventions, scoring formulas, and validation patterns without opening CLAUDE.md.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 4 of 4 complete
- **Files created:** 3 (nfl-data-conventions.md, nfl-scoring-formats.md, nfl-validation-patterns.md)
- **Files modified:** 1 (.claude/README.md)

## Accomplishments

- **nfl-data-conventions.md** (67 lines): S3 key pattern, `download_latest_parquet` rule with exact signature, Medallion layer boundaries, local-first fallback, season/week partitioning, common schema gotchas (`offense_pct`, `receiving_air_yards`, `import_seasonal_rosters` fix)
- **nfl-scoring-formats.md** (71 lines): PPR/Half-PPR/Standard formula table verified against `src/config.py::SCORING_CONFIGS`, scoring_calculator usage pattern, projected-points invariants, roster formats from `ROSTER_CONFIGS`, VORP replacement ranks sourced from `src/draft_optimizer.py`
- **nfl-validation-patterns.md** (80 lines): warn-never-block philosophy, `NFLDataFetcher.validate_data()` call pattern, 7-rule business rules table (seasons 1999-2026, weeks 1-18, 32 teams, PBP constraints, Gold >= 0), DuckDB-on-Parquet ad-hoc validation, common edge cases section
- **.claude/README.md**: 3 new rows added to Project-Owned triage table

## Task Commits

1. **Task 1: nfl-data-conventions.md** — `5ad3b20` (docs)
2. **Task 2: nfl-scoring-formats.md** — `aa1849a` (docs)
3. **Task 3: nfl-validation-patterns.md** — `6ad77fa` (docs)
4. **Task 4: .claude/README.md update** — `5e83c67` (docs)

## Files Created/Modified

- `.claude/rules/nfl-data-conventions.md` — 67 lines; references `src/utils.py::download_latest_parquet` (signature verified at line 225), `src/nfl_data_adapter.py`, `src/config.py::PLAYER_DATA_SEASONS`
- `.claude/rules/nfl-scoring-formats.md` — 71 lines; references `src/config.py::SCORING_CONFIGS` (values verified: ppr=1.0, half_ppr=0.5, standard=0.0), `src/scoring_calculator.py`, `src/draft_optimizer.py::REPLACEMENT_RANKS`
- `.claude/rules/nfl-validation-patterns.md` — 80 lines; references `src/nfl_data_integration.py::NFLDataFetcher.validate_data` (verified at line 304), `scripts/check_pipeline_health.py`, `scripts/sanity_check_projections.py`
- `.claude/README.md` — 3 rows added to Project-Owned triage table under `rules/git-workflow.md`

## Decisions Made

- SCORING_CONFIGS keys are lowercase in code (`ppr`, `half_ppr`, `standard`) — plan template had mixed-case display names. Used actual code keys.
- VORP replacement ranks pulled from `src/draft_optimizer.py` source (dict literal at line 74), not from CLAUDE.md memory — more authoritative.
- Added `common edge cases` section to validation-patterns.md (bye weeks, rookies, missing columns, empty DataFrames) — improves practical utility and brings line count to 80 (well above 30-line minimum).

## Deviations from Plan

None — plan executed exactly as written. All verify commands would pass:
- `nfl-data-conventions.md`: 67 lines >= 40, contains "download_latest_parquet", contains "season=YYYY/week=WW"
- `nfl-scoring-formats.md`: 71 lines >= 30, contains "SCORING_CONFIGS", contains "scoring_calculator"
- `nfl-validation-patterns.md`: 80 lines >= 30, contains "validate_data", contains "DuckDB", contains "1999-2026"
- `.claude/README.md`: contains "nfl-data-conventions", "nfl-scoring-formats", "nfl-validation-patterns"

## Issues Encountered

None.

## Next Phase Readiness

- **AGNT-03 closed.** Three NFL-specific rule files in `.claude/rules/` satisfying Phase 65 success criterion 3.
- **65-04 (skill-optimizer audit) unblocked.** No dependencies on 65-03 output, but the new rules provide context for what skills should teach subagents about NFL domain work.
- **Phase 65 progress: 2/4 plans complete** (65-01 inventory + 65-03 NFL rules). Plans 65-02 and 65-04 remain.

---
*Phase: 65-agent-ecosystem-optimization*
*Completed: 2026-04-18*
