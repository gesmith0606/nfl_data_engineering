# Wind Lever 2026-08-16: High-Wind QB/WR/TE Bias Shrink

**Status: HOLD.** The narrow lever recommended by
`.planning/WEATHER_DATA_2026_08_16.md` was built, fit strictly on 2022-2023,
and gated against 2024 + a fresh sealed-2025 read. The fit-window bias
direction **replicates on 2024 but INVERTS SIGN on 2025** — the combined
held-out gate fails hard (bias gets 139% worse, not >=50% better). Lever
shipped as opt-in only (`--wind-adjust`), NOT recommended default-on.

## 1. Mission recap

`WEATHER_DATA_2026_08_16.md` found QB/WR/TE Vegas-net signed bias flips from
-0.503 (low wind) to +0.409 (wind >=15mph, t=3.17, p=0.0016) across the
2022-2024 backtest — the model over-projects pass-catchers in high wind. The
recommendation was a small multiplicative shrink to QB/WR/TE projections in
high-wind games, fit on 2022-2023 only (walk-forward spirit) and evaluated
untouched on 2024 + 2025.

## 2. Pre-registered gate

Written before reading held-out numbers, per this task's brief:

- **SHIP** if high-wind-bucket `|mean bias|` for QB/WR/TE shrinks by **>=50%**
  on the held-out seasons (2024 + 2025 combined) with **n>=150**, AND
- global MAE does not worsen by more than **0.01**, AND
- **zero effect** on non-high-wind rows (byte-identical guard).
- Otherwise **HOLD**.

## 3. Fit (2022-2023 ONLY)

Joined `output/backtest/backtest_half_ppr_ml_fullfeatures_BASELINE_combined.csv`
(sealed 2022-2024 backtest) to `src/weather_features.compute_weather_features()`
on `(season, week, team)`, restricted to `season in {2022, 2023}`,
`position in {QB, WR, TE}`, `is_high_wind` (>=15mph).

| | value |
|---|---|
| n (fit bucket) | 342 |
| mean bias (proj − actual) | +0.4228 |
| mean projected_points | 7.8489 |
| vs low-wind/outdoor bucket (n=3,626) | -0.2433 |
| t-test (fit bucket vs low-wind) | t=2.05, p=0.041 |

**Shrink formula:** a multiplicative discount `s` applied to `projected_points`
zeros the bucket's mean bias when `s = mean(error) / mean(projected_points)`
(derivation: `new_error = error − s·proj`; set to 0 and solve for `s`).

```
HIGH_WIND_SHRINK = 0.4228 / 7.8489 = 0.0539   (5.39%)
```

This is the ONLY knob, fit on 2022-2023 exclusively — no peeking at 2024 or
2025 during fitting. Shipped as `src/wind_adjust.py::HIGH_WIND_SHRINK`.

## 4. Held-out gate results

**2024** (from the existing `BASELINE_combined.csv`, untouched during fit):

| | value |
|---|---|
| n | 108 |
| bias before | +0.3644 |
| bias after (× 0.9461) | -0.0691 |
| `\|bias\|` reduction | **81.0%** — matches fit direction |

**Sealed 2025** (fresh one-touch read this task — no fantasy-projection
backtest existed for 2025 before this run; generated
`output/backtest/backtest_half_ppr_ml_fullfeatures_20260816_200952.csv` via
`python scripts/backtest_projections.py --seasons 2025 --weeks 1-18 --scoring half_ppr --ml --full-features`,
the identical recipe used for `BASELINE_combined.csv`'s 2022-2024 rows.
Logged to `.planning/holdout_ledger.json` per the repo's sealed-2025
one-touch discipline — this file will not be re-fit against 2025 numbers):

| | value |
|---|---|
| n | 188 |
| bias before | **-0.6166** |
| bias after | **-0.9348** |
| `\|bias\|` change | **-51.6% (WORSE)** — sign inverted vs the fit window |

**Combined 2024 + 2025 (the pre-registered gate population, n>=150 required):**

| | value |
|---|---|
| n | 296 (>= 150 required — OK) |
| bias before | -0.2586 |
| bias after | -0.6190 |
| `\|bias\|` change | **-139.3% (WORSE)** |
| **Gate result** | **FAIL** (needed >=+50%, got -139.3%) |

Position/wind-band breakdown showing the inversion is not just the unstable
20+mph tail — even the 15-19mph sub-band flips:

| bucket | 2024 mean error | 2025 mean error |
|---|---|---|
| wind 15-19mph | +0.364 (n=108) | -0.350 (n=133) |
| wind 20-24mph | n/a (0 rows) | -1.261 (n=55) |
| QB | +2.515 (n=20) | -1.136 (n=26) |
| WR | +0.122 (n=62) | -1.108 (n=105) |
| TE | -0.712 (n=26) | +0.525 (n=57) |

QB and WR both flip sign; TE flips the other direction. This is not a
single-tail artifact — the whole high-wind bucket's bias direction is
unstable year to year, which the 2022-2023-only fit window could not see.

**MAE check** (global, all positions, all rows — shrink only ever touches
QB/WR/TE high-wind rows):

| season | MAE before | MAE after | delta |
|---|---|---|---|
| 2024 | 4.6165 | 4.6138 | -0.0027 (passes <=0.01 threshold) |
| 2025 | 4.0509 | 4.0511 | +0.0003 (passes <=0.01 threshold) |

MAE is essentially flat, as expected for a bias-only lever — this leg of the
gate would have passed on its own. The failure is entirely on the bias
criterion.

**Zero-effect guard (non-high-wind rows):** guaranteed by construction —
`src/wind_adjust.py::apply_wind_shrink` only multiplies rows where
`position in {QB,WR,TE}` AND `recent_team in high_wind_teams`; every other
row (RB always, domes always, low-wind always, and non-high-wind-team
QB/WR/TE) is returned byte-identical. Verified in
`tests/test_wind_adjust.py::TestScopingByteIdenticalGuard` (RB on the same
high-wind team untouched, low-wind team untouched, empty high-wind-team set
→ fully byte-identical DataFrame).

## 5. Firing rate (checked before reading the verdict, per the vault's
`gated-experiment-coverage-check` discipline)

| season | QB/WR/TE outdoor rows (eligible) | high-wind rows (fired) | firing rate |
|---|---|---|---|
| 2024 | 1,664 | 108 | 6.5% |
| 2025 | 2,141 | 188 | 8.8% |

Non-trivial population both years — this is a real gate result, not a
vacuous one (the lever fires plenty; it just fires in the wrong direction in
2025).

## 6. Verdict: HOLD

The 2022-2024 pooled signal reported in `WEATHER_DATA_2026_08_16.md` was
real (p=0.0016) but, as that report's own verdict warned, it was already
"weak / bias-only" with a "small effect size." Splitting it into a genuine
walk-forward fit/holdout (fit on 2022-2023, blind on 2024+2025) shows the
bias *direction* itself doesn't hold up out of sample — 2024 confirms it,
2025 contradicts it just as strongly. This is the class of result the
pre-registered gate exists to catch: a plausible, statistically-significant
in-sample pattern that doesn't survive a genuine held-out test. Same failure
shape as QB_STARTER_FLOOR and RB_TAIL_CALIBRATION (both HOLD), but a
stronger negative result — those two at least didn't get *worse* on
held-out data.

**Recommendation:** ship the lever as opt-in (`--wind-adjust` /
`--wind-adjust-shrink`) for anyone who wants to experiment with it, but do
**NOT** default it on in the weekly pipeline. Revisit only if a future
season's data suggests the bias direction stabilizes, or if the mechanism
is rebuilt around something more targeted than an aggregate ">=15mph"
threshold (e.g. per-position or gust-specific splits) — a coarse threshold
averaging over a bucket whose sign flips year to year is not fixable by
re-fitting the magnitude alone.

## 7. Production wiring (built regardless of verdict, since ownership was
clear and the lever is opt-in)

- `src/wind_adjust.py` — the lever module:
  - `apply_wind_shrink(proj_df, high_wind_teams, shrink, points_col)` — pure
    function, no I/O; the byte-identical/scoping guarantee lives here.
  - `compute_high_wind_teams(season, week, schedules_df=None)` — resolves
    this week's high-wind teams, preferring committed Bronze weather
    (`src/weather_features.py`, 2016-2025) and falling back to a forecast
    fetch for weeks not yet archived.
  - `fetch_forecast_high_wind_teams(schedules_df, season, week)` — Open-Meteo
    **forecast** API fallback for current-season weeks. Verified 2026-08-16
    that the forecast endpoint (`api.open-meteo.com/v1/forecast`) works with
    the identical no-key pattern as the historical archive
    (`archive-api.open-meteo.com/v1/archive`) used by
    `scripts/bronze_weather_ingestion.py` — same param shape, just
    `forecast_days` instead of a date range. Confirmed live in this task
    (200 response, hourly `wind_speed_10m` returned in mph).
  - `apply_wind_adjust(proj_df, season, week, schedules_df, shrink)` —
    orchestrator wiring the above together; logs a
    `Wind forecast GATE COVERAGE: n_covered/n_eligible` line whenever the
    forecast fallback fires, and a fail-open skip message when neither
    Bronze nor forecast has data (no adjustment applied — never a guess).
  - **Fail-open discipline:** a per-venue forecast request failure (network
    error, missing stadium coords, kickoff beyond the 16-day forecast
    horizon) skips only that game — it never defaults a game to
    "high-wind" and never crashes the run. Forecast-at-projection-time is
    legitimately pre-game information (not a leak) since forecasts are
    fetched before kickoff, same as injury reports.
- `scripts/generate_projections.py` — `--wind-adjust` / `--wind-adjust-shrink`
  flags (weekly mode only), applied after `--wr-tiebreak` and before
  `--use-events`, mirroring the existing opt-in-lever ordering convention.
- `scripts/backtest_projections.py` — matching `--wind-adjust` /
  `--wind-adjust-shrink` flags and `run_backtest()` parameters, so the lever
  is evaluable on historical seasons the same way as the other opt-in
  levers. `schedules_df` (already loaded for the matchup factor) is passed
  through for signature parity with production, though historical backtest
  seasons are always covered by committed Bronze weather so the forecast
  fallback never fires there in practice.
- `tests/test_wind_adjust.py` (14 tests, all passing):
  - `TestShrinkMath` — exact multiplicative-shrink arithmetic, the fitted
    constant applied correctly, floor at 0.
  - `TestScopingByteIdenticalGuard` — RB untouched even on a high-wind team,
    low-wind team untouched, empty `high_wind_teams` set → fully
    byte-identical output, `wind_adjust_flag` set only on the exact rows
    that changed, empty-DataFrame edge case.
  - `TestForecastFailOpen` — a `requests.get` exception skips that game
    without raising, a missing stadium-coords entry skips gracefully, an
    empty schedules frame returns cleanly.
  - `TestComputeHighWindTeamsFailOpen` — no Bronze + no schedules →
    `source="unavailable"` and a full no-op through `apply_wind_adjust`.

## Files

- `src/wind_adjust.py` — the lever (fit constant, shrink, forecast fallback)
- `scripts/generate_projections.py` — `--wind-adjust` wiring (weekly mode)
- `scripts/backtest_projections.py` — `--wind-adjust` wiring (backtest mode)
- `tests/test_wind_adjust.py` — 14 unit tests (shrink math, scoping,
  fail-open forecast)
- `output/backtest/backtest_half_ppr_ml_fullfeatures_20260816_200952.csv` —
  the sealed-2025 backtest generated this task (one-touch, logged to
  `.planning/holdout_ledger.json`)
- `.planning/holdout_ledger.json` — appended this task's sealed-2025 read
