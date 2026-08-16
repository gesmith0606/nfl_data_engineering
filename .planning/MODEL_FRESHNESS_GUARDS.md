# Model Freshness Guards — 2026-08-15/16

Closes MODEL_REVIEW_2026_08_15.md findings #2, #3, #5, #6, #7, #9, #11: makes the
model-staleness failure class structurally detectable, mirroring what
`scripts/check_data_completeness.py` did for data holes
(`.planning/DATA_COMPLETENESS_AUDIT.md`). New files: `scripts/check_model_freshness.py`,
`src/model_provenance.py`. Touched: `.github/workflows/ci.yml`, `src/rb_role_signals.py`,
`scripts/silver_advanced_transformation.py`. Did **not** touch
`src/ml_projection_router.py`, `src/hybrid_projection.py`, `src/quantile_models.py`,
`scripts/train_*.py`, or `models/` — those are owned by concurrent workstreams (confirmed
live: `git status` shows `src/hybrid_projection.py`, `src/quantile_models.py`,
`src/ml_projection_router.py`, and most of `models/residual/` + `models/quantile/`
mid-edit by other agents during this same session).

## 1. The checker: `scripts/check_model_freshness.py`

### Design

One `CheckResult(id, tier, passed, message)` per check, same shape and same
`print_report()`/exit-code convention as `check_data_completeness.py`
(FAIL blocks, WARN reports-but-never-blocks). Three mechanisms per shipped family
(`models/residual`, `models/quantile`, `models/ensemble`, `models/bayesian`):

- **(a) Imputer NaN statistics** — `check_imputer_nan()`. Loads every frozen
  `SimpleImputer` this family ships and asserts `imputer.statistics_` has zero NaN.
  This is the exact finding #1 mechanism: sklearn's `SimpleImputer` (default
  `keep_empty_features=False`) permanently drops any column that was all-NaN *at fit
  time* from every future `transform()` — confirmed empirically (see §2).
  FAIL-tier for residual/quantile/ensemble, WARN-tier for bayesian.
- **(b) Live-schema mismatch** — `check_feature_coverage()`. Assembles a real, current
  feature frame via `src/player_feature_engineering.py::assemble_player_features()`
  (the same function the live serving path uses) and cross-checks it against each
  artifact's fitted feature list two ways: `.../dropped` (FAIL-capable) flags any
  feature that is **both** live right now **and** has a NaN imputer statistic — i.e.
  reproduces finding #1 directly, not just "is there a NaN somewhere"; `.../live_coverage`
  (always WARN) flags features simply absent from the live probe (may be normal schema
  drift). Best-effort: both degrade to a WARN "skipped" result when no local
  `data/silver/` exists (it is gitignored — never present in a fresh CI clone).
- **(c) Staleness** — `check_staleness()`, WARN-tier only. Compares artifact vintage
  (`trained_at`/`created_at` from meta.json, or an mtime fallback when neither exists)
  against the newest `*.parquet` mtime anywhere under `data/silver/` — the lazy proxy
  the task spec asked for, not a real content hash. Skipped (WARN, non-blocking) when
  `data/silver/` isn't present locally.

`--no-probe` skips (b) and (c) outright (both degrade to the same WARN-skip regardless,
this just avoids the ~5s `assemble_player_features()` call) — used in CI, since
`data/silver/` is never committed there. `models/` **is** committed (only
`models/quantile/_backup_leaky/` is gitignored), so check (a) — the FAIL-tier one — runs
for real in CI off a fresh checkout with no extra setup.

### Structural test coverage

`tests/test_check_model_freshness.py`, 42 tests: pure-function tests for all three check
mechanisms against synthetic `SimpleImputer`s (clean / NaN-stat, single/multi-column),
per-family tests against `tmp_path`-built fake artifacts (residual LGB + Ridge-pipeline
shapes, quantile shared-imputer shape, ensemble Ridge/MeanMeta shape incl. the "no
imputer at all" verdict, bayesian's forced-WARN tier), `find_newest_silver_timestamp` /
`probe_live_feature_columns` (monkeypatched, never-raises contract), `print_report` exit
codes, and two end-to-end tests against the real `models/` directory. Deliberately does
**not** pin exact today's-artifact pass/fail counts anywhere (see §2 — this repo has
concurrent retrains landing mid-session, so that would be flaky by design); what's pinned
is structural facts about the code (e.g. "ensemble never claims to have an imputer").

## 2. Current-state results — and why they moved mid-session

**This is a live, shared working tree.** `git status` at the time of writing shows other
agents mid-edit on `src/hybrid_projection.py`, `src/quantile_models.py`,
`src/ml_projection_router.py`, most of `models/residual/*`, and all of `models/quantile/*`.
Concretely: my first empirical check of `models/quantile/imputer.pkl` (early in this
session) found **454 features, 28 NaN statistics** — reproducing finding #1 exactly,
including the entire `snap_pct*` family and the `prospect_comp_*`/college columns. Later
in the same session, after another workstream's quantile retrain landed
(`models/quantile/imputer.pkl` mtime `2026-08-15 23:17`, `metadata.json` `created_at`
`2026-08-15T23:06:57`), the checker reported **486 features, 0 NaN** — the retrain fixed
it. `python scripts/check_model_freshness.py` now exits 0 (all FAIL-tier checks pass;
14 WARN-tier misses remain, all staleness/live-coverage, non-blocking). Both snapshots
were captured directly off the real repo state, not simulated — this is the checker
correctly detecting a real fix landing in real time, which is exactly what it's for.

Residual family (`models/residual/`): clean across QB/RB/WR/TE, both mechanisms —
0 NaN imputer statistics on every position, and no live feature silently dropped. Two
low-signal WARNs: `residual/te` has 2 features (`route_rate_trail4`, `route_rate_slope`)
absent from today's live schema probe, and `residual/wr` + `residual/te` staleness WARNs
against my own re-run of `silver_advanced_transformation.py --season 2023` during testing
(§4) bumping the Silver mtime past their June vintage — an artifact of my own test run,
not a real regression.

### Ensemble Ridge meta-learner verdict (finding #6)

**No frozen imputer exists in this family — verified empirically, not assumed.**
`models/ensemble/ridge_{spread,total}.pkl` are `ensemble_training.MeanMeta` /
`RidgeCV` / non-negative-`Ridge` instances (`select_meta_learner()` picks the best of
the three by season-out CV) that stack exactly 3 inputs: `xgb_pred`, `lgb_pred`,
`cb_pred` — always-populated OOF predictions from the three base learners, never raw
features. The base features feeding XGB/LGB/CB themselves are cleaned with a **live**
`week_df[...].fillna(0.0)` at inference time (`scripts/generate_predictions.py:184-338`),
not a persisted `SimpleImputer`. So the finding #1 mechanism (frozen fit-time NaN
statistics silently dropping a now-real column forever) is structurally impossible in
this family — there's no frozen artifact for it to happen to. The checker reports this
explicitly as a passing `N/A` result (`ensemble/{spread,total}/imputer_nan`) rather than
silently omitting the check, per the task's ask to "check them now, report what you find."

One incidental finding while building the check: `models/ensemble/ridge_{spread,total}.pkl`
are legacy `MeanMeta` pickles predating `coef_`/`intercept_` persistence on that class —
their unpickled `__dict__` is empty, so `getattr(meta_model, "coef_", None)` is `None`
and the shape-sanity check (`.../meta_shape`) has nothing to check. Also reported
explicitly rather than silently skipped. `models/ensemble_retrained_2026_08_15/` (a
newer, concurrently-produced sibling directory — not one of the 4 canonical families the
task named) *does* have `coef_`/`intercept_` populated, for what it's worth.

Bayesian family: all four positions clean on imputer NaN (0/60 each), but with sizeable
`live_coverage` WARNs (21-31 of 60 features absent from today's live schema probe per
position) — expected for a research-tier, stale (`.joblib` mtime June 24), unwired
family per finding #14; forced WARN-tier throughout regardless of severity, as specified.

## 3. `src/model_provenance.py` — provenance helper

`build_provenance(source_dirs, data_root=None, project_root=None) -> dict`. Given a
mapping of short source labels to paths relative to `data/` (e.g.
`{"silver_players_usage": "silver/players/usage"}`), returns:

```json
{
  "generated_at": "2026-08-15T23:06:57+00:00",
  "git_sha": "abc123...",
  "sources": {
    "silver_players_usage": {
      "path": "silver/players/usage",
      "row_count": 123456,
      "n_files": 10,
      "latest_partition_at": "2026-08-10T09:00:00+00:00"
    }
  }
}
```

Row counts come from Parquet footer metadata only (`_scan_parquet_source`, same
technique as `check_data_completeness.py::_sum_parquet_rows` — no data is read).
`git_sha()` shells out to `git rev-parse HEAD`, degrading to `None` (never raising)
outside a git repo, with git missing, or on timeout. 15 unit tests in
`tests/test_model_provenance.py`, including a real-repo assertion that `git_sha()`
resolves to a real 40-char hex SHA in this checkout.

### Exact patch for each train_*.py entry point (not applied — those files are owned by
### other workstreams per the task's file-ownership boundary; apply when convenient)

**`src/hybrid_projection.py`** — two near-identical sites build residual `meta` dicts
(LGB path ~line 1153, Ridge path ~line 1205), neither has `trained_at` today (confirmed
empirically — every `models/residual/*_meta.json` lacks it). Add 3 lines before each
`json.dump(meta, f, indent=2)`:

```python
from model_provenance import build_provenance  # top-of-file import, once

meta["provenance"] = build_provenance({
    "silver_players_usage": "silver/players/usage",
    "silver_players_advanced": "silver/players/advanced",
    "bronze_players_snaps": "bronze/players/snaps",
    "bronze_players_injuries": "bronze/players/injuries",
})
```

**`src/quantile_models.py::save_quantile_models`** (~line 385, right before the
`metadata = {...}` dict is built) — same pattern:

```python
metadata = {
    "feature_cols": result["feature_cols"],
    ...
    "provenance": build_provenance({
        "silver_players_usage": "silver/players/usage",
        "silver_players_advanced": "silver/players/advanced",
    }),
}
```

**`src/bayesian_projection.py`** (~line 680, inside the `metadata = {...}` dict before
the `_meta.json` write at line 693) — identical 2-line addition:

```python
"provenance": build_provenance({"silver_players_usage": "silver/players/usage"}),
```

**`src/ensemble_training.py::train_ensemble`** (~line 513) already stamps `trained_at`
(a real one — `datetime.utcnow().isoformat() + "Z"`) and `training_seasons`, so this one
is lower priority, but still lacks row counts/git SHA. Add to the `metadata` dict:

```python
"provenance": build_provenance({
    "silver_teams_pbp_derived": "silver/teams/pbp_derived",
    "bronze_schedules": "bronze/schedules",
}),
```

## 4. CI wiring — `.github/workflows/ci.yml`

New `model-freshness` job, right after `data-completeness`. Fresh checkout + full
`pip install -r requirements.txt` (unpickling shipped sklearn/lightgbm/xgboost/catboost
artifacts needs matching library versions, not just pyarrow), then
`python scripts/check_model_freshness.py --no-probe` (fast, artifact-only — CI never has
`data/silver/` to probe against).

**`continue-on-error: true` is wired, intentionally and temporarily**, with an inline
comment block explaining why and a `TODO: flip continue-on-error to false ... the moment
check_model_freshness.py --no-probe exits 0 on main`. At the moment I wired it, the
job's underlying check (`quantile/imputer_nan`) *was* genuinely red — the pre-retrain
28-NaN state from §2. By the time I finished testing, another workstream's retrain had
already fixed it, so `--no-probe` now exits 0 in this checkout. I left `continue-on-error`
in place anyway rather than flipping it based on my own local run: the task was explicit
("If it fails on CURRENT repo state... wire it with continue-on-error: true... do not
paper over a red check by weakening thresholds"), residual/wr and residual/te still carry
real staleness WARNs, and — more importantly — I don't own the retrain workstreams and
can't attest to what lands on `main` by the time this merges. Whoever lands the next clean
green run of `check_model_freshness.py --no-probe` on `main` should flip it per the TODO
comment; don't let it sit soft-fail past that point.

## 5. Finding #5 — RB role-signal coverage assertion (`src/rb_role_signals.py`)

Added `_assert_season_coverage(df, seasons, source_name, min_rows=100)` and wired it into
`build_rb_role_signals()` right after loading snaps/injuries/depth_charts (the lines
finding #5 cited: 755/473/526, all "if empty: silently degrade" branches). For each
requested season, warns loudly (`logger.warning`, `"GATE COVERAGE: ..."` prefix — same
convention as `scripts/silver_player_transformation.py::_prepare_snap_data`'s existing
`"WARNING: GATE COVERAGE: snap join matched only..."` line) when a season's row count is
below the floor, naming the exact season and source. This is defense-in-depth at the
point of consumption: `check_data_completeness.py` already gates the underlying Bronze
paths at CI/pipeline time, but `build_rb_role_signals()` degrades silently (0-fill /
empty table) if invoked directly with thin data (a notebook, an ad-hoc script) — this
closes that gap with a warn, not a raise, matching the codebase's warn-never-block
convention and the audit's own "warn-loud" phrasing. 5 new tests in
`tests/test_rb_role_signals.py` (36 total in that file, all passing), including an
end-to-end test that `build_rb_role_signals()` itself surfaces the warning for a season
with real depth-chart data but near-empty snaps — the literal shape of the original
RB_SNAP_COLLAPSE bug.

## 6. Finding #9 — Silver name-keyed join sweep

Swept every `scripts/silver_*.py` plus the `src/` helper modules they call
(`player_analytics.py`, `player_advanced_analytics.py`, `historical_profiles.py`,
`market_analytics.py`, `game_context.py`, `ftn_features.py`, `team_analytics.py`,
`player_feature_engineering.py`, `feature_engineering.py`) for `.merge(...)` calls keyed
on a name/display-name column instead of an ID.

**Found and fixed:** `scripts/silver_advanced_transformation.py`'s QBR merge (~line 458,
`on=["player_display_name_norm", "recent_team", "season", "week"]`) had only a
row-count-preservation `assert` — which a silent-0%-match left join always satisfies,
since unmatched rows just get NaN and the row count doesn't change. Its sibling three
merges up (the PFR pressure merge, ~line 337, same join-key shape) already had a real
match-rate check; QBR didn't. Added the same pattern, scoped to QB rows (QBR is QB-only,
so a match rate over all positions would always misleadingly read as "low"): computes
`qb_matched / qb_total`, logs it at INFO always, and logs
`"GATE COVERAGE: QBR match rate below 50%..."` via `logger.warning` when it drops below
50% — verified against real 2023 data (`python scripts/silver_advanced_transformation.py
--season 2023 --no-s3`): `QBR match rate: 77.5% (535/690 QB player-weeks)`, no crash, no
behavior change to the pipeline's output.

**Verified as already covered** (no changes needed): `_prepare_snap_data` in
`scripts/silver_player_transformation.py` (the reference pattern this whole task points
at) and the PFR pressure merge above both already have match-rate assertions. The NGS
merges in `silver_advanced_transformation.py` and every merge in
`player_feature_engineering.py`/`player_analytics.py`/`team_analytics.py` are keyed on
`player_gsis_id`/team abbreviation/`game_id`, not names — not in scope.

**Found, not fixed (outside this task's file-ownership boundary — `src/college_prospect_features.py`
is not `scripts/silver_*.py` and not on my file list):** `src/college_prospect_features.py`
line 357, `result.merge(college, on=available_merge, how="left", ...)` where
`available_merge` can be just `["player_name"]` (comment: *"Merge on player_name (fuzzy —
best effort)"*) — a genuine cross-source name join (NFL-side roster/combine/draft data vs.
CFBD college stats), no match-rate check at all. This feeds `college_market_share`,
`college_yards_per_game`, `college_breakout_age` and similar `college_*`/`prospect_comp_*`
columns via `scripts/build_prospect_features.py` → `data/silver/college/prospect_features/`
— i.e. it **is** part of the Silver layer despite the non-`silver_`-prefixed script name,
and those are exactly the columns finding #1 caught being silently dropped by the
quantile imputer. Recommended patch (same shape as the QBR fix above), for whichever
agent owns that file:

```python
if available_merge:
    before = len(result)
    result = result.merge(
        college, on=available_merge, how="left", suffixes=("", "_college")
    )
    matched = result["total_yards"].notna().sum() if "total_yards" in result.columns else 0
    match_pct = (matched / before * 100) if before else 0.0
    logger.info("College stats match rate: %.1f%% (%d/%d)", match_pct, matched, before)
    if match_pct < 50:
        logger.warning(
            "GATE COVERAGE: college stats match rate below 50%% (%.1f%%) -- "
            "check player_name normalization", match_pct,
        )
```

(`(also checked and ruled safe: college_prospect_features.py:681`'s
`df.merge(best_ages, on="player_name")` is a self-join — `best_ages` is derived from
`df.groupby("player_name")` on the same frame, so every key is guaranteed present by
construction; not a genuine 0%-match risk, no assertion warranted.)

## 7. Tests summary

| File | Tests | Status |
|---|---|---|
| `tests/test_check_model_freshness.py` (new) | 42 | pass |
| `tests/test_model_provenance.py` (new) | 15 | pass |
| `tests/test_rb_role_signals.py` (+5 new, 36 total) | 36 | pass |
| Full suite (`pytest tests/ -q`) | 3660 collected (excl. 2 pre-existing unrelated flakes below) | pass |

Two pre-existing failures in `tests/test_data_quality.py` (`test_freshness_check_ok`,
`test_freshness_check_warn`) — a day-boundary timing flake ("3 days old" vs "2 days old"
depending on exact wall-clock at fixture setup vs assertion). Confirmed unrelated: that
file isn't touched by this work, and `git diff` on it is empty. Not fixed (out of scope,
not owned by this task).
