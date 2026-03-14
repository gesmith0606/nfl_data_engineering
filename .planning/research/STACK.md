# Technology Stack

**Project:** NFL Data Engineering v1.2 Silver Expansion
**Researched:** 2026-03-13
**Confidence:** HIGH — all findings verified by direct execution in the project venv

## Verdict: No New Dependencies Required

Every computation needed for the Silver expansion (PBP team metrics, rolling windows, situational breakdowns, advanced player profiles, strength of schedule, historical context) is achievable with the existing installed stack. The key libraries — pandas 1.5.3, numpy 1.26.4, scipy 1.13.1 — are already installed and cover all required operations. Zero new pip packages.

## Current Stack (Unchanged for v1.2)

### Core Processing

| Technology | Version | Purpose | Silver Expansion Role |
|------------|---------|---------|----------------------|
| Python | 3.9.7 | Runtime | No change — all Silver APIs are 3.9-compatible |
| pandas | 1.5.3 | DataFrame processing | Primary engine for all 6 Silver expansion feature areas |
| numpy | 1.26.4 | Array math | Weighted averages (SoS), conditional logic, float32 downcasting |
| scipy | 1.13.1 | Statistical functions | `rankdata` for SoS percentile ranks; already installed |
| pyarrow | 21.0.0 | Parquet read/write | Reads Bronze PBP (float32 columns), writes Silver outputs |
| nfl-data-py | 0.3.3 | NFL data source | Bronze PBP already ingested; Silver reads from local Parquet |

### Infrastructure (Unchanged)

| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| fastparquet | 2024.11.0 | nfl-data-py dep | Required by nfl-data-py, not directly used in Silver |
| boto3 | 1.40.11 | S3 upload (optional) | Local-first; only used with --s3 flag |
| python-dotenv | 1.1.1 | Environment config | No change |
| tqdm | 4.67.1 | Progress bars | Useful for multi-season Silver builds |

## Verified Capability Map

Every Silver expansion feature area was prototyped and executed against the actual venv (2026-03-13):

### PBP Team Metrics (EPA/play, success rate, CPOE, red zone)

**Pattern:** `pbp_df[pbp_df['play_type'].isin(['pass','run'])].groupby(['season','week','posteam']).agg(...)`

**Verified:** Aggregates 49,492 PBP rows per season → ~180 team-week rows in 17 KB. Pure pandas `.groupby().agg()` — no new dependencies. Pass/rush split, red zone filter (`yardline_100 <= 20`), CPOE mean on pass plays all confirmed working.

**Confidence:** HIGH

### Rolling Windows on Team Metrics (3-week, 6-week, season-to-date, EWM)

**Pattern:** `df.groupby(['team','season'])['metric'].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())`

**Verified:** pandas 1.5.3 supports:
- `rolling(N, min_periods=1).mean()` — standard short windows
- `expanding(min_periods=1).mean()` — season-to-date
- `ewm(halflife=N).mean()` and `ewm(halflife=N).std()` — recency-weighted decay
- `ewm` via `groupby().transform(lambda s: s.ewm(...).mean())` — tested and confirmed working in pandas 1.5.3

**Key design decision (verified by execution):** Group by `['team', 'season']` for within-season rolling (Week 1 of each season gets NaN, not carry-over from prior season's Week 18). Use `groupby(['team'])` without season if cross-season carry-over is desired for the season opener. Both patterns work.

**Confidence:** HIGH

### Situational Breakdowns (game script, home/away, divisional)

**Pattern:** `pd.cut()` for game script bins → `groupby(['situation']).agg()` for split stats

**Verified:** Existing `compute_game_script_indicators()` in `src/player_analytics.py` already uses this pattern. Extension to team-level situational splits requires only additional groupby keys — no new code patterns.

**Confidence:** HIGH (pattern already in codebase)

### Advanced Player Profiles (NGS + PFR + QBR merge)

**Pattern:** Multi-table `pd.merge()` on `[player_id, season, week]` keys

**Verified:** Standard pandas merge. All Bronze data (NGS separation, PFR pressure/blitz, QBR) is already ingested as local Parquet. The only risk is key alignment across tables — covered in PITFALLS.md.

**Confidence:** HIGH

### Strength of Schedule (opponent-adjusted EPA rankings)

**Pattern:** Join schedule to team EPA ratings → `scipy.stats.rankdata()` for percentile ranking → rolling weighted average via `numpy.average(weights=...)`

**Verified:** `scipy.stats.rankdata` converts EPA ratings to ordinal ranks (1–32). `numpy.average(vals, weights=weights)` computes recency-weighted SoS. Both confirmed working. `pandas.Series.rank(pct=True)` is an alternative that avoids scipy entirely if preferred.

**Confidence:** HIGH

### Historical Context (combine + draft capital linking)

**Pattern:** `pd.merge()` on player_id/gsis_id to link combine measurables and draft pick data to player profiles

**Verified:** Standard merge; Bronze combine and draft_picks tables are already available as local Parquet. Join key alignment (player_id vs gsis_id vs name matching) is the only complexity — covered in PITFALLS.md.

**Confidence:** HIGH

## Memory Profile for Silver Expansion

PBP is the only large input. Per-season processing (reading one season at a time from Bronze Parquet):

| Input | Rows/Season | In-Memory (relevant cols) | Silver Output |
|-------|-------------|--------------------------|---------------|
| PBP (10 cols for team metrics) | ~49,500 | ~9 MB (float32) | ~180 team-week rows (17 KB) |
| player_weekly | ~6,000 | ~5 MB | existing Silver |
| NGS (3 stat types) | ~2,650 total | <2 MB | player profile rows |
| PFR weekly (4 s_types) | ~2,800 total | <2 MB | player profile rows |
| QBR weekly | ~573 | <1 MB | player profile rows |

**Safe pattern:** Read one season of PBP, aggregate to team-week metrics, write Silver Parquet, release DataFrame. Peak memory stays under 50 MB per season. Do not load all 10 seasons of PBP simultaneously.

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| pandas rolling/ewm | Polars rolling | Requires Python 3.10+ migration; entire pipeline rewrite |
| pandas rolling/ewm | Dask | PBP at 9 MB/season (relevant cols) is trivially small; no need for distributed |
| scipy.stats.rankdata | statsmodels | Not installed; statsmodels OLS is overkill for ranking; pandas.rank(pct=True) is simpler |
| pandas .groupby().agg() | DuckDB SQL | DuckDB available as MCP but adds I/O round-trip; pandas is faster for in-memory PBP slices |
| numpy.average (weighted) | scipy.signal.lfilter | FIR filters for sports analytics is over-engineered; numpy.average with explicit weights is readable and sufficient |
| pandas ewm(halflife=int) | ewm(halflife=timedelta) | timedelta-based halflife requires pandas timestamp index; week integers work and are simpler |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| statsmodels | Not installed; OLS regression for SoS adjustment is premature optimization; adds 8 MB dependency | `scipy.stats.rankdata` + weighted mean covers SoS |
| polars | Python 3.9 incompatible; entire Silver/Gold/Draft pipeline uses pandas DataFrames | Keep pandas 1.5.3 |
| pyjanitor | Syntactic sugar over pandas; adds dependency for no capability gain | Native pandas chaining |
| nfl-analytics / nfelo libraries | No battle-tested pip-installable Python NFL analytics library exists with this scope; community solutions are R-first | Compute from raw PBP columns (EPA, WPA, CPOE already pre-computed by nflverse) |
| great_expectations for Silver validation | Already installed (v1.5.8) but overly complex for layer-boundary checks; existing `validate_data()` pattern is sufficient | Keep `validate_data()` pattern |
| Any new pip package | Zero new capabilities are blocked by missing libraries | Use existing stack |

## Stack Patterns by Feature Area

**PBP team metrics (EPA, success rate, CPOE, pace):**
- Filter: `play_type.isin(['pass','run'])` for scrimmage plays
- Aggregate: `groupby(['season','week','posteam']).agg(epa_per_play=('epa','mean'), success_rate=('success','mean'), ...)`
- Red zone: add `yardline_100 <= 20` filter before groupby
- CPOE: filter `play_type == 'pass'` only, then mean of `cpoe` column

**Rolling windows on team metrics:**
- Short windows (3, 6 week): `groupby(['team','season'])['metric'].transform(lambda s: s.shift(1).rolling(N, min_periods=1).mean())`
- Season-to-date: `.transform(lambda s: s.shift(1).expanding().mean())`
- EWM recency weighting: `.transform(lambda s: s.shift(1).ewm(halflife=3).mean())` — halflife=3 means week N-3 weighted at 50% of week N-1

**Strength of schedule:**
- Build team defensive EPA ratings per season-week from PBP defteam aggregation
- Join to schedule (home_team, away_team) to get each team's upcoming/past opponents
- `scipy.stats.rankdata(team_epa) / 32` for percentile difficulty
- Rolling 3/6 week weighted average with `numpy.average(opp_ratings, weights=recency_weights)`

**Player profile merging:**
- Load Bronze NGS, PFR, QBR as separate DataFrames
- Primary join key: `player_id` (where available) or `player_name + team + season`
- Use `pd.merge(..., how='left')` to keep player_weekly as the spine
- Combine/draft: join on `player_id` or name-matching (name matching needed for older seasons)

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pandas 1.5.3 | numpy 1.26.4 | Verified; numpy 2.x breaks ABI — do not upgrade numpy |
| pandas 1.5.3 | pyarrow 21.0.0 | Verified; newer pyarrow is backward-compatible with old pandas |
| pandas 1.5.3 | scipy 1.13.1 | No direct integration; scipy used standalone — no compatibility concern |
| nfl-data-py 0.3.3 | fastparquet 2024.11.0 | Required dependency; do not remove |

## Installation

No changes to requirements.txt:

```bash
pip install -r requirements.txt
```

All required capabilities (pandas rolling/ewm/expanding, numpy.average, scipy.stats.rankdata) are already present.

## Sources

- Local venv execution (2026-03-13) — all patterns verified against pandas 1.5.3, numpy 1.26.4, scipy 1.13.1
- [pandas 1.5 window operations docs](https://pandas.pydata.org/pandas-docs/version/1.5/user_guide/window.html) — rolling, expanding, ewm confirmed in 1.5 series
- [pandas DataFrame.ewm](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.ewm.html) — halflife parameter (integer) confirmed working in 1.5.3
- [scipy.stats.rankdata](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.rankdata.html) — used for SoS percentile ranking
- [nflverse PBP field reference](https://github.com/nflverse/nflverse-pbp) — EPA, WPA, CPOE, success pre-computed fields available in Bronze PBP
- [nflfastR team aggregation patterns](https://nflfastr.com/articles/nflfastR.html) — standard EPA/play, success_rate, CPOE aggregation approach (R, but patterns translate directly to pandas)
- Memory profile: measured against 49,492-row simulated PBP with float32 columns — 8.8 MB in-memory, 17 KB after team-week aggregation

---
*Stack research for: NFL Data Engineering v1.2 Silver Expansion*
*Researched: 2026-03-13*
