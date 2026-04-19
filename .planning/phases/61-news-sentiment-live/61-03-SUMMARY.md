---
phase: 61-news-sentiment-live
plan: 03
subsystem: projection-engine
tags: [projections, events, rule-first, d-03, ship-gate, skip-decision]

# Dependency graph
requires:
  - file: "src/sentiment/processing/rule_extractor.py"
    provides: "Structured event flags from 61-02 (is_questionable, is_returning, is_traded, is_usage_boost, is_usage_drop, is_weather_risk, etc.)"
  - file: "src/projection_engine.py::apply_injury_adjustments"
    provides: "Signature pattern for companion adjuster"
provides:
  - "src/projection_engine.py::apply_event_adjustments: deterministic event→multiplier adjuster (opt-in via --use-events)"
  - "src/projection_engine.py::EVENT_MULTIPLIERS: 12-entry lookup table, clamped [0.0, 1.10] via EVENT_MULT_MIN/MAX"
  - "scripts/backtest_event_adjustments.py: CLI comparing MAE with/without events on 2022-2024 half_ppr"
  - "61-03-backtest.md: backtest report (structural no-op — 0/48 weeks had Gold events data)"
affects:
  - "Plan 61-05 can render event flags as NEWS-04 badges without projection-engine coupling"
  - "Future phase can flip --use-events default to True after Gold events covers ≥1 full historical season"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Companion-adjuster pattern: apply_event_adjustments mirrors apply_injury_adjustments signature for uniform composition"
    - "Bounded-multiplier table per D-03: each event flag gets a specific multiplier, NOT a continuous sentiment_multiplier"
    - "Unknown-flag tolerance: events_df columns beyond EVENT_MULTIPLIERS keys are silently ignored (forward compat)"
    - "Opt-in SHIP gate: --use-events flag ships disabled; backtest non-regression required before flipping default"

key-files:
  created:
    - "tests/test_event_adjustments.py (10 tests, all passing)"
    - "scripts/backtest_event_adjustments.py"
    - ".planning/phases/61-news-sentiment-live/61-03-backtest.md"
  modified:
    - "src/projection_engine.py (added EVENT_MULTIPLIERS, apply_event_adjustments)"
    - "scripts/generate_projections.py (added --use-events flag, default False)"
---

# Plan 61-03 — Event-based projection adjustments (SKIP)

## Outcome: SKIP (opt-in retained)

`--use-events` ships **opt-in** (default False). Per-event multipliers, function, CLI flag, and backtest harness are all landed and unit-tested — but the SHIP gate was not cleared because the backtest is structurally null.

## What shipped

1. **`EVENT_MULTIPLIERS`** table in `src/projection_engine.py` — 12 deterministic multipliers clamped to `[EVENT_MULT_MIN=0.0, EVENT_MULT_MAX=1.10]`. Prevents runaway compounding (T-61-03-01).
2. **`apply_event_adjustments(projections_df, events_df)`** — mirrors `apply_injury_adjustments` signature; joins on `player_id` (fallback `gsis_id`); adds `event_multiplier` (float) and `event_flags` (list[str]) columns; scales `projected_points`, `projected_floor`, `projected_ceiling`, and every `proj_*` column.
3. **Tests** — 10 new passing tests; 0 regressions in existing `test_projection_engine.py` (27/27 still green).
4. **`--use-events` CLI flag** in `scripts/generate_projections.py` — default `False`, separate from `--use-sentiment` per D-03.
5. **`scripts/backtest_event_adjustments.py`** — runs projections twice per (season, week), joins actuals, emits per-position MAE delta with SHIP/SKIP verdict and 0.05-point slack.

## Backtest result (2022-2024 half_ppr, 48 weeks)

| Position | Baseline MAE | Treatment MAE | Delta | Verdict |
| -------- | -----------: | ------------: | ----: | ------- |
| QB       | 6.892        | 6.892         | +0.000 | PASS |
| RB       | 5.251        | 5.251         | +0.000 | PASS |
| WR       | 4.918        | 4.918         | +0.000 | PASS |
| TE       | 3.790        | 3.790         | +0.000 | PASS |

Production baseline at plan time: 5.05 MAE.

## Why SKIP (structural verdict, not empirical)

**0 of 48 backtest weeks had Gold sentiment/event data.** Gold sentiment is only populated for 2025 W1 (30 players) at execution time. Treatment == baseline by construction on every backtest week, so delta = +0.000 is mathematically guaranteed — not evidence the adjustment helps.

Phase 54 lesson (walk-forward CV wins don't reliably survive production) applies even more forcefully here: this is weaker than WFCV because it doesn't evaluate the adjustment at all, it only confirms it's a no-op when there's no data.

**Decision:** keep `--use-events` opt-in. NEWS-04 badges can render from the same event flags without projection coupling (plan 61-05). Re-open SHIP after Gold events covers ≥1 full historical season.

## Commits

| Task | Commit | Description |
| ---- | ------ | ----------- |
| 1 (RED)   | `5cd1a9d` | Failing tests for `apply_event_adjustments` |
| 1 (GREEN) | `5c6df61` | Implement `apply_event_adjustments` in projection_engine.py |
| 2         | `dbeaa65` | Wire `--use-events` flag and backtest CLI |
| 3 (docs)  | (this commit) | Document SKIP decision |

## Requirements coverage

- **NEWS-01** — partial (events flow through extractor, not yet default in projections)
- **NEWS-04** — partial (projection adjuster exists but opt-in; plan 61-05 renders badges from the same event flags)

## Unblocks

- **61-05**: render event badges from the flag columns produced by 61-02's rule extractor — no dependency on `apply_event_adjustments` being default
- **Future phase**: once Gold events data covers ≥1 full historical season, re-run `scripts/backtest_event_adjustments.py` and flip SHIP gate
