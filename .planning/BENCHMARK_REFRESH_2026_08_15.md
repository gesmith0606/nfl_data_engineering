# Benchmark Refresh on Repaired Data — 2026-08-15/16

Re-runs every headline accuracy claim (v4.3 audit, multi-source ESPN benchmark, FP
ordinal simulation, error decomposition) now that the three inputs documented as
broken in `.planning/SILVER_REGEN_REPORT.md` are real: `snap_pct` (was 100% NaN,
now 93-98% populated), `players/advanced` NGS/PFR/QBR columns (were 0 columns, now
88-128 real feature columns per season), and the `RB_SNAP_COLLAPSE` correction
(was a silent Bronze-snap-absence no-op, snaps now ingested 2022-2024).

**Bottom line up front: the "beats Sleeper overall" claim survives but the margin
nearly halved. The "beats ESPN overall" claim FLIPS to a wash. "Beats both sources
at WR" is FALSE now — WR is the position the data repair hurt, not helped, and the
mechanism looks like a stale-model distribution-shift bug, not a genuine accuracy
regression from more real data.**

## 0. Gate-coverage check (per `knowledge-vault/concepts/gated-experiment-coverage-check.md`)

Before trusting any number below: does `RB_SNAP_COLLAPSE` actually fire now?

- The `GATE COVERAGE: no local snap-count Bronze data found` warning that used to
  print unconditionally on every `backtest_projections.py` run **did NOT print** in
  any of the four runs below (`grep -n "GATE COVERAGE"` on each log shows only the
  *unrelated, still-open* WR route-slope-collapse warning — see caveat below).
- Firing rate, computed directly against `rb_role_signals.compute_snap_trend_signals`
  on RB-only Bronze snaps, 2022-2024, weeks 3-18 (matching the eval population):
  **193 / 4,432 RB-weeks (4.35%) trigger `snap_share_collapsing==1`** and get the
  0.60x multiplier. Non-vacuous, real, but a modest-reach lever — not the kind of
  near-zero-reach detector the concept doc warns about.
- **Still open / still a silent no-op**: the WR route-slope-collapse correction
  (`data/silver/graph_features/.../graph_route_participation_*.parquet` — PBP-derived
  route participation, out of scope for this task) is absent locally in every run
  below, and its own `GATE COVERAGE` warning fires every time. None of the WR numbers
  in this report exercise that lever; it's a separate, still-broken correction.
- **Same-vintage check**: all four backtests below ran back-to-back in this session
  (2026-08-15 22:20 - 22:46 local), same untouched Bronze/Silver on disk throughout.
  `git status --short` before/after shows zero changes to any Bronze/Silver/Gold
  path during the run window — safe from the "reused/contaminated baseline" class of
  bug.
- **Concurrency note (worth flagging, not a contamination)**: a separate concurrent
  process wrote `.planning/RETRAIN_ON_REPAIRED_FEATURES.md` and
  `.planning/ENSEMBLE_HEALTH_2026_08_15.md` plus two new model directories
  (`models/retrained_2026_08_15/`, `models/ensemble_retrained_2026_08_15/`) in this
  same working tree, timestamped 22:20-22:23 — squarely inside this session's run
  window. It explicitly avoided touching `scripts/backtest_projections.py` or
  `models/residual/` (the shipped models this task's runs actually load) "for
  concurrent-agent-safety reasons," and `git status` confirms only new/untracked
  files were added, nothing existing was modified. Its findings turn out to be
  directly relevant to §5 below — cited there, not re-derived.

## 1. Regeneration — commands run (all foreground, 3 seasons combined, 6-6.3 min each)

```
python scripts/backtest_projections.py --seasons 2022,2023,2024 --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper
python scripts/backtest_projections.py --seasons 2022,2023,2024 --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source espn
python scripts/backtest_projections.py --seasons 2022,2023,2024 --weeks 1-18 --scoring half_ppr --ml --full-features --vs-consensus --consensus-source sleeper
python scripts/backtest_projections.py --seasons 2022,2023,2024 --weeks 1-18 --scoring half_ppr --ml --full-features --vs-consensus --consensus-source espn
python scripts/benchmark_consensus_sources.py --backtest-csv <ml-fullfeatures csv> --sources espn sleeper --json-out output/backtest/consensus_benchmark_summary_MLFULL_20260815.json
python scripts/benchmark_consensus_sources.py --backtest-csv <heuristic csv> --sources espn sleeper --json-out output/backtest/consensus_benchmark_summary_HEURISTIC_20260815.json
python scripts/simulate_fp_accuracy.py
python scripts/decompose_consensus_errors.py --sleeper-csv <ml-fullfeatures matched> --espn-csv <ml-fullfeatures matched>
```

All matched-pair population sizes reproduce **exactly**: n=7,009 vs Sleeper, n=6,721
vs ESPN — same filter (`weeks 3-18, consensus ≥ 5pts, QB/RB/WR/TE`), same row counts
as every prior audit. The harness itself is unchanged; only the feature inputs are.

Note on which mode is "canonical": production/`--ml` routes **QB and RB through the
pure heuristic path unconditionally** (`HYBRID_POSITIONS = {"WR","TE"}` in
`ml_projection_router.py`) — so QB/RB numbers are byte-identical between the
heuristic-only run and the `--ml --full-features` run (verified: `-0.38591` /
`0.26360` vs Sleeper in both). Only WR/TE differ between modes, because only WR/TE
route through the hybrid residual model that consumes the repaired Silver
`players/usage`/`players/advanced` features via `--full-features`. This also
explains why heuristic-mode alone barely moved from data repair (see §3) — the
heuristic path never reads those Silver paths at all.

## 2. Headline table — canonical mode (`--ml --full-features`, matches the mode
behind the published −0.086/−0.027 numbers)

MAE gap = our MAE − source MAE. **Negative = we win.**

### vs Sleeper (n=7,009)

| Position | Old (MODEL_AUDIT_2026_06_12) | New (repaired data) | Δ (new − old) | Verdict |
|---|---:|---:|---:|---|
| QB | −0.386 (win) | **−0.386** (win) | 0.000 | unchanged (heuristic path, doesn't touch repair) |
| RB | +0.264 (lose) | **+0.264** (lose) | 0.000 | unchanged in aggregate (slice-level did shift — §4) |
| WR | −0.075 (win) | **+0.005** (flat/tiny loss) | **+0.080** | **FLIPS — no longer a win** |
| TE | −0.428 (win) | **−0.410** (win) | +0.018 | still a clear win, marginally smaller |
| **OVERALL** | **−0.086** (win) | **−0.050** (win) | **+0.036** | **still wins, margin down ~42%** |

### vs ESPN (n=6,721)

| Position | Old (CONSENSUS_BENCHMARK_MULTI_SOURCE) | New (repaired data) | Δ | Verdict |
|---|---:|---:|---:|---|
| QB | +0.186 (lose) | **+0.186** (lose) | 0.000 | unchanged |
| RB | +0.173 (lose) | **+0.173** (lose) | 0.000 | unchanged |
| WR | −0.122 (win) | **−0.038** (thin win) | **+0.084** | win shrinks ~69%, barely marketing-safe |
| TE | −0.420 (win) | **−0.410** (win) | +0.010 | essentially unchanged |
| **OVERALL** | **−0.027** (win) | **+0.009** (loss) | **+0.036** | **FLIPS — no longer a win** |

Both overall flips are driven almost entirely by WR — QB/RB are architecturally
untouched by this repair (heuristic-only path), TE moved by <0.02 either way.

## 3. Heuristic-only mode (secondary ablation, explicitly requested)

Running the exact same population WITHOUT `--ml` (so WR/TE also use the plain
rolling-average heuristic, never touching the repaired Silver advanced features)
isolates what the repair bought **outside** the hybrid model:

| Position | vs Sleeper gap | vs ESPN gap |
|---|---:|---:|
| QB | −0.386 | +0.186 |
| RB | +0.264 | +0.173 |
| WR | +0.107 | +0.074 |
| TE | +0.226 | +0.238 |
| OVERALL | +0.077 (lose) | +0.144 (lose) |

This is NOT directly comparable to the canonical numbers above (WR/TE never used
hybrid residuals in the original audit's non-`--ml` mode either), but it confirms
the mechanism: heuristic WR/TE trail consensus by a lot on their own (+0.11/+0.23
vs Sleeper) — the hybrid residual correction is what has historically made WR/TE
wins possible, and it's exactly that correction's stability that the repair
disturbed (§5).

## 4. Weeks 3-6 / RB-band decomposition — did the documented weak spots shrink?

Compared against `.planning/CONSENSUS_ERROR_DECOMPOSITION.md` (2026-08-09, 03:57 —
itself a same-day-but-pre-fix rerun of the same script/methodology, so this is an
apples-to-apples before/after on the decomposition tool specifically, distinct from
the Jun-12/Jul-11 headline docs used in §2).

### Weeks 3-6 gap (the single biggest documented weak spot) — all reliable (n≥250)

| Slice | Old gap (n) | New gap (n) | Δ |
|---|---:|---:|---:|
| RB vs Sleeper | +0.461 (529) | **+0.313** (529) | **−0.148 (better)** |
| RB vs ESPN | +0.373 (502) | **+0.228** (502) | **−0.145 (better)** |
| WR vs Sleeper | +0.350 (810) | **+0.184** (810) | **−0.166 (better)** |
| WR vs ESPN | +0.291 (763) | **+0.135** (763) | **−0.156 (better)** |
| TE vs Sleeper | +0.368 (251) | **−0.295** (251) | **−0.663 — FLIPS TO A WIN** |
| TE vs ESPN | +0.276 (254) | **−0.292** (254) | **−0.568 — FLIPS TO A WIN** |

**Every single weeks-3-6 slice improved**, several dramatically. This is the
clearest, cleanest signal in the whole refresh: early-season projections lean
hardest on the freshly-repaired NGS/snap/advanced features (thin same-season
sample, so the model needs whatever signal it can get), and the repair delivers
exactly there. TE weeks 3-6 goes from the worst slice to an outright win vs both
sources.

### RB magnitude-band tails (2nd documented weak spot)

| Band | Old vs Sleeper (n) | New vs Sleeper (n) | Old vs ESPN (n) | New vs ESPN (n) |
|---|---:|---:|---:|---:|
| <8 pts | +0.501 (553) | **+0.375** (605) | +0.297 (571) | **+0.160** (622) |
| 14+ pts | +0.503 (423) | **+0.372** (395) | +0.318 (407) | **+0.271** (384) |
| 8-14 pts | +0.122 (901) | +0.138 (877) | +0.124 (856) | +0.138 (828) |

Both tails improved 15-46% across both sources — the documented "under-project the
low end, over-project the high end" miscalibration is real but measurably less
severe now. The well-calibrated middle band (8-14) drifted slightly worse but stays
small (~0.14) and was already the position's best-behaved slice.

### Where it came from, and what offset it (RB week-band, full picture)

| Slice | Old gap | New gap | Δ |
|---|---:|---:|---:|
| RB wk3-6 vs Sleeper | +0.461 | +0.313 | −0.148 |
| RB wk7-12 vs Sleeper | +0.178 | +0.221 | **+0.043 (worse)** |
| RB wk13-18 vs Sleeper | +0.342 | +0.265 | −0.077 |

RB's aggregate gap landing unchanged at +0.264 (§2) isn't "nothing moved" — weeks
3-6 and 13-18 improved, weeks 7-12 got mildly worse, and the n-weighted average
happens to net out almost exactly where it started. Worth flagging: this is also
partial evidence of run-to-run noise in this harness independent of the repair —
the Aug-9 03:57 pre-fix rerun of this same decomposition tool already showed RB's
own overall gap had drifted to +0.319 vs the Jun-12 +0.264 (attributed in that doc
to "normal retrain/data refresh," not any lever) — so a ~0.05-pt swing on RB's
aggregate gap between any two nominally-identical runs is within observed noise,
and the +0.264 vs +0.264 exact match here should be read as "no evidence of a
change," not "proof of no change."

## 5. Biggest surprise — the WR hybrid model looks stale, not just "less lucky"

The WR degradation isn't a diffuse drift — it's concentrated in outlier blowups
consistent with a **model trained on all-NaN/absent features now seeing real
values it was never calibrated against**:

```
C.Wilson  WR  2023 W16  projection_source=hybrid  proj=75.55  actual=5.7  error=+69.8
```

A 75-point WR projection is not a "the market moved and we didn't" miss — it's a
model output blowing up. `models/wr_residual.joblib` (and `te_residual.joblib`) are
dated **2026-06-24**, i.e. trained back when `players/advanced` NGS/PFR/QBR columns
were either absent or 100%-NaN (per `SILVER_REGEN_REPORT.md`, fixed 2026-08-09/10).
That frozen Ridge model has never seen a real, non-imputed value for ~half its
input columns; at inference on repaired data it's now extrapolating into territory
its training never covered.

This is independently corroborated by the concurrent `RETRAIN_ON_REPAIRED_FEATURES.md`
investigation running in this same repo (§0): they retrained WR/TE residual models
from scratch on the exact same repaired features and found the **retrained** WR
model is *also* 0.111 MAE worse than the currently-shipped one, with 6x the bias
(+0.53 vs +0.09) — recommending KEEP SHIPPED. That result plus this session's
C.Wilson blowup together suggest the WR hybrid's problem is not simply "give it a
retrain" — something about how WR residuals interact with the newly-real NGS/snap
feature set (scale, leakage, or a genuinely noisier signal at that position) needs
architectural attention, not just a data refresh or a rote retrain. QB/RB, by
contrast, are NOT in production's `HYBRID_POSITIONS` today, and that same
concurrent investigation found their retrained hybrids would be decisive wins if
shipped (−0.685 / −0.189 MAE vs heuristic) — a real opportunity this repair
unlocked, orthogonal to the WR problem. Out of scope to ship here (that's the
other task's call), but worth the coordinator's attention.

## 6. FantasyPros ordinal simulation — unchanged, "we trail everywhere" still holds

Re-ran `scripts/simulate_fp_accuracy.py` fresh (auto-picks the latest plain
heuristic `--vs-consensus` CSV, matching the original methodology exactly — see
`FP_ACCURACY_SIMULATION.md`, which also used the non-`--ml` backtest).

| Position | 2022-2024 Ours (old → new) | Sleeper | ESPN | Winner |
|---|---|---:|---:|---|
| QB | 7.21 → **7.21** | 7.19 | 7.18 | ~Tie (unchanged) |
| RB | 6.18 → **6.17** | 5.92 | 5.91 | Sleeper/ESPN (unchanged) |
| WR | 6.64 → **6.64** | 6.29 | 6.47 | Sleeper (unchanged) |
| TE | 6.33 → **6.34** | 6.12 | 6.15 | Sleeper (unchanged) |

Movement is within noise (≤0.01) at every position — expected, since this
simulation runs on the heuristic-only backtest, which §3 confirms never touches
the repaired Silver features. **The published claim "consensus (either source)
beats us overall" under the ordinal metric stands exactly as documented.** This
is a genuinely different problem (ranking stability, not point-MAE calibration)
that data repair does not address.

## 7. Claims audit — what the public accuracy page says vs what's true now

| Claim (as currently published) | Status | Action |
|---|---|---|
| "Beats both Sleeper and ESPN overall, 2022-2024" | ⚠️ **HALF FALSE** — still beats Sleeper (−0.05), now **loses to ESPN** (+0.01) | **Update immediately** — drop or caveat the ESPN half |
| "Best-in-class TE: ~0.42 MAE better than both" | ✅ still true (−0.41 both) | keep, update 0.42→0.41 for precision |
| "Beats both sources at WR" | ❌ **FALSE** — loses to Sleeper (+0.005), barely beats ESPN (−0.038, was −0.122) | **Pull this claim now** |
| "Beats Sleeper at QB by 0.39" | ✅ true, unchanged | keep |
| (Implicit) FantasyPros ordinal competitiveness | Not currently claimed, correctly — §6 confirms we'd still be below-median | no action, don't add this claim |

**Loud flag for the coordinator:** two of the five marketing-safe bullets in
`CONSENSUS_BENCHMARK_MULTI_SOURCE.md` ("we beat BOTH sources overall", "beats both
sources at WR") are no longer accurate as of this refresh and are live on the
public accuracy page. This is a straightforward "the ground truth changed,
update the copy" situation, not a code bug — but it needs the same urgency as a
bug because it's a factual claim currently being shown to users.

## 8. What the data repair bought / cost, net

**Bought:**
- Weeks 3-6 (the single biggest documented weak spot): meaningfully better across
  RB/WR/TE and both sources, TE flips to an outright win there.
- RB magnitude-band tails: 15-46% smaller miscalibration at both extremes.
- Real, non-vacuous `RB_SNAP_COLLAPSE` firing (4.35% of RB-weeks) — the correction
  that used to be silently inert now genuinely runs, even though its net aggregate
  effect on RB happens to be a wash this time.
- An unshipped opportunity: QB/RB hybrid residual models, if retrained + shipped
  (separate task, see §5), would be decisive wins per the concurrent investigation.

**Cost:**
- WR overall accuracy vs both sources — real regression, concentrated in outlier
  blowups from the currently-shipped WR/TE residual model being fed feature
  distributions it was never trained on (§5). This is fixable (retrain or
  architecture fix) but is NOT fixed by this task and should not be read as "more
  real data made WR worse" — it's a stale-model artifact the repair exposed.
- Two public marketing claims now false (§7).

## 9. Recommendation

1. **Update the public accuracy page now** to drop "beats both sources overall"
   and "beats both sources at WR" per §7 — keep "beats Sleeper overall," "beats
   Sleeper at QB," and "best-in-class TE."
2. **Do not ship the concurrent WR/TE retrain** (§5) — it's worse than what's
   currently live, per that investigation's own pre-registered gate. The
   currently-shipped WR/TE hybrid, run against today's repaired features, is the
   one with the accuracy problem; a same-recipe retrain didn't fix it either.
3. **Follow-up worth prioritizing**: diagnose why the shipped WR residual model
   destabilizes on real (non-imputed) NGS/snap inputs — start from the C.Wilson
   2023w16 case in this report. Candidates: unscaled feature magnitude at
   inference vs training-time NaN-median imputation, a leaky/collinear repaired
   feature, or the Ridge model's coefficients simply being wrong for a feature
   distribution it never saw non-degenerate values for during training.
4. **Separately worth prioritizing** (not blocking the above): the QB/RB hybrid
   retrain opportunity flagged in the concurrent investigation — real upside,
   orthogonal to the WR problem, currently sitting in `models/retrained_2026_08_15/`
   unshipped.
5. Keep the FantasyPros ordinal story as-is — nothing here changes it, and no new
   claim should be added from this metric.

## Artifacts

- `output/backtest/backtest_half_ppr_consensus_20260815_222619.csv` — heuristic, sleeper-join
- `output/backtest/backtest_half_ppr_consensus_20260815_223232.csv` — heuristic, espn-join
- `output/backtest/backtest_half_ppr_ml_fullfeatures_consensus_20260815_224006.csv` — canonical, sleeper-join
- `output/backtest/backtest_half_ppr_ml_fullfeatures_consensus_20260815_224635.csv` — canonical, espn-join
- `output/backtest/consensus_benchmark_summary_MLFULL_20260815.json` — canonical combined summary
- `output/backtest/consensus_benchmark_summary_HEURISTIC_20260815.json` — heuristic combined summary
- `output/backtest/consensus_matched_{sleeper,espn}_half_ppr_20260816_024810.csv` — canonical matched pairs (input to §4)
- `output/backtest/fp_accuracy_simulation_summary.csv`, `fp_accuracy_simulation_gaps.csv` — §6
- `output/backtest/decompose_*` (regenerated by `decompose_consensus_errors.py`, this run) — §4
