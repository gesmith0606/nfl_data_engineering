# NFL Data Engineering Pipeline

A production-grade NFL analytics pipeline implementing the Medallion Architecture — Bronze ingestion through Gold projections — with a full fantasy football draft tool and game prediction feature generation.

---

## Architecture

```
nfl-data-py + Sleeper API
        |
Bronze  (data/bronze/ + s3://nfl-raw/)
        raw game, player, snap, injury, roster, PBP, NGS, PFR, QBR,
        depth charts, draft picks, combine — 25+ data types, 93 MB local
        |
Silver  (data/silver/ + s3://nfl-refined/)
        player usage metrics, rolling averages, opponent rankings
        team EPA/CPOE/success rate, strength of schedule, situational splits
        advanced player profiles (NGS separation, PFR pressure/blitz, QBR)
        |
Gold    (data/gold/ + s3://nfl-trusted/)
        weekly + preseason projections (PPR / Half-PPR / Standard)
        floor/ceiling ranges, injury adjustments, Vegas multipliers
        |
Draft Tool
        ADP comparison, VORP, snake/auction/mock drafts, waiver wire
```

Storage uses a local-first approach. S3 is optional — all scripts work without AWS credentials. When S3 is enabled, the key pattern is `dataset/season=YYYY/week=WW/filename_YYYYMMDD_HHMMSS.parquet`.

---

## Current Capabilities

### Bronze Layer (93 MB, 25+ data types, 2000-2025)

Ingested via `scripts/bronze_ingestion_simple.py`:

| Data Type | Seasons | Notes |
|-----------|---------|-------|
| schedules | 1999-2025 | Game dates, scores, teams |
| pbp | 2010-2025 | 103 curated columns including EPA, WPA, CPOE, air yards |
| player_weekly | 2020-2025 | Per-player per-week stats |
| player_seasonal | 2020-2025 | Season-aggregate stats |
| snap_counts | 2020-2025 | Offense/defense snap percentages |
| injuries | 2020-2025 | Practice/game injury reports |
| rosters | 2020-2025 | Active roster with positions and depth |
| teams | 2020-2025 | Team metadata |
| ngs_passing / ngs_rushing / ngs_receiving | 2016-2025 | Next Gen Stats |
| pfr_pass / pfr_rush / pfr_rec / pfr_def | 2018-2025 | Pro Football Reference weekly |
| pfr_seasonal_* | 2018-2025 | Pro Football Reference seasonal aggregates |
| qbr_weekly / qbr_seasonal | 2006-2025 | ESPN QBR |
| depth_charts | 2020-2025 | Team depth charts |
| draft_picks | 2000-2025 | Historical draft data |
| combine | 2000-2025 | NFL Combine measurables |

### Silver Layer (16 MB, analytics-ready features)

**Fantasy analytics** (`scripts/silver_player_transformation.py`, `src/player_analytics.py`):
- Target share, carry share, snap percentage, air yards share, red zone opportunities
- Opponent position rankings (1-32) for points allowed per position
- 3-game and 6-game rolling averages with recency weighting (45%/30%/25%)

**Team PBP metrics** (`scripts/silver_team_transformation.py`, `src/team_analytics.py`):
- EPA per play (offense/defense), success rate, CPOE, red zone efficiency
- Pace, pass rate over expected (PROE), 4th-down aggressiveness, early-down run rate
- 3-game and 6-game rolling windows, grouped by (team, season) to prevent cross-season contamination
- Strength of schedule (opponent-adjusted EPA rankings, lagged to avoid circular dependency)
- Situational splits: home/away, divisional, game script (leading/trailing by 7+)

**Advanced player profiles** (`scripts/silver_advanced_transformation.py`, `src/player_advanced_analytics.py`):
- NGS separation metrics, RYOE, time to throw
- PFR pressure rate, blitz rate, sack rate
- QBR rolling windows per player-week

### Gold Layer — Fantasy Projections

Projection model: `roll3(50%) + roll6(30%) + STD(20%) * usage_mult * matchup * vegas`

- Usage multiplier: 0.80-1.15 based on target/carry share
- Matchup multiplier: 0.85-1.15 based on opponent position ranking
- Vegas multiplier: implied team total / 23.0; RB run-heavy bonus when total < 20 and spread < -7
- Injury adjustments: Active 1.0, Questionable 0.85, Doubtful 0.50, Out/IR/PUP 0.0
- Bye week handling: zeroes all stats, sets `is_bye_week=True`
- Rookie fallback: starter/backup/unknown baselines at 100%/40%/25% of positional average
- Floor/ceiling: position-specific variance bands (QB: 45%, RB: 40%, WR: 38%, TE: 35%)

**Backtesting results (2022-2024, Weeks 3-18, Half-PPR, 11,183 player-weeks):**

| Metric | Overall | QB | RB | WR | TE |
|--------|---------|----|----|----|----|
| MAE | 4.91 | 6.58 | 5.06 | 4.85 | 3.77 |
| Bias | -0.60 | -2.20 | -0.37 | -0.28 | -0.63 |
| Correlation | 0.51 | — | — | — | — |

### Draft Tool

Interactive CLI (`scripts/draft_assistant.py`) supporting:
- Snake draft with VORP-based recommendations and positional scarcity awareness
- Auction draft with budget-optimized player valuation (`--auction --budget 200`)
- Mock simulation against AI opponents (`--simulate`)
- Waiver wire with position-filtered rankings (`waiver [pos]` in CLI)
- ADP refresh from Sleeper API (`scripts/refresh_adp.py`)

### Pipeline Monitoring

- GitHub Actions workflow runs Tuesdays 9am UTC, auto-detects current NFL week
- On failure: auto-opens GitHub issue with error details
- Health check: `scripts/check_pipeline_health.py` reports S3 freshness and file size across all three layers

---

## Quick Start

**Prerequisites:** Python 3.9+, Git

```bash
git clone https://github.com/gesmith0606/nfl_data_engineering.git
cd nfl_data_engineering
source venv/bin/activate
```

### Bronze ingestion

```bash
# Single week
python scripts/bronze_ingestion_simple.py --season 2024 --week 10 --data-type player_weekly

# Seasonal (no week argument)
python scripts/bronze_ingestion_simple.py --season 2024 --data-type player_seasonal

# Available data types:
# schedules, pbp, teams, player_weekly, snap_counts, injuries, rosters, player_seasonal
```

### Silver transformation

```bash
# Player fantasy analytics (usage, rolling averages, opponent rankings)
python scripts/silver_player_transformation.py --seasons 2020 2021 2022 2023 2024

# Team PBP metrics, SOS, situational splits
python scripts/silver_team_transformation.py --seasons 2024

# Advanced player profiles (NGS, PFR, QBR)
python scripts/silver_advanced_transformation.py --seasons 2024
```

### Gold projections

```bash
# Preseason (full season projections for draft prep)
python scripts/generate_projections.py --preseason --season 2026 --scoring half_ppr

# Weekly
python scripts/generate_projections.py --week 1 --season 2026 --scoring ppr
# Scoring options: ppr, half_ppr, standard
```

### Draft tool

```bash
# Snake draft — 12 teams, picking 5th
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5

# Auction draft
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --auction --budget 200

# Mock simulation
python scripts/draft_assistant.py --scoring half_ppr --teams 12 --my-pick 5 --simulate

# Refresh ADP from Sleeper
python scripts/refresh_adp.py --season 2026
```

### Backtesting

```bash
python scripts/backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr
```

### Pipeline health

```bash
python scripts/check_pipeline_health.py --season 2024 --week 10
```

### AWS (optional)

Without credentials, all scripts read and write to `data/` locally. To enable S3:

```bash
cp .env.example .env
# Add AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION=us-east-2
```

S3 buckets: `nfl-raw` (Bronze), `nfl-refined` (Silver), `nfl-trusted` (Gold).

---

## Project Structure

```
nfl_data_engineering/
├── src/
│   ├── config.py                      # S3 paths, SCORING_CONFIGS, ROSTER_CONFIGS, season ranges
│   ├── nfl_data_integration.py        # NFLDataFetcher — 8 fetch methods + validate_data()
│   ├── nfl_data_adapter.py            # Isolates all nfl.import_* calls; single migration point
│   ├── player_analytics.py            # Usage metrics, opponent rankings, rolling averages, Vegas totals
│   ├── player_advanced_analytics.py   # NGS separation/RYOE, PFR pressure/blitz, QBR rolling windows
│   ├── team_analytics.py              # Team EPA, CPOE, success rate, SOS, situational splits
│   ├── scoring_calculator.py          # Fantasy points — single dict + vectorized DataFrame
│   ├── projection_engine.py           # Weekly/preseason projections with bye, rookie, Vegas logic
│   ├── draft_optimizer.py             # DraftBoard, AuctionDraftBoard, MockDraftSimulator, DraftAdvisor
│   └── utils.py                       # get_latest_s3_key, download_latest_parquet, shared utils
│
├── scripts/
│   ├── bronze_ingestion_simple.py     # Bronze CLI — all 25+ data types
│   ├── silver_player_transformation.py # Fantasy analytics Silver CLI
│   ├── silver_team_transformation.py  # Team metrics Silver CLI
│   ├── silver_advanced_transformation.py # Advanced player profiles Silver CLI
│   ├── generate_projections.py        # Gold CLI — --week or --preseason
│   ├── draft_assistant.py             # Interactive draft CLI — snake/auction/mock/waiver
│   ├── backtest_projections.py        # Projected vs actual; MAE/RMSE/bias per position
│   ├── refresh_adp.py                 # Sleeper API ADP → data/adp_latest.csv
│   ├── check_pipeline_health.py       # S3 freshness + size checks across all layers
│   ├── generate_inventory.py          # Scans local data/, outputs markdown inventory
│   └── validate_project.py            # Environment and dependency validation
│
├── tests/
│   ├── test_scoring_calculator.py     # 14 tests — PPR/Half/Standard, DataFrame, edge cases
│   ├── test_projection_engine.py      # 19 tests — bye, rookie, Vegas, usage, injury
│   ├── test_player_analytics.py       # 7 tests — usage metrics, rolling averages, implied totals
│   ├── test_draft_optimizer.py        # 13 tests — board, advisor, waiver, value scores
│   ├── test_team_analytics.py         # Team metrics tests
│   ├── test_player_advanced_analytics.py # Advanced profile tests
│   ├── test_advanced_ingestion.py     # Bronze ingestion for advanced data types
│   └── test_utils.py                  # 5 tests — S3 paths, validation
│
├── data/                              # Local data store (gitignored)
│   ├── bronze/                        # 93 MB across 25+ data types
│   ├── silver/                        # 16 MB analytics-ready features
│   └── gold/                          # Projection outputs
│
├── docs/
│   ├── ARCHITECTURE.md                          # System design (medallion, 3 tracks, design patterns)
│   ├── NFL_DATA_DICTIONARY.md                   # Column specs for all data types
│   ├── NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md   # Phase history and upcoming work
│   ├── NFL_GAME_PREDICTION_DATA_MODEL.md        # Data model with implementation status
│   └── AWS_IAM_SETUP_INSTRUCTIONS.md            # AWS IAM and S3 setup
│
├── .github/workflows/weekly-pipeline.yml       # Tuesday cron; auto-opens issue on failure
├── .planning/                                  # Phase planning docs and roadmap
├── .env.example                                # Credentials template
└── requirements.txt                            # Python dependencies
```

---

## Configuration

`src/config.py` is the authoritative configuration source. Key settings:

| Setting | Value |
|---------|-------|
| AWS region | us-east-2 |
| Bronze bucket | nfl-raw |
| Silver bucket | nfl-refined |
| Gold bucket | nfl-trusted |
| Valid seasons | 1999-2026 |
| Player training data | 2020-2025 (`PLAYER_DATA_SEASONS`) |
| Scoring formats | PPR (1.0/rec), Half-PPR (0.5/rec), Standard (0.0/rec) |
| Roster formats | standard, superflex, 2qb |

All scripts accept `--no-s3` to disable S3 uploads and operate locally only. Scripts auto-detect invalid AWS credentials and fall back to local reads.

---

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

274 tests pass across scoring, projections, player analytics, team analytics, advanced profiles, draft optimization, ingestion, and utilities.

Code quality:

```bash
python -m black src/ tests/ scripts/
python -m flake8 src/ tests/ scripts/
```

---

## Roadmap

### v1.2 Silver Expansion (in progress)

| Phase | Status | Description |
|-------|--------|-------------|
| 15 — PBP Team Metrics | Complete | Team EPA, CPOE, success rate, red zone, pace, PROE, 4th down with rolling windows |
| 16 — SOS and Situational Splits | Complete | Opponent-adjusted EPA rankings, home/away, divisional, game script splits |
| 17 — Advanced Player Profiles | Complete | NGS separation/RYOE/TTT, PFR pressure/blitz/sack, QBR rolling windows |
| 18 — Historical Context | Next | Combine measurables + draft capital linked to player IDs; composite scores (speed score, burst score, BMI); static dimension table for rookie/breakout modeling |

### Planned (post-v1.2)

- **ML pipeline**: Random Forest / XGBoost game outcome model trained on Silver team features; target 65%+ win accuracy, < 3.5 point spread MAE
- **Neo4j integration**: WR-CB matchup graphs, QB-WR target share networks, injury cascade modeling
- **Live Sleeper integration**: Real-time league data, trade analysis, and waiver suggestions
- **Keeper/dynasty support**: Multi-year roster tracking and dynasty-specific VORP

---

## NFL Business Rules

- Valid seasons: 1999-2026 | Regular season weeks: 1-18 (playoff weeks excluded from team metrics)
- 32 teams | Down: 1-4 | Distance: 1-99 yards | Yard line: 0-100
- Projected fantasy points are always >= 0 for skill positions (QB, RB, WR, TE)
- Always read Silver/Gold via `download_latest_parquet()` from `src/utils.py` — never scan a full S3 prefix

---

## Contributing

1. Fork the repository and create a feature branch
2. Run the test suite before submitting: `python -m pytest tests/ -v`
3. Follow the existing conventions: type hints, Google-style docstrings, DataFrame-first processing
4. Open a pull request with a description of what changed and why

## License

MIT License — see the LICENSE file for details.
