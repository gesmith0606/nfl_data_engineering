# Small Fixes — 2026-08-10

Three small, independent bugs fixed per the sprint punch list. TDD where testable; no
multi-hour runs kicked off.

## 1. Sentiment roster-year hardcode

**File:** `src/sentiment/processing/pipeline.py`

**Bug:** `_roster_provider_factory` was called only once, at extractor construction time
inside `_build_extractor("claude_primary")`, using `datetime.now(timezone.utc).year` — the
*current calendar year* — instead of the season the caller actually asks for via
`pipeline.run(season=..., week=...)`. Since the season argument isn't known until `run()` is
called (construction happens first), any backfill run for a past season silently kept
resolving player names against the current year's roster parquet.

**Fix:** `run()` now rebinds `self._extractor.roster_provider` with
`self._roster_provider_factory(season)` at the top of the method, before either run-loop
branch executes, using the real `season` argument. The construction-time provider is now
explicitly documented as a placeholder that's always overwritten before any extraction
happens.

**Test:** `tests/sentiment/test_pipeline_claude_primary.py::test_run_rebinds_roster_provider_to_requested_season`
— seeds two roster parquets (a past season and the real current calendar year) with
disjoint name lists, asserts the construction-time provider returns the current-year names,
then asserts `run(season=<past>)` rebinds it so the provider returns the past-season names
instead.

**Evidence:**
```
tests/sentiment/test_pipeline_claude_primary.py .............. [14 passed]
tests/sentiment/ + tests/test_sentiment_processing.py ......... [261 passed]
```

## 2. Rookie classifier (dynasty/rookies)

**File:** `web/api/routers/dynasty.py` (+ tests in `tests/test_dynasty_api.py`)

**Observed bug (prod, 2026-08-08):** `/api/dynasty/rookies` ranked a kicker (Maddux
Trujillo) #1 and several 24-26-year-old journeyman UDFA WRs, with the `role` column showing
`unknown` for almost every row.

**Diagnosis:** The rookie *detection* itself (`entry_year == season OR years_exp == 0`
against the committed `rosters` Bronze parquet) was already correct — those WRs genuinely
have `entry_year=2026, years_exp=0` (real UDFA signees per nflverse, not a classifier bug).
Two real problems:
- No position filter. Preseason projections always include a K row (flat ~127-pt league-
  average baseline, generated unconditionally for preseason regardless of the weekly
  `--include-kickers` flag), which outranks every rookie WR/RB whose projection starts near
  zero. The frontend's own position selector for dynasty rankings only offers
  QB/RB/WR/TE — K/DST were never meant to appear on this page.
- `role` was read straight from the preseason projections file's `low_sample_role` column,
  which is `None` for ~63% of rows and the *string* `"unknown"` for another ~33% (only ~3%
  have a resolved `starter`/`backup`) — the projection pipeline's own depth-chart join
  mostly couldn't place rookies at generation time, and the router surfaced that literal
  `"unknown"` string for nearly every rookie instead of treating it as "no data."

**Fix:**
- Added `_ROOKIE_POSITIONS = {"QB", "RB", "WR", "TE"}` filter in `rookie_rankings()` — K/DST/DEF excluded. No league-scoring context reaches this endpoint (no `league_id`/scoring param), so there's nothing to opt back in on.
- Added `_load_depth_chart_roles(season)`, which re-resolves role fresh from the committed
  `data/bronze/depth_charts/` Bronze (ingested 2026-08-04) via the existing
  `src.rookie_projection._role_from_depth_charts` resolver — reused, not reimplemented.
  Only definitive `starter`/`backup` results are kept; anything else (not on the depth
  chart, or 3rd-string-or-deeper which that resolver itself calls `"unknown"`) is dropped
  from the map, so the API now returns `null` for `low_sample_role` instead of the string
  `"unknown"` (frontend already renders `null` as `—`).
- `_load_roster`'s file-finding glob was factored into `_find_latest_roster_file()` so the
  new depth-chart helper can reuse it without duplicating the glob.

**Tests added:**
- `test_rookies_excludes_kickers` — rookie K with a higher raw point total than a rookie WR
  must not appear; only the WR is returned.
- `test_load_depth_chart_roles_drops_non_definitive_roles` — synthetic depth chart with
  1st/2nd/3rd string at one position; asserts starter/backup survive and 3rd-string is
  absent from the map (not surfaced as `"unknown"`).
- `test_load_depth_chart_roles_empty_when_no_bronze_data` — missing Bronze fails open to
  `{}`, no 500.

**Manual verification against real 2026 data** (`/api/dynasty/rookies?season=2026`): no
`K` position in the response; `low_sample_role` is `null` where previously `"unknown"`.

**Evidence:**
```
tests/test_dynasty_api.py ........... [11 passed]  (8 pre-existing + 3 new)
```

## 3. Corrupted LightGBM ensemble artifacts

**Files:** `models/ensemble/lgb_spread.txt`, `models/ensemble/lgb_total.txt`

**Root cause (found, not guessed):** Both files are git-tracked and load fine straight from
the git blob (`git show HEAD:models/ensemble/lgb_spread.txt` → 81 trees load cleanly). The
*working-tree* copies on this machine were corrupted by `core.autocrlf=true` (this
machine's global git config) silently rewriting every `\n` to `\r\n` on checkout. LightGBM's
`.txt` format uses a byte-offset `tree_sizes` header to seek directly to each `Tree=N`
block; adding one byte per line shifts every subsequent seek, landing mid-line and
producing exactly the reported `Model format error, expect a tree here` — confirmed by
stripping the `\r\n`→`\n` from the corrupted file and reloading successfully, and by the
byte-count delta matching the line count exactly (`lgb_total.txt`: 11,069 bytes on disk vs
10,898 in the git blob = 171 extra bytes = 171 lines).

This is **local-only, not a prod issue** — the git blob itself is uncorrupted LF, so a Linux
checkout (Railway/HF Spaces) never hits this; no `.gitattributes` previously pinned the
line-ending policy, so it silently re-corrupts on every fresh Windows clone/checkout.

**Consumer:** `src/ensemble_training.py::load_ensemble()` loads these as `lgb.Booster` —
used by `scripts/generate_predictions.py --ensemble` (production game-prediction CLI) and
gated by `scripts/sanity_check_projections.py`'s artifact-completeness check. This was the
blocker reported in `.planning/VACUOUS_GATE_AUDIT.md` for `ablation_market_features.py --dry-run`.

**Fix (no retraining needed):**
1. Restored both working-tree files from the git blob (`git show HEAD:<path>`, byte-exact,
   LF-only) — no regeneration, no training run.
2. Added `.gitattributes` pinning `models/ensemble/lgb_*.txt -text` so line endings are
   never converted regardless of `core.autocrlf`, preventing recurrence on any future
   Windows clone/checkout.

**Verification:**
```
lightgbm.Booster(model_file="models/ensemble/lgb_spread.txt") -> 81 trees, loads clean
lightgbm.Booster(model_file="models/ensemble/lgb_total.txt")  -> 1 tree, loads clean

python scripts/ablation_market_features.py --dry-run
  Baseline: ATS=50.6%, Profit=-9.45
  [DRY RUN] Baseline evaluation complete. Skipping retraining.
  Baseline ATS: 50.6%
  Baseline Features: 120

tests/test_ensemble_training.py ..................... [12 passed]
```

The original ablation blocker from `VACUOUS_GATE_AUDIT.md` is resolved — no separate
"regeneration command" needed since the fix was restoring the correct bytes, not retraining.

## Suite-wide check

```
pytest tests/ -m "not integration and not network"
-> 1 failed, 3580 passed, 22 skipped, 13 deselected in 176.89s
```

The one failure, `tests/test_data_quality.py::test_freshness_check_ok`, is a pre-existing
date-relative flake (`assert '3 days old' in '... is 2 days old'`) unrelated to any of the
three fixes above — it doesn't touch sentiment, dynasty, or model artifacts, and reproduces
on a clean checkout (day-count math against "now"). Not touched here.

No changes were made to `scripts/bronze_ingestion_simple.py`,
`silver_advanced_transformation.py`, or `check_data_completeness.py` per the file
constraint — another agent's concurrent changes to `scripts/silver_player_transformation.py`
and new `data/silver/...` parquet files were left untouched.
