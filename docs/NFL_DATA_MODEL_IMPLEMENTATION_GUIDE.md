# NFL Data Platform Implementation Guide

**Version:** 5.0
**Last Updated:** March 28, 2026
**Purpose:** Living roadmap for the NFL data platform -- grounded in actual accomplishments, forward-looking for planned work
**Related Documents:**
- [NFL_GAME_PREDICTION_DATA_MODEL.md](./NFL_GAME_PREDICTION_DATA_MODEL.md) -- Data model with implementation status badges
- [NFL_DATA_DICTIONARY.md](./NFL_DATA_DICTIONARY.md) -- Full column specs for all data types

## Tech Stack

| Category | Technology | Status |
|----------|-----------|--------|
| Data processing | pandas, pyarrow | Active |
| Storage format | Apache Parquet (Snappy compression) | Active |
| Storage location | Local-first (`data/`), S3 optional (`s3://nfl-raw/`, `nfl-refined/`, `nfl-trusted/`) | Active |
| Ad-hoc query | DuckDB | Active |
| Data source | nfl-data-py (via NFLDataAdapter) | Active |
| Infrastructure | AWS S3 (us-east-2), GitHub Actions | Active |
| Python libraries | boto3, nfl-data-py, numpy | Active |
| ML | XGBoost, LightGBM, CatBoost, scikit-learn, SHAP, Optuna | Active |
| Graph DB (planned) | Neo4j | Planned |

### Architecture

```
nfl-data-py + Sleeper API + FinnedAI odds
        |
Bronze (s3://nfl-raw/)     -- 16 data types: PBP (140 cols), player stats, schedules,
                              snap counts, injuries, rosters, NGS, PFR, QBR, depth charts,
                              draft picks, combine, officials, teams, odds (2016-2021)
        |
Silver (s3://nfl-refined/) -- 14 paths: player usage/advanced/historical/quality, team PBP
                              metrics/tendencies/SOS/situational/PBP-derived, game
                              context, referee, playoff context, market data (line movement)
        |
Gold   (s3://nfl-trusted/) -- fantasy projections (PPR/Half-PPR/Standard) + game predictions
                              (v2.0 XGB+LGB+CB+Ridge ensemble, CLV tracking)
        |
Draft Tool                 -- ADP comparison, VORP, mock draft, auction, waiver wire
```

S3 key pattern: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`

Read convention: Always use `download_latest_parquet()` from `src/utils.py` -- never scan full prefix.

---

## Completed Phases

### Phase 1: Infrastructure Prerequisites

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Built the foundational infrastructure required before ingesting new data types.

**Key deliverables:**
- **Local-first storage** (INFRA-01): Bronze ingestion saves to `data/bronze/` by default; S3 upload is opt-in via `--s3` flag. Works without AWS credentials.
- **Dynamic season validation** (INFRA-02): Season upper bound is `current_year + 1` (callable in config), so 2026 works without code changes.
- **NFLDataAdapter** (INFRA-03): Single adapter module (`src/nfl_data_adapter.py`) isolates all `nfl.import_*` calls. Future migration to nflreadpy requires changes only in this file.
- **DATA_TYPE_REGISTRY** (INFRA-04): Registry/dispatch pattern in the Bronze CLI -- adding a new data type is config-only, no if/elif chains.
- **Per-type season ranges** (INFRA-05): `DATA_TYPE_SEASON_RANGES` config maps each data type to its valid season range (e.g., NGS starts 2016, PFR starts 2018).

**Key decisions:**
- Callable upper bound in `DATA_TYPE_SEASON_RANGES` for dynamic max season
- Lazy `nfl_data_py` import in adapter for graceful degradation

### Phase 2: Core PBP Ingestion

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Ingested full play-by-play data -- the foundation for game prediction analytics.

**Key deliverables:**
- **103 curated PBP columns** (PBP-01): Selected from ~390 available columns, including EPA, WPA, CPOE, air yards, success rate, and personnel groupings.
- **Memory-safe batch processing** (PBP-02): Processes one season at a time to stay under 2GB peak memory.
- **Column subsetting** (PBP-03): Uses the `columns` parameter to avoid loading all 390 columns.
- **Full history** (PBP-04): PBP data ingested for seasons 2010-2025.

**Key decisions:**
- 103 columns kept (not ~80 as originally estimated); `include_participation=False` default
- Single-season batch loop for memory safety

### Phase 3: Advanced Stats and Context Data

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Ingested all remaining data types to complete the Bronze layer.

**Key deliverables:**
- **NGS data** (ADV-01): Passing, rushing, receiving stats from Next Gen Stats (2016-2025)
- **PFR weekly stats** (ADV-02): Pass, rush, rec, def from Pro Football Reference (2018-2025)
- **PFR seasonal stats** (ADV-03): Same 4 sub-types, aggregated by season (2018-2025)
- **QBR** (ADV-04): ESPN QBR weekly + seasonal (2006-2025)
- **Depth charts** (ADV-05): Team depth charts (2020-2025)
- **Draft picks** (CTX-01): Historical draft data (2000-2025)
- **Combine** (CTX-02): NFL Combine results (2000-2025)
- **Validation** (VAL-01 to VAL-03): `validate_data()` extended for all new types; error handling for API timeouts; 25+ tests added

**Key decisions:**
- QBR filenames use frequency prefix to prevent weekly/seasonal file collisions
- `validate_data()` uses common columns shared across sub-types (conservative Bronze validation)
- Parametrized tests for sub-typed sources (NGS/PFR)

### Phase 4: Documentation Update

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Aligned all documentation with the actual data state after Phases 1-3.

**Key deliverables:**
- **Bronze inventory script** (DOC-03): `scripts/generate_inventory.py` -- reusable script that scans local data and generates markdown inventory
- **NFL Data Dictionary** (DOC-01): Comprehensive column specs for all 15+ Bronze data types, plus Silver and Gold layers
- **Prediction data model status badges** (DOC-02): Every section in the prediction model marked as Implemented, In Progress, or Planned
- **Implementation guide rewrite** (DOC-04): This document -- replaced obsolete 8-week roadmap with actual phase history

**Key decisions:**
- Auto-generated Parquet schemas for 6 local data types; representative columns from test mocks for 9 API-only types
- No row counts in inventory (too slow); metrics: file count, size, seasons, columns, last modified

### Phase 5: Phase 1 Verification Backfill

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Closed the requirements traceability gap for Phase 1 by formally verifying all 5 INFRA requirements with code evidence.

**Key deliverables:**
- **01-VERIFICATION.md**: Formal verification report with grep-verifiable code evidence for INFRA-01 through INFRA-05
- **REQUIREMENTS.md traceability**: All 5 INFRA requirements updated from Pending to Complete

**Key decisions:**
- Re-verification approach: evidence gathered from existing source files, no code changes needed since Phase 1 was functionally complete

### Phase 6: Wire Bronze Validation

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Wired `validate_data()` into the Bronze ingestion pipeline with warn-never-block semantics.

**Key deliverables:**
- **NFLDataAdapter.validate_data()**: Delegates to NFLDataFetcher with lazy import; produces human-readable pass/warning output via `format_validation_output()`
- **Bronze ingestion wiring**: Every fetch is validated before save, wrapped in try/except so validation issues never block data persistence
- **8 tests** in `tests/test_bronze_validation.py`: delegation, lazy import, return structure, output formatting, and integration wiring

**Key decisions:**
- Warn-never-block: validation issues print warnings but never prevent data save
- Lazy import of NFLDataFetcher inside validate_data() matches existing adapter isolation pattern

### Phase 7: Tech Debt Cleanup

**Milestone:** v1.0 Bronze Expansion | **Completed:** 2026-03-08

Resolved four v1.0 audit items: dynamic season bounds and DRY validation output.

**Key deliverables:**
- **Dynamic season validation**: Replaced hardcoded `s > 2025` bound with `get_max_season()` from `src/config.py` -- future-proofed for 2027+
- **DRY validation output**: Replaced 10 lines of inline formatting with delegation to `format_validation_output()`

**Key decisions:**
- Used existing `get_max_season()` rather than introducing a new utility
- Season bounds pattern: always use `get_max_season()`, never hardcode year constants

---

### Phase 8: Pre-Backfill Guards

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-09

Added safety guards to protect bulk backfill operations from known data source limitations.

**Key deliverables:**
- **Injury season cap**: `DATA_TYPE_SEASON_RANGES` for injuries capped at `lambda: 2024` -- prevents nflverse crash for 2025+ seasons where injury data is not published
- **Dependency pin documentation**: Inline `# pinned:` comments on `nfl_data_py` and `numpy` in `requirements.txt` for long-term stability
- **GITHUB_TOKEN documentation**: Added to `.env` with notes clarifying nfl-data-py does not use it for rate limiting

**Key decisions:**
- Static `lambda: 2024` cap matches existing callable pattern in `DATA_TYPE_SEASON_RANGES`
- Static cap pattern: use `lambda: YEAR` for discontinued or capped nflverse data types

### Phase 9: New Data Type Ingestion

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-09

Enhanced the Bronze CLI and ingested three categories of new data types across their full valid season ranges.

**Key deliverables:**
- **CLI variant looping**: `bronze_ingestion_simple.py` now auto-iterates all sub-types and frequencies when none is specified -- no more mandatory `--sub-type` flag
- **Schema diff logging**: `log_schema_diff()` compares column sets between consecutive seasons; caught depth_charts 2025 schema change (11 new, 14 removed columns)
- **Ingestion summary**: Per-variant counts of ingested/skipped seasons printed after each run
- **Simple types ingested**: teams (1 file), draft_picks (26 seasons, 2000-2025), combine (26 seasons, 2000-2025), depth_charts (25 seasons, 2001-2025)
- **Sub-type data ingested**: NGS (passing/rushing/receiving, 2016-2025), PFR weekly (pass/rush/rec/def, 2018-2025), PFR seasonal (same 4 sub-types, 2018-2025), QBR weekly + seasonal (2006-2025)
- **PBP backfill**: Full play-by-play for seasons 2016-2025 (10 seasons, ~484K total rows, 103 columns each)

**Key decisions:**
- QBR frequency parameter changed from `["weekly", "seasonal"]` to `["weekly", "season"]` to match nfl-data-py API
- Variant loop wraps the season loop (not inside it) for cleaner per-variant schema diff tracking
- Bronze stores raw data -- depth_charts 2025 schema change ingested as-is; Silver normalizes

### Phase 10: Existing Type Backfill

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-12

Backfilled all 6 existing Bronze data types to achieve full 10-year coverage (2016-2025).

**Key deliverables:**
- **Snap counts backfill**: 215 week-partitioned Parquet files for all 10 seasons (2016-2025), including 2020-2024 gap from expired S3 credentials
- **Schedules backfill**: 6 season files for 2020-2025 (previously S3-only, credentials expired)
- **Full coverage verified**: 6/6 Bronze data types pass with 10-year history (player_weekly/seasonal 2025 excluded -- nflverse HTTP 404, data not yet published at time of backfill)

**Key decisions:**
- snap_counts `player_id` validation issue noted (schema uses `player`, not `player_id`) -- handled in Phase 13
- player_weekly and player_seasonal 2025 accepted as unavailable pending nflverse publication

### Phase 11: Orchestration and Validation

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-12

Validated the completed backfill with an orchestration script and regenerated the Bronze inventory.

**Key deliverables:**
- **Updated Bronze inventory**: `docs/BRONZE_LAYER_DATA_INVENTORY.md` regenerated via `scripts/generate_inventory.py`; confirmed 25 data types, 517 files, 93.28 MB across 2000-2025 seasons
- **Coverage report**: All 25 data type groupings documented with file count, size, seasons, columns, and last modified

**Key decisions:**
- No code changes to `generate_inventory.py` were needed -- the existing script correctly scanned all 25 groupings

### Phase 12: 2025 Player Stats Gap Closure

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-13

Closed the 2025 player statistics gap by sourcing weekly and seasonal data from the nflverse `stats_player` endpoint and processing through Silver.

**Key deliverables:**
- **2025 weekly player stats**: 19,421 rows, 115 columns ingested (includes 62 additional columns vs 2024 such as defensive/kicker stats)
- **2025 seasonal player stats**: 2,025 rows, 60 columns including all 13 team-share columns
- **Silver 2025 pipeline**: 46,011 player-week rows with usage metrics, rolling averages, game script indicators, venue splits, and opponent rankings
- **Registry path fix**: `player_weekly` changed to season-only path (`players/weekly/season={season}/`) to match existing 2020-2024 storage pattern

**Key decisions:**
- Season-only bronze path for `player_weekly` (no week partition) -- matches how Silver reads the data
- High null percentages in EPA, kicker, and advanced columns are expected (position-specific stats)

### Phase 13: Bronze-Silver Path Alignment

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-13

Corrected Silver reader paths that had diverged from the reorganized Bronze filesystem.

**Key deliverables:**
- **snap_counts reader**: Fixed `_read_local_bronze()` to read from `players/snaps/` with week-partitioned concatenation (`pd.concat`) instead of single-file latest read
- **schedules reader**: Fixed path from non-existent `games/` to correct `schedules/`
- **validate_data() correction**: snap_counts required column changed from `player_id` to `player` (matches actual nfl-data-py schema)

**Key decisions:**
- Week-partitioned Bronze data: concatenate all week files when reading into Silver (not take-latest)
- Removed residual `data/bronze/players/snap_counts/` directory (superseded by `players/snaps/`)

### Phase 14: Bronze Cosmetic Cleanup

**Milestone:** v1.1 Bronze Backfill | **Completed:** 2026-03-13

Normalized the Bronze filesystem layout and corrected documentation that had mischaracterized GITHUB_TOKEN behavior.

**Key deliverables:**
- **player_weekly path normalization**: Moved 2016-2019 files from erroneous `week=0/` subdirectories to season level
- **draft_picks deduplication**: Removed 26 duplicate files (kept newest per season across all 26 seasons)
- **GITHUB_TOKEN doc correction**: Clarified in REQUIREMENTS.md, ROADMAP.md, and research files that nfl-data-py does NOT use the token for rate limiting
- **Cleanup script**: `scripts/bronze_cosmetic_cleanup.py` created with dry-run-by-default safety pattern

**Key decisions:**
- Cleanup scripts use dry-run as the default mode, requiring an explicit `--execute` flag to prevent accidental data loss

---

### Phase 15: PBP Team Metrics and Tendencies

**Milestone:** v1.2 Silver Expansion | **Completed:** 2026-03-14

Built the Silver team analytics layer from PBP data, fixing a cross-season rolling window bug in the process.

**Key deliverables:**
- **Rolling window bug fix** (PBP-05): Changed player rolling window groupby from `player_id` to `[player_id, season]` in `player_analytics.py` -- prevents Week 1 values from being contaminated by prior season data
- **`src/team_analytics.py`**: New module with `_filter_valid_plays()` and `apply_team_rolling()` shared utilities; mirrors `player_analytics.py` patterns grouped by `[team, season]`
- **PBP performance metrics**: `compute_pbp_metrics()` produces offensive/defensive EPA per play, success rate, CPOE (offense only), red zone efficiency (TD rate using unique drive denominator) -- per team-week with 3-game, 6-game, and STD rolling windows
- **Tendency metrics**: `compute_tendency_metrics()` produces pace (plays per minute), PROE (pass rate over expected), 4th down aggressiveness (go rate), and early-down run rate -- all with rolling windows. 4th down function accepts raw PBP to include punt/FG play types in denominator
- **`scripts/silver_team_transformation.py`**: New Silver CLI producing `pbp_metrics` and `tendencies` Parquet files per season at `data/silver/teams/`
- **Config registration**: `SILVER_TEAM_S3_KEYS` added to `config.py` for both output paths
- **36 tests** in `tests/test_team_analytics.py` covering all metric functions

**Key decisions:**
- Rolling windows group by `[entity, season]` to prevent cross-season contamination -- applied to both new team module and fixed player module
- Red zone TD rate uses unique drive denominator (not play count)
- PROE uses pandas `mean()` for xpass to auto-exclude NaN while preserving all rows in actual pass rate

### Phase 16: Strength of Schedule and Situational Splits

**Milestone:** v1.2 Silver Expansion | **Completed:** 2026-03-14

Extended the Silver team layer with opponent-adjusted EPA rankings and context-aware performance splits.

**Key deliverables:**
- **`compute_sos_metrics()`**: Opponent-adjusted EPA and schedule difficulty rankings (1-32 per team per week) using only lagged (week N-1) opponent strength to avoid circular dependency. Week 1 opponent-adjusted EPA equals raw EPA. Bye weeks produce no row in SOS output
- **`TEAM_DIVISIONS` config**: 32-team division lookup enabling divisional game tagging
- **`compute_situational_splits()`**: 12 EPA split columns in wide format (home/away offense+defense, divisional/non-divisional offense+defense, leading/trailing offense+defense) with 3-game, 6-game, and STD rolling windows (51 total output columns)
- **Silver team CLI extended**: Single CLI pass now produces 4 datasets per season (pbp_metrics, tendencies, sos, situational) at `data/silver/teams/`
- **247 full test suite** including 11 new situational and idempotency tests

**Key decisions:**
- SOS uses per-game opponent EPA from the specific week faced, not cumulative season-to-date
- Game script threshold: leading >= 7, trailing <= -7, neutral plays excluded from both categories
- Wide format pivot before rolling windows prevents cross-situation contamination
- Non-applicable situations produce NaN (not zero) for clean downstream filtering

### Phase 17: Advanced Player Profiles

**Milestone:** v1.2 Silver Expansion | **Completed:** 2026-03-14

Built the Silver advanced player analytics layer merging NGS, PFR, and QBR metrics onto player rosters.

**Key deliverables:**
- **`src/player_advanced_analytics.py`**: New module with 6 compute functions (NGS WR/TE separation + catch probability, NGS QB time-to-throw + aggressiveness, NGS RB rush yards over expected, PFR QB pressure rate, PFR defensive blitz rate, QBR rolling profiles) plus a generic `_compute_profile()` helper to DRY up the pattern. Player rolling uses `min_periods=3` (stricter than team `min_periods=1`)
- **`scripts/silver_advanced_transformation.py`**: New CLI script orchestrating Bronze read, three-tier join, merge, rolling, and Silver write for all 6 PLAYER_DATA_SEASONS (2020-2025). Produces 47,447 total player-week rows with 128 advanced stat columns
- **Three-tier join strategy**: GSIS ID (NGS), normalized name+team synthetic ID (PFR/QBR), team-only (PFR blitz rate)
- **Overlap detection**: Duplicate column detection before each merge prevents `_x`/`_y` suffix columns across NGS sources
- **Config registration**: `SILVER_PLAYER_S3_KEYS` extended with `advanced_profiles` path

**Key decisions:**
- Synthetic `player_gsis_id` (name+team concatenation) for PFR and QBR data -- enables rolling window groupby despite missing GSIS IDs
- PFR pressure 12% match rate is correct and expected -- PFR pass data covers QBs only (~700/5,653 player-weeks)
- Team abbreviation normalization: LAR->LA and WSH->WAS to prevent silent join failures
- QBR absent for 2024-2025 seasons as expected per research

### Phase 18: Historical Context

**Milestone:** v1.2 Silver Expansion | **Completed:** 2026-03-15

Built a static Silver dimension table linking combine measurables and draft capital to player IDs.

**Key deliverables:**
- **`src/historical_profiles.py`**: Combine composite scores (speed score, BMI, burst score, catch radius), position percentiles, Jimmy Johnson trade value mapping
- **`scripts/silver_historical_transformation.py`**: CLI producing single flat Parquet at `data/silver/players/historical/`
- **Dimension table**: Full outer join on `pfr_id` (combine + draft_picks) with `gsis_id` linkage for downstream matching; 9,892 player rows
- **Config registration**: `SILVER_PLAYER_S3_KEYS` extended with `historical_profiles` path

### Phase 19: v1.2 Tech Debt Cleanup

**Milestone:** v1.2 Silver Expansion | **Completed:** 2026-03-15

Resolved tech debt items accumulated during v1.2 Silver work.

**Key deliverables:**
- Code cleanup and documentation updates across Silver modules
- Pipeline health monitoring extended to all 7 Silver paths
- Test additions bringing total to 289 passing tests

---

### Phase 20: Infrastructure and Data Expansion

**Milestone:** v1.3 Prediction Data Foundation | **Completed:** 2026-03-16

Expanded PBP to 140 columns and ingested officials data for referee analysis.

**Key deliverables:**
- **PBP expansion**: 103 -> 140 columns adding penalty details, special teams, fumble recovery, drive fields; re-ingested for all 2016-2025 seasons
- **Officials Bronze**: Referee crew assignments ingested for 2016-2025 (5 columns per game)
- **`src/nfl_data_adapter.py` updates**: Extended PBP column list and added officials data type to registry
- **Stadium coordinates**: `STADIUM_ID_COORDS` dict (38 venues) for haversine travel distance calculation

### Phase 21: PBP-Derived Team Metrics

**Milestone:** v1.3 Prediction Data Foundation | **Completed:** 2026-03-16

Built 11 additional PBP-derived team metrics for the prediction feature vector.

**Key deliverables:**
- **11 new metric categories**: Penalties, turnovers, red zone trips, FG accuracy, kick/punt returns, 3rd down conversion, explosive plays, drive efficiency, sacks, time of possession, turnover luck
- **164-column output**: `data/silver/teams/pbp_derived/` with 3-game and 6-game rolling windows
- **Turnover luck**: Expanding-window fumble recovery rate for regression-to-mean modeling
- **Silver team CLI extended**: Now produces 5 datasets per season (added pbp_derived)

### Phase 22: Schedule-Derived Context

**Milestone:** v1.3 Prediction Data Foundation | **Completed:** 2026-03-17

Built game context features, referee tendencies, playoff context, and defensive positional stats from schedules and PBP data.

**Key deliverables:**
- **`src/game_context.py`**: New module with 4 compute functions for game-level context features
- **Game context**: Weather, rest days, travel distance (haversine), coaching matchup, surface type per team per week (22 columns)
- **Referee tendencies**: Expanding-window penalty rates per crew with `shift(1)` lag to prevent leakage (4 columns)
- **Playoff context**: Cumulative W-L-T, division rank, games behind leader, late-season contention flags (10 columns)
- **Defense positional stats**: Points allowed by position group for matchup modeling (6 columns)
- **`scripts/silver_game_context_transformation.py`**: Silver CLI producing 4 datasets per season

### Phase 23: Cross-Source Features and Integration

**Milestone:** v1.3 Prediction Data Foundation | **Completed:** 2026-03-19

Assembled the full prediction feature vector from 8 Silver sources and validated cross-source consistency.

**Key deliverables:**
- **337-column prediction feature vector**: Left joins on [team, season, week] from 8 Silver sources (PBP metrics, tendencies, SOS, situational, PBP-derived, game context, referee tendencies, playoff context)
- **Cross-source validation**: Schema checks, join completeness verification, feature coverage reporting
- **Pipeline health monitoring**: Extended to all 11 Silver paths
- **360 total tests passing** across 8 test files

---

## Upcoming Phases (v1.4 ML Game Prediction)

### Phase 24: Documentation Refresh (In Progress)

**Goal:** Update all project documentation to reflect v1.3 completion and v1.4 architecture.

**Planned deliverables:**
- Data dictionary updated with all Silver and Gold layer schemas
- CLAUDE.md refreshed with current architecture, key files, and status
- Implementation guide updated with phases 18-23 and v1.4 roadmap
- Bronze inventory regenerated

### Phase 25: Feature Assembly and Model Training (Planned)

**Goal:** Build XGBoost spread and over/under prediction models trained on game-level differential features with walk-forward cross-validation.

**Planned deliverables:**
- Game-level differential feature assembly (home-away) reducing ~680 features to ~180
- Walk-forward CV framework with expanding training windows
- XGBoost models for spread and total prediction
- Feature importance reporting

### Phase 26: Backtesting and Validation (Planned)

**Goal:** Validate models against historical closing lines with ATS accuracy and profit analysis.

**Planned deliverables:**
- Backtesting framework with ATS accuracy and vig-adjusted profit/loss
- 2024 season sealed holdout validation
- Per-season stability analysis

### Phase 27: Prediction Pipeline (Planned)

**Goal:** Weekly prediction generation with edge detection and confidence scoring vs Vegas lines.

**Planned deliverables:**
- Weekly prediction pipeline producing model spread and total lines
- Edge detection (model line minus Vegas line) with direction and magnitude
- Confidence tier classification (high/medium/low edge)
- Gold-layer Parquet output with season/week partitioning

---

## Existing Capabilities

These capabilities were built before the Bronze expansion work (Phases 1-4 above) and remain fully functional.

### Silver Layer: Fantasy Analytics

Built by `scripts/silver_player_transformation.py`:

- **Player usage metrics**: Target share, carry share, snap percentage, air yards share, red zone opportunities
- **Opponent rankings**: 1-32 rankings for points allowed to each position (QB, RB, WR, TE)
- **Rolling averages**: 3-game and 6-game rolling stats, weighted by recency (roll3: 45%, roll6: 30%, std: 25%)

### Silver Layer: Team Analytics

Built by `scripts/silver_team_transformation.py` (Phase 15-16):

- **PBP performance metrics**: Offensive/defensive EPA per play, success rate, CPOE, red zone efficiency per team-week with 3-game and 6-game rolling windows
- **Tendency metrics**: Pace (plays/minute), PROE (pass rate over expected), 4th down go rate, early-down run rate with rolling windows
- **Strength of schedule**: Opponent-adjusted EPA and schedule difficulty rankings (1-32) per team per week; uses lagged opponent strength to avoid circular dependency
- **Situational splits**: Home/away, divisional, and game script (leading/trailing by 7+) EPA splits in wide format with rolling windows -- 12 split columns, 51 total output columns

### Silver Layer: Advanced Player Profiles

Built by `scripts/silver_advanced_transformation.py` (Phase 17):

- **NGS metrics**: WR/TE separation and catch probability, QB time-to-throw and aggressiveness, RB rush yards over expected -- all with rolling windows
- **PFR metrics**: QB pressure rate allowed, team defensive blitz rate -- with rolling windows
- **QBR profiles**: Total QBR and points added per QB with rolling windows (available 2020-2023)
- **Coverage**: 47,447 player-weeks across 2020-2025 with 128 advanced stat columns; sparse columns use `min_periods=3`

### Gold Layer: Fantasy Projections

Built by `scripts/generate_projections.py`:

- **Weekly projections**: Per-player fantasy point projections with floor/ceiling ranges
- **Preseason projections**: Full-season projections for draft preparation
- **Projection model**: `roll3(50%) + roll6(30%) + STD(20%) * usage_mult * matchup * vegas`
- **Injury adjustments**: Multipliers by status (Questionable: 0.85, Doubtful: 0.50, Out/IR/PUP: 0.0)
- **Vegas integration**: Implied team total / 23.0, RB run-heavy bonus
- **Bye week handling**: Zeroes all stats, sets `is_bye_week=True`
- **Rookie fallback**: Conservative positional baselines (starter/backup/unknown at 100%/40%/25%)

### Draft Tool

Built by `scripts/draft_assistant.py`:

- **Snake draft**: VORP-based recommendations with positional scarcity
- **Auction draft**: Budget-optimized player valuation
- **Mock simulation**: Multi-round mock drafts against AI opponents
- **Waiver wire**: Position-filtered available player rankings

### Backtesting

Built by `scripts/backtest_projections.py`:

- **Results (2022-2024, Half-PPR)**: MAE 4.91, RMSE 6.72, Correlation 0.51, Bias -0.60
- **Per-position**: QB (6.58 MAE), RB (5.06), WR (4.85), TE (3.77)
- **Coverage**: 11,183 player-weeks across 48 weeks, 3 seasons

### Pipeline Monitoring

- **GitHub Actions**: Weekly pipeline runs Tuesdays 9am UTC; auto-detects NFL week from calendar
- **Health check**: `scripts/check_pipeline_health.py` -- S3 freshness + file size checks across all layers
- **Failure handling**: Auto-opens GitHub issue with error details on pipeline failure

### Test Suite

360 tests passing across:
- `tests/test_scoring_calculator.py` (14 tests)
- `tests/test_projection_engine.py` (19 tests)
- `tests/test_player_analytics.py` (7 tests, including 3 rolling window regression tests added in Phase 15)
- `tests/test_draft_optimizer.py` (13 tests)
- `tests/test_utils.py` (5 tests)
- `tests/test_advanced_ingestion.py` (22 tests)
- `tests/test_bronze_validation.py` (8 tests added Phase 6)
- `tests/test_infrastructure.py` (extended through Phases 7-12)
- `tests/test_team_analytics.py` (36 tests added Phases 15-16)
- `tests/test_pbp_ingestion.py` (13 tests added Phase 9)

Full suite at 360 passing tests as of Phase 23 (v1.3) completion.

---

## Future Work

### nflreadpy Migration (Planned)

Migrate from nfl-data-py to nflreadpy when feature parity is confirmed. Impact is limited to `src/nfl_data_adapter.py` by design (INFRA-03 adapter isolation).

### Deferred: Neo4j Graph Layer

Graph-based analytics for relationship-driven insights:

- **WR-CB matchup graphs:** Model receiver-cornerback matchup history with edge weights for yards allowed, targets, and catch rate. Enable "who covers whom" queries for game planning.
- **QB-WR target share networks:** Model passing networks showing target distribution, air yards allocation, and chemistry ratings. Identify scheme-dependent vs QB-dependent receivers.
- **Injury cascade analysis:** Model how injuries to one player affect usage and performance of related players (e.g., WR1 injury increases WR2 target share).
- **Team scheme graphs:** Connect personnel groupings to play types and outcomes for scheme identification.

Deferred until the tabular prediction model is validated. Graph features will be added as supplementary inputs to improve prediction accuracy.

---

## Development Setup

### Prerequisites

```bash
# Clone and set up virtual environment
git clone <repo-url>
cd nfl_data_engineering
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Key Commands

```bash
# Bronze ingestion (local-first)
python scripts/bronze_ingestion_simple.py --season 2024 --data-type player_weekly

# Silver transformation -- fantasy analytics
python scripts/silver_player_transformation.py --seasons 2020 2021 2022 2023 2024

# Silver transformation -- team PBP metrics, tendencies, SOS, situational splits
python scripts/silver_team_transformation.py --seasons 2024

# Silver transformation -- advanced player profiles (NGS/PFR/QBR)
python scripts/silver_advanced_transformation.py --seasons 2020 2021 2022 2023 2024

# Gold projections
python scripts/generate_projections.py --week 1 --season 2026 --scoring half_ppr

# Draft assistant
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5

# Tests
python -m pytest tests/ -v

# Code quality
python -m black src/ tests/ scripts/
python -m flake8 src/ tests/ scripts/
```

See [CLAUDE.md](../CLAUDE.md) for the full command reference and file map.

### Data Quality and Validation

The platform validates data at multiple points:

**Bronze ingestion validation** (`NFLDataFetcher.validate_data()` via `NFLDataAdapter.validate_data()`):
- Required column checks per data type (all 25 types have rules)
- Season range validation (per `DATA_TYPE_SEASON_RANGES`, including static caps like injuries at 2024)
- Empty response handling
- API timeout error handling with retries
- Warn-never-block semantics: issues print warnings but never prevent data save

**Silver transformation validation** (`silver_player_transformation.py`):
- Position filtering (QB, RB, WR, TE only for fantasy)
- Null handling for missing stats
- Season/week range verification

**Gold projection validation** (`generate_projections.py`):
- Non-negative projected points for skill positions
- Floor <= projected <= ceiling consistency
- Bye week zeroing verification
- Injury status multiplier bounds (0.0 to 1.0)

**Ad-hoc validation** (DuckDB):
```sql
-- Example: verify Bronze data completeness
SELECT season, COUNT(*) as games
FROM read_parquet('data/bronze/schedules/season=*/schedules_*.parquet')
GROUP BY season ORDER BY season;

-- Example: verify Silver team metrics coverage
SELECT season, team, COUNT(*) as weeks
FROM read_parquet('data/silver/teams/pbp_metrics/season=*/pbp_metrics_*.parquet')
GROUP BY season, team ORDER BY season, team;
```

### Key Files Reference

| File | Purpose |
|------|---------|
| `src/config.py` | S3 paths, SCORING_CONFIGS, ROSTER_CONFIGS, SILVER_TEAM_S3_KEYS, SILVER_PLAYER_S3_KEYS, DATA_TYPE_SEASON_RANGES |
| `src/nfl_data_adapter.py` | NFLDataAdapter -- all nfl-data-py imports isolated here; validate_data() and format_validation_output() |
| `src/nfl_data_integration.py` | NFLDataFetcher -- fetch methods + validate_data() with dynamic season bounds |
| `src/player_analytics.py` | Usage metrics, opp rankings, rolling avgs, Vegas implied totals |
| `src/team_analytics.py` | PBP metrics, tendency metrics, SOS, situational splits for teams (Phase 15-16) |
| `src/player_advanced_analytics.py` | NGS/PFR/QBR compute functions and rolling utilities for advanced player profiles (Phase 17) |
| `src/scoring_calculator.py` | Fantasy points -- single dict + vectorized DataFrame |
| `src/projection_engine.py` | Weekly/preseason projections; bye week, rookie, Vegas multiplier |
| `src/draft_optimizer.py` | DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor |
| `src/utils.py` | Shared utils incl. download_latest_parquet |
| `scripts/bronze_ingestion_simple.py` | Bronze CLI -- all 25+ data types via registry; variant looping, schema diff, ingestion summary |
| `scripts/bronze_cosmetic_cleanup.py` | One-time Bronze filesystem cleanup with dry-run/execute modes |
| `scripts/silver_player_transformation.py` | Silver CLI -- fantasy usage metrics, rolling averages, opp rankings |
| `scripts/silver_team_transformation.py` | Silver CLI -- team PBP metrics, tendencies, SOS, situational splits (Phase 15-16) |
| `scripts/silver_advanced_transformation.py` | Silver CLI -- advanced player profiles via NGS/PFR/QBR merge (Phase 17) |
| `scripts/generate_projections.py` | Gold CLI (--week or --preseason) |
| `scripts/draft_assistant.py` | Interactive draft CLI (snake, auction, mock, waiver) |
| `scripts/backtest_projections.py` | Compare projected vs actual; MAE/RMSE/bias |
| `scripts/generate_inventory.py` | Bronze data inventory generator |
| `scripts/check_pipeline_health.py` | S3 freshness + file size checks across all layers |

### Project Structure

| Directory | Purpose |
|-----------|---------|
| `src/` | Core modules (config, adapter, analytics, team analytics, advanced analytics, scoring, projections, draft, utils) |
| `scripts/` | CLI scripts for each pipeline stage |
| `tests/` | Unit tests (pytest) |
| `data/bronze/` | Local Bronze storage (mirrors S3) -- 25+ data types, 517+ files |
| `data/silver/` | Local Silver storage -- 12 paths: players/ (usage, advanced, historical), teams/ (pbp_metrics, tendencies, sos, situational, pbp_derived, game_context, referee_tendencies, playoff_context), defense/positional |
| `data/gold/` | Local Gold storage |
| `docs/` | Documentation (data dictionary, data model, implementation guide, Bronze inventory) |
| `.github/workflows/` | GitHub Actions pipeline |

---

## Configuration

### AWS

- **Region:** us-east-2
- **Buckets:** `nfl-raw` (Bronze), `nfl-refined` (Silver), `nfl-trusted` (Gold)
- **Credentials:** `.env` file (never committed)

### Scoring

| Format | Reception Points | Other |
|--------|-----------------|-------|
| PPR | 1.0/rec | 0.1/yd, 6/TD, 0.04/pass yd |
| Half-PPR | 0.5/rec | Same |
| Standard | 0.0/rec | Same |

### NFL Business Rules

- Valid seasons: 1999-2026
- Weeks: 1-18 regular season
- 32 teams
- Projected points >= 0 for skill positions (QB/RB/WR/TE)
- Player training data: 2020-2025 (PLAYER_DATA_SEASONS)
- PBP analysis range: 2016-2025 (NGS start year)
- Combine/draft history: 2000-2025

---

## Milestone Summary

| Milestone | Phases | Shipped | Scope |
|-----------|--------|---------|-------|
| v1.0 Bronze Expansion | 1-7 | 2026-03-08 | Infrastructure, PBP, advanced stats, docs, validation wiring, tech debt |
| v1.1 Bronze Backfill | 8-14 | 2026-03-13 | Guards, new type ingestion, backfill, orchestration, 2025 gap closure, path alignment, cleanup |
| v1.2 Silver Expansion | 15-19 | Shipped 2026-03-15 | Team PBP metrics, SOS/situational splits, advanced player profiles, historical context, tech debt |
| v1.3 Prediction Data Foundation | 20-23 | Shipped 2026-03-19 | PBP expansion (140 cols), officials, PBP-derived metrics, game context, referee tendencies, playoff context, 337-col feature vector |
| v1.4 ML Game Prediction | 24-27 | 2026-03-22 | Docs refresh, XGBoost spread/total models, walk-forward CV, backtest, prediction pipeline |
| v2.0 Model Improvement | 28-31 | 2026-03-27 | Player quality features, SHAP feature selection, XGB+LGB+CB+Ridge ensemble, ablation (53.0% ATS) |
| v2.1 Market Data | 32-34 | 2026-03-28 | Bronze odds (FinnedAI 2016-2021), Silver line movement features, CLV tracking, market ablation |

---

*Version 5.0 -- Updated March 28, 2026 to reflect v2.0 (ensemble model, 53.0% ATS) and v2.1 (market data, CLV tracking). 7 milestones, 34 phases, 64 plans shipped. 571 tests passing.*
