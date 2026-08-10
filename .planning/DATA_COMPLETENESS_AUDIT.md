# Data Completeness Audit — 2026-08-09

Systematic sweep of every `data/{bronze,silver,gold,ops,external,adp}` path read by
`src/`, `scripts/`, and `web/`, prompted by three silent holes found by accident on
2026-08-08 (missing bronze 2021 players/weekly, missing players/snaps entirely — the
shipped `RB_SNAP_COLLAPSE` correction was a no-op in every backtest ever run — and
missing players/injuries). Pattern per TD-08/09/10 (repo `CLAUDE.md`) and
`knowledge-vault/concepts/gated-experiment-coverage-check.md`: `data/` is gitignored
by default with a deny-then-allowlist `.gitignore` section, and most readers are
"local-first" with try/except or empty-DataFrame fallbacks that degrade **silently**
when a path is absent — no crash, just quietly wrong or empty output.

Method: 3 parallel research agents covered `src/` (46 files), `scripts/` (50 files),
and `web/` (request-time readers), cross-checked against `.gitignore`, `web/Dockerfile`,
and `deploy/huggingface/Dockerfile` (the actual prod deploy — it `git clone`s the repo,
so "committed" == "shipped", full stop). Findings below are ranked; fixes applied are
marked **FIXED**, everything else is **DEFERRED** (reported, not touched).

## What "prod" means here

- `deploy/huggingface/Dockerfile` (live backend, `gesmith0606-nfl-data-api.hf.space`)
  clones the public GitHub repo at build time. Any Bronze/Silver/Gold path without a
  `.gitignore` `!data/...` allowlist is silently absent in this deploy, even if it
  works perfectly on the local dev machine.
- `web/Dockerfile` (Railway, selective `COPY`) is confirmed **dead** since the May
  2026 trial expiry — findings note it for completeness but don't weight it.

## Findings, ranked by impact

### 1. SILENT-HOLE (FIXED) — RB_SNAP_COLLAPSE / WR route-slope no-op is live in production, not just backtests

`scripts/generate_projections.py` (the live weekly projection generator, not just
`backtest_projections.py`) globs `data/bronze/players/snaps/season={s}/week=*/*.parquet`
and `data/bronze/players/injuries/season={s}/*.parquet` for the current + prior season.
On an empty glob it prints a WARN and continues with `snap_counts_df=None` /
`injuries` empty — no error, no CI signal. Before this audit, snaps/injuries only
covered `season=2022,2023,2024`; both **2021** (prior-season trailing window) and
**2025** (current season for 2026 trailing-window lookups) were missing, meaning the
correction was silently off for early-2026 production runs too.

Same pattern independently confirmed in `src/rb_role_signals.py:build_rb_role_signals`
— it only guards on `depth_charts.empty`; missing `injuries`/`snaps` fall through to
all-zero/NaN neutral signals instead of failing. This is the exact mechanism of the
originally-reported RB_SNAP_COLLAPSE no-op.

**Fixed**: ingested full `players/weekly` (2016-2020 gap), `players/snaps` (2016-2021 +
2025 gap), `players/injuries` (2016-2021 + 2025 gap) — now complete 2016-2025 per
`PLAYER_DATA_SEASONS`. Sizes: weekly +1.3 MB, snaps +7 MB, injuries +1 MB. All three
paths were already `.gitignore`-allowlisted (TD-08/09/10), so no gitignore change
needed — just the missing ingest.

**Still open** (not fixed, out of "cheap ingest" scope): `rb_role_signals.py` and
`generate_projections.py` still don't hard-fail or loudly flag when snaps/injuries are
empty for a season in scope — a *future* re-introduction of this exact hole (e.g. next
season's data lagging) would again degrade silently. Recommend a loud check (row-count
assertion or CI gate) rather than warn-and-continue, as a follow-up.

### 2. SILENT-HOLE (found, NOT fixed — path bug, code fix applied) — `lineup_builder.py` reads a path that has never existed

`src/lineup_builder.py:_load_snap_counts` (line 260, pre-fix) read
`data/bronze/snap_counts/season={s}/week={w}/` — a path that doesn't exist under that
name anywhere, dev or prod. Every other reader (`PLAYER_S3_KEYS["snap_counts"]` in
`src/config.py`, `team_roster_service.py`) correctly uses `data/bronze/players/snaps/`.
This made `/api/lineups` snap-pct starter-confidence enrichment a guaranteed silent
no-op (empty DataFrame, `logger.debug` only) regardless of the snaps backfill above.

**Fixed**: corrected the path in `src/lineup_builder.py` to
`data/bronze/players/snaps/...` (one-line change + explanatory comment). Verified:
`_load_snap_counts(2024, 5)` now returns 1,310 rows (was 0 before). `tests/test_lineup_builder.py`
(52 tests) still passes — all tests mock `_load_snap_counts` directly, so the internal
path change is invisible to them.

### 3. SILENT-HOLE (DEFERRED — too large for "cheap fix") — `data/silver/graph_features/` doesn't exist at all

The single biggest hole by blast radius. Every graph-feature join in
`src/player_feature_engineering.py` and `src/hybrid_projection.py` — chemistry, red
zone, WR/TE matchup, scheme, familiarity, college networks, game script, route
participation — reads `data/silver/graph_features/season={s}/graph_*_*.parquet`,
finds nothing, and silently degrades to NaN/empty for every season, always. This also
disables WR route-slope collapse in `generate_projections.py`'s production path (same
file as finding #1). No `.gitignore` allowlist exists for this path either.

**Not fixed**: generating it requires `scripts/compute_graph_features.py`, which
depends on `data/bronze/pbp/` (PBP participation columns) — 100-400 MB/season,
explicitly out of scope for this sweep. The Bronze-fallback branches in
`player_feature_engineering.py`'s chemistry/red-zone/scheme joins are *also* dead for
the same reason (`data/bronze/pbp/` is completely absent locally). **Recommended
follow-up**: a dedicated task to ingest 2-3 recent PBP seasons (accepting the 100-400
MB/season cost deliberately) and run `compute_graph_features.py`, then allowlist the
output the same way `data/gold/correlations/` was.

### 4. SILENT-HOLE (DEFERRED — beyond "ingest bronze" scope) — `data/silver/players/{usage,advanced}/` don't exist at all

`SILVER_PLAYER_LOCAL_DIRS` in `src/config.py` defines `usage`, `advanced`, and
`historical` — only `historical` (a static ~1 MB combine/draft dimension table) exists
locally and is committed. `src/player_feature_engineering.py:_read_latest_local`
bases feature assembly on `usage` *first*; with it missing, `assemble_player_features`
returns empty for every season right now in this environment. This is the input to
every trained model's feature vector — plausibly a bigger lever than any of the three
originally-reported holes, since it's not opt-in like RB_SNAP_COLLAPSE, it's the base
feature pipeline.

**Not fixed**: this requires *running* `scripts/silver_player_transformation.py` /
`scripts/silver_advanced_transformation.py` (which itself needs Bronze `ngs`, `pfr`,
`qbr` — also all missing locally, see #6), not just ingesting a small bronze file. The
task scope was "ingest missing bronze," not "run the Silver transformation pipeline" —
doing that safely needs its own verification pass (does the regenerated output match
what the currently-shipped `models/` artifacts were trained on?) that's out of scope
for a same-day sweep. **This is the #1 recommended next investigation** — confirm
whether local `assemble_player_features()` is really returning empty today, and if so
whether that's masked by pre-trained/committed model artifacts (`models/player/*.json`,
`models/ensemble/`) still being used at inference time.

### 5. SILENT-HOLE + PROD-GAP (FIXED) — `data/bronze/{draft_picks,combine}/` were completely absent and unshipped

`src/graph_college_networks.py:_read_bronze_draft_picks` / `_read_bronze_combine` read
these paths with a silent empty-DataFrame fallback (no log). Neither existed at all —
100% dead, so every college-network graph feature (coaching-tree lineage, prospect
comps used by `src/college_prospect_features.py`) was a guaranteed no-op.
`_read_bronze_rosters` in the same file was flagged as reading a non-`players/`-root
`data/bronze/rosters/` path, but it has a working fallback chain to
`data/bronze/players/rosters/` (which is populated) — not actually dead, downgraded
from the initial CRITICAL flag.

**Fixed**: ingested `draft_picks` and `combine` bronze for 2016-2025 (404 KB + 320 KB
= 724 KB total) and added `.gitignore` allowlist entries (TD-08/09/10 pattern).

### 6. MEDIUM (DEFERRED, report only) — `ngs`, `pfr/weekly/*`, `qbr`, `officials`, `teams`, all college bronze types missing

`data/bronze/{ngs,pfr/weekly,qbr,officials,teams}/` and all four
`BRONZE_COLLEGE_LOCAL_DIRS` paths (college player stats/usage/teams/draft picks) don't
exist locally. Silver transformation scripts (`silver_player_transformation.py`,
`silver_advanced_transformation.py`, `silver_historical_transformation.py`) have a
local-empty → live-network-fetch fallback (`fetcher.fetch_X()`), so this is not a pure
silent no-op — it's a fragile "try the network every single run" pattern, which is its
own risk class (works today, breaks the moment the network call fails/rate-limits,
degrading to warn+continue either way). `teams` bronze specifically has **no reader at
all** found anywhere in `src/` — ingesting it would fix nothing currently broken, so
it was skipped. The others were skipped because ingesting bronze alone doesn't unblock
anything without also re-running the Silver transformation (see #4) — would be wasted
effort without that follow-up.

### 7. PROD-GAP (FIXED) — `data/adp/` and `data/ops/llm_costs/` had no `.gitignore` allowlist

- `web/api/routers/draft.py:get_adp` / `_load_adp_df` read
  `data/adp/adp_{source}_{scoring}.csv` (ffc/espn/sleeper) — only `data/adp_latest.csv`
  was allowlisted. Not silent-null (both call sites fall back gracefully to
  `adp_latest.csv`), but per-source ADP (`?source=ffc`) silently served the generic
  consensus file in prod with no error surfaced. **Fixed**: allowlisted
  `data/adp/**/*.csv` (~276 KB).
- `src/sentiment/processing/cost_log.py:running_total_usd` reads
  `data/ops/llm_costs/season={s}/week={w:02d}/*.parquet` for weekly Claude Haiku
  extraction budget tracking — only the top-level `data/ops/` dir + the single
  `pipeline_status.json` file were allowlisted, not these records. Every fresh
  checkout/deploy silently reset the running total to $0 (fail-open, no error)
  instead of accumulating across runs, which defeats the point of a *running* budget
  guard if the workflow that reads it runs from a fresh checkout. **Fixed**:
  allowlisted `data/ops/llm_costs/**/*.parquet` (~752 KB).

### 8. LOW/INFORMATIONAL (report only, no action)

- `data/bronze/odds_api/snapshots/` only has `season=2026` locally — any historical
  CLV read via `src/odds_snapshot_loader.py` for 2016-2025 is silently empty. Not
  fixable via backfill-ingestion the way weekly/snaps/injuries are — it's a live
  2×/daily snapshot capture mechanism (Phase 1.4), no historical archive exists to
  import. Report only.
- `src/graph_correlation.py:build_correlation_data` drops any season missing from
  `players/weekly` out of its 2016-2025 training loop with zero logging (only warns if
  the *entire* pool is empty). This is now moot as a live issue — the 2016-2020
  `players/weekly` gap that fed it is closed by fix #1 above — but the silent-drop
  code pattern itself remains and would re-hide a future gap without any signal.
- `src/sentiment/processing/pipeline.py:_roster_provider_factory._load` reads
  `data/bronze/players/rosters/season={current_calendar_year}/` — hardcoded to the
  *current* calendar year, not the `season` argument passed in. A logic bug, not a
  data-path hole; backfill sentiment runs for past seasons load the wrong-season
  roster hints. Flagged for a follow-up code fix, not touched here (out of the
  ingest/gitignore scope for this sweep).
- `web/Dockerfile` (Railway, confirmed dead) never mirrored the TD-10 fix or the
  snaps/external_projections/adp COPY lines that the HF clone-based deploy gets via
  git. Purely informational since Railway isn't live.
- `data/bronze/pbp/` is completely absent locally and not `.gitignore`-allowlisted —
  expected and correct: PBP is 100-400 MB/season, explicitly out of scope for "cheap"
  ingestion per this task's instructions. Kills `src/ftn_features.py` and
  `src/graph_scheme.py` entirely (both need it with no fallback) in addition to
  feeding finding #3/#4's Bronze-fallback branches. No allowlist should be added
  unless/until a deliberate decision is made to commit PBP seasons (large repo-size
  tradeoff).

## What was fixed (summary)

| Path | Action | Size |
|---|---|---|
| `data/bronze/players/weekly/` | ingested 2016-2020 (closes gap to full 2016-2025) | +1.3 MB |
| `data/bronze/players/snaps/` | ingested 2016-2021 + 2025 (closes gap to full 2016-2025) | +7 MB |
| `data/bronze/players/injuries/` | ingested 2016-2021 + 2025 (closes gap to full 2016-2025) | +1 MB |
| `data/bronze/draft_picks/` | ingested 2016-2025 (was entirely absent) + `.gitignore` allowlist | 404 KB |
| `data/bronze/combine/` | ingested 2016-2025 (was entirely absent) + `.gitignore` allowlist | 320 KB |
| `data/adp/` | `.gitignore` allowlist added (data already existed locally, wasn't shippable) | 276 KB |
| `data/ops/llm_costs/` | `.gitignore` allowlist added (data already existed locally, wasn't shippable) | 752 KB |
| `src/lineup_builder.py` | one-line path fix: `data/bronze/snap_counts/` → `data/bronze/players/snaps/` | code |

Total new/newly-shippable data: ~11 MB, well under the 50 MB cap. All changes are
staged/unstaged — no commits made.

## Deferred (needs a dedicated follow-up, not "cheap")

1. **Highest priority**: verify whether `data/silver/players/usage/` and `advanced/`
   being absent actually means `assemble_player_features()` returns empty right now,
   and whether that's masked by already-trained model artifacts still in `models/`.
2. Ingest 2-3 recent PBP seasons deliberately (100-400 MB/season, real repo-size
   decision) + run `compute_graph_features.py` to close `data/silver/graph_features/`
   — the single biggest silent hole by blast radius (#3).
3. Fix `_roster_provider_factory._load`'s current-calendar-year hardcoding
   (sentiment pipeline logic bug, `src/sentiment/processing/pipeline.py`).
4. Add a loud (non-silent) check to `rb_role_signals.py` / `generate_projections.py`
   when snaps/injuries are empty for an in-scope season, so this exact class of bug
   can't silently recur.

## Prevention wired (2026-08-09)

Item 4 above is done, generalized: `scripts/check_data_completeness.py` is a
declarative data-existence invariant gate covering every committed-and-required
path this audit mapped — Bronze `players/{weekly,snaps,injuries}`,
`depth_charts`, `players/rosters`, `schedules`, `draft_picks`, `combine`; Gold
`projections/preseason` (current season) and the dynamically-resolved latest
weekly `projections` partition; and WARN-tier `data/adp/`, `data/external/`
rankings, and `gold/sentiment/`. Season/week expectations come straight from
`config.PLAYER_DATA_SEASONS` and the audit findings above — nothing invented.

- **Manifest** (`REQUIREMENTS` in the script): each entry declares an id, a
  tier (`FAIL` blocks, `WARN` reports only), a `committed` flag, the seasons
  to check, and a minimum file count (plus an optional row floor for the
  three paths behind the original RB_SNAP_COLLAPSE no-op, so a
  written-but-empty file fails the same way an absent one does).
- **Two modes**: `--local` checks the full manifest (dev machines); `--ci`
  checks only `committed=True` entries — what a fresh `git clone` gets,
  matching what `deploy/huggingface/Dockerfile`'s clone-based prod deploy
  actually sees. Every current manifest entry happens to be committed (that
  was the point of TD-08/09/10 and this audit), so both modes currently
  agree — the `committed` flag exists so a future local-only/deferred path
  (e.g. `data/silver/graph_features/`, finding #3 above, once that's built)
  can be added to `--local` without breaking `--ci`.
- **Wiring**: `.github/workflows/ci.yml` runs `--ci` unconditionally on every
  PR (fail-closed — a PR that silently drops a committed path fails CI, no
  path filter, since data/ changes aren't covered by the existing
  python-files paths-filter). `.github/workflows/weekly-pipeline.yml` runs
  `--local` post-ingest (fail-open, step 9a) with the same deduped-GitHub-
  issue escalation pattern as the existing `--ml` fallback (step 7): one
  open issue per failure mode, closed manually to re-arm.
- **Current-state result** (2026-08-09, both modes): 88/88 checks PASS. No
  live findings — the audit's own remediation (weekly/snaps/injuries/
  draft_picks/combine backfill, TD-08/09/10 gitignore allowlists) already
  closed every gap this manifest checks for. The manifest deliberately does
  NOT cover findings #3/#4 (`data/silver/graph_features/`,
  `data/silver/players/{usage,advanced}/`) — those are out-of-scope,
  not-yet-built paths per this audit, not committed-and-required ones; adding
  them here would just be a permanently-red check for already-known,
  already-deferred work.
- **Tests**: `tests/test_check_data_completeness.py` (24 tests) — missing
  FAIL-tier season, WARN-tier miss (non-blocking), row-floor catches an
  empty-but-present file, `--ci` skips uncommitted entries, dynamic
  latest-weekly-partition resolution, and end-to-end `main()` exit codes.
