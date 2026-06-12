# WR/RB Blend-Consistent Hybrid Retry — Results (2026-06-12)

*Follow-up to the TE blend-consistency fix (743009f). Question: does the same fix
revive the WR residual (rejected 2026-06-10 at sealed-2025, bias +0.73) and the RB
residual (historically degrading)?*

## Protocol

- WR/RB Ridge residuals, same 60-feature architecture as shipped TE, trained
  2016-2021 ONLY with blend-consistent baselines (`compute_production_heuristic`
  with `weekly_df` passed → veteran prior blend active during training).
- Trained via the production trainer path (TE artifact reproduced bit-identical:
  alpha=0.001, n=8349, train MAE 2.92966… — training-path validity check).
- Evaluated through the PRODUCTION eval path: `backtest_projections.py
  --seasons 2022,2023,2024 --scoring half_ppr --ml --full-features --vs-consensus`
  with `HYBRID_POSITIONS={"TE","WR","RB"}` (temporary, restored after).
  CSV: `output/backtest/consensus_matched_half_ppr_20260612_083759.csv`.
- NOTE: a first eval attempt by a subagent used a custom backtest script that
  produced TE projections diverging from the verified production run by mean
  1.5 pts on identical model artifacts — discarded. Lesson re-confirmed: only
  the production eval path is trusted for ship decisions.
- 2025 NOT touched (sealed/amber).

## Results (matched vs Sleeper, cons≥5, 2022-24 w3-18, half-PPR, n=7,009, 0 dups)

| Pos | Path | MAE ours | MAE cons | Gap | Spearman ours | cons | Sp gap | Top-N ours/cons |
|-----|------|------|------|------|------|------|------|------|
| QB  | heuristic | 6.080 | 6.401 | **−0.320 (win)** | 0.343 | 0.370 | −0.027 | 0.602/0.599 |
| RB  | hybrid    | 5.607 | 5.332 | +0.275 | 0.373 | 0.453 | −0.080 | 0.729/0.753 |
| WR  | hybrid    | 4.995 | 5.042 | **−0.047 (WIN)** | 0.422 | 0.405 | **+0.017 (WIN)** | 0.569/0.568 |
| TE  | hybrid    | 4.019 | 4.455 | **−0.436 (win)** | 0.481 | 0.253 | +0.227 | 0.799/0.738 |

Heuristic-path reference (2026-06-12 final): RB +0.27/Sp −0.080, WR +0.09/Sp −0.056.

## Verdicts

- **WR: SHIP CANDIDATE.** Blend-consistent training flips both metrics to wins:
  MAE gap improves 0.137 (gate 0.05 ✅), Spearman gap improves 0.073 (gate 0.02 ✅).
  Per-season bias: 2022 −0.36, 2023 −0.39, 2024 −0.56 (2024 marginally over the
  0.4 gate, but stationary-negative — nothing like the old +0.73 reversal; a small
  bias correction can be swept if the sealed gate shows the same).
- **RB: KILL (again).** Gap +0.275 vs +0.27 heuristic, Spearman unchanged. The RB
  deficit is not residual-correctable with current features; it lives in
  who-gets-the-work variance (consistent with prior kills). RB stays heuristic.

## Blocking dependency before WR ship — Vegas sign fix (dbbef92)

The same audit session discovered the nflverse spread_line sign inversion
(implied totals swapped favorite/underdog since inception). The fix changes the
heuristic baseline → the WR/TE residuals above are now blend-INCONSISTENT with
the post-fix heuristic. Ship sequence (task #7):
1. Regenerate graph feature caches (predicted_script_boost direction fixed).
2. Re-measure heuristic consensus baseline post-Vegas-fix.
3. Retrain TE + WR residuals blend-consistent vs the FIXED heuristic (2016-2021).
4. Re-run 2022-24 hybrid gate (TE must hold ≤ −0.35; WR must hold ≤ 0.00 MAE gap
   and Spearman ≥ consensus −0.02).
5. ONE sealed amber-2025 confirmation for the combined ship (record in ledger).
6. Ship: HYBRID_POSITIONS = {"TE", "WR"}.
