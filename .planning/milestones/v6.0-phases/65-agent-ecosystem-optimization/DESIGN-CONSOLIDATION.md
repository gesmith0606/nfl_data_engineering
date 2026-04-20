---
phase: 65-agent-ecosystem-optimization
plan: 02
type: decision
tags: [design, skills, consolidation, routing, AGNT-01]

decision_date: 2026-04-18
approved_option: option-a
primary_skill: impeccable
---

# Design Skill Consolidation Decision

**The 5 DESIGN-HOLISTIC skills are consolidated under `impeccable` as the primary entry point. `redesign-skill` and `emil-design-eng` retain standalone invocation for specialized intents; `taste-skill` and `soft-skill` become config-only (aliases inside impeccable) and must not fire standalone.**

## Decision

From the checkpoint in `65-02-PLAN.md`, **option-a** was approved:

- **Primary:** `impeccable` — canonical entry point for greenfield UI work
- **Specialized (fire standalone):** `redesign-skill`, `emil-design-eng`
- **Aliased (do NOT fire standalone — configs inside impeccable):** `taste-skill`, `soft-skill`

Rationale:
1. `impeccable` already has the Context Gathering Protocol, the `polish` skill treats it as a mandatory prerequisite, and `critique` references `npx impeccable *` — it is already the hub in practice.
2. `redesign-skill` has the clearest use-case boundary ("existing code"), which makes it a trivially correct specialization.
3. `emil-design-eng` is advisory (philosophy / code review), not generative — it shouldn't be forced through the same router as builders.
4. `taste-skill` and `soft-skill` overlap heavily with impeccable on the greenfield-build use case but contribute unique config dimensions (metric dials, archetype selection). Keeping them as internal configs preserves the unique value without triggering redundant multi-skill invocations.

Per CONSTRAINT in the plan: all 5 SKILL.md files remain on disk (no deletions). Each gets a minimal additive routing block. This survives future `git pull` updates from `~/repos/everything-claude-code/`.

## Overlap Matrix (from 65-01 SKILL-INVENTORY.md)

The 5 skills share these core directives (pairwise evidence compiled in 65-01):

| Directive | impeccable | taste-skill | redesign-skill | soft-skill | emil-design-eng |
|---|---|---|---|---|---|
| Ban Inter / Roboto / Open Sans as default body fonts | Y | Y | Y | Y | — |
| Ban purple/blue "AI gradient" aesthetic | Y | Y | Y | Y | — |
| GPU-safe motion (transform/opacity only, never width/height) | Y | Y | Y | Y | Y |
| Viewport stability (`min-h-[100dvh]`, not `h-screen`) | Y | Y | Y | Y | — |
| Interactive state requirements (loading/empty/error) | Y | Y | Y | Y | — |
| Skeletal loaders over circular spinners | Y | Y | Y | Y | — |
| Scale-on-press (`scale(0.97)`) for button feedback | — | Y | — | Y | Y |
| Custom cubic-bezier easing (never `linear` or `ease-in-out`) | — | Y | — | Y | Y |
| Spring physics for interactive motion | Y | Y | — | Y | Y |
| Nested / "double-bezel" card architecture | — | — | — | Y | — |
| Metric dials (DESIGN_VARIANCE, MOTION_INTENSITY, VISUAL_DENSITY) | — | Y | — | — | — |
| Awwwards archetype selector (vibe + texture + layout combos) | — | — | — | Y | — |
| Context gathering protocol (`.impeccable.md`) | Y | — | — | — | — |
| Upgrades existing code (non-greenfield) | — | — | Y | — | — |
| Animation decision framework (frequency → animate-or-not) | — | — | — | — | Y |

**Where they contradict:** banned-font lists diverge (soft-skill bans Helvetica, impeccable bans Geist-family, taste-skill REQUIRES Geist); motion philosophy differs (emil says "never animate keyboard actions", taste-skill mandates perpetual micro-animations when `MOTION_INTENSITY > 5`). Running more than one on the same task produces contradictory output. That is the exact failure this consolidation resolves.

## Routing Table

| User Intent | Fires | Why |
|---|---|---|
| "Build a new page / component / dashboard" (greenfield) | `impeccable craft` | Primary. Includes Context Gathering Protocol. |
| "Redesign / upgrade / fix / audit existing UI" | `redesign-existing-projects` | Only one with an explicit existing-code audit workflow. |
| "Why does X feel right?" / "Review this animation" / craft philosophy Q&A | `emil-design-eng` | Advisory skill; outputs markdown Before/After tables, not code. |
| "I need variance/density/motion dialed to N" | config inside `impeccable` (taste-skill dials) | taste-skill dials (8/6/4 default) fold in as a config block — do not fire taste-skill standalone. |
| "Give me an Awwwards archetype" / "Ethereal Glass vibe" / "Editorial Luxury" | config inside `impeccable` (soft-skill archetypes) | soft-skill archetype selector folds in as a mode — do not fire soft-skill standalone. |
| "Setup design context for this project" | `impeccable teach` | Teach mode writes `.impeccable.md`. |
| "Extract reusable tokens into design system" | `impeccable extract` | Extract mode. |

### Forbidden multi-invocations

Do **not** fire these in the same turn — they will produce contradictory output:

- `impeccable` + `taste-skill` (taste-skill is a config INSIDE impeccable)
- `impeccable` + `soft-skill` (soft-skill is a config INSIDE impeccable)
- `taste-skill` + `soft-skill` (different banned-font lists, different motion philosophy)
- `redesign-skill` + `impeccable` (redesign is for existing code; impeccable is for greenfield — pick one based on user intent)

### Allowed co-invocations

- `impeccable` + `emil-design-eng` — emil is advisory, not generative. Fine to pair (e.g., "build this AND review the animation choices against Emil's framework").
- Any primary + one of the 9 DESIGN-TARGETED skills (polish, animate, layout, colorize, typeset, bolder, audit, critique, minimalist-skill) — these are scoped (not holistic) and do not overlap with the primary.

## Example Scenarios

### Scenario 1: Greenfield dashboard page

> **User:** "Build a new draft-tool page for the NFL analytics site with a bento grid of projection cards."

**Resolution:**
1. Task is greenfield UI → fires `impeccable craft`
2. If user says "make it dense" or "high motion", the taste-skill dials (DESIGN_VARIANCE/MOTION_INTENSITY/VISUAL_DENSITY) are applied AS CONFIG INSIDE impeccable. taste-skill SKILL.md is NOT invoked standalone.
3. If user says "Ethereal Glass vibe", the soft-skill Vibe Archetype "Ethereal Glass (SaaS / AI / Tech)" is applied AS CONFIG INSIDE impeccable. soft-skill SKILL.md is NOT invoked standalone.

**Before consolidation:** impeccable + taste-skill + soft-skill could all trigger on keywords, producing conflicting font choices (Geist vs. not-Geist vs. Clash Display) and conflicting motion intensity.
**After consolidation:** exactly one skill fires; the dials and archetypes are parameters on that skill's output, not separate skills.

### Scenario 2: Upgrade the existing lineup-builder page

> **User:** "The /lineups page works but it looks generic. Redesign it."

**Resolution:**
1. Task is "existing code" → fires `redesign-existing-projects` alone
2. `impeccable` does NOT fire because there is no greenfield build.
3. `taste-skill` does NOT fire because its dials are for generating new output, not auditing existing.

**Before consolidation:** user saying "redesign the lineups page" could plausibly trigger redesign-skill + impeccable + taste-skill (each keyword-matched on "design"), producing contradictory upgrade plans.
**After consolidation:** redesign-skill owns this use case. Done.

### Scenario 3: Animation philosophy question

> **User:** "Is it OK to animate the command palette open/close with ease-in?"

**Resolution:**
1. Advisory question → fires `emil-design-eng` alone
2. `impeccable` does NOT fire (no UI to build).
3. Returns a markdown Before/After table per emil-design-eng's required format. Cites the Animation Decision Framework: command palette is used 100+ times/day → no animation, regardless of easing.

**Before consolidation:** the word "animate" could have triggered impeccable + taste-skill + emil. Now emil-design-eng is the single correct answer for advisory questions.

## Implementation

Each of the 5 SKILL.md files receives an identical ~15-line "Invocation Routing (Phase 65 consolidation)" block immediately after the YAML frontmatter. For `impeccable/SKILL.md`, the block is placed AFTER the `<post-update-cleanup>` section (cleanup must run first on upgrade).

The `.claude/agents/design-engineer.md` file gets a short "Owned Skills — Invocation Routing" section that resolves user intent to exactly one primary skill.

## Source References

- `.planning/phases/65-agent-ecosystem-optimization/SKILL-INVENTORY.md` — pairwise overlap evidence
- `.planning/phases/65-agent-ecosystem-optimization/65-01-SUMMARY.md` — cluster identification
- `.planning/phases/65-agent-ecosystem-optimization/65-02-PLAN.md` — plan with checkpoint
- `.claude/skills/{impeccable,taste-skill,redesign-skill,soft-skill,emil-design-eng}/SKILL.md` — target files
- `.claude/agents/design-engineer.md` — agent with routing section
