# Draft-Time ADP Early-Season Gate — `--adp-prior` (2026-08-18)

Pre-registered BEFORE running any backtest results. Implements + gate-
evaluates the draft-time-ADP hypothesis: crowd-consensus ADP (Fantasy
Football Calculator, late-Aug/early-Sept snapshot — strictly before week 1)
improves EARLY-SEASON projections (weeks 1-6), where our model is
historically weakest, because trailing-usage features are thin/absent then
and prior-season PPG mispredicts players with changed roles (rookies, team
changes, promoted starters) — exactly the players the drafting crowd prices
in.

Closest precedent lever: `--early-season-prior`
(`.planning/EARLY_SEASON_PRIOR_GATE.md`) — HOLD, deconfounded weeks 3-6 MAE
gap improvement 0.053 (bar 0.10) / ordinal gap improvement 0.037 (bar 0.05).
This gate mirrors its structure, bars, and eval method exactly, extended to
weeks 1-6 and a different signal source.

## Data — new today

`data/adp/history/adp_ffc_{format}_{year}.csv` for `format` in
`{ppr, half_ppr, standard}`, `year` in `{2021..2025}` — FFC's public API,
snapshot_date late Aug/early Sept each year (strictly pre-week-1, so usable
for every in-season week of that season with zero leakage). Columns:
`season, snapshot_date, source, format, player_name, team, position, adp,
high, low, stdev, times_drafted`. `data/adp/history/adp_mfl_season_aggregate_{year}.csv`
also exists (MFL, full-draft-season aggregate) — robustness check only per
the leakage note below, not the primary source.

**Leakage**: FFC snapshot_date is late Aug/early Sept — strictly before
week 1 of that season — so it is valid pre-game information for every week
of the season it was drafted for. MFL's `PERIOD=ALL` aggregates the entire
draft season (including in-season redraft/dynasty startup drafts that occur
after week 1 in some formats) — noisier and a weaker leak-free guarantee,
used only as a cross-check if at all, never as the primary lever input.

## Lever implemented

`proj' = (1-w)*proj + w*adp_implied_ppg` for weeks 1-6 only (no-op
elsewhere), where:

- `adp_implied_ppg` = a per-position log10(ADP) -> realized-season-PPG
  linear mapping (`numpy.polyfit`, degree 1), applied to the CURRENT
  season's ADP snapshot. The mapping is fit **walk-forward on prior seasons
  only**: season S's mapping pools (ADP, realized full-season PPG) pairs
  from every season `2021 <= y < S` that has both a committed ADP snapshot
  and Bronze weekly data — e.g. 2021 ADP + 2021 realized PPG informs 2022's
  mapping; 2021+2022 inform 2023's; 2021+2022+2023 inform 2024's;
  2021-2024 inform the sealed-2025 mapping. Never same-season.
- Realized-season-PPG training labels are gated on >=6 games played in that
  training season (mirrors `early_season_prior.MIN_PRIOR_GAMES` — same bar,
  same rationale: below this the season average is noisier than useful).
- A position's mapping is only fit if the training pool has >=5 pooled
  rows after the games-played gate and the ADP/realized-PPG name join;
  otherwise that position is a structural no-op for the eval season.
- `w = scale * schedule[week]`, fixed decaying schedule
  `{1: 0.5, 2: 0.45, 3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}` — heavier than
  `--early-season-prior`'s weeks-3-6-only schedule because weeks 1-2 have
  ZERO current-season signal (vs. `--early-season-prior`, which starts at
  week 3 because weeks 1-2 lack the "2 weeks of history" the backtest
  harness requires for its own rolling features — the ADP lever has no such
  requirement since it doesn't depend on current-season history at all).
  `scale` defaults to 1.0.
- Applies to QB/RB/WR/TE only. Implied PPG is floored at 0.

**Join**: ADP snapshots carry no `player_id` (FFC exposes name/team/
position only), so the join is `(sleeper_player_map.normalize_name(name),
position)` — the same hardened name-join helper already used by
`src/adp_sources.py` for ADP joins and by the live-draft pick-matching code
(`map_picks_to_projections`), NOT a raw name string. Per the coverage-check
rule ("never join on name alone"), position is part of the key so two
different-position players sharing a normalized name don't collide.

**New module**: `src/adp_prior.py` — `load_adp_snapshot()`,
`compute_realized_season_ppg()`, `fit_adp_ppg_mapping()`,
`compute_adp_implied_ppg()`, `apply_adp_prior()`, mirroring the
`early_season_prior.py` compute/apply pattern.

**Wiring** (opt-in, mirrors `--early-season-prior`):
- `scripts/generate_projections.py --adp-prior` / `--adp-prior-weight`
  (weekly mode only; applied after the early-season-prior blend, before
  the QB starter floor — a role/usage correction, not a news/market
  signal).
- `scripts/backtest_projections.py --adp-prior` / `--adp-prior-weight` —
  threads the lever into `run_backtest()`, with a per-eval-season mapping
  cache built once before the week loop (walk-forward training seasons
  loaded from Bronze weekly data independent of the season the harness
  would otherwise load, since a sealed single-season run needs 2021+
  training history the harness's own `season ∪ {season-1}` window doesn't
  cover).

## Pre-registered gate

**Coverage/firing rate is reported BEFORE any MAE/ordinal numbers below**
(per `knowledge-vault/concepts/gated-experiment-coverage-check.md`): % of
projected QB/RB/WR/TE player-weeks in weeks 1-6 with a non-null
`adp_implied_ppg`, by position and season, plus a changed-rows count
(before-vs-after `projected_points` diff != 0) per season. If any
position's coverage is <60%, that is flagged explicitly and the aggregate
verdict is read with that caveat — a silent join failure must not produce a
vacuous SHIP or HOLD.

**Gates** (same bars as `--early-season-prior`):
- **PRIMARY (MAE)**: weeks 1-6 matched-pair MAE gap vs Sleeper improves by
  >=0.10 pts overall, **OR** per-position (mirrors the precedent's "overall
  or per-position" scoping-rule corollary — per-position wins are not
  discarded just because the overall composite misses, since positions
  train/fit independently here just as in the 2026-08-16 consolidation
  re-gate).
- **SECONDARY (ordinal)**: weeks 1-6 (or nearest supported window, 1-17)
  FantasyPros-style Accuracy Gap vs Sleeper improves by >=0.05 overall.
- **Guard**: full-season (weeks 1-18, or 7-18 as the non-overlapping
  control) overall gap does not worsen by >0.02, and no position's
  full-season gap worsens by >0.05. Weeks 7-18 must be BYTE-IDENTICAL
  between baseline and treated (proof the lever is correctly scoped to
  weeks 1-6 only, no leakage) — same invariant check the early-season-prior
  gate used to catch its 2021-data confound.
- **Deconfounded slices** (coverage-check rule): report weeks-1-6 MAE gap
  split into (a) rows where the lever actually fired (`adp_implied_ppg`
  notna) vs all rows, and (b) a cheap rookie/team-change proxy — players
  with zero prior-season (S-1) games in Bronze weekly history — vs
  established players, since that subgroup is exactly who the hypothesis
  targets.

**Walk-forward**: 2022-2024 (mapping trained on whatever of 2021-2023 is
available before each eval season). **Sealed confirm**: 2025, run ONCE at
the end, mapping trained on 2021-2024, no iterating on the result.

**Baseline discipline**: per the early-season-prior gate's hard-won lesson
(0.098-pt confound from a stale pre-ingestion baseline), baseline and
treated backtests are generated back-to-back in the SAME session, on the
SAME data vintage, no reused CSVs from prior runs.

**Verdict rule**: SHIP if the primary gate clears walk-forward AND holds
direction (same sign, doesn't need to clear the bar) on sealed 2025 AND the
full-season guard passes. HOLD otherwise. Either way `--adp-prior` ships as
inert, evaluable, opt-in machinery (repo pattern) — this doc's verdict only
gates the DEFAULT, never removes the flag.

## Protocol amendment slot

If the log(ADP)->PPG mapping approach proves unworkable (e.g., too little
training signal, degenerate fits), the fallback is a single simpler
variant: use ADP RANK directly as a feature in the blend weight (e.g.
`w = base_w * (1 - normalized_adp_rank)`, no fitted mapping at all) instead
of a regression-derived implied-PPG target. Any such change will be
documented here as a dated amendment BEFORE running on sealed 2025 data —
not applied silently.

---

## Results

### 0. Bug caught mid-run: the first implementation was a silent no-op

The first `--adp-prior` implementation joined ADP's full names ("Tom
Brady") against `player_id`-blind name keys derived from Bronze
`players/weekly`'s `player_name` column — which is ABBREVIATED (e.g.
`"T.Brady"`; see `backtest_projections.compute_actuals`'s own docstring for
the same fact). 0% of training rows joined, `fit_adp_ppg_mapping` returned
`{}` for every season, and the treated walk-forward CSV came back
**byte-identical** to the baseline CSV. Caught via the coverage-check
discipline (diffed treated vs baseline before reading any MAE numbers).
Fixed by resolving ADP's full names to `player_id` via a
(name, position) -> `player_id` crosswalk built from Bronze
`players/rosters` (full names + `player_id`, and — unlike weekly — covers
players before their season debut, so rookies resolve). Every downstream
join in the module is now by `player_id`, never by name. See
`src/adp_prior.py`'s module docstring for the full account. All numbers
below are from the FIXED implementation (tests: 32/32 passing).

### 1. Coverage / firing rate (BEFORE any MAE numbers, per pre-registration)

"Fired" = `adp_implied_ppg` notna, weeks 1-6, QB/RB/WR/TE.

**Walk-forward (2022-2024):**

| Season | QB | RB | WR | TE | Season total |
|---|---|---|---|---|---|
| 2022 | 65/159 (40.9%) | 189/332 (56.9%) | 179/505 (35.4%) | 47/223 (21.1%) | **480/1219 (39.4%)** |
| 2023 | 97/153 (63.4%) | 200/305 (65.6%) | 262/518 (50.6%) | 86/225 (38.2%) | **645/1201 (53.7%)** |
| 2024 | 96/149 (64.4%) | 187/313 (59.7%) | 246/476 (51.7%) | 59/205 (28.8%) | **588/1143 (51.4%)** |

**Sealed 2025:** QB 74/145 (51.0%), RB 189/381 (49.6%), WR 231/600 (38.5%),
TE 55/268 (20.5%) — **549/1394 (39.4%)** total, same shape as 2022.

**Coverage flag (as pre-registered — <60% triggers a flag):** TE is below
60% in **every** season (20.5-38.2%) and WR is below 60% in every season
(35.4-51.7%); QB and RB clear 60% only in 2023/2024, not 2022 or 2025. This
is a real, structural ceiling, not a join bug: FFC's ADP snapshot only
covers the ~120-160 most commonly drafted players — a mid-round rookie or a
backup who wasn't preseason-relevant simply isn't in the file, independent
of whether the name-join works. The aggregate MAE-gap numbers below reflect
a lever that reaches under half the target population, most acutely at TE.

**Changed-rows proof-of-firing** (weeks 1-6, `projected_points` diff != 0):
2022: 479/1219, 2023: 641/1201, 2024: 586/1143, sealed 2025: 547/1394 — all
closely track the coverage numbers above.

### 2. Primary gate — weeks 1-6 matched-pair MAE vs Sleeper/ESPN

`gap = our_mae - source_mae`; Delta = treated - baseline (negative =
improvement). Baseline and treated generated back-to-back in this session
on identical data (no reused CSVs).

**Walk-forward (2022-2024), weeks 1-6 (target):**

| Position | n | vs Sleeper base | vs Sleeper treated | Delta | vs ESPN base | vs ESPN treated | Delta |
|---|---|---:|---:|---:|---:|---:|---:|
| QB | 443/424 | -1.775 | -1.665 | **+0.110** (worse) | -0.887 | -0.772 | **+0.116** (worse) |
| RB | 670/633 | -0.296 | -0.325 | -0.029 | -0.297 | -0.333 | -0.036 |
| WR | 1048/981 | +0.173 | +0.094 | **-0.079** | +0.166 | +0.094 | -0.072 |
| TE | 323/324 | -0.242 | -0.256 | -0.014 | -0.214 | -0.254 | -0.040 |
| **OVERALL** | 2484/2362 | **-0.355** | **-0.378** | **-0.023** | **-0.199** | **-0.224** | **-0.025** |

**Gate check (walk-forward):** overall improvement required >=0.10 —
measured **0.023** (23% of bar) vs Sleeper, 0.025 vs ESPN. **Per-position**:
best is WR at **-0.079** (79% of bar) — closest, still short. QB moves the
WRONG direction on both sources (+0.110/+0.116) — the raw log(ADP) mapping
is too blunt for QB, the same failure mode `--early-season-prior` found
(concentrated backup/committee situations don't fit a smooth ADP curve).
**No position clears the 0.10 bar. FAILS the primary gate.**

**Sealed 2025, weeks 1-6 (Sleeper only — ESPN Silver has no 2025 external
projections committed):**

| Position | n | base | treated | Delta |
|---|---|---:|---:|---:|
| QB | 142 | -0.427 | -0.408 | +0.018 (worse, small) |
| RB | 228 | +0.117 | -0.009 | **-0.126** |
| WR | 320 | +0.034 | -0.031 | -0.064 |
| TE | 117 | -0.103 | -0.163 | -0.061 |
| **OVERALL** | 807 | **-0.044** | **-0.110** | **-0.067** |

**Gate check (sealed):** overall improvement 0.067 (67% of bar) — closer
than walk-forward but still short. RB alone clears the 0.10 per-position
bar on sealed 2025 (-0.126) — but RB did NOT clear walk-forward (-0.029,
29% of bar), so this is a magnitude inconsistency across the two runs, not
a confirmed per-position win (the pre-registered SHIP rule requires
clearing walk-forward, not just holding direction).

### 3. Guard — weeks 7-18 invariant + full-season regression

**Weeks 7-18** (outside the lever's scope; any nonzero Delta here would be
a scoping bug): **exactly 0.000** for every position, both sources, both
walk-forward and sealed 2025. Confirms the blend is correctly restricted to
weeks 1-6 with zero leakage — the same invariant check that caught the
`--early-season-prior` 2021-data confound.

**Weeks 1-18 (full-season guard), walk-forward vs Sleeper:** QB +0.036,
RB -0.010, WR -0.026, TE -0.005, **OVERALL -0.008** (within +/-0.02, no
position worsens >0.05). vs ESPN: OVERALL -0.008, max position +0.038
(QB) — passes.

**Weeks 1-18, sealed 2025 vs Sleeper:** QB +0.006, RB -0.039, WR -0.020,
TE -0.017, **OVERALL -0.021** (inside +/-0.02, no position worsens >0.05) —
passes.

**Guard verdict: PASSES on both runs.**

### 4. Secondary gate — ordinal (FantasyPros-style Accuracy Gap)

`scripts/simulate_fp_accuracy.py` hardcodes its evaluation window to
seasons (2022, 2023, 2024) / weeks 3-17 (shared machinery, not modified for
this gate) — so this metric is walk-forward-only; there is no sealed-2025
ordinal read. Reused as-is (staged the two backtest CSVs under isolated
`--output-dir`s so the script's own file-discovery glob resolves correctly
— no logic changes).

Overall (QB+RB+WR+TE mean) FantasyPros-style Accuracy Gap vs Sleeper, weeks
3-17, 2022-2024 pooled:

| Position | Base gap | Treated gap | Delta |
|---|---:|---:|---:|
| QB | -1.75 | -1.70 | **+0.05** (worse) |
| RB | -0.60 | -0.58 | +0.02 (worse) |
| TE | -0.42 | -0.42 | 0.00 |
| WR | +0.19 | +0.15 | **-0.04** |
| **OVERALL (mean)** | **-0.645** | **-0.6375** | **+0.0075** (worse) |

**Gate check:** required >=0.05 improvement (negative Delta) — measured
**+0.0075**, essentially flat and in the WRONG direction. **FAILS the
secondary gate**, more decisively than the primary MAE gate.

### 5. Deconfounded slices (coverage-check rule)

**Fired vs not-fired rows** (weeks 1-6, treated, MAE against actuals —
descriptive population characterization, NOT a treated-vs-baseline
comparison): walk-forward FIRED n=1713 MAE=5.002 vs NOT-FIRED n=1850
MAE=3.692; sealed 2025 FIRED n=549 MAE=5.134 vs NOT-FIRED n=845 MAE=3.430.
Fired rows are harder to project in both runs — expected, since a player
appearing in ADP is by definition draft-relevant (higher, more volatile
opportunity) while non-fired rows skew toward low-variance bench/waiver
players. This is population shape, not a lever effect.

**Rookie/changed-role proxy** (cheap: `player_id` has <6 games in Bronze
weekly for season S-1 -> "new/changed role", computed post-hoc via
`early_season_prior.compute_prior_season_ppg`, not shipped in the lever):

| Run | Subgroup | n | our MAE | ADP-prior firing rate |
|---|---|---|---:|---:|
| Walk-forward | NEW/CHANGED-ROLE | 733 | 4.183 | **28.8%** |
| Walk-forward | ESTABLISHED | 2830 | 4.358 | 53.1% |
| Sealed 2025 | NEW/CHANGED-ROLE | 388 | 3.433 | **18.6%** |
| Sealed 2025 | ESTABLISHED | 1006 | 4.359 | 47.4% |

**Important negative finding, contrary to the hypothesis:** the lever fires
LESS often, not more, for exactly the rookies/role-changers it was meant to
target (29% and 19% firing vs 53% and 47% for established players). The
mechanism is structurally self-limiting: FFC's ADP snapshot is taken
pre-season, so it can only price in role changes that were ALREADY visible
by late August (a hyped rookie who was drafted early). A player who
breaks out mid-season due to an injury ahead of him, an in-season role
change, or a late training-camp promotion was — almost by definition — NOT
highly drafted (or drafted at all) in the ADP snapshot the lever reads.
The hypothesis's best-case population is the one this specific data source
is least equipped to cover.

## Verdict: **HOLD**

Per the pre-registered rule (SHIP requires the primary gate to clear
walk-forward AND hold direction on sealed 2025 AND the guard to pass):
the primary MAE gate does **not** clear walk-forward (0.023 vs 0.10
required, 23%) — verdict is HOLD regardless of the sealed reading. Sealed
2025 came in directionally consistent and closer to the bar (0.067, 67%)
but does not by itself satisfy a SHIP rule that explicitly requires
clearing walk-forward first. The secondary ordinal gate fails more clearly
(walk-forward Delta +0.0075, wrong direction). The guard passes cleanly on
both runs (weeks 7-18 exactly 0.000 — proof of correct scoping).
`--adp-prior` ships as inert, evaluable, opt-in machinery — same pattern as
`--early-season-prior`, `--qb-starter-floor`, `--rb-tail-calibration`,
`--wr-tiebreak`. Do not flip the default on.

**What's real here:** RB and WR show a consistent, same-direction,
non-trivial effect across both runs (RB: -0.029 walk-forward / -0.126
sealed; WR: -0.079 walk-forward / -0.064 sealed) — the mechanism is
directionally validated for RB/WR, just short of the bar, and QB is the
clear drag (wrong direction on every cut, walk-forward and sealed, Sleeper
and ESPN) — the same QB failure mode `--early-season-prior` found with a
raw, unconditioned per-game baseline. A follow-up worth trying before
re-registering a new gate: RB/WR-only scoping (drop QB, mirroring the
`--early-season-prior` caveat's own recommendation), and/or blending FFC
ADP with the MFL season-aggregate source (untested here) to raise the
<40% coverage ceiling — though the rookie/changed-role finding above
suggests coverage on the highest-value subgroup may be a structural, not
just a data-volume, limit.

## Files changed

- `src/adp_prior.py` (new) — `load_adp_snapshot()`, `build_name_id_crosswalk()`,
  `resolve_adp_player_ids()`, `compute_realized_season_ppg()`,
  `fit_adp_ppg_mapping()`, `compute_adp_implied_ppg()`, `apply_adp_prior()`,
  `ADP_PRIOR_WEIGHTS`, `MIN_LABEL_GAMES`, `MIN_TRAINING_ROWS`,
  `ADP_PRIOR_POSITIONS`.
- `scripts/generate_projections.py` — `--adp-prior` / `--adp-prior-weight`
  CLI flags, weekly-mode wiring after the early-season-prior blend.
- `scripts/backtest_projections.py` — same two CLI flags,
  `run_backtest(adp_prior=..., adp_prior_weight=...)`, per-eval-season
  mapping + implied-PPG cache (loads rosters + training-season weekly data
  independent of the harness's own `season ∪ {season-1}` window), applied
  after the early-season-prior block in the per-week loop, output filename
  `_adpprior` tag.
- `tests/test_adp_prior.py` (new) — 32 unit tests (mapping fit, crosswalk
  resolution, blend math, decay schedule, no-match passthrough, zero-row
  handling). All passing.
- `CLAUDE.md` — one-line command reference under "Gold: Fantasy projections".
