# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment (required for all operations)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt

# Setup project (first time only)
./setup.sh
```

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test types
python tests/test_utils.py
python scripts/test_aws_connectivity.py
python scripts/test_nfl_data.py
python scripts/validate_project.py

# Test individual components
python src/nfl_data_integration.py
```

### Data Pipeline Operations
```bash
# Bronze layer — game data
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type schedules
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type pbp

# Bronze layer — player data (all types)
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type player_weekly
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type snap_counts
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type injuries
python scripts/bronze_ingestion_simple.py --season 2024 --data-type rosters
python scripts/bronze_ingestion_simple.py --season 2024 --data-type player_seasonal

# Silver layer — player transformation
python scripts/silver_player_transformation.py --season 2024
python scripts/silver_player_transformation.py --seasons 2022 2023 2024 --week 10

# Gold layer — projections
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr
python scripts/generate_projections.py --week 1 --season 2026 --scoring ppr

# Draft assistant (interactive)
python scripts/draft_assistant.py --scoring half_ppr --roster-format standard --teams 12 --my-pick 5

# Data exploration
python scripts/list_bronze_contents.py
python scripts/explore_bronze_data.py
```

### Skills (Claude Code slash commands)
```bash
/ingest 2024 1 player_weekly      # Bronze ingestion
/weekly-pipeline 2026 1 half_ppr  # Full Bronze→Silver→Gold chain
/validate-data 2024 10            # NFL business rule + DuckDB validation
/test                             # Full test suite
/draft-prep 2026 half_ppr 5 12    # Pre-season draft workflow
/simplify                         # Code quality review of changed files
/batch                            # Parallel multi-season operations
```

### Code Quality
```bash
python -m black src/ tests/ scripts/
python -m isort src/ tests/ scripts/
python -m flake8 src/ tests/ scripts/
```

## Architecture Overview

This is an NFL data engineering pipeline implementing the **Medallion Architecture** with local development, AWS S3 cloud storage, and a Fantasy Football Projection System targeting the 2026-2027 NFL season.

### Key Architectural Patterns
- **Medallion Architecture**: Bronze (raw) → Silver (cleaned) → Gold (analytics-ready)
- **Local Development**: Python virtual environment as primary execution environment
- **Cloud Storage**: AWS S3 buckets for all pipeline layers
- **Fantasy Football Engine**: Weekly projections + pre-season draft tool (PPR/Half-PPR/Standard)
- **Neo4j (Phase 5)**: Deferred — WR-CB matchup graphs, target share networks

### Data Flow
```
nfl-data-py + Sleeper API
        ↓
Bronze Layer (s3://nfl-raw/)      — raw game, player, snap, injury, roster data
        ↓
Silver Layer (s3://nfl-refined/)  — usage metrics, rolling averages, opp rankings
        ↓
Gold Layer (s3://nfl-trusted/)    — projections, draft rankings
        ↓
Draft Tool                        — rankings, ADP comparison, live draft optimizer
```

### S3 Storage Structure
```
nfl-raw/
├── games/season=YYYY/week=WW/schedules_YYYYMMDD_HHMMSS.parquet
├── plays/season=YYYY/week=WW/pbp_YYYYMMDD_HHMMSS.parquet
├── teams/season=YYYY/teams_YYYYMMDD_HHMMSS.parquet
├── players/weekly/season=YYYY/week=WW/player_weekly_*.parquet
├── players/snaps/season=YYYY/week=WW/snap_counts_*.parquet
├── players/injuries/season=YYYY/week=WW/injuries_*.parquet
├── players/rosters/season=YYYY/rosters_*.parquet
└── players/seasonal/season=YYYY/player_seasonal_*.parquet

nfl-refined/
├── players/usage/season=YYYY/week=WW/usage_*.parquet
├── defense/positional/season=YYYY/week=WW/opp_rankings_*.parquet
└── players/rolling/season=YYYY/week=WW/rolling_*.parquet

nfl-trusted/
└── projections/season=YYYY/week=WW/projections_*.parquet
```

## Key Components

### Core Modules (`src/`)
- **`config.py`**: S3 paths, SCORING_CONFIGS (PPR/Half-PPR/Standard), ROSTER_CONFIGS, player season constants
- **`nfl_data_integration.py`**: `NFLDataFetcher` class — game, play-by-play, team, and all 5 player fetch methods
- **`player_analytics.py`**: Usage metrics (target share, carry share, air yards), opponent rankings (1-32), rolling averages, game script indicators
- **`scoring_calculator.py`**: Configurable fantasy point calculation — single-player dict and vectorized DataFrame
- **`projection_engine.py`**: Weekly projections (roll3/roll6/STD blend + usage multiplier + matchup factor) and preseason projections
- **`draft_optimizer.py`**: `DraftBoard`, `DraftAdvisor`, `compute_value_scores` — ADP comparison, VORP, positional scarcity
- **`utils.py`**: Shared utility functions

### Pipeline Scripts (`scripts/`)
- **`bronze_ingestion_simple.py`**: CLI for all 8 Bronze data types (schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal)
- **`silver_player_transformation.py`**: Silver layer — usage metrics, rolling averages, opponent rankings
- **`generate_projections.py`**: Projection CLI — weekly mode (`--week`) or preseason mode (`--preseason`)
- **`draft_assistant.py`**: Interactive draft CLI with snake draft support and real-time recommendations
- **`list_bronze_contents.py`**: S3 Bronze content exploration
- **`explore_bronze_data.py`**: Interactive Bronze data analysis
- **`validate_project.py`**: Full project validation including AWS and NFL API connectivity

### Project Skills (`.claude/skills/`)
| Skill | Trigger | MCPs used |
|---|---|---|
| `/ingest` | Fetch any Bronze data type | Sleeper MCP (for `sleeper_adp`, `sleeper_rosters`) |
| `/weekly-pipeline` | Full in-season pipeline run | — |
| `/validate-data` | Data quality checks | DuckDB MCP (SQL on Parquet) |
| `/test` | Run test suite | — |
| `/draft-prep` | Pre-season draft workflow | Sleeper MCP + fetch MCP (ADP) |

## Configuration

### AWS Configuration
- **Region**: us-east-2 (Ohio)
- **Buckets**: Bronze: `nfl-raw` | Silver: `nfl-refined` | Gold: `nfl-trusted`
- **Credentials**: Configured via AWS CLI (`aws configure`) or `.env` file

### Fantasy Scoring Formats
Defined in `src/config.py` → `SCORING_CONFIGS`:
- **PPR**: 1.0 pt/reception
- **Half-PPR**: 0.5 pt/reception
- **Standard**: 0.0 pt/reception
All formats: 0.1/rush yd, 0.1/rec yd, 6/TD, 0.04/pass yd, 4/pass TD, -2/INT, -2/fumble lost

### Roster Formats
Defined in `src/config.py` → `ROSTER_CONFIGS`: `standard`, `superflex`, `2qb`

### MCP Servers (`.mcp.json`)
| Server | Status | Purpose |
|---|---|---|
| `aws-core-server` | Enabled | AWS operations |
| `aws-s3-server` | Enabled | Direct S3 read/write |
| `aws-docs-server` | Enabled | AWS documentation |
| `github-server` | Enabled | PR/issue management |
| `duckduckgo-search` | Enabled | Web search |
| `duckdb` | Enabled | SQL queries on local Parquet files |
| `fetch` | Enabled | HTTP/ADP scraping (FantasyPros) |
| `sleeper` | Enabled | Sleeper API — ADP, rosters, drafts |
| `neo4j` | Configured, disabled | Phase 5 graph analysis (activate when ready) |

### Environment Variables (`.env`)
```bash
# AWS Configuration
AWS_REGION=us-east-2
S3_BUCKET_BRONZE=nfl-raw
S3_BUCKET_SILVER=nfl-refined
S3_BUCKET_GOLD=nfl-trusted

# NFL Data Settings
DEFAULT_SEASON=2024
DEFAULT_WEEK=1

# Neo4j Configuration (Phase 5 - deferred)
# NEO4J_URI=neo4j+s://your-aura-instance.databases.neo4j.io
# NEO4J_USERNAME=neo4j
# NEO4J_PASSWORD=your-password
```

### Data Model Documentation
- **NFL Game Prediction Data Model**: `docs/NFL_GAME_PREDICTION_DATA_MODEL.md`
- **NFL Data Dictionary**: `docs/NFL_DATA_DICTIONARY.md`
- **Implementation Guide**: `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md`

## NFL Data Context

### Data Types Available (Bronze Layer)
1. **Game Schedules** (`schedules`): Game metadata, scores, dates, teams
2. **Play-by-Play** (`pbp`): Detailed play data with downs, yards, players
3. **Team Stats** (`teams`): Team information and statistics
4. **Player Weekly** (`player_weekly`): Weekly rushing/receiving/passing stats per player
5. **Snap Counts** (`snap_counts`): Snap % and route participation per player per week
6. **Injuries** (`injuries`): Weekly injury reports (active/questionable/out/IR)
7. **Rosters** (`rosters`): Depth chart positions and team assignments
8. **Player Seasonal** (`player_seasonal`): Full-season aggregates for trend analysis

### Player Training Data
- Seasons: 2020–2025 (`PLAYER_DATA_SEASONS` in `config.py`)
- Fantasy-relevant positions: QB, RB, WR, TE

### NFL Business Rules for Validation
- Games per week: 14–16 regular season games
- Season structure: Weeks 1-18 regular season, then playoffs
- Team validation: 32 NFL teams with consistent abbreviations
- Play validation: Down (1-4), distance (1-99), yard line (0-100)
- Score logic: Points scored must align with play outcomes

## Development Patterns

### Error Handling
Always include robust error handling for:
- NFL API calls (network timeouts, rate limits)
- S3 operations (credentials, bucket access, upload failures)
- Data validation (missing columns, invalid values)

### Data Processing
- **Primary Format**: Pandas DataFrames for all data manipulation
- **Storage Format**: Parquet files for efficient storage and querying
- **Partitioning**: Always partition by `season=YYYY/week=WW` for performance
- **Validation**: Validate data at each layer boundary using `NFLDataFetcher.validate_data()`
- **Local ADP data**: Sleeper/FantasyPros ADP saved to `data/adp.csv` (not in S3)

### Code Style
- Use descriptive function names with NFL context (e.g., `fetch_player_weekly`, `compute_usage_metrics`)
- Include type hints for function parameters and return values
- Document functions with docstrings including purpose, parameters, and return values
- Follow existing patterns in `src/nfl_data_integration.py` for consistency

## Current Development Status

### Completed ✅
- Bronze Layer: Game data (schedules, pbp, teams) + all player data types
- Silver Layer: Player analytics — usage metrics, rolling averages, opponent rankings
- Gold Layer: Weekly projections + preseason draft projections
- Fantasy Scoring: PPR/Half-PPR/Standard configurable scoring engine
- Draft Tool: Interactive CLI with ADP comparison, VORP, positional scarcity alerts
- Project Skills: `/ingest`, `/weekly-pipeline`, `/validate-data`, `/test`, `/draft-prep`
- MCP Integration: DuckDB, fetch, Sleeper added alongside existing AWS/GitHub MCPs

### In Progress 🚧
- Model tuning: Incorporate injury status filter from Bronze injuries data into projections
- ADP data pipeline: Automate Sleeper ADP fetch into `data/adp.csv` on a schedule
- In-season weekly pipeline: Cron/scheduled run of Bronze → Silver → Gold → projections

### Planned ⏳
- Neo4j (Phase 5): WR-CB matchup graphs, target share networks, injury cascade trees
- Advanced ML models: Replace weighted average baseline with Random Forest/XGBoost
- Live draft optimizer enhancements: Real-time Sleeper league integration

## Agent Integration Framework

This project uses specialized Claude Code agents to accelerate development.

### Available Agents
- **🏗️ system-architect**: Design architecture, data schemas, API contracts
- **💻 code-implementation-specialist**: Implement features following project patterns
- **🔍 code-reviewer** (MANDATORY): Review all production code before commits
- **🧪 test-engineer**: Create test suites, improve coverage, design validation
- **📋 project-orchestrator**: Coordinate multi-step projects across agents
- **📚 docs-specialist**: Create and maintain documentation
- **⚙️ devops-engineer**: CI/CD, containerization, AWS infrastructure

### Development Workflow

#### Phase 1: Architecture & Planning
1. `project-orchestrator`: Break down requirements into tasks
2. `system-architect`: Design component structure and data flow

#### Phase 2: Implementation
3. `code-implementation-specialist`: Write the implementation
4. `/simplify`: Review changed code for quality and efficiency
5. `test-engineer`: Create test coverage
6. `code-reviewer`: Final review before commit

#### Phase 3: Documentation & Deployment
7. `docs-specialist`: Update documentation
8. `devops-engineer`: Handle deployment and infrastructure

### Quality Gates
- **Code Review**: All implementations must pass `code-reviewer` validation
- **Testing**: Minimum 80% test coverage for new features
- **Documentation**: All public interfaces must have updated documentation
- **NFL Validation**: All data transformations must pass NFL business rule checks

## Important Notes

- **Virtual Environment**: Always activate `venv` before running any Python commands
- **AWS Credentials**: Ensure AWS credentials are configured before S3 operations
- **Data Dependencies**: Bronze layer data must exist before Silver layer development
- **NFL Seasons**: Valid seasons range from 1999-2026 based on nfl-data-py coverage
- **Testing**: Run `/test` or `validate_project.py` after any significant changes
- **Agent Workflow**: Follow the agent integration framework for all development tasks
- **Skills**: Use project skills (`/ingest`, `/weekly-pipeline`, etc.) for recurring pipeline operations
- **MCP Usage**: DuckDB MCP for local Parquet queries; Sleeper/fetch MCPs for ADP data
