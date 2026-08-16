# Props-Blend Historical Backtest — Archive Run (2026-08-16)

Executes opportunity-scan move #1 (`.planning/OPPORTUNITY_SCAN_2026_08_16.md`
candidate #1): runs the props-blend backtest pre-registered in June and
**never previously executed** (confirmed by that scan: `data/bronze/odds_api/
props/` did not exist locally before this session). Rather than buying the
$29 Odds API historical tier, this uses the free archive found by
`.planning/PROPS_DATA_PLAN.md` Phase 1 scout
(`github.com/firstandthirty/nfl-tools`).

## Data provenance + legal constraint

**Source**: `github.com/firstandthirty/nfl-tools`, public GitHub repo, no
`LICENSE` file (default all-rights-reserved on the repo owner's derived
work). The underlying odds are themselves sourced from The Odds API (a
commercial provider) via the owner's own capture scripts. **Redistribution
rights are ambiguous.** Reading a public repo's committed CSVs for private
research is treated the same as reading any other public repo's data
(low risk); redistributing the data or derived artifacts is not authorized.

**Handling**: `scripts/ingest_props_archive.py` fetches the 4 CSVs directly
from `raw.githubusercontent.com` into memory, normalizes, and writes Parquet
to `data/bronze/odds_api/props/season={2023,2024}/props_archive_<season>.parquet`
— **local only**. `data/bronze/odds_api/**/*.parquet` is allowlisted
(un-ignored) in `.gitignore` for our own forward-captured props, so a
file-pattern-scoped re-ignore rule was added specifically for the archive
output (`.gitignore` line ~414: `data/bronze/odds_api/props/season=*/
props_archive_*.parquet`) — verified with `git check-ignore` (confirmed
ignored) and `git status --short` (confirmed absent from any diff). Derived
research CSVs in `output/backtest/props_blend_archive/` are also gitignored
(`*.csv` is globally ignored in this repo). **Nothing from this session was
staged or committed.** Private research use only, per the task constraint.

## Validation

Row counts vs the Phase 1 scout's numbers, and issues found/fixed during
normalization:

| File | Scout's claim | Actual raw rows | Verdict |
|---|---:|---:|---|
| `fanduel_pass_yds_history.csv` | 6,901 | **1,538** | Scout error (see below) — archive itself is fine |
| `fanduel_receptions_history.csv` | 6,902 | **6,901** | Matches (off-by-one is a header-count artifact) |
| `rush_yds_market_analysis_rows.csv` | 1,095 | **1,094** | Matches |
| `reception_yds_market_analysis_rows.csv` | 2,334 | **2,333** | Matches |

The scout's "6,901 / 6,902 rows" note paired the two counts to `pass_yds` /
`receptions` in that order; both numbers actually belong to
`fanduel_receptions_history.csv` (6,901 data rows) — a transcription error,
not a bad archive. `fanduel_pass_yds_history.csv`'s real row count (1,538 ≈
3 seasons × ~17 weeks × ~28 starting QBs/week) is internally consistent and
was independently confirmed continuous 2023 wk2 → 2025 wk18 (see below).

**Two real data-quality bugs found and fixed in `ingest_props_archive.py`**
(would have silently corrupted the entire backtest if missed):

1. **Week-guess off-by-one, season 2023 only.** `fanduel_pass_yds_history.csv`
   / `fanduel_receptions_history.csv` carry only a *guessed* week
   (`week_guess_numeric`), not a validated one. Cross-checked against real
   nflverse actuals (`data/bronze/players/weekly/`): the 2023 Week 1 Thursday
   opener (KC @ DET, 2023-09-08 kickoff) is tagged `week_guess_numeric=2` in
   the archive, and KC's real 2023 bye week (nflverse week 10) shows up as a
   gap at archive `week_guess=11` — both confirm the archive's week guess is
   **+1 vs real nflverse week for season 2023 only**. The same check on 2024
   and 2025 rows (Week 1 openers, KC's 2024 bye at nflverse week 6) confirms
   **no offset** for those seasons. Corrected per-season
   (`WEEK_GUESS_OFFSET_BY_SEASON = {2023: -1}`) — a uniform offset across all
   seasons would have been wrong.
2. **Decimal vs American odds.** Those same two files store `over_price`/
   `under_price` as **decimal** odds (e.g. `1.91`), not American, despite
   `src/prop_implied.py::american_to_prob` expecting American. Converted via
   the standard decimal→American formula before writing.

Not a bug, but noted: `rush_yds_market_analysis_rows.csv` /
`reception_yds_market_analysis_rows.csv` already carry correct season/week
and American odds, but had 2 and 12 duplicate `(player, event_id)` rows
respectively (two capture snapshots for the same game) — deduped to the
**latest** `requested_snapshot_time` per the task's "prefer closing/latest"
instruction.

**Spot checks (5) against known real games**, using local `player_weekly`
Bronze actuals as ground truth:

| Player | Market | Game | Line | Actual | Check |
|---|---|---|---:|---:|---|
| Patrick Mahomes | pass yds | KC@DET, 2023 wk1 opener | 280.5 | 226.0 | Real matchup, plausible elite-QB opener line |
| Najee Harris | rush yds | PIT@BAL, 2024 wk11 | 51.5 | 63.0 | Matches scout's own spot-check exactly |
| Diontae Johnson | rec yds | PIT@BAL, 2024 wk11 | 17.5 | 0.0 | Archive's own pre-graded `actual`=0 matches our independent `player_weekly` actual exactly |
| CeeDee Lamb | receptions | DAL@LAC, 2023 wk6 | 5.5 | 7 (over) | Real matchup, plausible elite-WR line |
| Tyreek Hill | rec yds | MIA@TEN, 2024 wk4 | 51.5 | 23.0 | Real matchup, plausible line |

**Line distribution sanity** (all fetched rows, pre-window-filter): pass yds
mean 224 (σ 27), rec yds mean 33 (σ 19), receptions mean 3.4 (σ 1.4), rush
yds mean 37 (σ 23) — all within normal NFL prop ranges, no unit/scale
anomalies.

**Coverage limits** (post-normalization, matches scout's finding): pass
yds + receptions span 2023-2025 continuously; rush yds + reception yds are
**2024 only** (weeks 1-17); no anytime-TD data anywhere in the archive. Per
`PROP_IMPLIED_DECISION.md` ("2025 stays sealed"), 2025 rows were fetched for
validation above but **never written** — only 2023 + 2024 exist in
`data/bronze/odds_api/props/`.

## The pre-registered gate (quoted verbatim, `.planning/PROP_IMPLIED_DECISION.md`, written 2026-06-12)

> **Backtest plan (write-once, pre-registered)**
> - Window: 2023 w5–18 + 2024 w1–18 (props history starts May 2023; 2025 stays sealed).
> - Step 1 (benchmark): MAE + within-position-week Spearman of `prop_implied_points` alone vs our heuristic vs Sleeper consensus on matched player-weeks.
> - Step 2 (blend): `proj' = (1−λ)·proj + λ·prop_implied_points`, λ swept per position in the heuristic lab. Players without props (deep bench) keep λ=0.
> - Step 3 (gate): consensus-matched eval. SHIP if WR/RB MAE gap improves ≥0.05 OR Spearman gap narrows ≥0.02 at either position, no QB/TE regression.
>
> **Predicted delta**: RB consensus gap +0.27 → ≤+0.10; WR +0.09 → ≤0. Spearman +0.03–0.06 at RB/WR. **If the blend moves <0.02 at every position: KILL** and downgrade to benchmark-only use.

Both `PROPS_CAPTURE.md` and `OPPORTUNITY_SCAN_2026_08_16.md` restate this
identically — one consistent, never-revised gate. No new bar invented.

## Method

`scripts/eval_props_blend_archive_backtest.py` — does not reimplement any
metric: imports `apply_props_blend` / `compute_prop_implied_points` from
`src/prop_implied.py` (the exact machinery `--props-blend` uses in
production) and `compute_mae_gap` / `compute_spearman_rank_corr` /
`apply_consensus_filter` from `src/consensus_metrics.py` (single source of
truth for every other backtest/grading report in this repo). It only adds
the per-week loop `backtest_projections.py` doesn't have (that script has no
`--props-blend` wiring — the flag exists solely on `generate_projections.py`,
which reads one *latest* forward-capture file, not a multi-week archive).

**Baseline** = `output/backtest/pooled_2022_2024_{sleeper,espn}_matched.csv`
reused **byte-identical, unmodified** (same precedent
`OPPORTUNITY_SCAN_2026_08_16.md` used: "reused, did not regenerate, the
exact matched population" — same repo/model state as what's live now, this
session made no model-code or Bronze/Silver changes upstream of it).
**Treated** = the identical rows, in this same session, with
`apply_props_blend` applied per-week using the archive props above; rows
with no in-window coverage are untouched by construction, so only
`projected_points` for covered player-weeks differs between the two frames.

**Necessary name-matching bridge**: the pooled CSV stores `player_name` in
`backtest_projections.py`'s own abbreviated convention ("C.McCaffrey"), but
the archive (like the live pipeline) carries full names ("Christian
McCaffrey") — `normalize_player_name` cannot bridge an abbreviation gap, only
punctuation. Built a `player_id → player_display_name` lookup from Bronze
`player_weekly` (both frames already share nflverse `player_id`/`gsis_id`)
and substituted full names before calling `apply_props_blend`. 118/7,009
(1.7%) pooled rows have no lookup hit (edge-case players missing from local
`player_weekly`) and keep the abbreviated name — this can only *undercount*
coverage, never inflate it, so it does not risk a false SHIP.

## Firing rates (matched, `consensus_proj>=5`, per position per season)

| Season | Position | n matched | n covered | Firing rate |
|---|---|---:|---:|---:|
| 2023 | QB | 358 (Sleeper) / 351 (ESPN) | 319 / 316 | **89-90%** |
| 2024 | QB | 422 / 421 | 363 / 363 | **86%** |
| 2023 | RB | 533 / 545 | 0 / 0 | **0%** (no rush-yds market before 2024) |
| 2024 | RB | 607 / 628 | 467 / 475 | **77% / 76%** |
| 2023 | WR | 825 / 787 | 0 / 0 | **0%** (no reception-yds market before 2024) |
| 2024 | WR | 1,000 / 952 | 766 / 742 | **77% / 78%** |
| 2023 | TE | 242 / 260 | 0 / 0 | **0%** |
| 2024 | TE | 319 / 323 | 242 / 244 | **76% / 76%** |

Confirms the task brief's expected scoping exactly: **QB is evaluable across
both 2023 and 2024 (pass-yds archive); RB/WR/TE are evaluable in 2024 only**
(rush-yds / reception-yds archives don't cover 2023). Coverage where
available is high (76-90% of the consensus-matched population), so this is
a real read on the hypothesis, not a detector-sparsity artifact.

## Step 1 — benchmark: prop_implied_points alone (covered player-weeks only)

| Source | Position | n | market MAE | our MAE | consensus MAE | market − consensus |
|---|---|---:|---:|---:|---:|---:|
| Sleeper | QB | 682 | 8.152 | 5.780 | 6.291 | **+1.861** (market loses badly) |
| Sleeper | RB | 467 | 5.922 | 5.390 | 5.476 | +0.446 |
| Sleeper | WR | 766 | 5.234 | 5.100 | 5.124 | +0.110 (near parity) |
| Sleeper | TE | 242 | 4.694 | 4.023 | 4.533 | +0.161 |
| ESPN | QB | 679 | 8.171 | 5.787 | 6.018 | +2.153 |
| ESPN | RB | 475 | 5.781 | 5.284 | 5.441 | +0.339 |
| ESPN | WR | 742 | 5.261 | 5.120 | 5.191 | +0.069 (near parity) |
| ESPN | TE | 244 | 4.643 | 4.024 | 4.408 | +0.236 |

**Important caveat on the QB row**: this archive only has `player_pass_yds`
— no `player_pass_tds` market exists in it (matches the Phase 1 scout's
finding: no TD-market data anywhere in this archive). `prop_implied_points`
for QB here is therefore a *deliberately partial* stat line (passing yards
only, missing ~6+ pts/game of passing-TD value and any rushing value) — the
market-alone MAE of ~8.15 vs our 5.78 is **not** a fair read on "would a
complete QB prop signal beat our model," it just reflects the coverage gap
this specific free archive has. WR/TE are closer to a complete stat line
(reception yds + receptions both present) and correspondingly closer to
parity with consensus even unblended.

## Step 3 — the blend gate (RB/WR primary; QB/TE regression guard)

`gap = our_mae − consensus_mae` (negative = we beat consensus). `Δ = treated
− baseline` (negative Δ = MAE gap improves). Spearman gap = our rank-corr −
consensus rank-corr (positive Δ = ranking improves). Lambdas used: the
**shipped, unmodified** `PROPS_BLEND_LAMBDAS` (QB 0.0, RB 0.5, WR 0.3, TE
0.0) — not re-tuned for this eval.

**MAE gap** (window = 2023 w5-18 + 2024 w1-18, matched, cons≥5):

| Source | Position | baseline | treated | Δ | % of 0.05 SHIP bar |
|---|---|---:|---:|---:|---:|
| Sleeper | QB | −0.4497 | −0.4497 | 0.0000 | n/a (λ=0) |
| Sleeper | **RB** | −0.2695 | −0.2893 | **−0.0198** | 40% |
| Sleeper | **WR** | −0.0038 | −0.0301 | **−0.0263** | 53% |
| Sleeper | TE | −0.4288 | −0.4288 | 0.0000 | n/a (λ=0) |
| ESPN | QB | −0.1748 | −0.1748 | 0.0000 | n/a (λ=0) |
| ESPN | **RB** | −0.3433 | −0.3723 | **−0.0290** | **58%** |
| ESPN | **WR** | −0.0412 | −0.0634 | **−0.0223** | 45% |
| ESPN | TE | −0.3669 | −0.3669 | 0.0000 | n/a (λ=0) |

**Spearman gap** (same window/population):

| Source | Position | baseline | treated | Δ | % of 0.02 SHIP bar |
|---|---|---:|---:|---:|---:|
| Sleeper | RB | 0.0728 | 0.0802 | +0.0074 | 37% |
| Sleeper | WR | 0.0068 | 0.0136 | +0.0067 | 34% |
| ESPN | RB | 0.0599 | 0.0703 | +0.0104 | 52% |
| ESPN | WR | 0.0018 | 0.0073 | +0.0056 | 28% |
| Sleeper/ESPN | QB, TE | — | — | 0.0000 | n/a (λ=0) |

## Verdict: **HOLD**

| Criterion | Required | Measured (best of 4 RB/WR × 2 source combos) | Result |
|---|---|---|---|
| WR/RB MAE gap improves ≥0.05 | ≥0.05 | 0.0290 (ESPN RB, 58% of bar) | **FAIL** |
| OR Spearman gap narrows ≥0.02 | ≥0.02 | 0.0104 (ESPN RB, 52% of bar) | **FAIL** |
| No QB/TE regression | Δ ≤ 0 | 0.0000 both (λ=0, unchanged by construction) | **PASS (vacuous)** |
| Blanket KILL check: moves <0.02 everywhere | — | RB/WR MAE moves are 0.0198-0.0290 (above 0.02); Spearman moves are 0.0056-0.0104 (below 0.02) | **Neither clean KILL nor SHIP** |

Every non-zero cell (RB and WR, both sources, both metrics) moved in the
**predicted direction** (we beat consensus by more with the blend on) and
**none regressed** — but no cell clears the pre-registered SHIP bar, and the
MAE moves are large enough (0.02-0.03) that this doesn't cleanly satisfy the
memo's own blanket-KILL condition either ("moves <0.02 at every position").
This lands in the same real-but-sub-threshold zone as `RB_TAIL_CALIBRATION_GATE.md`
(HOLD at 79% of its bar) and `WR_TIEBREAK_GATE.md` (HOLD at 16%) — closest
individual result is ESPN RB MAE gap at **58% of the bar**, the strongest of
the three positions/metrics tested. Per house convention (all criteria must
clear to SHIP), the composite is **HOLD**: `--props-blend` stays opt-in,
current provisional lambdas (RB 0.5 / WR 0.3 / QB 0 / TE 0) are **not**
promoted to default-on.

QB/TE "no regression" passes only because their shipped lambda is already 0
— this is a vacuous pass by construction, not new evidence that a non-zero
QB/TE lambda would be safe. The Step 1 benchmark above suggests it would be
premature to try a non-zero QB lambda on this specific archive regardless
(the market signal there is measurably incomplete, missing the TD market
entirely).

## Caveats / follow-ups

- **RB/WR/TE evidence is single-season (2024 only, 17 weeks).** The archive
  simply doesn't have rush-yds/reception-yds coverage before 2024 (a scout
  finding, not a bug). This HOLD is a real read on 2024 but has no
  independent-season replication yet — the in-season 2026 gate (Sunday
  snapshots, `STATE.md` open thread) is still the source of truth for
  multi-season confirmation.
- **QB evidence (both seasons, 76-90% firing) is the strongest-coverage part
  of this archive, but is unusable for a fair QB blend gate** because the
  archive has no `player_pass_tds` market — any QB blend built on this data
  would systematically under-project by omitting the TD component. Not
  attempted; would need either a TD-market source or a corrective addition
  (e.g. blend only the yards residual, not full points) to be trustworthy.
- **No anytime-TD data anywhere in this archive** (matches the Phase 1
  scout's finding) — RB/WR/TE prop_implied_points here also omit their own
  TD contribution, likely *understating* the market signal's true predictive
  power. The 58%-of-bar ESPN RB result may be a floor, not a ceiling, on
  what a TD-complete props blend could do — worth reconsidering once the
  in-season capture (which does request `player_anytime_td`, per
  `PROPS_CAPTURE.md`) accumulates real TD-market coverage.
- **Single book (FanDuel only)**, matching the scout's finding — no
  cross-book median available for this historical slice (the live capture
  path does support multi-book once DK/FanDuel both post in-season).

## Files changed

- `scripts/ingest_props_archive.py` (new) — fetches the 4 archive CSVs from
  `raw.githubusercontent.com`, fixes the season-2023 week-guess off-by-one
  and decimal→American odds conversion, dedupes to closing snapshots, maps
  team names via the existing `ODDS_API_TO_NFLVERSE` dict, writes
  `data/bronze/odds_api/props/season={2023,2024}/props_archive_<season>.parquet`
  (gitignored — see provenance section).
- `scripts/eval_props_blend_archive_backtest.py` (new) — runs the
  pre-registered gate: per-week `apply_props_blend`/`compute_prop_implied_points`
  from `src/prop_implied.py`, gap/Spearman tables from
  `src/consensus_metrics.py`, firing-rate + Step 1 benchmark diagnostics.
  Writes derived (gitignored) CSVs to `output/backtest/props_blend_archive/`.
- `.gitignore` — one new file-pattern-scoped re-ignore rule for the archive
  output (see provenance section).
- No production code changed (`src/prop_implied.py`, `generate_projections.py`,
  `backtest_projections.py` untouched) — this was a pure evaluation run
  against existing, unmodified machinery.
