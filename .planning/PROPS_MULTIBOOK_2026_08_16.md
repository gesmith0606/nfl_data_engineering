# Props multi-book read path — 2026-08-16

Follow-up to `.planning/PROPS_DATA_PLAN.md` Phase 2 (`bronze_weekly_props_ingestion.py`,
built earlier in this session), whose own docstring flagged the gap this closes: DK/FanDuel
direct captures write week-partitioned, book-tagged files that `--props-blend`'s single-glob
read never saw. This makes `--props-blend` genuinely multi-book, and separately fixes a
dormant quantile-model bug found while wiring `generate_projections.py`'s floor/ceiling call
site to carry real features (`.planning/QUANTILE_REFIT_2026_08_15.md` section 7's flagged gap).

## 1. Read-path design (`src/prop_implied.py`)

Three new functions, appended after `apply_props_blend`:

- **`discover_props_sources(season, week, project_root) -> Dict[str, str]`** — locates the
  latest file per capture source:
  - `"odds_api"`: latest flat `props/season={season}/props_*.parquet`
    (`scripts/bronze_props_ingestion.py`) — season-only partition (no `week=` subdir), matching
    that source's actual layout; excludes gitignored `props_archive_*.parquet` historical-backtest
    files (`PROPS_BLEND_BACKTEST_2026_08_16.md`).
  - `"dk_direct"` / `"fd_direct"`: latest week-partitioned
    `props/season={season}/week={week}/props_dk_*.parquet` / `props_fd_*.parquet`
    (`scripts/bronze_weekly_props_ingestion.py`).
  A source with no file present is simply absent from the dict — the whole thing is empty when
  nothing exists for that (season, week), which is the fail-open signal callers already checked
  for.
- **`load_multibook_props(season, week, project_root) -> pd.DataFrame`** — reads every source
  `discover_props_sources` finds and concatenates them, tagging each row's originating capture
  with a new `capture_source` column (`odds_api` / `dk_direct` / `fd_direct`). Empty frame when
  no source exists.
- **`summarize_book_coverage(props_df) -> pd.DataFrame`** — per-`market` distinct-bookmaker
  count + sorted book-name list, for the visibility requirement (logged by the CLI, see §3).

**Why `compute_prop_implied_points` needed zero changes**: it already groups by
`(name_key, market)` and takes the median across every row in that group, and every source
already carries a correct per-row `bookmaker` value (verified in
`bronze_weekly_props_ingestion.py`'s own schema-mapping notes — DK rows are tagged
`"draftkings"`, FanDuel rows `"fanduel"`, matching the Odds API's existing bookmaker vocabulary
exactly). Concatenating sources with real `bookmaker` values was the only thing missing; the
median-across-books machinery was already correct and already proven in production for the
Odds API's own multi-bookmaker snapshots.

## 2. Cross-book rule

Matches `src/season_prop_implied.py`'s documented behavior exactly, because it's the same
underlying function: **median of per-book implied stat means when 2+ books quote a market;
that book's single value when only one quotes it.** No new logic was written for this — DK/FD
rows landing in the same `(name_key, market)` group as Odds API rows is sufficient for
`compute_prop_implied_points`'s existing `means.dropna().median()` to do the right thing
automatically. Verified directly (`tests/test_prop_implied_multibook.py::test_multibook_median_of_implied_points`):
three balanced-juice books quoting rush yards at 80.5 / 84.5 / 88.5 (Odds API/betmgm,
DK-direct, FD-direct respectively) produce an implied value of 84.5 — the median, not a mean or
a book-priority pick.

## 3. CLI wiring (`scripts/generate_projections.py`, `--props-blend` block)

Replaced the old single `_glob.glob(...props_*.parquet)` + `pd.read_parquet(files[-1])` with:

```python
props_sources = discover_props_sources(args.season, args.week, PROJECT_ROOT)
...
props_df = load_multibook_props(args.season, args.week, PROJECT_ROOT)
...
coverage = summarize_book_coverage(props_df)
# prints "Props book coverage per market: player_rush_yds=2 book(s) ['draftkings', 'fanduel'], ..."
```

Now prints, per run: which source files were found (`Props blend sources (N): odds_api=...,
dk_direct=..., fd_direct=...`) and per-market book counts — both requirements from the task
brief ("firing visible in output/log").

## 4. Backward compatibility

- **Zero books found**: `discover_props_sources` returns `{}`, the CLI prints the same-shaped
  WARN and skips the blend — identical fail-open behavior to before, just week-scoped in the
  warning text now (season+week vs season-only).
- **Only Odds API present → byte-identical**: `load_multibook_props` on an Odds-API-only
  directory returns that file's rows plus one added `capture_source` column;
  `compute_prop_implied_points` doesn't read that column, so its output is identical either way.
  Proven directly:
  `tests/test_prop_implied_multibook.py::TestLoadMultibookProps::test_byte_identical_when_only_odds_api_present`
  asserts `compute_prop_implied_points(pd.read_parquet(<file>))` equals
  `compute_prop_implied_points(load_multibook_props(...))` via `pd.testing.assert_frame_equal`
  (passes).

## 5. Quantile CLI call-site fix (`.planning/QUANTILE_REFIT_2026_08_15.md` §7 gap)

That report flagged that `generate_projections.py`'s weekly floor/ceiling call site passes
`add_floor_ceiling()` the trimmed weekly-output frame, which never carries the quantile model's
feature columns — so the quantile path's `has_features` gate always failed and every call
(with or without `--conformal-bands`) silently used the heuristic ±mult fallback.

**Fix**: extracted a new `attach_floor_ceiling_with_features(projections, season, week,
use_conformal, log)` in `generate_projections.py` (called from the weekly, non-`--ml`,
non-`--preseason` branch in place of the bare `add_floor_ceiling()` call). It assembles the real
feature vector via `player_feature_engineering.assemble_player_features(season)`, filters to
the target week, and joins the feature columns onto `projections` by `player_id` before calling
`add_floor_ceiling()`; only the two new `projected_floor`/`projected_ceiling` columns are kept
on the returned frame, so output schema is unchanged. Fails open (heuristic fallback, `log()`
warning) on empty features or any exception.

**A second, real bug found while verifying this** (not previously documented): even with
features wired through, the quantile path crashed with `ValueError: The feature names should
match those that were passed during fit` — `sklearn.SimpleImputer.transform()` requires the
*exact* fit-time column set; `predict_quantiles()`'s `valid_features` subsetting silently hands
it a subset when the input frame doesn't have every one of the 486 trained-on columns, which
raises instead of gracefully imputing. Root cause: **Silver's `advanced` layer is missing all
`qbr_*` columns for seasons 2024 and 2025** (confirmed: 2022/2023 advanced Parquet has 16
`qbr_*` columns, 2024/2025 has zero) — a pre-existing Bronze/Silver QBR coverage gap, not
something introduced by this task. Fixed within `attach_floor_ceiling_with_features` (not
`quantile_models.py`, kept out of scope per the mission's file boundaries): any of the loaded
model's `feature_cols` absent from the assembled frame are added as an all-NaN column before the
join, so the imputer receives its full fit-time column set and fills the gap with its own
(verified non-NaN, per the June `_check_imputer_statistics` fix) median statistics — exactly the
same handling a genuinely-missing-at-training-time column already gets.

**Verified end-to-end, real data, no mocking** (`tests/test_generate_projections_floor_ceiling.py::TestRealDataQuantileFire`,
season 2025 week 10, matching the original report's own smoke-test season/week):

```
INFO:projection_engine:Floor/ceiling set via quantile models
```

fires, floor/ceiling values vary per player (not the flat heuristic `pts*(1±mult)` pattern), and
`floor <= projected_points <= ceiling` holds on every row.

## 6. Tests

- `tests/test_prop_implied_multibook.py` (13 tests): `discover_props_sources` (missing-week
  fail-open, Odds-API-only, archive-file exclusion, latest-file-wins, DK/FD week-scoping,
  all-three-found), `load_multibook_props` (fail-open empty frame, single-book passthrough,
  multi-source concatenation + `capture_source` tagging, cross-book median, byte-identical-legacy),
  `summarize_book_coverage` (empty input, per-market counts).
- `tests/test_generate_projections_floor_ceiling.py` (6 tests): quantile path fires with a full
  synthetic feature frame; missing-columns (simulated `qbr_*` gap) backfilled without crashing;
  empty feature frame falls back to heuristic with a warning; feature-assembly exception falls
  back to heuristic with the exception message in the warning; output schema unchanged besides
  the two new columns; real-2025-week-10 end-to-end fire (skipped if local Silver data absent).

Ran together with the existing props/quantile suites for regressions:

```
tests/test_prop_implied.py tests/test_prop_implied_multibook.py tests/test_season_prop_implied.py
tests/test_generate_projections_floor_ceiling.py tests/test_quantile_models.py
tests/test_bronze_weekly_props_ingestion.py tests/test_bronze_props_ingestion.py
tests/test_projection_engine.py
    -> 224 passed
```

Full repo suite also run (`pytest tests/`); one pre-existing, unrelated failure
(`tests/test_bronze_2025.py::TestBronze2025Completeness::test_player_seasonal_exists` — a local
Bronze `players/seasonal/season=2025` file is simply absent on this machine, unrelated to props
or quantile code) confirmed present before this session's changes and left as-is (out of scope:
neither file is in `src/prop_implied.py`, `generate_projections.py`, `backtest_projections.py`,
or their tests).

## 7. `scripts/backtest_projections.py` — confirmed no-op

Grepped for any `props`/`prop_implied`/`PROPS_BLEND` reference: none exist. Confirmed by
`PROPS_BLEND_BACKTEST_2026_08_16.md` ("that script has no `--props-blend` wiring — the flag
exists solely on `generate_projections.py`"). Nothing to extend for multi-book support here;
left untouched.

## Files changed

- `src/prop_implied.py` — added `discover_props_sources`, `load_multibook_props`,
  `summarize_book_coverage`, plus `glob`/`os` imports. `compute_prop_implied_points` /
  `apply_props_blend` unchanged.
- `scripts/generate_projections.py` — `--props-blend` block now calls the new multi-book read
  path (was: single `glob` + `pd.read_parquet(files[-1])`); new module-level
  `attach_floor_ceiling_with_features()` replaces the inline feature-less
  `add_floor_ceiling()` call in the weekly (non-ml, non-preseason) branch.
- `tests/test_prop_implied_multibook.py` (new), `tests/test_generate_projections_floor_ceiling.py`
  (new).
- Not touched: `scripts/backtest_projections.py` (confirmed no existing props path), `src/quantile_models.py`,
  `web/api`, `web/frontend`, `scripts/generate_frontend_metrics.py`.
