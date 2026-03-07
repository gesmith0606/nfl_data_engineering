# Codebase Concerns

**Analysis Date:** 2026-03-07

## Tech Debt

**Hardcoded Season Upper Bound:**
- Issue: `NFLDataFetcher.available_seasons` is hardcoded as `range(1999, 2026)` and the validation check on line 365 rejects seasons > 2025. The CLAUDE.md and MEMORY.md state valid seasons go to 2026, but the code caps at 2025. This must be manually bumped each year.
- Files: `src/nfl_data_integration.py` (lines 21, 365)
- Impact: Fetching data for the 2026 season will silently filter it out or raise validation warnings. Draft assistant defaults to `--season 2026` which would be rejected.
- Fix approach: Replace hardcoded upper bound with `datetime.date.today().year + 1` or a config constant in `src/config.py`.

**GHA Workflow Hardcoded to Season 2024:**
- Issue: `DEFAULT_SEASON` in `.github/workflows/weekly-pipeline.yml` is `"2024"`. The auto-compute logic handles this correctly for most cases, but the fallback default is stale.
- Files: `.github/workflows/weekly-pipeline.yml` (line 42)
- Impact: If auto-compute fails, pipeline falls back to 2024 season data.
- Fix approach: Remove the hardcoded default or make it dynamic.

**sys.path.insert Hack Across All Scripts:**
- Issue: Every script in `scripts/` uses `sys.path.insert(0, ...)` to import from `src/`. This is brittle and prevents the project from being installed as a proper Python package.
- Files: `scripts/generate_projections.py` (line 23), `scripts/backtest_projections.py` (line 23), `scripts/refresh_adp.py` (line 24), `scripts/check_pipeline_health.py` (line 28), `scripts/silver_player_transformation.py` (line 26), `scripts/draft_assistant.py` (line 32)
- Impact: Import order issues, IDE confusion, no `pip install -e .` support, fragile relative path resolution.
- Fix approach: Add a `pyproject.toml` or `setup.py` with `src` as the package root. Use `pip install -e .` in the venv. Remove all `sys.path.insert` calls.

**PySpark Dead Code in utils.py:**
- Issue: `src/utils.py` contains PySpark functions (`get_spark_session`, `pandas_to_spark`, `add_audit_columns`, `validate_game_data_quality`) that are never called anywhere in the codebase. The project uses pandas exclusively.
- Files: `src/utils.py` (lines 26-148)
- Impact: ~120 lines of dead code; the guarded PySpark import on line 14-20 catches all exceptions including `ImportError`, which could mask real import errors. The broad `except (ImportError, Exception)` is equivalent to bare `except`.
- Fix approach: Remove PySpark functions entirely. If PySpark support is needed in the future, add it to a separate module.

**Duplicate Data Prep Functions:**
- Issue: `_prepare_weekly_data()` and `_prepare_weekly()` are near-identical functions that map `receiving_air_yards` to `air_yards`. They exist independently in two scripts.
- Files: `scripts/silver_player_transformation.py` (lines 42-51), `scripts/backtest_projections.py` (lines 97-103)
- Impact: If the column mapping logic changes, both must be updated. Risk of drift.
- Fix approach: Move to a shared utility function in `src/utils.py` or `src/player_analytics.py`.

**Databricks Config Never Used:**
- Issue: `DATABRICKS_CLUSTER_ID` and `DATABRICKS_WORKSPACE_URL` are defined in `src/config.py` but never referenced anywhere else in the codebase.
- Files: `src/config.py` (lines 28-29)
- Impact: Confusing for new contributors; suggests a Databricks integration that does not exist.
- Fix approach: Remove these constants.

## Known Bugs

**Double Fantasy Points Calculation After Vegas Adjustment:**
- Symptoms: In `generate_weekly_projections()`, fantasy points are calculated once inside `project_position()` (line 449-451, including shrinkage), then the Vegas multiplier scales the projected stats and recalculates points (lines 604-611). The second calculation does NOT re-apply the ceiling shrinkage, creating inconsistency: Vegas-adjusted projections skip the regression-to-mean shrinkage that non-Vegas projections receive.
- Files: `src/projection_engine.py` (lines 592-611 vs. 456-463)
- Trigger: Provide `implied_totals` to `generate_weekly_projections()`.
- Workaround: The shrinkage is partially redundant since Vegas scaling usually reduces high projections, but the logic path differs.

**Rename Collision in Vegas Recalculation:**
- Symptoms: The Vegas recalculation block (lines 604-611) renames `proj_*` columns to raw stat names for scoring, but does not drop the original raw stat columns first (unlike `project_position()` which does on line 447). If the DataFrame still has original raw stat columns from Silver data, the rename creates duplicates or overwrites them.
- Files: `src/projection_engine.py` (lines 604-611)
- Trigger: When Silver DataFrame columns like `passing_yards`, `rushing_yards` survive into the combined projection DataFrame.
- Workaround: Currently works because `pd.concat` on per-position DataFrames usually drops the raw columns, but this is fragile.

**DraftBoard.remaining_needs() FLEX Logic Is Broken:**
- Symptoms: The FLEX slot calculation on lines 213-217 has a logical error. The condition `p.get('position') not in ['RB', 'WR', 'TE'] or self._used_as_flex(p)` always evaluates True for non-FLEX-eligible positions and calls `_used_as_flex` only as an OR fallback. The result is that FLEX needs are incorrectly computed.
- Files: `src/draft_optimizer.py` (lines 213-217)
- Trigger: Drafting multiple RB/WR/TE players in an interactive session.
- Workaround: The draft assistant still works because recommendations use `recommendation_score` which bypasses FLEX counting.

## Security Considerations

**Broad Exception Catching Masks Errors:**
- Risk: Multiple `except Exception` blocks silently swallow errors and return empty DataFrames or None. This can mask credential errors, network failures, or data corruption.
- Files: `src/nfl_data_integration.py` (11 instances), `src/utils.py` (4 instances), `scripts/silver_player_transformation.py` (lines 118, 177, 260)
- Current mitigation: Errors are logged before re-raising in `nfl_data_integration.py`, but scripts like `silver_player_transformation.py` silently swallow on lines 118 and 260.
- Recommendations: Use specific exception types. At minimum, distinguish `ClientError` (AWS), `ImportError`, and `ValueError` from unexpected exceptions.

**AWS Credentials Expired:**
- Risk: AWS credentials expired in March 2026 per MEMORY.md. The pipeline workflow and any S3 operations will fail silently (scripts fall back to local data or nfl-data-py).
- Files: `.github/workflows/weekly-pipeline.yml`, all scripts with S3 upload logic
- Current mitigation: Local-first data reads with S3 fallback implemented in key scripts.
- Recommendations: Rotate AWS credentials and update GitHub Secrets. Consider using IAM roles instead of static keys.

**Embedded Test Function in Production Module:**
- Risk: `src/nfl_data_integration.py` contains a `test_nfl_data_integration()` function (lines 378-433) with `if __name__ == "__main__"` that makes live API calls. This is not a unit test and could be accidentally invoked.
- Files: `src/nfl_data_integration.py` (lines 378-433)
- Current mitigation: Only runs when module is executed directly.
- Recommendations: Move to `scripts/` or delete in favor of the proper test suite in `tests/`.

## Performance Bottlenecks

**Row-by-Row Vegas Multiplier via DataFrame.apply():**
- Problem: `generate_weekly_projections()` uses `combined.apply(lambda row: _vegas_multiplier(...), axis=1)` to compute Vegas multipliers. `apply(axis=1)` is slow on large DataFrames.
- Files: `src/projection_engine.py` (lines 572-580)
- Cause: `_vegas_multiplier()` is a scalar function applied row-by-row via lambda.
- Improvement path: Vectorize by mapping team to implied total using `pd.Series.map()`, then compute the multiplier as a vectorized expression.

**Row-by-Row Spread Computation:**
- Problem: `_build_spread_by_team()` iterates over schedule rows with `iterrows()` to build a dict.
- Files: `src/projection_engine.py` (lines 814-819)
- Cause: `iterrows()` is inherently slow in pandas.
- Improvement path: Use `set_index` + `to_dict()` or vectorized operations.

**Row-by-Row Implied Totals Computation:**
- Problem: `compute_implied_team_totals()` in `player_analytics.py` uses `iterrows()` (line 356) to build the implied totals dict.
- Files: `src/player_analytics.py` (lines 355-358)
- Cause: Same `iterrows()` anti-pattern.
- Improvement path: Use `pd.Series` operations with `set_index()`.

**Rookie Baseline Fill via Individual Cell Assignment:**
- Problem: `project_position()` fills rookie baselines using `pos_df.at[idx, col] = value` in nested loops (lines 405-415). For large numbers of rookies, this is O(n * stats * suffixes) individual cell writes.
- Files: `src/projection_engine.py` (lines 405-415)
- Cause: Per-cell assignment instead of batch DataFrame operations.
- Improvement path: Build a DataFrame of baseline values and use `pd.DataFrame.update()` or `fillna()`.

## Fragile Areas

**Column Name Assumptions Across Layers:**
- Files: `src/player_analytics.py` (line 89: expects `snap_pct`), `scripts/silver_player_transformation.py` (lines 60-69: maps `offense_pct` to `snap_pct`, `player` to `player_id`)
- Why fragile: The snap counts schema from `nfl-data-py` uses `offense_pct` and `player` (not `snap_pct` and `player_id`). The mapping happens only in the Silver transformation script. If any code path reads snap data without going through `_prepare_snap_data()`, it will silently produce NaN values.
- Safe modification: Always run column mapping through a centralized function. Add schema validation at layer boundaries.
- Test coverage: `tests/test_player_analytics.py` tests `compute_usage_metrics` but mocks snap data with pre-mapped column names, so schema drift is not caught.

**Injury Join Column Resolution:**
- Files: `src/projection_engine.py` (lines 732-746)
- Why fragile: `apply_injury_adjustments()` has a complex chain of if/elif logic to determine the join column between projections and injuries DataFrames. The fallback chain (`gsis_id` -> `player_id` -> `player_name`) depends on which columns exist in both DataFrames, which varies by data source (nfl-data-py vs. local Bronze vs. S3).
- Safe modification: Standardize on `player_id` as the canonical join key across all layers. Add a validation step that ensures `player_id` exists before reaching the projection engine.
- Test coverage: Tests use `player_name` join. No tests cover the `gsis_id` or `player_id` join paths.

**Preseason Projections Group-By Instability:**
- Files: `src/projection_engine.py` (lines 869-877)
- Why fragile: `generate_preseason_projections()` dynamically builds `group_cols` by checking if `player_name` and `recent_team` exist in the DataFrame. If a player changes teams between seasons, `recent_team` in `group_cols` causes that player to appear as two separate entries rather than being aggregated.
- Safe modification: Group only by `player_id` and `position`. Resolve `recent_team` and `player_name` by taking the most recent season's values.
- Test coverage: No tests for `generate_preseason_projections()`.

## Scaling Limits

**In-Memory DataFrame Processing:**
- Current capacity: The pipeline processes ~7 MB Bronze, ~4.2 MB Silver data entirely in memory using pandas. This works for 5-6 seasons of NFL data (~100K player-week rows).
- Limit: If historical data grows significantly (e.g., including play-by-play at ~500 MB/season), pandas will hit memory limits.
- Scaling path: The PySpark infrastructure exists in `src/utils.py` but is unused. For the current scope (player stats, not PBP), pandas is sufficient. For PBP analysis, consider DuckDB (already configured as an MCP) or chunked reading.

**Local Data Storage Without Cleanup:**
- Current capacity: 11+ MB across Bronze/Silver/Gold local directories.
- Limit: Each pipeline run appends a new timestamped file. Over months of weekly runs, the local `data/` directory will accumulate hundreds of files.
- Scaling path: Add a cleanup step that retains only the latest N files per partition, mirroring the `download_latest_parquet()` read pattern.

## Dependencies at Risk

**nfl-data-py API Schema Changes:**
- Risk: The project depends on `nfl-data-py` for all data ingestion. Column names like `receiving_air_yards`, `offense_pct`, and `fantasy_points_ppr` come from this library. If the upstream schema changes, multiple modules break silently (returning NaN or empty DataFrames instead of erroring).
- Impact: All Bronze ingestion, Silver transformation, and backtesting would produce incorrect results.
- Migration plan: Pin `nfl-data-py` version in `requirements.txt`. Add schema validation assertions at ingestion time (e.g., assert expected columns exist before writing to Bronze).

**dotenv Dependency Without Fallback:**
- Risk: Scripts import `from dotenv import load_dotenv` unconditionally. If `python-dotenv` is not installed, all CLI scripts fail at import time.
- Impact: `scripts/draft_assistant.py`, `scripts/generate_projections.py`, `scripts/silver_player_transformation.py`
- Migration plan: Already in `requirements.txt`, but add a guarded import or make it optional since env vars can be set directly.

## Test Coverage Gaps

**No Tests for CLI Scripts:**
- What's not tested: All 8 scripts in `scripts/` have zero test coverage. The `main()` functions, argument parsing, local/S3 data loading logic, and output writing are untested.
- Files: `scripts/generate_projections.py`, `scripts/silver_player_transformation.py`, `scripts/draft_assistant.py`, `scripts/backtest_projections.py`, `scripts/bronze_ingestion_simple.py`, `scripts/refresh_adp.py`, `scripts/check_pipeline_health.py`, `scripts/validate_project.py`
- Risk: Refactoring scripts could break CLI behavior without detection. The Silver transformation script's data loading and fallback logic is particularly critical.
- Priority: Medium - the core `src/` modules have good coverage (71 tests), but integration-level script testing is missing.

**No Tests for generate_preseason_projections():**
- What's not tested: The entire preseason projection path, which is used by the draft assistant.
- Files: `src/projection_engine.py` (lines 824-904)
- Risk: Changes to seasonal data schema or weighted averaging logic could break draft prep without detection.
- Priority: High - this function drives the draft assistant, the most user-facing feature.

**No Tests for generate_weekly_projections() End-to-End:**
- What's not tested: The full weekly projection pipeline including bye week zeroing, Vegas adjustment, and injury adjustment integration. Individual components are tested, but the combined flow is not.
- Files: `src/projection_engine.py` (lines 468-654)
- Risk: Integration bugs (like the double-calculation issue noted above) are not caught.
- Priority: High - this is the core projection pipeline.

**No Tests for MockDraftSimulator or AuctionDraftBoard:**
- What's not tested: `MockDraftSimulator.run_full_simulation()`, `AuctionDraftBoard.win_bid()`, `AuctionDraftBoard.value_vs_cost()`, `AuctionDraftBoard.budget_summary()`
- Files: `src/draft_optimizer.py` (lines 424-857)
- Risk: Auction draft and mock simulation features could regress silently.
- Priority: Medium - these are secondary features.

**DraftBoard.undo Test Is Conditional:**
- What's not tested: The test for undo (line 101 in `tests/test_draft_optimizer.py`) checks `if hasattr(board, 'undo_last_pick')` and skips if the method doesn't exist. The method does NOT exist on `DraftBoard` -- undo is implemented only in the CLI script via direct list manipulation.
- Files: `tests/test_draft_optimizer.py` (lines 97-104), `scripts/draft_assistant.py` (lines 710-718)
- Risk: The undo logic in the CLI is untested and fragile (directly manipulates `board.my_roster` and `board.available`).
- Priority: Low - undo is a convenience feature.

---

*Concerns audit: 2026-03-07*
