# Phase 79: Audit Provenance + Live Version Probe — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-27
**Phase:** 79-audit-provenance-version-probe
**Areas discussed:** script_sha definition, git_sha format & shape, Live-proof for SC#3, Historical audit JSON backfill

---

## script_sha Definition

### Q1: What should script_sha actually capture?

| Option | Description | Selected |
|--------|-------------|----------|
| File-specific last-commit SHA | `git log -1 --format=%H -- {script_path}`. Survives noise commits. | ✓ |
| Repo HEAD at execution time | `git rev-parse HEAD`. Simpler; cosmetic commits invalidate every audit. | |
| SHA-256 of file contents | Works outside git checkout; loses git lineage. | |
| Hybrid: file SHA + dirty flag | File commit + `script_dirty` boolean for uncommitted edits. | |

**User's choice:** File-specific last-commit SHA (Recommended)
**Notes:** The dirty flag was promoted into a separate question rather than bundled — see Q2.

### Q2: Should script_sha also flag 'dirty' (uncommitted) script edits at runtime?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — add `script_dirty: bool` field | Catches "ran from feature branch with local edits" failure mode. | ✓ |
| No — commit SHA only | Minimal JSON; trust clean-checkout discipline. | |

**User's choice:** Yes — add `script_dirty: bool` field (Recommended)
**Notes:** Phase 84's DEPLOY-04 can hard-reject `script_dirty: true` audits if desired.

### Q3: Where should the script_sha resolver live?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared helper in `src/utils.py` | New `get_script_sha(path) -> dict`; all 3 audit scripts import it. | ✓ |
| Inline in each audit script | Copy-paste subprocess call into 3 scripts; duplicate-pattern risk. | |
| New `scripts/_audit_common.py` module | Cleaner separation; new module to maintain. | |

**User's choice:** Shared helper in `src/utils.py` (Recommended)
**Notes:** Lands alongside existing `download_latest_parquet`, `get_latest_s3_key` helpers — same module style.

---

## git_sha Format & Shape

### Q4: What git_sha format should /api/version return?

| Option | Description | Selected |
|--------|-------------|----------|
| Full 40-char SHA | Drop `[:8]` truncation. Unambiguous compare against GITHUB_SHA. | ✓ |
| Keep [:8] truncation | Match current frontend convention; collision risk at scale. | |
| Both — `git_sha` (full) + `git_sha_short` (8) | Belt-and-suspenders; payload bloat. | |

**User's choice:** Full 40-char SHA (Recommended)
**Notes:** Phase 84's DEPLOY-02 asymmetry probe compares against GitHub Actions `${{ github.sha }}` — full SHA gives clean equality semantics.

### Q5: What should the diagnostic route flags do?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep them | `has_team_events_route` + `has_player_badges_route` proved useful in v7.1 silent-freeze; add `llm_enrichment_ready`. | ✓ |
| Move to a new `/api/version/diagnostics` | Tighten `/api/version` to spec; one more endpoint. | |
| Drop them | Tighten to DQ-02 spec verbatim; lose forensic surface area. | |

**User's choice:** Keep them (Recommended)
**Notes:** Final response shape: `{version, git_sha, build_id, deployed_at, llm_enrichment_ready, has_team_events_route, has_player_badges_route}`.

---

## Live-Proof for SC#3

### Q6: How should we prove SC#3 (live curl returns just-pushed SHA)?

| Option | Description | Selected |
|--------|-------------|----------|
| CI smoke step in deploy-web.yml | Poll `/api/version` until `git_sha == GITHUB_SHA` or timeout. Phase 84 inherits as the asymmetry-detection probe. | ✓ |
| Manual one-time verification artifact | Operator captures curl output to verification doc; no CI machinery. | |
| Structural test only | pytest asserts `version_info()` reads env var; doesn't prove live deploy. | |
| Both: structural test + CI smoke step | Belt-and-suspenders covering code regressions and image staleness. | |

**User's choice:** CI smoke step in deploy-web.yml (Recommended)
**Notes:** Warn-only in Phase 79; Phase 84 DEPLOY-02 promotes to fail-on-mismatch.

### Q7: Smoke-step polling timeout when Railway is slow?

| Option | Description | Selected |
|--------|-------------|----------|
| 5 min, warn-only | Mirrors Railway p95 deploy time; conservative ramp. | ✓ |
| 10 min, warn-only | Generous buffer for Docker layer rebuilds; slower CI feedback. | |
| 3 min, fail on miss | Tight loop; risks false positives on Railway slow days. | |

**User's choice:** 5 min, warn-only (Recommended)
**Notes:** Tail latency beyond 5 min during v7.0 hotfixes was the silent-freeze case — exactly what we want to surface.

---

## Historical Audit JSON Backfill

### Q8: What to do with existing v7.1 audit JSONs?

| Option | Description | Selected |
|--------|-------------|----------|
| Forward-only | Existing JSONs stay as-is; new runs have script_sha. Phase 84 treats missing field as "pre-provenance era — manual review". | ✓ |
| Re-run v7.1 audits with script_sha | Re-execute against current Railway; clean post-v7.2 baseline. Risk of result drift if backfilled data churns. | |
| Stamp existing JSONs in place | Add script_sha to existing files manually using historical `git log`. Cosmetic; preserves v7.1 evidence. | |

**User's choice:** Forward-only (Recommended)
**Notes:** Tightest scope. v7.1 audits already passed; re-running risks introducing churn unrelated to provenance.

---

## Wrap-Up

### Q9: Anything else to explore before writing CONTEXT.md?

| Option | Description | Selected |
|--------|-------------|----------|
| I'm ready for context | Write CONTEXT.md with the 8 decisions captured. | ✓ |
| Explore more gray areas | Surface 2-3 more decisions (test strategy, schema validation, onboarding doc). | |

**User's choice:** I'm ready for context

---

## Claude's Discretion (deferred to planner)

- Test layout and depth (unit + integration + smoke).
- Whether `script_provenance` is a top-level JSON key or nested under existing metadata block per audit script.
- Optional structural pytest asserting `version_info()` reads `RAILWAY_GIT_COMMIT_SHA` env var rather than hardcoding.

## Deferred Ideas

- Stamp historical v7.1 audit JSONs in place — rejected via D-08; could revisit in v7.3.
- `scripts/AUDIT_CONVENTIONS.md` onboarding doc — nice-to-have, planner discretion.
- Generic `routes: {name: bool}` map replacing ad-hoc diagnostic flags — out of scope, future hardening cycle.
- Vercel-side `/api/version` symmetry probe — parked behind Phase 84 DEPLOY-02 (chunk-fingerprint approach).
