# Feature Landscape: Market Data Integration

**Domain:** NFL game prediction -- historical odds, line movement features, CLV tracking
**Researched:** 2026-03-27
**Confidence:** MEDIUM-HIGH

## Table Stakes

Features that any serious betting model evaluation must have. Missing = incomplete evaluation.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| CLV tracking | Gold standard for model evaluation; win rate alone is noisy over small samples | Low | Compare model line at prediction time vs closing line |
| Opening/closing line pairs | Foundation for all line movement analysis | Med | Requires external data source ingestion |
| Opening-to-closing spread shift | Most basic line movement signal | Low | closing_spread - opening_spread, trivial once data exists |
| Opening-to-closing total shift | Same as spread shift for totals | Low | closing_total - opening_total |

## Differentiators

Features that add analytical value beyond basics.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Line movement magnitude | Large moves (>1.5 pts) correlate with sharp action | Low | abs(closing - opening) |
| Movement direction vs result | Does the market "correct" toward the winner? | Low | Evaluation metric, not a prediction feature |
| No-vig implied probability | True market-implied win probability (removes bookmaker margin) | Med | Requires away_spread_odds + home_spread_odds for devig |
| Opening line as feature | Market's initial assessment incorporates public info efficiently | Low | Could be a strong feature -- markets aggregate information |
| Spread movement (signed) | Directional shift captures where sharp money went | Low | positive = line moved toward home, negative = toward away |
| Key number crossing | Movement across 3, 7, 10 is more significant than same-magnitude moves elsewhere | Med | Requires special handling for NFL key numbers |

## Anti-Features

Features to explicitly NOT build in v2.1.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time line tracking | Requires live API polling infrastructure; out of scope for batch pipeline | Capture snapshots at known times (opening, closing) |
| Public betting percentages | No free reliable source; requires paid subscription | Use line movement as a proxy for sharp/public split |
| Multi-book line comparison | Adds complexity with marginal signal for game-level models | Use consensus/Pinnacle line only |
| Player prop odds | Different market; not game-level; massive data volume | Defer to v3.1 Alternative Data |
| In-game live odds | Requires real-time infrastructure | Out of scope for batch prediction |
| Futures/season win totals | Different time horizon; not game-level features | Possibly useful in v3.x |

## Feature Dependencies

```
Bronze odds data (opening + closing lines)
    |
    +--> Silver line movement features (src/market_analytics.py)
    |       |
    |       +--> spread_shift = closing_spread - opening_spread
    |       +--> total_shift = closing_total - opening_total
    |       +--> spread_move_abs = abs(spread_shift)
    |       +--> total_move_abs = abs(total_shift)
    |       +--> spread_move_dir = sign(spread_shift)
    |       +--> total_move_dir = sign(total_shift)
    |       +--> crosses_key_spread = binary flag for crossing 3/7/10
    |       |
    |       +--> Feature assembly via feature_engineering.py
    |               |
    |               +--> Ablation: add to feature set, re-run SHAP selection, test on holdout
    |
    +--> Gold CLV tracking (src/prediction_backtester.py)
            |
            +--> clv_spread = model_spread - closing_spread  (positive = beat the close)
            +--> clv_total = model_total - closing_total
            +--> mean_clv = average CLV across all predictions
```

## Candidate Silver Features (Per-Game)

These are the specific columns that `src/market_analytics.py` would produce:

| Column | Type | Description | Pre-game knowable? |
|--------|------|-------------|-------------------|
| opening_spread | float | Opening spread (home perspective) | YES -- available days before game |
| closing_spread | float | Closing spread (cross-ref with nflverse) | NO -- only known at kickoff |
| opening_total | float | Opening over/under total | YES |
| closing_total | float | Closing over/under total | NO |
| spread_shift | float | closing - opening spread | NO -- requires closing line |
| total_shift | float | closing - opening total | NO |
| spread_move_abs | float | Absolute spread movement | NO |
| total_move_abs | float | Absolute total movement | NO |
| spread_move_dir | int | Sign of spread movement (-1/0/+1) | NO |
| total_move_dir | int | Sign of total movement (-1/0/+1) | NO |
| crosses_key_spread | int | 1 if spread crossed 3, 7, or 10 | NO |

**CRITICAL LEAKAGE NOTE:** Line movement features that use the closing line are NOT knowable before kickoff. They can be used for historical backtesting and CLV analysis, but using them as prediction features would be leakage because the model predicts before the game and the closing line is only known at kickoff. The opening line IS pre-game knowable and CAN be used as a feature. See PITFALLS.md for detailed discussion.

**Practical resolution:** For backtesting (evaluating past predictions), line movement features use actual closing lines. For live predictions (generating week-ahead forecasts), only the opening line is available. The ablation should test whether line movement features improve backtested ATS accuracy -- if yes, consider mid-week line snapshot as a proxy for real-time use.

## MVP Recommendation

Prioritize:
1. Opening/closing spread and total pairs into Bronze (table stakes for everything else)
2. Opening line as a candidate feature (pre-game knowable)
3. CLV tracking in backtester (model evaluation metric, not a prediction feature)
4. Ablation of opening_spread as candidate feature

Defer:
- Key number crossing: adds complexity; test basic features first
- No-vig implied probability: requires devigging logic; save for v2.2
- Moneyline-implied features: may overlap with spread information

## Sources

- [CLV methodology](https://oddsjam.com/betting-education/closing-line-value) -- CLV definition and calculation
- [CLV as evaluation metric](https://www.sharpfootballanalysis.com/sportsbook/clv-betting/) -- why CLV matters
- [Reverse line movement](https://www.actionnetwork.com/education/reverse-line-movement) -- line movement concepts
- [NFL key numbers](https://www.dimers.com/sports-betting-101/sports-betting-explained/how-to-read-line-movement-in-sports-betting) -- 3, 7 as critical thresholds
