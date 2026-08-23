# `--ecr-anchor` 2026 In-Season Forward Gate (2026-08-21, amended 2026-08-22, amended again 2026-08-22)

## 2026-08-22 amendment #2: Sleeper consensus anchor SHIPPED default for WR — this gate's baseline changed

`--consensus-anchor-src sleeper` (mechanism=blend, weight=0.5, WR-only —
`.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md`) passed its pre-registered gate
decisively and the user approved promotion the same day this doc's first
amendment landed. `scripts/generate_projections.py` (weekly mode) and
`scripts/backtest_projections.py`'s default evaluation path now apply that
lever to WR **by default** (opt out via `--no-sleeper-anchor`) — this is a
DIFFERENT, independent consensus source (Sleeper's own historical weekly
projections) from the one this doc's `--ecr-anchor` lever anchors toward
(FantasyPros weekly ECR), but it changes what "baseline" means for every
comparison this forward gate registers:

- **The shadow-mode baseline in §1 is now the Sleeper-anchored config**,
  not the raw heuristic/ML projection. `generate_projections.py --week N
  --season 2026` (no extra flags) already includes the Sleeper WR blend —
  the §1 "Primary comparison" (`baseline` vs `--ecr-anchor`) is therefore
  now "Sleeper-anchored WR ordering" vs "Sleeper-anchored WR ordering +
  ECR-anchored WR ordering" (both anchors compose additively per their
  code-path ordering — ECR anchor runs first, Sleeper anchor runs second,
  see `generate_projections.py`'s per-week block ordering), not "raw" vs
  "ECR-anchored" as originally registered on 2026-08-21.
- **`--ecr-anchor` remains fully opt-in shadow** — nothing in this
  amendment changes `--ecr-anchor`'s own default (still off) or this gate's
  verdict rules (§2). The only thing that changed is what "off" now means:
  "off" = shipped-default Sleeper anchor only; "on" = shipped-default
  Sleeper anchor + ECR anchor stacked. Anyone running the §1 comparison
  from this point forward should note in their results which baseline
  (pre- or post- Sleeper-anchor-ship) they're comparing against, since the
  two are not the same population/ordering.
- **No interaction/composition gate has been run** for stacking
  `--ecr-anchor` on top of the now-default Sleeper anchor — flagged as an
  explicit open question in
  `.planning/SLEEPER_CONSENSUS_ANCHOR_GATE.md`'s "Recommended follow-up"
  #3 and repeated here: a future dedicated gate should measure whether the
  two anchors' composition helps, hurts, or is neutral relative to either
  one alone, before any recommendation to ship `--ecr-anchor` on top of
  the shipped Sleeper default.
- To reproduce the ORIGINAL (pre-Sleeper-anchor-ship) §1 baseline for an
  apples-to-apples comparison against past forward-gate weeks (if any were
  already collected under the old baseline), pass `--no-sleeper-anchor`
  explicitly.

## 2026-08-22 amendment: live-path completion (blockers #1/#2/#3 below closed)

Three blockers flagged in §0 below at the end of the 2026-08-21 bridge
session are now closed. Summary (full detail inline at each numbered
finding, marked "FIXED 2026-08-22"):

1. **Scoring-label mismatch (§0.2) — FIXED.** `src/ecr_anchor.py`'s
   hardcoded `ECR_SCORING = "ppr"` is now
   `ECR_SCORING_PREFERENCE = ("ppr", "half_ppr")`, a set-membership filter.
   **Historical gating was PPR-only — an archive-only limitation** (the
   DynastyProcess archive never captured a half-PPR weekly page, see
   `FP_ECR_HISTORY_COVERAGE.md`), not a modeling choice; every season
   `<=2024` is 100% `"ppr"` rows, so `isin(("ppr","half_ppr"))` reads
   exactly the same rows the old `== "ppr"` filter did — proven
   byte-identical against the real `data/silver/fp_ecr/season=2024/`
   file in `tests/test_ecr_anchor.py::TestScoringPreferenceRegression`.
   **Live (2026+) is half_ppr** (the daily cron's un-overridden
   `refresh_external_rankings.py` default) — that label is now read
   instead of silently producing zero rows. Verified directly:
   `_load_ecr_season(2026)` returns 5,098 rows (was 0) after re-bridging
   (see §0.4 update below for the harness).
2. **Draft-board vs weekly-ECR gap (§0.1) — TRUE weekly capture added.**
   `refresh_external_rankings.py` gains `fetch_fantasypros_weekly()`,
   hitting FantasyPros' public weekly-position pages
   (`ppr-{rb,wr,te}.php`, `half-point-ppr-{rb,wr,te}.php`, `qb.php`)
   directly and parsing their embedded `var ecrData = {...}` payload — the
   actual weekly per-position product the historical archive was built
   from, not the perpetual overall draft board. **Live finding
   (2026-08-22, preseason, 18 days before 2026-09-09 kickoff): FantasyPros
   is already serving a provisional week=1 WEEKLY board on every
   position/scoring page** (`ranking_type_name: "weekly"`, not `"draft"`),
   89 QB / 152 RB / 238 WR / 125 TE players, 12 contributing experts,
   `last_updated` same-day. No 404s, no draft-board fallback needed at any
   position — the "handle gracefully" preseason-404 contingency plan
   turned out to be unnecessary today, but the fail-open per-position
   handling is still in place for if/when that changes. `bridge_fp_ecr_live
   .py::load_all_captures` now prefers this weekly-position capture over
   the draft board per scrape_date when both exist. Wired into the SAME
   daily cron step (`daily-sentiment.yml` step 5b already runs
   `refresh_external_rankings.py --source all`-equivalent with no
   `--source` flag) via a new `fantasypros_weekly` entry in the default
   source list — no workflow file changes needed. Output is a sibling file
   (`data/external/fantasypros_weekly_rankings.json` + dated archive),
   the existing `fantasypros_rankings.json` schema/path is untouched.
3. **PlayerNameResolver bugs (§0.4) — FIXED.** (a) `_NICKNAME_MAP` entries
   whose mapped value contains punctuation (`"aj brown" -> "a.j. brown"`,
   `"dj moore"`, `"dj chark"`) were dead because `_normalise()` strips
   periods from every index key but the raw mapped value was used as the
   lookup key unnormalised — fixed by re-normalising the mapped value
   before lookup. (b) `_normalise()` stripped periods but not apostrophes,
   so `"Tre' Harris"` failed to match an apostrophe-free roster entry
   `"Tre Harris"` — fixed by stripping both straight (`'`) and curly (`'`)
   apostrophes. Both fixed test-first
   (`tests/test_player_name_resolver.py`); full resolver test suite +
   sentiment-pipeline tests that depend on it (391 tests across
   `test_ecr_anchor.py`, `test_player_name_resolver.py`,
   `test_bridge_fp_ecr_live.py`, `test_external_rankings_archive.py`,
   `test_sentiment_integration.py`, `test_sentiment_processing.py`,
   `test_team_sentiment.py`, `tests/sentiment/`) pass green after the fix.
4. **Re-bridged end-to-end 2026-08-22** with all three fixes live: 45
   capture dates (was 43), 13,012 rows (was 12,126) — the new count
   includes the first true weekly-position capture (2026-08-23 UTC,
   598/604 rows resolved). **WR match rate on the weekly-position capture:
   98.3% (238 WR rows)** — exceeds the pre-registered ≥90% floor
   comfortably and improves on the draft-board-only bridge's previously
   reported 96.3-96.4% (109-111 WR rows/day). Positional coverage is also
   materially better: the weekly WR page alone carries 238 ranked WRs vs.
   ~110 WR rows/day out of the draft board's fixed 300-player overall cap
   — the weekly per-position pages simply rank more players at each
   position than fit in a 300-player cross-position board.
   `build_ecr_lookup()` confirmed returning nonzero 2026 rows via a direct
   module-import harness (season=2026, week=1): `n_ecr_wr_rows=5050`,
   `n_final_matched=200` against a synthetic 200-player WR projection
   pool built from real 2026 roster team assignments (0 Thursday-excluded,
   as expected this far before kickoff).

Pre-registered BEFORE week 1 of the 2026 season and BEFORE any shadow-mode
result exists. This is the "true forward gate" flagged as outstanding in
`.planning/WR_ECR_ORDINAL_GATE.md` constraint #1 and caveat "2026 forward
gate remains the true test": that gate's HOLD verdict (shuffle-test
criterion, despite the primary/guard gates clearing 4.4x) was measured
entirely on 2022-2024 historical data, because the DynastyProcess archive
`--ecr-anchor` reads from (`data/silver/fp_ecr/season={2020..2024}/`) stops
in 2024 with no sealed 2025. This doc registers how that gap gets closed
with real 2026 in-season data, using `scripts/bridge_fp_ecr_live.py` (new,
this session) as the data source.

**Read `scripts/bridge_fp_ecr_live.py`'s module docstring before trusting
anything downstream of it** — it documents several honest, load-bearing
gaps between what this forward gate can actually test and what
`WR_ECR_ORDINAL_GATE.md` originally validated. Summarized in "Known gaps"
below; not repeated in full here.

## 0. Data bridge (built this session)

`scripts/bridge_fp_ecr_live.py` turns our own daily FantasyPros capture
(`data/external/fantasypros_rankings.json` + dated archive under
`data/external/archive/YYYY-MM-DD/`, refreshed by
`scripts/refresh_external_rankings.py` via the `daily-sentiment.yml` cron)
into `data/silver/fp_ecr/season=2026/` rows matching the historical Silver
schema column-for-column (same columns, same order, reusing
`ingest_fp_ecr_history.SILVER_COLUMNS` directly rather than re-declaring
it). Idempotent per capture date (rerunning replaces that date's rows, does
not duplicate). Run against the real archive this session:

- **43 capture dates bridged** (2026-07-09 through 2026-08-21; every
  archived day plus the current live snapshot — one gap, 2026-07-23, where
  the source didn't change that day so no dated snapshot exists, which is
  expected `save_rankings()` behavior, not a bridge bug).
- **12,126 total rows written**, all landing in **season=2026, week=1**
  (see "Preseason week-mapping decision" below).
- **Match rate**: overall 98.2% (282 rows/day), **WR 96.3-96.4%
  (109-111 WR rows/day)** — comfortably clears the pre-registered ≥90% WR
  floor (`scripts/bridge_fp_ecr_live.py::MIN_WR_MATCH_RATE`); the script
  raises `RuntimeError` and refuses to write if any date falls below it.

### Known gaps (read before reading any future forward-gate result)

1. **Source-product mismatch (the big one) — FIXED 2026-08-22, see the
   amendment at the top of this doc.** `refresh_external_rankings
   .py::fetch_fantasypros` always requests FantasyPros' partners
   `consensus-rankings.php` with `week=0&type=draft` — the perpetual
   season-long **redraft/overall consensus board**, with no code path that
   ever switches to a weekly per-position page once the season starts. The
   historical archive this lever was gated against came from FantasyPros'
   *weekly-position* pages (`ppr-wr.php` etc — re-scraped every week,
   reacting to that week's matchups/injuries). Our live bridge substitutes
   a much slower-moving, week-agnostic signal. **This means the forward
   gate below is testing "does anchoring toward FantasyPros' overall draft
   consensus help WR ordering," not the originally-gated "does anchoring
   toward FantasyPros' weekly expert consensus help."** That's a real,
   weaker version of the hypothesis. Any SHIP-recommend verdict from this
   forward gate should be read with that substitution in mind. **UPDATE
   2026-08-22:** a true weekly-position capture
   (`fetch_fantasypros_weekly`) now exists and is preferred by the bridge
   whenever present for a scrape_date — see the amendment at the top of
   this doc for the live finding and match-rate numbers. Dates captured
   before 2026-08-22 remain draft-board-sourced (the substitution above
   still applies to THOSE rows specifically); the historical framing in
   this bullet is left as-written for the record.
2. **Scoring mismatch blocks the wiring today — FIXED 2026-08-22, see the
   amendment at the top of this doc.** Our capture's true scoring
   is `half_ppr` (the daily cron's un-overridden default). `src/ecr_anchor
   .py` hardcodes `ECR_SCORING = "ppr"` in `_load_ecr_season()`. The bridge
   writes the honest `scoring="half_ppr"` label rather than mislabeling
   rows `"ppr"` to force a match. **Net effect: `build_ecr_lookup()` will
   read ZERO rows from this bridge's output today.** Before any shadow-mode
   week-1 run can produce a non-trivial result, one of the following must
   happen (neither is this session's to do — `src/ecr_anchor.py`,
   `scripts/generate_projections.py`, and `scripts/backtest_projections.py`
   are all outside this session's file-ownership boundary):
   - Generalize `src/ecr_anchor.py`'s `ECR_SCORING` constant (and thread a
     matching CLI passthrough in `generate_projections.py`/
     `backtest_projections.py` if the scoring needs to vary by caller), or
   - Add a second daily `--scoring ppr` capture in
     `refresh_external_rankings.py` so a true PPR-labeled live source
     exists (one extra API call, near-zero cost).
   This is flagged loudly rather than silently worked around, per this
   repo's coverage-check discipline
   (`knowledge-vault/concepts/gated-experiment-coverage-check.md`).
3. **`ecr`/`sd`/`best`/`worst` are null for every 2026 row — PARTIALLY
   ADDRESSED 2026-08-22.** Draft-board-sourced rows still have no
   per-expert dispersion and no float consensus average (unchanged, still
   no functional impact on the lever — `ecr_anchor.py` only ever reads
   `pos_rank`). Weekly-position-sourced rows (2026-08-22+) DO carry real
   `ecr`/`sd`/`best`/`worst` values now, since FantasyPros publishes them
   directly on the weekly pages — see the amendment at the top of this
   doc. A row's `ecr` nullness is therefore also the per-row provenance
   label distinguishing which source fed it (no schema change was made to
   carry this — see `bridge_fp_ecr_live.py`'s docstring finding #3b).
4. **No `fantasypros_id` — PARTIALLY ADDRESSED 2026-08-22.** Draft-board
   rows still carry no FantasyPros numeric id; weekly-position rows now
   do (also published directly on the weekly pages), though nothing
   downstream joins on it yet (id resolution for both source kinds still
   goes through `PlayerNameResolver`, fuzzy name match — there's still no
   local DynastyProcess-style id crosswalk to join against). Two
   pre-existing bugs in `src/player_name_resolver.py` were found while
   diagnosing the ~3.6% WR non-match rate and are now **FIXED (2026-08-22)**:
   - `_NICKNAME_MAP` has three dead/harmful entries (`"aj brown"`,
     `"dj moore"`, `"dj chark"`) that map a dot-stripped normalized key
     back to a **dotted** string (`"a.j. brown"` etc). Since `_normalise()`
     strips periods from every name (including when the lookup index
     itself was built), the dotted remapped string can never match any
     index key — these three entries actively broke resolution for exactly
     the players they were meant to help. Fixed by re-normalising the
     mapped value before using it as a lookup key.
   - `_normalise()` stripped periods but not apostrophes, so a name like
     `"Tre' Harris"` normalized to `"tre' harris"` and failed to match the
     index's `"tre harris"` (no apostrophe in the roster source name).
     Fixed by stripping both straight and curly apostrophes.
   Neither bug was severe enough to threaten the ≥90% floor (measured
   96.3-96.4% before the fix), but both were real and reproducible.
   Test-first regressions live in `tests/test_player_name_resolver.py`;
   full resolver + dependent sentiment-pipeline test suites (391 tests)
   pass green post-fix.
5. **Preseason week-mapping decision.** Every capture date bridged so far
   (2026-07-09 through today) sits well before the 2026 week-1 window
   closes (kickoff 2026-09-09, week 1 spans through 2026-09-14). Reusing
   `ingest_fp_ecr_history.map_scrape_date_to_week()` unchanged — the same
   "smallest week not yet concluded" rule the historical ingestion applies
   — maps **every one of these 43 dates to week=1**. This is a deliberate,
   documented choice, not an accident: FantasyPros' `week=0/type=draft`
   endpoint has no per-week concept at all in the preseason (see gap #1),
   so "current knowledge as of this date, applicable to the imminent week
   1" is the only honest interpretation available, and it's the same
   leakage-boundary logic `src/ecr_anchor.py`'s Thursday-exclusion rule
   already assumes (`kickoff_date > scrape_date`). The practical
   consequence — many days collapsing onto one `(season, week)`
   partition — is handled by writing rows sorted `scrape_date` DESCENDING,
   so `build_ecr_lookup()`'s unguarded `drop_duplicates("player_id",
   keep="first")` picks the freshest (closest-to-kickoff) capture for any
   player with conflicting values across days, rather than an arbitrary
   file-order artifact.

## 1. Protocol

Shadow mode from week 1: **run both with and without `--ecr-anchor` every
week, record both, ship neither as the default.** This mirrors
`--wr-tiebreak`'s and `--adp-prior`'s existing opt-in-forever posture — the
flag lands evaluable, never defaults ON, until a SHIP verdict is reached
and a human explicitly flips it (per `WR_ECR_ORDINAL_GATE.md`'s own
SHIP-PENDING-USER rule).

- **Primary comparison**: baseline `generate_projections.py --week N
  --season 2026` vs. `--ecr-anchor` using the CLI's own default
  configuration (`--ecr-anchor-mode near_tie`, i.e. mechanism (b) — the
  flag's default when no mode is given).
- **Secondary/informational comparison**: also run `--ecr-anchor
  --ecr-anchor-mode blend --ecr-anchor-weight 0.5` (the 2022-2024
  tuning-set winner) side by side, since it's cheap (same weekly
  projections re-run) and the primary gate on that mechanism cleared the
  historical bar 4.4x — only the shuffle-test sanity check was in
  question, and the redesigned test in §3 below is specifically for this
  mechanism.
- Both runs read whatever `data/silver/fp_ecr/season=2026/` contains at
  the time — i.e., THIS bridge's output, once the scoring-mismatch gap
  (§0.2) is resolved by whoever owns `src/ecr_anchor.py`.

**Grading**: reuse the existing Tuesday grading/ordinal-tracking machinery
wired 2026-08-10 (`scripts/weekly_grading_report.py`, which calls
`simulate_fp_accuracy.build_ordinal_table` — the exact same FP-style
ordinal Accuracy Gap function `WR_ECR_ORDINAL_GATE.md`'s historical gate
used) — do not build new grading machinery. `weekly_grading_report.py
--season 2026 --week N` already runs from the `weekly-pipeline.yml` Tuesday
09:00 UTC cron once actuals are final for the previous week, producing both
a single-week and a season-to-date cumulative ordinal Accuracy Gap table.
For each of the two `--ecr-anchor` configurations above, additionally save
their own graded projections under a distinguishing output path/filename
tag (mirrors `backtest_projections.py`'s existing output-filename tagging
for other opt-in levers) so `weekly_grading_report.py` (or a small ad-hoc
script reusing `build_ordinal_table`) can grade the treated run against the
same week's actuals independently of the shipped baseline.

**Cadence**: weekly, weeks 1-6 minimum (per the pre-registered checkpoint
below); continues opportunistically beyond week 6 if the checkpoint doesn't
produce a clean kill.

## 2. Verdict checkpoint — after week 6

- **SHIP-recommend** if cumulative WR ordinal Accuracy-Gap improvement
  (baseline − treated, summed/averaged consistently with how
  `WR_ECR_ORDINAL_GATE.md`'s pooled metric was computed) is **≥0.05** AND
  **≥4 of the 6 graded weeks are individually positive** (treated beats
  baseline that week).
- **Kill** (fold back to permanent HOLD, no further forward-gate weeks
  needed) if cumulative improvement is **≤0**.
- Anything strictly between 0 and 0.05, or a positive cumulative with <4/6
  positive weeks: **inconclusive** — continue shadow-mode data collection
  past week 6 rather than forcing a premature verdict; re-check the same
  two bars at each subsequent week until one clearly triggers.
- Report the primary (near_tie) and secondary (blend w=0.5) comparisons'
  checkpoints separately — do not average them into one number. A
  divergence between the two (e.g. near_tie kills while blend ships, or
  vice versa) is itself a result worth recording, not an error to resolve
  by picking one.
- Per the existing deconfounded-slices discipline
  (`WR_ECR_ORDINAL_GATE.md` §5 / `gated-experiment-coverage-check.md`),
  also report the week-1 coverage numbers (ECR-match rate among graded WR
  population, before/after the Thursday-exclusion rule) BEFORE any
  ordinal-gap numbers each week — the same "coverage before results"
  discipline that gate applied to the 2022-2024 data.

## 3. Redesigned sanity/leak test (supersedes the single-fixed-seed
   collapse-to-zero bar, blend mechanism only)

Per `knowledge-vault/concepts/shuffle-test-must-match-mechanism-shape.md`
(written 2026-08-18 directly from this lever's HOLD verdict): "the effect
must collapse to ~0 under a shuffled signal" is the right null **only** for
a disagreement-gated mechanism (near_tie, mechanism (b)) — it is the wrong
null for an unconditional full-reorder/weighted-blend mechanism (blend,
mechanism (a)), because shuffling a full-reorder's input signal doesn't
turn firings into no-ops, it swaps real information for `w`-weighted pure
noise, which actively hurts rather than washing out to zero. That's exactly
what the original historical shuffle test found (blend w=0.5: true
Δ=-0.220, shuffled Δ=+0.920 — a 4.2x inversion, not a collapse) — and per
the vault note, an inversion is *evidence against* a leak, not evidence of
one, for this mechanism shape.

**This section pre-registers the shape-appropriate replacement test**, to
be applied to any future re-run of the historical 2022-2024 blend gate
AND, where enough in-season weeks accumulate, to this forward gate's own
blend-mechanism track:

1. **Null distribution construction.** Draw **K=100** independent random
   shuffles of `ecr_pos_rank` within each `(season, week)` group (same set
   of matched players each shuffle; ranks reassigned via
   `numpy.random.default_rng(seed)` for `seed in range(100)` — distinct
   seeds, not the single fixed seed 42 the original test used). For each
   shuffle `k`, rerun the exact blend mechanism at the exact weight under
   test (`w=0.5` for the historical tuning-set winner) and compute the
   pooled ordinal Accuracy-Gap delta `Δ_k = treated_gap − baseline_gap`
   over the same evaluation weeks used for the real result. This yields an
   empirical null distribution `{Δ_1, ..., Δ_100}` — "what does a
   full-reorder at this exact weight do to the metric when the reordering
   carries zero real information."
2. **Test statistic.** Compute the TRUE delta `Δ_true` using the real
   (unshuffled) `ecr_pos_rank`.
3. **Empirical p-value.** `p = fraction of {Δ_k} at least as good as
   Δ_true` (i.e., as negative or more negative, since lower Accuracy Gap
   is better — a one-sided test in the improving direction).
4. **Pass/fail bar.** The mechanism clears the redesigned sanity check if
   `p < 0.05` — i.e., the true signal beats at least 95% of same-shape,
   same-weight noise. This directly tests "is the ORDERING information in
   `ecr_pos_rank` responsible for the effect," which is what a shuffle
   test is supposed to establish, without requiring the mechanically
   impossible "collapses to ~0" behavior a full-reorder mechanism can't
   produce even when the signal is genuine.
5. **Reported alongside, not instead of:** the null distribution's own
   mean and std. If the null distribution's mean is *itself* substantially
   improving over baseline (rather than centered near/worse than baseline
   noise should be), that's a distinct red flag about the metric/mechanism
   interaction independent of whether the true signal clears the p<0.05
   bar — surfaced explicitly, not folded into the single p-value.
6. **near_tie (mechanism (b)) keeps the ORIGINAL collapse-to-zero test**
   unchanged — it already passed cleanly (91% reduction on shuffle,
   single-seed) and is disagreement-gated, the shape that test is actually
   valid for. Do not apply the K=100 redesigned test to it; there is no
   reason to and it would just add compute for no informational gain.

This is registered here, BEFORE re-running it against either the
historical 2022-2024 data or new 2026 forward-gate weeks — consistent with
this repo's pre-registration discipline (no post-hoc test redesign after
seeing an inconvenient result; this redesign was proposed as a named
follow-up in `WR_ECR_ORDINAL_GATE.md`'s own "Recommended follow-up"
section and is being formally specified now, before use).

## 4. Cron-vs-local decision (explicit, per instructions)

**Decision: the bridge runs locally, not in any GitHub Actions workflow.**
`data/silver/fp_ecr/` is fully gitignored (`.gitignore` lines ~443-444,
`data/bronze/fp_ecr_history/` / `data/silver/fp_ecr/` — no allowlist
entries anywhere near it, confirmed by grep) — local-only by the same
GPL-3.0/FantasyPros-ToS provenance rule the historical archive already
follows, and this bridge's 2026 output inherits that gitignore
automatically (same path prefix, not a new pattern). A GitHub Actions
runner is a fresh, ephemeral checkout every run: anything the bridge wrote
to a gitignored path would be silently discarded the moment the job ends,
so a cron-side bridge step would burn CI minutes computing output nobody
downstream — in that job or any other — could ever read. That fails the
ponytail test in the task instructions ("if a cron-side bridge run
produces output the runner immediately discards, DON'T add the step").

Instead: `scripts/bridge_fp_ecr_live.py` is meant to be run **locally**
(the same machine that runs `scripts/generate_projections.py` /
`scripts/backtest_projections.py` for the weekly forward-gate shadow
comparisons in §1 — those already have to run locally too, since their
`--ecr-anchor` output depends on this bridge's local, gitignored Silver
data existing on disk first). A short pointer was added to
`.claude/skills/weekly-pipeline/SKILL.md` (new optional "Step 0") noting
that anyone running the weekly pipeline during the `--ecr-anchor` forward
gate should run the bridge first so the week's Silver ECR data is current
before generating projections.

No workflow file was created or modified this session
(`.github/workflows/madden*` is explicitly out of scope per the
multi-agent file-ownership split, and per the analysis above, no *other*
workflow would benefit from a bridge step either).

## 5. Files

- `scripts/bridge_fp_ecr_live.py` — the bridge; see its module docstring
  for the full list of schema/scoring/mapping decisions. Amended
  2026-08-22 with weekly-position preference (`load_all_captures` now
  prefers a true weekly-position capture over the draft board per
  scrape_date; `Capture.kind` + `weekly_capture_to_position_rows`).
- `tests/test_bridge_fp_ecr_live.py` — 34 tests (was 26; +8 2026-08-22):
  position-ranked row derivation, id-resolution fallback tiers +
  team-code normalization + memoization, week mapping (incl.
  unmapped/post-season drop), honest null-field mapping, ≥90% WR
  match-rate fail-loud (below and at the boundary), schema-column-for-
  column match against the real `data/silver/fp_ecr/season=2024/`
  historical file, idempotent upsert (replace-not-duplicate, cross-date
  accumulation, descending scrape_date sort), archive/live capture
  loading (folder-name-as-date, live-file dedup against already-archived
  dates, malformed folder names ignored), and (new) weekly-position
  row shaping + weekly-vs-draft-board preference resolution.
- `scripts/refresh_external_rankings.py` — amended 2026-08-22:
  `fetch_fantasypros_weekly()` + `_extract_ecr_data_json()` +
  `_parse_fp_weekly_page()` (new), `save_rankings()` gains an additive
  `extra` kwarg, `--source fantasypros_weekly` / included in `--source all`.
- `tests/test_external_rankings_archive.py` — +17 tests (2026-08-22) for
  the above.
- `src/ecr_anchor.py` — amended 2026-08-22: `ECR_SCORING_PREFERENCE`
  replaces the hardcoded `ECR_SCORING="ppr"` filter in `_load_ecr_season`
  / `build_ecr_lookup` (additive, backward-compatible keyword param).
- `tests/test_ecr_anchor.py` — +5 tests (2026-08-22),
  `TestScoringPreferenceRegression`.
- `src/player_name_resolver.py` — amended 2026-08-22: dead `_NICKNAME_MAP`
  entries fixed (re-normalise mapped value), apostrophe stripping added
  to `_normalise()`.
- `tests/test_player_name_resolver.py` — +9 tests (2026-08-22).
- `.claude/skills/weekly-pipeline/SKILL.md` — optional "Step 0" pointer to
  run the bridge locally before projections during the forward-gate period
  (no GHA changes — see §4).
- **Data**: `data/silver/fp_ecr/season=2026/fp_ecr_2026.parquet` (local
  only, gitignored, not committed) — 13,012 rows across 45 bridged capture
  dates as of 2026-08-22 (was 12,126 rows / 43 dates on 2026-08-21), all
  `week=1` (see §0.5); the 2026-08-23 date is the first true
  weekly-position capture (598/604 rows resolved, WR 98.3%).
  `data/external/fantasypros_weekly_rankings.json` (new; `data/external/`
  is committed by the daily-sentiment cron, same as the existing
  `fantasypros_rankings.json` — no new gitignore entry needed) is the
  live weekly-position cache; dated archive alongside the existing
  `fantasypros_rankings.json` snapshots.

## 6. Results

*(Empty pending week 1 of the 2026 season, 2026-09-09+. Do not fill this in
until real graded weekly data exists — filling in placeholder or simulated
numbers here would defeat the point of a pre-registered forward gate.)*
