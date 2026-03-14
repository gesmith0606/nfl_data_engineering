# Architecture Research

**Domain:** Silver layer expansion — PBP analytics, rolling windows, advanced metrics, SOS, historical context
**Researched:** 2026-03-13
**Confidence:** HIGH (based on direct inspection of all Bronze files, Silver schemas, and existing src/ modules)

## Standard Architecture

### System Overview

```
Bronze Layer (data/bronze/)
├── pbp/season=YYYY/               ← 103-col play-by-play (EPA, WPA, CPOE, situation)
├── ngs/{passing,receiving,rushing}/season=YYYY/   ← separation, RYOE, CPOE
├── pfr/weekly/{pass,rush,rec,def}/season=YYYY/    ← pressure, blitz, adot
├── pfr/seasonal/{pass,rush,rec,def}/season=YYYY/  ← season aggregates
├── qbr/season=YYYY/               ← ESPN QBR weekly + seasonal
├── combine/season=YYYY/           ← measurables: forty, wt, ht, vertical...
├── draft_picks/season=YYYY/       ← round, pick, w_av, car_av, gsis_id
├── schedules/ or games/season=YYYY/ ← home/away, scores, spread, total
└── players/{weekly,seasonal,...}/ ← existing 6 original types
        |
        v (Silver CLI reads Bronze; new modules join on game_id, season, team, player_id)
        |
Silver Layer (data/silver/) — NEW layout for v1.2
├── teams/
│   ├── pbp_metrics/season=YYYY/   ← EPA/play, success rate, CPOE, red zone efficiency
│   ├── tendencies/season=YYYY/    ← pace, pass rate OE, 4th-down aggressiveness
│   └── sos/season=YYYY/           ← opponent-adjusted EPA, schedule difficulty rankings
├── players/
│   ├── usage/season=YYYY/         ← EXISTING: usage metrics + rolling avgs (113 cols)
│   ├── advanced/season=YYYY/      ← NEW: NGS + PFR + QBR profiles with rolling windows
│   └── historical/season=YYYY/    ← NEW: combine measurables + draft capital linked by gsis_id
├── defense/
│   ├── positional/season=YYYY/    ← EXISTING: avg_pts_allowed, rank (6 cols)
│   └── coverage/season=YYYY/      ← NEW: PFR def coverage stats + EPA allowed per position
└── situational/
    └── splits/season=YYYY/        ← NEW: game_script / home_away / divisional breakdowns
        |
        v (Gold reads Silver; new metrics feed projection multipliers and prediction features)
        |
Gold Layer (data/gold/)  ← unchanged in v1.2 (projection_engine.py reads Silver usage)
```

### Component Responsibilities

| Component | Responsibility | Input | Output |
|-----------|---------------|-------|--------|
| `src/player_analytics.py` | EXISTING — usage, rolling avgs, opponent rankings, game script, venue | player_weekly + snap_counts + schedules | `players/usage/` enriched DF |
| `src/team_analytics.py` | NEW — PBP-derived team metrics + tendencies + SOS | PBP Bronze + schedules | `teams/pbp_metrics/`, `teams/tendencies/`, `teams/sos/` |
| `src/advanced_player_analytics.py` | NEW — NGS/PFR/QBR profiles + rolling windows | NGS + PFR + QBR Bronze | `players/advanced/` enriched DF |
| `src/historical_context.py` | NEW — combine + draft capital linked to active players | combine + draft_picks Bronze | `players/historical/` DF |
| `src/situational_analytics.py` | NEW — game script / home_away / divisional splits | player_weekly + schedules | `situational/splits/` DF |
| `scripts/silver_player_transformation.py` | EXISTING CLI — orchestrates player-level transforms | calls player_analytics functions | writes `players/usage/` |
| `scripts/silver_team_transformation.py` | NEW CLI — orchestrates team-level transforms | calls team_analytics functions | writes `teams/` and `defense/coverage/` |
| `scripts/silver_advanced_transformation.py` | NEW CLI — orchestrates advanced player + historical transforms | calls advanced_player_analytics + historical_context | writes `players/advanced/` + `players/historical/` |

## Recommended Project Structure

```
src/
├── player_analytics.py          # EXISTING — add no new functions here for v1.2
├── team_analytics.py            # NEW — compute_pbp_team_metrics(), compute_team_tendencies(), compute_sos()
├── advanced_player_analytics.py # NEW — compute_ngs_profiles(), compute_pfr_profiles(), compute_qbr_features()
├── historical_context.py        # NEW — compute_draft_capital(), link_combine_to_roster()
├── situational_analytics.py     # NEW — compute_situational_splits()
├── config.py                    # MODIFY — add SILVER_TEAM_S3_KEYS, SILVER_ADVANCED_S3_KEYS
├── projection_engine.py         # MODIFY — add new multiplier hooks (team tendencies, SOS)
└── ...                          # unchanged

scripts/
├── silver_player_transformation.py   # EXISTING — no structural change needed
├── silver_team_transformation.py     # NEW CLI for team metrics + SOS + situational
├── silver_advanced_transformation.py # NEW CLI for NGS/PFR/QBR profiles + historical

data/silver/
├── players/
│   ├── usage/season=YYYY/            # EXISTING output (unchanged)
│   ├── advanced/season=YYYY/         # NEW
│   └── historical/                   # NEW (no season partition — combine/draft are static-ish)
├── teams/
│   ├── pbp_metrics/season=YYYY/      # NEW
│   ├── tendencies/season=YYYY/       # NEW
│   └── sos/season=YYYY/             # NEW
├── defense/
│   ├── positional/season=YYYY/       # EXISTING
│   └── coverage/season=YYYY/         # NEW
└── situational/
    └── splits/season=YYYY/           # NEW
```

### Structure Rationale

- **`src/team_analytics.py` (separate module):** PBP aggregation is team-level, not player-level. Mixing it into `player_analytics.py` would bloat that module (currently 418 lines) and create confusing coupling. Team metrics and SOS have different grain (team-week vs player-week) — they write to separate Silver paths and are consumed differently by `projection_engine.py`.
- **`src/advanced_player_analytics.py` (separate module):** NGS, PFR, QBR use different join keys (`player_gsis_id`, `pfr_player_id`, `player_id`) and require their own rolling window logic on different column sets. Keeping separate from `player_analytics.py` preserves the existing Silver `players/usage/` schema with zero risk of column collision.
- **`src/historical_context.py` (separate module):** Combine + draft capital are not weekly data — they are career-time attributes. The join logic (gsis_id → player roster → combine/draft) is distinct. Keeping separate ensures it can be built and tested independently.
- **`scripts/silver_team_transformation.py` (new CLI):** The existing `silver_player_transformation.py` is player-scoped. Adding team-level PBP transforms into it would require loading large PBP files for a script currently used for quick player-only refreshes. A separate CLI allows independent execution.
- **`data/silver/players/historical/` (no season partition):** Combine and draft capital are year-of-entry attributes, not season-varying. They are referenced as static context for projections and should be stored without a season partition to simplify reads.

## Architectural Patterns

### Pattern 1: PBP Aggregation — Play-Filter then Group-By Team

**What:** PBP data (103 cols, ~50K plays/season) is too large to load fully for every Silver run. The correct pattern filters to the relevant play types first, then aggregates to team-week grain.

**When to use:** Every function in `team_analytics.py` that touches PBP.

**Trade-offs:** Slightly more verbose than loading and groupby-ing full PBP, but reduces peak memory ~70% per season by dropping non-relevant plays early.

**Example:**
```python
def compute_pbp_team_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute EPA/play, success rate, CPOE, red zone efficiency per team per week."""
    # Filter to scrimmage plays only (exclude penalties, kickoffs, etc.)
    plays = pbp_df[pbp_df['play_type'].isin(['pass', 'run'])].copy()

    dropbacks = plays[plays['qb_dropback'] == 1]
    rushes = plays[plays['rush_attempt'] == 1]
    rz = plays[plays['yardline_100'] <= 20]

    team_epa = (
        plays.groupby(['season', 'week', 'posteam'])
        .agg(
            epa_per_play=('epa', 'mean'),
            success_rate=('success', 'mean'),
            plays=('play_id', 'count'),
        )
        .reset_index()
        .rename(columns={'posteam': 'team'})
    )
    cpoe = (
        dropbacks.groupby(['season', 'week', 'posteam'])
        .agg(cpoe=('cpoe', 'mean'))
        .reset_index()
        .rename(columns={'posteam': 'team'})
    )
    rz_eff = (
        rz.groupby(['season', 'week', 'posteam'])
        .agg(
            rz_epa=('epa', 'mean'),
            rz_td_rate=('touchdown', 'mean'),
        )
        .reset_index()
        .rename(columns={'posteam': 'team'})
    )
    return team_epa.merge(cpoe, on=['season', 'week', 'team'], how='left') \
                   .merge(rz_eff, on=['season', 'week', 'team'], how='left')
```

### Pattern 2: Rolling Windows on Team/Player Data — Shift-then-Roll

**What:** All rolling averages must shift(1) before rolling to avoid data leakage (current week's value must not appear in the current week's rolling average).

**When to use:** Every rolling average computation in every new module.

**Trade-offs:** The `shift(1)` pattern is already established in `player_analytics.compute_rolling_averages`. New modules must follow the same pattern for consistency with how `projection_engine.py` consumes Silver data.

**Example:**
```python
def _add_rolling_to_team_df(df: pd.DataFrame, cols: list, windows: list = [3, 6]) -> pd.DataFrame:
    df = df.sort_values(['team', 'season', 'week'])
    for window in windows:
        for col in cols:
            if col in df.columns:
                df[f"{col}_roll{window}"] = (
                    df.groupby('team')[col]
                    .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
                )
    return df
```

### Pattern 3: Cross-Source Player Join — Use gsis_id as Canonical Key

**What:** NGS uses `player_gsis_id`, PFR uses `pfr_player_id`, QBR uses `player_id`. The canonical join key in Silver is `player_id` (gsis_id) as used in `players/usage/`. Join NGS directly. PFR and QBR require a cross-reference via `players/rosters/` or `draft_picks` (which has both `gsis_id` and `pfr_player_id`).

**When to use:** Any function in `advanced_player_analytics.py` that merges NGS/PFR/QBR into player-week grain.

**Trade-offs:** PFR and QBR will have non-matches for some players (name-only PFR records, unqualified QBR entries). Use left-joins from the player_weekly base and fill NaN for missing advanced stats. Never inner-join — this would silently drop players.

**Join chain:**
```
player_weekly (gsis_id) ← left join → NGS (player_gsis_id)
player_weekly (player_id) ← left join → QBR (player_id, via gsis_id match)
player_weekly ← left join → draft_picks (gsis_id) → PFR weekly (pfr_player_id)
```

### Pattern 4: SOS Computation — Rolling Opponent Quality

**What:** Strength-of-schedule at week W is the average opponent EPA-per-play from weeks 1..W-1 (using already-played games, not future schedule). This requires the team PBP metrics computed in Pattern 1 to exist first — SOS depends on team metrics.

**When to use:** `compute_sos()` in `team_analytics.py`.

**Trade-offs:** SOS is a derived metric that requires team EPA metrics as input. Build order within `silver_team_transformation.py` must compute `pbp_team_metrics` before `sos`. Both can be written to Silver in the same CLI run.

**Example:**
```python
def compute_sos(team_metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Rolling opponent-quality SOS. team_metrics_df must have epa_per_play."""
    # team_metrics_df grain: season, week, team, epa_per_play
    # Build opponent lookup from schedules (passed in separately)
    ...
    # For each team at each week, look back at opponents' epa_per_play through that week
    # and compute rolling mean (windows 3, 6, season-to-date)
```

### Pattern 5: Historical Context — Static Join to Active Roster

**What:** Combine measurables (forty, wt, ht, vertical, etc.) and draft capital (round, pick, w_av) are career attributes. They are linked to active players via `gsis_id`, which is present in both `draft_picks` (column: `gsis_id`) and `combine` (requires cross-reference via `pfr_id`, then to roster).

**When to use:** `compute_draft_capital()` and `link_combine_to_roster()` in `historical_context.py`.

**Trade-offs:** Not all players have combine data (undrafted free agents, international players, historical gaps). Not all draft picks have `gsis_id` (older picks pre-2009). Build with left-joins from active roster; treat historical context as enrichment, not required fields.

**Join chain:**
```
rosters (player_id=gsis_id, pfr_id) ← left join → draft_picks (gsis_id)
rosters (pfr_id) ← left join → combine (pfr_id)
```

## Data Flow

### Silver Expansion Data Flow

```
Bronze PBP (pbp/season=YYYY/)
    |
    v
silver_team_transformation.py
    |
    +-- team_analytics.compute_pbp_team_metrics()  --> silver/teams/pbp_metrics/season=YYYY/
    |
    +-- team_analytics.compute_team_tendencies()   --> silver/teams/tendencies/season=YYYY/
    |         (requires pbp_team_metrics as input)
    |
    +-- team_analytics.compute_sos()               --> silver/teams/sos/season=YYYY/
              (requires pbp_team_metrics as input)

Bronze NGS + PFR + QBR
    |
    v
silver_advanced_transformation.py
    |
    +-- advanced_player_analytics.compute_ngs_profiles()    --> silver/players/advanced/season=YYYY/
    +-- advanced_player_analytics.compute_pfr_profiles()    (merged into same advanced file)
    +-- advanced_player_analytics.compute_qbr_features()    (merged into same advanced file)

Bronze combine + draft_picks + rosters
    |
    v
silver_advanced_transformation.py (or standalone)
    |
    +-- historical_context.link_combine_to_roster()         --> silver/players/historical/
    +-- historical_context.compute_draft_capital()          (merged into same historical file)

Bronze player_weekly + schedules (already in Silver pipeline)
    |
    v
silver_player_transformation.py (EXISTING — no change)
    |
    +-- player_analytics.compute_usage_metrics()            --> silver/players/usage/season=YYYY/
    +-- player_analytics.compute_rolling_averages()
    +-- player_analytics.compute_game_script_indicators()
    +-- player_analytics.compute_venue_splits()
    +-- player_analytics.compute_opponent_rankings()         --> silver/defense/positional/season=YYYY/
```

### Gold Consumption of New Silver Data

```
silver/players/usage/         ← EXISTING feed into projection_engine.py (unchanged)
silver/teams/pbp_metrics/     ← NEW feed: team EPA/play used as Vegas-equivalent multiplier
silver/teams/sos/             ← NEW feed: schedule difficulty factor (replaces simple rank-based matchup)
silver/players/advanced/      ← NEW feed: NGS separation / RYOE / pressure rate for QB/RB/WR/TE adjustments
silver/players/historical/    ← NEW feed: draft capital / combine athleticism for rookie projection baseline
```

### Key Data Flows

1. **PBP to team EPA:** Bronze PBP (50K plays) → filter scrimmage plays → groupby team+week → ~32 teams × ~18 weeks = 576 rows per season. Fast, low-memory after initial filter.
2. **NGS to player profiles:** Bronze NGS (passing 614 rows, receiving 1435 rows, rushing 601 rows per season) → join on player_gsis_id → 2-3K rows per season. Trivially fast.
3. **PFR to player profiles:** Bronze PFR weekly/def (7992 rows per season) → join on pfr_player_id via draft_picks cross-reference → left-join into player_weekly base. ~5K matched rows per season.
4. **Combine/draft to historical:** Bronze combine (321 rows/year) + draft_picks (257 rows/year) → join on gsis_id/pfr_id → one static file (multi-season, all-time). Updated once per draft year.

## Integration Points with Existing Silver Pipeline

### player_analytics.py — No Modifications Required

The existing module provides: `compute_usage_metrics`, `compute_rolling_averages`, `compute_game_script_indicators`, `compute_venue_splits`, `compute_implied_team_totals`, and `compute_opponent_rankings`. These already write the 113-column `players/usage/` Silver table.

**v1.2 does NOT modify this file.** New metrics live in new modules and new Silver paths. This preserves:
- The 71+ existing test suite (none need changing)
- The exact `players/usage/` schema that `projection_engine.py` reads
- The `silver_player_transformation.py` CLI contract

### projection_engine.py — Optional Extension Points

The projection engine currently reads `players/usage/` Silver. After v1.2 ships, two hooks are available for future Gold enhancement:

| Hook | Where | New Silver Data |
|------|-------|-----------------|
| `RECENCY_WEIGHTS` blending | `projection_engine.py` line ~30 | Replace simple opponent rank with SOS-adjusted EPA from `teams/sos/` |
| `usage_multiplier` computation | `projection_engine.py` line ~140 | Supplement target_share/carry_share with NGS separation (WR) / RYOE (RB) from `players/advanced/` |

These are v1.2 stretch goals, not blockers — the new Silver tables are the prerequisite.

### config.py — Additions Required

Add Silver S3 key templates for new paths:

```python
SILVER_TEAM_S3_KEYS = {
    "pbp_metrics": "teams/pbp_metrics/season={season}/pbp_metrics_{ts}.parquet",
    "tendencies": "teams/tendencies/season={season}/tendencies_{ts}.parquet",
    "sos": "teams/sos/season={season}/sos_{ts}.parquet",
}
SILVER_ADVANCED_S3_KEYS = {
    "advanced_players": "players/advanced/season={season}/advanced_{ts}.parquet",
    "historical": "players/historical/historical_{ts}.parquet",
    "situational": "situational/splits/season={season}/splits_{ts}.parquet",
    "coverage": "defense/coverage/season={season}/coverage_{ts}.parquet",
}
```

## Build Order (Dependency-Driven)

This ordering respects data dependencies and isolates risk — each step can be tested independently before proceeding.

| Step | Module/Script | Reads From | Writes To | Why This Order |
|------|--------------|-----------|----------|----------------|
| 1 | `src/team_analytics.py` | (new module) | — | No deps; write + test in isolation |
| 2 | `scripts/silver_team_transformation.py` | Bronze PBP + schedules | `teams/pbp_metrics/`, `teams/tendencies/` | PBP metrics first; SOS depends on them |
| 3 | SOS in `team_analytics.py` | Output of step 2 | `teams/sos/` | Must have PBP metrics to compute opponent quality |
| 4 | `src/advanced_player_analytics.py` | (new module) | — | No deps; write + test in isolation |
| 5 | `scripts/silver_advanced_transformation.py` (NGS + PFR + QBR) | Bronze NGS/PFR/QBR + player_weekly | `players/advanced/` | Need player_id cross-reference from existing usage table |
| 6 | `src/historical_context.py` | (new module) | — | No deps; combine/draft logic is self-contained |
| 7 | historical in `silver_advanced_transformation.py` | Bronze combine + draft_picks + rosters | `players/historical/` | Rosters needed for gsis_id link; rosters Bronze must exist |
| 8 | `src/situational_analytics.py` | (new module) | — | No deps; pure computation from existing player_weekly |
| 9 | situational in `silver_team_transformation.py` | Silver `players/usage/` | `situational/splits/` | Reads enriched Silver (with game_script already computed) |

**Summary:** Team metrics → SOS → Advanced player profiles → Historical context → Situational splits.

## Anti-Patterns

### Anti-Pattern 1: Adding New Metrics to `player_analytics.py`

**What people do:** Append `compute_pbp_team_metrics()` or `compute_ngs_profiles()` to the existing `player_analytics.py` because it already handles Silver transforms.

**Why it's wrong:** `player_analytics.py` operates at player-week grain from player_weekly Bronze. PBP aggregation operates at team-week grain from PBP Bronze. NGS/PFR profiles require different Bronze sources with different join keys. Mixing them creates a 1000+ line god module with confusing imports and makes independent testing impossible.

**Do this instead:** One module per analytic domain. `team_analytics.py`, `advanced_player_analytics.py`, `historical_context.py`, `situational_analytics.py`. Each tested independently.

### Anti-Pattern 2: Loading Full PBP for Each Team Metric

**What people do:** `pbp_df = pd.read_parquet('data/bronze/pbp/season=2024/pbp.parquet')` then immediately groupby team — fine for one season, but if looped over 10 seasons it loads 1+ GB sequentially.

**Why it's wrong:** At 2016-2025 (10 seasons), full PBP loads sum to ~1 GB peak if not managed. Silver transforms run per-season in a loop, so this is not catastrophic, but the filter-first pattern cuts memory ~70% per iteration.

**Do this instead:** Filter to relevant `play_type` rows immediately after reading. Process one season at a time in the CLI loop (existing pattern from `silver_player_transformation.py`).

### Anti-Pattern 3: Inner-Joining NGS/PFR to Player Weekly

**What people do:** Use `how='inner'` when merging NGS or PFR data into the player-weekly base table to keep only matched rows.

**Why it's wrong:** NGS has minimum ~614 passing records per season — only qualified QBs. PFR coverage is better but still misses UDFAs and obscure backups. An inner-join silently drops all players without advanced stats, breaking downstream projections for those players.

**Do this instead:** Always left-join from player_weekly as the base. NaN values in advanced metric columns are expected and handled by `projection_engine.py` via fillna defaults.

### Anti-Pattern 4: Storing Advanced + Usage in the Same Parquet File

**What people do:** Extend the existing 113-column `players/usage/` Silver table with new NGS/PFR columns by modifying `silver_player_transformation.py`.

**Why it's wrong:** The `players/usage/` schema is a stable contract consumed by `projection_engine.py` and 71 tests. Adding 30+ new columns risks column name collisions (NGS has `aggressiveness`, PFR has `times_pressured` which conflicts with player_weekly context), increases file size ~30%, and forces Silver CLI re-runs whenever any new source changes.

**Do this instead:** Write separate Silver tables: `players/advanced/` for NGS/PFR/QBR, `players/historical/` for combine/draft. Gold and the projection engine read from multiple Silver tables with explicit left-joins.

### Anti-Pattern 5: Season Partition for Historical Context

**What people do:** Store combine and draft capital as `players/historical/season=2024/historical_2024.parquet`.

**Why it's wrong:** A player's combine measurables and draft round do not change year to year. Season-partitioning creates 25 identical or near-identical copies and forces callers to decide which season to read.

**Do this instead:** Store as `players/historical/historical_{ts}.parquet` (no season partition). Use `download_latest_parquet()` to always read the latest. Append new draft classes when they join the league.

## Scaling Considerations

| Concern | Current (Silver: 6 files, ~4 MB) | Post v1.2 Silver (~30 files, ~20-30 MB) | Notes |
|---------|----------------------------------|----------------------------------------|-------|
| Disk space | Trivial | Trivial | Team metrics are tiny (576 rows/season); even 10 seasons = <1 MB per metric type |
| Memory during transform | ~150 MB peak (player_weekly join) | ~250 MB peak (PBP filter + team groupby) | PBP filter-first keeps peak manageable |
| Read performance | Instant | Instant | download_latest_parquet reads one file; team metrics are tiny |
| CLI runtime | ~30s per season | ~90s per season (adds PBP processing) | PBP is 50K rows; groupby is fast |
| Gold compatibility | No change | projection_engine.py needs left-join hooks | Additive — existing paths unchanged |

## Sources

- `src/player_analytics.py` — existing Silver module, current function signatures and column outputs
- `scripts/silver_player_transformation.py` — existing Silver CLI, storage path patterns
- `src/config.py` — PBP_COLUMNS (103 cols), SILVER_PLAYER_S3_KEYS, DATA_TYPE_SEASON_RANGES
- `src/projection_engine.py` — RECENCY_WEIGHTS, USAGE_STABILITY_STAT, usage multiplier patterns
- `data/silver/players/usage/season=2024/*.parquet` — confirmed 113-column schema
- `data/bronze/pbp/season=2024/*.parquet` — confirmed 103 cols, 49,492 plays, EPA/WPA/CPOE present
- `data/bronze/ngs/*/season=2024/*.parquet` — confirmed column sets for passing (29 cols), receiving (23 cols), rushing (22 cols)
- `data/bronze/pfr/weekly/def/season=2024/*.parquet` — confirmed 29 cols (pressure, blitz, coverage)
- `data/bronze/pfr/weekly/pass/season=2024/*.parquet` — confirmed 24 cols (bad throws, pressure)
- `data/bronze/pfr/seasonal/*/season=2024/*.parquet` — confirmed schemas for pass/rec/rush/def
- `data/bronze/qbr/season=2024/*.parquet` — confirmed 30 cols including qbr_total, epa_total, pts_added
- `data/bronze/combine/season=2024/*.parquet` — confirmed 18 cols (forty, wt, ht, vertical, pfr_id)
- `data/bronze/draft_picks/season=2024/*.parquet` — confirmed 36 cols including gsis_id, pfr_player_id, round, pick, w_av
- `.planning/PROJECT.md` — v1.2 milestone definition, existing decisions

---
*Architecture research for: NFL Silver layer expansion (v1.2)*
*Researched: 2026-03-13*
