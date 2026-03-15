# Phase 17: Advanced Player Profiles - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate NGS, PFR, and QBR-derived player profile metrics with rolling windows for enhanced QB, RB, WR, and TE evaluation. Expose via a new Silver CLI script (`silver_advanced_transformation.py`) and analytics module (`player_advanced_analytics.py`). Output as a single merged Parquet file per season at `data/silver/players/advanced/`. Register new Silver output paths in config.py.

</domain>

<decisions>
## Implementation Decisions

### Data Source Coverage
- Use PLAYER_DATA_SEASONS (2020-2025) for all three sources — consistent with existing Silver player data
- Do not use each source's full historical range (NGS 2016+, PFR 2018+, QBR 2006+) — avoids sparse early years and misaligned coverage

### Player ID Joining
- Left-join from Bronze roster/player data as the master list
- Join NGS/PFR/QBR onto roster by name+team+season
- Players without advanced stats get NaN columns — preserved in output (no silent row drops per success criteria #4)
- PFR match rate (~80%) logged at WARNING level with unmatched player names; match rate reported at INFO level
- Never fail the pipeline on match quality — log warnings only

### Output Structure
- Single merged wide Parquet file per season at `data/silver/players/advanced/season=YYYY/`
- All NGS, PFR, and QBR columns in one row per player-week
- Easier downstream consumption than 3 separate joins
- Rolling windows (roll3, roll6) with min_periods=3 (per success criteria #5) for sparse advanced stat columns

### Data Input
- Read from Bronze parquet files at data/bronze/ngs/, data/bronze/pfr/, data/bronze/qbr/ — follows medallion pattern (Silver reads from Bronze)
- Do not call nfl-data-py live — Bronze layer is the source of truth

### CLI Design
- New script: `scripts/silver_advanced_transformation.py`
- Always processes all three sources (NGS + PFR + QBR) in every run — no selective --sources flag
- Matches silver_team_transformation.py pattern (always computes all datasets per run)
- Full season processing via `--seasons` argument (e.g., `--seasons 2020 2021 2022 2023 2024`)
- If Bronze data for a source is missing for a season, log warning and produce output with NaN columns for that source — never fail the whole run

### Module Organization
- New file: `src/player_advanced_analytics.py` — keeps concerns separate from existing player_analytics.py
- player_analytics.py handles PBP-derived metrics; player_advanced_analytics.py handles NGS/PFR/QBR sources
- Mirrors the team_analytics.py pattern as a separate, focused module

### Rolling Windows
- Carried forward from Phase 15: shift(1) for lag, groupby([player_id, season])
- min_periods=3 (per success criteria #5) — requires meaningful history before producing values
- Column naming: `{metric}_roll3`, `{metric}_roll6` suffix — matches existing convention

### Claude's Discretion
- Exact NGS/PFR/QBR column selection and naming
- Player ID join logic details (fuzzy matching, name normalization)
- How to handle mid-season team changes for player matching
- NaN coverage logging format at write time
- Whether to include season-to-date (STD) expanding average alongside roll3/roll6

</decisions>

<specifics>
## Specific Ideas

- PFR pressure rate = (hits + hurries + sacks) / dropbacks — standard NFL analytics formula
- NGS WR/TE separation and catch probability are the signature NGS receiving metrics — use these as the core receiving profile
- QBR is QB-only — only produce QBR rolling columns for QB position rows
- NaN coverage should be logged at write time showing % of non-null values per advanced stat column — helps validate data quality without blocking

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `nfl_data_adapter.py:fetch_ngs()` — NGS fetch with stat_type (passing/rushing/receiving), seasons 2016+
- `nfl_data_adapter.py:fetch_pfr_weekly()` — PFR weekly with s_type (pass/rush/rec/def), seasons 2018+
- `nfl_data_adapter.py:fetch_qbr()` — ESPN QBR with frequency (weekly/season), seasons 2006+
- `team_analytics.py:apply_team_rolling()` — rolling window pattern with shift(1), groupby, min_periods; adapt for player-level
- `silver_team_transformation.py` — CLI pattern (argparse, local Bronze read, transform, local Silver write)
- `config.py:SILVER_PLAYER_S3_KEYS` — registration pattern for new Silver player datasets
- Bronze data exists locally: ngs/ (passing/receiving/rushing), pfr/ (weekly/seasonal), qbr/ (2006-2023)

### Established Patterns
- Local-first storage with optional S3 upload
- Timestamped filenames: `{dataset}_{YYYYMMDD_HHMMSS}.parquet`
- Season-partitioned directories
- `_read_local_bronze()` helper pattern from silver_team_transformation.py
- Wide format with descriptive column prefixes (off_/def_ for teams; ngs_/pfr_/qbr_ likely for player profiles)

### Integration Points
- Bronze NGS at `data/bronze/ngs/{passing,receiving,rushing}/season=YYYY/`
- Bronze PFR at `data/bronze/pfr/weekly/{pass,rush,rec,def}/season=YYYY/`
- Bronze QBR at `data/bronze/qbr/season=YYYY/`
- `config.py` — register new SILVER_PLAYER_S3_KEYS entry for 'advanced_profiles'
- Future Gold layer projection engine may consume advanced profiles for enhanced player evaluation

</code_context>

<deferred>
## Deferred Ideas

- Integrate advanced profiles into projection engine (Gold layer) — tracked as GOLD-01/GOLD-02 in REQUIREMENTS.md for v1.3+
- PFR seasonal aggregates as alternative to weekly rolling — could supplement weekly profiles
- NGS combine-style speed/burst metrics linked to profiles — related to Phase 18 (Historical Context)
- Positional matchup grades using advanced profiles (WR vs CB) — deferred to Neo4j Phase 5

</deferred>

---

*Phase: 17-advanced-player-profiles*
*Context gathered: 2026-03-14*
