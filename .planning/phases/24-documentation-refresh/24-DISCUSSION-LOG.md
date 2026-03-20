# Phase 24: Documentation Refresh - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-20
**Phase:** 24-documentation-refresh
**Areas discussed:** Silver schema depth, Gold prediction schema, Bronze inventory refresh, CLAUDE.md scope

---

## Silver Schema Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-generate from parquet | Read parquet files, extract columns/types/samples, add hand-written descriptions | ✓ |
| Hand-written only | Manually document from source code — more narrative but slower | |
| Summary tables only | One table per path listing columns and types, no descriptions | |

**User's choice:** Auto-generate from parquet (Recommended)
**Notes:** None

### Silver Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Expand existing file | Add Silver sections to NFL_DATA_DICTIONARY.md after Bronze | ✓ |
| Separate Silver dictionary | New docs/SILVER_DATA_DICTIONARY.md | |

**User's choice:** Expand existing file (Recommended)
**Notes:** None

### Silver Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Replace with real schemas | Remove planned Games Silver, replace with auto-generated from parquet | ✓ |
| Keep both | Leave planned Games Silver alongside real schemas | |

**User's choice:** Replace with real schemas (Recommended)
**Notes:** None

---

## Gold Prediction Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Spec from requirements | Document planned columns from REQUIREMENTS.md, mark as "Planned" with badges | ✓ |
| Minimal placeholder | Section header saying "TBD — see Phase 25-27" | |
| Skip Gold for now | Don't add until tables exist | |

**User's choice:** Spec from requirements (Recommended)
**Notes:** None

### Gold Existing Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, document both | Add existing fantasy projection schema alongside planned prediction schema | ✓ |
| Prediction only | Only add new prediction schema | |

**User's choice:** Yes, document both (Recommended)
**Notes:** None

---

## Bronze Inventory Refresh

| Option | Description | Selected |
|--------|-------------|----------|
| Script-generated | Write/update script to scan data/bronze/ and auto-generate inventory from parquet metadata | ✓ |
| Manual update | Hand-edit markdown table | |
| You decide | Claude picks based on existing script availability | |

**User's choice:** Script-generated (Recommended)
**Notes:** None

---

## CLAUDE.md Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full refresh | Update test count, Silver paths, prediction vector, key files, status | ✓ |
| Numbers only | Just update counts and status lines | |
| Restructure | Reorganize sections for prediction+fantasy platform | |

**User's choice:** Full refresh (Recommended)
**Notes:** None

### Key Files Table

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add new modules | Add team_analytics.py, game_context.py, prediction_features.py | ✓ |
| Keep table compact | Only update existing entries | |

**User's choice:** Yes, add new modules (Recommended)
**Notes:** None

### Implementation Guide

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, full update | Add phases 20-23 completed, v1.4 phases 24-27 as planned with badges | ✓ |
| v1.3 only | Only add phases 20-23, skip v1.4 | |

**User's choice:** Yes, full update (Recommended)
**Notes:** None

---

## Claude's Discretion

- Column description wording for auto-generated Silver schemas
- Gold "Planned" badge layout
- Whether to update NFL_GAME_PREDICTION_DATA_MODEL.md

## Deferred Ideas

None — discussion stayed within phase scope
