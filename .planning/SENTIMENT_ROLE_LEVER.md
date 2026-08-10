# Sentiment-Driven Role-Change Lever — Coverage Check + Forward Path (2026-08-09)

Evaluates whether the **existing** sentiment/news pipeline can power an
early-season role-change lever per
`.planning/CONSENSUS_ERROR_DECOMPOSITION.md` finding #1 (weeks 3-6 weakness)
and #4 (role-volatile RBs) — the information consensus sources get from
human beat-reporter news that trailing-stat rolling averages structurally
cannot see this early in a season. Process per
`knowledge-vault/concepts/gated-experiment-coverage-check.md`: data reality
first, then branch to a gated backtest (PATH A) or a forward design (PATH B).

## STEP 0 — Data reality check

**Sentiment ingestion coverage, exhaustively inventoried:**

| Layer | Path | Seasons present | Weeks present |
|---|---|---|---|
| Bronze (rss/sleeper/pft/rotowire/reddit) | `data/bronze/sentiment/{source}/season=YYYY/` | **2025, 2026 only** | flat (not week-partitioned; date-stamped files) |
| Silver (signals) | `data/silver/sentiment/signals/season=YYYY/week=WW/` | **2025 (weeks 01, 17, 18), 2026 (week 01)** | 3 of 18 weeks in 2025, 1 of 18 in 2026 |
| Gold (multipliers) | `data/gold/sentiment/season=YYYY/week=WW/` | **2025 (weeks 01, 17, 18), 2026 (week 01)** | same as Silver |

`find data/{bronze,silver,gold}/sentiment -iname "*season=202[0-4]*"` returns
**zero files** — confirmed exhaustively, not just spot-checked. The earliest
Bronze RSS/Sleeper files are timestamped **2026-04-24**; every subsequent day
through today (2026-08-09) is present (173 RSS files, 123 Sleeper files, 140
PFT, 125 RotoWire, 11 Reddit), so the *daily* cadence since April is real —
the gap is exclusively **historical backfill**, and it cannot be closed: RSS
feeds serve current content only, there is no API that retroactively
reconstructs "what a beat reporter tweeted about a backup RB in October
2023." The `season=2025 week=18` pileup (100+ files, one per day since
late April) is `detect_nfl_week()` in `scripts/daily_sentiment_pipeline.py`
clamping to `week=18` during the current off-season, not a bug — verified
the clamp logic (`week = max(1, min((days_since // 7) + 1, 18))`) correctly
resolves to real weeks 1-18 once the 2026 season starts in September.

**This is exactly the expected outcome flagged in the task brief.**
`scripts/backtest_event_adjustments.py` (built in Phase 61-03, months before
this task) already documents this independently:

> Zero weeks had Gold sentiment/event data for the backtest window.
> Treatment equals baseline by construction, so the verdict is structurally
> SHIP (no regression possible)... sentiment Gold Parquet is only populated
> for 2025 W1 as of Phase 61-02. Re-run the backtest after the sentiment
> pipeline has produced Gold data for 2022-2024 before relying on the
> verdict for a ship decision.

**Verdict: PATH B.** No 2022-2024 (or 2020-2024) sentiment coverage exists
locally or ever existed — RSS/Sleeper ingestion is a 2026-vintage pipeline
with no retroactive backfill possible. A gated backtest experiment
(PATH A) is not executable; `--use-events`'s existing "ship gate" is
vacuous (0 events weeks) and must not be read as a real pass. This finding
matches finding "Fourth instance" — well, actually matches the general
lesson in `gated-experiment-coverage-check.md`: **verify the lever actually
has data to fire on before trusting any verdict.**

## Unexpected finding: the forward lever mostly already exists — it's silently starved

Before designing new machinery, I searched for existing role-change
infrastructure (ponytail: reuse before building). Phase 61 (D-02/D-03,
`.planning/phases/61-news-sentiment-live/`) already built almost everything
the task asked for:

1. **Leak-free extraction** — `src/sentiment/processing/rule_extractor.py`
   already detects role-change language via regex and sets two structured
   boolean flags per player-signal: `is_usage_boost` (workhorse, lead back,
   named starter, promoted, increased role, primary target, bell-cow — 55
   true instances in the 1,470 Silver records on disk) and `is_usage_drop`
   (timeshare, committee back, benched, demoted, splitting carries, limited
   snaps — 11 true instances). These fire **at document-ingestion time**,
   strictly before the projected week, so they are leak-free by
   construction — no different from the depth-chart/injury leak-free
   patterns already used by `qb_starter_floor.py`.
2. **Bounded, deterministic multiplier table** —
   `src/projection_engine.py::EVENT_MULTIPLIERS` already maps
   `is_usage_boost → 1.08` and `is_usage_drop → 0.85` (plus 10 other event
   flags), clamped to `[0.0, 1.10]` when compounded
   (`apply_event_adjustments()`). This is deliberately a **tighter, bounded**
   design than the continuous `sentiment_multiplier` path (`0.70-1.15`) per
   Phase 61 decision D-03, specifically because Phase 54 found wide
   continuous ranges degrade production even when offline CV looks good —
   i.e. the exact caution this task's brief implicitly wants.
3. **Opt-in weekly CLI wiring** — `scripts/generate_projections.py
   --use-events` (default `False`) already calls
   `apply_event_adjustments()` after injury adjustments, mirroring the
   `--early-season-prior` / `--qb-starter-floor` pattern this task asked me
   to replicate. **No new flag was needed.**
4. **A pre-registered forward-style gate script** —
   `scripts/backtest_event_adjustments.py` already exists, with a
   documented ship rule (D-03: treatment MAE within +0.05 of baseline on
   every position) and already self-flags its own vacuous-pass problem
   in its markdown output when `events_weeks == 0`.

**What was actually broken:** `src/sentiment/aggregation/weekly.py`
(`WeeklyAggregator`, the Silver→Gold step) only OR-aggregated **5 of the 12**
event flags into the Gold Parquet — `is_ruled_out`, `is_inactive`,
`is_questionable`, `is_suspended`, `is_returning`. The other 7, including
**both role-change flags**, were computed at Silver time and then silently
dropped before reaching Gold. `apply_event_adjustments()` only reads flags
that are actually present as columns in `events_df`
(`present_flags = [f for f in EVENT_MULTIPLIERS if f in events_df.columns]`)
— so `is_usage_boost`/`is_usage_drop` never had a column to read from, and
the role-change multiplier was a **silent structural no-op end-to-end**,
even in the (small) 2025/2026 window where data does exist, and even though
`--use-events` and every downstream piece is already wired and tested. This
is the same class of bug the coverage-check doc's "Fourth instance" and
TD-08/09/10 pattern describe: correct-looking code, dead in practice because
of one missing wiring hop. `tests/test_event_adjustments.py`'s own test
fixture (`_make_events()`) already builds a DataFrame with **all 12**
`EVENT_MULTIPLIERS` columns, i.e. the test suite's own contract assumed
Gold carried all 12 — the aggregator just didn't honor it.

## Fix applied (small wiring gap, per the task brief's explicit ask)

`src/sentiment/aggregation/weekly.py::WeeklyAggregator._compute_player_aggregate`
now OR-aggregates all 7 previously-dropped flags (`is_activated`,
`is_traded`, `is_released`, `is_signed`, `is_usage_boost`, `is_usage_drop`,
`is_weather_risk`) alongside the existing 5, and `aggregate()`'s
`ordered_cols` includes them in the Gold Parquet schema. No changes to
extraction, the multiplier table, or CLI wiring — those were already
correct. The daily cron (`daily-sentiment.yml` → `daily_sentiment_pipeline.py`
→ `_run_player_aggregation` → `WeeklyAggregator.aggregate()`) picks up this
fix automatically on its next run; no separate wiring change needed there.

Verified additive/non-breaking: every Gold-sentiment consumer I found
(`web/api/services/news_service.py`, `projection_engine.apply_sentiment_adjustments`,
`apply_event_adjustments`) accesses columns via `.get()` or
`if "col" in df.columns` guards — none assume an exact column set, so
adding 7 columns cannot break an existing reader.

## Forward feature (already exists, now actually live)

Per-player role-change score = the OR'd `is_usage_boost` / `is_usage_drop`
boolean flags in `data/gold/sentiment/season=S/week=W/*.parquet`, available
at projection time (Silver signals are timestamped strictly before the
projected week; the Gold aggregation reads only already-published news).
`--use-events` on `scripts/generate_projections.py`'s weekly path applies
the bounded `1.08`/`0.85` multiplier. **Left OFF by default**, unchanged
from its pre-existing state — this fix does not flip any default, it only
lets an already-opt-in lever actually do something when opted into.

`scripts/backtest_projections.py` was not touched: there is no
2022-2024 sentiment Gold data for it to backtest against (confirmed
above), so wiring `--use-events` there today would be dead machinery
identical in kind to the bug just fixed — inert until real data
accumulates. `scripts/backtest_event_adjustments.py` already exists for
this purpose and will start producing a real signal once run against a
season with actual Gold coverage.

## Pre-registered forward gate (to run once 2026 weeks 1-6 accumulate)

Written now, before any 2026 in-season data exists, so the eventual
read cannot be curve-fit to the outcome.

**Trigger:** after NFL 2026 weeks 1-6 have completed and
`data/gold/sentiment/season=2026/week={01..06}/` all have real
Silver-derived signal coverage (not the off-season week-18 clamp).

**Method:** run `scripts/backtest_event_adjustments.py --seasons 2026
--positions qb rb wr te` (it already builds the baseline/treatment split
end-to-end via the production code path) restricted to weeks 3-6, or a
purpose-built variant that filters to `week in [3,4,5,6]`. Report, in this
order, before any headline number (per the coverage-check doc's mandatory
rule):

1. **Firing rate**: `is_usage_boost`/`is_usage_drop` rows changed / QB+RB+WR+TE
   rows eligible, per week. If firing rate is nowhere near practically
   material (e.g. <2% of rows, echoing the QB-starter-floor lever's 0.7%
   detector-starvation HOLD), stop and report "detector starved," not a
   hypothesis rejection — do not force a full gate read on a handful of
   flagged rows.
2. **Gold data completeness check**: confirm weeks 3-6 actually have
   Silver signal files (not silently empty), and that baseline/treated are
   generated back-to-back in one session on identical data (the
   byte-identical-untouched-slices guard from
   `gated-experiment-coverage-check.md`) — reused-stale-baseline
   contamination bit three separate levers earlier this cycle
   (early-season-prior, RB-tail, QB-starter-floor gates all hit this).

**SHIP** if, once firing rate clears a materiality floor (≥5% of QB/RB/WR/TE
weeks 3-6 rows flagged — otherwise treat as underpowered per (1) above):

- Weeks 3-6 overall MAE vs Sleeper improves by ≥0.05 pts **on the subset of
  rows the flag actually touched** (not the full population — diluting by
  the ~95%+ untouched rows would hide a real effect, the same selection
  dynamic already documented in `RB_TAIL_CALIBRATION_GATE.md`'s "population
  shrinkage note"), **AND**
- No position's full-season (weeks 3-18) MAE worsens by >0.05, **AND**
- QB/RB/WR/TE rows NOT touched by either flag are byte-identical between
  baseline and treated (confirms scoping — the multiplier table already
  guarantees this by construction, but verify empirically per the coverage
  doc's repeated lesson that "should be scoped" and "is scoped" are not
  the same claim without a diff).

**Else HOLD**, report the numbers and firing rate honestly, keep
`--use-events` opt-in/off (as it already is).

This gate deliberately does **not** reuse the `_MAE_SLACK=0.05` /
"byte-identical if untouched" ship rule already coded into
`backtest_event_adjustments.py` verbatim, because that script's rule
answers "does turning on ALL 12 event flags regress anything" (a safety
question, already answerable and already vacuously SHIP), not "does the
role-change signal specifically move the weeks-3-6 needle enough to be
worth defaulting on" (the effectiveness question this task cares about,
which needs its own firing-rate-aware bar).

## Caveats

- **Sparse by construction, likely to stay sparse.** 55 `is_usage_boost` /
  11 `is_usage_drop` true records across ~4 months and 5 free RSS/Reddit/
  Sleeper sources is a low base rate; a materially higher volume would need
  more sources (e.g. beat-reporter Twitter/X, currently not ingested —
  `twitter_doc_count` exists as a Gold column but no Twitter ingester exists
  in `scripts/ingest_sentiment_*.py`) or the `ENABLE_LLM_ENRICHMENT` Claude
  path turned on (currently `false` by default per `daily-sentiment.yml`,
  rule-based extraction is authoritative per D-06). Both are levers for a
  future iteration, not required for this task.
- **`player_id` resolution noise.** The one inspected `is_usage_boost=True`
  sample record was Mike Vrabel (a head coach, `player_id: null`) — the
  name-extraction regex in `rule_extractor.py` catches non-player subjects
  too. `WeeklyAggregator` already drops `player_id=None` records before
  aggregation (`last_null_player_count` telemetry), so this doesn't
  contaminate Gold rows, but it does mean part of the already-small
  usage-boost signal volume is coach/team news, not player role changes —
  worth a `subject_type == "player"` filter tightening as a future
  precision improvement, not blocking this task.
- **The multiplier magnitude (1.08/0.85) was set by Phase 61 design
  judgment, not backtested against role-change outcomes specifically** —
  the forward gate above is also implicitly the first real test of whether
  that magnitude is well-calibrated once enough weeks-3-6 role-change
  weeks accumulate to say anything.

## Files changed

- `src/sentiment/aggregation/weekly.py` — `_compute_player_aggregate()` now
  OR-aggregates `is_activated`, `is_traded`, `is_released`, `is_signed`,
  `is_usage_boost`, `is_usage_drop`, `is_weather_risk` (previously computed
  at Silver but dropped before Gold); `aggregate()`'s `ordered_cols` extended
  to match. No other files touched — `--use-events`,
  `apply_event_adjustments`, `EVENT_MULTIPLIERS`, and the CLI wiring in
  `scripts/generate_projections.py` were already correct and needed no
  changes.
- `tests/test_sentiment_processing.py` — 5 new unit tests: 4 in
  `TestEventFlagOrLogic` covering OR-aggregation of the 7 previously-dropped
  flags (usage boost/drop propagation, all-false stays false, transaction +
  weather flags), 1 new integration test in `TestWeeklyAggregation`
  (`test_aggregate_usage_boost_column_survives_to_gold`) proving the fix
  end-to-end through `aggregate()`'s public API, not just the private
  helper. All passing.

## Tests run

```
./venv/Scripts/python.exe -m pytest tests/test_sentiment_processing.py \
    tests/test_sentiment_integration.py tests/test_event_adjustments.py \
    tests/sentiment/ tests/test_team_sentiment.py -q
```

311 passed, 0 failed (includes the 5 new tests plus every existing
sentiment/event-adjustment test — no regressions).
