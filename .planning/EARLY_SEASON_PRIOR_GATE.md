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

---

## Re-gate with 2021 priors (2026-08-09, later same day)

Both original gate runs (the MAE gate above and the ordinal-gate addendum in
`.planning/WR_ORDERING_DIAGNOSIS.md`) were silently diluted:
`data/bronze/players/weekly/season=2021` didn't exist locally, so
`apply_early_season_prior` was a confirmed structural no-op for every 2022
player-week — the lever only ever fired for 2023 (needs 2022 prior data) and
2024 (needs 2023). `season=2021` has since been ingested
(`data/bronze/players/weekly/season=2021/player_weekly_20260809_150647.parquet`,
5,698 rows, 660 players, weeks 1-22). This section re-runs both eval paths
with full 3-season coverage. **Eval only — no changes to
`src/early_season_prior.py`, `scripts/generate_projections.py`, or
`scripts/backtest_projections.py` this round.**

### 1. Firing rate (new required metric)

"Fired" = `prior_season_ppg` notna on that row (the exact same flag
`generate_projections.py`'s own log line uses) — weeks 3-6, QB/RB/WR/TE.
Identical between the two engine modes (the prior-PPG computation doesn't
depend on `--ml`/`--full-features`; only the projection it blends into does),
so one table covers both:

| Season | QB | RB | TE | WR | Season total |
|---|---|---|---|---|---|
| 2022 | 110/125 (0.880) | 197/264 (0.746) | 139/175 (0.794) | 312/397 (0.786) | **758/961 (0.789)** |
| 2023 | 92/120 (0.767) | 176/238 (0.739) | 151/181 (0.834) | 311/402 (0.774) | 730/941 (0.776) |
| 2024 | 85/115 (0.739) | 202/247 (0.818) | 132/161 (0.820) | 298/371 (0.803) | 717/894 (0.802) |

**Confirmed: 2022 now fires** at a 78.9% rate, in line with 2023 (77.6%) and
2024 (80.2%) — no longer the structural 0/397 (WR) / 0-across-the-board null
control the original `WR_ORDERING_DIAGNOSIS.md` addendum measured. The
~20-22% non-firing remainder each season is players below the 6-game
prior-season minimum (rookies, new arrivals, injury-shortened prior year) —
expected, not a bug.

### 2. Data-state confound (read before trusting the deltas below)

Both baselines being reused (`consensus_matched_*_20260809_035714.csv` for
the MAE gate; `backtest_half_ppr_consensus_20260809_145355.csv` for the
ordinal gate) were generated **before** the 2021 ingestion. The treated runs
below were generated **after**. `run_backtest()` always loads
`weekly_df` for `season ∪ {season-1}` regardless of `--early-season-prior` —
that same weekly frame also feeds `compute_defensive_strength()`'s
trailing-8-week matchup window, which crosses season boundaries. So having
2021 present changes early-2022 matchup-factor quality for **every** 2022
projection, not just the ones the prior blend touches.

Measured size of this confound (vs Sleeper, MAE-gate matched CSVs, weeks
7-18 — outside the lever's scope, so any non-zero delta here is confound,
not lever): **2022 delta −0.018**, 2023 delta −0.0005, 2024 delta 0.0000.
Only 2022 moves, and only by ~0.02 gap-points — about an order of magnitude
smaller than the effects reported below. The clean fix is a freshly
regenerated no-flag baseline on 2021-inclusive data; that wasn't run this
round per the coordinator's reuse instruction. Treat the weeks 3-6 numbers as
~95% lever, ~5% confound for 2022 specifically; 2023/2024 are unaffected
(their trailing windows never needed 2021 data).

### 3. Gate (a) re-score — original MAE gate

Same method as the original run above (`consensus_metrics.apply_consensus_filter`
+ `build_position_table` on matched CSVs), `--ml --full-features` engine mode
(matches this doc's original run):

```bash
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --scoring half_ppr --ml --full-features --early-season-prior --output-dir output/backtest
# -> output/backtest/backtest_half_ppr_ml_fullfeatures_earlyseasonprior_20260809_151946.csv
./venv/Scripts/python.exe scripts/benchmark_consensus_sources.py \
    --backtest-csv output/backtest/backtest_half_ppr_ml_fullfeatures_earlyseasonprior_20260809_151946.csv \
    --sources espn sleeper --output-dir output/backtest \
    --json-out output/backtest/consensus_benchmark_summary_earlyseasonprior_2021.json
# -> output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260809_191953.csv
```

**Weeks 3-6** (`gap = our_mae − source_mae`; Δ = new-treated − baseline, negative = improvement):

| Position | vs Sleeper base | vs Sleeper treated | Δ | vs ESPN base | vs ESPN treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | −0.740 | −0.772 | −0.032 | +0.100 | +0.062 | −0.038 |
| RB | +0.461 | +0.292 | −0.169 | +0.373 | +0.207 | −0.166 |
| WR | +0.350 | +0.154 | −0.195 | +0.291 | +0.106 | −0.185 |
| TE | +0.368 | +0.233 | −0.134 | +0.276 | +0.131 | −0.145 |
| **OVERALL** | **+0.188** | **+0.037** | **−0.151** | **+0.277** | **+0.129** | **−0.148** |

Every position improves now (QB included — the small QB regression seen in
the diluted run is gone with 2022 actually firing). Weeks 3-18 guard:

| Position | vs Sleeper base | vs Sleeper treated | Δ | vs ESPN base | vs ESPN treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | −0.343 | −0.366 | −0.023 | +0.230 | +0.206 | −0.024 |
| RB | +0.319 | +0.274 | −0.045 | +0.221 | +0.178 | −0.043 |
| WR | +0.123 | +0.063 | −0.060 | +0.089 | +0.031 | −0.058 |
| TE | +0.195 | +0.160 | −0.035 | +0.202 | +0.165 | −0.037 |
| **OVERALL** | **+0.102** | **+0.056** | **−0.046** | **+0.166** | **+0.121** | **−0.045** |

**Gate check**: weeks 3-6 overall vs Sleeper improves **0.151** (≥0.10 ✓, and
even net of the ~0.018 2022-only confound, comfortably ≥0.13 lever-only ✓);
directionally vs ESPN ✓ (−0.148); full weeks 3-18 overall does not worsen —
it improves (−0.046, inside the ±0.02 band) ✓; no position's weeks 3-18 gap
worsens by >0.05 — none worsen at all, every position improves ✓.

**Verdict (a): SHIP.** All three criteria pass, the primary bar clears with
50%+ headroom over the 0.10 threshold, and it survives even a conservative
haircut for the identified confound.

### 4. Gate (b) re-score — ordinal gate (WR_ORDERING_DIAGNOSIS.md addendum)

Same method and engine mode as the addendum (plain heuristic, `--vs-consensus`,
isolated `--output-dir` so `simulate_fp_accuracy.load_ours()`'s glob is
unambiguous):

```bash
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper \
    --early-season-prior --output-dir output/backtest/treated_esp_2021
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/treated_esp_2021
./venv/Scripts/python.exe scripts/diagnose_wr_ordering.py --output-dir output/backtest/treated_esp_2021
# baseline re-scored fresh against the same backtest_half_ppr_consensus_20260809_145355.csv:
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest
```

Overall (QB+RB+WR+TE mean) FantasyPros-style Accuracy Gap vs Sleeper, weeks
3-17, 2022-2024:

| Position | Base gap | Treated gap | Δ |
|---|---:|---:|---:|
| QB | +0.034 | −0.023 | **−0.058** |
| RB | +0.271 | +0.244 | **−0.027** |
| WR | +0.375 | +0.306 | **−0.069** |
| TE | +0.220 | +0.180 | **−0.041** |
| **OVERALL (mean)** | **+0.2253** | **+0.1767** | **−0.0486** |

(vs ESPN: identical deltas per position — `ours` moves, `sleeper`/`espn`
don't — overall base +0.176 → treated +0.127, Δ −0.0486.)

**Gate check**:
1. Overall improvement ≥0.05 vs Sleeper: measured **0.0486** — **fails, by
   0.0014** (97% of the threshold; the closest of any criterion scored in
   either gate run today or the original ones).
2. WR improving: yes, −0.069. **Passes.**
3. No position worsening >0.03: none worsen at all (all four improve).
   **Passes.**

The confound from §2 cuts the wrong way for a "just give it more room"
reading: it's isolated to 2022 non-early weeks and (by the same mechanism as
the MAE gate) most likely nudges 2022's weeks-7-17 numbers *toward*
improvement too, meaning some of the measured 0.0486 is probably confound,
not lever — a fully deconfounded number would likely be equal to or slightly
below 0.0486, not above it. There's no basis here for calling this a
measurement artifact that masks a true pass.

**Verdict (b): HOLD** — criterion 1 fails, narrowly. Per the addendum's
pre-registered rule (all three required), the composite is HOLD even though
2 of 3 criteria pass and criterion 1 missed by less than 3% of its own value.

### 5. Bottom line

The two gates now disagree: **MAE gate → SHIP**, **ordinal gate → HOLD (by a
hair)**. Both moved substantially toward SHIP once 2022 actually fires
(MAE-gate improvement 0.023→0.151 pts at weeks 3-6; ordinal-gate improvement
implicitly larger too, though the pre-2021 ordinal number wasn't restated
here since the addendum already flagged 2022 as a null control). Given a
split decision on two independently pre-registered gates, **do not flip
`--early-season-prior` on by default from this re-gate alone.** The
recommended next step is the clean fix flagged in §2 (a no-flag baseline
regenerated on 2021-inclusive data, removing the confound) before treating
either verdict — especially the razor-thin ordinal HOLD — as final. The flag
remains opt-in/evaluable machinery in both `generate_projections.py` and
`backtest_projections.py`.

### Regeneration

```bash
# MAE gate
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --scoring half_ppr --ml --full-features --early-season-prior --output-dir output/backtest
./venv/Scripts/python.exe scripts/benchmark_consensus_sources.py \
    --backtest-csv <the CSV just written> --sources espn sleeper --output-dir output/backtest \
    --json-out output/backtest/consensus_benchmark_summary_earlyseasonprior_2021.json

# Ordinal gate
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper \
    --early-season-prior --output-dir output/backtest/treated_esp_2021
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/treated_esp_2021
./venv/Scripts/python.exe scripts/diagnose_wr_ordering.py --output-dir output/backtest/treated_esp_2021
```

---

## Deconfounded verdict (2026-08-09, final)

The prior section flagged but didn't fix a confound: both reused baselines
predated the 2021 ingestion while the treated runs postdated it, so
`compute_defensive_strength()`'s trailing-8-week window (which reads the
same `season ∪ {season-1}` weekly frame regardless of `--early-season-prior`)
was silently better for 2022 in the treated runs than in the baselines, for
reasons having nothing to do with the lever. This section regenerates a
**no-flag baseline on the same 2021-inclusive data**, same two engine modes
as the treated runs, and rescores both gates against it. **Eval only — no
changes to `src/early_season_prior.py`, `scripts/generate_projections.py`,
or `scripts/backtest_projections.py`.**

```bash
# MAE-gate engine mode, no flag
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --scoring half_ppr --ml --full-features --output-dir output/backtest
# -> output/backtest/backtest_half_ppr_ml_fullfeatures_20260809_153353.csv
./venv/Scripts/python.exe scripts/benchmark_consensus_sources.py \
    --backtest-csv output/backtest/backtest_half_ppr_ml_fullfeatures_20260809_153353.csv \
    --sources espn sleeper --output-dir output/backtest \
    --json-out output/backtest/consensus_benchmark_summary_cleanbaseline_2021.json
# -> output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260809_193853.csv

# Ordinal-gate engine mode, no flag, isolated dir
./venv/Scripts/python.exe scripts/backtest_projections.py --seasons 2022,2023,2024 \
    --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper \
    --output-dir output/backtest/baseline_clean_2021
./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py --output-dir output/backtest/baseline_clean_2021
```

### Confound size (proof the fix worked)

Weeks 7-18 (outside the lever's scope — any delta here is pure data-state
effect, not lever) between the new clean baseline and the treated run, MAE
gate:

| Source | Weeks 7-18 Δ (clean-base → treated) |
|---|---|
| Sleeper | **0.000000** (exact, every position) |
| ESPN | **0.000000** (exact, every position) |

Compare to the prior section's stale-baseline comparison, which showed a
non-zero 2022-only Δ of −0.018 at weeks 7-18 — that was the 2021-data
artifact, and it is now gone by construction (both sides of the comparison
share the same 2021-inclusive data; only the flag differs). This is the
clean control the original design should have had from the start.

**What this reveals**: the *baseline itself* moved substantially once 2021
data was available — e.g. weeks 3-6 overall vs Sleeper: old stale baseline
0.188 → new clean baseline 0.089 (a 0.098-pt improvement from data alone,
zero lever involvement). That data-driven improvement is larger at weeks 3-6
than at weeks 7-18 specifically because the defensive-strength trailing-8
window needs prior-season history most exactly when current-season history
is thinnest — the same reason the lever itself targets weeks 3-6. The
previous section's confound estimate (~0.018, borrowed from the weeks 7-18
magnitude) badly under-corrected; the true confound at weeks 3-6 was ~5x
larger. Re-scoring against the clean baseline was necessary, not optional.

### Firing rate — reconfirmed unchanged

Firing rate is a property of the treated run alone (whether `prior_season_ppg`
is notna), independent of which baseline it's compared against, so it is
identical to the previous section — restated for the record:

| Season | Fired / eligible (weeks 3-6, QB/RB/WR/TE) | Rate |
|---|---|---|
| 2022 | 758/961 | 0.789 |
| 2023 | 730/941 | 0.776 |
| 2024 | 717/894 | 0.802 |

Unchanged, as expected — 2022 still fires.

### Gate (a) — MAE gate, deconfounded

`gap = our_mae − source_mae`; Δ = treated − clean_base (negative = improvement).

**Weeks 3-6:**

| Position | vs Sleeper clean-base | vs Sleeper treated | Δ | vs ESPN clean-base | vs ESPN treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | −0.792 | −0.772 | +0.020 (worse) | +0.045 | +0.062 | +0.017 (worse) |
| RB | +0.346 | +0.292 | −0.054 | +0.260 | +0.207 | −0.053 |
| WR | +0.234 | +0.154 | −0.079 | +0.178 | +0.106 | −0.072 |
| TE | +0.298 | +0.233 | −0.065 | +0.214 | +0.131 | −0.084 |
| **OVERALL** | **+0.089** | **+0.037** | **−0.053** | **+0.182** | **+0.129** | **−0.053** |

**Weeks 3-18 (guard):**

| Position | vs Sleeper clean-base | vs Sleeper treated | Δ | vs ESPN clean-base | vs ESPN treated | Δ |
|---|---:|---:|---:|---:|---:|---:|
| QB | −0.372 | −0.366 | +0.006 | +0.201 | +0.206 | +0.005 |
| RB | +0.289 | +0.274 | −0.015 | +0.192 | +0.178 | −0.015 |
| WR | +0.085 | +0.063 | −0.022 | +0.051 | +0.031 | −0.020 |
| TE | +0.177 | +0.160 | −0.018 | +0.188 | +0.165 | −0.023 |
| **OVERALL** | **+0.070** | **+0.056** | **−0.015** | **+0.136** | **+0.121** | **−0.014** |

**Gate check**: weeks 3-6 overall vs Sleeper improves **0.053** — **fails**
the ≥0.10 bar, at just over half of it. Directionally vs ESPN: passes
(−0.053, same magnitude, consistent). Weeks 3-18 overall does not worsen
(improves −0.015, inside ±0.02) ✓. No position worsens by >0.05 at 3-18 (max
is QB +0.006) ✓.

**Verdict (a), deconfounded: HOLD.** The apparent SHIP in the prior section
was driven roughly 65% by the 2021-ingestion data-quality improvement and
only ~35% by the lever itself (0.098 data-effect vs 0.053 lever-effect,
summing to the previously-measured 0.151). Once isolated, the lever alone
does not clear the primary bar.

### Gate (b) — ordinal gate, deconfounded

Overall (QB+RB+WR+TE mean) FantasyPros-style Accuracy Gap vs Sleeper, weeks
3-17, 2022-2024, clean baseline vs treated:

| Position | Clean-base gap | Treated gap | Δ |
|---|---:|---:|---:|
| QB | +0.025 | −0.023 | **−0.048** |
| RB | +0.262 | +0.244 | **−0.017** |
| WR | +0.357 | +0.306 | **−0.051** |
| TE | +0.209 | +0.180 | **−0.029** |
| **OVERALL (mean)** | **+0.2133** | **+0.1767** | **−0.0366** |

(vs ESPN: same per-position deltas — only `ours` moves — overall +0.164 →
+0.127, Δ −0.0366.)

**Gate check**:
1. Overall improvement ≥0.05 vs Sleeper: measured **0.0366** — **fails**,
   at 73% of the threshold (a clearer miss than the previous section's
   confounded 0.0486, which was within 3% of passing).
2. WR improving: yes, −0.051. **Passes.**
3. No position worsening >0.03: none worsen. **Passes.**

**Verdict (b), deconfounded: HOLD.** Criterion 1 fails by a real, no-longer
razor-thin margin (0.0134 short of the 0.05 bar) once the same data-quality
confound is removed from this metric too.

### Final numbers, both gates, deconfounded

| Gate | Metric | Required | Measured | Result |
|---|---|---|---|---|
| (a) MAE | weeks 3-6 overall Δ vs Sleeper | ≥0.10 improvement | 0.053 (53% of bar) | **FAIL** |
| (b) Ordinal | weeks 3-17 overall Δ vs Sleeper | ≥0.05 improvement | 0.037 (73% of bar) | **FAIL** |

Both gates: **HOLD.**

### Recommendation: do not flip `--early-season-prior` default ON

Weighing the three factors the coordinator flagged:

- **MAE "SHIP margin" — retracted.** The confounded run's 0.151 (50% over
  the bar) was mostly a 2021-ingestion data-quality artifact unrelated to
  the lever. The deconfounded, apples-to-apples number is 0.053 — a real,
  same-direction effect, but short of the bar, not over it. There is no
  SHIP margin to weigh in favor of flipping the default.
- **Ordinal "near-miss" — also retracted, but less severely.** 0.0366 vs a
  0.05 bar is a genuine, if partial, miss (73% of the way there) — not the
  0.0486-vs-0.05 razor's-edge the confounded run suggested, but also not a
  wide gap. Of the two gates, ordinal ends up proportionally the closer one
  post-deconfounding, which is a mild point in the lever's favor, not
  against it.
- **FP competition uses the ordinal metric** — the one now given the most
  weight. Even scored on its own preferred metric, the lever misses the
  pre-registered bar by a real (not noise-level) margin, and the composite
  ordinal gate requires all three criteria regardless of how close criterion
  1 lands.

**Recommendation: keep `--early-season-prior` opt-in / default OFF** in both
`generate_projections.py` and `backtest_projections.py`. Both independently
pre-registered gates now agree (HOLD, HOLD) once the shared data-quality
confound is removed — this is a materially stronger basis for the call than
either individual run before this section, and it does not support a
default flip. The lever remains valid, real (positive, consistent sign
across every position except QB, across both metrics, across three
seasons), evaluable opt-in machinery — a good building block for the
follow-ups already on record (RB/WR/TE-only scoping, role-adjusted prior,
raising the ~79-80% coverage ceiling) rather than a shipped default today.
