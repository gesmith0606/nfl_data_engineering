# TOTALS_VERDICT.md — Phase 1.2 Diagnosis

*Generated 2026-06-10 20:41 by `scripts/diagnose_totals_edge.py`*

---

## Executive Summary

**VERDICT: KILL**

No subgroup met all three gates simultaneously (|t| > 2.5, n ≥ 100, hit ≥ 52.5%). Near-
misses (|t| > 2.0 but did not pass all gates): Dome games: t=3.30, n=488, hit=52.460%

> Action: Remove the game-totals betting surface from production. Keep `predicted_total` as website content labeled **market tracking** (useful context; not a bet recommendation). No further totals modeling work until a new information source (e.g., The Odds API opener data per Phase 1.4) makes the hypothesis re-testable.

---

## Q1: Signal Beyond the Line

**OLS**: `actual_total ~ total_line + meta_oof_pred`  (n=1599)

| Predictor | Coef | SE | t-stat | p-value |
|-----------|-----:|---:|-------:|--------:|
| Intercept | -25.027 | 13.219 | -1.89 | 0.0585 |
| total_line | 0.945 | 0.074 | 12.80 | <0.001 |
| meta_oof_pred | 0.614 | 0.290 | 2.12 | 0.0345 |

- **R²**: 0.1015
- **Partial correlation** of `meta_oof_pred` controlling for `total_line`: 0.0572
- **Overall O/U (% overs in actuals)**: 47.97%
- **Model O/U accuracy** (meta_oof_pred > total_line → pick over): 49.84%

> meta_oof_pred coefficient t=2.12, below threshold 2.5. The ML ensemble carries **no statistically reliable signal beyond the closing line**.

---

## Q2: Residual Subgroup Analysis

`resid = actual_total − total_line` (positive = over, negative = under). Multiple-testing threshold: |t| > 2.5.

| # | Subgroup | n | mean_resid | std | t-stat | p-value | Naive hit rate | Real? |
|---|----------|--:|----------:|----:|-------:|--------:|:--------------:|:-----:|
| 1 | High wind outdoor (wind_speed ≥ 15 mph) | 117 | -1.06 | 13.02 | -0.88 | 0.3822 | 53.850% (under) | no |
| 2 | Cold outdoor (temp ≤ 25F) | 23 | -3.28 | 9.71 | -1.62 | 0.1194 | 69.570% (under) | no |
| 3 | Dome games | 488 | +2.05 | 13.74 | 3.30 | 0.0010 | 52.460% (over) | YES |
| 4 | Both teams top-quartile pace_roll3 | 99 | +0.43 | 13.87 | 0.31 | 0.7560 | 47.470% (over) | no |
| 5 | High-wind × under interaction (same-sample reframe of #1) | 117 | -1.06 | 13.02 | -0.88 | 0.3822 | 53.850% (under) | no |

> Subgroup 5 (high-wind × under interaction) is the same game sample as Subgroup 1 reframed around the under-betting hypothesis; its t-stat is identical by construction.

---

## Q3: Verdict Details

**Gates applied:**
- Subgroup |t| > 2.5
- Subgroup n ≥ 100
- Naive hit rate ≥ 52.5% (implied O/U accuracy)

**No subgroup passed all three gates.**

**Verdict: KILL**

No subgroup met all three gates simultaneously (|t| > 2.5, n ≥ 100, hit ≥ 52.5%). Near-
misses (|t| > 2.0 but did not pass all gates): Dome games: t=3.30, n=488, hit=52.460%

---

## Data Coverage Notes

- OOF games: 1599 (seasons 2019–2024)
- total_line missing: 0
- wind_speed missing: 155 (9.7%) — dome/closed-roof games have wind=0
- temperature missing: 155 (9.7%) — dome/closed-roof games have temp=72
- pace_roll3 missing (either team): 111 (6.9%) — typically early-season games
- Dome games in OOF: 488 (30.5%)
- High-wind outdoor games (wind ≥ 15 mph): 117 (7.3%)
- Cold outdoor games (temp ≤ 25F): 23 (1.4%)
- Both-teams top-quartile pace: 99 (6.2%)