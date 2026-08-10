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
  rest").
- `data/silver/graph_features/` — audit finding #3, needs PBP bronze, explicitly out of scope.
- The 2025 Bronze `players/weekly` schema difference (145 cols incl. defense, vs. 53
  offense-only in prior seasons) — noted here as a new observation, not investigated further.
