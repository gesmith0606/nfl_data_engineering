# The prediction backtester scored games that had not been played (2026-10-23)

`MODEL_ASSESSMENT_2026_10_21.md` listed the game-prediction side as
UNASSESSABLE: one week-7 file for all of 2026, and no 2026 ATS/O-U/CLV
evidence of any kind. Closing that gap turned up a harness bug that had to be
fixed before any number from it could be trusted — and the number it was
reporting was the dangerous kind.

## What it reported, and what was true

Running `backtest_predictions.py --ensemble --seasons 2026` after generating
weeks 1-6:

```
O/U RESULTS -- Ensemble (272 games)
  Record:       206-66-0
  O/U Accuracy: 75.7%
  Break-even:   52.38% (-110 vig)
  Profit:       +121.27 units
  ROI:          +44.59%
```

A 75.7% over/under hit rate at a 52.38% break-even would be the most
profitable betting model ever built. Two things give it away before any code
is read:

1. **Nobody has a 23-point edge.** Magnitude alone should stop interpretation.
2. **272 games is the full 2026 season** (17 x 16). Only six weeks had been
   played.

## Mechanism

`assemble_multiyear_features` returns every row of the schedule, settled or
not. For 2026 that is 272 rows of which **93** carried a final score. Nothing
downstream filtered, and the outcome comparisons are written as:

```python
df["actual_over"] = df["actual_total"] > df["total_line"]
```

On a NaN actual that evaluates to **`False`**, not NaN. Pandas comparisons do
not propagate missingness, so an unplayed fixture is silently scored as an
"Under" outcome rather than being excluded or raising. Verified directly:

```
assembled rows: 272
  actual_total: non-null 93/272
played: 93 | unplayed: 179
actual_over distribution on UNPLAYED rows: {False: 179}
```

179 phantom Unders, which the model mostly "won": 41 real wins + 179 phantom
= 206. The arithmetic of the reported record is entirely accounted for.

**For every completed historical season this harness was ever pointed at,
every row is settled and the omission is invisible.** It was correct for its
whole prior life. The assessment's own next-step — "grade the 2026 predictions"
— is the first thing that would have exposed it, and would instead have
produced a triumphant false positive.

This is worse than a crash. A crash gets fixed; a plausible 75% hit rate with
positive ROI is a number someone sizes a bet on.

## Fix

A `drop_unsettled_games` filter (requires non-null `actual_margin` *and*
`actual_total` — ATS needs one, O/U the other, and the harness scores both in
one pass), applied through a single `_assemble_settled` wrapper that every
path now calls. It prints the population it scored:

```
Dropped 179 unplayed game(s) (backtest); 93 settled game(s) remain
```

The wrapper matters more than the filter. There were **five** independent
`assemble_multiyear_features` call sites, none filtering. Patching them one at
a time is exactly how the live path was missed on the first attempt: `--ensemble`
routes through `run_comparison_backtest`, not the `run_ensemble_backtest` that
was patched first, so the fix appeared to do nothing and produced byte-identical
output. One wrapper makes the omission unrepeatable, and a test asserts no
unfiltered call survives.

## The actual 2026 verdict

93 settled games, weeks 1-6, ensemble:

| market | record | accuracy | profit (flat $100) | ROI |
|---|---|---|---|---|
| **ATS** | 41-46-6 | **47.1%** | -8.73 units | **-10.03%** |
| **O/U** | 41-52-0 | **44.1%** | -14.73 units | **-15.84%** |
| break-even | | 52.38% | | |

Both markets are losing, and not marginally.

The harness also printed a "CLV" line (mean +0.37 points, median +0.24, 52.7%
"beating the close", higher at medium/high tiers), which this note first read
as the one positive signal. **It is not CLV — retracted 2026-10-24.**
`evaluate_clv` (since renamed `evaluate_model_vs_close`) is `predicted_margin - spread_line` against the closing line
only: no opening price, no movement. So +0.37 is the model leaning 0.37 points
more toward home than the close, 52.7% is the share of games where our number
sits on the home side, and the tier table is the sign of our own edge inside
buckets of its own magnitude:

| tier | games | mean edge toward home (printed as "CLV") | home-side share (printed as "beat close") |
|---|---|---|---|
| low | 46 | -0.04 | 41.3% |
| medium | 25 | +0.76 | 68.0% |
| high | 22 | +0.78 | 59.1% |

That lean is the losing record, not a counterweight to it: home teams and
favourites covered 39 of 87 (44.8%) in weeks 1-6. The O/U record has the same
character — 41-52 reproduces exactly from the Vegas total line plus one
constant, with no model input. Both derivations:
`CLV_PICK_RULE_AUDIT_2026_10_24.md`. True CLV is `evaluate_line_capture` (open
vs close) and has not been ruled on.

### How much weight this carries

- **n=93 is small.** The standard error on a win rate at that sample is
  ~5.2pp, so 47.1% sits roughly one SE below break-even. This is *no evidence
  of edge*; it is not proof of a broken model either.
- **The predictions were generated retrospectively** (today, for weeks 1-6).
  Bronze PBP for 2026 only contains weeks 1-6, so rolling features cannot see
  the future and the inputs are point-in-time in the ways that matter. But
  these are not live forward picks, so they test inputs and calibration, not a
  realised edge.
- **The 2024-holdout claims in the project status (53.0% ATS, +$3.09) are not
  current** and should stop being quoted as if they were.

## Why there was nothing to evaluate in the first place

None of the team-side Silver inputs existed for 2026 — `teams/pbp_metrics`,
`game_context`, `market_data`, `sos`, `tendencies`, `situational`,
`referee_tendencies`, `playoff_context`, `player_quality` all stopped at 2025.
The weekly workflow computes them in-job and the commit step never staged
`data/silver/teams/`, the same gap as `graph_features` and `players/usage`
(TD-08/09/10's pattern, third and fourth instances). They were rebuilt locally
to run this evaluation; whether to stage them weekly is a size decision of its
own and is not taken here.

## Ranked follow-ups

1. ~~**Understand positive CLV alongside losing picks.**~~ Premise false
   (2026-10-24): the "CLV" was the spread edge, so there was no paradox to
   explain. Real follow-ups are in `CLV_PICK_RULE_AUDIT_2026_10_24.md`
   (stop emitting O/U picks; validate the open-price proxy before the week-10
   line-capture gate).
2. **Re-add `--check-predictions` to the sanity gate.** It was disabled
   because no workflow produced predictions; one does now (since 2026-10-18).
3. **Decide whether the ensemble should be making ATS picks at all this
   season** at 47.1% on 93 games. Continue measuring weekly before concluding.
4. Stage `data/silver/teams/` so this is evaluable without a local rebuild.
