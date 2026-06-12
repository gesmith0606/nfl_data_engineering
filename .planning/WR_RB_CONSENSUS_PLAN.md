# WR_RB_CONSENSUS_PLAN.md — Beat Sleeper Consensus at RB and WR

*Planned 2026-06-10. Child plan of `ELITE_MODELS_PLAN.md` (sharpens items 2.1/2.2 with head-to-head evidence). Primary metric: per-position consensus gap on matched player-weeks, NOT raw MAE.*

## Where We Stand (measured, not guessed)

Head-to-head vs Sleeper consensus, matched player-weeks, 2022-24 w3-18, half-PPR, consensus ≥ 5 pts.

**CORRECTED BASELINE (2026-06-10, post Workstream A dedup fix —
`output/backtest/consensus_matched_half_ppr_20260610_220524.csv`, n=7,009 at cons≥5):**

| Pos | n | MAE ours | MAE consensus | Gap |
|-----|------|------|------|--------|
| QB  | 1250 | 6.16 | 6.40 | **−0.24 (we win)** |
| TE  |  917 | 4.76 | 4.46 | **+0.30 (we lose)** |
| RB  | 1877 | 5.69 | 5.33 | **+0.36 (we lose)** |
| WR  | 2965 | 5.26 | 5.04 | **+0.21 (we lose)** |

The original baseline (n=10,912 file) contained 842 duplicate rows from an abbreviated-name join
fan-out (Tyreek/Taysom Hill both "T.Hill"); dedup flipped TE from apparent −0.17 win to +0.30 loss
and is confirmed filter-independent. TE remediation is out of scope for this plan (WR/RB focus) but
inherits workstreams B/D. Pre-fix rank-corr/top-24 numbers (RB 0.543 vs 0.610, WR 0.457 vs 0.516)
need recomputation on the corrected file before use as gates.

## Gap Decomposition — Where the Losses Actually Are

**1. The entire gap lives in disagreement cases.** Where we agree with consensus (±1.5 pts; ~55% of rows), gap ≈ 0.00. Where we disagree by 4+ pts, consensus is right:

| Bucket | RB gap | RB n | WR gap | WR n |
|--------|--------|------|--------|------|
| ours >> cons (+4) | +2.23 | 161 | +2.55 | 111 |
| ours << cons (−4) | +1.60 | 166 | +1.12 | 180 |
| ours > cons (+1.5..4) | +0.43 | 609 | +0.57 | 702 |
| agree (±1.5) | +0.04 | 1596 | 0.00 | 2694 |

Disagreement buckets account for ~0.29 of the 0.30 RB gap. **We don't need a better model on agreed cases — we need to stop being confidently wrong on ~25% of rows.**

**2. WR gap is almost entirely early-season.** w3-6: +0.50 | w7-11: +0.14 | w12-18: **+0.04 (parity)**. The w3-6 bucket alone is ~70% of the WR gap. RB gap persists all season (+0.40 → +0.26) — structural, not just ramp-up.

**3. Named failure modes (worst disagreements, all verified in the matched CSV):**

| Failure mode | Examples | Root cause in our code |
|---|---|---|
| **Star returns from IR/suspension projected near zero** | CMC 2024 w11 (ours 3.8, cons 19.5, actual 12.6 — flagged `is_rookie_projection=True`!), Hopkins 2022 w8, Kupp 2023 w6, Kamara 2023 w5 | Rolling windows empty after absence → falls through to rookie fallback. A 3-time All-Pro is treated as an unknown rookie. |
| **Established starters buried after 1-2 quiet weeks (w3 cluster)** | D.Smith 2022 w3 (ours 0.5, cons 9.6, actual 26.9), St. Brown 2024 w3 (ours 3.5, cons 14.4, actual 17.0), M.Harrison 2024 w3, T.Higgins, D.London | WR recency weights are std=1.00 — two quiet weeks IS the whole signal. No prior-season/preseason prior blended in. Consensus carries preseason expectations. |
| **RB role loss not detected (teammate returns)** | Z.Moss 2023 w5/w9/w10 (J.Taylor back; ours 13-17, actual 0-3 range), A.Gibson 2022 w3 (B.Robinson returned), D.Jackson 2022 w8 | Stale rolling averages from the fill-in window; no teammate-status awareness. |
| **RB role gain not detected (teammate leaves)** | D.Foreman 2022 w8 (CMC traded; ours 1.6, cons 10.4, actual 29.8), Charbonnet 2024 w15 (K9 hurt) | Same — no opportunity-redistribution signal. We HAVE `src/graph_injury_cascade.py` but it doesn't drive the heuristic. |
| **Harness data bug** | T.Hill appears twice 2023 w3 MIA with different actuals (26.2 / 2.6) | Join duplication in consensus matching — must fix before trusting per-row analysis. |

## RESULTS (2026-06-11 — Workstreams A, B, C complete)

Consensus gap (matched, cons≥5, 2022-24 w3-18, half-PPR; heuristic path):

| Pos | Session start | After B (veteran priors) | After B+C (snap collapse) | Total movement |
|-----|------|------|------|------|
| QB  | −0.22 win | −0.31 | **−0.32 (bigger win)** | −0.10 |
| RB  | +0.44 | +0.37 | **+0.27** | **−0.17** |
| WR  | +0.25 | +0.13 | **+0.12** (w3-6: +0.78 → +0.38) | **−0.13** |
| TE  | +0.33 | +0.25 | **+0.23** (hybrid path separately wins −0.38) | −0.10 |

Shipped (uncommitted): veteran prior blend (all positions, n_full=5 steep=0.7 decay=1.0,
`USE_VETERAN_PRIOR_BLEND`), veteran-never-rookie routing (CMC 2024 w11: 3.81→15.83,
is_rookie False), RB snap-collapse 0.60x (`USE_RB_SNAP_COLLAPSE`; Z.Moss w8-10 14-17→7.7-10.2).
Killed with evidence: both teammate signals (+0.004/+0.006 joint, gate 0.02), both depth-rank
signals. Full suite 2225 passed / 0 failed. Remaining gap to close: workstreams D (route-rate
for WR rank ordering) and E (yardage allowances); rank-corr gates not yet re-measured.

**Post-review fixes (2026-06-11):** code review found the snap-collapse was eval-only —
production `generate_projections.py` never passed snap_counts_df (now loads + passes it;
verified live: blend rerouted 2 players, collapse fired on 6 RBs, 2024 w11). All ML-router
call sites now thread weekly_df/snap_counts_df; missing inputs warn once instead of silently
skipping; priors/name-map identity-cached (backtest speedup); baselines single-sourced from
projection_engine; is_veteran_return exposed in output.
**TE hybrid re-validation COMPLETE (2026-06-11) — GATE PASSED after architectural fix:**

| Run | TE gap | Notes |
|-----|--------|-------|
| Pre-blend (2026-06-10, reference) | −0.38 | We won by 0.38 |
| Post-blend + old residual (2026-06-11, `backtest_half_ppr_ml_consensus_20260611_191929.csv`) | +0.15 | We lose — degraded +0.53 |
| Post-retrain (same arch, 2026-06-11, `consensus_matched_half_ppr_20260611_193110.csv`) | +0.25 | Worse — discarded |
| **Blend-consistent retrain (2026-06-11, `consensus_matched_half_ppr_20260611_200019.csv`)** | **−0.44** | **GATE PASSED ✅** |

Gate was ≤ −0.35; result is −0.44 (improved further beyond the −0.38 reference by 0.06). **SHIPPED.**

Root cause (fixed): `train_and_save_residual_models` called `compute_heuristic_baseline` on raw
Silver features without passing `weekly_df` — the veteran blend was never applied during training.
Residual model learned offsets against the unblended heuristic; at inference the blended baseline
was higher (mean +3.1 pts for the ~20% of TE rows affected), causing systematic over-correction.

**Fix applied (Primary — Option 1):**
1. `compute_heuristic_baseline` in `projection_engine.py` extended with optional `weekly_df`
   parameter.  When provided and `USE_VETERAN_PRIOR_BLEND=True`, applies `apply_veteran_prior_blend`
   per unique (season, week) group before computing the heuristic — exact same logic as
   `generate_weekly_projections` uses at inference.
2. `compute_production_heuristic` in `unified_evaluation.py` passes `weekly_df` through.
3. `train_and_save_residual_models` in `hybrid_projection.py` loads Bronze weekly data (incl.
   prior season) and passes it to `compute_production_heuristic`, making training residuals
   numerically consistent with production.
4. Version stamp: `heuristic_version: "v4.2+blend"` (new), router updated to accept both
   `"v4.2"` and `"v4.2+blend"` for HYBRID routing.
5. Pre-blend backup files preserved: `te_residual.joblib.pre_blend_backup`,
   `te_residual_meta.json.pre_blend_backup`.

Fallback (Option 3) not needed — primary fix cleared the gate on first retrain.

**New TE metrics (2022-24, w3-18, half-PPR, --ml path, consensus ≥5):**
- TE MAE: 4.02 (ours) vs 4.46 (Sleeper) → gap **−0.44** ✅
- TE Spearman: 0.481 (ours) vs 0.253 (Sleeper) → delta **+0.227** ✅
- TE Top-12 hit rate: 0.799 (ours) vs 0.738 (Sleeper) → delta **+0.061** ✅
- Model file: `models/residual/te_residual.joblib` (ridge, alpha=0.001, n=8349, 60 features)
- All 2259 tests pass (0 failed).

### Rank-ordering gates re-measured (2026-06-11)

On the deduped files (pre-blend `20260610_220524` vs post-blend `20260611_101631`; cons≥5,
mean within-position-week Spearman over weeks with ≥10 players; top-12 QB/TE, top-24 RB/WR
hit rate; 48 weeks each, 0 duplicate player-weeks in both):

| Pos | Spearman ours pre→post | Spearman cons | Rank gap post | Top-N ours pre→post | Top-N cons | Top-N gap post |
|-----|------|------|------|------|------|------|
| QB  | 0.326 → 0.343 | 0.370 | **−0.027** | 0.595 → 0.602 | 0.599 | **+0.003** |
| RB  | 0.359 → 0.373 | 0.453 | **−0.080** | 0.727 → 0.735 | 0.753 | −0.017 |
| WR  | 0.336 → 0.349 | 0.405 | **−0.056** | 0.552 → 0.553 | 0.568 | −0.015 |
| TE  | 0.166 → 0.178 | 0.253 | **−0.075** | 0.710 → 0.710 | 0.738 | −0.028 |

WR w3-6 Spearman (the named weakness): ours 0.203 → **0.254** vs consensus 0.391 (gap −0.189 → −0.137; 12 weeks).

**Interpretation:** the blend+collapse ship improved rank ordering, not just MAE — every position
gained +0.012 to +0.017 Spearman with consensus fixed, the biggest single move being WR w3-6
(+0.051), and QB top-12 hit rate now edges consensus. But the A-grade gate (rank corr within 0.02
of consensus) is met nowhere: QB is closest at −0.027; RB (−0.080), TE (−0.075), and WR (−0.056)
remain well short — consensus's rank-ordering edge is 3-4x the gate at RB/WR/TE, so workstreams
D (route rate) and E (allowances) must carry the rest. Note the pre-fix numbers quoted above
(RB 0.543 vs 0.610, WR 0.457 vs 0.516) came from the duplicated file with a different
aggregation and should not be compared to these; this table is the new baseline for gates.

## Workstreams (ranked by expected gap closure ÷ effort)

### A. Harness integrity fix — 0.5 day, do first
Dedup the consensus join (T.Hill double-match — likely name-resolver collision on abbreviated names). Re-run the matched eval; re-baseline the gap table above. All later gates measure against the corrected baseline.
**Gate:** zero duplicate (player_id, season, week) rows; baseline re-printed.

### B. Veteran prior blending (early-season + return-from-absence) — 2-3 days. HIGHEST VALUE.
One mechanism fixes the two biggest failure modes:
1. Compute a **per-player prior**: previous-season per-game half-PPR rate (and per-game usage), decayed toward positional baseline for age/team-change.
2. Blend: `proj = w(n_recent) * rolling + (1 - w(n_recent)) * prior` where `n_recent` = games played in lookback window. Full rolling weight by ~4-5 games played; mostly prior at 0-1 games.
3. **Return-from-absence routing:** player with ≥1 prior NFL season must never hit the rookie fallback (`is_rookie_projection` misfire on CMC). Route to prior-blend instead, with an optional first-week-back discount (sweep it).
4. Implement as lab-sweepable parameters in `scripts/experiment_heuristic_lab.py` (cached-sweep infra exists); production in `src/projection_engine.py`.

**Expected:** kills most of WR w3-6 gap (~0.13 of 0.19) + the ours<<cons RB tail. Plausibly takes WR to parity alone.
**Gate:** WR consensus gap ≤ +0.05 on 2022-24 (from +0.19); no regression w7-18; QB/TE wins preserved. Kill: <0.05 WR gap improvement after sweep → revisit decay shape before abandoning.

### C. RB role-change detection (teammate status + depth chart) — 3-5 days

> **VALIDATED 2026-06-11** (31/31 tests; `output/backtest/rb_role_signal_validation.csv` in worktree, corrected CSV, n=2,814 RB rows):
> - **SHIP: `snap_share_collapsing`** (trailing 2-wk vs prior 2-wk snap-share delta) at 0.60x multiplier → est **+0.032 RB MAE** (clears 0.02 gate). Catches Z.Moss 2023 w8-10 over-projections. Distinct mechanism from the killed route-rate multiplier (velocity of collapse, not usage level).
> - **HOLD, re-evaluate jointly with Workstream B:** `rb_better_teammate_out` (+0.004), `rb_better_teammate_returning` (+0.009) — mechanisms correct (Charbonnet 2024 w15 fires; Foreman 2022 w8 caught via depth-rank instead since trades aren't injury-report events) but Bronze injury data misses holdouts/trades → recall too low standalone.
> - **KILL: `depth_rank_improved` (+0.002), `depth_rank_worsened` (+0.015)** — below gate, weak precision; snap trend subsumes demotions. Revisit depth_rank_improved only with rank-1 gating.
> Integration pending: apply snap_share_collapsing 0.60x in projection_engine AFTER Workstream B lands (same file).
RB is a *who-gets-the-work* problem. Three lagged, leak-safe signals:
1. **Teammate-status adjustment:** for each RB, weekly status of higher/lower depth-chart RBs on own team (depth_charts Bronze, committed per TD-08; injuries Bronze). Teammate OUT → redistribute opportunity up; teammate RETURNING → haircut the fill-in. Wire `src/graph_injury_cascade.py::compute_redistribution` output into the heuristic as a multiplier candidate.
2. **Snap-share trend:** trailing 2-week snap-share delta (snap_counts Bronze) — role changes show in snaps a week before points. Shrink projection toward prior when snap share is collapsing (Z.Moss case).
3. **Depth-chart rank this week vs rank during the rolling window** — direct staleness detector.

**Expected:** the RB disagreement buckets (ours>>cons + ours<<cons ≈ 0.21 of the 0.30 gap) are exactly these cases.
**Gate:** RB consensus gap ≤ +0.10 (from +0.30) AND RB rank corr ≥ 0.58 (from 0.543). Kill per-signal: any multiplier <0.02 MAE in lab sweep → drop that signal, keep survivors.

### D. Route-participation rate (WR usage trend) — ~1 week (= ELITE 2.2)
Per-player share of team dropbacks on field from `data/bronze/pbp_participation` (dense 2020-25). Trailing 4-week route rate + WoW delta as heuristic multiplier candidates + future WR-hybrid features. New `src/graph_route_participation.py` following `src/graph_qb_wr_chemistry.py` pattern; register in `scripts/compute_graph_features.py`; must pass `detect_leakage`.
**Gate:** WR consensus gap improvement ≥0.03 beyond workstream B; route-rate vs snap-share sanity corr ≥0.8. Kill: <0.02 → web content only.

### E. Opponent-adjusted yardage allowances — ~1 week (= ELITE 2.1, demoted)

> **KILLED 2026-06-11** (worktree agent-abdc6dd56547d7a23; 50-config sweep, 18 tests passing):
> position-split opponent-adjusted trailing allowances (7 stat-types, strictly lagged,
> league-week-mean adjusted) moved MAE <0.002 at every position vs the 0.02 kill threshold.
> Root cause: trailing yardage-allowed correlates only ~0.08 with next-week actuals, and the
> remaining WR/RB gap lives in who-has-the-role disagreement cases, not defense-quality cases.
> **Feeds ELITE 3.2 (PFF ROI):** the free version of matchup-allowance data measurably carries
> <0.001 MAE per position — any PFF purchase must justify itself against this, not assumptions.
> Experiment code preserved in the worktree branch (build_yardage_allowances +
> sweep-yardage-allowances + tests) for optional salvage as a lab-only commit.
Position-split trailing allowances (rush vs receiving). Run AFTER B-D: matchup sharpening can't fix being wrong about who has the role, and the agree-bucket gap (where matchup would help) is already ≈ 0.
**Gate:** ≥0.03 CV MAE + consensus-gap narrowing. Kill: <0.02 → revert.

## Sequencing & Discipline

| Order | Item | Effort | Cumulative target |
|---|---|---|---|
| 1 | A. Harness dedup | 0.5 d | Trustworthy baseline |
| 2 | B. Veteran priors + return routing | 2-3 d | WR gap +0.19 → ≤ +0.05 |
| 3 | C. RB role-change signals | 3-5 d | RB gap +0.30 → ≤ +0.10 |
| 4 | D. Route-rate proxy | 1 wk | WR gap → ≤ 0 (parity or win) |
| 5 | E. Yardage allowances | 1 wk | Residual polish both positions |

**Rules carried from ELITE_MODELS_PLAN:** select on 2022-24 CV, confirm on amber-2025 at most once per shipped change; every feature passes `assemble_player_features.py --validate`; lab sweeps in `scripts/experiment_heuristic_lab.py` gate all multiplier changes; consensus gap is the primary metric (raw MAE secondary). No new model architectures — every workstream above is new *information*, not new fitting.

**Definition of done (A grade):** RB and WR matched-MAE ≤ Sleeper consensus AND rank corr within 0.02, on 2022-24 backtest, confirmed once on amber-2025. (A+ = sustained over live 2026 w3-18 per ELITE 3.1.)
