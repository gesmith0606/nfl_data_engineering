# Prop-Implied Projections — Purchase & Build Decision Memo

*Written 2026-06-12 per ELITE_MODELS_PLAN 3.2 discipline: named feature, backtest plan,
and predicted delta committed BEFORE any spend. Source evidence: .planning/SOTA_RESEARCH.md.*

## The case

Player props are the sharpest per-player consensus available — sharper than Sleeper/ESPN
projections because money disciplines them. Measured external evidence: a pure
FanDuel-prop-derived ranking beat DraftSharks (a top paid projector) 4.76 vs 4.84 MAE over
13 weeks of 2025. We currently use Vegas information only at the TEAM level (implied
totals, spread). Per-player market information is our single largest unused data source.

## What to buy

**The Odds API paid tier** ($29-99/mo depending on credits): historical player props
since **May 2023** at 5-minute snapshot granularity. Covers receiving yards, rushing
yards, receptions, anytime TD, pass yards/TDs across major US books.
Blocked on: `ODDS_API_KEY` (user must register; same key unlocks the idle
odds-capture cron — double value).

## Named features

1. `prop_implied_points` (player-week): invert each prop line + juice → implied mean
   (Unabated method: de-vig the over/under prices, median across books), combine
   per-market implied stats through `scoring_calculator` → implied half-PPR points.
2. `prop_anchor_gap` = our heuristic projection − prop_implied_points (a "we disagree
   with the market" flag, the same disagreement signal that drives our consensus losses).

## Backtest plan (write-once, pre-registered)

- Window: 2023 w5–18 + 2024 w1–18 (props history starts May 2023; 2025 stays sealed).
- Step 1 (benchmark): MAE + within-position-week Spearman of `prop_implied_points`
  alone vs our heuristic vs Sleeper consensus on matched player-weeks.
- Step 2 (blend): `proj' = (1−λ)·proj + λ·prop_implied_points`, λ swept per position
  in the heuristic lab. Players without props (deep bench) keep λ=0 — props coverage
  is concentrated in the exact high-volume players where our disagreement losses live.
- Step 3 (gate): consensus-matched eval. SHIP if WR/RB MAE gap improves ≥0.05 OR
  Spearman gap narrows ≥0.02 at either position, no QB/TE regression.

## Predicted delta (committed in advance)

- RB consensus gap +0.27 → ≤ +0.10; WR +0.09 → ≤ 0 (parity/win).
- Spearman: +0.03–0.06 at RB/WR (props directly encode role/usage news we systematically
  miss — late-week injury/role information is priced into props by Sunday morning).
- If the blend moves <0.02 at every position: KILL and downgrade to benchmark-only use.

## Honest caveats

1. **Self-reference**: blending market data means our "edge vs consensus" partially
   becomes "the market vs the market". Mitigation: always ALSO report the unblended
   model's gap; the blended product is what users consume, the unblended gap is the
   research metric.
2. **Live timing**: production use requires pulling props before kickoff (the existing
   odds-capture cron pattern extends to props endpoints).
3. **Coverage**: props exist for ~top-150 players; the tail keeps the pure model.

## Recommendation

BUY ($29/mo tier first; upgrade only if credit limits bind). This is the
highest-expected-value data acquisition available to the project, it is cheap, and the
same key activates the already-built spread line-capture infrastructure (ELITE 2.4),
which is calendar-critical before 2026 w1.
