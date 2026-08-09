# Early-Season Prior Gate — Lever #1 (2026-08-09)

Implements + gate-evaluates lever #1 from `.planning/CONSENSUS_ERROR_DECOMPOSITION.md`
finding #1: weeks 3-6 lose ~0.3-0.46 MAE to Sleeper/ESPN across all four skill
positions — the single biggest, most consistent weak spot in the consensus-error
decomposition. Hypothesis: our rolling-average features have only 1-3
current-season games of history that early, so projections lean too hard on a
thin in-season sample, while consensus sources blend in preseason/analyst
priors that adapt to role changes faster.

## Lever implemented

`proj' = (1-w)*proj + w*prior_pg` for weeks 3-6 only (no-op elsewhere), where:

- `prior_pg` = the player's **prior-season** (S-1) per-game half-PPR points,
  computed from `data/bronze/players/weekly/season={S-1}` via
  `scoring_calculator.calculate_fantasy_points_df`, gated on ≥6 games played
  in the prior season (no prior, or <6 games → no adjustment).
- `w = scale * schedule[week]`, fixed decaying schedule
  `{3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}`, `scale` defaults to 1.0.
- Applies to QB/RB/WR/TE only.

Prior-season (not preseason props/consensus) was chosen per the task spec: it
is available for every backtest season (2022-2024) as well as production,
whereas the preseason-lines parquet only exists from 2026 onward.

**New module**: `src/early_season_prior.py` — `compute_prior_season_ppg()` +
`apply_early_season_prior()`, mirroring the existing `prop_implied.py`
compute/apply pattern used by `--props-blend`.

**Wiring** (opt-in, mirrors `--props-blend`):
- `scripts/generate_projections.py --early-season-prior` /
  `--early-season-prior-weight` (weekly mode only; applied after injury
  adjustments, before event/props/sentiment blends).
- `scripts/backtest_projections.py --early-season-prior` /
  `--early-season-prior-weight` — threads the same lever into
  `run_backtest()` so it is evaluable on historical seasons; prior-season PPG
  is computed once per season from the same multi-season `weekly_df` the
  backtest already loads (no extra I/O).

## Pre-registered gate (written before running the eval)

- **SHIP** if: weeks 3-6 matched-pairs MAE gap vs Sleeper improves ≥0.10 pts
  overall (and directionally vs ESPN), **AND** full weeks 3-18 overall gap
  does not worsen by >0.02, **AND** no position's overall (3-18) gap worsens
  by >0.05.
- **Else HOLD**, report numbers.

## Method

Canonical eval process (`.planning/CONSENSUS_BENCHMARK_MULTI_SOURCE.md` /
`CONSENSUS_ERROR_DECOMPOSITION.md`):

```bash
# Baseline — reused the matched CSVs already on disk from the 2026-08-09
# decomposition run (same seasons/scoring/mode; regenerating would be a
# noisy re-draw of the same methodology, not a different baseline):
#   output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260809_035714.csv

# Treated:
./venv/Scripts/python.exe scripts/backtest_projections.py \
    --seasons 2022,2023,2024 --scoring half_ppr --ml --full-features \
    --early-season-prior --output-dir output/backtest
# -> output/backtest/backtest_half_ppr_ml_fullfeatures_earlyseasonprior_20260809_092607.csv

./venv/Scripts/python.exe scripts/benchmark_consensus_sources.py \
    --backtest-csv output/backtest/backtest_half_ppr_ml_fullfeatures_earlyseasonprior_20260809_092607.csv \
    --sources espn sleeper --output-dir output/backtest \
    --json-out output/backtest/consensus_benchmark_summary_earlyseasonprior.json
# -> output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260809_132617.csv
```

Weeks 3-6 / 7-18 / 3-18 gap tables computed from the matched CSVs via
`src/consensus_metrics.apply_consensus_filter` + `build_position_table`
(cons≥5 pts, matched player-weeks) — the same primitives
`benchmark_consensus_sources.py` uses, applied per week-band.

## Results — weeks 3-6 (the lever's target window)

`gap = our_mae − source_mae`, negative = we win. Δ = treated − baseline
(negative Δ = improvement).

| Position | n | vs Sleeper baseline | vs Sleeper treated | Δ | vs ESPN baseline | vs ESPN treated | Δ |
|---|---|---|---|---|---|---|---|
| QB | 346/331 | −0.740 | −0.719 | **+0.021** (worse) | +0.100 | +0.118 | **+0.018** (worse) |
| RB | 529/502 | +0.461 | +0.436 | −0.025 | +0.373 | +0.349 | −0.025 |
| WR | 810/763 | +0.350 | +0.312 | −0.037 | +0.291 | +0.253 | −0.038 |
| TE | 251/254 | +0.368 | +0.331 | −0.036 | +0.276 | +0.230 | −0.047 |
| **OVERALL** | 1,936/1,850 | **+0.188** | **+0.164** | **−0.023** | **+0.277** | **+0.251** | **−0.026** |

**Gate check on the primary criterion**: weeks 3-6 overall gap vs Sleeper
improved by **0.023 pts** — real, same-direction-as-hypothesized, and
internally consistent (RB/WR/TE all improve, vs both sources), but **less
than a quarter of the required ≥0.10 improvement**. QB moved the wrong way
in both matched sets (small: +0.02, +0.018).

## Results — full weeks 3-18 (regression guard)

| Position | vs Sleeper baseline | vs Sleeper treated | Δ | vs ESPN baseline | vs ESPN treated | Δ |
|---|---|---|---|---|---|---|
| QB | −0.343 | −0.337 | +0.006 | +0.230 | +0.235 | +0.005 |
| RB | +0.319 | +0.312 | −0.007 | +0.221 | +0.215 | −0.007 |
| WR | +0.123 | +0.113 | −0.010 | +0.089 | +0.079 | −0.011 |
| TE | +0.195 | +0.185 | −0.010 | +0.202 | +0.189 | −0.013 |
| **OVERALL** | **+0.102** | **+0.096** | **−0.006** | **+0.166** | **+0.159** | **−0.007** |

Weeks 7-18 are **byte-identical** between baseline and treated for every
position/source (Δ = 0.000 exactly) — confirms the blend is correctly scoped
to weeks 3-6 only, no leakage into the rest of the season.

**Gate check on the guard criteria**: full-season overall gap does not
worsen (it improves slightly, −0.006/−0.007, well inside the ±0.02 band).
No position's overall gap worsens by more than +0.006 (QB, both sources) —
nowhere close to the 0.05 tolerance.

## Verdict: **HOLD**

The safety guards (full-season regression, per-position regression) both
pass comfortably. The primary bar — weeks 3-6 overall MAE gap vs Sleeper
improving ≥0.10 — **fails**: measured improvement is **0.023**, about a
fifth of the threshold. Do not flip `--early-season-prior` on by default.
The flag stays opt-in/off and merges as inert, evaluable machinery, matching
the pattern already established for `--props-blend` and
`--vacated-opportunity`.

## Caveats / follow-ups

- **Coverage is the likely limiter, not weight.** Only ~52% of weeks 3-6
  QB/RB/WR/TE player-weeks in the treated backtest carry a
  `prior_season_ppg` (the other ~48% are players without ≥6 prior-season
  games — rookies, new team, injury-shortened prior year — exactly the
  players the decomposition doc's magnitude-band/committee-back findings
  (#2, #4) flag as the harder problem). A blend that only touches half the
  population caps how much it can move the aggregate gap.
- **Doubling the weight does not fix it — and hurts QB.** An exploratory
  run at `--early-season-prior-weight 2.0` (schedule effectively
  `{3:0.8, 4:0.6, 5:0.4, 6:0.2}`) moved the weeks 3-6 overall vs-Sleeper gap
  to only +0.173 (vs +0.164 at scale 1.0 — *worse*, not better) and pushed
  QB further the wrong way (vs Sleeper: −0.667 vs −0.719 at scale 1.0, a
  further +0.052 pts of regression vs ESPN: +0.168 vs +0.118). The raw
  prior-season PPG is too blunt a signal for QB specifically — likely
  because backup/injury-driven starter changes (finding #3 in the
  decomposition doc) get pulled toward the *outgoing* player's own prior
  history rather than a role-appropriate baseline. This is a strong signal
  that a starter-designation-aware version (finding #3's proposed lever)
  is a better fit for QB than blanket PPG shrinkage.
- **RB/WR/TE show a real, consistent, if small, effect** (~0.025-0.047 pts
  improvement at weeks 3-6, both sources, same direction as the hypothesis)
  — the mechanism is directionally validated even though it doesn't clear
  the gate. A future iteration could restrict the lever to RB/WR/TE (drop
  QB, which regresses), and/or replace the raw prior-season PPG with a
  role-adjusted prior (e.g. weighted by projected snap share vs prior-season
  snap share) to raise coverage and quality simultaneously — worth a
  follow-up experiment before re-registering a gate, not a blind
  higher-weight retry.

## Files changed

- `src/early_season_prior.py` (new) — `compute_prior_season_ppg()`,
  `apply_early_season_prior()`, `EARLY_SEASON_PRIOR_WEIGHTS`,
  `MIN_PRIOR_GAMES`, `EARLY_SEASON_PRIOR_POSITIONS`.
- `scripts/generate_projections.py` — `--early-season-prior` /
  `--early-season-prior-weight` CLI flags, weekly-mode wiring after injury
  adjustments.
- `scripts/backtest_projections.py` — same two CLI flags,
  `run_backtest(early_season_prior=..., early_season_prior_weight=...)`,
  per-season prior-PPG cache, applied after the injury-adjustment block in
  the per-week loop, output filename `_earlyseasonprior` tag.
- `tests/test_early_season_prior.py` (new) — 15 unit tests covering
  `compute_prior_season_ppg` (averaging, min-games gate, empty/missing
  input) and `apply_early_season_prior` (per-week schedule weights, no-op
  outside weeks 3-6, scale knob, missing-prior/position no-ops, provenance
  column). All passing.
- `CLAUDE.md` — one-line command reference under "Gold: Fantasy projections".
