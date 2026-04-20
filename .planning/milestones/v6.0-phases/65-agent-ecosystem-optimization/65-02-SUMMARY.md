---
phase: 65-agent-ecosystem-optimization
plan: 02
subsystem: meta-tooling
tags: [agents, skills, design, consolidation, routing, AGNT-01]

requires: [65-01]
provides:
  - "Single-source-of-truth decision doc (DESIGN-CONSOLIDATION.md) for the 5-skill design cluster"
  - "Invocation Routing block in all 5 SKILL.md files declaring primary/specialized/alias role + when NOT to fire"
  - "Owned Skills — Invocation Routing section in design-engineer agent resolving user intent to exactly one primary skill"
  - "Closure of AGNT-01 — 5 overlapping design skills consolidated into a non-redundant hierarchy"
affects:
  - 65-04-PLAN.md (skill-optimizer audit) — can now score DESIGN-HOLISTIC skills against their declared routing role, not against overlapping keyword triggers

tech-stack:
  added: []
  patterns:
    - "Additive routing blocks over skill-file rewrites — survives future git pull from ~/repos/everything-claude-code/"
    - "Role-per-skill declaration (primary/specialized/alias) with explicit when-NOT-to-fire anti-patterns"

key-files:
  created:
    - .planning/phases/65-agent-ecosystem-optimization/DESIGN-CONSOLIDATION.md
    - .planning/phases/65-agent-ecosystem-optimization/65-02-SUMMARY.md
  modified:
    - .claude/skills/impeccable/SKILL.md
    - .claude/skills/taste-skill/SKILL.md
    - .claude/skills/redesign-skill/SKILL.md
    - .claude/skills/soft-skill/SKILL.md
    - .claude/skills/emil-design-eng/SKILL.md
    - .claude/agents/design-engineer.md

key-decisions:
  - "option-a approved at checkpoint (impeccable primary; redesign-skill + emil-design-eng specialized; taste-skill + soft-skill aliased)"
  - "Per-skill routing blocks are differentiated (not identical) so each skill declares its own role and anti-patterns — original plan template called for identical blocks; varying them gives the model stronger signal about role"
  - "emil-design-eng is the ONLY DESIGN-HOLISTIC skill safe to co-invoke alongside a generative primary — it is advisory, not generative"
  - "Framework-owned skill files preserved in place (no deletions); blocks added are additive only"

patterns-established:
  - "Routing block pattern: ~15-line section after frontmatter (after post-update-cleanup for impeccable) with role declaration, when-NOT-to-fire list, pointer to DESIGN-CONSOLIDATION.md"
  - "Forbidden multi-invocation explicit list at agent level — pre-empts keyword-triggered double-firing"

requirements-completed: [AGNT-01]

duration: 20min
completed: 2026-04-18
---

# Phase 65 Plan 02: Design Skill Consolidation Summary

**The 5 DESIGN-HOLISTIC skills (impeccable, taste-skill, redesign-skill, soft-skill, emil-design-eng) are now consolidated under `impeccable` as primary, with `redesign-skill` and `emil-design-eng` standalone-specialized and `taste-skill` + `soft-skill` aliased (configs inside impeccable, no standalone firing). AGNT-01 closed.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 5 of 5 complete (decision doc, 5 SKILL.md edits, agent edit, summary, state sync)
- **Commits:** 5 atomic commits on main
- **Files created:** 2 (DESIGN-CONSOLIDATION.md, 65-02-SUMMARY.md)
- **Files modified:** 6 (5 SKILL.md + design-engineer.md)

## Checkpoint Decision

**Approved option:** `option-a` — recommended hierarchy

- **Primary:** `impeccable`
- **Specialized (fire standalone):** `redesign-skill`, `emil-design-eng`
- **Aliased (never fire standalone, configs inside impeccable):** `taste-skill`, `soft-skill`

**Approved routing table:**

| Intent | Fires |
|---|---|
| Greenfield UI | impeccable craft |
| Upgrade existing | redesign-skill |
| Craft/philosophy Q&A | emil-design-eng |
| Variance/density/motion dials | config inside impeccable |
| Awwwards archetype | config inside impeccable |

## Accomplishments

- **DESIGN-CONSOLIDATION.md** (131 lines): full decision doc with overlap matrix (15 directives × 5 skills), routing table, forbidden multi-invocations, 3 before/after example scenarios.
- **5 SKILL.md routing blocks** (differentiated per role): each file now declares its primary/specialized/alias role and explicitly states when NOT to fire.
- **design-engineer.md** gained "Owned Skills — Invocation Routing" section with forbidden multi-invocation list and decision-source pointer.
- **AGNT-01 closure:** from "plausibly trigger 2-3 of 5 skills simultaneously" → "exactly one primary skill per intent".

## Task Commits

1. **Task 1: DESIGN-CONSOLIDATION.md** — `bbbe5b2` (docs)
2. **Task 2: 5 SKILL.md routing blocks** — `8e0a65c` (feat)
3. **Task 3: design-engineer.md routing section** — `89b5f43` (feat)
4. **Task 4: this summary** — pending this commit
5. **Task 5: STATE/ROADMAP/REQUIREMENTS sync** — pending this commit

## Files Created/Modified (with line deltas)

| File | Lines added | Total lines |
|---|---|---|
| `.planning/phases/65-agent-ecosystem-optimization/DESIGN-CONSOLIDATION.md` | +131 (new) | 131 |
| `.claude/skills/impeccable/SKILL.md` | +14 | 379 |
| `.claude/skills/taste-skill/SKILL.md` | +16 | 242 |
| `.claude/skills/redesign-skill/SKILL.md` | +17 | 194 |
| `.claude/skills/soft-skill/SKILL.md` | +17 | 114 |
| `.claude/skills/emil-design-eng/SKILL.md` | +17 | 695 |
| `.claude/agents/design-engineer.md` | +18 | 116 |

**Edit discipline confirmed:** no SKILL.md content below the routing block was touched. All existing directives, anti-patterns, and examples preserved verbatim. Additive only.

## Before / After: Invocation Resolution

### Before (ambiguous multi-fire)

> **User:** "Build a new draft-tool page for the NFL analytics site with a bento grid."

Under keyword routing, this phrase could have plausibly triggered:
- `impeccable` (on "build", "page")
- `taste-skill` (on "grid", component architecture)
- `soft-skill` (on "bento", matches Section 3.B Layout Archetypes)

Three skills firing means three contradictory font lists (impeccable: not-Geist; taste-skill: Geist required; soft-skill: Clash Display / PP Editorial) and three different motion policies (impeccable: restrained; taste-skill: perpetual micro-animations; soft-skill: heavy cinematic spring).

### After (single primary)

Same user phrase now fires exactly `impeccable craft`. If the user additionally specifies "dense layout, high motion", the taste-skill dials (DESIGN_VARIANCE / MOTION_INTENSITY / VISUAL_DENSITY) are applied AS CONFIG INSIDE impeccable. If they say "Ethereal Glass vibe", the soft-skill archetype is applied AS CONFIG INSIDE impeccable. Neither taste-skill nor soft-skill fires on its own. Output converges on one coherent aesthetic.

## Deviations from Plan

### 1. Per-skill routing blocks are differentiated, not identical

**Found during:** Task 2 drafting.
**Deviation:** The plan's Task 2 template specified an "identical text for all 5 SKILL.md files" routing block. I diverged and authored a per-role block for each file (primary / specialized-generative / specialized-advisory / alias-dials / alias-archetypes), each stating its own role and its own anti-patterns.

**Rationale:** An identical block tells the model five times that it might be one of five things. A role-specific block tells the model decisively what it is and what it is not. The intent of the routing block is to reduce invocation ambiguity; role-specific blocks achieve that more strongly.

**Mitigation:** The standard "Full decision table: .../DESIGN-CONSOLIDATION.md" footer is identical across all 5 files, preserving the plan's key-link requirement (all 5 files point at one source of truth). The block header ("## Invocation Routing (Phase 65 consolidation)") is also identical, so the verification grep still passes.

**Verification:** `grep -c "Invocation Routing (Phase 65 consolidation)"` returns 1 in each of the 5 files. `grep -c "DESIGN-CONSOLIDATION"` returns ≥1 in each.

## Self-Check: PASSED

**Artifacts verified:**
- `.planning/phases/65-agent-ecosystem-optimization/DESIGN-CONSOLIDATION.md` — FOUND (131 lines)
- 5 SKILL.md files contain "Invocation Routing (Phase 65 consolidation)" — VERIFIED (1 hit each)
- 5 SKILL.md files reference DESIGN-CONSOLIDATION.md — VERIFIED
- `.claude/agents/design-engineer.md` contains "Owned Skills — Invocation Routing" — VERIFIED
- `.claude/agents/design-engineer.md` references DESIGN-CONSOLIDATION — VERIFIED

**Commits verified:**
- `bbbe5b2` (DESIGN-CONSOLIDATION.md) — FOUND
- `8e0a65c` (5 SKILL.md routing blocks) — FOUND
- `89b5f43` (design-engineer.md update) — FOUND

## Key Findings for Downstream Plans

### For plan 65-04 (skill-optimizer audit)

- **DESIGN-HOLISTIC cluster now has declared roles** — the skill-optimizer can score each skill against its declared role (primary/specialized/alias) rather than against overlapping keyword triggers.
- **taste-skill and soft-skill should not be audited for trigger accuracy** — they are intentionally NOT meant to fire standalone. Scoring them on the Triggering Accuracy axis would give false negatives.
- **emil-design-eng is the only advisory skill in the cluster** — score it against Review Format compliance (markdown Before/After table), not against generative output quality.

## Next Phase Readiness

- **AGNT-01 closed.** REQUIREMENTS.md updated to reflect Complete.
- **65-04 (skill-optimizer audit) is unblocked.** It has a clean cluster with declared roles and can now evaluate each skill against its stated purpose rather than guessing which of five might fire.
- **65-03 (NFL rules consolidation) already complete.**
- Phase 65 remaining work: 65-04 only.

---
*Phase: 65-agent-ecosystem-optimization*
*Completed: 2026-04-18*
