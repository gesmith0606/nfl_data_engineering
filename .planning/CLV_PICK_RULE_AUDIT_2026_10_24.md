# The "positive CLV with losing picks" paradox dissolves (2026-10-24)

`HANDOFF_2026_10_23.md` ranked this first: *"Understand positive CLV alongside
losing picks. If the line moves our way but the pick loses, the fault is likely
the edge calculation or pick rule, not the prediction."* Right instinct, wrong
premise. **There is no positive CLV.** The metric reported under that name does
not observe the market a second time, so it cannot say the line moved our way.

Then, auditing the pick rules as the handoff suggested, the O/U rule turned out
to be degenerate: the entire 2026 over/under betting record is reproducible
from the Vegas line and one constant, with no model input at all.

## 1. The "CLV" is the spread edge, renamed

`src/prediction_backtester.py:114`:

```python
df["clv"] = df["predicted_margin"] - df["spread_line"]
```

That is the definition of `spread_edge`. `compute_clv_by_tier` then buckets on
`|predicted_margin - spread_line|` — the same quantity — and reports
`pct_beating_close` as `(clv > 0).mean()`.

So the three headline numbers decompose as:

| reported as | actually is |
|---|---|
| mean CLV **+0.37** | our model leans **0.37 pts more toward home** than the closing line |
| **52.7%** "beating the close" | 52.7% of games where our number is on the home side of the line |
| CLV by tier (low 41.3%, med 68.0%, high 59.1%) | the sign distribution of our own edge, within buckets of its own magnitude |

Only one line is involved — the close — and we bet into it. No opening price,
no movement, no second observation. "Beating the close" is a misnomer for
"having a positive edge", which is true by construction for every pick on the
home side.

The module is not at fault: its docstring says in capital letters
`TRUE CLV vs MODEL-VS-CLOSE NOTE ... This is NOT true Closing Line Value`, and
names `evaluate_line_capture` as the real metric. The write-up quoted it as CLV
anyway. This is the sixth claim in this body of work to fail on inspection, and
the same shape as the other five: an aggregate nobody opened up.

### The signal and the losses are the same fact

In 2026 weeks 1–6, home teams and favourites covered **39 of 87** (44.8%). Our
model's "+0.37 CLV" is a systematic home lean. The season punished exactly that
lean. What was read as evidence of edge *is* the mechanism of the loss, seen
twice.

| ATS, 2026 wk1-6 (n=93) | record | acc | ROI |
|---|---|---|---|
| always HOME / always FAVOURITE | 39-48-6 | 44.8% | −14.42% |
| **ensemble (reported)** | **41-46-6** | **47.1%** | **−10.03%** |
| always AWAY / always UNDERDOG | 48-39-6 | 55.2% | +5.33% |

The ensemble beat a blanket home bet by 2.3 points. At n=93 (SE ≈5.2pp) that
is not a verdict on the spread model either way — but it is not an edge, and
the "+0.37 CLV" was never independent evidence for one.

## 2. The O/U pick rule is a step function of the Vegas line

The totals model is **near-constant**. On the served week-7 board (n=14):

| | std | range |
|---|---|---|
| `predicted_total` (ours) | **0.49** | 44.34 – 46.55 |
| `vegas_total` | 4.66 | 38.50 – 53.50 |

So `total_edge = predicted_total − vegas_total` is the Vegas line with the sign
flipped:

```
corr(total_edge, vegas_total)     = -0.9944
corr(total_edge, predicted_total) = +0.038
```

Our own model explains ~0% of its own edge. And since
`ou_pick = "over" if total_edge > 0`, the rule collapses to **"bet over on
every line below ~45.3, under on every line above it"** — fade the extreme,
with no game-specific information. Week 7 sorts perfectly: all nine lines
≤44.5 → over, all five ≥47.5 → under.

### Reproduced exactly, model-free

Grading that rule against the 93 settled games using only `total_line` and the
final score:

| rule | record | acc | ROI |
|---|---|---|---|
| always OVER | 47-46-0 | 50.5% | −3.52% |
| always UNDER | 46-47-0 | 49.5% | −5.57% |
| **OVER if line < 45.3** | **41-52-0** | **44.1%** | **−15.84%** |

41-52-0, 44.1%, −15.84% is byte-identical to the reported 2026 O/U result.
**The totals model contributed nothing to a single pick.** The market was a
coin flip (overs 50.5%); the rule converted it into 44.1% by systematically
fading extremes.

### The pick contradicts our own calibrated probability

`over_prob` (leak-free OOF calibrator) on the served week-7 board is **below
0.50 for all 14 games** (0.4644–0.4987) — the calibrator says *under* is the
better side everywhere. `ou_pick` says **over in 9 of 14**.

```
rows where ou_pick contradicts over_prob:        9/14
rows where ats_pick contradicts home_cover_prob: 1/14
```

Both columns ship side by side to the API and the site. The tiering is already
better than the pick: `classify_tier_prob` (wired on the `--ensemble` path,
`generate_predictions.py:396`) tiers on the picked side's calibrated
probability and correctly demotes all nine over picks to "low". Its docstring
even explains why — *"the totals model is near-constant, so big 'edges' just
mean Vegas posted an extreme line"*. The diagnosis was written down; the pick
rule was never changed to match.

Following `over_prob` instead would have bet under on everything: 49.5%, still
a loser after vig. **So the fix is not to flip the rule — it is to stop
emitting O/U picks.** There is no edge to harvest in this market with this
model.

## 3. No sign or convention bug — the thing we set out to find is clean

Checked end to end, all in the nflverse home-positive convention:

| quantity | definition | verdict |
|---|---|---|
| `spread_line` (nflverse) | positive = home favoured | — |
| `actual_margin` | `home_score − away_score` (`feature_engineering.py:914`) | ✓ |
| spread model target | `actual_margin` (`ensemble_training.py:506`) | ✓ |
| `model_picks_home` | `predicted_margin > spread_line` | ✓ |
| `ats_pick` | away if `spread_edge < 0` else home | ✓ consistent |
| `actual_over` / `model_picks_over` | both vs `total_line` | ✓ |

The one place a convention genuinely flips is the odds snapshot, where
`open_spread`/`close_spread` use the sportsbook sign (negative = home
favoured). `backtest_predictions.py:954` negates it before comparing, and that
negation is **correct**:

```
corr(spread_line, -close_spread) = +0.9899     mean |diff| = 0.29 pts
corr(spread_line, +close_spread) = -0.9899
```

## 4. CORRECTED 2026-10-25: the open proxy is sound; the *gate* cannot fail

This section originally claimed the open proxy was too noisy to rule on —
"mean deviation 2.38 pts, 16% of settled games fitting the opposite sign,
87% sourced from 1-2 books ... input noise roughly 8x the gate threshold."
**That reading was wrong**, and a dedicated validation
(`.planning/OPEN_PROXY_VALIDATION_2026_10_25.md`) overturned it:

- **No sign bug.** Exactly **1 of 45,398** book-quotes fits the inverted sign.
  Per-book deviation from same-snapshot consensus runs −0.057 to +0.002 across
  all nine books. `src/odds_snapshot_loader.py` is correct as written.
- **No thin-book artifact.** Each open matches the median consensus over the
  following 3/7/10/21 days with **median deviation 0.00 pts**, and not one
  game deviates by more than 1.0 pt in any window. The apparent book-depth
  effect was confounded with horizon: hold the horizon at ≤7 days and it
  vanishes and reverses.
- **The deviations are real repricing.** The "open" is simply the first
  snapshot ever captured for a game, which sits a median **109 days** before
  kickoff (25th pct 89, max 165; independently verified). So `close − open` is
  the entire summer-to-gameday move, not betting-week line value. wk4 ARI@NYG
  really was a 7-pt home favourite in June and a 2.5-pt dog by week 4.

So the measurement is honest about what it measures; it just does not measure
CLV. The ELITE 2.4 gate (**mean capture > +0.3**, n≥100 by week 10; kill at ≤0
with n≥150) has two defects instead, the second disqualifying:

1. **Underpowered ~3x.** sd of the open→close move is **3.20 pts**, so the SE
   at n=100 is **0.320** — larger than the entire +0.3 threshold. A printed
   +0.3 would carry a 95% CI of roughly [−0.33, +0.93]. The kill criterion is
   equally blind.
2. **Biased toward ship — it cannot fail.** `scripts/backtest_predictions.py`
   (~line 961) re-assigns the pick side *against the open proxy*, so the
   harness pretends we bet in June at the June price using a model trained on
   data through October. Simulated on the real 93 games, a model with **zero
   genuine edge** — one that knows only the week-of consensus line, so cannot
   beat the close — is credited with **+2.277** mean capture. Even at 8 pts of
   error it scores **+0.923**, against a +0.3 bar. **Had week 10 been ruled on
   this, it would have shipped on nothing.**

Narrowing the window to ≤7 days cuts the bias ~3x but does not remove it; the
*pick rule* is what needs fixing. This is the second time the betting harness
has produced a flattering fabrication, after the 179 phantom Unders in
`PREDICTION_BACKTEST_PHANTOM_GAMES.md`.

Note also that at a ≤7-day window the entire mean absolute move is 0.76 pts,
so a +0.3 bar means harvesting 39% of all available movement — demanding but
coherent. At ≤3 days the mean move is 0.34 and +0.3 would require ~90% of it,
which is not a real target. The threshold and a resolvable window have to be
set together.

## Recommended actions, in order

1. **Stop emitting O/U picks** (`ou_pick`, `over_prob`) until the totals model
   has dispersion worth betting. A constant prediction cannot pick a side. Serve
   nothing rather than a line-fade dressed as a model.
2. **Rename `evaluate_clv` → `evaluate_model_vs_close`** and `pct_beating_close`
   → `pct_home_lean`. The docstring warning did not survive contact with a
   write-up; the name has to carry it. Keep "CLV" for `evaluate_line_capture`
   alone.
3. **Retract the CLV claim** wherever it is quoted —
   `PREDICTION_BACKTEST_PHANTOM_GAMES.md`, `HANDOFF_2026_10_23.md` next-step 1,
   `MODEL_ASSESSMENT_2026_10_21.md`, and the project-status memory.
4. **Make the pick follow the calibrated probability**, not the raw edge, and
   publish only when it clears 52.38%. The ATS side already agrees 13/14 times;
   making it explicit costs little and closes the contradiction.
5. **Do not rule on ELITE 2.4 as wired.** Fix the pick side first (capture must
   use the line the published board was priced against, not one back-fitted
   from a June price), then set the open horizon to ≤7 days — which costs no
   sample, since n is set by the schedule at ~150 games through week 10 — and
   restate the threshold against that window (~+0.15, or slip the gate to
   accumulate n). Details in `OPEN_PROXY_VALIDATION_2026_10_25.md`.
6. **Diagnose the totals model** separately: a std of 0.49 against a 14.45 std
   outcome means it is predicting the mean and nothing else. That is a modelling
   question, not a pick-rule one.

## Method notes

- Every number here is from the committed schedule (`data/bronze/schedules/season=2026/`)
  and the served week-7 board
  (`data/gold/predictions/season=2026/week=07/predictions_20261020_092514.parquet`),
  so the O/U reproduction needs no model and no regeneration.
- The ATS record (41-46-6) is quoted from the handoff, not re-derived; that
  would need the weeks 1–6 predictions regenerated. The model-free baselines
  around it are computed here.
- One grep in this audit silently did nothing (`--include=*.py` unquoted under
  zsh errors out, and the error reads like a result). It produced a wrong
  "`classify_tier_prob` is dead code" conclusion that the re-run overturned.
  The handoff's "assert non-vacuity" trap, in a new costume.
