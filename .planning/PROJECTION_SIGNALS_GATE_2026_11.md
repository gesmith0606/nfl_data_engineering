# Projection signals gate (pre-registered) - 2026-11-16

Status: **protocol only, no modelling, no result below.** Written before any
candidate is built so the bar cannot move after the numbers are seen. The four
candidates come from the orchestrator's plan; "first-read target share" is
listed because it was named, and is blocked on data.

## Common protocol (applies to every signal)

**Baseline.** The board production would publish without the signal: the
heuristic engine + Sleeper anchor + dispersion shrink (+ residual only where the
serve-time coverage guard lets it run), regenerated point-in-time with data
truncated at W-1 (`.scratch`-style replay: live Sleeper injury statuses stubbed;
see PR 3's replay-fidelity section for how close the laptop replay is to the
runner). A signal is evaluated as a change to that board, never against a naive
average.

**Population.** QB/RB/WR/TE player-weeks that played, consensus (Sleeper
half-PPR) >= 5 (`consensus_metrics.apply_consensus_filter`), scored against
ACTUAL half-PPR points. Never against the consensus or against anything the
signal blends toward.

**Splits (fixed now).**
- Fit/selection: 2022-2024 weeks 3-18, leave-one-season-out (3 folds). Report
  every fold.
- Held-out 1: 2025 weeks 3-18, touched once.
- Held-out 2 (forward): 2026 weeks 10-18, scored as they complete; nothing fitted
  on them. 2026 weeks 2-9 are reported as a development read, not as evidence.
- Every table states n. Per-position results below n = 150 matched rows are
  reported but cannot SHIP.

**Metrics.** Primary: MAE vs actuals, per position and pooled. Secondary:
within position-week Spearman (`consensus_metrics.compute_spearman_rank_corr`),
top-12/24 hit rate. Uncertainty: player-week bootstrap, 2,000 draws, 95% CI on
the MAE difference.

**SHIP bar (all must hold, per position the signal touches).**
1. MAE improves by >= 0.03 pts on held-out 1 AND held-out 2 (once it has >= 80
   matched rows) AND on the later development weeks (2026 weeks 6-9) taken alone.
2. The 95% bootstrap CI of the MAE difference on held-out 1 excludes 0.
3. Spearman does not fall by more than 0.005.
4. The signal fires on >= 5% of the position's matched rows (a lever that
   changes nothing is not a result; confirm firing from the replay log first).
5. Every input is available at the moment the board is built (Tuesday 09:13 UTC
   cron for the published board; Sunday refresh for the lineup board). Anything
   that needs the Wednesday-Friday official injury report or a same-week snapshot
   is evaluated on the Sunday board only and says so.
Otherwise **HOLD**. Opposite-sign results between folds are a **REJECT**, not a
borderline HOLD (precedent: `EP_FEATURES_GATE.md`).

**Retire rule.** A signal whose input cannot exist in-season is not repaired,
it is listed for removal (precedent: route participation, PR 3).

## 1. ffopportunity expected points (expected minus actual)

- **Source.** `ffverse/ffopportunity` release `latest-data`: `ep_pbp_pass_{season}`
  and `ep_pbp_rush_{season}` (parquet), CC BY-SA 4.0 data. Ingest and Silver
  aggregation exist: `scripts/ingest_ffopportunity.py`,
  `data/silver/ffopportunity_features/season=2016..2025` (2026 not ingested).
- **In-season?** **Yes.** Checked 2026-11-16: `ep_pbp_*_2026` assets were last
  updated 2026-11-16T14:00Z (Monday). So at the Tuesday 09:13 UTC cron the file
  holds games through Sunday; Monday night's game may be missing. Required
  pre-check before any use: share of the previous week's games present in
  `ep_pbp` at cron time must be >= 95%; below that the lag is W-2.
- **Already tested, differently.** As trailing features inside the residual
  models: HOLD/REJECT every position (`.planning/EP_FEATURES_GATE.md`,
  2026-08-21: RB and WR sealed-2025 -0.038/-0.036 worse, QB gain was volume,
  TE worse). That does not test the use below.
- **Candidate (exact).** `ep_gap_roll6` = mean over the player's last <= 6 games
  (strictly before W) of (actual half-PPR points - expected half-PPR points).
  Adjusted board = board - beta_pos x `ep_gap_roll6`, beta_pos fitted per position
  on 2022-2024 (leave-one-season-out), clipped to +/-2.5 pts, applied before the
  anchor/shrink stages. Positive gap = over-performing expectation = regress down.
  Expected points recomputed in half-PPR from the Silver components (the release
  is standard scoring; reception bonus added from expected receptions).
- **Comparison.** Baseline board vs adjusted board, common protocol.
- **Sample.** Sleeper-consensus >= 5 player-weeks, weeks 3-18 (counted from
  `data/silver/external_projections`, before the played filter): 2022 2,722,
  2023 2,651, 2024 2,689, 2025 2,770 per season (per season: QB ~480, RB
  690-770, WR 1,090-1,140, TE 340-430). Fit pool 2022-2024 = 8,062; held-out 1 =
  2025 = 2,770; 2026 w2-9 development n = 1,439 (replay population).
- **Kill early.** If `ep_gap_roll6` explains < 1% of baseline residual variance
  in the 2022-2024 folds, stop (no fit needed).

## 2. First-read target share

- **Source.** None free. First-read data comes from charting vendors (PFF,
  Fantasy Points Data Suite). The free charting available in the repo (nflverse
  FTN, `data/bronze/ftn_charting`, 2022+) has no first-read field (see
  `.planning/FTN_DATA_SPIKE.md`); NGS has separation/cushion but no read order.
- **In-season?** **No** from any source this repo can ingest without a paid
  subscription.
- **Status: BLOCKED-DATA. No work scheduled, no proxy under this name.**
  Substituting target share, air-yards share or WOPR and calling it first-read
  would be a different (already-available) feature; test those under signal 3 or
  as plain features, not here.
- **Unblock condition.** A point-in-time per-player-game first-read target count
  for 2022-2025 plus weekly 2026 delivery before the Tuesday cron. If that
  appears, evaluate with the same template as signal 1 (lagged roll-6 share, one
  coefficient per position, same bars). Decision for George: PFF/Fantasy Points
  subscription (his call).

## 3. RB receiving role

- **Source.** In-repo and in-season: Bronze `player_weekly` (targets,
  receptions, receiving yards), Bronze `snap_counts` (`offense_pct`), depth
  charts. Route participation is NOT available in-season (the reason the WR
  route levers are off), so "role" is defined without routes.
- **In-season?** **Yes**, all inputs are written weekly and are known by Tuesday.
- **Candidate (exact).** For each RB, with games strictly before W:
  `rb_tgt_share_roll4` = RB targets / team targets (mean of last <= 4 games);
  `rb_tgt_per_snap_roll4` = RB targets / offensive snaps. Role flag
  `receiving_back` = top-quartile `rb_tgt_per_snap_roll4` among RBs with >= 25%
  snap share. Adjustment: scale `proj_receptions` and `proj_receiving_yards` of
  flagged RBs by (1 + g), g per position-role fitted on 2022-2024
  (leave-one-season-out), clipped to [-0.25, +0.25]; mirror `-g'` for the
  non-receiving complement. Half-PPR makes receptions 0.5 each, so the effect is
  on `projected_points` through the reception and yardage terms.
- **Comparison.** Baseline vs adjusted, RB only; secondary: reception MAE
  (actual vs `proj_receptions`) must improve too, so a points gain is not a
  yardage fluke.
- **Sample.** RB rows with cons >= 5: 691-771 per season (2022-2025, w3-18),
  2,138 in the 2022-2024 fit pool, 771 in held-out 1; flagged share expected
  15-25% (so ~110-190 flagged rows in held-out 1, near the n >= 150 floor: the
  per-position verdict may be capped at HOLD by n alone, and is reported as
  such); 2026 w2-9 development n = 399. The RB gap is the largest open deficit
  vs Sleeper in the 2026-06 audit (+0.26), which is why it is on the list.
- **Kill early.** If flagged RBs' mean (actual - baseline) residual differs from
  unflagged by < 0.5 pts in the 2022-2024 folds, stop.

## 4. Injury-designation expectation

- **Source.** Official reports: Bronze `players/injuries` (`report_status`,
  `practice_status`; nflverse, 2016-2025 = final weekly report; 2026 has daily
  snapshots since 2026-09-23). Live: Sleeper registry designations (no history
  archive, so no point-in-time Sleeper statuses before 2026-09-23).
- **In-season?** Partly. The official report for week W is published
  Wednesday-Friday, **after** the Tuesday 09:13 UTC cron; on Tuesday only Sleeper
  designations and last week's report exist. So this signal is evaluated on the
  **Sunday refresh board** (final Friday report), and separately reported for a
  Tuesday-available variant using last report + Sleeper live designation, 2026
  only.
- **Candidate (exact).** Replace the fixed `INJURY_MULTIPLIERS`
  (Questionable 0.85, Doubtful 0.50, Out/IR 0.0) with empirical expected-value
  multipliers `m(status, practice_trail, position)` = E[actual points] / E[
  uninjured baseline points] over the 2019-2024 designated player-weeks
  (practice trail = best of the Wed/Thu/Fri statuses; <= 6 cells per position,
  shrunk to the status-level mean when a cell has < 40 rows).
- **Comparison.** MAE on player-weeks WITH a designation (and pooled), baseline
  multipliers vs empirical multipliers, scored on rows that played AND rows that
  did not (a did-not-play row is an actual of 0 and must be included; scoring
  only players who played, as the cons>=5 population does, selects away the
  cases the multiplier exists for).
- **Sample.** 2025 skill-position injury rows: 1,828 = 444 Out, 371
  Questionable, 26 Doubtful, 987 with no game status (practice-only listings).
  Doubtful (26) is below the 40-row cell floor and is pooled with Out/Questionable
  by the shrinkage rule; Out rows are never in the cons>=5 played population, so
  their evaluation is the did-not-play scoring above. 2026 w2-9 development uses
  the daily snapshots (n to be counted at run time).
- **Bar addition.** MAE on designated rows improves by >= 0.15 pts (the effect
  is concentrated there; 0.03 pooled is unreachable by construction), on both
  held-out sets, with n(designated, held-out 1) >= 300.

## What is not in this PR
No model is fitted and no board changes. The first step after merge is the
firing/availability check for each signal (the SHIP bar's item 4 and the data
timing checks), run on the faithful replay, before any coefficient is fitted.
