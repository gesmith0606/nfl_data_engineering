# `--ecr-anchor` 2026 In-Season Forward Gate (2026-08-21)

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

1. **Source-product mismatch (the big one).** `refresh_external_rankings
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
   forward gate should be read with that substitution in mind. The
   structural fix (a true weekly-position capture) is outside this
   session's file ownership (`scripts/refresh_external_rankings.py`) —
   flagged as a follow-up, not applied.
2. **Scoring mismatch blocks the wiring today.** Our capture's true scoring
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
3. **`ecr`/`sd`/`best`/`worst` are null for every 2026 row.** Our capture
   has no per-expert dispersion and no float consensus average — only an
   integer overall-board rank. `ecr_anchor.py` only ever reads `pos_rank`
   from the Silver file (verified by reading `build_ecr_lookup()`'s source
   — it never touches `ecr`/`sd`/`best`/`worst`), so this has **no
   functional impact on the lever itself**, only on anyone else who might
   read those columns expecting real values.
4. **No `fantasypros_id`.** Our capture carries no FantasyPros numeric
   player id, so id resolution goes through
   `src.player_name_resolver.PlayerNameResolver` (fuzzy name match) instead
   of the historical ingestion's DynastyProcess id-crosswalk join. Two
   pre-existing bugs in `src/player_name_resolver.py` were found while
   diagnosing the ~3.6% WR non-match rate (not fixed here — out of this
   session's ownership, and shared infra other agents may be touching
   concurrently):
   - `_NICKNAME_MAP` has three dead/harmful entries (`"aj brown"`,
     `"dj moore"`, `"dj chark"`) that map a dot-stripped normalized key
     back to a **dotted** string (`"a.j. brown"` etc). Since `_normalise()`
     strips periods from every name (including when the lookup index
     itself was built), the dotted remapped string can never match any
     index key — these three entries actively break resolution for exactly
     the players they were meant to help. Explains "A.J. Brown" and
     "DJ Moore" showing up unresolved despite being present in the index
     under an unambiguous `(team, position)`.
   - `_normalise()` strips periods but not apostrophes, so a name like
     `"Tre' Harris"` normalizes to `"tre' harris"` and fails to match the
     index's `"tre harris"` (no apostrophe in the roster source name).
   Neither bug is severe enough to threaten the ≥90% floor (measured
   96.3-96.4%), but both are real, reproducible, and worth a follow-up fix
   in `src/player_name_resolver.py` by whoever owns it next.
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

- `scripts/bridge_fp_ecr_live.py` (new) — the bridge; see its module
  docstring for the full list of schema/scoring/mapping decisions.
- `tests/test_bridge_fp_ecr_live.py` (new) — 26 tests: position-ranked row
  derivation, id-resolution fallback tiers + team-code normalization +
  memoization, week mapping (incl. unmapped/post-season drop), honest
  null-field mapping, ≥90% WR match-rate fail-loud (below and at the
  boundary), schema-column-for-column match against the real
  `data/silver/fp_ecr/season=2024/` historical file, idempotent
  upsert (replace-not-duplicate, cross-date accumulation, descending
  scrape_date sort), and archive/live capture loading (folder-name-as-date,
  live-file dedup against already-archived dates, malformed folder
  names ignored).
- `.claude/skills/weekly-pipeline/SKILL.md` — optional "Step 0" pointer to
  run the bridge locally before projections during the forward-gate period
  (no GHA changes — see §4).
- **Data**: `data/silver/fp_ecr/season=2026/fp_ecr_2026.parquet` (local
  only, gitignored, not committed) — 12,126 rows across 43 bridged capture
  dates as of 2026-08-21, all `week=1` (see §0.5).

## 6. Results

*(Empty pending week 1 of the 2026 season, 2026-09-09+. Do not fill this in
until real graded weekly data exists — filling in placeholder or simulated
numbers here would defeat the point of a pre-registered forward gate.)*
