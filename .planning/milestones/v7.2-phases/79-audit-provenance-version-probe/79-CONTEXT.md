# Phase 79: Audit Provenance + Live Version Probe — Context

**Gathered:** 2026-04-27
**Status:** Ready for planning
**Milestone:** v7.2 Data + Site Polish
**Requirements covered:** DQ-01, DQ-02

<domain>
## Phase Boundary

Phase 79 makes audit + deploy evidence forensically traceable.

**Delivers:**
1. `script_sha` (+ `script_dirty`) field on every audit-script JSON output, capturing the audit script's git provenance at execution time.
2. `/api/version` returning a complete `{git_sha, deployed_at, llm_enrichment_ready}` payload that reflects the *running Railway image*, plus a CI smoke step that proves it after every deploy.

**Does NOT deliver (Phase 84 territory):**
- Promoting the version probe from warn-only to fail-on-mismatch (DEPLOY-02).
- The audit-JSON consumer that asserts `script_sha` matches a known-good commit (DEPLOY-04).
- Auto-rollback workflow-touch guard or rebase-loop structural test (DEPLOY-01, DEPLOY-03).

**Critical-path role:** Phase 79 → Phase 84. 79 produces the asymmetry-detection capability; 84 enforces it.

</domain>

<decisions>
## Implementation Decisions

### script_sha Definition (DQ-01)

- **D-01:** `script_sha` = file-specific last-commit SHA, resolved via `git log -1 --format=%H -- {script_path}`. Survives noise commits — only re-runs when the script itself changes. Phase 84's "known-good script revision" check therefore means "this exact script logic was approved", not "this audit ran from any commit on main".
- **D-02:** Include a `script_dirty: bool` companion field. Set true when `git diff HEAD -- {script_path}` is non-empty at execution time. Catches the "ran from a feature branch with local edits" failure mode. Phase 84 can choose to hard-reject `script_dirty: true` audits.
- **D-03:** Resolver lives in `src/utils.py` as `get_script_sha(script_path: str) -> dict` returning `{sha, dirty, resolved_at}`. All three current audit scripts (`audit_event_coverage.py`, `audit_advisor_tools_evt05.py`, `audit_advisor_tools.py`) import it and embed the dict under a top-level `script_provenance` key in their JSON output. Future audit scripts get the field for one import line.

### /api/version Format & Shape (DQ-02)

- **D-04:** Return full 40-char `git_sha` from `RAILWAY_GIT_COMMIT_SHA` (drop the current `[:8]` truncation in `web/api/main.py:118`). Phase 84's asymmetry probe compares against `GITHUB_SHA` (40 chars) — unambiguous equality check beats truncated comparison. The 32-byte payload bump is trivial.
- **D-05:** Keep the existing diagnostic route flags (`has_team_events_route`, `has_player_badges_route`) — they proved useful during the v7.1 silent-freeze. **Add `llm_enrichment_ready: bool`** mirroring `/api/health` logic (`bool(os.environ.get("ANTHROPIC_API_KEY"))`). Final response shape: `{version, git_sha, build_id, deployed_at, llm_enrichment_ready, has_team_events_route, has_player_badges_route}`.

### Live-Proof for SC#3

- **D-06:** Add a new smoke step in `.github/workflows/deploy-web.yml` (Railway deploy job): after the redeploy trigger, poll `/api/version` until the returned `git_sha == GITHUB_SHA` for the just-pushed commit. This *is* the asymmetry-detection capability — Phase 84 promotes the same probe to fail-on-mismatch via DEPLOY-02.
- **D-07:** Polling budget: **5 minutes, warn-only**. Mirrors Railway's typical p95 deploy time. Phase 79 keeps it warn-only because Phase 84 inherits the probe and promotes to hard-fail behavior; flipping the gate now risks blocking deploys on Railway latency before the probe is hardened.

### Historical Audit JSON Backfill

- **D-08:** **Forward-only.** Existing v7.1 audit JSONs (`event_coverage.json`, `advisor_tools_72.json`) stay unchanged. Phase 84's audit-JSON consumer (DEPLOY-04) treats a missing `script_sha`/`script_provenance` field as "pre-provenance era — manual review required" rather than auto-reject. Tightest scope; preserves v7.1 evidence intact.

### Claude's Discretion

- Test layout (unit tests for `get_script_sha`, integration test for `/api/version` shape, smoke-step assertion in CI workflow) — planner decides.
- Whether `script_provenance` is a top-level key vs nested under existing `metadata` block in audit JSONs — planner decides based on each script's existing structure.
- Whether to add a structural pytest asserting `version_info()` reads the env var (rather than hardcodes) — recommended but not required by DQ-02.

### Folded Todos

None. Phase 79 todos are bounded by DQ-01 + DQ-02 verbatim; no backlog items merged in.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/milestones/v7.2-REQUIREMENTS.md` §"Data Freshness + Correctness (DQ-XX)" — DQ-01 and DQ-02 source-of-truth wording.
- `.planning/milestones/v7.2-ROADMAP.md` §"Phase 79" — Goal statement, dependencies, 3 success criteria.
- `.planning/STATE.md` — Milestone position, critical-path note (79 → 84).

### Existing Code (must be read before editing)
- `web/api/main.py:113-127` — Current `/api/version` implementation. D-04 + D-05 modify this function.
- `web/api/main.py:95-110` — `/api/health` (source of `llm_enrichment_ready` logic to mirror).
- `web/api/models/schemas.py:336` — `HealthResponse.llm_enrichment_ready` field definition.
- `scripts/audit_event_coverage.py` — DQ-01 consumer #1 (writes `event_coverage.json`).
- `scripts/audit_advisor_tools_evt05.py` — DQ-01 consumer #2 (writes `advisor_tools_72.json`).
- `scripts/audit_advisor_tools.py` — DQ-01 consumer #3 (parent script of evt05 sibling).
- `src/utils.py` — Lands new `get_script_sha()` helper (D-03). Existing utilities use the same `from __future__ import annotations` + type-hint style.
- `.github/workflows/deploy-web.yml` — Lands new smoke step (D-06).

### Downstream-Phase Coupling
- Phase 84 plan will consume `script_provenance` and the version-probe smoke step. CONTEXT.md decisions D-04, D-06, D-07 are the explicit contract Phase 84 builds against (DEPLOY-02 + DEPLOY-04).

### Prior-Phase Context (for pattern continuity)
- `.planning/phases/66-p0-deployment-hotfixes/66-CONTEXT.md` — Original `/api/version` design (Phase 66 created the endpoint).
- `.planning/phases/68-sanity-check-v2/68-CONTEXT.md` — Live-gate consumer pattern; Phase 79's smoke step uses the same warn-only-then-promote rhythm.

### External Conventions
- Railway docs: `RAILWAY_GIT_COMMIT_SHA`, `RAILWAY_DEPLOYMENT_ID`, `RAILWAY_GIT_COMMIT_TIMESTAMP` env vars (already in use; no new wiring).
- GitHub Actions: `${{ github.sha }}` is the just-pushed 40-char SHA used by deploy-web.yml.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/utils.py` — Lands `get_script_sha()` alongside existing helpers (`download_latest_parquet`, `get_latest_s3_key`). Same module style; imports follow project convention.
- `web/api/main.py` `version_info()` — Already wired; modifications are additive (drop truncation, add `llm_enrichment_ready`). No new route needed.
- `.github/workflows/deploy-web.yml` — Already runs after Railway redeploy; smoke step appends here, no new workflow file.

### Established Patterns
- **Audit JSON schema**: each script writes a top-level metadata block (timestamp, target_url, gate values). `script_provenance: {sha, dirty, resolved_at}` slots in alongside.
- **Subprocess for git**: `python_name_resolver.py` and other scripts use `subprocess.run(["git", ...], capture_output=True)` — mirror this style in `get_script_sha`.
- **Warn-only first, promote later**: Phase 68's live-gate pattern — ship the probe warn-only, prove it stable, then a follow-on phase flips the gate. D-07 follows this rhythm.

### Integration Points
- Audit JSON output → Phase 84 DEPLOY-04 consumer (must read `script_provenance.sha`).
- `/api/version` response → Phase 84 DEPLOY-02 fingerprint probe (must read `git_sha` and `deployed_at`).
- CI smoke step → Phase 84 promotes existing job to fail-on-mismatch.

</code_context>

<specifics>
## Specific Ideas

- **`script_dirty` is the forensics tightener** that turns "audit was run from main" into "audit was run from clean main". The `git diff HEAD -- {path}` check is what gives Phase 84 the leverage to reject "I ran it from my feature branch" evidence.
- **5-minute polling budget** comes from Railway's observed p95 redeploy time during v7.0 hotfixes (Phase 66). Tail-latency cases beyond that are real freezes (the v7.1 silent-freeze incident sat at ∞).
- **Full SHA over truncated** is specifically because the v7.1 silent freeze wasn't a SHA-collision problem — it was a route-staleness problem. Full SHA gives Phase 84 the cleanest equality semantics.

</specifics>

<deferred>
## Deferred Ideas

- **Stamp historical v7.1 audit JSONs in place** — considered, rejected (D-08). Could revisit in v7.3 if forensic gap proves problematic.
- **Future audit-script onboarding doc** — a `scripts/AUDIT_CONVENTIONS.md` describing the `get_script_sha()` import + `script_provenance` JSON schema. Not required by DQ-01; planner can include as nice-to-have or push to a docs follow-up.
- **Per-route diagnostic flags evolution** — Phase 79 keeps the existing two flags. As more routes need stale-detection, a generic `routes: {name: bool}` map could replace ad-hoc fields. Out of scope here; raise during a future deploy-hardening cycle.
- **Vercel-side version probe** — DQ-02 covers Railway only. A symmetric Vercel `/api/version` (or build-manifest probe) would close the asymmetry-detection loop completely. Currently parked behind Phase 84 DEPLOY-02 (chunk-fingerprint approach).

### Reviewed Todos (not folded)

None — phase scope already matches DQ-01 + DQ-02 exactly.

</deferred>

---

*Phase: 79-audit-provenance-version-probe*
*Context gathered: 2026-04-27*
