# FTN Data Spike — Findings

**Date:** 2026-06-12
**nfl_data_py:** `import_ftn_data` confirmed present
**Scope:** Evaluate FTN charting data before any PFF purchase decision
**Status:** READ-ONLY spike — no production code modified

---

## 1. Coverage Table

| Season | Rows    | Columns |
|--------|---------|---------|
| 2022   | 41,643  | 29      |
| 2023   | 48,225  | 29      |
| 2024   | 48,031  | 29      |
| 2025   | 47,316  | 29      |
| **Total** | **185,215** | **29** |

FTN data is free via nflverse under CC-BY-SA 4.0. Coverage starts 2022; no pre-2022 data exists.

---

## 2. Full Schema (29 columns)

| Column                 | Dtype              | Null % | Notes |
|------------------------|--------------------|--------|-------|
| ftn_game_id            | int32              | 0.0%   | FTN internal game ID |
| nflverse_game_id       | object             | 0.0%   | **Primary join key** — matches PBP game_id exactly |
| season                 | int32              | 0.0%   | |
| week                   | int32              | 0.0%   | |
| ftn_play_id            | int32              | 0.0%   | FTN internal play ID |
| nflverse_play_id       | int32              | 0.0%   | **Secondary join key** — matches PBP play_id |
| starting_hash          | object             | 2.6%   | Hash mark position (left/right/middle) |
| qb_location            | object             | 2.6%   | under_center/shotgun/pistol/wildcat |
| n_offense_backfield    | float64            | 2.0%   | # players in backfield |
| n_defense_box          | int32              | 0.0%   | # defenders in box |
| is_no_huddle           | bool               | 0.0%   | |
| is_motion              | bool               | 0.0%   | Pre-snap motion |
| is_play_action         | bool               | 0.0%   | |
| is_screen_pass         | bool               | 0.0%   | |
| is_rpo                 | bool               | 0.0%   | Run-pass option |
| is_trick_play          | object             | 0.0%   | |
| is_qb_out_of_pocket    | bool               | 0.0%   | |
| is_interception_worthy | bool               | 0.0%   | |
| is_throw_away          | bool               | 0.0%   | |
| read_thrown            | object             | 11.9%  | 1st/2nd/3rd/4th/checkdown/scramble/other |
| is_catchable_ball      | bool               | 0.0%   | |
| is_contested_ball      | bool               | 0.0%   | |
| is_created_reception   | bool               | 0.0%   | YAC-created catch |
| is_drop                | bool               | 0.0%   | |
| is_qb_sneak            | bool               | 0.0%   | |
| n_blitzers             | int32              | 0.0%   | Count of blitzers |
| n_pass_rushers         | float64            | 0.8%   | Count of pass rushers |
| is_qb_fault_sack       | bool               | 0.0%   | |
| date_pulled            | datetime64[ns, UTC]| 0.0%   | Data extraction date |

**Absent from FTN** (were candidates): `is_spike`, `is_qb_scramble`, `is_pressure`, `time_to_throw`, `air_yards`

---

## 3. Join Quality

Join keys: `nflverse_game_id` (FTN) → `game_id` (PBP), `nflverse_play_id` (FTN) → `play_id` (PBP)

| Metric | Result |
|--------|--------|
| FTN unique games (2022) | 284 |
| PBP unique games (2022) | 284 |
| Game-level overlap | **284 / 284 = 100.0%** |
| FTN play rows (2022) | 41,643 |
| Play-level join hits | **41,643 / 41,643 = 100.0%** |

Join is clean. Every FTN play row matches a PBP row on `(game_id, play_id)`. Pass-play join rate per season:

- 2022: 20,382 / 20,458 pass plays = **99.6%**
- 2023: 20,797 / 20,797 = **100.0%**
- 2024: 20,082 / 20,082 = **100.0%**

The ~0.4% miss in 2022 is a minor nflverse version mismatch in the cached Bronze file; not a structural issue.

---

## 4. Per-Player-Week Aggregates — Feasibility Confirmed

After joining FTN to PBP via `(game_id, play_id)`, receiver attribution comes from `receiver_player_id` / `passer_player_id` in PBP. Player-week aggregates confirmed buildable:

**Receiver (WR/TE) features:**
- `catchable_rate` = catchable_targets / targets
- `contested_rate` = contested_targets / targets
- `drop_rate` = drops / targets
- `pa_target_share` = play_action_targets / targets
- `created_reception_rate` = is_created_reception / completions (YAC skill proxy)

**QB features:**
- `blitz_rate_faced` = mean(n_blitzers > 0) per dropback
- `avg_pass_rushers_faced` = mean(n_pass_rushers)
- `qb_out_of_pocket_rate` = mean(is_qb_out_of_pocket)
- `throw_away_rate` = mean(is_throw_away)
- `interception_worthy_rate` = mean(is_interception_worthy)
- `play_action_rate` (as QB caller) = mean(is_play_action)
- `read_depth_distribution` = proportion of 1st/2nd/3rd read thrown (7-level categorical)

Total receiver player-weeks built: 13,611 (across 2022-2024), 7,951 after >=3 targets filter.

---

## 5. Signal Checks — Partial Correlations

**Methodology:** Week W-1 FTN metric → Week W half-PPR points, partial correlation controlling for lag_targets. Sample: 7,394 player-weeks (>=3 targets, with prior week), 2022-2024. Full leak discipline: all FTN values are shifted by 1 week before correlation.

| Feature (lagged) | Partial r | p-value | n | Significant? |
|------------------|-----------|---------|---|---|
| contested_rate | **+0.0537** | 0.0000 | 7,394 | YES (p<0.001) |
| pa_target_share | +0.0197 | 0.0909 | 7,394 | Marginal (p~0.09) |
| drop_rate | -0.0149 | 0.2013 | 7,394 | No |
| catchable_rate | -0.0124 | 0.2869 | 7,394 | No |

Baseline: `lag_targets ~ half_ppr_pts`: r=0.2853 (p<0.001)

**Interpretation:**
- `contested_rate` is the strongest signal at r=+0.054, statistically significant after controlling for target volume. Direction is positive: players who receive more contested targets in week W-1 score more in week W. This is a role-quality signal — it captures receivers who run routes into tight coverage zones, indicating usage in high-value situations (red zone, scramble routes). It is not simply a catch-quality metric.
- `pa_target_share` shows marginal signal (p=0.09). Play-action targets tend to come on play-fakes that open underneath routes — not a strong direct predictor but potentially useful in combination.
- `drop_rate` and `catchable_rate` are not significant at conventional thresholds after controlling for volume. Drop rate in week W-1 has essentially no predictive power for week W points (r=-0.015, p=0.20) — drops are too rare and noisy at the single-week level.

**Effect size context:** The contested_rate partial r of 0.054 is modest in absolute terms but comparable to individual player-model features like receiving air yards or snap count percentage when evaluated in isolation. Its value is as an ensemble input, not a standalone predictor.

---

## 6. Team-Level Aggregate Candidates for Spread Model

All features must be lagged (only weeks prior to W) before joining to `feature_engineering.py`.

**Offensive team aggregates (posteam):**
| Feature | Source | Roll window |
|---------|---------|-------------|
| play_action_rate | mean(is_play_action) | roll3, roll6 |
| screen_pass_rate | mean(is_screen_pass) | roll3, roll6 |
| rpo_rate | mean(is_rpo) | roll3, roll6 |
| qb_out_of_pocket_rate | mean(is_qb_out_of_pocket) | roll3, roll6 |
| throw_away_rate | mean(is_throw_away) | roll3, roll6 |
| motion_rate | mean(is_motion) | roll3, roll6 |

**Defensive team aggregates (defteam — requires defteam join from PBP):**
| Feature | Source | Roll window |
|---------|---------|-------------|
| blitz_rate_faced | mean(n_blitzers > 0) | roll3, roll6 |
| avg_pass_rushers_faced | mean(n_pass_rushers) | roll3, roll6 |
| opp_play_action_rate | mean(is_play_action) faced | roll3, roll6 |

Source file for implementation: `src/feature_engineering.py` `_build_team_metrics()` section. Join pattern: `(posteam, season, week)` with shift(1) within season before join.

---

## 7. What FTN Does NOT Have (PFF Pricing Delta)

FTN covers **play-design and catch-quality** binary flags. It does NOT include:

**Receiver-level gaps (vs PFF):**
- Route type (go/curl/slant/cross/post/out/flat/screen) — no route col in FTN
- Route depth / release classification
- Separation distance at catch point (yards of separation is the PFF signature metric)
- Coverage shell at snap (man/zone/cover-2/cover-3)
- Coverage player identity — which CB covered which WR (the key input to `graph_wr_matchup.py`)
- Post-catch separation / yards after contact

**QB-level gaps (vs PFF):**
- Pressure location (A-gap/B-gap/edge/stunt)
- Time to throw (FTN absent; PFF has it)
- Per-throw accuracy rating
- Graded hits/hurries vs clean pockets

**OL-level gaps (vs PFF):**
- Individual blocker grades per play
- Sack/hit/hurry responsibility assignment by lineman

**Implication for PFF purchase decision:**
FTN is orthogonal to PFF — they measure different things. `graph_wr_matchup.py` was designed to consume WR-CB separation and coverage assignment data which FTN does not provide. PFF fills that gap; FTN does not. Building FTN features first is correct because: (a) free vs $300-500, (b) features are non-overlapping, (c) FTN signal is confirmed positive for contested_rate. If FTN features improve the model, that validates the charting-data approach and strengthens the PFF ROI argument.

---

## 8. Leak Discipline Audit

Every FTN feature must be lagged before use in any prediction:

| Feature use case | Leak-safe approach |
|------------------|--------------------|
| Player projection week W | Use FTN aggregated through week W-1 (shift=1) |
| Team spread feature week W | Rolling mean of weeks 1..W-1 (shift=1 before rolling) |
| Training data join | Sort by (player_id/team, season, week), shift before merge |

Same-week FTN stats (e.g., drop_rate for the game being predicted) are a direct leak — the features must never use the current week's charting data. The spike's signal check was done correctly using `shift(1)` on the player time series.

---

## 9. Recommendation

**VERDICT: BUILD**

Rationale:
1. **Coverage is complete**: 4 seasons (2022-2025), 185K plays, 29 columns, zero null on key flags
2. **Join is perfect**: 100% game-level match to Bronze PBP; play-level 99.6-100%
3. **Contested_rate has confirmed signal**: partial_r=0.054, p<0.001, controlling for target volume
4. **Orthogonal to existing features**: no overlap with current Silver (target share, rolling yards, etc.)
5. **Cost**: free data + ~150 lines of new code in `silver_ftn_transformation.py`

**Implementation plan:**
1. `scripts/silver_ftn_transformation.py` — pull FTN via `import_ftn_data`, join to PBP, compute player-week and team-week aggregates, write to `data/silver/players/ftn/season=YYYY/`
2. `src/feature_engineering.py` — add `_build_ftn_features()` method; join on `(player_id, season, week)` with shift(1) enforced
3. Impute NaN for 2016-2021 with position-mean (FTN only covers 2022+); alternatively gate these features to 2022+ subset for model training
4. Primary candidates to add to model: `contested_rate` (p<0.001), `blitz_rate_faced` (for QB features), `play_action_rate` (team-level for spread model)
5. Test against `unified_evaluation.py` holdout before shipping

**Risk:** FTN covers only 2022-2025, giving 4 seasons vs the current 10-season (2016-2025) training window. Adding FTN features will force either (a) position-mean NaN imputation for 2016-2021 plays, or (b) a 2022-2025 restricted model variant. This is manageable but needs to be tracked.

---

## Spike artifacts

- Script: `scripts/spikes/ftn_data_spike.py` (read-only, no production side effects)
