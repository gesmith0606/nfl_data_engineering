---
phase: SV2-team-sentiment-game-lines
plan: 02
subsystem: sentiment-pipeline
tags: [sentiment, team-aggregation, game-predictions, edge-adjustment]
dependency_graph:
  requires: [SV2-01]
  provides: [team-sentiment-aggregation, sentiment-edge-adjustment]
  affects: [generate_predictions.py, process_sentiment.py]
tech_stack:
  added: []
  patterns: [team-level-aggregation, post-prediction-adjustment, word-boundary-regex]
key_files:
  created:
    - src/sentiment/aggregation/team_weekly.py
    - tests/test_team_sentiment.py
  modified:
    - scripts/generate_predictions.py
    - scripts/process_sentiment.py
decisions:
  - "Team multiplier range [0.95, 1.05] — tighter than player [0.70, 1.15] due to noise"
  - "Edge adjustment max +/- 0.15 pts via SENTIMENT_EDGE_WEIGHT=1.5"
  - "Case-sensitive regex for short abbreviations (CAR, GB, etc.) to avoid false positives"
  - "Sentiment adjusts spread_edge only (post-prediction), never model predictions"
metrics:
  duration_seconds: 2146
  completed: "2026-04-13T02:35:00Z"
  tasks_completed: 2
  tasks_total: 2
  test_count: 19
  files_created: 2
  files_modified: 2
---

# Phase SV2 Plan 02: Team Sentiment Aggregation and Game Line Adjustment Summary

Team-level sentiment aggregation from player signals with conservative post-prediction edge adjustment (max +/- 0.15 pts) wired into game predictions via --use-sentiment flag.

## What Was Built

### 1. Team-Level Sentiment Aggregation (`src/sentiment/aggregation/team_weekly.py`)

- **TeamWeeklyAggregator** reads Gold player sentiment, groups by team, computes weighted-average team sentiment
- **TEAM_NAME_TO_ABBR** dictionary mapping all 32 NFL teams (name, abbreviation, city, full name) to canonical 3-letter codes
- **detect_teams_in_text()** word-boundary regex detection with case-sensitive matching for short abbreviations to avoid false positives (e.g., "car" does not match "CAR")
- **team_sentiment_to_multiplier()** linear mapping: score [-1, +1] to multiplier [0.95, 1.05]
- **apply_team_sentiment_adjustment()** post-prediction edge modifier bounded to +/- 0.15 points
- Output: Parquet to `data/gold/sentiment/team_sentiment/season=YYYY/week=WW/`

### 2. Game Prediction Integration (`scripts/generate_predictions.py`)

- Added `--use-sentiment` flag for opt-in team sentiment edge adjustment
- Loads team sentiment, computes `sentiment_adjustment = (home_mult - away_mult) * 1.5`
- Adds transparency columns: `home_sentiment`, `away_sentiment`, `sentiment_adjustment`, `adjusted_spread_edge`
- Does NOT modify model predictions -- adjustment is on the edge (comparison vs Vegas) only

### 3. Pipeline CLI Update (`scripts/process_sentiment.py`)

- Added Step 3: Team Aggregation (Gold player -> Gold team) after player aggregation
- Added `--skip-team` flag to skip team aggregation if desired
- Prints team multiplier range summary when verbose

### 4. Tests (`tests/test_team_sentiment.py`)

- 19 tests across 4 test classes covering:
  - Team name detection (abbreviation lookup, 32-team coverage, word boundary, case sensitivity)
  - Multiplier conversion (neutral, bounds, clamping, partial)
  - Full aggregation pipeline (player data grouping, empty data, output columns, range enforcement, Parquet output)
  - Edge adjustment (bounded, no-data graceful, directional correctness, transparency columns)

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | a140e4e | Failing tests for team sentiment aggregation |
| 1 (GREEN) | f9c516f | Team-level sentiment aggregation and edge adjustment module |
| 2 | 3f4499e | Wire team sentiment into game predictions and pipeline CLI |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Case-sensitive abbreviation matching**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Word-boundary regex with case-insensitive flag matched lowercase "car" as "CAR" (Panthers)
- **Fix:** Made abbreviations (<= 3 chars, all-uppercase) use case-sensitive matching
- **Files modified:** src/sentiment/aggregation/team_weekly.py
- **Commit:** f9c516f

## Decisions Made

1. **Tight multiplier range [0.95, 1.05]** — Team-level sentiment is noisier than player-level, so the range is intentionally narrow (vs player [0.70, 1.15])
2. **SENTIMENT_EDGE_WEIGHT = 1.5** — With max multiplier diff of 0.10, this gives max adjustment of 0.15 points, as specified
3. **Case-sensitive abbreviation matching** — Short team codes (GB, KC, CAR, etc.) require exact uppercase to avoid false positives in natural text
4. **Post-prediction only** — Sentiment adjusts the edge transparency layer, not model predictions, preserving model integrity

## Verification

- All 19 team sentiment tests pass
- All 85 sentiment-related tests pass (team + processing + integration)
- Multiplier always clamped to [0.95, 1.05]
- Edge adjustment always bounded to +/- 0.15 points

## Self-Check: PASSED
