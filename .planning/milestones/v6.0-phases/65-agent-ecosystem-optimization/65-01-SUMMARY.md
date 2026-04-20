---
phase: 65-agent-ecosystem-optimization
plan: 01
subsystem: meta-tooling
tags: [agents, skills, inventory, triage, consolidation-input]

requires: []
provides:
  - "Ground-truth inventory of every agent in .claude/agents/ with triage tag (ACTIVE/FRAMEWORK-OWNED/DORMANT/REDUNDANT)"
  - "Ground-truth inventory of every skill in .claude/skills/ with triage tag (DATA-OWNED/DESIGN-HOLISTIC/DESIGN-TARGETED/DOC-SPECIALIST/FRAMEWORK)"
  - "Identified 5-skill design-holistic overlap cluster for 65-02 consolidation"
  - "Pairwise overlap evidence for the 10 skill pairs in the cluster"
  - "Two consolidation options (umbrella-with-modes vs shared-rules-include) framed for 65-02 checkpoint"
affects:
  - 65-02-PLAN.md (design consolidation — consumes SKILL-INVENTORY.md cluster definition)
  - 65-03-PLAN.md (NFL rules consolidation — references DATA-OWNED skill list)
  - 65-04-PLAN.md (skill-optimizer audit — references AGENT-INVENTORY.md to scope framework-owned vs project-owned)

tech-stack:
  added: []
  patterns:
    - "Read-only inventory: no agent or skill files modified"
    - "Triage-tag discipline: every file gets exactly one tag from a closed set"

key-files:
  created:
    - .planning/phases/65-agent-ecosystem-optimization/AGENT-INVENTORY.md
    - .planning/phases/65-agent-ecosystem-optimization/SKILL-INVENTORY.md
  modified: []

key-decisions:
  - "All 11 project-owned agents are ACTIVE per CLAUDE.md — no DORMANT/REDUNDANT tags needed this round"
  - "code-reviewer vs git-code-reviewer near-redundancy flagged for 65-04 audit but kept ACTIVE (division of labour: opus pre-commit vs sonnet post-push)"
  - "5-skill DESIGN-HOLISTIC cluster confirmed as plan hypothesis: impeccable, taste-skill, soft-skill, emil-design-eng, redesign-skill"
  - "minimalist-skill kept DESIGN-TARGETED per plan rubric despite structural similarity to the 5 — flagged as 65-02 optional fold candidate"
  - "Option A (impeccable umbrella with mode flags) preferred over Option B (shared-rules include) — final choice deferred to 65-02 checkpoint"

patterns-established:
  - "Inventory provenance: CLAUDE.md Agent-Skill Architecture table is the single source of truth for ACTIVE tags"
  - "Framework ownership heuristic: filename prefix gsd-* = FRAMEWORK-OWNED, not subject to archive decisions"
  - "Overlap evidence format: pairwise table with one concrete shared directive per pair"

requirements-completed: [AGNT-02]

duration: 12min
completed: 2026-04-17
---

# Phase 65 Plan 01: Agent & Skill Inventory Summary

**Triage inventory of 42 agents (11 ACTIVE / 31 FRAMEWORK-OWNED) and 29 skills (12 DATA-OWNED / 5 DESIGN-HOLISTIC cluster / 9 DESIGN-TARGETED / 2 DOC-SPECIALIST / 1 FRAMEWORK), with pairwise overlap evidence for the 5-skill consolidation cluster.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 of 2 complete
- **Files created:** 2 (AGENT-INVENTORY.md, SKILL-INVENTORY.md)
- **Files modified:** 0 (read-only plan, no agent or skill files touched)

## Accomplishments

- **AGENT-INVENTORY.md**: triage table for all 42 agents. All 11 project-owned agents ACTIVE; all 31 gsd-* agents FRAMEWORK-OWNED; zero DORMANT, zero REDUNDANT.
- **SKILL-INVENTORY.md**: triage table for all 29 skills, with 5 explicitly named as the `design-holistic-cluster` and 10 pairwise-overlap rows documenting why they belong together.
- **Two consolidation options framed** for plan 65-02's checkpoint decision: umbrella-with-modes vs shared-rules-include.

## Task Commits

1. **Task 1: AGENT-INVENTORY.md** — `919fd31` (docs)
2. **Task 2: SKILL-INVENTORY.md** — `1d5369c` (docs)

## Files Created/Modified

- `.planning/phases/65-agent-ecosystem-optimization/AGENT-INVENTORY.md` — 42-agent triage table, near-redundancy notes, cross-reference to CLAUDE.md
- `.planning/phases/65-agent-ecosystem-optimization/SKILL-INVENTORY.md` — 29-skill triage table, 5-skill cluster analysis with pairwise overlap evidence, consolidation option sketches

## Decisions Made

- **No archive recommendations in this plan.** Every project-owned agent is already ACTIVE in CLAUDE.md; no DORMANT candidates surfaced. This is the expected outcome given the agent-skill map was recently refreshed.
- **Held to the plan's explicit categorization** for minimalist-skill as DESIGN-TARGETED even though its content style matches the holistic cluster. The plan author's judgment that minimalist is a "style variant" not a "full generator" is preserved; 65-02 may revisit.
- **Option A (umbrella with modes) recommended** as the consolidation target, but flagged as a 65-02 checkpoint rather than a prescriptive conclusion. Rationale: `critique` already references `npx impeccable *`, so `impeccable` is already treated as the hub.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated agent count from 41 to 42**
- **Found during:** Task 1 enumeration
- **Issue:** Plan expected 41 agents (11 + 30). Actual directory count is 42 (11 + 31) — `gsd-intel-updater.md` is present and was added by a recent `npx get-shit-done-cc@latest` update.
- **Fix:** Ran the triage with actual count 42. Updated the Summary counts and verification thresholds accordingly. The plan's automated check (`>=42 pipe-prefixed lines`) happens to accommodate this perfectly.
- **Files modified:** AGENT-INVENTORY.md (Summary + Triage Table reflect 42)
- **Verification:** `grep -c "^|" AGENT-INVENTORY.md` returned 50 lines, well above the 42 threshold.
- **Committed in:** 919fd31

**2. [Rule 3 - Blocking] Updated skill count from 25 to 29**
- **Found during:** Task 2 enumeration
- **Issue:** Plan expected 25 skills. Actual directory count is 29. The four extras (`graph`, `health-check`, `refresh`, `sentiment`) are all DATA-OWNED skills already listed in CLAUDE.md as owned by `data-engineer`. The plan's Summary template showed `DATA-OWNED: 8`, but the correct data-owned count given all NFL data skills is 12 (the 8 in the template + `graph`, `health-check`, `refresh`, `sentiment`).
- **Fix:** Ran the triage with actual count 29 and set `DATA-OWNED: 12`. The DESIGN-HOLISTIC cluster is still exactly 5, which is what the verification check keys on.
- **Files modified:** SKILL-INVENTORY.md (Summary + Triage Table reflect 29 total, 12 DATA-OWNED)
- **Verification:** `grep -c "design-holistic-cluster" SKILL-INVENTORY.md` returned 6, above the 5 threshold.
- **Committed in:** 1d5369c

---

**Total deviations:** 2 auto-fixed (both Rule 3 — reality-driven count updates)
**Impact on plan:** No scope creep. Counts diverged from plan's preamble only because the agent/skill directories changed after the plan was written. Downstream plans receive accurate counts.

## Issues Encountered

None. The plan was precisely specified and read-only, and both tasks ran without blockers.

## Key Findings for Downstream Plans

### For plan 65-02 (design consolidation)

- **5-skill cluster confirmed as plan hypothesis:** `impeccable`, `taste-skill`, `soft-skill`, `emil-design-eng`, `redesign-skill`.
- **Pairwise overlap evidence captured in SKILL-INVENTORY.md** — 10 pairs, one concrete shared directive per pair, covering: banned fonts (Inter/Roboto/Open Sans), banned AI-purple gradients, GPU-safe motion rules (transform/opacity), viewport stability (min-h-[100dvh]), interactive state requirements, skeletal loaders over spinners.
- **Two consolidation options framed:**
  - **Option A (preferred):** Umbrella `impeccable` with mode flags (`craft` | `upgrade` | `tune` | `review` | `teach` | `extract`). Net skill count 29 → 25. Archive soft-skill, redesign-skill, taste-skill, emil-design-eng with DEPRECATED.md stubs.
  - **Option B:** Keep all 5 files but dedupe via shared-rules include. No file reduction but ~60% content reduction.
- **Optional 6th fold candidate:** `minimalist-skill` can be absorbed as `/impeccable craft --archetype minimalist-editorial` if Option A is taken.

### For plan 65-03 (NFL rules consolidation)

- **12 DATA-OWNED skills** are all cohesive and trigger-disjoint. No consolidation candidates. Per-skill eval coverage remains the 65-04 concern.

### For plan 65-04 (skill-optimizer audit)

- **Zero project-owned agents to archive.** All 11 ACTIVE in CLAUDE.md.
- **One near-redundancy to score:** `code-reviewer` (opus) vs `git-code-reviewer` (sonnet). Both are ACTIVE, division of labour is intentional (pre-commit vs post-push), but both prompts should be audited for scope creep into each other's territory.
- **31 FRAMEWORK-OWNED agents** are in-scope for quality scoring (trigger accuracy, prompt hygiene) but out-of-scope for archive decisions (managed by `npx get-shit-done-cc@latest`).

## Self-Check: PASSED

**Artifacts verified:**
- `.planning/phases/65-agent-ecosystem-optimization/AGENT-INVENTORY.md` — FOUND (50 pipe-prefixed lines >= 42 threshold)
- `.planning/phases/65-agent-ecosystem-optimization/SKILL-INVENTORY.md` — FOUND (6 design-holistic-cluster refs >= 5 threshold)

**Commits verified:**
- `919fd31` (AGENT-INVENTORY commit) — FOUND in git log
- `1d5369c` (SKILL-INVENTORY commit) — FOUND in git log

## Next Phase Readiness

- **65-02 (design consolidation) is unblocked.** It can open SKILL-INVENTORY.md, see the 5 cluster skills with pairwise evidence, and start its checkpoint discussion on Option A vs Option B without re-analyzing.
- **65-03 (NFL rules) is unblocked.** The 12 DATA-OWNED skill list is clean.
- **65-04 (skill-optimizer audit) is unblocked.** It has a clear scope map: 11 project-owned agents (in-scope for archive + scoring) vs 31 framework-owned (in-scope for scoring only).

---
*Phase: 65-agent-ecosystem-optimization*
*Completed: 2026-04-17*
