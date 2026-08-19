# ffopportunity Expected-Points Coverage (2026-08-18)

## Source

- Package: [ffverse/ffopportunity](https://github.com/ffverse/ffopportunity) — "Models and Data for Expected Fantasy Points." An xgboost model trained on nflverse play-by-play (2006-2020 training window) that scores every pass/rush play with expected-value outputs (completion probability, expected YAC, expected TD probability, etc.), independent of that play's actual outcome.
- Release: `latest-data` tag, assets `ep_pbp_pass_{season}.parquet` / `ep_pbp_rush_{season}.parquet` (one row per pass attempt / rush attempt, not pre-aggregated). Fetched via the authenticated `gh` CLI (`gh release download latest-data -R ffverse/ffopportunity ...`).
- **Licensing correction vs. the original task brief**: the task assumed GPL-3.0 for the data. The source README (`gh api repos/ffverse/ffopportunity/contents/README.md`) states the **R package code** is GPL-3.0, but the **model outputs / data** (what this ingestion consumes) are licensed **CC BY-SA 4.0** (https://creativecommons.org/licenses/by-sa/4.0/). This coverage doc + the ingestion script docstring serve as the attribution.

## Grain and join key

- Raw ep_pbp_pass/ep_pbp_rush: one row per play, keyed by `passer_player_id` / `receiver_player_id` / `rusher_player_id`.
- These are **gsis ids** in the same `00-00xxxxx` format nflverse/nfl-data-py uses everywhere else in this repo (verified empirically — e.g. Christian McCaffrey is `00-0033280` in both ffopportunity and nflverse). **Join key: `player_id` == `gsis_id`**, joins directly to `player_weekly`, `players/rosters`, and every other gsis-keyed Bronze/Silver table with no id-crosswalk needed.
- Silver output grain: one row per `(player_id, season, week)`. A player who both rushed and caught passes in the same week (e.g. a receiving back) gets **one merged row** with contributions summed from both roles — verified with 0 duplicate `(player_id, season, week)` keys across all 10 seasons.

## Aggregation logic (scripts/ingest_ffopportunity.py)

Raw columns are play-level flags stored as `category` dtype with `"0"`/`"1"` string labels (the same nflverse-adjacent gotcha as `snap_counts.offense_pct` / `player_weekly.receiving_air_yards` documented in `.claude/rules/nfl-data-conventions.md`) — cast to int before summing.

ffopportunity's `ep_pbp_pass` file has no single "expected passing/receiving yards" column (unlike the pre-built `ep_weekly` release asset, which this ingestion intentionally does NOT use — the task calls for building our own player-week aggregation from the play-level files so we control exactly which ~20 features land in Silver instead of carrying all 159 `ep_weekly` columns). We derive it as:

```
exp_yards_per_play = pass_completion_exp * (air_yards + yards_after_catch_exp)
```

i.e. completion probability × (fixed target depth + model's expected YAC). This is our own derivation, not an ffopportunity-native column — flagged here as a documented assumption.

Expected fantasy points use the **standard** (non-PPR) scoring constants from `src.config.SCORING_CONFIGS` (read-only import — yardage/TD/INT constants are identical across ppr/half_ppr/standard, so "standard" is just a stable source, not an endorsement of that format). No PPR reception bonus is baked into `exp_*_fantasy_points` — `receptions`/`targets` are exposed as raw counts so any downstream consumer can add their own league's reception credit.

## Feature column contract (20 feature columns + 5 keys = 25 total)

| Column | Meaning |
|---|---|
| `player_id`, `season`, `week`, `team`, `position` | Keys |
| `pass_attempts`, `targets`, `carries` | Opportunity counts |
| `completions`, `pass_yards`, `receptions`, `rec_yards`, `rush_yards`, `interceptions`, `total_tds` | Actual production |
| `exp_pass_yards`, `exp_rec_yards`, `exp_rush_yards`, `exp_total_tds` | Expected production (ffopportunity model outputs, aggregated) |
| `exp_pass_fantasy_points`, `exp_rec_fantasy_points`, `exp_rush_fantasy_points`, `exp_fantasy_points_total` | Expected fantasy points (standard scoring) |
| `actual_fantasy_points_total`, `fantasy_points_over_expected` | Actual fantasy points + actual-minus-expected residual (regression-candidate signal) |

Deliberately excluded from this minimal set: per-role TD/INT expected breakdowns beyond the combined `exp_total_tds` (folded together — position-specific breakdowns can be re-derived from the raw Bronze pbp files if a future gated experiment needs them), and the raw `ep_weekly` release's 159-column superset.

## Per-season coverage (2016-2025)

| Season | Pass rows | Rush rows | Player-weeks | Distinct players | Weeks | Null `player_id` |
|---|---|---|---|---|---|---|
| 2016 | 19,193 | 13,889 | 5,271 | 591 | 1-21 | 0 |
| 2017 | 18,396 | 14,342 | 5,309 | 581 | 1-21 | 0 |
| 2018 | 18,589 | 13,877 | 5,276 | 611 | 1-21 | 0 |
| 2019 | 18,642 | 14,029 | 5,248 | 607 | 1-21 | 0 |
| 2020 | 19,084 | 14,502 | 5,441 | 636 | 1-21 | 0 |
| 2021 | 19,769 | 15,164 | 5,688 | 653 | 1-22 | 0 |
| 2022 | 19,100 | 15,479 | 5,624 | 616 | 1-22 | 0 |
| 2023 | 19,333 | 15,331 | 5,643 | 589 | 1-22 | 0 |
| 2024 | 18,689 | 15,481 | 5,586 | 604 | 1-22 | 0 |
| 2025 | 18,463 | 15,345 | 5,631 | 608 | 1-22 | 0 |
| **Total** | **189,258** | **147,439** | **54,717** | — | — | **0** |

(Week range extends to 21-22 to cover playoffs; 2016-2019 max out at week 21 because the 17th regular-season week wasn't added until 2021.) `position` is null for ~0.2% of rows (trick plays / unusual snaps — 100 of 54,717) and non-null for every season except a handful with a low double-digit count; not treated as a data-quality blocker.

## Spot check: 2023 Christian McCaffrey, Week 4 (`player_id=00-0033280`)

```
season                            2023
week                                 4
team                                 SF
position                            RB
carries                             20
rush_yards                         106.0
exp_rush_yards                     76.78
targets                              8
receptions                           7
rec_yards                          71.0
exp_rec_yards                      44.60
total_tds                            4
exp_total_tds                      2.81
exp_rush_fantasy_points            20.82
exp_rec_fantasy_points              8.20
exp_fantasy_points_total           29.01
actual_fantasy_points_total        41.70
fantasy_points_over_expected       12.69
```

High-volume mid-season workload (20 carries + 8 targets) drives a high `exp_rush_fantasy_points` (20.82) on the strength of opportunity alone, well before accounting for his 4 total TDs that week — exactly the "opportunity, not outcome" signal this feature set exists to surface. Actual output (41.7 pts) beat expectation (29.0) by +12.7, mostly TD variance (`exp_total_tds`=2.81 vs. 4 actual).

## Size / licensing decision

- **Bronze (raw play-level pbp)**: `data/bronze/ffopportunity/season=YYYY/` — **43.5 MB** for 2016-2025 (20 files: 10× `ep_pbp_pass` ~2.5 MB + 10× `ep_pbp_rush` ~1.8 MB). Kept **LOCAL-ONLY** — the blanket `*.parquet` deny in `.gitignore` already blocks it and no allowlist entry was added. Rationale: although under the ~50 MB rule-of-thumb ceiling, it's sizable raw third-party data with no clear redistribution need (the small aggregated Silver derivative is the useful artifact downstream code actually reads), and per the task's own guidance ("if in doubt keep data local-only"). Re-fetch anytime via `python scripts/ingest_ffopportunity.py [--force-download]` — no API key required, `gh` CLI must be authenticated.
- **Silver (aggregated player-week features)**: `data/silver/ffopportunity_features/season=YYYY/` — **3.7 MB** total for 2016-2025. **COMMITTED** — small, well within the size of other committed Silver aggregates in this repo (e.g. `data/silver/players/advanced/` at ~7.3 MB), and this is a heavily-transformed derivative (10 files, one row per player-week, not a redistribution of the raw play-level data), consistent with CC BY-SA 4.0's share-alike terms (attributed here + in the script docstring).
- `.gitignore`: added a `data/silver/ffopportunity_features/**/*.parquet` allowlist block (with the size/licensing rationale inline); deliberately did NOT add one for `data/bronze/ffopportunity/`.

## Deviations from the task brief

1. **License**: brief said GPL-3.0; actual data license is CC BY-SA 4.0 (package code is GPL-3.0). Corrected above and in the script docstring.
2. **`exp_yards` derivation**: ffopportunity's play-level files don't expose a ready-made "expected yards" column (only the pre-built `ep_weekly` release asset does, which this ingestion intentionally bypasses per the task's instruction to build our own player-week aggregation). Derived as `pass_completion_exp * (air_yards + yards_after_catch_exp)` — documented as our own assumption, not an ffopportunity-native value.
3. Feature set landed at 20 feature columns (25 total incl. keys) rather than a stricter reading of "~10-20" — justified above by the three distinct player roles (passer/receiver/rusher) needing to coexist on one row.
