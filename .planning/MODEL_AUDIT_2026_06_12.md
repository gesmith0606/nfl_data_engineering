# Model Audit & Improvement Session — 2026-06-12

*Goal: audit all models and push them to rival the best available. Findings ordered
by impact. Companion docs: SOTA_RESEARCH.md, FTN_DATA_SPIKE.md / FTN_BUILD_RESULTS.md,
WR_RB_HYBRID_RETRY.md, PROP_IMPLIED_DECISION.md, RANK_ORDERING_EXPERIMENTS.md (pending).*

## Headline findings

### 1. PRODUCTION BUG: nflverse spread sign inverted (fixed — dbbef92)
nflverse `spread_line` is the expected HOME margin (positive = home favored; 99.6%
moneyline agreement 2022-24). Five fantasy-side functions assumed the sportsbook
convention. Consequences since inception: implied team totals SWAPPED between
favorite and underdog in every game (live Vegas multiplier boosted underdogs,
suppressed favorites); RB run-heavy bonus fired for the wrong teams;
predicted_script_boost penalized favorites. Game-prediction stack was unaffected
(always used the correct convention). 7 regression tests pin the convention.

### 1b. PRODUCTION BUG: Vegas branch discarded all points-level tuning (fixed — 661f077)
The implied_totals branch of generate_weekly_projections re-derived
projected_points from scaled raw stats — silently discarding ceiling shrinkage,
the QB +2.3 bias correction and the low-projection floor boost. Live production
ALWAYS passes implied_totals; backtests never did (bug #2) — so live ran without
the v4.2 tuning that backtests validated (C.Kupp 2022w3: 18.92 shrunk vs 26.88
raw). Together with bug #1 (inverted Vegas), this plausibly explains the live
sanity-gate rank-gap anomalies (Jayden Daniels cons #12 vs ours #132) that were
previously attributed to model signal. Live quality should now match backtests.

### 2. EVAL-VALIDITY BUG: backtests never applied the Vegas multiplier (fixed — 6b0cce6)
`implied_totals` was gated on `--constrain`, so vegas_multiplier == 1.0 on 100% of
rows in every standard backtest — all historical consensus-gap numbers measured a
no-Vegas system while live production applied (inverted) Vegas. Residual training
baselines also exclude Vegas (consistent with old eval, INconsistent with live).
Now measuring, for the first time, whether correctly-signed Vegas helps the eval;
the outcome decides whether Vegas enters the training baseline (consistency by
inclusion) or leaves production (consistency by removal).

### 3. WR HYBRID FLIPS TO A CONSENSUS WIN (ship-candidate)
Blend-consistent retrain (the fix that shipped TE) applied to WR, evaluated through
the PRODUCTION path: WR MAE gap +0.09 → **−0.047 (we beat Sleeper)**; WR Spearman
gap −0.056 → **+0.017 (we out-rank Sleeper)**. RB hybrid: no effect — killed again.
Ship blocked only on the post-Vegas-fix retrain cascade (task #7). If confirmed +
sealed-2025 gate passes, standing becomes: **QB, WR, TE all beat consensus; RB
trails by 0.27 MAE** — 3 of 4 positions better than the free market standard.

### 4. SOTA position (external research, .planning/SOTA_RESEARCH.md)
- Spread: 52.9% OOF ATS is near the public frontier — nfelo (best transparent
  model) hits 53.7% vs CLOSING lines (≈breakeven); even elite selective systems
  are ~55%. Verdict: our spread model is roughly at par; the only honest upgrade
  is line-capture vs OPENERS (plumbing landed, c0398de + 2b97c8f review fixes;
  blocked on ODDS_API_KEY).
- Fantasy: prop-implied projections are the sharpest per-player benchmark
  (FanDuel-derived beat a top paid projector 4.76 vs 4.84). Purchase memo with
  pre-registered gates: PROP_IMPLIED_DECISION.md. RECOMMEND BUY ($29/mo).
- The top projection systems are opportunity-first (routes/TPRR × game script),
  consistent with where our residual wins come from.

### 5. FTN charting data: built, leak-clean, HOLD
Free FTN (2022+) ingested Bronze→Silver with 22 trailing features registered and
leak-gated (e2b2533). Verdict honest HOLD: lag-1 contested_rate signal (r=+0.05)
decays to noise under rolling aggregation; WR Ridge probe +0.002 MAE. Pipeline
production-ready; revisit with lag-1 features or 2022+-restricted training.
This also further prices the PFF decision: free charting ≈ exhausted.

### 6. Infrastructure shipped this session
- Conformal quantile floor/ceiling bands activated, opt-in `--conformal-bands`
  (f88e521): 10-90 band reaches ~80% coverage (was 72-75% raw).
- True-CLV plumbing: evaluate_line_capture + snapshot loader + --clv-true with
  70 tests (c0398de); review fixed convention labels and pick-at-open (2b97c8f).
- WR/RB/TE rank-ordering experiments (TPRR, spread-conditioned game script) in
  flight (opportunity-lab agent) — warned re: spread convention.

## FINAL SESSION STANDING (2022-24 matched vs Sleeper, cons≥5, n=7,009)

After the continuation round (injury-aware eval 97c8b0c, TPRR collapse bd6aeb8,
--ml route_df threading fix):

| Pos | MAE gap | Spearman gap | Path |
|-----|------|------|------|
| QB | **−0.386 (win)** | **0.000 (exact parity)** | heuristic + VEGAS_BETA + injuries |
| RB | +0.264 | −0.080 | heuristic + injuries |
| WR | **−0.075 (win)** | −0.002 (parity) | hybrid + collapses + injuries |
| TE | **−0.428 (win)** | **+0.224 (win)** | hybrid + injuries |
| **Overall** | **−0.086 (WE BEAT THE CONSENSUS)** | | (was +0.083 at session start) |

Additional fixes in the continuation: backtest never applied injury reports
(production always did; Sleeper embeds them — eval-fidelity, leak-free);
production injuries week-filter bug (season file + keep-last was row-order
dependent); --ml backtest branch dropped route_df (every hybrid eval skipped
the WR collapses production applies). TPRR collapse forward-confirms on the
2026 live season (sealed-2025 budget preserved at 5 uses).

## Open items (priority order)
1. **Task #7 remediation cascade**: graph cache regen (running) → Vegas-active
   baseline measurement (running) → blend-consistent TE+WR retrain vs the fixed
   heuristic → 2022-24 gates → ONE sealed amber-2025 confirmation → ship
   HYBRID_POSITIONS={"TE","WR"}.
2. **USER ACTION — ODDS_API_KEY** (unchanged, still the most time-sensitive):
   unlocks odds capture (calendar-critical before 2026 w1) AND the prop-implied
   evaluation (PROP_IMPLIED_DECISION.md).
3. Rank-ordering experiment verdicts + post-Vegas-fix re-confirmation of any
   gate-passers.
4. RB remains the one consensus deficit (+0.27): killed levers now include
   residuals (2x), route-rate level, yardage allowances, teammate/depth signals.
   Live levers: props blend (#2), TPRR/game-script (in flight), late-week
   freshness (process change — consensus updates Sunday morning, we project
   Tuesday: plausibly most of the RB Spearman gap).
