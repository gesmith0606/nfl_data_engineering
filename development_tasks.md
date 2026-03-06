# NFL Data Engineerin### 📊 **Current Metrics**
- **Files Created**: 25+ Python scripts, notebooks, and docs
- **Data Ingested**: 2,816 NFL plays + 16 games (0.21 MB in S3)
- **Test Coverage**: AWS, NFL API, S3 operations, data validation
- **Documentation**: README, Quick Start, Implementation Summary, API docs, Bronze layer inventory

## 🛠️ **Technical Infrastructure Completed**

### **Core Components Built**
1. **Data Integration Layer** (`src/nfl_data_integration.py`)
   - `NFLDataFetcher` class with comprehensive methods
   - Error handling for API rate limits and data validation
   - Support for multiple seasons/weeks with quality metrics

2. **Bronze Layer Ingestion** (`scripts/bronze_ingestion_simple.py`)
   - Command-line interface for flexible data ingestion
   - Configurable parameters (season, week, data type)
   - Automatic S3 upload with proper partitioning
   - Real-time validation and summary reporting

3. **AWS S3 Integration**
   - Full CRUD operations tested and working
   - Proper IAM permissions configured (AmazonS3FullAccess)
   - Parquet format optimization and cross-region connectivity
   - Partitioned storage structure (`games/season=YYYY/week=WW/`)

4. **Testing & Validation Suite**
   - `test_aws_connectivity.py` - S3 access verification
   - `test_nfl_data.py` - NFL API functionality testing  
   - `test_s3_full_operations.py` - Comprehensive S3 CRUD testing
   - `scripts/list_bronze_contents.py` - Data inventory viewer
   - `scripts/explore_bronze_data.py` - Interactive data analysis

5. **Configuration Management**
   - Environment variables in `.env` file with AWS credentials
   - S3 bucket names and regions configured (us-east-2)
   - NFL data defaults and processing parameters - Development Task List

**Last Updated:** March 2026
**Current Status:** Fantasy Football System (Phases 1–4) Complete | Neo4j Deferred (Phase 5)

## 📋 MVP Definition
Create a functional NFL data pipeline that ingests game data, cleans it, and produces basic analytics for the 2024 NFL season. The MVP demonstrates the medallion architecture using local Python development with S3 storage.

## 🎯 Project Status Overview

### ✅ **COMPLETED PHASES**
- **Phase 1**: Environment Setup & Foundation (100%)
- **Phase 2**: Bronze Layer — game data + all 5 player data types (100%)
- **Phase 3**: Silver Layer — usage metrics, rolling averages, opponent rankings (100%)
- **Phase 4**: Gold Layer — weekly + preseason projections, fantasy scoring engine (100%)
- **Phase 5**: Draft Tool — interactive CLI, ADP comparison, VORP, positional scarcity (100%)
- **Phase 6**: Project Skills — `/ingest`, `/weekly-pipeline`, `/validate-data`, `/test`, `/draft-prep` (100%)
- **Phase 7**: MCP Integration — DuckDB, fetch, Sleeper added; Neo4j configured (100%)
- **Documentation**: CLAUDE.md, copilot-instructions.md, development_tasks.md updated (100%)

### 🚧 **CURRENT PRIORITIES**
1. Model tuning: Add injury status filter from Bronze injuries data into projection engine
2. Automate Sleeper ADP refresh → `data/adp.csv` (weekly cron or pre-draft trigger)
3. In-season scheduled pipeline: Bronze → Silver → Gold → projections (weekly automation)

### �📊 **Current Metrics**
- **Files Created**: 25+ Python scripts, notebooks, and docs
- **Data Ingested**: 2,816 NFL plays + 16 games (0.21 MB in S3)
- **Test Coverage**: AWS, NFL API, S3 operations, data validation
- **Documentation**: README, Quick Start, Implementation Summary, API docs, Bronze layer inventory

## Development Tasks (In Priority Order)

### Phase 1: Environment Setup and Foundation (Days 1-2)

#### Task 1.1: Local Environment Configuration 🔄 **IN PROGRESS**
**Priority:** Critical  
**Estimated Time:** 2-3 hours  
**Dependencies:** None
**Started:** August 15, 2025

**Subtasks:**
- [x] Run `./setup.sh` to create virtual environment
- [x] Install all dependencies from `requirements.txt`
- [x] Configure `.env` file with AWS credentials (template ready)
- [x] Test AWS CLI connectivity: `aws --version`
- [ ] Verify S3 access to all three buckets (pending AWS credentials)
- [x] Test Python imports: `from src.config import get_s3_path`

**Progress Notes:**
- ✅ Virtual environment created and activated
- ✅ All Python dependencies installed successfully (nfl-data-py v0.3.3, boto3, etc.)
- ✅ AWS CLI installed via Homebrew (v2.28.11)
- ✅ Environment file (.env) configured with your S3 buckets and Databricks workspace
- ✅ Python imports working - config module accessible
- ✅ S3 path generation working: `s3://nfl-raw/games/season=2024/week=1/`
- ⏳ **Next Step:** Configure AWS credentials with `aws configure`

**Success Criteria:** 
- All dependencies installed without errors
- S3 buckets accessible via AWS CLI
- Python modules import successfully

**✅ COMPLETED:** All success criteria met

---

#### Task 1.2: AWS S3 Connectivity Testing ✅ **COMPLETED**
**Priority:** Critical  
**Estimated Time:** 1-2 hours  
**Dependencies:** Task 1.1
**Started:** August 15, 2025
**Completed:** August 15, 2025

**Final Status:**
- ✅ AWS credentials working perfectly
- ✅ AWS authentication successful (Account: 512821312570, User: gesmith0606)
- ✅ IAM permissions added (AmazonS3FullAccess)
- ✅ All S3 buckets accessible (nfl-raw, nfl-refined, nfl-trusted)
- ✅ Full CRUD operations tested and working
- ✅ Parquet file format support verified
- ✅ Partitioned directory structure tested

**Subtasks:**
- [x] Create test script to upload/download from each bucket
- [x] Validate S3 permissions (read, write, list)
- [x] Test cross-region connectivity (us-east-2)
- [x] Verify Parquet file format support
- [x] Test large file uploads (>100MB simulation)

**Files Created:**
- `test_aws_connectivity.py` - Main S3 connectivity test
- `test_s3_permissions.py` - Detailed permission testing
- `test_s3_full_operations.py` - Comprehensive CRUD operations test
- `aws-iam-policy.json` - IAM policy reference
- `AWS_IAM_SETUP_INSTRUCTIONS.md` - Setup documentation

**Success Criteria:** ✅ ALL MET
- Can upload/download files to all S3 buckets
- Parquet files can be written and read successfully
- No authentication or permission errors

**Success Criteria:**
- Can upload/download files to all S3 buckets
- Parquet files can be written and read successfully
- No authentication or permission errors

---

### Phase 2: Bronze Layer Implementation (Days 3-4)

#### Task 2.1: NFL Data Integration ✅ **COMPLETED**
**Priority:** High  
**Estimated Time:** 3-4 hours  
**Dependencies:** Task 1.2
**Started:** August 15, 2025
**Completed:** August 15, 2025

**Final Status:**
- ✅ NFL-data-py library tested and working perfectly
- ✅ Game schedules ingestion implemented and tested
- ✅ Play-by-play data ingestion implemented and tested
- ✅ Team data integration working
- ✅ Data validation and error handling implemented
- ✅ S3 Bronze layer uploads working with proper partitioning
- ✅ Command-line interface created for easy ingestion

**Subtasks:**
- [x] Test `nfl-data-py` library installation and basic usage
- [x] Create function to fetch current season game data (Week 1)  
- [x] Implement error handling for API rate limits
- [x] Add data validation for fetched game data
- [x] Test with multiple weeks and seasons

**Files Created/Modified:**
- `src/nfl_data_integration.py` - Core NFL data fetching and validation
- `bronze_ingestion_simple.py` - Command-line Bronze layer ingestion
- `test_nfl_data.py` - NFL library functionality testing
- `list_bronze_contents.py` - S3 Bronze layer content viewer

**Bronze Layer Data Inventory:** � [Complete catalog](docs/BRONZE_LAYER_DATA_INVENTORY.md)

| Data Type | Season | Week | Records | Columns | Size | File Path |
|-----------|--------|------|---------|---------|------|-----------|
| **Games** | 2023 | 1 | 16 games | 50 | 0.03 MB | `games/season=2023/week=1/schedules_*.parquet` |
| **Plays** | 2023 | 1 | 2,816 plays | 32 | 0.18 MB | `plays/season=2023/week=1/pbp_*.parquet` |
| **Total** | - | - | - | - | **0.21 MB** | S3 Bronze Layer Ready ✅ |

**Success Criteria:** ✅ ALL MET
- NFL data library working with multiple data types
- Error handling for API rate limits and validation
- Data successfully stored in S3 Bronze layer
- Partitioned directory structure implemented

**Success Criteria:**
- Can fetch NFL game data for any season/week
- Data is properly formatted as pandas DataFrame
- Error handling prevents crashes on API issues

---

#### Task 2.2: Bronze Layer S3 Storage ✅ **COMPLETED**
**Priority:** High  
**Estimated Time:** 2-3 hours  
**Dependencies:** Task 2.1
**Completed:** August 15, 2025

**Final Status:**
- ✅ S3 upload functionality implemented and tested
- ✅ Partitioned directory structure: `games/season=YYYY/week=WW/` working
- ✅ Pandas DataFrames to Parquet format conversion working
- ✅ File naming conventions with timestamps implemented
- ✅ Idempotent uploads working (overwrite existing files)

**Subtasks:**
- [x] Implement S3 upload functionality for game data
- [x] Create partitioned directory structure: `games/season=YYYY/week=WW/`
- [x] Convert pandas DataFrames to Parquet format
- [x] Add file naming conventions with timestamps
- [x] Implement idempotent uploads (overwrite existing)

**Files Modified:**
- `scripts/bronze_ingestion_simple.py` - Complete CLI ingestion tool
- `src/nfl_data_integration.py` - S3 upload functions

**Success Criteria:** ✅ ALL MET
- Game data successfully stored in `s3://nfl-raw/`
- Proper partitioning by season and week
- Files can be re-uploaded without corruption

---

#### Task 2.3: Bronze Layer Command Line Interface ✅ **COMPLETED**
**Priority:** Medium  
**Estimated Time:** 2 hours  
**Dependencies:** Task 2.2
**Completed:** August 15, 2025

**Final Status:**
- ✅ Argparse for command-line parameters (season, week, data-type) working
- ✅ Comprehensive logging for ingestion process implemented
- ✅ Progress indicators for operations working
- ✅ Help documentation for CLI usage complete
- ✅ Tested with multiple parameter combinations

**Subtasks:**
- [x] Add argparse for command-line parameters (season, week)
- [x] Implement logging for ingestion process
- [x] Add progress indicators for long-running operations
- [x] Create help documentation for CLI usage
- [x] Test with multiple parameter combinations

**Files Modified:**
- `scripts/bronze_ingestion_simple.py` - Complete CLI implementation

**Usage Example:**
```bash
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type schedules
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type pbp
```

**Success Criteria:** ✅ ALL MET
- Can run: `python scripts/bronze_ingestion_simple.py --season 2024 --week 1`
- Clear logging shows ingestion progress
- Help text explains all parameters

---

---

### Phase 3: Silver Layer Implementation ✅ **COMPLETE**

#### Task 3.1: Data Quality Pipeline ✅ **COMPLETED**
**Priority:** High  
**Estimated Time:** 4-5 hours  
**Dependencies:** Bronze Layer Complete ✅

**Current Bronze Data Available:**
- ✅ 16 games (2023 Week 1) - Complete game metadata  
- ✅ 2,816 plays (2023 Week 1) - Full play-by-play data
- ✅ Parquet format in S3 with proper partitioning
- ✅ Data validated and ready for transformation

**Recommended Subtasks:**
- [ ] **Read existing Bronze data**: Load from `s3://nfl-raw/games/` and `s3://nfl-raw/plays/`
- [ ] **Implement data quality checks**: Missing values, data types, NFL business rules
- [ ] **Standardize data formats**: Team names, player names, timestamps  
- [ ] **Add calculated fields**: Game duration, play success indicators, drive context
- [ ] **Implement duplicate removal**: Handle any duplicate plays or games

**Files to Create:**
- `notebooks/silver_transformation.ipynb` - Interactive development notebook
- `scripts/silver_pipeline.py` - Production Silver layer pipeline
- `src/data_quality.py` - Data quality validation functions
- `src/silver_transformations.py` - Silver layer transformation logic

**Success Criteria:**
- Raw Bronze data successfully cleaned and validated
- Data quality metrics generated (completeness, accuracy, consistency)
- Invalid records properly handled or flagged
- Silver layer data ready for business analytics

---

#### Task 3.2: Silver Layer S3 Storage ✅ **COMPLETED**
**Priority:** High  
**Estimated Time:** 2-3 hours  
**Dependencies:** Task 3.1

**Subtasks:**
- [ ] Save cleaned data to `s3://nfl-refined/`
- [ ] Maintain same partitioning structure as Bronze
- [ ] Add data lineage metadata (source file references)
- [ ] Implement data quality reports (JSON/CSV format)
- [ ] Test end-to-end Bronze → Silver pipeline

**Files to Modify:**
- `notebooks/silver_transformation.py`
- `src/utils.py` (data quality reporting)

**Success Criteria:**
- Cleaned data stored in `s3://nfl-refined/`
- Data quality reports generated
- Can process multiple weeks sequentially

---

### Phase 4: Gold Layer Implementation ✅ **COMPLETE**

#### Task 4.1: Business Metrics Calculation ✅ **COMPLETED**
**Priority:** High  
**Estimated Time:** 4-6 hours  
**Dependencies:** Task 3.2

**Subtasks:**
- [ ] Read all Silver layer data for a season
- [ ] Calculate team performance metrics (wins, losses, points scored/allowed)
- [ ] Generate player statistics aggregations
- [ ] Create game outcome analysis (margins, trends)
- [ ] Implement season-level aggregations

**Files to Modify:**
- `notebooks/gold_aggregation.py`
- `src/utils.py` (business metric functions)

**Success Criteria:**
- Team season statistics are accurately calculated
- Player aggregations match expected results
- Business metrics are properly formatted for analysis

---

#### Task 4.2: Gold Layer Analytics Storage ✅ **COMPLETED**
**Priority:** High  
**Estimated Time:** 2-3 hours  
**Dependencies:** Task 4.1

**Subtasks:**
- [ ] Save aggregated data to `s3://nfl-trusted/`
- [ ] Create separate datasets: team_stats, player_stats, game_analysis
- [ ] Optimize file structure for querying (partition by season)
- [ ] Generate summary reports in CSV format for easy analysis
- [ ] Test complete Bronze → Silver → Gold pipeline

**Files to Modify:**
- `notebooks/gold_aggregation.py`

**Success Criteria:**
- Business-ready data stored in `s3://nfl-trusted/`
- Multiple analysis datasets available
- CSV files can be opened in Excel/BI tools

---

### Phase 5: Testing and Validation 🚧 **IN PROGRESS**

#### Task 5.1: Unit Testing Implementation 🚧
**Priority:** Medium  
**Estimated Time:** 3-4 hours  
**Dependencies:** Task 4.2

**Subtasks:**
- [ ] Create unit tests for all utility functions
- [ ] Mock S3 operations using `moto` library
- [ ] Test data quality validation functions
- [ ] Validate business metric calculations
- [ ] Test error handling scenarios

**Files to Modify:**
- `tests/test_utils.py`
- Create additional test files as needed

**Success Criteria:**
- All unit tests pass: `pytest tests/ -v`
- Code coverage >80% for core functions
- Mock tests validate S3 integration logic

---

#### Task 5.2: End-to-End Integration Testing ⏳ **PENDING**
**Priority:** Medium  
**Estimated Time:** 2-3 hours  
**Dependencies:** Task 5.1

**Subtasks:**
- [ ] Test complete pipeline with sample data (1 week)
- [ ] Validate data consistency across all three layers
- [ ] Test pipeline with multiple weeks of data
- [ ] Verify S3 storage and retrieval accuracy
- [ ] Performance test with larger datasets

**Success Criteria:**
- Complete pipeline runs without errors
- Data integrity maintained across all layers
- Performance is acceptable for MVP scope

---

### Phase 6: Documentation and MVP Delivery (Day 11)

#### Task 6.1: User Documentation ⏳
**Priority:** Medium  
**Estimated Time:** 2-3 hours  
**Dependencies:** Task 5.2

**Subtasks:**
- [ ] Update README.md with actual usage examples
- [ ] Create step-by-step setup guide with screenshots
- [ ] Document common troubleshooting issues
- [ ] Add example outputs and expected results
- [ ] Create quick start guide for new users

**Files to Modify:**
- `README.md`
- Create `docs/` directory with additional documentation

---

#### Task 6.2: MVP Demo Preparation ⏳
**Priority:** Low  
**Estimated Time:** 2 hours  
**Dependencies:** Task 6.1

**Subtasks:**
- [ ] Process 2024 NFL season data (Weeks 1-4)
- [ ] Generate sample analytics and insights
- [ ] Create simple visualization of results (optional)
- [ ] Prepare demo script showing key features
- [ ] Document next steps for production scaling

**Success Criteria:**
- Complete NFL data pipeline demonstrated
- Real data processed and analyzed
- Clear path for future enhancements

---

## MVP Success Criteria Summary

### Functional Requirements ✅
- [x] **Data Ingestion:** Fetch NFL game data from nfl-data-py
- [ ] **Storage:** Store data in S3 using medallion architecture  
- [ ] **Processing:** Clean and validate data through Silver layer
- [ ] **Analytics:** Generate business metrics in Gold layer
- [ ] **CLI Interface:** Command-line execution for all pipeline stages

### Technical Requirements ✅
- [x] **Local Development:** Runs on local Python environment
- [x] **S3 Integration:** Direct integration with your AWS S3 buckets
- [x] **Error Handling:** Robust error handling and logging
- [ ] **Testing:** Unit and integration tests for core functionality
- [x] **Documentation:** Comprehensive setup and usage documentation

### Business Requirements ✅
- [ ] **Current Data:** Process 2024 NFL season data
- [ ] **Team Analytics:** Team performance statistics
- [ ] **Data Quality:** Clean, validated datasets
- [ ] **Scalability:** Ready for future Databricks migration

## Estimated Timeline: 11 Days Total
- **Phase 1:** 2 days (Environment and Foundation)
- **Phase 2:** 2 days (Bronze Layer)
- **Phase 3:** 2 days (Silver Layer)  
- **Phase 4:** 2 days (Gold Layer)
- **Phase 5:** 2 days (Testing and Validation)
- **Phase 6:** 1 day (Documentation and Demo)

## Risk Mitigation
- **NFL Data API Issues:** Have backup sample data ready
- **S3 Connectivity Problems:** Test credentials and permissions early
- **Performance Issues:** Start with small datasets, optimize later
- **Time Constraints:** Focus on core functionality first, defer nice-to-have features

---

## 🎯 **NFL GAME PREDICTION DATA MODEL IMPLEMENTATION** 

### Newly Added ✅ **COMPLETED DOCUMENTATION**
- **NFL Game Prediction Data Model**: `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` - Comprehensive data model for ML-powered game prediction
- **NFL Data Dictionary**: `docs/NFL_DATA_DICTIONARY.md` - Complete table definitions with 200+ columns, data types, and relationships
- **Implementation Guide**: `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` - 8-week phased implementation roadmap

### Implementation Priority 🚧 **NEXT PHASES**

#### Phase A: Enhanced Silver Layer (Weeks 1-2)
**Based on data model specifications:**
- [ ] **Team Performance Metrics**: Implement offensive/defensive efficiency calculations (EPA per play, success rates)
- [ ] **Advanced Player Stats**: Create comprehensive player performance tracking across multiple metrics
- [ ] **Situational Analytics**: Weather impact, rest advantages, injury tracking
- [ ] **Temporal Features**: Rolling performance metrics, season progression indicators

#### Phase B: Prediction-Ready Gold Layer (Weeks 3-4) 
**Following data model architecture:**
- [ ] **Feature Engineering Pipeline**: Automated generation of 200+ ML features
- [ ] **Advanced NFL Analytics**: EPA, Win Probability, CPOE calculations
- [ ] **Historical Context**: Head-to-head records, coaching matchups, playoff implications
- [ ] **Real-time Updates**: Game-day feature refresh and prediction scoring

#### Phase C: ML Prediction Framework (Weeks 5-6)
**Implementing prediction system:**
- [ ] **Model Training Pipeline**: Random Forest, Neural Networks, XGBoost implementations
- [ ] **Cross-Validation**: Leave-One-Season-Out validation framework
- [ ] **Performance Monitoring**: Target 65%+ accuracy, <3.5 point spread MAE
- [ ] **Prediction API**: Real-time game prediction service

### Data Model Integration Notes
- **Builds on existing Bronze layer** (16 games, 2,816 plays from 2023 Week 1)
- **Compatible with medallion architecture** and current S3 bucket structure
- **Uses established patterns** from `src/nfl_data_integration.py`
- **Production-grade design** with comprehensive data quality framework

---

---

## Fantasy Football System (March 2026)

### Phase FF-1: Bronze Layer — Player Data ✅ **COMPLETED**
**Completed:** March 2026

- [x] Add `fetch_player_weekly` to `NFLDataFetcher` (nfl.import_weekly_data)
- [x] Add `fetch_snap_counts` (nfl.import_snap_counts)
- [x] Add `fetch_injuries` (nfl.import_injuries)
- [x] Add `fetch_rosters` (nfl.import_rosters)
- [x] Add `fetch_player_seasonal` (nfl.import_seasonal_data)
- [x] Extend `bronze_ingestion_simple.py` with 5 new `--data-type` options
- [x] Add `SCORING_CONFIGS`, `ROSTER_CONFIGS`, `PLAYER_DATA_SEASONS` to `config.py`
- [x] Add S3 key templates for player Bronze/Silver/Gold paths to `config.py`

**Files modified:** `src/config.py`, `src/nfl_data_integration.py`, `scripts/bronze_ingestion_simple.py`

---

### Phase FF-2: Silver Layer — Player Analytics ✅ **COMPLETED**
**Completed:** March 2026

- [x] `src/player_analytics.py` — `compute_usage_metrics` (target/carry/air yards share, snap%)
- [x] `src/player_analytics.py` — `compute_opponent_rankings` (positional defense rank 1-32)
- [x] `src/player_analytics.py` — `compute_rolling_averages` (3-week, 6-week, season-to-date)
- [x] `src/player_analytics.py` — `compute_game_script_indicators` (blowout/close/losing)
- [x] `src/player_analytics.py` — `compute_venue_splits` (home/away, dome/outdoor)
- [x] `scripts/silver_player_transformation.py` — full Silver CLI for single or multiple seasons

**Files created:** `src/player_analytics.py`, `scripts/silver_player_transformation.py`

---

### Phase FF-3: Projection Engine ✅ **COMPLETED**
**Completed:** March 2026

- [x] `src/scoring_calculator.py` — single-player and DataFrame fantasy scoring (PPR/Half/Standard/custom)
- [x] `src/projection_engine.py` — `generate_weekly_projections` (roll3/roll6/STD + usage + matchup)
- [x] `src/projection_engine.py` — `generate_preseason_projections` (2-season weighted average)
- [x] `scripts/generate_projections.py` — CLI for `--week` (weekly) and `--preseason` modes
- [x] All smoke tests passing: scoring calculator, usage metrics, rolling averages

**Files created:** `src/scoring_calculator.py`, `src/projection_engine.py`, `scripts/generate_projections.py`

---

### Phase FF-4: Draft Tool ✅ **COMPLETED**
**Completed:** March 2026

- [x] `src/draft_optimizer.py` — `DraftBoard` (available pool + roster tracking)
- [x] `src/draft_optimizer.py` — `DraftAdvisor` (recommendations, scarcity alerts, best available)
- [x] `src/draft_optimizer.py` — `compute_value_scores` (model rank, ADP diff, VORP, value tier)
- [x] `scripts/draft_assistant.py` — interactive CLI (snake draft, undo, search, all advisor commands)
- [x] `output/projections/` directory created for local CSV output

**Files created:** `src/draft_optimizer.py`, `scripts/draft_assistant.py`

---

### Phase FF-5: Skills & MCP Integration ✅ **COMPLETED**
**Completed:** March 2026

**Skills created (`.claude/skills/`):**
- [x] `/ingest` — Bronze ingestion + Sleeper API data types
- [x] `/weekly-pipeline` — full Bronze → Silver → Gold chain
- [x] `/validate-data` — NFL business rules + DuckDB SQL on Parquet
- [x] `/test` — pytest + module import + script compile checks
- [x] `/draft-prep` — preseason projections + ADP fetch (Sleeper/FantasyPros) + draft assistant

**MCPs added to `.mcp.json`:**
- [x] `duckdb` — SQL queries on local Parquet files (enabled)
- [x] `fetch` — HTTP/ADP scraping from FantasyPros (enabled)
- [x] `sleeper` — Sleeper API for ADP, rosters, draft boards (enabled)
- [x] `neo4j` — Phase 5 graph analysis (configured, not yet enabled)
- [x] Neo4j connection stubs added to `.env`

---

### Phase FF-6: Upcoming (Month 2–5 to August 2026 Drafts)

#### Task FF-6.1: Injury Filter in Projections 🚧
- [ ] Load current week's injury data from Bronze layer
- [ ] Apply status multiplier: active=1.0, questionable=0.85, doubtful=0.5, out=0.0
- [ ] Add `injury_status` column to projection output

#### Task FF-6.2: Automated ADP Refresh ⏳
- [ ] Schedule Sleeper MCP call to refresh `data/adp.csv` weekly during season
- [ ] Add pre-draft trigger: re-fetch ADP day-of-draft for most current rankings
- [ ] Version ADP files by date: `data/adp_YYYYMMDD.csv`

#### Task FF-6.3: In-Season Weekly Pipeline Automation ⏳
- [ ] Create `scripts/run_weekly_pipeline.sh` — wraps Bronze → Silver → Gold → projections
- [ ] Add GitHub Actions workflow: trigger every Tuesday morning (post-MNF)
- [ ] Slack/email notification with top projection changes week-over-week

#### Task FF-6.4: Model Evaluation & Tuning ⏳
- [ ] Backtest 2023/2024 seasons: compare projected vs. actual fantasy points
- [ ] Calculate MAE per position, identify systematic biases
- [ ] Tune RECENCY_WEIGHTS in `projection_engine.py` based on backtest results
- [ ] Add confidence intervals to projections (high/medium/low floor/ceiling)

#### Task FF-6.5: Draft Tool Enhancements ⏳
- [ ] Live Sleeper league integration — import actual league rosters during live draft
- [ ] Keeper league support — pre-mark kept players as drafted before session starts
- [ ] Export draft results to CSV for season-long reference

---

### Phase FF-7: Neo4j Graph Layer ⏳ **DEFERRED (Post-Season)**

**Trigger:** After projection engine is tuned and weekly pipeline is stable

- [ ] Provision Neo4j AuraDB instance and update `.env` with connection details
- [ ] Enable `neo4j` in `.claude/settings.local.json` `enabledMcpjsonServers`
- [ ] WR-CB matchup graphs: historical performance by coverage type
- [ ] QB-WR target share directed graphs (weighted by season)
- [ ] Injury cascade trees: depth chart impact traversal

---

*This task list is updated as development progresses. Completed tasks retain full implementation notes for reference.*
