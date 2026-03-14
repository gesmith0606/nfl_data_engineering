# Project Research Summary

**Project:** NFL Data Engineering v1.2 Silver Layer Expansion
**Domain:** Sports data engineering — medallion architecture Silver layer extension with PBP-derived analytics
**Researched:** 2026-03-13
**Confidence:** HIGH

## Executive Summary

The v1.2 Silver expansion adds PBP-derived team metrics, rolling window analytics, strength of schedule, situational breakdowns, and advanced player profiles (NGS/PFR/QBR) to the existing medallion architecture. Research confirmed that zero new dependencies are required — pandas 1.5.3, numpy 1.26.4, scipy 1.13.1, and pyarrow 21.0.0 already cover every computation needed. All Bronze source data (PBP, NGS, PFR, QBR, combine, draft_picks) is confirmed locally available for the target 2016–2025 range. The recommended approach is to split the expansion across four new source modules (`team_analytics.py`, `advanced_player_analytics.py`, `historical_context.py`, `situational_analytics.py`) and two new CLI scripts, leaving `player_analytics.py` and the existing `players/usage/` Silver schema completely unchanged to protect the 71-test suite and downstream Gold consumers.

The highest-priority deliverable is the PBP team metrics pipeline: EPA/play, success rate, CPOE, red zone efficiency, pace, and pass rate over expected, all with 3-game and 6-game rolling windows. These feed directly into Gold matchup multiplier improvements and are prerequisites for strength-of-schedule computation. Strength of schedule must be built in the same CLI run as PBP team metrics because it depends on team EPA rankings. NGS/PFR/QBR advanced player profiles are additive P2 work that improves QB/RB/WR projections without modifying the current projection engine weights.

The single most critical risk is rolling window season-boundary contamination: the existing `compute_rolling_averages()` in `player_analytics.py` groups by `player_id` alone (not `(player_id, season)`), allowing Week 1 averages to silently incorporate the prior season's final weeks. This flaw must be fixed in `player_analytics.py` simultaneously with implementing team-level rolling windows, so the correction propagates consistently rather than requiring a retroactive patch. Two other must-address risks are playoff-week EPA contamination (filter `season_type == 'REG'` at every PBP read) and PBP memory management (aggregate to team-week grain before any cross-season operations; never load all 10 seasons simultaneously).

## Key Findings

### Recommended Stack

No new packages are needed. The entire Silver expansion is achievable with the existing venv. All patterns were directly verified by execution against pandas 1.5.3, numpy 1.26.4, and scipy 1.13.1 on 2026-03-13. The read-column-subset-first pattern (`pd.read_parquet(path, columns=[...])`) and the per-season processing loop (already in `silver_player_transformation.py`) are the two non-negotiable implementation constraints. Do not upgrade numpy (2.x breaks ABI with pandas 1.5.3); do not introduce polars (Python 3.9 incompatible).

**Core technologies:**
- **pandas 1.5.3**: Primary engine for all aggregation, rolling windows (`.rolling()`, `.expanding()`, `.ewm()`), and multi-table merges — all patterns verified by direct execution
- **numpy 1.26.4**: Weighted averages for SOS (`numpy.average(weights=...)`), float32 downcasting — no upgrade; numpy 2.x breaks ABI
- **scipy 1.13.1**: `rankdata()` for SOS percentile ranking (1–32) — already installed; `pandas.Series.rank(pct=True)` is an equivalent fallback
- **pyarrow 21.0.0**: Column-projection reads (`columns=` kwarg) reduce PBP in-memory size ~70%; already installed

See [STACK.md](./STACK.md) for full analysis including alternatives considered and version compatibility matrix.

### Expected Features

**Must have (P1 — table stakes for Gold game prediction model, feeds SLV-01 to SLV-03):**
- Team EPA/play (offense + defense, pass/rush splits) with 3-game and 6-game rolling windows
- Success rate by team (offense + defense) with rolling windows — standard EPA complement used in every public NFL prediction model
- Red zone efficiency (offense + defense) — most direct TD-count predictor; single highest-leverage projection improvement
- CPOE team aggregate per QB and team with rolling windows — differentiates QB quality from scheme
- Pass Rate Over Expected (PROE) per team — quantifies run-heavy vs pass-heavy scheme; critical for RB/WR share projections
- Pace (plays per game) per team — total volume predictor; affects all position projections multiplicatively
- Strength of Schedule (opponent-adjusted EPA, ranks 1–32) — normalizes team rankings; must be computed in same run as team EPA
- Situational tags (home/away, divisional, game script) as standalone Silver table — promotes existing inline logic

**Should have (P2 — competitive differentiators, add after P1 backtest validation):**
- NGS player profiles: WR/TE separation + catch probability, QB time-to-throw + aggressiveness, RB RYOE
- PFR pressure rate (QB) and blitz rate (team defense) with rolling windows
- QBR rolling windows (low-effort once NGS passing pipeline is built)
- 4th down aggressiveness index with rolling windows

**Defer to v1.3+ (P3):**
- Combine measurables + draft capital linked to players — high join complexity (name-based cross-reference required); outputs are static; defer until rookie breakout modeling is an explicit Gold target
- EWMA rolling windows — add only if backtesting shows EWMA outperforms fixed 3/6-game windows
- Forward-looking SOS (schedule-remaining) — different use case from current backward-looking SOS

**Explicit anti-features (confirmed by research — never build):**
- Play-level Silver copy of Bronze PBP — adds zero transformation value; query Bronze PBP directly via DuckDB
- WPA team rolling aggregates — WPA sums to near-zero per game; EPA is the correct aggregation unit
- Real-time within-game metrics — out of scope for batch Parquet pipeline; weekly batch is the correct granularity
- NGS before 2016 — tracking chips not deployed; nfl-data-py returns empty or raises errors

See [FEATURES.md](./FEATURES.md) for full feature landscape, dependency graph, and MVP definition.

### Architecture Approach

The expansion follows a clean module-per-domain separation anchored by four new `src/` modules and two new CLI scripts. The existing `player_analytics.py` and `silver_player_transformation.py` are untouched, preserving the 71-test suite and the 113-column `players/usage/` Silver schema that `projection_engine.py` reads. New Silver tables live at separate paths (`data/silver/teams/`, `data/silver/players/advanced/`, `data/silver/situational/`) and are consumed by Gold via explicit left-joins. Every new Silver output must be registered in `config.py::SILVER_PLAYER_S3_KEYS` and verified via `download_latest_parquet()` before shipping.

**Major components:**
1. **`src/team_analytics.py`** (NEW) — `compute_pbp_team_metrics()`, `compute_team_tendencies()`, `compute_sos()`; operates at team-week grain from PBP Bronze; writes `teams/pbp_metrics/`, `teams/tendencies/`, `teams/sos/`
2. **`src/advanced_player_analytics.py`** (NEW) — `compute_ngs_profiles()`, `compute_pfr_profiles()`, `compute_qbr_features()`; always left-joins from player_weekly base to avoid silently dropping players without advanced stats; writes `players/advanced/`
3. **`src/historical_context.py`** (NEW) — `compute_draft_capital()`, `link_combine_to_roster()`; outputs a static dimension table at `players/historical/` (no season partition); never joined to weekly Silver fact table
4. **`src/situational_analytics.py`** (NEW) — promotes existing inline `compute_game_script_indicators()` and `compute_venue_splits()` logic to standalone Silver output at `situational/splits/`
5. **`scripts/silver_team_transformation.py`** (NEW CLI) — orchestrates PBP team metrics → SOS → situational; processes one season at a time
6. **`scripts/silver_advanced_transformation.py`** (NEW CLI) — orchestrates NGS/PFR/QBR + historical context; separate from team CLI for independent execution

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full component map, data flow diagrams, anti-patterns, and build order.

### Critical Pitfalls

1. **Rolling windows bleed across season boundaries** — Group by `(player_id, season)` not `player_id` alone; this bug exists in current `player_analytics.py` lines 210–215 and must be fixed; assert Week 1 roll3 values are NaN in tests
2. **Playoff weeks contaminate regular-season team metrics** — Apply `pbp_df[pbp_df['season_type'] == 'REG']` at every PBP read; `week <= 18` filter alone is insufficient for edge cases; verify max week in Silver team-metrics is 18
3. **PBP loads OOM on multi-season backfills** — Column-subset at read time (`pd.read_parquet(path, columns=[...])`); aggregate 50K plays to ~512 team-week rows before any cross-season operations; process one season at a time
4. **Circular dependency in rolling SOS** — Compute opponent quality using lagged (week N-1) EPA values only; assert Week 1 adjusted EPA equals raw EPA; run idempotency test (two transforms on same input must produce identical output); recovery cost is HIGH
5. **NGS/PFR/QBR silent NaN columns in rolling averages** — Log NaN coverage at Silver write time for all sparse metrics; use `min_periods=3` (not 1) for NGS/PFR rolling to require meaningful history before producing an average
6. **New Silver tables bypass path convention** — Register every new Silver output in `config.py::SILVER_PLAYER_S3_KEYS` before writing first file; verify via `download_latest_parquet()` before shipping
7. **Combine/draft join causes row explosion** — Store combine/draft as a player dimension table (one row per player, no season partition); never join to weekly Silver fact table; assert row count unchanged after join

See [PITFALLS.md](./PITFALLS.md) for all 7 pitfalls with full recovery strategies, warning signs, and a phase-to-pitfall mapping.

## Implications for Roadmap

Based on the dependency graph in FEATURES.md and the build order in ARCHITECTURE.md, a four-phase approach is recommended (plus a deferred P3 phase for historical context). The ordering is driven by hard dependencies (SOS requires team EPA; advanced profiles require player_id cross-reference tables), risk isolation (each phase is independently testable), and the principle that P1 features ship with backtest validation gates before P2 work begins.

### Phase 1: PBP Team Metrics Foundation

**Rationale:** All P1 features depend on PBP aggregation being available; SOS depends on team EPA; this phase contains the hardest correctness problems (OOM risk, playoff contamination, season-boundary rolling bleed) and must be solved first. Fixing the existing rolling window season-boundary bug in `player_analytics.py` simultaneously prevents the flaw from propagating into every subsequent phase.
**Delivers:** `team_analytics.py` module + `silver_team_transformation.py` CLI; Silver outputs for `teams/pbp_metrics/` (EPA/play, success rate, CPOE, red zone efficiency, pace, PROE) with rolling windows (3-game, 6-game, season-to-date) for seasons 2016–2025; bug fix to rolling window groupby in `player_analytics.py`
**Addresses:** Team EPA per play, success rate, CPOE, red zone efficiency, pace, PROE (all P1 from FEATURES.md)
**Avoids:** PBP OOM pitfall (column subsetting + per-season loop), playoff contamination pitfall (`season_type == 'REG'` filter), rolling season-boundary bleed pitfall (fix groupby key to `(player_id, season)`)

### Phase 2: Strength of Schedule

**Rationale:** Hard dependency on Phase 1 team EPA outputs; SOS is the highest-complexity P1 feature (circular dependency risk) and benefits from isolation in its own phase so the lagged computation pattern can be thoroughly tested before Gold consumes it.
**Delivers:** `compute_sos()` in `team_analytics.py`; Silver output at `teams/sos/season=YYYY/`; idempotency tests; regression test for Week 1 adj_EPA == raw_EPA
**Addresses:** Strength of Schedule P1 feature; feeds updated Gold matchup multiplier (replaces simple rank-based opponent ranking)
**Avoids:** Circular SOS dependency pitfall (lagged opponent quality, idempotency tests); recovery cost is HIGH if baked into Gold without validation

### Phase 3: Situational Splits

**Rationale:** Low-complexity promotion of already-implemented logic; independent of PBP outputs; depends only on schedules Bronze (2020–2025 available locally) and existing Silver usage table. Establishes the standalone Silver table pattern before the more complex Phase 4 work.
**Delivers:** `situational_analytics.py` module; Silver output at `situational/splits/season=YYYY/`; home/away, divisional, and game-script tags with rolling splits; registered in `config.py` and verified via `download_latest_parquet()`
**Addresses:** Situational tags P1 feature; promotes existing inline Silver logic to a proper, registered output
**Avoids:** Silver path convention bypass pitfall (register in config.py before first write)

### Phase 4: Advanced Player Profiles (NGS/PFR/QBR)

**Rationale:** P2 work gated on P1–P2 backtest validation showing team EPA rolling windows improve Gold MAE; NGS/PFR/QBR sparse-join and NaN-coverage pitfalls are solved in isolation without risking the team metrics pipeline; requires player_id cross-reference from existing usage Silver table
**Delivers:** `advanced_player_analytics.py` module + `silver_advanced_transformation.py` CLI; Silver output at `players/advanced/season=YYYY/`; NGS separation/RYOE/TTT, PFR pressure/blitz, QBR rolling windows per player-week; NaN coverage logging; `min_periods=3` on sparse columns
**Addresses:** NGS player profiles, PFR pressure/blitz, QBR rolling windows (all P2 from FEATURES.md)
**Avoids:** NGS/PFR silent NaN pitfall (coverage logging + `min_periods=3`), inner-join player drop anti-pattern (always left-join from player_weekly)

### Deferred: Historical Context (P3)

**Rationale:** Combine + draft capital join is the highest-risk join in the project (name-based cross-reference for pre-2016 data, ~30–40% UFDA NaN rate, row explosion risk); outputs are static (not weekly); defer until rookie breakout modeling is an explicit Gold target
**Delivers:** `historical_context.py` module; static `players/historical/combine_draft_profiles.parquet`; one row per player; annual refresh at draft time
**Addresses:** Combine measurables + draft capital P3 feature from FEATURES.md
**Avoids:** Combine/draft row explosion pitfall (dimension table pattern, row count assertion after join)

### Phase Ordering Rationale

- **Team metrics before SOS**: Hard data dependency — SOS is computed from team EPA rankings computed in Phase 1; both can run in the same CLI but team EPA must complete first
- **Fix rolling window bug in Phase 1**: The groupby season-boundary bug in `player_analytics.py` affects backtesting accuracy across all seasons; fixing in Phase 1 prevents all subsequent phases from being built on contaminated Silver rolling averages
- **Phases 1–3 before Phase 4**: Backtest gate — run `backtest_projections.py` after Phases 1–3 to confirm MAE improvement before investing in NGS/PFR/QBR profiles (P2 only justified by demonstrated P1 improvement)
- **Historical context deferred**: Name-based cross-reference for pre-2016 draft picks has ~20% unlinked player rate; static output provides low weekly ROI compared to P1/P2 improvements
- **Each phase is independently testable**: New modules have no cross-dependencies; each can be built and tested in isolation before the next phase begins

### Research Flags

Phases with well-documented patterns (standard — skip additional research during planning):
- **Phase 1 (PBP Team Metrics)**: pandas groupby/agg patterns fully verified by direct execution; PBP schema confirmed; working code snippets in ARCHITECTURE.md and STACK.md
- **Phase 3 (Situational Splits)**: Logic already exists in `player_analytics.py`; this is a refactor to a standalone table, not new research

Phases that benefit from deeper research during planning:
- **Phase 2 (SOS)**: The lagged opponent-quality computation and idempotency testing approach should be designed carefully before implementation; recovery cost is HIGH if circular dependency bakes into Gold
- **Phase 4 (Advanced Player Profiles)**: PFR player ID cross-reference via `draft_picks` (pfr_player_id → gsis_id) should be validated against actual data before implementation; NGS position-filter coverage rates need measurement to set realistic `min_periods` thresholds

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All patterns executed against actual venv on 2026-03-13; zero new dependencies confirmed; memory profiles measured against real data |
| Features | HIGH | Feature scope derived from `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` (SLV-01 to SLV-03) and Bronze schema inventory; Bronze data availability confirmed from local filesystem |
| Architecture | HIGH | Based on direct inspection of all Bronze schemas, existing Silver module source, projection engine consumption patterns, and confirmed column counts |
| Pitfalls | HIGH | Grounded in codebase analysis (rolling window bug confirmed at specific lines in `player_analytics.py`); all pitfalls tied to specific code patterns or confirmed data characteristics |

**Overall confidence:** HIGH

### Gaps to Address

- **SOS lagged computation validation**: The specific implementation of rolling opponent quality using lagged EPA values should be prototyped and validated (Week 1 adj_EPA == raw_EPA assertion) before the full SOS phase ships. Recovery cost is HIGH if circular dependency is baked into Gold.
- **PFR player ID coverage rate**: The `pfr_player_id → gsis_id` cross-reference via `draft_picks` should be measured against actual 2024 player_weekly data before Phase 4 begins. The expected ~80% match rate needs empirical confirmation.
- **NGS weekly qualification thresholds**: The minimum-target or minimum-play count that qualifies a player for a weekly NGS record needs confirmation from Bronze data inspection. This determines realistic NaN rates and appropriate `min_periods` settings for Phase 4.
- **Schedules backfill (2016–2019)**: Situational tags currently have Bronze schedules only for 2020–2025. If Phase 3 needs to cover the full 2016–2025 PBP range, a Bronze schedules backfill must precede Phase 3 execution. For v1.2 launch, 2020–2025 coverage is sufficient and acceptable.
- **Gold projection engine hooks**: The two identified hooks in `projection_engine.py` (SOS-adjusted matchup multiplier, NGS-supplemented usage multiplier) are stretch goals post-v1.2 Silver, not Phase 1–4 blockers. Integration points should be confirmed during Phase 2 and Phase 4 planning respectively.

## Sources

### Primary (HIGH confidence)
- `src/player_analytics.py` — confirmed rolling window groupby gap (lines 210–215 vs season-scoped std line 219); existing module patterns and function signatures
- `data/bronze/pbp/season=2024/*.parquet` — confirmed 103 cols, 49,492 plays per season, EPA/WPA/CPOE/success present
- `data/silver/players/usage/season=2024/*.parquet` — confirmed 113-column schema consumed by `projection_engine.py`
- Local venv execution 2026-03-13 — all pandas/numpy/scipy patterns verified against actual installed versions (pandas 1.5.3, numpy 1.26.4, scipy 1.13.1)
- `docs/NFL_GAME_PREDICTION_DATA_MODEL.md` — Silver layer planned schema (SLV-01 to SLV-03), feature categories, out-of-scope decisions
- `docs/NFL_DATA_DICTIONARY.md` — PBP 103-column schema, NGS schemas (29/23/22 cols), PFR schemas, QBR schema (30 cols)
- `data/bronze/ngs/*/season=2024/*.parquet` — confirmed column sets for passing, receiving, rushing
- `data/bronze/pfr/weekly/def/season=2024/*.parquet` — confirmed 29 cols (pressure, blitz, coverage)
- `data/bronze/combine/season=2024/*.parquet` — confirmed 18 cols including forty, wt, ht, pfr_id
- `data/bronze/draft_picks/season=2024/*.parquet` — confirmed 36 cols including gsis_id, pfr_player_id, round, pick, w_av

### Secondary (MEDIUM confidence)
- [pandas 1.5 window operations docs](https://pandas.pydata.org/pandas-docs/version/1.5/user_guide/window.html) — rolling, expanding, ewm confirmed in 1.5 series
- [nflfastR team aggregation patterns](https://nflfastr.com/articles/nflfastR.html) — standard EPA/play, success_rate, CPOE approach (R patterns translated to pandas)
- [scipy.stats.rankdata docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.rankdata.html) — used for SOS percentile ranking
- `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` — Phase 2 PBP memory-safe batching decision; team abbreviation change crosswalk (OAK→LV, SD→LAC)

### Tertiary (LOW confidence)
- NGS minimum qualification thresholds — inferred from "only targeted players appear" pattern; exact weekly minimums need empirical measurement from Bronze data
- PFR player ID match rate — estimated ~80%; needs measurement against actual `draft_picks` × `player_weekly` join before Phase 4 implementation

---
*Research completed: 2026-03-13*
*Ready for roadmap: yes*
