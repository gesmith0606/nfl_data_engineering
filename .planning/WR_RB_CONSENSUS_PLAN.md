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
