# FantasyPros Accuracy Competition — Simulated Score, 2022-2024

Companion to `docs/ACCURACY_COMPETITION.md`. That playbook is about *entering*
FantasyPros' Expert Accuracy Competition; this note estimates *how we'd
score* once entered, by replaying their published methodology on our own
historical weekly rankings. We've only ever measured point MAE
(`scripts/backtest_projections.py --vs-consensus`) — FantasyPros grades
**ordinal positional rankings**, a different metric, so a good MAE result
does not guarantee a good result here.

Script: `scripts/simulate_fp_accuracy.py` (`--selftest` for the runnable
assertion check).

## Methodology (from FantasyPros' published FAQs)

Sources:
- [Fantasy Football: In-Season Accuracy Methodology](https://www.fantasypros.com/about/faq/football-inseason-accuracy-methodology/)
- [How do you measure the in-season accuracy of fantasy football experts?](https://support.fantasypros.com/hc/en-us/articles/44470556043547-How-do-you-measure-the-in-season-accuracy-of-fantasy-football-experts)

Verbatim/paraphrased key points:
- Scoring format: **Half PPR**.
- "The projected point value is based on the average fantasy production for
  that particular rank slot, factoring in bye weeks" — i.e. a rank (e.g.
  "RB #14") is converted into a point value using the *historical average*
  points scored by whoever finishes at that rank slot, not the expert's own
  projected point total.
- **Accuracy Gap** = `|baseline_points(rank) - actual_points|` for each
  player an expert ranked. 0 = perfect, lower is always better.
- Player pool per position/week = union of **top-N by ECR** (site
  consensus) and **top-N by actual finish**: QB 20, RB 40, WR 50, TE/K/DST
  15.
- Season aggregation: sum/average weekly results across weeks **1-17**
  (week 18 excluded), convert to z-scores, drop each expert's worst week
  from week 8 onward, sum the remaining 16 weeks. "Overall" = QB + RB + WR +
  TE (K/DST excluded for consistency reasons).

## What we implemented vs. what we assumed

| FP spec | Our implementation | Why |
|---|---|---|
| Baseline = historical avg points at a rank slot | Built from the actual 2022-2024 sample itself (pooled across all 3 seasons, per position): rank players by **actual** points each week, then average actual points at each rank across all 45 week-instances (3 seasons × weeks 3-17). | FP's internal multi-year baseline isn't published; our own historical sample is the closest available substitute. |
| Player pool = top-N by **ECR** ∪ top-N by actual | top-N by **that ranker's own** rank ∪ top-N by actual | We don't have a multi-expert consensus (ECR) for our own list — we compare three single sources (Ours/Sleeper/ESPN) on their own merits, each pooled against the same actual-finish threshold. |
| Missing player in an expert's ranking | Penalized: rank = (that source's max rank that week/position) + 1 | Matches FP's known practice of penalizing omissions rather than ignoring them. |
| Weeks 1-17, drop worst week from wk8, z-score, sum | Weeks **3-17** only, plain mean (no z-score, no drop-week) | Weeks 1-2 excluded because our own heuristic backtest has no in-season history yet at week 1 (cold start — a hard `SKIP` in `backtest_projections.py`); week 18 excluded to match FP. Z-scoring and worst-week-dropping require the full field of 150+ FantasyPros experts to normalize against each week — we don't have that population, so we report the raw (pre-z-score) mean Accuracy Gap directly. This is the right metric for a same-source, apples-to-apples comparison (Ours vs Sleeper vs ESPN); it is **not** directly comparable in magnitude to FantasyPros' published z-scored leaderboard numbers. |
| Leaderboard placement | Not derivable | FantasyPros' public accuracy pages are JS-rendered leaderboards; no raw per-expert Accuracy Gap numbers or score distributions are published in any FAQ/article we could find. We can say how we'd rank *relative to Sleeper/ESPN consensus* under the same metric, not where that would land among 150+ named experts. |

## Data sources

- **Our rankings**: `output/backtest/backtest_half_ppr_consensus_20260808_235409.csv`,
  produced by `scripts/backtest_projections.py --seasons 2022,2023,2024
  --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source
  sleeper`. This is the same heuristic engine and weekly walk-forward
  process `export_rankings_submission.py` would package for submission —
  local Gold weekly parquet only covers season=2024 (weeks 1/10/17) +
  season=2025, so historical 2022-2023 weeks don't exist as committed Gold
  artifacts; the backtest re-derives them walk-forward instead (no lookahead
  — each week uses only prior-week history, same as production).
- **Actual points**: `actual_points` column from that same CSV — computed by
  `calculate_fantasy_points_df` (half-PPR) inside the backtest against
  nfl-data-py weekly stats (fetched live since local Bronze
  `players/weekly/` only ships `season=2025`).
- **Sleeper / ESPN consensus**: `data/silver/external_projections/season={2022,2023,2024}/week={01..18}/*.parquet`,
  filtered to `source in {sleeper, espn}` and `scoring_format == half_ppr`
  (both committed locally, full 2022-2024 coverage).

Coverage: 3 seasons × 15 scored weeks (3-17) = 45 week-instances per
position. Average weekly pool sizes: QB ~27, RB ~53, WR ~72, TE ~24 players.

## Results — mean Accuracy Gap (lower = better), half-PPR

| Position | Season | Ours | Sleeper | ESPN | Winner |
|---|---|---:|---:|---:|---|
| QB | 2022 | 6.74 | 6.79 | 6.88 | Ours |
| QB | 2023 | 7.25 | 7.27 | 7.20 | ESPN |
| QB | 2024 | 7.66 | 7.51 | 7.45 | ESPN |
| QB | **2022-2024** | **7.21** | **7.19** | **7.18** | **~Tie (ESPN, barely)** |
| RB | 2022 | 6.49 | 6.15 | 6.15 | Sleeper/ESPN (tied) |
| RB | 2023 | 6.01 | 5.86 | 5.81 | ESPN |
| RB | 2024 | 6.03 | 5.73 | 5.76 | Sleeper |
| RB | **2022-2024** | **6.18** | **5.91** | **5.91** | **Sleeper/ESPN** |
| WR | 2022 | 6.57 | 6.08 | 6.32 | Sleeper |
| WR | 2023 | 6.52 | 6.23 | 6.47 | Sleeper |
| WR | 2024 | 6.85 | 6.55 | 6.63 | Sleeper |
| WR | **2022-2024** | **6.64** | **6.29** | **6.47** | **Sleeper** |
| TE | 2022 | 6.49 | 6.15 | 6.29 | Sleeper |
| TE | 2023 | 6.32 | 6.08 | 6.16 | Sleeper |
| TE | 2024 | 6.18 | 6.13 | 5.99 | ESPN |
| TE | **2022-2024** | **6.33** | **6.12** | **6.15** | **Sleeper (barely)** |

**Overall (mean of QB/RB/WR/TE season scores, 2022-2024):** Ours 6.59 |
Sleeper 6.38 | ESPN 6.43. **Consensus (either source) beats us overall
under this metric.**

Full per-player-week detail: `output/backtest/fp_accuracy_simulation_gaps.csv`.
Summary table (all seasons × positions × sources): `output/backtest/fp_accuracy_simulation_summary.csv`.

## Interpretation

This is a materially different picture than our MAE-based benchmark
(`docs/ACCURACY_COMPETITION.md` cites us beating Sleeper on point MAE for
QB/WR/TE, losing only RB). Under the **ordinal, FantasyPros-style** metric —
which only rewards getting the *order* right, not the projected point
magnitude — we lag consensus at every position, most clearly at WR (+0.35
Accuracy Gap vs Sleeper) and RB (+0.27 vs both). QB is close to a dead heat
(within 0.03-0.05 of both sources across the full sample).

Why the divergence: MAE rewards well-calibrated point totals even if the
order is occasionally scrambled; the FantasyPros metric is blind to point
calibration and only cares whether player A is ranked above player B when A
actually outscored B. Our engine's ranking stability/ordering is evidently
weaker than its point calibration relative to consensus — consistent with
the existing repo finding of negative Spearman-correlation deltas vs.
Sleeper at RB/WR/TE in the `--vs-consensus` MAE report (`SpearmanR delta
(ours - cons)`: RB −0.08, WR −0.06, TE −0.08 in this same backtest run).

## Estimated leaderboard placement

Not derivable from public data — FantasyPros does not publish raw
per-expert Accuracy Gap scores, the season's z-score distribution, or a
"top-10 / median expert" score range anywhere in their FAQs or the accuracy
pages we could fetch (the leaderboard itself is a JS-rendered table with no
underlying numbers in static HTML/markdown). What we *can* say: on this
metric, entering with our current rankings would likely place us **below
median relative to Sleeper- and ESPN-caliber consensus rankings** (which
themselves are typically strong-but-not-top performers in FantasyPros'
actual competition, since they're algorithmic aggregations, not a single
sharp human analyst) — i.e. we should not expect a "most accurate expert"
result out of the gate. QB is closest to competitive; WR is the biggest gap
to close.

## Assumptions log (summary)

1. Baseline rank→points table built from our own 2022-2024 actual-points
   sample (pooled), not FantasyPros' undisclosed internal baseline.
2. Player pool uses each ranker's own list instead of a true multi-expert
   ECR (we don't have one to compare against).
3. No z-score normalization or worst-week-drop — raw mean Accuracy Gap
   across weeks 3-17 (weeks 1-2 unscored for "Ours" due to cold-start;
   week 18 excluded to match FP convention).
4. "Ours" is the walk-forward heuristic backtest engine (matches
   `export_rankings_submission.py`'s methodology), not literal historical
   Gold weekly parquet, which isn't committed for 2022-2023.
5. K/DST excluded (matches FP's own "Overall" definition, which drops them
   for consistency reasons); we don't project them in this backtest either.

## Status

2026-08-08: simulation built and run. Reuses the already-completed
2022-2024 weeks 1-18 `--vs-consensus` backtest (`backtest_half_ppr_consensus_20260808_235409.csv`)
rather than regenerating it — that run already existed in
`output/backtest/` from this same session, no further heavy computation
needed.
