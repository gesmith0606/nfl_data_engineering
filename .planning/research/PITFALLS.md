# Pitfalls Research

**Domain:** NFL data engineering — Silver layer expansion with PBP analytics, rolling windows, team metrics, and advanced player profiles
**Researched:** 2026-03-13
**Confidence:** HIGH (grounded in existing codebase analysis, confirmed implementation patterns, and established data engineering anti-patterns)

---

## Critical Pitfalls

### Pitfall 1: Rolling Windows Bleed Across Season Boundaries

**What goes wrong:**
The current `compute_rolling_averages()` in `src/player_analytics.py` groups by `player_id` only — not `(player_id, season)`. A 3-week rolling average for Week 1 of 2024 silently includes Weeks 16–18 of 2023. The same flaw propagates to team-level metrics if the Silver expansion groups by `posteam` instead of `(posteam, season)` when computing EPA/play or CPOE rolling windows.

This is not a theoretical issue — the existing `_std` (season-to-date) average on line ~219 of `player_analytics.py` correctly uses `groupby(['player_id', 'season'])`. The rolling windows on lines ~211–215 do not:

```python
# Current (line ~212) — season-blind, WRONG for multi-season datasets:
df.groupby('player_id')[col].transform(
    lambda s: s.shift(1).rolling(window, min_periods=1).mean()
)
```

Backtest datasets covering 2020–2024 contain ~26K player-week rows. The contamination is only visible when Week 1 rolling values are inspected or when backtesting Week 1–3 predictions.

**Why it happens:**
The groupby('player_id') pattern is intuitive — you want each player's rolling history. Within a single season it produces correct output because all weeks sort contiguously. Multi-season runs expose the flaw only when you look at Week 1 values.

**How to avoid:**
Change the groupby key to `['player_id', 'season']` for all rolling windows:

```python
df.groupby(['player_id', 'season'])[col].transform(
    lambda s: s.shift(1).rolling(window, min_periods=1).mean()
)
```

Apply the same pattern to team-level rolling metrics in new PBP Silver transforms. Add a regression test:

```python
week1_rolls = df.loc[df['week'] == 1, 'fantasy_points_ppr_roll3']
assert week1_rolls.isna().all(), "Week 1 roll3 should be NaN (no prior in-season games)"
```

**Warning signs:**
- Week 1 rolling averages are non-null and non-zero for veterans when they should be NaN
- Backtest Week 1–3 MAE is anomalously lower than Week 4+ MAE (contamination makes early predictions look too good)
- Multi-season Silver output shows fewer NaN rolling values than single-season output

**Phase to address:**
PBP Team Metrics (first Silver expansion phase) — fix the existing player_analytics.py pattern simultaneously, so the correction propagates rather than requiring a retroactive patch after team metrics are built on the same flawed convention.

---

### Pitfall 2: Loading Raw PBP Into Silver Transform Causes OOM on Multi-Season Backfills

**What goes wrong:**
A single PBP season is ~50K rows × 103 columns. In memory as float64, that is approximately 400–500 MB. Three seasons (the rolling window context needed for SOS calculations) reaches 1.2–1.5 GB, leaving no headroom on a 16 GB machine. A 10-season backfill (2016–2025) of team metrics that loads all seasons simultaneously OOMs or triggers OS swap, making the Silver backfill impractical.

The Bronze ingestion script already solved this by processing one season at a time (Phase 2 decision, documented in `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md`). Silver expansion developers may not realize this constraint applies equally to Silver reads.

**Why it happens:**
Team metric rolling windows appear to require cross-season data (e.g., "what was this team's EPA in the last 3 games of last season?"). The temptation is to load all seasons, compute rolling values across the concatenated DataFrame, and write output. This works for player_weekly (5K rows/season) but not for PBP (50K rows/season).

**How to avoid:**
Always aggregate PBP to game-level or team-week-level **before** any cross-season operations:

```python
# Step 1: aggregate within the season (50K rows → 512 team-game rows)
team_weekly = (
    pbp_df[pbp_df['season_type'] == 'REG']
    .groupby(['posteam', 'season', 'week'])
    .agg(epa_per_play=('epa', 'mean'), success_rate=('success', 'mean'), ...)
    .reset_index()
)
# Step 2: write team_weekly to Silver, then compute rolling across seasons from Silver
```

A Silver team-week summary table (`data/silver/teams/weekly/season=YYYY/`) contains 512 rows/season (32 teams × 16 weeks), not 50K. Cross-season rolling against this table is trivial.

Enforce: never `pd.read_parquet(pbp_path)` in Silver scripts without `columns=` subsetting. Use pyarrow column projection at read time:

```python
pbp_df = pd.read_parquet(pbp_path, columns=['epa', 'posteam', 'defteam', 'week', 'season', 'success', 'play_type'])
```

**Warning signs:**
- Silver team metrics transform takes >2 minutes per season
- Process memory exceeds 2 GB during Silver runs (monitor with `tracemalloc` or `/usr/bin/time -l`)
- Scripts complete for a single recent season but crash when run on the full 2016–2025 backfill

**Phase to address:**
PBP Team Metrics (first phase) — establish the aggregation-first pattern as the baseline Silver convention before any rolling logic is added. Document it explicitly: "PBP Silver outputs are always aggregated summaries, never row-level play data."

---

### Pitfall 3: Opponent-Adjusted Metrics Create Circular Dependencies in Rolling SOS

**What goes wrong:**
Computing opponent-adjusted EPA (team A's EPA adjusted for the strength of team B's defense) requires knowing team B's defensive EPA strength, which was itself computed against other opponents including team A. If both teams played each other in Week 1, adjusting Week 5 performance creates a feedback loop: team A's Week 5 adjusted EPA depends on team B's defense strength, which depends on team A's Week 1 offensive EPA, which was also adjusted.

Naive implementations either converge to wrong values (iterative adjustment without convergence check) or silently produce NaN-contaminated outputs (NaN propagation through the circular chain).

The existing `compute_opponent_rankings()` avoids this because it uses simple un-adjusted averages computed post-season, with no circular dependency. Rolling in-season SOS changes the dependency structure.

**Why it happens:**
The mathematical structure looks like a standard join: "for each team-week, look up opponent's defensive EPA rating." Developers don't recognize that the opponent's rating is itself derived from data that includes the current team's past performances against that opponent.

**How to avoid:**
Apply the one-lag rule universally: when computing team A's adjusted metric for week N, use opponent strength metrics computed through week N-1 only:

```python
# Step 1: compute raw (unadjusted) team EPA by week
raw_epa = pbp_agg.groupby(['team', 'season', 'week'])['epa'].mean()

# Step 2: lag the raw values before joining as opponent strength
opponent_strength = raw_epa.shift(1)  # lag within (team, season) groups

# Step 3: join opponent strength using the lagged values only
```

Test: assert that Week 1 adjusted EPA equals raw EPA — with no prior data, the adjustment should be zero.

Test idempotency: run the SOS transform twice on the same input, compare outputs byte-for-byte. A circular dependency will produce different values on repeated runs if any randomness is involved in convergence.

**Warning signs:**
- Week 1 adjusted EPA is non-zero (no prior opponent data should mean no adjustment)
- Running the transform twice gives different results (non-idempotent)
- Teams that played each other in Week 1 show anomalous adjusted values after Week 4
- SOS rankings change retroactively when new weeks are added (should only change for weeks that haven't been locked in)

**Phase to address:**
Strength of Schedule phase — circular dependency only manifests when rolling SOS is implemented. Define and test the lagged computation pattern before any SOS code ships.

---

### Pitfall 4: NGS / PFR / QBR Availability Gaps Produce Silent NaN Columns in Rolling Averages

**What goes wrong:**
NGS data starts in 2016; PFR in 2018; QBR in 2006 but only for qualified QBs. Many players in nfl-data-py weekly data have no NGS record in some weeks (only targeted players appear in NGS receiving; QBs who threw fewer than ~20 passes may not qualify for QBR). When joining NGS separation or PFR pressure rates to player-week Silver tables, the left join silently produces NaN for 20–60% of rows depending on position.

Rolling averages applied to NaN-heavy columns with `min_periods=1` (the current default in `compute_rolling_averages()`) produce "averages" that are actually single-game observations — statistically meaningless but formatted identically to well-supported averages in the Parquet output.

**Why it happens:**
The `how='left'` merge is correct for data completeness. The issue is that downstream code treats all Silver columns as uniformly populated. Sparse NGS/PFR metrics get the same rolling treatment as high-coverage weekly stats like `targets` and `yards`.

**How to avoid:**
- Track and log NaN coverage at Silver write time for all NGS/PFR/QBR-derived columns:

```python
for col in ['ngs_separation', 'pfr_pressure_rate', 'qbr']:
    coverage = df[col].notna().mean()
    logger.info(f"Coverage: {col} = {coverage:.1%}")
    if coverage < 0.20:  # threshold depends on position filter
        logger.warning(f"Sparse metric {col}: only {coverage:.1%} populated")
```

- Use `min_periods=3` (not `min_periods=1`) for rolling windows on sparse NGS/PFR/QBR columns to require meaningful history before producing an average.
- Separate metrics into "high coverage" (snap_pct, targets, yards → all skill position players) and "sparse/optional" (NGS separation → targeted WRs only; QBR → qualified QBs only). Document each metric's expected coverage in the Silver schema.
- Do not include sparse metrics in the default rolling average loop (`ROLLING_STAT_COLS` in `player_analytics.py`). Handle them in a separate function with explicit coverage validation.

**Warning signs:**
- NaN rate >50% for NGS or PFR columns in Silver output for WR/RB rows
- Rolling averages for the same metric showing wildly different values for similar players (one has 5 data points, another has 1 because the join only caught one week)
- Gold projections for QBs show NaN QBR feature columns in the projection DataFrame

**Phase to address:**
Advanced Player Profiles phase — coverage tracking must be built before NGS/PFR metrics are added to Silver rolling averages, not as a post-hoc fix.

---

### Pitfall 5: Combine / Draft Capital Join Causes Row Explosion in Silver

**What goes wrong:**
Combine data is one row per player (no season/week partition). Draft picks are one row per player per draft year. When joining either to the player-week Silver table on `player_id` alone, the join succeeds but each player's single combine/draft row gets duplicated across all weeks of all seasons for that player. A player with 5 seasons × 18 weeks = 90 Silver rows gets 90 identical combine rows after the join — a 90× duplication of static data.

This inflates the Silver table size (combine data has ~50 columns), breaks any aggregation that double-counts the join key, and makes the table semantically incorrect: combine data is a player attribute, not a weekly observation.

A subtler version: joining by `player_name` instead of `player_id` causes multi-player collisions. "Mike Williams" returned 3 different players in nfl-data-py across different seasons.

**Why it happens:**
Combine and draft data don't have week/season partitions, so the natural join key appears to be just `player_id`. Developers use a standard `df.merge()` without thinking through the cardinality — the Silver player-week table has one row per player per week, and a 1:1 join on `player_id` alone produces 1:N.

**How to avoid:**
Treat combine/draft capital as a **player profile dimension table**, not a fact table:
- Store it separately: `data/silver/players/profiles/combine_draft_profiles.parquet` — one row per player, containing `player_id`, combine measurables, draft round, draft pick, AV, career_av, etc.
- In downstream Gold/projection code and ML feature matrices, join the profile table at feature-construction time, not during Silver transformation of weekly data.
- If embedding in a weekly Silver table is required (e.g., for a flat ML feature export), explicitly document the join as a broadcast join and verify row count is unchanged after the join.
- Always join on GSIS `player_id` (or `gsis_id` for combine). Never join on player names.

```python
# Correct: dimension table stays separate
assert len(weekly_silver.merge(combine_profiles, on='player_id', how='left')) == len(weekly_silver), \
    "Combine join should not change row count"
```

**Warning signs:**
- Silver usage parquet file size grows significantly after combine/draft join is added (should be ~same row count)
- Row count of Silver output exceeds row count of player_weekly Bronze source
- Duplicate player entries for the same season/week after merge

**Phase to address:**
Historical Context phase (combine + draft capital) — establish the profile dimension table pattern before writing any join logic.

---

### Pitfall 6: New Silver Outputs Bypass the download_latest_parquet() Read Convention

**What goes wrong:**
The project's read convention is `download_latest_parquet()` from `src/utils.py` for S3 reads, and the corresponding glob-and-sort pattern for local reads. The existing `_read_local_bronze()` function uses `files[-1]` (last by alphabetical sort = latest timestamp). New Silver writers for PBP team metrics, SOS rankings, or player profiles that use ad-hoc paths or non-standard naming conventions will be invisible to `generate_projections.py` and `backtest_projections.py`, which look for Silver tables at registered paths.

Additionally, the existing `SILVER_PLAYER_S3_KEYS` in `config.py` only covers three tables: `usage_metrics`, `opponent_rankings`, `rolling_averages`. Adding five new Silver tables without registering them in config creates fragile path strings scattered across scripts.

**Why it happens:**
The local-first workflow makes path registration feel optional — you can read any file with a direct path. The convention matters for S3 (when credentials are re-established), for the health check script, and for ensuring the GHA weekly pipeline finds the right tables.

**How to avoid:**
- Register every new Silver output in `config.py::SILVER_PLAYER_S3_KEYS` before writing the first file:
  - `team_metrics`, `team_tendencies`, `situational_splits`, `player_profiles`, `sos_rankings`
- Write a `_read_local_silver()` helper in `silver_player_transformation.py` that mirrors `_read_local_bronze()` — takes `(table_name, season, week=None)` and uses the registered key pattern.
- Add the new Silver tables to `check_pipeline_health.py` so the health check validates their presence.
- Before shipping any new Silver table, run: `download_latest_parquet()` (S3) or `_read_local_silver()` (local) and confirm the correct file is returned.

**Warning signs:**
- New Silver tables exist on disk but `generate_projections.py` doesn't use them (reads old data)
- Adding `--season 2024` to a Silver-dependent script reads files from a different season
- S3 health check passes but new Silver tables are not checked
- `check_pipeline_health.py` reports "OK" despite new Silver tables being missing

**Phase to address:**
Every Silver expansion phase — establish the path convention at the start of each phase as a precondition, not as a cleanup step.

---

### Pitfall 7: Playoff Weeks Contaminate Regular-Season Rolling Metrics

**What goes wrong:**
PBP data includes `season_type` values of `'REG'` (regular season, weeks 1–18) and `'POST'` (playoffs, weeks 19–22). Team EPA, CPOE, and success rate computed from playoff games are not predictive of regular-season performance — playoff opponents, game scripts, and defensive schemes are systematically different. If playoff games are included in rolling team metrics used to project Week 1 of the next season, teams with deep playoff runs receive inflated or deflated EPA estimates that don't reflect their regular-season profile.

This also affects the within-season rolling window: if the Silver transform processes games by week number, and postseason games are coded as weeks 19–22, a 3-week rolling average for Week 1 of the next season picks up playoff data from weeks 20–22.

**Why it happens:**
The `PBP_COLUMNS` list includes `season_type` but Silver developers may filter on `week <= 18` rather than `season_type == 'REG'`. Week 19–22 exists in PBP data; filtering by week number is correct for regular-season only if the `season_type` filter is also applied.

**How to avoid:**
Always filter at the earliest point in PBP Silver transforms:

```python
pbp_reg = pbp_df[pbp_df['season_type'] == 'REG'].copy()
```

Write a test that verifies `posteam_team_epa_per_play` is only computed for regular-season games:

```python
assert pbp_df[pbp_df['season_type'] == 'POST']['epa_per_play'].isna().all()  # no playoff rows in aggregation
```

For within-season rolling, verify that the maximum week in any Silver team-metrics table is 18, not 22.

**Warning signs:**
- Teams with Super Bowl appearances show anomalously high/low EPA in Week 1 projections
- Team-week Silver table contains rows with `week > 18`
- Week 1 rolling averages for defending Super Bowl teams differ from other teams with equivalent regular-season performance

**Phase to address:**
PBP Team Metrics (first phase) — the `season_type` filter must be added to all PBP aggregation functions as a baseline requirement, not as a later refinement.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Load full-season PBP then aggregate | Simpler code, no pre-aggregation step | OOM on 3+ season backfills; 2–5 min per season | Never — always aggregate at read time using column subsetting |
| `groupby('player_id')` for rolling windows | Less typing than `groupby(['player_id', 'season'])` | Season-boundary contamination in backtests and Gold projections | Never — one line change, no complexity cost |
| `min_periods=1` for sparse NGS/PFR rolling | No NaN in output, "feels complete" | Rolling averages from 1–2 data points are statistically meaningless; downstream ML overfit to noise | Never for model features; acceptable for exploratory/manual analysis only |
| Join combine/draft to player-week fact table | All features in one wide table for ML | Row explosion (90× static data duplication), inflated file size, fragile if schema changes | Only for a final flat ML feature export, clearly documented, never stored in Silver |
| Hardcode window sizes and thresholds | Quick implementation | Blocks experimentation; different Gold consumers want different window sizes | Parameterize from day one; 3 and 6 are fine defaults |
| Glob-and-sort instead of `download_latest_parquet()` for Silver reads | Works locally, no S3 dependency | Silent stale reads when S3 is re-enabled; not compatible with health check convention | Local-only dev experiments only; must swap before any S3 sync |
| Compute SOS from raw PBP on each weekly run | No intermediate table needed | Re-aggregating 50K × 103 PBP rows repeatedly adds 30–60s/season; compounds in GHA 6-minute timeout | Acceptable for one-time backfill; cache team-week summaries for weekly pipeline |
| Skip `season_type` filter on PBP | One less filter step | Playoff games contaminate regular-season metrics silently | Never — one `.copy()` + boolean filter |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PBP `pd.read_parquet(pbp_path)` | No `columns=` argument — loads all 103 Bronze columns into memory | Pass `columns=[list of needed columns]`; column projection via pyarrow avoids loading unused data |
| NGS `import_ngs_data(stat_type='receiving')` | Assuming all WRs have an NGS record each week | Only targeted players appear; join with `how='left'` and log NaN rate per column |
| PFR sub-types (`pass`, `rush`, `rec`, `def`) | Merging all 4 sub-types simultaneously on `(player_id, week)` | Each sub-type covers a different player population; join them one at a time onto player-week master, in separate passes |
| QBR `import_qbr(frequency='weekly')` | Using QBR presence to confirm a QB started | QBR only includes QBs with qualifying playing time; absence means did not qualify, not necessarily did not play |
| Combine `import_combine_data()` | Assuming every player_weekly player has a combine row | ~30–40% of players have no combine data (UDFAs, international, pre-2000); always `how='left'` join |
| Draft picks join | Joining on `player_name` for players without `gsis_id` match | Use `pfr_id` or `gsis_id` as primary key; document that pre-2016 draft capital has ~20% unlinked players |
| PBP playoff games | Filtering `week <= 18` to exclude playoffs | Filter `season_type == 'REG'` — week 19–22 exists in PBP; week-number filter alone is insufficient for some edge cases |
| Team abbreviations | OAK (2019) ≠ LV (2020), SD (2016) ≠ LAC (2017) | Use the team abbreviation crosswalk from `data/bronze/teams/`; or normalize to `nfl.import_team_desc()` canonical abbreviations |
| Schedules merge for opponent lookup | Building opponent lookup per week from schedules without deduplicating postseason games | Filter schedules to `game_type == 'REG'` before building opponent map used in regular-season ranking |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Raw PBP in Silver transform (no aggregation) | Silver parquet is 200–500 MB/season instead of <1 MB; transform takes 2–5 min/season | Aggregate to team-week before Silver write; use column subsetting at read time | Immediately on 3+ season backfills |
| `groupby().transform()` on 103-column DataFrame | 60–90s per season for rolling computation on PBP-sourced data | Select only needed columns before transform; roll on 5–10 target columns, not all 103 | At 3+ seasons or when adding new rolling metrics |
| Recomputing historical SOS each weekly run | O(seasons × teams) recalculation of stable past data | Cache team-week summaries; on weekly runs, only recompute current season rows | After 5 seasons of history, cumulative time matters in GHA 6-minute timeout |
| `iterrows()` in Vegas implied totals | Currently iterates schedule rows to build dict (player_analytics.py line ~357) — 32 rows is fine, but if adapted for PBP game-by-game it degrades | Vectorize with `df.set_index(['home_team'])[['implied_home']].to_dict()` | At 32 teams it is trivial; matters if iterated per play |
| PBP duplicate play_id rows | Cartesian product when joining PBP player IDs to NGS/PFR if duplicate play IDs exist (known nfl-data-py issue for some seasons) | Deduplicate PBP on `(game_id, play_id)` before any player-level join | Silently doubles player stat totals for affected seasons |
| Multi-season PBP load for rolling context | Need 3 weeks of prior season for Week 1 rolling — loads full prior season unnecessarily | Load prior season summary table (512 rows), not prior season PBP (50K rows) | First weekly run of a new season where prior-season Silver summaries are available |

---

## "Looks Done But Isn't" Checklist

- [ ] **Playoff filter:** Silver team-metrics table contains no rows with `week > 18` or `season_type == 'POST'`
- [ ] **Season-scoped rolling:** Assert that Week 1 rolling values are NaN or equal to the single in-season observation (no prior-season bleed into roll3, roll6)
- [ ] **NGS/PFR coverage:** NaN rate per metric is logged at Silver write time; CI assertion fails if NaN >80% for a metric expected to cover the filtered position group
- [ ] **Combine/draft join cardinality:** `len(silver_with_profiles) == len(silver_without_profiles)` — no row explosion
- [ ] **Circular SOS check:** Week 1 adjusted EPA equals raw EPA (zero adjustment with no prior opponent data)
- [ ] **Silver path registration:** Every new Silver output has a key in `config.py::SILVER_PLAYER_S3_KEYS` and is checked by `check_pipeline_health.py`
- [ ] **download_latest_parquet() compliance:** New Silver tables are readable via the existing utility functions, not only via direct path strings
- [ ] **Memory gate:** Full 2016–2025 Silver team-metrics backfill stays under 2 GB peak memory (verifiable with `tracemalloc` or `/usr/bin/time -l`)
- [ ] **QBR null handling:** Gold QB projections do not silently drop QBR features for QBs who don't appear in QBR data; they receive positional average fallback or an explicit null flag
- [ ] **CPOE null handling:** CPOE in PBP is only populated for pass plays (~40% of rows); team-level CPOE aggregation uses `nanmean`, not `mean`, to avoid nullifying games where no pass plays occurred in a subset

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Season-boundary rolling contamination discovered post-build | MEDIUM | Fix groupby key in `player_analytics.py` (one-line change); re-run Silver for all seasons; Silver outputs are idempotent via timestamped writes, so corrected files automatically take precedence via latest-file read |
| OOM crash during 10-season PBP Silver backfill | LOW | Add column subsetting and per-season aggregation; re-run backfill sequentially with `--seasons 2016 2017 ...` |
| Circular opponent-adjusted SOS values baked into Gold | HIGH | Roll back Silver SOS files by keeping the prior timestamped version; fix lagged computation pattern; regenerate SOS then Gold; validate via backtest that Week 1 adjusted EPA = raw EPA |
| Combine/draft join row explosion in Silver | MEDIUM | Drop the inflated Silver table; move combine/draft to profile dimension table (`data/silver/players/profiles/`); regenerate Silver; downstream Gold still uses player_weekly Silver unchanged |
| NGS NaN-heavy rolling averages in Gold features | LOW | Add `min_periods=3` guard and coverage logging; re-run Silver for affected seasons; Gold automatically picks up corrected Silver via latest-file convention |
| New Silver tables not found by `download_latest_parquet()` | LOW | Register correct paths in `SILVER_PLAYER_S3_KEYS` and confirm glob pattern matches; no data loss |
| Playoff weeks in team EPA rolling averages | LOW | Add `season_type == 'REG'` filter to PBP aggregation function; re-run Silver team metrics; compare before/after for teams with >2 playoff wins |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Rolling window season-boundary bleed | PBP Team Metrics (Phase 1) | Test: Week 1 roll3 values are NaN; backtest Week 1–3 MAE should not improve significantly vs baseline |
| PBP memory / full-season load | PBP Team Metrics (Phase 1) | Peak memory <2 GB on 10-season backfill; measured with tracemalloc |
| Playoff-week EPA contamination | PBP Team Metrics (Phase 1) | Assert max week in Silver team-metrics table is 18; compare Super Bowl team EPA before/after fix |
| New Silver path convention bypass | Every phase | Integration test: write Silver file, read via utility function, confirm latest version returned |
| Opponent-adjusted circular SOS | Strength of Schedule phase | Week 1 adj_EPA == raw_EPA; idempotency test: run transform twice, diff output |
| NGS/PFR silent NaN coverage | Advanced Player Profiles phase | NaN rate logged per metric; CI fails if coverage unexpectedly low for targeted position group |
| Combine/draft join cardinality | Historical Context phase | Assert row count unchanged after combine/draft join; profile table is separate parquet |
| QBR null in Gold QB projections | Advanced Player Profiles phase | Unit test: QB missing from QBR still gets a projection (positional average fallback) |

---

## Sources

- `src/player_analytics.py` — confirmed rolling average groupby gap (lines 210–215 vs. season-scoped std on line 219)
- `scripts/silver_player_transformation.py` — local file reader patterns, established Silver path convention
- `src/config.py` — `PBP_COLUMNS` (103 columns), `SILVER_PLAYER_S3_KEYS` (3 registered tables), `DATA_TYPE_SEASON_RANGES` (NGS 2016+, PFR 2018+, QBR 2006+)
- `.planning/PROJECT.md` — v1.2 milestone feature list, confirmed PBP is 50K rows × 103 columns, season ranges per data type
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — Phase 2 PBP memory-safe batching decision; team abbreviation changes documented
- `docs/NFL_DATA_DICTIONARY.md` — NGS/PFR/QBR availability windows and coverage characteristics
- CLAUDE.md / MEMORY.md — known quirks: `snap_counts` uses `offense_pct` not `snap_pct`; `receiving_air_yards` not `air_yards`; `import_rosters` vs `import_seasonal_rosters` — confirms the column-name surprise pattern repeats across data types and must be anticipated for NGS/PFR/QBR joins

---
*Pitfalls research for: NFL Silver layer expansion — PBP analytics, rolling windows, team metrics, advanced player profiles*
*Researched: 2026-03-13*
