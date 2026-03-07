# NFL Data Engineering Pipeline — AI Assistant Instructions

**Project:** NFL Data Engineering Pipeline + Fantasy Football Projection System
**Architecture:** Medallion (Bronze → Silver → Gold) + Fantasy Projection Engine
**Last Updated:** March 2026
**Current Phase:** Fantasy Football System complete (Phases 1–5 of pipeline); Neo4j deferred

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
  players/usage/       (target share, carry share, air yards share, snap %)
  defense/positional/  (opponent rankings 1-32 per position)
  players/rolling/     (3-week, 6-week, season-to-date rolling averages)
        ↓
Gold Layer — s3://nfl-trusted/
  projections/         (weekly + preseason, PPR/Half-PPR/Standard)
        ↓
Draft Tool (local)
  output/projections/  (CSVs for draft assistant)
  data/adp.csv         (Sleeper/FantasyPros ADP)
        ↓
[Phase 5 — deferred] Neo4j
  WR-CB matchup graphs, target share networks, injury cascades
```

**S3 partitioning pattern:** `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`

**Read rule:** Always use `download_latest_parquet()` from `src/utils.py`. Never scan the full prefix — reads are scoped to the `season/week/` level and return only the single latest file per partition.

---

## Current Development Status

### Completed ✅
- **Bronze Layer**: All 8 data types operational (schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal)
- **Silver Layer**: Usage metrics, opponent defensive rankings (1-32), rolling averages (3/6-week + season-to-date), game script indicators, venue splits
- **Gold Layer**: Weekly projections + preseason draft projections for QB/RB/WR/TE
- **Fantasy Scoring Engine**: PPR, Half-PPR, Standard — single-player and vectorized DataFrame
- **Projection Engine Enhancements**: Bye week handling, rookie/new player fallback baselines, Vegas lines integration
- **Draft Tool**: Interactive CLI — snake draft, mock draft simulation, auction draft, waiver wire
- **S3 Deduplication**: `get_latest_s3_key()` and `download_latest_parquet()` in `src/utils.py`; all scripts use latest-file convention
- **Pipeline Monitoring**: GitHub Actions weekly cron + `check_pipeline_health.py` for S3 freshness and file size validation
- **Security**: Pre-commit credential scanning blocks `AKIA*`, `github_pat_*`, and private key patterns
- **Token Efficiency**: `.claudeignore` excludes venv/, __pycache__/, output/, data/, docs/, *.parquet
- **Project Skills**: `/ingest`, `/weekly-pipeline`, `/validate-data`, `/test`, `/draft-prep`
- **MCP Integration**: DuckDB (Parquet SQL), fetch (ADP scraping), Sleeper (live ADP/rosters)
- **Automated Code Review**: Git hooks with credential scanning and `/simplify` integration

### In Progress 🚧
- Injury status filtering in projection engine
- Automated weekly Sleeper ADP refresh to `data/adp.csv`
- Weekly pipeline cron tuning

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
| `nfl_data_integration.py` | NFLDataFetcher — all 8 fetch methods + validate_data() |
| `player_analytics.py` | Usage metrics, opp rankings, rolling averages, `compute_implied_team_totals()` for Vegas lines |
| `scoring_calculator.py` | Fantasy point calculation (single dict + DataFrame, any scoring format) |
| `projection_engine.py` | Weekly/preseason projections; bye week zeroing, rookie fallback, Vegas multiplier |
| `draft_optimizer.py` | DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor, VORP |
| `utils.py` | Shared utils including `get_latest_s3_key()`, `download_latest_parquet()` |

### Pipeline Scripts (`scripts/`)
| File | Purpose |
|---|---|
| `bronze_ingestion_simple.py` | Bronze CLI — all 8 data types |
| `silver_player_transformation.py` | Silver transform — usage, rolling, opp rankings |
| `generate_projections.py` | Gold CLI — `--week` or `--preseason` |
| `draft_assistant.py` | Interactive draft CLI — snake, auction (`--auction`), simulation (`--simulate`) |
| `check_pipeline_health.py` | S3 freshness (>8 days = WARN), file size (<1KB = ERROR), partition existence |
| `list_bronze_contents.py` | S3 Bronze content viewer |
| `explore_bronze_data.py` | Interactive Bronze data exploration |
| `validate_project.py` | Full AWS + NFL API validation |

### Automation
| File | Purpose |
|---|---|
| `.github/workflows/weekly-pipeline.yml` | Tuesday 9am UTC cron; auto-detects NFL week; opens GitHub issue on failure |
| `.claude/AGENT_FRAMEWORK.md` | Agent workflow details and quality gates |
| `.claudeignore` | Excludes large/irrelevant paths from AI context (venv/, data/, docs/, *.parquet) |

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
| `aws-core-server` | Yes | AWS operations |
| `aws-s3-server` | Yes | Direct S3 read/write |
| `aws-docs-server` | Yes | AWS documentation lookup |
| `github-server` | Yes | PR/issue/branch management |
| `duckduckgo-search` | Yes | Web search |
| `duckdb` | Yes | SQL on local Parquet files — use in `/validate-data` |
| `fetch` | Yes | HTTP fetch — pull ADP CSVs from FantasyPros |
| `sleeper` | Yes | Sleeper API — ADP, rosters, leagues, draft boards |
| `neo4j` | Configured, disabled | Phase 5 matchup graphs — enable when ready |

Config: `.mcp.json` (server definitions) and `.claude/settings.local.json` (enabled list)

---

## Fantasy Football System

### Scoring Formats (`src/config.py → SCORING_CONFIGS`)
```python
# PPR:      reception=1.0, rush_yd=0.1, rec_yd=0.1, TD=6, pass_yd=0.04, pass_td=4, INT=-2
# Half-PPR: reception=0.5 (all others same as PPR)
# Standard: reception=0.0 (all others same as PPR)
```

### Roster Formats (`ROSTER_CONFIGS`): `standard`, `superflex`, `2qb`

### Projection Model Logic
1. Weighted blend: roll3 (50%) + roll6 (30%) + season-to-date (20%)
2. Usage multiplier: snap%/target-share → [0.7, 1.3] range
3. Matchup adjustment: opponent defensive rank → [0.85, 1.15] factor
4. Vegas multiplier (`_vegas_multiplier()`): clips to [0.80, 1.20]; RB run-heavy bonus applied; adds `vegas_multiplier` column
5. Bye week handling (`get_bye_teams()`): zeroes all stats for players on bye; adds `is_bye_week` column
6. Rookie/new player fallback (`_rookie_baseline()`): conservative positional baselines at starter/backup/unknown tiers (100%/40%/25%); adds `is_rookie_projection` column
7. Convert projected stats → fantasy points via `scoring_calculator`

Vegas implied team totals are computed in `player_analytics.py → compute_implied_team_totals()` and consumed by the projection engine.

### Draft Tool Key Commands

**Snake draft:**
`rec`, `pick <name>`, `draft <name>`, `best [pos]`, `undervalued`, `overvalued`, `roster`, `undo`, `skip`, `positions`, `top [N]`, `search <name>`

**Auction draft** (`--auction --budget 200`):
`nominate <name>`, `bid <amount>`, `sold <name> <amount>`, `value [pos]`, `budget`

**Waiver wire:**
`waiver [pos]` — filters available players not in rostered file (pass `--rostered-file` for CSV/JSON of owned players)

**Mock draft simulation** (`--simulate`):
Opponent picks are ADP-based with randomness; produces a draft grade (A/B/C/D) at completion via `MockDraftSimulator`.

---

## NFL Business Rules

- Regular season: Weeks 1–18, 14–16 games per week
- Valid downs: 1–4 | Valid yard lines: 0–100 | Valid distance: 1–99
- 32 NFL teams with consistent abbreviations
- Valid seasons: 1999–2026 (nfl-data-py coverage)
- Fantasy positions: QB, RB, WR, TE
- Projected points: always >= 0 for skill positions
- Player training data: 2020–2025 (`PLAYER_DATA_SEASONS` in config.py)

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
- S3 reads: use `download_latest_parquet()` — never scan full prefix
- ADP data: stored in `data/adp.csv` locally, not in S3

### Code Style
- Descriptive names with NFL context: `fetch_player_weekly`, `compute_usage_metrics`
- Type hints on all function signatures
- Google-style docstrings: purpose, args, returns
- Follow patterns in `src/nfl_data_integration.py`

### Agent Workflow (for significant changes)
See `.claude/AGENT_FRAMEWORK.md` for full details.

1. `system-architect` — design approach
2. `code-implementation-specialist` — write code
3. `git commit` — triggers automated review: credential scan, static analysis, `/simplify` on functions >50 lines
4. `test-engineer` — add coverage (minimum 80% for new features)
5. `code-reviewer` (optional manual review for complex features)
6. `docs-specialist` — update docs

### Automated Code Review (Every Commit)
```
git commit
    ↓
Credential scan — blocks AKIA*, github_pat_*, private keys
    ↓
Static analysis of changed Python files
    ↓
/simplify applied to functions >50 lines automatically
    ↓
BLOCK on critical issues | WARN + 5s delay | Pass
    ↓
Quality metrics saved to .claude/review_history/
```

### Security
- `.env` is in `.gitignore` and must never be committed
- Pre-commit hook scans for and blocks: `AKIA*`, `github_pat_*`, private key headers
- AWS credentials have been rotated; treat any leaked key as compromised immediately

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

# Bronze — all data types
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type player_weekly
python scripts/bronze_ingestion_simple.py --season 2024 --data-type player_seasonal
# data-types: schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal

# Silver
python scripts/silver_player_transformation.py --season 2024

# Gold — projections
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr
python scripts/generate_projections.py --week 10 --season 2025 --scoring ppr

# Draft
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5 --simulate
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5 --auction --budget 200
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5 --rostered-file data/rostered.csv

# Pipeline health
python scripts/check_pipeline_health.py

# Testing and validation
python -m pytest tests/ -v
python scripts/validate_project.py

# Code quality
python -m black src/ tests/ scripts/
python -m flake8 src/ tests/ scripts/
```
