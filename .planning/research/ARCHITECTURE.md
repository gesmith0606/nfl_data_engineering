# Architecture: Market Data Integration

**Domain:** Adding historical odds, line movement features, and CLV tracking to existing prediction pipeline
**Researched:** 2026-03-27
**Confidence:** HIGH (based on direct inspection of existing codebase, feature_engineering.py, prediction_backtester.py, and config.py)

## Current Architecture (What Exists)

```
Bronze (data/bronze/)
  schedules/season=YYYY/  ──  spread_line, total_line (CLOSING lines from nflverse)
  pbp/season=YYYY/        ──  spread_line, total_line (same closing lines, per-play)
  [14 other data types]
      |
      v
Silver (data/silver/)
  teams/pbp_metrics/      ──  EPA, success rate, rolling windows
  teams/tendencies/       ──  pace, PROE, 4th-down aggro
  teams/sos/              ──  opponent-adjusted EPA, SOS rankings
  teams/situational/      ──  home/away, divisional, game script
  teams/pbp_derived/      ──  penalties, turnovers, red zone, 11 metrics
  teams/game_context/     ──  weather, rest, travel, coaching (BASE for joins)
  teams/referee_tendencies/ ── penalty rates per crew
  teams/playoff_context/  ──  W-L-T, division rank, contention
  teams/player_quality/   ──  QB EPA, positional quality
      |
      v  (all joined on [team, season, week] via _assemble_team_features())
      |
      v  (split home/away, joined on game_id, differenced)
      |
Gold (data/gold/)
  predictions/            ──  model_spread, model_total, edges vs Vegas
  [backtester evaluates ATS accuracy + profit]
```

**Key join pattern:** game_context is the base table (has game_id, team, season, week, is_home). All other Silver sources left-join on [team, season, week]. Then home/away rows merge on game_id to create game-level differential features.

**Key leakage guard:** `get_feature_columns()` in feature_engineering.py only allows rolling/lagged features (_roll3, _roll6, _std, _ewm3) and pre-game context. Raw same-week stats are excluded.

## Proposed Architecture (What Changes)

```
Bronze (data/bronze/)
  odds/season=YYYY/       ──  NEW: opening_spread, closing_spread, opening_total,
                               closing_total, opening_home_ml, opening_away_ml
  schedules/season=YYYY/  ──  UNCHANGED (still has closing lines)
      |
      v
Silver (data/silver/)
  teams/market_data/      ──  NEW: line movement features per game_id
  [9 existing sources]    ──  UNCHANGED
      |
      v
Gold (data/gold/)
  predictions/            ──  UNCHANGED (output format)
  [backtester adds CLV]   ──  MODIFIED: CLV metrics in evaluation output
```

### New Components

| Component | Type | Path | Purpose |
|-----------|------|------|---------|
| Bronze odds ingestion | Script | `scripts/bronze_odds_ingestion.py` | Ingest opening/closing lines from external source |
| Market analytics | Module | `src/market_analytics.py` | Compute line movement features from Bronze odds |
| Silver market data CLI | Script | `scripts/silver_market_transformation.py` | CLI to run market analytics Silver transform |
| Bronze odds data | Data | `data/bronze/odds/season=YYYY/` | Raw opening/closing lines per game |
| Silver market data | Data | `data/silver/teams/market_data/season=YYYY/` | Derived line movement features |

### Modified Components

| Component | File | Change |
|-----------|------|--------|
| Config | `src/config.py` | Add `market_data` to `SILVER_TEAM_LOCAL_DIRS`, add Bronze odds path config |
| Feature engineering | `src/feature_engineering.py` | Update `get_feature_columns()` to allow market data features |
| Backtester | `src/prediction_backtester.py` | Add `evaluate_clv()` function |
| Backtest CLI | `scripts/backtest_predictions.py` | Add CLV reporting to output |
| Bronze registry | `scripts/bronze_ingestion_simple.py` | Add `odds` to `DATA_TYPE_REGISTRY` |

### Unchanged Components

Everything else. The ensemble training, model training, feature selection, prediction generation, and all existing Silver transforms remain untouched. Market data integrates through the existing join mechanism.

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `scripts/bronze_odds_ingestion.py` | Download external odds data, normalize schema, write Bronze Parquet | External data source (HTTP/file), data/bronze/odds/ |
| `src/market_analytics.py` | Read Bronze odds + Bronze schedules, compute movement features, write Silver | data/bronze/odds/, data/bronze/schedules/, data/silver/teams/market_data/ |
| `src/feature_engineering.py` (modified) | Include market_data in Silver source assembly + feature filtering | data/silver/teams/market_data/ |
| `src/prediction_backtester.py` (modified) | Compute CLV from model predictions vs closing lines | Gold predictions DataFrame |

## Data Flow: Bronze Odds Ingestion

```
External source (Excel/CSV/API)
    |
    v  [download + normalize schema]
    |
    v  [map team names to nflverse abbreviations]
    |
    v  [validate: one row per game_id, no duplicates]
    |
    v  [cross-reference closing_spread against nflverse spread_line for validation]
    |
data/bronze/odds/season=YYYY/odds_YYYYMMDD_HHMMSS.parquet
```

**Schema (Bronze odds):**

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| game_id | str | Constructed from date + teams | Must match nflverse format: YYYY_WW_AWAY_HOME |
| season | int | From schedule | Partition key |
| week | int | From schedule | |
| home_team | str | From source | Mapped to nflverse abbreviation |
| away_team | str | From source | Mapped to nflverse abbreviation |
| opening_spread | float | External source | Home perspective (positive = home favored) |
| closing_spread | float | External source or nflverse | Cross-validated against schedules.spread_line |
| opening_total | float | External source | Over/under |
| closing_total | float | External source or nflverse | Cross-validated against schedules.total_line |
| opening_home_ml | float | External source (if available) | American odds format |
| opening_away_ml | float | External source (if available) | American odds format |

## Data Flow: Silver Market Features

```
data/bronze/odds/season=YYYY/*.parquet
    |
    v  [read latest parquet per season]
    |
    v  [compute derived features]
    |       spread_shift = closing_spread - opening_spread
    |       total_shift = closing_total - opening_total
    |       spread_move_abs = abs(spread_shift)
    |       total_move_abs = abs(total_shift)
    |       spread_move_dir = sign(spread_shift)
    |       total_move_dir = sign(total_shift)
    |       crosses_key_spread = 1 if spread crossed 3, 7, or 10
    |
    v  [reshape to per-team-per-week rows (home + away perspectives)]
    |
data/silver/teams/market_data/season=YYYY/market_data_YYYYMMDD_HHMMSS.parquet
```

**Key design choice:** The Silver market_data output MUST be per-team-per-week (like all other Silver sources) to join cleanly in `_assemble_team_features()`. Each game produces two rows: one for the home team and one for the away team. The `team` and `is_home` columns are added to enable the join.

Market features that are symmetric (same for both teams, like spread_move_abs) get the same value in both rows. Features that are directional (like opening_spread) flip sign for the away perspective.

## Data Flow: CLV Tracking

```
Gold predictions (model_spread, model_total)
    +
Gold labels (spread_line as closing spread, total_line as closing total)
    |
    v  [evaluate_clv()]
    |
    v  clv_spread = model_spread - closing_spread
    v  clv_total = model_total - closing_total
    v  mean_clv, pct_beating_close, clv_by_season
    |
    v  [printed in backtest report; optionally saved to Gold CLV parquet]
```

**Important:** CLV uses the nflverse closing lines that are already in the assembled game DataFrame (spread_line, total_line columns from Bronze schedules). No additional data join needed.

## Integration with Feature Assembly

The feature assembly in `feature_engineering.py` currently:

1. Loads game_context as base (has game_id, team, season, week, is_home)
2. Left-joins 8 other Silver sources on [team, season, week]
3. Splits into home/away by is_home
4. Joins home + away on game_id
5. Computes diff_ columns for numeric features
6. Filters with get_feature_columns()

Market data integration touches steps 2 and 6:

**Step 2:** Add market_data to the Silver source loop. Since it is per-team-per-week (with flipped signs for away), it joins exactly like every other source.

**Step 6:** Update `get_feature_columns()` to recognize market data columns. Opening line features (opening_spread, opening_total) are pre-game knowable and should be allowed. Line movement features (spread_shift, etc.) are post-close and should be flagged -- allow for backtesting but document the leakage risk for live predictions.

The `_PRE_GAME_CONTEXT` set in get_feature_columns() would be extended:

```python
_PRE_GAME_CONTEXT = {
    # ... existing entries ...
    "opening_spread", "opening_total",  # Market opening assessment
}
```

Line movement features would need a separate category. The cleanest approach: add them to `_PRE_GAME_CONTEXT` for backtesting ablation, and document that for live use they would need to use a mid-week snapshot instead of closing lines.

## Patterns to Follow

### Pattern 1: Registry-Driven Bronze Ingestion
**What:** Add odds to DATA_TYPE_REGISTRY in bronze_ingestion_simple.py
**When:** Bronze ingestion phase
**Example:**
```python
"odds": {
    "adapter_method": "fetch_odds",  # or custom function
    "bronze_path": "odds/season={season}",
    "requires_week": False,
    "requires_season": True,
}
```

### Pattern 2: Silver Transform Module
**What:** Create market_analytics.py following the exact same pattern as team_analytics.py
**When:** Silver feature phase
**Example:**
```python
def compute_market_features(season: int) -> pd.DataFrame:
    """Compute line movement features from Bronze odds data."""
    odds = _read_latest_local("odds", season)  # Read Bronze
    # ... compute features ...
    # Reshape to per-team-per-week
    return features_df
```

### Pattern 3: Local-First Storage
**What:** Write Parquet to data/silver/teams/market_data/season=YYYY/
**When:** Always
**Note:** Follows existing timestamped filename pattern: `market_data_YYYYMMDD_HHMMSS.parquet`

## Anti-Patterns to Avoid

### Anti-Pattern 1: Storing Closing Lines Redundantly
**What:** Ingesting closing lines from an external source when nflverse already has them
**Why bad:** Two "truth" sources for the same number leads to disagreements and confusion
**Instead:** Use nflverse spread_line/total_line as canonical closing lines; only ingest opening lines from external source; cross-validate closing lines for data quality

### Anti-Pattern 2: Game-Level Features Without Per-Team Reshape
**What:** Adding market features directly at the game level (one row per game)
**Why bad:** Breaks the existing join pattern in _assemble_team_features() which expects per-team-per-week
**Instead:** Reshape to two rows per game (home + away) with appropriate sign flips

### Anti-Pattern 3: Using Closing Line Movement as a Prediction Feature
**What:** Using spread_shift (closing - opening) as input to the model for live predictions
**Why bad:** Closing line is not known until kickoff; this is leakage for live use
**Instead:** For ablation/backtesting this is fine (documented as retrospective). For live use, only opening_spread is pre-game knowable.

## Scalability Considerations

Not applicable for this milestone. The data volume is tiny: ~280 games per season x 9 seasons = ~2,500 rows total. No performance concerns.

## Sources

- Direct inspection of `src/feature_engineering.py` (lines 168-415) -- join pattern, feature filtering
- Direct inspection of `src/config.py` (SILVER_TEAM_LOCAL_DIRS, LABEL_COLUMNS)
- Direct inspection of `src/prediction_backtester.py` -- existing evaluation functions
- Direct inspection of `data/bronze/schedules/season=2024/` -- verified spread_line and total_line are closing lines
- [nflverse schedules dictionary](https://nflreadr.nflverse.com/articles/dictionary_schedules.html) -- column definitions
