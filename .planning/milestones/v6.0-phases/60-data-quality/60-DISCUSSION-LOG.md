# Phase 60: Data Quality - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-17
**Phase:** 60-Data Quality
**Areas discussed:** Roster refresh strategy, Position classification, Sanity check scope, Consensus data freshness

---

## Roster Refresh Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| GHA daily cron | GitHub Actions cron runs refresh_rosters.py daily, commits updated Gold parquet | ✓ |
| Pre-pipeline hook | Roster refresh runs automatically before every projection generation | |
| Manual on-demand | Keep current approach — run refresh_rosters.py manually | |

**User's choice:** GHA daily cron (Recommended)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-fix and log | Update team assignment automatically, log changes to roster_changes.log | ✓ |
| Flag and require approval | Write changes to staging file, require manual review | |
| Auto-fix silently | Just update the data, no special logging | |

**User's choice:** Auto-fix and log (Recommended)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Teams + positions | Update both recent_team and position from Sleeper in one pass | ✓ |
| Teams only | Keep position classification as separate step/script | |

**User's choice:** Teams + positions (Recommended)
**Notes:** None

---

## Position Classification

| Option | Description | Selected |
|--------|-------------|----------|
| Sleeper is always truth | Sleeper API is canonical position source for all contexts | ✓ |
| Sleeper for display, nfl-data-py for models | Different sources for display vs ML training | |
| Manual override list | Maintain manual override CSV for known mismatches | |

**User's choice:** Sleeper is always truth (Recommended)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Gold only | Fix positions in Gold projections and website display only | ✓ |
| Gold + Silver | Also update Silver parquet files | |
| All layers | Rewrite positions everywhere including historical training data | |

**User's choice:** Gold only (Recommended)
**Notes:** None

---

## Sanity Check Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Structural absurdities | Backup QB in top 5, negative projections, wrong team in top 20, missing positions | ✓ |
| Any rank deviation > 15 | Any player ranked 15+ spots from consensus = critical | |
| You decide | Claude determines appropriate thresholds | |

**User's choice:** Structural absurdities (Recommended)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| CI gate on deploy | Sanity check in deploy pipeline, 0 critical = proceed, any critical = blocked | ✓ |
| GHA check only | Run in GitHub Actions on push/PR but don't block deploys | |
| Manual only | Keep as manual script | |

**User's choice:** CI gate on deploy (Recommended)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add freshness checks | Warn if Gold >7 days stale, Silver >14 days stale | ✓ |
| No, keep projection-focused | Only validate projection content quality | |

**User's choice:** Yes, add freshness checks (Recommended)
**Notes:** None

---

## Consensus Data Freshness

| Option | Description | Selected |
|--------|-------------|----------|
| Live fetch from FantasyPros | Scrape/API-fetch ECR at runtime, always current | ✓ |
| Periodic manual update | Update hardcoded list monthly | |
| Sleeper ADP as proxy | Use existing Sleeper ADP data as benchmark | |

**User's choice:** Live fetch from FantasyPros (Recommended)
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Fall back to hardcoded list | Keep CONSENSUS_TOP_50 as stale-but-safe fallback, log warning | ✓ |
| Fall back to Sleeper ADP | Use Sleeper ADP as secondary source | |
| Fail the check | Report 'unable to validate' as warning | |

**User's choice:** Fall back to hardcoded list (Recommended)
**Notes:** None

---

## Claude's Discretion

- Warning threshold calibration (exact rank deviation for warning vs info)
- Sanity check output format (JSON vs text vs both)
- GHA cron schedule timing
- Specific FantasyPros endpoint/scraping approach

## Deferred Ideas

None — discussion stayed within phase scope
