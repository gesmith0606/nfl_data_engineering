# NFL Data Engineering Pipeline — AI Assistant Instructions

**Project:** NFL Data Engineering Pipeline + Fantasy Football Projection System
**Architecture:** Medallion (Bronze → Silver → Gold) + Fantasy Projection Engine
**Last Updated:** March 2026
**Current Phase:** Fantasy Football System complete (Phases 1–4), Neo4j deferred (Phase 5)

---

## Project Overview

A comprehensive NFL data engineering solution built on the **Medallion Architecture** (Bronze → Silver → Gold) using local Python execution with AWS S3 storage. The pipeline extends into a full **Fantasy Football Projection System** targeting the 2026–2027 NFL season, including a pre-season draft tool and weekly in-season projections.

**Data Sources:**
- `nfl-data-py`: Game schedules, play-by-play, player weekly stats, snap counts, injuries, rosters, seasonal aggregates
- **Sleeper API** (via MCP): Live ADP data, league rosters, draft boards
- **FantasyPros** (via fetch MCP): Consensus ADP rankings

**Infrastructure:**
- S3 Buckets: `nfl-raw` (Bronze), `nfl-refined` (Silver), `nfl-trusted` (Gold) — us-east-2
- Local execution with boto3 S3 integration
- MCP servers for data fetching, SQL analytics, and draft tooling

---

## Architecture & Data Flow

```
nfl-data-py + Sleeper API (MCP) + FantasyPros (fetch MCP)
        ↓
Bronze Layer — s3://nfl-raw/
  games/, plays/, teams/, players/weekly/, players/snaps/,
  players/injuries/, players/rosters/, players/seasonal/
        ↓
Silver Layer — s3://nfl-refined/
  players/usage/    (target share, carry share, air yards share, snap %)
  defense/positional/  (opponent rankings 1-32 per position)
  players/rolling/  (3-week, 6-week, season-to-date rolling averages)
        ↓
Gold Layer — s3://nfl-trusted/
  projections/      (weekly + preseason, PPR/Half-PPR/Standard)
        ↓
Draft Tool (local)
  output/projections/   (CSVs for draft assistant)
  data/adp.csv          (Sleeper/FantasyPros ADP)
        ↓
[Phase 5 — deferred] Neo4j
  WR-CB matchup graphs, target share networks, injury cascades
```

**S3 Partitioning pattern:** `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`

---

## Current Development Status

### Completed ✅
- **Bronze Layer**: All 8 data types operational (schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal)
- **Silver Layer**: Player analytics — usage metrics, opponent defensive rankings (1-32), rolling averages (3/6-week + season-to-date), game script indicators, venue splits
- **Gold Layer**: Weekly projections + preseason draft projections for QB/RB/WR/TE
- **Fantasy Scoring Engine**: PPR, Half-PPR, Standard — single-player and vectorized DataFrame
- **Draft Tool**: Interactive CLI with snake draft, ADP comparison, VORP, positional scarcity
- **Project Skills**: `/ingest`, `/weekly-pipeline`, `/validate-data`, `/test`, `/draft-prep`
- **MCP Integration**: DuckDB (Parquet SQL), fetch (ADP scraping), Sleeper (live ADP/rosters)

### In Progress 🚧
- Injury status filtering in projection engine
- Automated weekly Sleeper ADP refresh to `data/adp.csv`
- Cron/scheduled in-season pipeline (Bronze → Silver → Gold → projections weekly)

### Planned ⏳
- **Phase 5 — Neo4j**: WR-CB matchup graphs, QB-WR target share networks, injury cascade trees
- Advanced ML models (Random Forest/XGBoost) to replace weighted-average baseline
- Live Sleeper league integration in draft assistant

---

## Key Files

### Source Modules (`src/`)
| File | Purpose |
|---|---|
| `config.py` | S3 paths, SCORING_CONFIGS, ROSTER_CONFIGS, PLAYER_DATA_SEASONS |
| `nfl_data_integration.py` | NFLDataFetcher — all 8 fetch methods + validation |
| `player_analytics.py` | Usage metrics, opponent rankings, rolling averages, game script |
| `scoring_calculator.py` | Fantasy point calculation (single dict + DataFrame, any scoring format) |
| `projection_engine.py` | Weekly + preseason projection models |
| `draft_optimizer.py` | DraftBoard, DraftAdvisor, compute_value_scores, VORP |
| `utils.py` | Shared utility functions |

### Pipeline Scripts (`scripts/`)
| File | Purpose |
|---|---|
| `bronze_ingestion_simple.py` | CLI — all 8 Bronze data types |
| `silver_player_transformation.py` | Silver transform — usage, rolling, opp rankings |
| `generate_projections.py` | Weekly (`--week`) or preseason (`--preseason`) projections |
| `draft_assistant.py` | Interactive draft CLI |
| `list_bronze_contents.py` | S3 Bronze content viewer |
| `explore_bronze_data.py` | Interactive Bronze data exploration |
| `validate_project.py` | Full AWS + NFL API validation |

### Project Skills (`.claude/skills/`)
| Skill | Purpose | MCPs |
|---|---|---|
| `/ingest` | Bronze ingestion + Sleeper data types | Sleeper |
| `/weekly-pipeline` | Full Bronze→Silver→Gold chain | — |
| `/validate-data` | Business rules + DuckDB SQL checks | DuckDB |
| `/test` | Full test suite + import checks | — |
| `/draft-prep` | Projections + ADP fetch + draft assistant | Sleeper, fetch |

---

## MCP Servers

| Server | Enabled | Purpose |
|---|---|---|
| `aws-core-server` | ✅ | AWS operations |
| `aws-s3-server` | ✅ | Direct S3 read/write |
| `aws-docs-server` | ✅ | AWS documentation lookup |
| `github-server` | ✅ | PR/issue/branch management |
| `duckduckgo-search` | ✅ | Web search |
| `duckdb` | ✅ | SQL on local Parquet files — use in `/validate-data` |
| `fetch` | ✅ | HTTP fetch — pull ADP CSVs from FantasyPros |
| `sleeper` | ✅ | Sleeper API — ADP, rosters, leagues, draft boards |
| `neo4j` | Configured, disabled | Phase 5 matchup graphs — enable when ready |

Config: `.mcp.json` (server definitions) and `.claude/settings.local.json` (enabled list)

---

## Fantasy Football System

### Scoring Formats (`src/config.py → SCORING_CONFIGS`)
```python
# PPR: reception=1.0, rush_yd=0.1, rec_yd=0.1, TD=6, pass_yd=0.04, pass_td=4, INT=-2
# Half-PPR: reception=0.5 (all others same as PPR)
# Standard: reception=0.0 (all others same as PPR)
```

### Roster Formats (`ROSTER_CONFIGS`): `standard`, `superflex`, `2qb`

### Projection Model Logic
1. Weighted blend: roll3 (50%) + roll6 (30%) + season-to-date (20%)
2. Usage multiplier: snap%/target-share → [0.7, 1.3] range
3. Matchup adjustment: opponent defensive rank → [0.85, 1.15] factor
4. Convert projected stats → fantasy points via `scoring_calculator`

### Draft Tool Key Commands
`rec`, `pick <name>`, `draft <name>`, `best [pos]`, `undervalued`, `overvalued`, `roster`, `undo`, `skip`, `positions`, `top [N]`, `search <name>`

---

## NFL Business Rules

- Regular season: Weeks 1–18, 14–16 games per week
- Valid downs: 1–4 | Valid yard lines: 0–100 | Valid distance: 1–99
- 32 NFL teams with consistent abbreviations
- Valid seasons: 1999–2026 (nfl-data-py coverage)
- Fantasy positions: QB, RB, WR, TE
- Projected points: always ≥ 0 for skill positions

---

## Development Patterns

### Error Handling
Always include error handling for:
- NFL API calls (network timeouts, rate limits)
- S3 operations (credentials, bucket access, upload failures)
- Data validation (missing columns, invalid values, empty DataFrames)

### Data Processing
- Primary format: Pandas DataFrames
- Storage format: Parquet
- Partitioning: always `season=YYYY/week=WW`
- Validate at each layer boundary with `NFLDataFetcher.validate_data()`
- ADP data: stored in `data/adp.csv` locally, not in S3

### Code Style
- Descriptive names with NFL context: `fetch_player_weekly`, `compute_usage_metrics`
- Type hints on all function signatures
- Docstrings: purpose, args, returns
- Follow patterns in `src/nfl_data_integration.py`

### Agent Workflow (for significant changes)
1. `system-architect` — design approach
2. `code-implementation-specialist` — write code
3. `/simplify` — review for quality/efficiency
4. `test-engineer` — add coverage
5. `code-reviewer` (MANDATORY before commit)
6. `docs-specialist` — update docs

### When to Use `/batch`
Multi-season Bronze ingestion or Silver transformation across 5+ seasons — avoids 25+ sequential CLI calls.

---

## Environment Variables (`.env`)
```bash
AWS_REGION=us-east-2
S3_BUCKET_BRONZE=nfl-raw
S3_BUCKET_SILVER=nfl-refined
S3_BUCKET_GOLD=nfl-trusted
DEFAULT_SEASON=2024
DEFAULT_WEEK=1

# Neo4j (Phase 5 — uncomment when ready)
# NEO4J_URI=neo4j+s://your-aura-instance.databases.neo4j.io
# NEO4J_USERNAME=neo4j
# NEO4J_PASSWORD=your-password
```

---

## Common Commands Reference
```bash
# Environment
source venv/bin/activate

# Bronze — player data
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type player_weekly
python scripts/bronze_ingestion_simple.py --season 2024 --data-type player_seasonal

# Silver
python scripts/silver_player_transformation.py --season 2024

# Projections
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr
python scripts/generate_projections.py --week 10 --season 2025 --scoring ppr

# Draft
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5

# Testing
python -m pytest tests/ -v
python scripts/validate_project.py
```
