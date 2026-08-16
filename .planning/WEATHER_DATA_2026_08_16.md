# Weather Data 2026-08-16: Ingestion + Signal Evaluation

**Status: HOLD (documented-not-wired).** Weak, bias-only signal found — not an
accuracy (MAE) lever. Standalone feature table built and evaluated; NOT
integrated into `player_feature_engineering.py` per this sprint's file
ownership. Integration patch below if a future sprint wants to gate it.

## 1. Existing coverage audit

`src/game_context.py::compute_weather_features` already derives `is_dome`,
`temperature`, `wind_speed`, `is_high_wind` (>15mph), `is_cold` (<=32F) from
nflverse schedules' `temp`/`wind`/`roof` columns. Checked actual null rates
in the committed Bronze schedules (`data/bronze/schedules/`, 2016-2025,
outdoor/open-roof games only — `temp` and `wind` are always null together):

| season | outdoor games | temp/wind null rate |
|--------|---------------|----------------------|
| 2016 | 200 | 1.0% |
| 2017 | 205 | 2.4% |
| 2018 | 202 | 2.5% |
| 2019 | 206 | 4.9% |
| 2020 | 176 | 0.0% |
| 2021 | 202 | 5.4% |
| **2022** | 198 | **46.0%** |
| **2023** | 199 | **20.6%** |
| 2024 | 187 | 2.7% |
| 2025 | 193 | 2.1% |

**Verdict on what exists:** nflverse temp/wind is adequate for most seasons
(1-5% null) but has a real hole in 2022 (46% missing) and a smaller one in
2023 (21% missing) — roughly one full season's worth of outdoor games has no
temp/wind at all. nflverse **never** carries precipitation or wind gusts —
those columns don't exist anywhere in the schema. Domes are already handled
correctly in `game_context.py` (roof in {dome, closed} → temp=72, wind=0).

**Pivot taken:** rather than re-scrape temp/wind duplicating what mostly
works, this sprint ingested Open-Meteo for **all** 2016-2025 games (so the
2022/2023 hole is filled as a side effect) plus the two variables that don't
exist anywhere in this repo: **precipitation** and **wind gusts**.

## 2. Ingestion

**Source:** Open-Meteo historical archive API (`archive-api.open-meteo.com/v1/archive`),
free, no API key, hourly reanalysis data (ERA5-based), UTC timezone requested
directly to avoid DST bugs.

**Coordinates:** reused `STADIUM_ID_COORDS` from `src/config.py` (already
existed — 42 stadium_ids incl. relocated/legacy venues and international
sites; did NOT build a new lat/lon table, per the "check for reuse first"
instruction). Fetched weather for the 36 stadium_ids that ever hosted a
non-domed game 2016-2025; the other 6 dome-only venues (ATL00, DET00,
LAX01, MIN01, NOR00, VEG00) get `is_dome=True` defaults with zero API calls.

**Kickoff-hour mapping:** nflverse `gametime` is posted in ET broadcast-slot
convention regardless of the venue's actual local timezone (verified: Denver
home games at the "4:05pm ET slot" show `gametime='16:05'`, not their
2:05pm MT local kickoff). Localized `gameday`+`gametime` as
`America/New_York`, converted to UTC, rounded to nearest hour, looked up in
the venue's Open-Meteo hourly series.

**Chunking:** one API call per venue per season (10 calls × 36 venues),
1s sleep between calls, raw JSON response cached to
`data/bronze/weather/_raw_cache/<stadium_id>.json` so reruns are free. A
single 10-year request per venue was tried first and reliably timed out
server-side — per-season chunking was the fix, not just politeness.

**Bug caught and fixed during the run:** the first pass used `{year}-12-31`
as the end date for the final season (2025), which silently missed the
2025 season's playoff weeks (Jan/Feb 2026) — 24 games came back
`weather_source=unavailable`. Fixed to always extend to `{year+1}-02-15`
regardless of whether it's the last season in range, re-fetched the 13
affected venues, reran. Final result: **0 unavailable**.

**Output:** `data/bronze/weather/season=YYYY/weather_<ts>.parquet`, one row
per `game_id` — 2,761 games total (267-285/season), matched 1,968 via
Open-Meteo (outdoor/retractable-open) + 793 dome defaults + 0 unavailable.
**Total Bronze size: 0.13 MB** (game-level, not yet unpivoted to per-team).
Raw JSON cache is 68 MB, gitignored (`*.json` catch-all already covers
`data/bronze/weather/_raw_cache/`), not meant to ship — the actual output
artifact is the 0.13 MB parquet.

Columns: `game_id, season, week, stadium_id, is_dome, temp_f, precip_in,
wind_mph, wind_gust_mph, weather_hour_utc, weather_source`.

## 3. Signal evaluation

**Method:** joined the standalone per-team weather feature table
(`src/weather_features.py::compute_weather_features`, keyed
`(season, week, team)`) to `output/backtest/backtest_half_ppr_ml_fullfeatures_BASELINE_combined.csv`
— the shipped model's sealed backtest, `error = projected_points - actual_points`
(positive = overprojection). **This backtest only covers 2022-2024** (10,591
player-weeks) — no 2016-2021 backtest artifact exists in `output/backtest/`
to extend the window; this is the full available span, not a shortcut.

**Lever firing rate (checked before reading the verdict, per
`knowledge-vault/concepts/gated-experiment-coverage-check.md`):**
10,588/10,591 rows (100.0%) joined successfully. 3,359 rows (31.7%) are
dome games. Of the 7,229 outdoor rows, 628 (8.7%) are high-wind (>=15mph),
1,294 rows total have measurable precipitation. Non-trivial population in
every bucket — this is a real test, not a vacuous one.

**Accuracy (abs_error / MAE) — the metric that actually drives model
quality:**

| bucket | n | mean abs_error |
|---|---|---|
| wind 0-9mph | 4,857 | 4.526 |
| wind 10-14mph | 1,744 | 4.427 |
| wind 15-19mph | 568 | 4.370 |
| wind 20+mph | 60 | 5.631 |
| high-wind (>=15) | 628 | 4.491 |
| low-wind (<15) | 6,601 | 4.499 |
| dome | 3,359 | 4.544 |
| outdoor | 7,229 | 4.499 |

Pearson r(wind_speed_mph, abs_error) = **-0.0108, p=0.36** (not
significant). Pearson r(precip_in, abs_error) = **-0.0090, p=0.45** (not
significant). High-wind vs low-wind abs_error t-test: **t=-0.05, p=0.96**.
**MAE does not move with weather in any bucket.** The model is not less
accurate in bad weather.

**Bias (signed error) — smaller but statistically present:**

| bucket | n | mean error (proj - actual) |
|---|---|---|
| wind 0-9mph | 4,857 | -0.649 |
| wind 10-14mph | 1,744 | -0.136 |
| wind 15-19mph | 568 | +0.496 |
| wind 20+mph | 60 | -0.937 (n too small to trust) |
| precip none | 5,935 | -0.562 |
| precip trace (<=0.05in) | 1,067 | +0.114 |
| precip light-moderate (0.05-0.25in) | 227 | +0.218 |
| precip heavy (>0.25in) | 0 | n/a — zero games this magnitude in 2022-2024 |

Pearson r(wind_speed_mph, error) = **+0.045, p=0.0001**. High-wind vs
low-wind signed-error t-test: **0.359 vs -0.514, t=3.49, p=0.0005**
(pass-catchers QB/WR/TE specifically: 0.409 vs -0.503, t=3.17, p=0.0016).
Pearson r(precip_in, error) = **+0.024, p=0.046**; wet(>0.05in) vs dry
signed-error: 0.218 vs -0.459, t=1.68, p=0.09 (marginal).

**Interpretation:** the model has a mild baseline tendency to *underproject*
(negative mean error across the whole outdoor population, -0.56 to -0.65),
and that underprojection shrinks or flips to slight *overprojection* as wind
rises. That's the theoretically expected direction — wind suppresses passing
production and the model isn't currently discounting for it — but the swing
is ~0.5-1.1 fantasy points on a ~8-point baseline (roughly 6-12% of the
week's typical error), it doesn't touch MAE at all, and it only fires on
8.7% of outdoor rows (628/7,229). The heavy-precip bucket has zero games in
the 3-season eval window, so precipitation as a distinct lever is
untested by real data, not just weak — n=0 there is a genuine blind spot,
not a negative result.

Note this backtest already includes `vegas_multiplier` as an input feature,
so any residual correlation found here is *already net of* whatever Vegas
lines price in — the weak signal that remains is the incremental,
beyond-Vegas piece, which matches the mission's framing.

## 4. Verdict

**Not a dead end, but not a ship either: WEAK / BIAS-ONLY signal.**

- Vegas has NOT fully priced weather out of residuals — the correlation is
  real (p<0.001 on the wind→bias relationship) and directionally sensible.
- But it moves *bias*, not *accuracy*. MAE is flat across every wind/precip
  bucket. A model that's already well-calibrated on average would see no
  benefit from a lever that shifts the mean without tightening the spread.
- Effect size is small (~0.5-1pt) and the reach is narrow (8.7% of outdoor
  games are high-wind; heavy precip has zero eval-window observations).
- This reads exactly like the QB_STARTER_FLOOR and RB_TAIL_CALIBRATION
  precedents in this repo (`.planning/QB_STARTER_FLOOR_GATE.md`,
  `.planning/RB_TAIL_CALIBRATION_GATE.md`) — both HOLD, both "real but
  sub-threshold" levers — not the EARLY_SEASON_PRIOR dead-lever pattern
  where the join silently fired on zero rows.

**Recommendation:** build the features (done, standalone — see below) but do
NOT wire them in this sprint. If a future sprint wants to chase the bias
correction, gate it narrowly: a small downward shrink to QB/WR/TE
projections specifically in high-wind games (the population where the
t-test is significant), pre-registered against bias reduction (not MAE) as
the success metric, re-evaluated once 2025 completes a backtest and the
heavy-precip bucket has any observations at all.

## 5. Standalone feature table (built, not wired)

`src/weather_features.py::compute_weather_features(seasons=None) -> DataFrame`
keyed `(season, week, team)`, columns:

- `wind_speed_mph` — Open-Meteo game-hour wind speed, 0.0 for domes
- `is_high_wind` — `wind_speed_mph >= 15` (matches `game_context.py`'s
  threshold, though that module uses `>` not `>=` — a 15.0mph reading
  is extremely rare so this doesn't matter in practice, noted for anyone
  reconciling the two)
- `precip_in` — game-hour precipitation in inches, 0.0 for domes (does NOT
  exist anywhere else in this repo)
- `is_dome` — duplicated from Bronze so this table is self-contained

Deliberately does not duplicate `temperature`/`is_cold` — those already
exist in `game_context.py` and are adequate outside 2022/2023 (this table's
wind values are uniform across all seasons including 2022/2023, so joining
both tables gives you temp from game_context + reliable wind/precip from
here without re-deriving anything).

**Coverage guard already in the module:** `compute_weather_features()`
restricts schedules to exactly the seasons present in Bronze weather
(2016-2025) even when the caller passes no `seasons` filter — nflverse
schedules go back to 1999, so an unfiltered join would otherwise silently
default `is_dome=False, wind=0.0` for every out-of-range season instead of
excluding those rows. Caught this exact bug during this sprint (see
`knowledge-vault/concepts/gated-experiment-coverage-check.md` — the "join
keys and paths validated by no one" failure mode) before it reached the
evaluation; fixed in `weather_features.py` before any numbers above were
computed.

### Integration patch (NOT applied — file ownership is new-files-only this sprint)

If/when a future sprint wants to wire this into
`src/player_feature_engineering.py`, the pattern to follow (mirrors how
`game_context` features are merged in elsewhere in that module):

```python
# In src/player_feature_engineering.py, near where game_context features
# are merged onto the player-week frame (same [team, season, week] key):

from src.weather_features import compute_weather_features

weather_feats = compute_weather_features(seasons=seasons)
player_df = player_df.merge(
    weather_feats[["season", "week", "team", "wind_speed_mph", "is_high_wind", "precip_in"]],
    on=["season", "week", "team"],
    how="left",
)
# is_dome intentionally NOT merged here -- game_context.py already provides
# it (compute_weather_features -> is_dome), avoid a duplicate column.

# Then gate any model-facing use behind an opt-in flag, e.g.:
#   --weather-bias-correction
# applying a small downward shrink to QB/WR/TE projected_points when
# is_high_wind=True, following the opt-in-flag pattern used by
# --early-season-prior / --qb-starter-floor / --rb-tail-calibration in
# scripts/generate_projections.py. Pre-register the gate against bias
# reduction (mean signed error in the high-wind bucket), not MAE -- MAE
# will not move per the evaluation above, and a gate that checks the wrong
# metric will falsely HOLD a lever that's actually working as designed.
```

## Files

- `scripts/bronze_weather_ingestion.py` — Open-Meteo ingestion CLI
- `src/weather_features.py` — standalone per-team feature table
- `scripts/evaluate_weather_signal.py` — the evaluation in section 3 (rerunnable)
- `tests/test_weather_features.py` — unit tests (kickoff-hour UTC conversion, unpivot, threshold constant)
- `data/bronze/weather/season=YYYY/*.parquet` — output data (0.13 MB total, gitignored like all Bronze parquet)
- `data/bronze/weather/_raw_cache/*.json` — raw Open-Meteo responses, dev-only cache (68 MB, gitignored)
