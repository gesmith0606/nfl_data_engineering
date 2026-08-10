# Silver Regen Report — `data/silver/players/{usage,advanced}` — 2026-08-09

Closes the #1 open follow-up from `.planning/DATA_COMPLETENESS_AUDIT.md`: `players/usage`
and `players/advanced` didn't exist locally (only `historical/` did), so
`assemble_player_features()` — the input to every trained model's feature vector — returned
empty for every season. Bronze is complete 2016-2025 (per that audit's fixes), so this was
purely a "run the transformation" gap, not an ingest gap.

## What each script writes (confirmed by reading source, not assumed)

| Script | Reads (Bronze) | Writes (Silver) | Bronze status locally |
|---|---|---|---|
| `scripts/silver_player_transformation.py` | `players/weekly`, `schedules`, `players/snaps` | `players/usage/season=Y/`, `defense/positional/season=Y/` (opp rankings) | complete 2016-2025 |
| `scripts/silver_player_quality_transformation.py` | `players/weekly`, `depth_charts`, `players/injuries` | `teams/player_quality/season=Y/` | complete 2016-2025 |
| `scripts/silver_advanced_transformation.py` | `players/weekly` (roster base) + `ngs/{receiving,passing,rushing}`, `pfr/weekly/{pass,def}`, `qbr` | `players/advanced/season=Y/` | roster base present; **ngs/, qbr/ absent entirely; pfr/ has only `seasonal/def` (not `weekly/pass` or `weekly/def`)** |

`teams/player_quality/` already existed locally (undated April run) — the audit didn't flag it
as missing, this task just refreshed it to confirm current-run correctness. There is no
separate `players/quality/` path anywhere in `src/config.py` (`SILVER_PLAYER_LOCAL_DIRS` has
only `usage`/`advanced`/`historical`) — the "quality" transformation's output lives under
`teams/player_quality/`, already allowlisted in `.gitignore`.

## NGS/PFR/QBR bronze: confirmed absent, ran anyway — documented-graceful, not silent

`data/bronze/ngs/` and `data/bronze/qbr/` don't exist at all. `data/bronze/pfr/` has only
`seasonal/def` — not the `weekly/pass` or `weekly/def` subpaths the advanced script reads.
Ran `silver_advanced_transformation.py` regardless per the task's "run what's runnable"
instruction: it completed successfully for all 10 seasons, logging one `WARNING` per missing
source (`No NGS receiving/passing/rushing data found`, `No PFR pass/def data`, `No QBR weekly
data`) and asserting row-count preservation (`log_nan_coverage` + an explicit
`assert len(master) == master_rows`). Because every source was 100% absent, the merge
functions short-circuit and add **zero** `ngs_`/`pfr_`/`qbr_` columns (not NaN-filled columns —
literally no columns), so each season's `players/advanced/season=Y/` file has only the 7
join-key columns (`player_gsis_id`, `player_display_name`, `position`, `recent_team`, `season`,
`week`, `player_display_name_norm`). This is the documented-graceful degradation path the
script was built for — it did not silently fail or partially corrupt data.

## Runs executed (all local, `--no-s3`, foreground, well under 10 min each)

1. `silver_player_transformation.py --seasons 2016..2025 --no-s3` — 3.5s/season, ~38s total.
2. `silver_player_quality_transformation.py --seasons 2016..2025` — ~4s total.
3. `silver_advanced_transformation.py --seasons 2016..2025 --no-s3` — <1s total.

## Bug found and fixed during verification: `snap_pct` was 100% NaN in every season, forever

Step-3 verification ("no all-NaN key columns") caught a real, pre-existing bug — not
introduced by this task, just never visible before because `players/usage/` didn't exist to
inspect. `_prepare_snap_data()` in `scripts/silver_player_transformation.py` built its
name→`player_id` lookup from Bronze weekly's `player_name` column, which is **abbreviated**
("A.Rodgers", "T.Brady" — true for every season, 2016-2025). Bronze snap counts' `player`
column holds **full display names** ("Cooper Kupp"). The join therefore matched 0% of rows in
every season that has ever gone through this script — `snap_pct` has always been entirely NaN
in Silver `players/usage`.

For 2016-2024 this only meant a silently-empty `snap_pct` column (no row-count symptom, because
Bronze weekly has 0 null `player_id` rows in those seasons — a 0%-match left-join just leaves
NaN, no fan-out). For season 2025 specifically, Bronze weekly's newer/wider schema (145 cols
vs. 53 for prior seasons, includes defensive players) has 22 trailer rows with null
`player_id`/`position`. Pandas `merge()` treats `NaN == NaN` as a match, so those 22 rows
cross-joined against **every** one of the 26,612 unmatched (all-NaN) snap rows for that season,
inflating `players/usage/season=2025` from a plausible ~19.4K rows to a garbage 46,011 rows —
caught by the row-count plausibility check in step 3, not silently passed.

**Fix applied** (`scripts/silver_player_transformation.py::_prepare_snap_data`): join on
`player_display_name` instead of `player_name`, and drop unmatched snap rows before returning
(defensive — prevents the NaN-cross-join fan-out even if a future season reintroduces null
`player_id` rows). Re-ran step 1 after the fix.

| | Before fix | After fix |
|---|---|---|
| `snap_pct` non-null (all seasons) | 0% | 93.2%-98.2% |
| `players/usage/season=2025` rows | 46,011 (corrupt) | 19,512 (plausible) |
| `assemble_player_features(2024)` eligibility filter | fell back to "position only" (warned: `snap_pct_roll3 unavailable`) | real `snap_pct_roll3 >= 0.20` filter active (D-01/D-02 rule) |

Deleted the 10 pre-fix `players/usage/season=*/usage_20260809_220613.parquet` (and the one
`_220605` test file) plus 10 duplicate `defense/positional/.../opp_rankings_20260809_220613.parquet`
side-outputs from the same buggy run, so only the corrected timestamped files remain on disk.

Test coverage: no test exercises `_prepare_snap_data` directly (script-local helper), so this
was a genuine blind spot closed by this task, not a regression against an existing test.

## Coverage table (post-fix, all 10 seasons)

| Season | `players/usage` rows | `snap_pct` non-null | `players/advanced` rows | advanced feature cols |
|---|---|---|---|---|
| 2016 | 5,330 | 97.8% | 5,274 | 0 (NaN-degraded, as documented above) |
| 2017 | 5,359 | 98.2% | 5,319 | 0 |
| 2018 | 5,302 | 98.2% | 5,281 | 0 |
| 2019 | 5,279 | 96.1% | 5,261 | 0 |
| 2020 | 5,466 | 95.5% | 5,447 | 0 |
| 2021 | 5,709 | 96.5% | 5,698 | 0 |
| 2022 | 5,651 | 96.0% | 5,631 | 0 |
| 2023 | 5,654 | 96.2% | 5,653 | 0 |
| 2024 | 5,599 | 95.5% | 5,597 | 0 |
| 2025 | 19,512 | 93.2% | 19,421 | 0 |

All 10 `players/usage` files: 111 real feature columns (targets, carries, EPA, shares, rolling
avgs, etc.), zero nulls in key columns (`player_id`, `recent_team`, `position`, `week`,
`season`). Note 2025's Bronze weekly uses a materially different/wider schema (145 cols,
includes defense/special-teams players nflverse now returns) than 2016-2024 (53 cols,
offense-only) — out of scope to reconcile here, flagged for awareness; it doesn't corrupt
`players/usage` (defensive rows just carry NaN offensive stats and get filtered out downstream
by position) but is worth a follow-up look if 2025 numbers ever look off elsewhere.

`teams/player_quality/season=Y/`: all 10 seasons re-ran clean, 534-570 rows/season, 28 columns,
matches the pre-existing (already-committed-shippable) output shape.

## Consumer proof: `assemble_player_features()` — the actual downstream reader

**Before**: by construction, guaranteed empty. `_read_latest_local(SILVER_PLAYER_LOCAL_DIRS["usage"], season)`
globs a directory that didn't exist → returns an empty DataFrame → `assemble_player_features`
hits `if base.empty: return pd.DataFrame()` on its very first line. This isn't inferred, it's
the literal code path (confirmed by reading `src/player_feature_engineering.py:1690-1693`)
that was live in this environment before this task ran.

**After** (ran live, post-fix):

| Season | Rows | Columns | `snap_pct` non-null |
|---|---|---|---|
| 2020 | 3,822 | 452 | 3,822 (100%) |
| 2024 | 3,989 | 452 | 3,989 (100%) |
| 2025 | 4,085 | 547 | 4,082 (99.9%) |

Real player-week feature vectors with real snap-share-based eligibility filtering, where
before there was nothing. (2025 has more columns because its wider Bronze schema adds extra
raw stat columns that flow through un-pruned — consistent with the schema note above, not a bug
in the feature assembly itself.)

## Test suites run

```
pytest tests/test_player_analytics.py tests/test_player_advanced_analytics.py \
       tests/test_player_quality.py tests/test_feature_engineering.py \
       tests/test_player_feature_engineering.py -q
```
115 passed, both before and after the `_prepare_snap_data` fix (~43s each run). No other test
file references `players/usage`, `players/advanced`, or `SILVER_PLAYER_LOCAL_DIRS`, so this is
the full affected set.

## Sizes

| Path | Size | Files |
|---|---|---|
| `data/silver/players/usage/` | 9.2 MB | 10 (one per season, post-cleanup) |
| `data/silver/players/advanced/` | 516 KB | 10 |
| `data/silver/teams/player_quality/` | 1.9 MB | 21 (10 pre-existing + refreshed history) |
| `data/silver/` (total, all paths) | 34 MB | — |

## Commit recommendation

**Do not commit yet without a decision** — flagging for the coordinator, matching the audit's
own framing (prod HF Spaces deploy is `git clone`-based, so "committed" == "shipped", per
`deploy/huggingface/Dockerfile` / TD-08/09/10 in `CLAUDE.md`).

- `data/silver/players/usage/**/*.parquet` and `data/silver/players/advanced/**/*.parquet` have
  **no `.gitignore` allowlist today** — they fall under the default `*.parquet` deny (line 209).
  `data/silver/players/historical/` already has one; `usage`/`advanced` do not.
- If the intent is for `assemble_player_features()` to work in prod the same way it now works
  locally (this task's whole point), the TD-08/09/10 pattern applies: add
  ```
  !data/silver/players/usage/
  !data/silver/players/usage/**
  !data/silver/players/usage/**/*.parquet
  !data/silver/players/advanced/
  !data/silver/players/advanced/**
  !data/silver/players/advanced/**/*.parquet
  ```
  and commit ~9.7 MB (usage + advanced combined) — well under the 50 MB precedent this repo has
  used for prior Bronze/Silver allowlist additions.
  - Caveat: since NGS/PFR-weekly/QBR bronze is absent, `players/advanced` currently ships with
    **zero** advanced feature columns — shipping it now means prod gets the same join-key-only
    file, no worse than today (empty), strictly better than "doesn't exist" once code starts
    reading it, but it's not yet delivering its real value (that needs a separate NGS/PFR/QBR
    ingest task).
  - `teams/player_quality` is already allowlisted (`!data/silver/teams/**/*.parquet`); the
    refreshed files here need no gitignore change, only a commit if the coordinator wants the
    refreshed content shipped.
- Recommend: allowlist + commit `players/usage` now (it's the one that actually unblocks
  `assemble_player_features` in prod and just had a real correctness bug fixed). Hold
  `players/advanced` for a follow-up commit alongside whichever future task ingests NGS/PFR-weekly/QBR,
  so the commit message can honestly say what it contains — shipping an all-join-key-columns file
  today isn't harmful but also isn't the audit's actual ask.

## Summary of what's still deferred (unchanged from the audit, confirmed still true)

- NGS/PFR-weekly/QBR bronze ingestion — needed for `players/advanced` to carry real features,
  not just join keys. Not attempted here (task scope was "run what's runnable, document the
  rest"). **Closed 2026-08-10, see below.**
- `data/silver/graph_features/` — audit finding #3, needs PBP bronze, explicitly out of scope.
- The 2025 Bronze `players/weekly` schema difference (145 cols incl. defense, vs. 53
  offense-only in prior seasons) — noted here as a new observation, not investigated further.

---

# 2026-08-10 — NGS/PFR-weekly/QBR bronze ingested, `players/advanced` now has real features

Closes the deferred item above and `DATA_COMPLETENESS_AUDIT.md` finding #6. Bronze `ngs/`,
`qbr/` were entirely absent locally and `pfr/` only had `seasonal/def`; as a result every
`players/advanced/season=Y/` file had 0 `ngs_`/`pfr_`/`qbr_` columns (join keys only) and the
`--ml` full-feature path NaN-imputed every advanced feature. This task ingested all three
Bronze types via `scripts/bronze_ingestion_simple.py`, re-ran
`scripts/silver_advanced_transformation.py`, and verified the actual downstream consumer
(`assemble_player_features()`).

## Bronze ingestion — per-season row counts (registry names: `ngs`, `pfr_weekly`, `qbr --frequency weekly`)

**NGS** (`--data-type ngs --seasons 2016-2025`, valid range 2016+): all 10 seasons × all 3
sub-types succeeded, 30/30, exit 0.

| Season | passing | rushing | receiving |
|---|---|---|---|
| 2016 | 573 | 579 | 1,601 |
| 2017 | 575 | 595 | 1,422 |
| 2018 | 578 | 594 | 1,419 |
| 2019 | 576 | 588 | 1,418 |
| 2020 | 581 | 596 | 1,520 |
| 2021 | 608 | 618 | 1,575 |
| 2022 | 603 | 617 | 1,466 |
| 2023 | 620 | 623 | 1,473 |
| 2024 | 614 | 601 | 1,435 |
| 2025 | 605 | 648 | 1,402 |

**PFR weekly** (`--data-type pfr_weekly --seasons 2018-2025`, valid range starts 2018 —
`validate_season_for_type` hard-rejects 2016-2017 upfront, so those two seasons were not
requested at all rather than requested-and-failing): all 8 seasons × all 4 sub-types
succeeded, 32/32, exit 0. **2016-2017 have no PFR-weekly data upstream by design, not a bug.**

| Season | pass | rush | rec | def |
|---|---|---|---|---|
| 2018 | 646 | 2,189 | 4,292 | 7,277 |
| 2019 | 640 | 2,148 | 4,269 | 7,285 |
| 2020 | 666 | 2,266 | 4,428 | 7,643 |
| 2021 | 706 | 2,375 | 4,608 | 8,442 |
| 2022 | 685 | 2,389 | 4,547 | 7,878 |
| 2023 | 700 | 2,380 | 4,594 | 7,902 |
| 2024 | 697 | 2,359 | 4,453 | 7,992 |
| 2025 | 684 | 2,355 | 4,533 | 7,926 |

**QBR** (`--data-type qbr --frequency weekly --seasons 2016-2025`): 8/10 seasons ingested,
**2024 and 2025 skipped — 0 rows returned upstream** (`nfl.import_qbr` returned empty for
both). This matches the task brief's documented caveat ("QBR 2024+ may be absent upstream,
fail-open"); confirmed by a real ingest attempt against the live source, not assumed. Because
2 of 10 season/variant combinations were empty but the other 8 succeeded, the script's exit-code
contract (fail only on a *total* no-op) correctly returned **exit 0** — this is the "upstream
has no data" case, not "broken."

| Season | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|
| Rows | 529 | 531 | 531 | 525 | 543 | 567 | 561 | 573 | **0 (skip)** | **0 (skip)** |

## Sizes before allowlist decision (step 2 gate: skip allowlisting anything over 50 MB)

| Bronze path | Size |
|---|---|
| `data/bronze/ngs/` | 2.8 MB |
| `data/bronze/pfr/weekly/` | 2.4 MB |
| `data/bronze/qbr/` | 332 KB |
| **Total new Bronze** | **~5.5 MB** |

All three are far under the 50 MB cap — all allowlisted (see below).

## Silver `players/advanced` regen — `scripts/silver_advanced_transformation.py --seasons 2016..2025 --no-s3`

All 10 seasons processed, exit 0, row counts unchanged from the 2026-08-09 run (row-count
preservation asserted internally — this transform only adds columns, never drops/fans-out
rows). Advanced feature-column count **went from 0 in every season to real merged columns**:

| Season | Rows | Advanced cols (was 0) | NGS any-nonNaN | PFR-offense any-nonNaN | PFR-def any-nonNaN | QBR any-nonNaN |
|---|---|---|---|---|---|---|
| 2016 | 5,274 | 88 | 47.7% | n/a (pre-2018) | n/a (pre-2018) | 9.0% |
| 2017 | 5,319 | 88 | 44.5% | n/a (pre-2018) | n/a (pre-2018) | 9.0% |
| 2018 | 5,281 | 128 | 44.7% | 11.8% | 96.9% | 9.2% |
| 2019 | 5,261 | 128 | 44.9% | 11.4% | 96.8% | 9.2% |
| 2020 | 5,447 | 128 | 45.2% | 11.9% | 100.0% | 9.2% |
| 2021 | 5,698 | 128 | 45.2% | 12.3% | 100.0% | 9.5% |
| 2022 | 5,631 | 128 | 43.8% | 12.1% | 100.0% | 9.3% |
| 2023 | 5,653 | 128 | 44.2% | 12.0% | 99.3% | 9.5% |
| 2024 | 5,597 | 112 | 43.3% | 12.2% | 99.3% | n/a (upstream absent) |
| 2025 | 19,421 | 112 | 12.5% | 3.4% | 99.5% | n/a (upstream absent) |

"Any-nonNaN" = share of player-week rows with at least one non-null value across that
source's columns (each source only applies to a subset of positions/plays — QBR is QB-only,
NGS passing/rushing/receiving each apply to different position groups, PFR-offense pressure
is QB-only, PFR-def blitz rate is team-level so it applies to nearly every roster row). 2025's
lower percentages are the already-documented 2025 Bronze `players/weekly` schema difference
(145 cols incl. defense/special-teams players vs. 53 offense-only in prior seasons) diluting
the denominator — not a regression in this task's ingest.

Column count breakdown: 88 = 2016-2017 (NGS 3 sources + QBR, no PFR since PFR-weekly starts
2018); 128 = 2018-2023 (NGS + PFR-offense + PFR-def + QBR, full coverage); 112 = 2024-2025
(NGS + PFR-offense + PFR-def, no QBR since it's absent upstream for those seasons).

**Silver size**: `data/silver/players/advanced/` = 6.8 MB (10 files, one per season, after
deleting the 10 stale 2026-08-09 join-keys-only files that were still sitting alongside the
new ones — same cleanup pattern as the prior `players/usage` fix in this report).

## Full-feature consumer proof — `assemble_player_features()`

Before this task (per the 2026-08-09 section above): `players/advanced` had 0 `ngs_`/`pfr_`/
`qbr_` columns in every season, so every advanced feature in the assembled feature vector was
NaN — **0% non-NaN advanced-feature coverage**, unconditionally, regardless of which season.

After (ran live, `src/player_feature_engineering.py::assemble_player_features`):

| Season | Rows | Total cols | Advanced cols | Rows with ≥1 non-NaN advanced feature | Mean per-column non-NaN rate |
|---|---|---|---|---|---|
| 2020 | 3,822 | 580 | 131 | 100.0% | 26.1% |
| 2024 | 3,989 | 564 | 115 | 99.9% | 27.7% |
| 2025 | 4,085 | 659 | 115 | 100.0% | 27.1% |

"Mean per-column non-NaN rate" is lower than "rows with ≥1 non-NaN" for the same reason as the
Silver table above — each advanced source is position/context-specific, so no single column is
expected to be near-100% on its own; what matters is that virtually every eligible player-week
now carries *some* real advanced signal, versus strictly zero before.

## `check_data_completeness.py` manifest update (step 5)

Added four **WARN**-tier, `committed=True` entries (not FAIL — see inline comments in the
script for why): `bronze_ngs` (coarse: ≥3 files anywhere under `data/bronze/ngs/`),
`bronze_pfr_weekly` (coarse: ≥4 files anywhere under `data/bronze/pfr/weekly/`, static glob
since PFR-weekly's season dir is nested under each pass/rush/rec/def sub-type dir and the
checker doesn't support per-season `{season}` substitution inside `glob`, only inside
`path_template`), `bronze_qbr` (per-season, 2016-2023 only — 2024-2025 deliberately excluded
from the manifest since they're a confirmed real upstream gap, not a bug; including them would
make the check permanently WARN-red for a condition nothing here can fix), and
`silver_players_advanced` (per-season, all of `PLAYER_SEASONS` 2016-2025). WARN tier because a
season with roster data but no NGS/PFR/QBR upstream still legitimately produces a join-keys-only
`players/advanced` file (the documented degrade path in `silver_advanced_transformation.py`) —
that's graceful, not a failure.

`--local`: **108/108 PASS** (up from 88/88 pre-task — 20 new checks, all passing).
`--ci`: **108/108 PASS** (all four new entries are `committed=True` since all four paths are
allowlisted below and well under size caps).

## `.gitignore` allowlist additions (TD-08/09/10 pattern, step 6)

All four new/changed paths are small and genuinely consumed (Silver reads Bronze `ngs`/
`pfr/weekly`/`qbr` directly; `assemble_player_features()` reads Silver `players/advanced`
directly) — allowlisted per precedent:

```
!data/bronze/ngs/**/*.parquet          # 2.8 MB
!data/bronze/pfr/weekly/**/*.parquet   # 2.4 MB
!data/bronze/qbr/**/*.parquet          # 332 KB
!data/silver/players/advanced/**/*.parquet   # 6.8 MB
```

Total newly-shippable data this task: **~12.3 MB**, well under the 50 MB precedent cap. All
four paths are staged (`git add`), not committed, per this task's instructions.

## Tests run

```
pytest tests/test_player_analytics.py tests/test_player_advanced_analytics.py \
       tests/test_player_quality.py tests/test_feature_engineering.py \
       tests/test_player_feature_engineering.py tests/test_check_data_completeness.py \
       tests/test_bronze_exit_code.py tests/test_silver_exit_codes.py -q
```
**156 passed.** `scripts/check_data_completeness.py --local` and `--ci`: both 108/108 PASS.

## What's still deferred (unchanged)

- `data/silver/graph_features/` — audit finding #3, needs PBP bronze (100-400 MB/season),
  explicitly out of scope for "cheap" ingestion.
- QBR 2024-2025 weekly data — confirmed absent upstream (ESPN side), not something a re-ingest
  can fix. Revisit only if/when ESPN resumes publishing it.
- PFR-weekly 2016-2017 — out of `nfl-data-py`'s supported range for that data type (starts
  2018), same as above: not a local gap, an upstream one.
- The 2025 `players/weekly` wide-schema note from the 2026-08-09 section remains unresolved
  and continues to dilute 2025's advanced-feature coverage percentages (documented above, not
  a new issue introduced by this task).
