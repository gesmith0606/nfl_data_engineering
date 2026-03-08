# NFL Data Platform Implementation Guide

**Version:** 2.0
**Last Updated:** March 8, 2026
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
| ML (planned) | XGBoost, LightGBM, scikit-learn | Planned |
| Graph DB (planned) | Neo4j | Planned |

### Architecture

```
nfl-data-py + Sleeper API
        |
Bronze (s3://nfl-raw/)     -- raw game, player, snap, injury, roster data (15+ types)
        |
Silver (s3://nfl-refined/) -- usage metrics, rolling averages, opp rankings
        |
Gold   (s3://nfl-trusted/) -- weekly + preseason projections (PPR/Half-PPR/Standard)
        |
Draft Tool                 -- ADP comparison, VORP, mock draft, auction, waiver wire
```

S3 key pattern: `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`

Read convention: Always use `download_latest_parquet()` from `src/utils.py` -- never scan full prefix.

---

## Completed Phases

### Phase 1: Infrastructure Prerequisites

**Requirements:** INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05

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

**Requirements:** PBP-01, PBP-02, PBP-03, PBP-04

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

**Requirements:** ADV-01 through ADV-05, CTX-01, CTX-02, VAL-01 through VAL-03

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

**Requirements:** DOC-01 through DOC-04

Aligned all documentation with the actual data state after Phases 1-3.

**Key deliverables:**
- **Bronze inventory script** (DOC-03): `scripts/generate_inventory.py` -- reusable script that scans local data and generates markdown inventory
- **NFL Data Dictionary** (DOC-01): Comprehensive column specs for all 15+ Bronze data types, plus Silver and Gold layers
- **Prediction data model status badges** (DOC-02): Every section in the prediction model marked as Implemented, In Progress, or Planned
- **Implementation guide rewrite** (DOC-04): This document -- replaced obsolete 8-week roadmap with actual phase history

**Key decisions:**
- Auto-generated Parquet schemas for 6 local data types; representative columns from test mocks for 9 API-only types
- No row counts in inventory (too slow); metrics: file count, size, seasons, columns, last modified

---

## Existing Capabilities

These capabilities were built before the Bronze expansion work (Phases 1-4 above) and remain fully functional.

### Silver Layer: Fantasy Analytics

Built by `scripts/silver_player_transformation.py`:

- **Player usage metrics**: Target share, carry share, snap percentage, air yards share, red zone opportunities
- **Opponent rankings**: 1-32 rankings for points allowed to each position (QB, RB, WR, TE)
- **Rolling averages**: 3-game and 6-game rolling stats, weighted by recency (roll3: 45%, roll6: 30%, std: 25%)

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

71 unit tests passing across:
- `tests/test_scoring_calculator.py` (14 tests)
- `tests/test_projection_engine.py` (19 tests)
- `tests/test_player_analytics.py` (7 tests)
- `tests/test_draft_optimizer.py` (13 tests)
- `tests/test_utils.py` (5 tests)
- `tests/test_nfl_data_adapter.py` and `tests/test_advanced_ingestion.py` (13+ tests)

---

## Upcoming Phases (v2)

### Phase 5: Silver Prediction Layer

**Requirements:** SLV-01, SLV-02, SLV-03

Build the Silver layer tables needed for game outcome prediction. This phase transforms raw Bronze data into analytics-ready team and matchup features.

| Req | Description | Details |
|-----|-------------|---------|
| SLV-01 | Team EPA aggregates | Rolling offensive/defensive EPA per play at team-week level |
| SLV-02 | Exponentially weighted rolling metrics | Team performance metrics with recency weighting |
| SLV-03 | Matchup feature generation | Team A offense vs Team B defense feature combinations |

**Planned tables:**

1. **Team EPA Aggregates** (`s3://nfl-refined/team_epa/season=YYYY/week=WW/`)
   - Offensive EPA per play (pass, rush, overall)
   - Defensive EPA per play allowed (pass, rush, overall)
   - Success rate (percentage of positive-EPA plays)
   - Explosive play rate (20+ yard plays)
   - Rolling windows: 3-game, 6-game, season-to-date

2. **Exponentially Weighted Metrics** (`s3://nfl-refined/team_ewm/season=YYYY/week=WW/`)
   - Points per game (exponentially weighted, half-life = 4 weeks)
   - Turnover differential
   - Third down conversion/stop rate
   - Red zone efficiency
   - Time of possession trends

3. **Matchup Features** (`s3://nfl-refined/matchup_features/season=YYYY/week=WW/`)
   - Offense vs defense EPA differential (for each game)
   - Pass matchup advantage (team pass EPA vs opponent pass defense EPA)
   - Rush matchup advantage (team rush EPA vs opponent rush defense EPA)
   - Recent form differential (last 4 games)
   - Rest advantage, home/away adjustment

**Tech approach:** pandas DataFrames with rolling window calculations. Output as Parquet files in `s3://nfl-refined/`. DuckDB for validation queries.

**Input data:** PBP (Phase 2), schedules, player weekly stats, snap counts

**Dependencies:** Bronze PBP data (Phase 2), advanced stats (Phase 3)

### Phase 6: ML Pipeline

**Requirements:** ML-01, ML-02, ML-03

Build the prediction model from Bronze/Silver data to game outcome predictions.

| Req | Description | Details |
|-----|-------------|---------|
| ML-01 | Feature engineering pipeline | 200+ ML features per game from team, player, situational, and market data |
| ML-02 | Model training | Random Forest / XGBoost with leave-one-season-out validation |
| ML-03 | Accuracy target | 65%+ win prediction accuracy, <3.5 point spread MAE |

**Feature categories (200+ total):**

1. **Team performance (40+ features):** EPA per play (off/def/pass/rush), success rate, explosive play rate, turnover margin, red zone efficiency, third down rates
2. **Player impact (30+ features):** Starting QB EPA, CPOE, pressure rate; key skill player usage and efficiency ratings; injury severity scores
3. **Situational (20+ features):** Home/away, division game, conference game, prime time, dome/outdoor, rest days, travel distance
4. **Temporal (30+ features):** Rolling averages at multiple windows (3/6/10 games), season week number, momentum indicators, bye week effects
5. **Historical (20+ features):** Head-to-head records (last 5 meetings), coaching matchup history, franchise historical performance
6. **Market (15+ features):** Opening/closing spread, total, line movement, moneyline implied probability
7. **Advanced stats (40+ features):** NGS metrics (completion probability, separation, rush efficiency), PFR advanced stats, QBR components
8. **Composite (10+ features):** Power ratings, Elo-style rankings, schedule-adjusted efficiency

**Model architecture:**
- **Primary:** XGBoost gradient boosted trees (best for tabular data with mixed feature types)
- **Secondary:** Random Forest (robust baseline, less prone to overfitting)
- **Validation:** Leave-one-season-out cross-validation (train on N-1 seasons, test on held-out season)
- **Feature selection:** Recursive feature elimination, SHAP-based importance analysis

**Evaluation metrics:**
- Win prediction accuracy (target: 65%+)
- Against-the-spread accuracy (target: 53%+, profitable threshold: 52.4%)
- Point spread MAE (target: <3.5 points)
- Total points MAE
- Calibration (predicted probability vs actual frequency)

**Tech approach:** scikit-learn for pipeline, XGBoost/LightGBM for models. Feature store as Parquet in Gold layer.

**Dependencies:** Silver prediction layer (Phase 5)

### Phase 7: nflreadpy Migration

**Requirements:** MIG-01

Migrate from nfl-data-py to nflreadpy when feature parity is confirmed.

**Impact:** Changes only in `src/nfl_data_adapter.py` (by design -- INFRA-03 adapter isolation).

**Dependencies:** Confirmed feature parity in nflreadpy

### Deferred: Neo4j Graph Layer

Graph-based analytics for relationship-driven insights:

- **WR-CB matchup graphs:** Model receiver-cornerback matchup history with edge weights for yards allowed, targets, and catch rate. Enable "who covers whom" queries for game planning.
- **QB-WR target share networks:** Model passing networks showing target distribution, air yards allocation, and chemistry ratings. Identify scheme-dependent vs QB-dependent receivers.
- **Injury cascade analysis:** Model how injuries to one player affect usage and performance of related players (e.g., WR1 injury increases WR2 target share).
- **Team scheme graphs:** Connect personnel groupings to play types and outcomes for scheme identification.

Deferred until the tabular prediction model (Phase 6) is validated. Graph features will be added as supplementary inputs to improve prediction accuracy.

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

# Silver transformation
python scripts/silver_player_transformation.py --seasons 2020 2021 2022 2023 2024

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

**Bronze ingestion validation** (`NFLDataFetcher.validate_data()`):
- Required column checks per data type
- Season range validation (per `DATA_TYPE_SEASON_RANGES`)
- Empty response handling
- API timeout error handling with retries

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
```

### Key Files Reference

| File | Purpose |
|------|---------|
| `src/config.py` | S3 paths, SCORING_CONFIGS, ROSTER_CONFIGS, PLAYER_DATA_SEASONS |
| `src/nfl_data_adapter.py` | NFLDataAdapter -- all nfl-data-py imports isolated here |
| `src/nfl_data_integration.py` | NFLDataFetcher -- fetch methods + validate_data() |
| `src/player_analytics.py` | Usage metrics, opp rankings, rolling avgs, Vegas implied totals |
| `src/scoring_calculator.py` | Fantasy points -- single dict + vectorized DataFrame |
| `src/projection_engine.py` | Weekly/preseason projections; bye week, rookie, Vegas multiplier |
| `src/draft_optimizer.py` | DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor |
| `src/utils.py` | Shared utils incl. download_latest_parquet |
| `scripts/bronze_ingestion_simple.py` | Bronze CLI -- all 15+ data types via registry |
| `scripts/silver_player_transformation.py` | Silver CLI |
| `scripts/generate_projections.py` | Gold CLI (--week or --preseason) |
| `scripts/draft_assistant.py` | Interactive draft CLI (snake, auction, mock, waiver) |
| `scripts/backtest_projections.py` | Compare projected vs actual; MAE/RMSE/bias |
| `scripts/generate_inventory.py` | Bronze data inventory generator |

### Project Structure

| Directory | Purpose |
|-----------|---------|
| `src/` | Core modules (config, adapter, analytics, scoring, projections, draft, utils) |
| `scripts/` | CLI scripts for each pipeline stage |
| `tests/` | Unit tests (pytest) |
| `data/bronze/` | Local Bronze storage (mirrors S3) |
| `data/silver/` | Local Silver storage |
| `data/gold/` | Local Gold storage |
| `docs/` | Documentation (data dictionary, data model, implementation guide) |
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

---

*Version 2.0 -- Rewritten March 8, 2026 to reflect actual GSD Phases 1-4 and v2 roadmap*
