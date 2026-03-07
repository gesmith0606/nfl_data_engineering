# Codebase Structure

**Analysis Date:** 2026-03-07

## Directory Layout

```
nfl_data_engineering/
├── src/                            # Core library modules
│   ├── __init__.py                 # Package marker
│   ├── config.py                   # Centralized configuration (S3 paths, scoring, roster configs)
│   ├── nfl_data_integration.py     # NFLDataFetcher class — all data ingestion methods
│   ├── player_analytics.py         # Silver-layer analytics (usage, rankings, rolling avgs)
│   ├── scoring_calculator.py       # Fantasy point calculation (dict + vectorized DataFrame)
│   ├── projection_engine.py        # Weekly/preseason projection generation
│   ├── draft_optimizer.py          # Draft board, auction, mock draft, advisor classes
│   └── utils.py                    # S3 helpers (get_latest_s3_key, download_latest_parquet)
├── scripts/                        # CLI entry points for pipeline stages
│   ├── bronze_ingestion_simple.py  # Bronze layer ingestion (8 data types)
│   ├── silver_player_transformation.py  # Silver layer transformation
│   ├── generate_projections.py     # Gold layer projection generation
│   ├── draft_assistant.py          # Interactive draft CLI
│   ├── backtest_projections.py     # Projection accuracy backtesting
│   ├── refresh_adp.py              # Fetch ADP from Sleeper API
│   ├── check_pipeline_health.py    # S3 freshness/size validation
│   ├── validate_project.py         # Project-level validation script
│   ├── expand_bronze_layer.py      # Legacy: Bronze layer expansion
│   ├── explore_bronze_data.py      # Legacy: Bronze data exploration
│   ├── list_bronze_contents.py     # Legacy: List Bronze S3 contents
│   ├── test_aws_connectivity.py    # Legacy: AWS connectivity test
│   ├── test_aws_direct.py          # Legacy: Direct AWS test
│   ├── test_nfl_data.py            # Legacy: NFL data test
│   ├── test_s3_full_operations.py  # Legacy: S3 full operations test
│   └── test_s3_permissions.py      # Legacy: S3 permissions test
├── tests/                          # Unit test suite (71 tests)
│   ├── __init__.py                 # Package marker
│   ├── test_scoring_calculator.py  # 14 tests — scoring formats, edge cases
│   ├── test_projection_engine.py   # 19 tests — bye weeks, rookies, Vegas, injuries
│   ├── test_player_analytics.py    # 7 tests — usage metrics, rolling avgs
│   ├── test_draft_optimizer.py     # 13 tests — board, advisor, waiver, values
│   └── test_utils.py              # 5 tests — S3 paths, validation
├── data/                           # Local data storage (mirrors S3 structure)
│   ├── bronze/                     # Raw ingested data
│   │   ├── games/season=YYYY/      # Game schedules
│   │   └── players/                # Player data by type
│   │       ├── weekly/season=YYYY/ # Weekly player stats
│   │       ├── seasonal/season=YYYY/  # Season aggregates
│   │       ├── snap_counts/season=YYYY/  # Snap participation
│   │       ├── injuries/season=YYYY/    # Injury reports
│   │       └── rosters/season=YYYY/     # Team rosters
│   ├── silver/                     # Transformed analytics data
│   │   ├── players/usage/season=YYYY/   # Usage metrics
│   │   └── defense/positional/season=YYYY/  # Opponent rankings
│   └── gold/                       # Projection output
│       └── projections/season=YYYY/week=WW/  # Weekly projections
├── output/                         # Non-data output files
│   ├── backtest/                   # Backtest result CSVs
│   └── projections/                # Projection export CSVs
├── .github/
│   └── workflows/
│       └── weekly-pipeline.yml     # Tuesday cron: Bronze→Silver→Gold
├── docs/                           # Documentation files
├── notebooks/                      # Jupyter notebooks (exploration)
├── .claude/                        # Claude AI configuration
│   ├── rules/                      # Agent rules and workflows
│   └── AGENT_FRAMEWORK.md          # Agent workflow documentation
├── CLAUDE.md                       # Claude project instructions
├── requirements.txt                # Python dependencies
├── setup.sh                        # Environment setup script
├── .env                            # Environment variables (gitignored)
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore rules
├── .claudeignore                   # Claude context exclusions
└── .mcp.json                       # MCP server configuration
```

## Directory Purposes

**`src/`:**
- Purpose: Core library code — all business logic lives here
- Contains: Python modules (no sub-packages, flat structure)
- Key files: `config.py` (constants), `nfl_data_integration.py` (data fetching), `player_analytics.py` (Silver transforms), `projection_engine.py` (Gold projections), `scoring_calculator.py` (fantasy points), `draft_optimizer.py` (draft tools), `utils.py` (S3 helpers)
- Import convention: Scripts add `src/` to `sys.path` and import modules directly (no package install)

**`scripts/`:**
- Purpose: CLI entry points that orchestrate pipeline stages
- Contains: Executable Python scripts with `argparse` interfaces
- Active scripts: `bronze_ingestion_simple.py`, `silver_player_transformation.py`, `generate_projections.py`, `draft_assistant.py`, `backtest_projections.py`, `refresh_adp.py`, `check_pipeline_health.py`, `validate_project.py`
- Legacy scripts: `expand_bronze_layer.py`, `explore_bronze_data.py`, `list_bronze_contents.py`, `test_aws_*.py`, `test_nfl_data.py` — kept for reference but not part of active pipeline

**`tests/`:**
- Purpose: Unit tests using pytest
- Contains: Test files mirroring `src/` module names with `test_` prefix
- Pattern: One test file per `src/` module (except `config.py` and `nfl_data_integration.py`)

**`data/`:**
- Purpose: Local data storage mirroring S3 bucket structure
- Contains: Parquet files organized by layer → dataset → Hive-style partitions
- Partition pattern: `season=YYYY/` or `season=YYYY/week=WW/`
- File naming: `{type}_{YYYYMMDD_HHMMSS}.parquet` (timestamped for versioning)
- Generated: Yes — created by pipeline scripts
- Committed: No — excluded via `.gitignore` and `.claudeignore`

**`output/`:**
- Purpose: Human-readable exports (CSV) and backtest results
- Contains: CSV files from projection/backtest runs
- Generated: Yes
- Committed: No

## Key File Locations

**Entry Points:**
- `scripts/bronze_ingestion_simple.py`: Bronze layer data ingestion CLI
- `scripts/silver_player_transformation.py`: Silver layer transformation CLI
- `scripts/generate_projections.py`: Gold layer projection generation CLI
- `scripts/draft_assistant.py`: Interactive draft assistant CLI
- `scripts/backtest_projections.py`: Projection backtesting CLI

**Configuration:**
- `src/config.py`: S3 buckets, scoring configs (`SCORING_CONFIGS`), roster formats (`ROSTER_CONFIGS`), S3 key templates, `PLAYER_DATA_SEASONS`
- `.env`: AWS credentials, Databricks config (gitignored)
- `.env.example`: Template for required environment variables
- `.mcp.json`: MCP server configuration for Claude
- `requirements.txt`: Python package dependencies

**Core Logic:**
- `src/nfl_data_integration.py`: `NFLDataFetcher` class — all 8 data fetch methods + validation
- `src/player_analytics.py`: Silver-layer analytics functions (usage, rankings, rolling averages, game script, venue splits, Vegas implied totals)
- `src/projection_engine.py`: Projection model — weighted baselines, multipliers, rookie fallbacks, bye weeks, injury adjustments, floor/ceiling
- `src/scoring_calculator.py`: Fantasy point calculation — single-dict and vectorized DataFrame modes
- `src/draft_optimizer.py`: `DraftBoard`, `AuctionDraftBoard`, `MockDraftSimulator`, `DraftAdvisor`
- `src/utils.py`: S3 helpers — `get_latest_s3_key()`, `download_latest_parquet()`, `validate_s3_path()`

**Testing:**
- `tests/test_scoring_calculator.py`: 14 tests covering all scoring formats and edge cases
- `tests/test_projection_engine.py`: 19 tests covering bye weeks, rookies, Vegas, usage, injury adjustments
- `tests/test_player_analytics.py`: 7 tests for usage metrics, rolling averages, implied totals
- `tests/test_draft_optimizer.py`: 13 tests for board operations, advisor, waiver, value scores
- `tests/test_utils.py`: 5 tests for S3 path validation and utilities

**CI/CD:**
- `.github/workflows/weekly-pipeline.yml`: Tuesday cron pipeline — compute week → Bronze → Silver → Gold → health check → failure notification

## Naming Conventions

**Files:**
- Source modules: `snake_case.py` (e.g., `player_analytics.py`, `scoring_calculator.py`)
- Scripts: `snake_case.py` with descriptive names (e.g., `bronze_ingestion_simple.py`, `generate_projections.py`)
- Tests: `test_{module_name}.py` matching the `src/` module (e.g., `test_scoring_calculator.py`)
- Data files: `{type}_{YYYYMMDD_HHMMSS}.parquet` with timestamp suffix

**Directories:**
- Source: `src/` (flat, no sub-packages)
- Scripts: `scripts/` (flat)
- Tests: `tests/` (flat)
- Data: Hive-style partitions — `season=YYYY/week=WW/`

**Functions:**
- Public: `snake_case` (e.g., `compute_usage_metrics()`, `generate_weekly_projections()`)
- Private/internal: `_snake_case` with leading underscore (e.g., `_weighted_baseline()`, `_usage_multiplier()`)

**Classes:**
- `PascalCase` (e.g., `NFLDataFetcher`, `DraftBoard`, `AuctionDraftBoard`, `MockDraftSimulator`, `DraftAdvisor`)

**Constants:**
- `UPPER_SNAKE_CASE` (e.g., `SCORING_CONFIGS`, `RECENCY_WEIGHTS`, `POSITION_STAT_PROFILE`, `REPLACEMENT_RANKS`)

## Where to Add New Code

**New Data Source (Bronze):**
- Add fetch method to `src/nfl_data_integration.py` → `NFLDataFetcher` class
- Add S3 key template to `src/config.py` → `PLAYER_S3_KEYS`
- Add data type to `scripts/bronze_ingestion_simple.py` → `ALL_DATA_TYPES` list
- Add required columns to `NFLDataFetcher.validate_data()` → `required_columns` dict
- Add tests to `tests/` as `test_{module}.py`

**New Analytics Metric (Silver):**
- Add function to `src/player_analytics.py` following pattern: takes DataFrame(s), returns enriched DataFrame
- Call from `scripts/silver_player_transformation.py`
- Add S3 key template to `src/config.py` → `SILVER_PLAYER_S3_KEYS` if new output type

**New Projection Feature (Gold):**
- Add to `src/projection_engine.py` — new multiplier or adjustment function
- Wire into `generate_weekly_projections()` or `generate_preseason_projections()`
- Add tests to `tests/test_projection_engine.py`

**New Scoring Rule:**
- Add format to `src/config.py` → `SCORING_CONFIGS` dict
- No other changes needed — `scoring_calculator.py` is config-driven

**New Draft Feature:**
- Add to `src/draft_optimizer.py` — extend `DraftBoard` or `DraftAdvisor`
- Wire into `scripts/draft_assistant.py` interactive loop
- Add tests to `tests/test_draft_optimizer.py`

**New CLI Script:**
- Create in `scripts/` following existing pattern:
  1. Add `sys.path.insert(0, ...)` for `src/` imports
  2. Use `argparse` for CLI interface
  3. Use `load_dotenv()` for environment variables
  4. Define `main()` function with `if __name__ == '__main__': main()`

**New Utility Function:**
- Add to `src/utils.py` for S3/infrastructure helpers
- Add to the relevant `src/` module for domain-specific utilities

## Special Directories

**`data/`:**
- Purpose: Local mirror of S3 data lake (Bronze/Silver/Gold layers)
- Generated: Yes — by pipeline scripts
- Committed: No — excluded by `.gitignore`
- Size: ~11 MB total (7 MB Bronze, 4.2 MB Silver)

**`output/`:**
- Purpose: CSV exports from backtesting and projection runs
- Generated: Yes
- Committed: No — excluded by `.gitignore`

**`venv/`:**
- Purpose: Python virtual environment
- Generated: Yes — by `setup.sh` or manual `python -m venv venv`
- Committed: No

**`.claude/`:**
- Purpose: Claude AI agent configuration, rules, and workflow definitions
- Generated: Partially (review history is generated)
- Committed: Yes (rules and agent configs)

**`.planning/`:**
- Purpose: GSD planning documents and codebase analysis
- Generated: Yes — by GSD commands
- Committed: Yes

---

*Structure analysis: 2026-03-07*
