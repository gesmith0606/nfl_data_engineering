# Coding Conventions

**Analysis Date:** 2026-03-07

## Naming Patterns

**Files:**
- Source modules: `snake_case.py` (e.g., `src/scoring_calculator.py`, `src/player_analytics.py`)
- Scripts: `snake_case.py` with verb-noun pattern (e.g., `scripts/bronze_ingestion_simple.py`, `scripts/generate_projections.py`)
- Tests: `test_<module_name>.py` mirroring source module name (e.g., `tests/test_scoring_calculator.py`)

**Functions:**
- Public functions: `snake_case` with verb prefix (e.g., `calculate_fantasy_points`, `compute_usage_metrics`, `generate_weekly_projections`)
- Private/internal functions: `_leading_underscore` (e.g., `_weighted_baseline`, `_usage_multiplier`, `_rookie_baseline`, `_vegas_multiplier`)
- Helper methods in classes: `snake_case` with verb prefix (e.g., `fetch_game_schedules`, `validate_data`)

**Variables:**
- Local variables: `snake_case` (e.g., `target_df`, `bye_teams`, `scoring_input`)
- Module-level constants: `UPPER_SNAKE_CASE` (e.g., `RECENCY_WEIGHTS`, `FANTASY_POSITIONS`, `INJURY_MULTIPLIERS`)
- Private module constants: `_LEADING_UPPER_SNAKE` (e.g., `_STARTER_BASELINES`, `_ROLE_SCALE`, `_LEAGUE_AVG_IMPLIED_TOTAL`, `_FLOOR_CEILING_MULT`)
- DataFrames: descriptive `snake_case` with `_df` suffix for function parameters (e.g., `silver_df`, `opp_rankings`, `schedules_df`)

**Types:**
- Classes: `PascalCase` (e.g., `NFLDataFetcher`, `DraftBoard`, `DraftAdvisor`, `MockDraftSimulator`)
- Type aliases: Use `typing` module types directly in signatures (e.g., `Dict[str, float]`, `Optional[pd.DataFrame]`)

## Code Style

**Formatting:**
- Tool: `black` (run via `python -m black src/ tests/ scripts/`)
- Line length: black default (88 characters)
- No `pyproject.toml` or `setup.cfg` configuration file detected -- uses black defaults

**Linting:**
- Tool: `flake8` (run via `python -m flake8 src/ tests/ scripts/`)
- No `.flake8` config file detected -- uses flake8 defaults

**Pre-commit:**
- Custom pre-commit hook at `.git/hooks/pre-commit`
- Credential scan: blocks AWS keys (`AKIA...`), GitHub PATs, SSH private keys
- Automated code review via `.claude/workflows/automated-code-review.py`

## Import Organization

**Order:**
1. Standard library imports (`sys`, `os`, `logging`, `datetime`, `json`)
2. Third-party imports (`pandas as pd`, `numpy as np`, `boto3`)
3. Local/project imports (`from config import SCORING_CONFIGS`, `from scoring_calculator import calculate_fantasy_points_df`)

**Common aliases:**
- `import pandas as pd`
- `import numpy as np`
- `import nfl_data_py as nfl`

**Path manipulation for imports:**
- Scripts use `sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))` or `'..', 'src'`
- Tests use `sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))`
- Source modules import siblings directly: `from config import SCORING_CONFIGS`

**Path Aliases:**
- None. No `pyproject.toml` path config or importlib customization.

## Error Handling

**Patterns:**
- **Try/except with logging + re-raise** for critical operations (S3, API calls):
  ```python
  try:
      df = nfl.import_weekly_data(valid_seasons)
  except Exception as e:
      logger.error(f"Error fetching player weekly stats: {str(e)}")
      raise
  ```
- **ValueError for invalid inputs** with descriptive messages:
  ```python
  if scoring_format not in SCORING_CONFIGS:
      raise ValueError(f"Unknown scoring format: {scoring_format}. "
                       f"Choose from {list(SCORING_CONFIGS.keys())} or 'custom'.")
  ```
- **Graceful fallback with warnings** for missing optional data:
  ```python
  if schedules_df is None:
      bye_teams = set()  # skip bye detection
  ```
- **Empty DataFrame return** when no data available (never raise on missing data):
  ```python
  if pos_df.empty:
      return pd.DataFrame()
  ```
- **`fillna()` with sensible defaults** for missing values in computations:
  ```python
  opp_rank = merged['opp_rank'].fillna(16)  # neutral if not found
  ```

## Logging

**Framework:** Python `logging` module (standard library)

**Setup pattern:**
```python
import logging
logger = logging.getLogger(__name__)
```

**Root config** (set in `src/utils.py` and `src/nfl_data_integration.py`):
```python
logging.basicConfig(level=logging.INFO)
```

**Patterns:**
- Use `logger.info()` for operation summaries with counts: `logger.info(f"Fetched {len(df)} player-week rows")`
- Use `logger.warning()` for fallbacks and missing optional data: `logger.warning("No injury data provided; all players treated as Active")`
- Use `logger.error()` for failures before re-raising: `logger.error(f"Error fetching player weekly stats: {str(e)}")`
- Use `logger.debug()` for detailed internal state: `logger.debug("No baseline defined for position '%s'", position)`
- Use f-strings for most log messages; use `%s` formatting for debug-level messages

## Comments

**When to Comment:**
- Section dividers using `# ---------------------------------------------------------------------------` bars in longer modules
- Inline comments for non-obvious business logic (e.g., `# WOPR is a composite air-yards+target metric`)
- Backtest-derived constants include rationale comments:
  ```python
  # Backtest shows projections above 15 pts systematically overshoot.
  PROJECTION_CEILING_SHRINKAGE = {
      15.0: 0.90,   # projections 15-20 pts -> multiply by 0.90
  ```

**Docstrings:**
- Google-style docstrings on all public and private functions
- Include `Args:`, `Returns:`, and often `Example:` sections
- Document edge cases and fallback behavior in docstrings
- Module-level docstrings describe the module's purpose and approach
- Example pattern from `src/projection_engine.py`:
  ```python
  def get_bye_teams(schedules_df: pd.DataFrame, week: int) -> set:
      """
      Return the set of team abbreviations that have a bye in the given week.

      Args:
          schedules_df: Game schedule DataFrame from ``nfl.import_schedules()``.
          week:         The NFL week number to check (1-based).

      Returns:
          Set of team abbreviations on bye.

      Example:
          >>> bye_teams = get_bye_teams(schedules_df, week=9)
          >>> 'KC' in bye_teams
          True
      """
  ```

## Function Design

**Size:** Functions are typically 20-60 lines. Larger orchestration functions (`generate_weekly_projections` at ~180 lines) are broken into numbered sections with comment headers.

**Parameters:**
- Use type hints on all parameters and return types
- Use `Optional[T]` for parameters that can be `None` (Python 3.9 compatible -- no `T | None` syntax)
- Default parameter values for scoring format: `scoring_format: str = "half_ppr"`
- DataFrames as primary input/output type for all data processing functions

**Return Values:**
- Data processing functions return `pd.DataFrame` (empty DataFrame on no-data, never None)
- Lookup functions return `Dict` or `set`
- Scalar computations return `float` (rounded via `round(value, N)`)
- Validation functions return `Dict[str, Any]` with structured results

## Module Design

**Exports:**
- No explicit `__all__` in any module
- All public functions are importable directly from the module
- Private functions prefixed with `_` but still imported in tests for unit testing

**Barrel Files:**
- `src/__init__.py` contains only a comment: `# NFL Data Engineering Pipeline`
- `tests/__init__.py` is present (empty or minimal)
- No barrel re-exports -- each module is imported directly

**Module organization pattern:**
1. Module docstring
2. Imports (stdlib, third-party, local)
3. Module-level constants (public `UPPER_CASE`, private `_UPPER_CASE`)
4. Private helper functions (`_underscore_prefix`)
5. Public functions/classes
6. `if __name__ == '__main__':` block (in some modules)

## DataFrame Conventions

**Always copy input DataFrames** before mutation:
```python
df = weekly_df.copy()
```

**Column naming:** Use `snake_case` for all DataFrame columns (e.g., `target_share`, `rushing_yards`, `projected_points`)

**Projected stat columns** use `proj_` prefix (e.g., `proj_rushing_yards`, `proj_passing_tds`)

**Boolean flag columns** use `is_` prefix (e.g., `is_bye_week`, `is_rookie_projection`, `is_home`, `is_dome`)

**Storage format:** Always Parquet, partitioned by `season/week`

---

*Convention analysis: 2026-03-07*
