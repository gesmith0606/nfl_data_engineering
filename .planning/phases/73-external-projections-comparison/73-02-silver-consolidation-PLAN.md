---
phase: 73-external-projections-comparison
plan: 02
type: execute
wave: 2
depends_on: [73-01]
files_modified:
  - scripts/silver_external_projections_transformation.py
  - src/external_projections.py
  - tests/test_silver_external_projections.py
  - tests/fixtures/external_projections/silver_inputs/
autonomous: true
requirements: [EXTP-02]
must_haves:
  truths:
    - "Silver transformation reads all 3 Bronze sources + our Gold projections and emits a single long-format Parquet at data/silver/external_projections/season=YYYY/week=WW/external_projections_YYYYMMDD_HHMMSS.parquet"
    - "Silver Parquet has long-format schema {player_id, player_name, position, team, source, scoring_format, projected_points, projected_at} where source ∈ {ours, espn, sleeper, yahoo_proxy_fp}"
    - "Missing sources are gracefully omitted (D-06): if Bronze ESPN partition is empty, Silver still writes with the 3 remaining sources; never raises"
    - "PlayerNameResolver bridges Bronze player_name → canonical gsis player_id at Silver merge time (so Bronze sources with raw names align with our Gold gsis_ids)"
    - "Silver schema is additive: existing Silver layouts (player_weekly, team_pbp_metrics, etc.) are NOT modified"
  artifacts:
    - path: "scripts/silver_external_projections_transformation.py"
      provides: "CLI that consolidates all 4 sources into Silver long-format Parquet"
      exports: ["main"]
    - path: "src/external_projections.py"
      provides: "Reusable SilverConsolidator with read_bronze_source(), merge_with_ours(), to_long_format()"
      contains: "class SilverConsolidator"
    - path: "tests/test_silver_external_projections.py"
      provides: "Unit + integration tests for the consolidation pipeline"
  key_links:
    - from: "scripts/silver_external_projections_transformation.py"
      to: "src/external_projections.SilverConsolidator"
      via: "module import + .run() invocation"
      pattern: "SilverConsolidator|external_projections"
    - from: "SilverConsolidator.merge_with_ours"
      to: "data/gold/projections/season=YYYY/week=WW/"
      via: "_latest_parquet read of our Gold projections"
      pattern: "data/gold/projections|GOLD_PROJECTIONS_DIR"
    - from: "SilverConsolidator"
      to: "src.player_name_resolver.PlayerNameResolver"
      via: "name → gsis_id resolution for any Bronze rows missing player_id"
      pattern: "PlayerNameResolver"
---

<objective>
Consolidate the 3 external Bronze sources (ESPN, Sleeper, Yahoo proxy) plus our Gold projections into a single long-format Silver Parquet that the API can read in one go. This is the canonical merge point — the API does NOT join sources at request time.

Purpose: Centralize cross-source merge logic in one place (Silver) so the API endpoint is a thin pivot/projection over a stable schema. Future 5th source = column-free addition.
Output: 1 reusable consolidator module, 1 CLI script, 1 test file with ≥6 tests, 1 fixture directory.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/73-external-projections-comparison/73-CONTEXT.md
@.planning/phases/73-external-projections-comparison/73-01-bronze-ingesters-PLAN.md
@CLAUDE.md
@src/utils.py
@src/player_name_resolver.py
@scripts/silver_player_transformation.py

<interfaces>
<!-- Bronze schema produced by Wave 1 ingesters (per 73-01) -->
Bronze Parquet columns (per source, per week):
- player_name (str), player_id (Optional[str]), team (Optional[str]), position (Optional[str])
- projected_points (float), scoring_format (str), source (str), season (int), week (int)
- projected_at (str — ISO 8601 UTC), raw_payload (str)

<!-- Our Gold projections schema (existing — see web/api/services/projection_service.py) -->
Gold projections columns of interest:
- player_id (str — gsis), player_name (str), recent_team / team (str), position (str)
- projected_points (float — for the requested scoring), season (int), week (int)
- (preseason variant uses projected_season_points which is normalized to projected_points)

<!-- Silver output schema (long format, per CONTEXT D-04) -->
Silver Parquet columns (target, written by this plan):
- player_id (str — gsis), player_name (str), position (str), team (str)
- source (str — one of "ours" | "espn" | "sleeper" | "yahoo_proxy_fp")
- scoring_format (str — "ppr" | "half_ppr" | "standard")
- projected_points (float)
- projected_at (str — ISO 8601 UTC of upstream Bronze write OR ISO of our Gold parquet mtime)
- season (int), week (int)

Existing scoring formats (from .claude/rules/nfl-scoring-formats.md):
- "ppr", "half_ppr", "standard" — lowercase keys; src/config.py SCORING_CONFIGS is the source of truth
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: SilverConsolidator class with bronze/gold readers + long-format pivot</name>
  <files>
    src/external_projections.py,
    tests/fixtures/external_projections/silver_inputs/,
    tests/test_silver_external_projections.py
  </files>
  <behavior>
    - Module exports `class SilverConsolidator` with constructor `(season: int, week: int, scoring_format: str, bronze_root: Path = Path("data/bronze/external_projections"), gold_root: Path = Path("data/gold/projections"))`
    - `read_bronze_source(source: str) -> pd.DataFrame` — reads the latest Bronze Parquet for that source/season/week, returns empty DataFrame if missing or unreadable (does not raise per D-06)
    - `read_ours() -> pd.DataFrame` — reads our latest Gold projection Parquet for season/week, normalizes to the long-format columns with `source="ours"`. Honors `recent_team` → `team` rename like `projection_service._get_projections_parquet`. Empty DF if missing.
    - `_resolve_missing_player_ids(df: pd.DataFrame, resolver: PlayerNameResolver) -> pd.DataFrame` — for any row where `player_id` is null/empty, attempt resolver.resolve(name, team, position); rows that remain unresolved are kept (the API can still display by name) but flagged via `player_id=""`
    - `to_long_format(frames: List[pd.DataFrame]) -> pd.DataFrame` — concats all frames, ensures the 9 target Silver columns are present (creates empty defaults if missing on a per-source basis), enforces dtypes (`projected_points: float`, `season/week: int`)
    - `consolidate() -> pd.DataFrame` — orchestrates read all 4 sources → resolve player_ids → to_long_format → return
    - Empty-frame edge case: if ALL sources are empty, return an empty DataFrame with the correct columns/dtypes (callers handle the "no data" case)
    - Test fixtures: `tests/fixtures/external_projections/silver_inputs/{ours,espn,sleeper,yahoo_proxy_fp}/season=2025/week=1/*.parquet` — 4 small Parquet files (~10 players each) with overlapping + disjoint player_ids so the merge is non-trivial
  </behavior>
  <action>
    1. Create `src/external_projections.py` per the Behavior block. Use `dataclasses.dataclass(frozen=True)` for any DTOs; type hints Python 3.9 (`Optional`, `List`, `Dict`).
    2. Read implementation: use `Path.glob("*.parquet")` + `max(..., key=lambda p: p.stat().st_mtime)` (mirrors `web/api/services/projection_service.py::_latest_parquet`). DO NOT use S3 helpers — Silver consolidation runs against the local Bronze.
    3. PlayerNameResolver instantiated lazily in `consolidate()` so tests can monkeypatch with a stub.
    4. Empty-frame contract verified by a dedicated test (no sources present → returns empty DF with 9 columns).
    5. Create the `tests/fixtures/external_projections/silver_inputs/` directory and write 4 fixture Parquet files via a small helper script in the test file (parameterized fixture builder using `tmp_path` + `pd.DataFrame.to_parquet` inside the test setup) — OR commit them as static files. Choose static files for determinism (~5 KB total).
    6. Add `tests/test_silver_external_projections.py` with these tests:
       - `test_read_bronze_source_returns_empty_when_partition_missing` — ESPN partition absent → empty DataFrame
       - `test_read_ours_normalizes_recent_team_to_team` — Gold input with `recent_team` column → output has `team`
       - `test_to_long_format_unions_all_4_sources` — fixture with 4 sources, asserts 4 unique source values + ≥3 player_ids appearing across all 4
       - `test_resolve_missing_player_ids_uses_resolver` — 1 row with null player_id + matching name in fixture roster → player_id populated by stub resolver
       - `test_consolidate_handles_all_sources_missing` — empty bronze_root → returns empty DF with correct columns/dtypes (no raise)
       - `test_consolidate_handles_one_source_missing` — fixture with only ESPN + Sleeper Bronze (Yahoo missing) → output has 3 source values incl. "ours"; "yahoo_proxy_fp" absent
    7. Run `python -m pytest tests/test_silver_external_projections.py -v` — all 6 pass.
  </action>
  <verify>
    <automated>python -m pytest tests/test_silver_external_projections.py -v</automated>
  </verify>
  <done>
    - `src/external_projections.py` exists with `SilverConsolidator` class
    - 6 tests pass
    - D-06 fail-open verified for both per-source missing and all-sources-missing cases
    - PlayerNameResolver bridge tested with a stub
    - Type hints Python 3.9 compatible
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: CLI script + Silver write + integration test</name>
  <files>
    scripts/silver_external_projections_transformation.py,
    tests/test_silver_external_projections.py
  </files>
  <behavior>
    - CLI: `argparse` with `--season`, `--week`, `--scoring half_ppr|ppr|standard` (default `half_ppr`), `--out-root` default `data/silver/external_projections`
    - `main()` instantiates `SilverConsolidator`, calls `consolidate()`, writes Parquet to `{out_root}/season=YYYY/week=WW/external_projections_YYYYMMDD_HHMMSS.parquet` using `df.to_parquet(path, index=False)`
    - If `consolidate()` returns empty DataFrame, log WARNING and exit 0 WITHOUT writing a Parquet (D-06; downstream API treats absence as all-sources-empty)
    - Print summary line: `consolidated N rows from {sources_present} sources → {output_path}` (use `logger.info` not `print` per .claude/rules/hooks.md)
    - Non-zero exit ONLY for argparse errors (invalid scoring format, etc.) — NEVER for upstream data absence
    - Integration test: `test_silver_cli_end_to_end_with_fixture_inputs` uses `tmp_path` to set `--out-root`, points `--season 2025 --week 1` at the fixtures from Task 1 via monkeypatched bronze_root/gold_root, asserts the output Parquet exists with ≥1 row from each present source
  </behavior>
  <action>
    1. Create `scripts/silver_external_projections_transformation.py`. Mirror the structure of `scripts/silver_player_transformation.py` (argparse, logging setup, `__main__` guard).
    2. Use `logger = logging.getLogger(__name__)` and `logging.basicConfig(level=logging.INFO)` in main only. NO `print()` statements (per Python hooks rule).
    3. Validate `--scoring` via `from src.config import SCORING_CONFIGS; if scoring not in SCORING_CONFIGS: parser.error(...)` — single source of truth.
    4. Output path construction with `datetime.utcnow().strftime("%Y%m%d_%H%M%S")`.
    5. Add 1 integration test to `tests/test_silver_external_projections.py`:
       - `test_silver_cli_end_to_end_with_fixture_inputs`: invoke `main(["--season", "2025", "--week", "1", "--scoring", "half_ppr", "--out-root", str(tmp_path)])` after monkeypatching the consolidator's bronze/gold roots to the fixtures dir; assert exactly one Parquet exists under `tmp_path/season=2025/week=1/`; assert the read DataFrame has ≥4 source values (or ≥3 if one source is intentionally missing in the fixture)
    6. Add 1 negative test:
       - `test_silver_cli_no_write_when_all_empty`: monkeypatch `SilverConsolidator.consolidate` to return empty DataFrame; assert no Parquet written under `tmp_path` and exit code 0
    7. Run `python -m pytest tests/test_silver_external_projections.py -v` — all 8 pass total.
    8. Manual sanity (optional): `python scripts/silver_external_projections_transformation.py --season 2025 --week 1 --scoring half_ppr` writes a Parquet (or logs WARNING if Bronze partitions empty).
  </action>
  <verify>
    <automated>python -m pytest tests/test_silver_external_projections.py -v</automated>
  </verify>
  <done>
    - CLI script exists and is invokable
    - 8 tests pass total in `tests/test_silver_external_projections.py`
    - No `print()` statements (uses `logger`)
    - D-06: all-empty case → exit 0, no Parquet written
    - Output partition path matches `data/silver/external_projections/season=YYYY/week=WW/external_projections_YYYYMMDD_HHMMSS.parquet`
    - `--scoring` validated against `src.config.SCORING_CONFIGS`
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Bronze Parquet → Silver merge | Untrusted upstream data crosses into the canonical Silver schema |
| Gold projections → Silver merge | Internal-but-decoupled — Gold may have schema changes |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-73-02-01 | Tampering | Bronze ESPN/Sleeper/FP DataFrame | mitigate | `to_long_format` enforces target dtypes (`projected_points: float`); rows with non-coercible values are dropped with WARNING |
| T-73-02-02 | Denial of Service | Reading all 4 sources eagerly | accept | Each Bronze partition is small (~32 teams × 5 positions = ~160 rows); total ~640 rows. Memory footprint negligible. |
| T-73-02-03 | Information Disclosure | raw_payload column carried through | mitigate | Silver schema EXCLUDES raw_payload — only the 9 target columns are written. Bronze remains the raw audit trail. |
| T-73-02-04 | Repudiation | source label collision | mitigate | Source values restricted to {"ours","espn","sleeper","yahoo_proxy_fp"} via the enum-style assertion in `to_long_format` (warn-and-drop unknown sources) |
| T-73-02-05 | Tampering | Player_id resolution drift | mitigate | PlayerNameResolver is the single resolution point; rows that remain unresolvable are kept with `player_id=""` so the comparison API can still display by name (degraded but visible) |
</threat_model>

<verification>
- All 8 Silver tests green: `python -m pytest tests/test_silver_external_projections.py -v`
- Flake8 clean: `python -m flake8 src/external_projections.py scripts/silver_external_projections_transformation.py`
- Black formatted: `python -m black src/external_projections.py scripts/silver_external_projections_transformation.py --check`
- No regression in existing tests: `python -m pytest tests/ -q -x`
</verification>

<success_criteria>
- [x] `SilverConsolidator` class encapsulates all 4-source merge logic
- [x] CLI script writes Silver Parquet with the 9-column long-format schema
- [x] D-06 fail-open: all-empty + per-source-empty both handled without raising
- [x] PlayerNameResolver bridges Bronze names → gsis player_ids
- [x] No new print() — logging throughout
- [x] 8 tests pass; no regressions in full suite
</success_criteria>

<output>
After completion, create `.planning/phases/73-external-projections-comparison/73-02-SUMMARY.md` summarizing: module + script created, Silver schema written, requirements covered (EXTP-02), and the input contract Wave 3 (API) consumes.
</output>
