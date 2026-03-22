# Phase 27: Prediction Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-21
**Phase:** 27-prediction-pipeline
**Areas discussed:** Output format & display, Confidence tiers, Vegas line source, CLI design & workflow

---

## Output Format & Display

| Option | Description | Selected |
|--------|-------------|----------|
| Compact (Recommended) | Teams, model line, Vegas line, edge, confidence tier — just the decision-relevant info | ✓ |
| Detailed | All of compact plus model MAE, feature count, top contributing features per game | |
| Both modes | Default to compact, --verbose flag shows detailed | |

**User's choice:** Compact
**Notes:** None

### Sorting

| Option | Description | Selected |
|--------|-------------|----------|
| By edge magnitude (Recommended) | Strongest edges first — best plays at the top | ✓ |
| By game time | Chronological order matching the weekly schedule | |
| By confidence tier then edge | High-confidence group first, then medium, then low | |

**User's choice:** By edge magnitude
**Notes:** None

### Output destination

| Option | Description | Selected |
|--------|-------------|----------|
| Console + Gold Parquet (Recommended) | Print table to console AND save as Gold-layer Parquet | ✓ |
| Console only | Print table, no file output | |
| Console + CSV | Print table and save a human-readable CSV alongside | |

**User's choice:** Console + Gold Parquet
**Notes:** None

### Table layout

| Option | Description | Selected |
|--------|-------------|----------|
| Combined table (Recommended) | One row per game with both spread and total edges | ✓ |
| Separate sections | Spread predictions table first, then total predictions table | |

**User's choice:** Combined table
**Notes:** None

---

## Confidence Tiers

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed points (Recommended) | High: >= 3 pts, Medium: 1.5-3 pts, Low: < 1.5 pts | ✓ |
| Percentile-based | Top 25% = High, middle 50% = Medium, bottom 25% = Low | |
| You decide | Claude picks thresholds based on backtest MAE | |

**User's choice:** Fixed points
**Notes:** None

### Small edges

| Option | Description | Selected |
|--------|-------------|----------|
| Show as Low (Recommended) | All games shown, smallest edges just labeled Low tier | ✓ |
| Filter with 'No edge' label | Games below 0.5 pts labeled 'No edge' | |

**User's choice:** Show as Low
**Notes:** None

### Tier independence

| Option | Description | Selected |
|--------|-------------|----------|
| Independent tiers (Recommended) | Separate spread_tier and total_tier per game | ✓ |
| Combined tier | One overall confidence per game based on stronger edge | |

**User's choice:** Independent tiers
**Notes:** None

---

## Vegas Line Source

| Option | Description | Selected |
|--------|-------------|----------|
| Schedules Bronze (Recommended) | Use spread_line and total_line from nfl-data-py schedules | ✓ |
| Manual CSV input | User provides CSV with current Vegas lines | |
| Both with fallback | Try schedules first, prompt for manual if null | |

**User's choice:** Schedules Bronze
**Notes:** None

### Missing lines

| Option | Description | Selected |
|--------|-------------|----------|
| Show prediction, skip edge (Recommended) | Output model line but edge/tier as N/A | ✓ |
| Skip entire game | Only show games with Vegas lines | |
| Accept --lines flag | Allow CSV flag for supplementary lines | |

**User's choice:** Show prediction, skip edge
**Notes:** None

---

## CLI Design & Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| --season and --week (Recommended) | Match roadmap success criteria exactly | ✓ |
| --season --week --target | Add --target spread\|total\|both | |
| Auto-detect current week | Defaults to current NFL week | |

**User's choice:** --season and --week
**Notes:** None

### --model-dir flag

| Option | Description | Selected |
|--------|-------------|----------|
| Yes (Recommended) | Consistent with other prediction scripts | ✓ |
| No | Always use default MODEL_DIR | |

**User's choice:** Yes
**Notes:** None

### Data ingestion

| Option | Description | Selected |
|--------|-------------|----------|
| Assume pre-ingested (Recommended) | Reads existing local data, user runs /ingest first | ✓ |
| Auto-fetch if missing | Auto-fetches via nfl-data-py if not found | |

**User's choice:** Assume pre-ingested
**Notes:** None

---

## Claude's Discretion

- Gold Parquet filename convention and exact output path
- Console table formatting library
- Edge sign convention
- Summary line count after table
- Error handling for missing models/data

## Deferred Ideas

None
