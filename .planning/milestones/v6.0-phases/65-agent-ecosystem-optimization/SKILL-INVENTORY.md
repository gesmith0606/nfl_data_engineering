# Skill Inventory — Phase 65

**Generated:** 2026-04-17
**Total skills enumerated:** 29 directories under `.claude/skills/`

> Deviation note: the plan expected 25 skills. Actual directory count is 29. The four extras
> (`graph`, `health-check`, `refresh`, `sentiment`) are all data-owned skills that the
> `data-engineer` agent already owns per CLAUDE.md and are handled under the DATA-OWNED bucket.
> The design-skill cluster, doc-specialist skills, and skill-creator counts all match the plan.

## Summary

- DATA-OWNED: 12
- DESIGN-HOLISTIC: 5 (consolidation target for 65-02)
- DESIGN-TARGETED: 9
- DOC-SPECIALIST: 2
- FRAMEWORK: 1
- TOTAL: 29

## Triage Table

| Skill | Category | Overlap Group | Description (one line) |
|-------|----------|---------------|------------------------|
| backtest | DATA-OWNED | owned-by-nfl | Run fantasy projection or game prediction backtests to evaluate model accuracy |
| draft-prep | DATA-OWNED | owned-by-nfl | Preseason fantasy draft workflow (projections + ADP + interactive assistant) |
| graph | DATA-OWNED | owned-by-nfl | Compute graph-based player features from PBP participation, optional Neo4j load |
| health-check | DATA-OWNED | owned-by-nfl | Check Bronze/Silver/Gold pipeline freshness and data quality |
| ingest | DATA-OWNED | owned-by-nfl | Bronze S3 ingestion for all 16 NFL data types + odds + college + Sleeper |
| model-training | DATA-OWNED | owned-by-nfl | Train XGBoost/ensemble/residual/Bayesian/quantile models |
| prediction-pipeline | DATA-OWNED | owned-by-nfl | Generate weekly game predictions with edge detection vs Vegas |
| refresh | DATA-OWNED | owned-by-nfl | Refresh ADP, rosters, and external rankings from live sources |
| sentiment | DATA-OWNED | owned-by-nfl | RSS + Sleeper ingest → Claude extraction → weekly sentiment aggregation |
| test | DATA-OWNED | owned-by-nfl | Run the NFL data engineering pytest suite with coverage |
| validate-data | DATA-OWNED | owned-by-nfl | Validate NFL data against business rules across pipeline layers |
| weekly-pipeline | DATA-OWNED | owned-by-nfl | Full in-season Bronze→Silver→Gold chain for a given week |
| emil-design-eng | DESIGN-HOLISTIC | design-holistic-cluster | Emil Kowalski's craft philosophy: taste-trained, unseen-details-compound UI |
| impeccable | DESIGN-HOLISTIC | design-holistic-cluster | Distinctive production-grade frontend (craft/teach/extract) that avoids AI slop |
| redesign-skill | DESIGN-HOLISTIC | design-holistic-cluster | Audit + upgrade existing sites to premium quality via generic-pattern detection |
| soft-skill | DESIGN-HOLISTIC | design-holistic-cluster | $150k agency-tier "Awwwards" generator with Variance Engine + archetype selection |
| taste-skill | DESIGN-HOLISTIC | design-holistic-cluster | High-agency frontend with metric dials (variance/motion/density) + deterministic rules |
| animate | DESIGN-TARGETED | standalone | Add purposeful micro-interactions and motion effects to an existing feature |
| audit | DESIGN-TARGETED | standalone | Accessibility/performance/responsive quality report with P0-P3 severity |
| bolder | DESIGN-TARGETED | standalone | Amplify safe or boring designs for more visual impact and personality |
| colorize | DESIGN-TARGETED | standalone | Introduce strategic color to monochromatic or dull interfaces |
| critique | DESIGN-TARGETED | standalone | UX critique with scoring, persona testing, and anti-pattern detection |
| layout | DESIGN-TARGETED | standalone | Improve layout, spacing, and visual rhythm for weak compositions |
| minimalist-skill | DESIGN-TARGETED | standalone | Editorial-style warm monochrome, bento grid, typographic minimalism |
| polish | DESIGN-TARGETED | standalone | Final pre-ship quality pass for alignment, spacing, consistency |
| typeset | DESIGN-TARGETED | standalone | Fix typography choices, hierarchy, sizing, weight, and readability |
| fireworks-tech-graph | DOC-SPECIALIST | standalone | Create technical diagrams (architecture, data flow, flowchart) as SVG+PNG |
| notebooklm | DOC-SPECIALIST | standalone | Generate NFL content packages for Google NotebookLM audio overviews |
| skill-creator | FRAMEWORK | standalone | Create/modify skills, run evals, benchmark performance, optimize triggering |

## Design Holistic Cluster — Overlap Analysis

The 5 skills tagged `design-holistic-cluster` are:

1. **impeccable** — primary entry point, has `craft`/`teach`/`extract` sub-commands, other design
   skills reference it (`critique` uses `npx impeccable *` in `allowed-tools`). Frontmatter
   description: "Create distinctive, production-grade frontend interfaces… avoids generic AI aesthetics."
2. **taste-skill** — frontmatter name is `design-taste-frontend`. Metric dials
   (`DESIGN_VARIANCE`/`MOTION_INTENSITY`/`VISUAL_DENSITY`) + deterministic "bias-correction" rules
   (banned fonts, color calibration, layout diversification, materiality, interactive states).
3. **soft-skill** — frontmatter name is `high-end-visual-design`. "$150k+ agency-level" Variance
   Engine + archetype selection (Ethereal Glass / Editorial Luxury / Soft Structuralism), Absolute
   Zero directive of anti-patterns.
4. **emil-design-eng** — Emil Kowalski's design-engineering philosophy: taste is trained, unseen
   details compound, animation decision framework, required Before/After review table format.
5. **redesign-skill** — frontmatter name is `redesign-existing-projects`. Same anti-generic-pattern
   rulebook but applied as a 3-step audit→diagnose→fix workflow for existing codebases.

### Shared concerns (every one of the 5)

- **Full-page/component generator scope.** Each skill produces or upgrades complete interfaces, not
  a single property like color or spacing.
- **Anti-AI-slop directive.** All 5 carry a "banned patterns" list that overlaps heavily:
  - Banned fonts: Inter / Roboto / Open Sans / Helvetica appear verbatim across `impeccable`,
    `taste-skill`, `soft-skill`, `minimalist-skill`, and `redesign-skill`. `emil-design-eng` does
    not ban fonts explicitly but covers the same ground via "taste" narrative.
  - Banned shadows/borders: generic `box-shadow` / thin-grey 1px borders called out in 4/5.
  - Banned "AI purple/blue gradient": explicit in `taste-skill` ("THE LILA BAN"), `soft-skill`
    ("Ethereal Glass" with considered mesh rather than default gradient), `impeccable` and
    `redesign-skill` call out "Purple/blue 'AI gradient' aesthetic" as the top fingerprint.
- **Typography stack recommendation convergence.** All 5 recommend `Geist` as a core alternative;
  `impeccable` and `soft-skill` add `Clash Display` / `PP Editorial New`; `redesign-skill` and
  `taste-skill` overlap on `Outfit` / `Cabinet Grotesk` / `Satoshi`.
- **GPU-safe motion rules.** All 5 tell the agent to animate `transform`/`opacity` only, never
  `top`/`left`/`width`/`height`.
- **Interactive state requirements.** All 5 require full state coverage (loading, empty, error,
  `:active`, focus ring) — the scale/translateY pressed-state is recommended identically in 4/5.
- **Responsiveness / viewport stability.** `min-h-[100dvh]` over `h-screen` appears verbatim in
  `impeccable`, `taste-skill`, `soft-skill`, `redesign-skill` (and `minimalist-skill`, which is
  kept DESIGN-TARGETED per plan but would be a 6th candidate).

### Pairwise overlap evidence (representative)

| Pair | Concrete shared directive |
|------|---------------------------|
| impeccable ↔ taste-skill | Both forbid Inter as default, both enforce `max-w-[1400px]`/`max-w-7xl` container width, both require skeletal loaders over spinners |
| impeccable ↔ soft-skill | Both warn against "AI purple/blue gradient" and require the designer to pick ONE aesthetic direction before coding (impeccable "Design Direction" = soft-skill "Variance Engine" roll) |
| impeccable ↔ redesign-skill | Both list "Generic names like John Doe", "Lorem Ipsum", "Title Case Everywhere", and "Symmetric vertical padding" as anti-patterns with near-identical wording |
| impeccable ↔ emil-design-eng | Both dedicate a section to animation "purpose" and reject `ease-in` on enter, `ease-out` on exit — same underlying motion philosophy |
| taste-skill ↔ soft-skill | Both define numbered "Rule" blocks for typography, color, layout, materiality, motion; both mandate `@phosphor-icons/react` as the icon library |
| taste-skill ↔ redesign-skill | Both give weighted recipes for pairing serif display + sans body, both require tabular-nums for data tables |
| soft-skill ↔ emil-design-eng | Both require purposeful motion (soft-skill "Magnetic Micro-physics" gated on `MOTION_INTENSITY > 5`; emil's "should this animate at all?" frequency table) — same intent, different framing |
| soft-skill ↔ redesign-skill | Both specify "backdrop-blur only on fixed/sticky elements" to avoid mobile GPU thrash |
| emil-design-eng ↔ redesign-skill | Both call out "inconsistent easing across an app" and require a single canonical curve (Emil names it; redesign-skill lists it under "Motion") |
| redesign-skill ↔ impeccable | Both describe the same `grid-template-columns` asymmetry upgrades to break "3 equal cards" AI monoculture |

Every pair shows at least one verbatim or near-verbatim shared rule. The five skills are
documenting the same underlying design philosophy from five different angles.

### Unique contributions each brings

| Skill | Unique contribution (not duplicated by the other 4) |
|-------|-----------------------------------------------------|
| impeccable | Project context-gathering protocol (`.impeccable.md`, `/impeccable teach`) and the `craft`/`teach`/`extract` command structure — this is the orchestration layer |
| taste-skill | Quantitative dials (VARIANCE / MOTION / DENSITY as 1-10) so the caller can bias output deterministically |
| soft-skill | Named archetype combinations ("Ethereal Glass" + "Asymmetrical Bento") and the Double-Bezel / Button-in-Button component recipes |
| emil-design-eng | Frequency-based animation decision framework (100+/day → no animation) and the Before/After markdown review-table format |
| redesign-skill | Codebase-first audit flow — scans existing framework (Tailwind/vanilla/styled-components) and patches in place rather than generating from scratch |

### Consolidation recommendation preview (feeds plan 65-02)

Two viable shapes — plan 65-02 should pick one at its checkpoint:

**Option A (umbrella with modes, preferred):** Keep `impeccable` as the single canonical entry point
and expose the other four as modes:
- `/impeccable craft` (default, green-field generation — absorbs `soft-skill`'s archetypes as a mode
  flag `/impeccable craft --archetype ethereal-glass`)
- `/impeccable upgrade` (brownfield audit — absorbs `redesign-skill`'s scan→diagnose→fix flow)
- `/impeccable tune` (parametric — absorbs `taste-skill`'s variance/motion/density dials)
- `/impeccable review` (absorbs `emil-design-eng`'s Before/After table format and animation decision
  framework)
- `/impeccable teach` / `/impeccable extract` (already exist)

Then archive `soft-skill`, `redesign-skill`, `taste-skill`, `emil-design-eng` directories (leave a
`DEPRECATED.md` stub pointing to `impeccable`). Net skill count: 29 → 25.

**Option B (alias with ownership):** Keep all 5 files but dedupe content. Move every shared rule
(banned fonts, motion rules, state requirements, viewport stability) into
`.claude/skills/impeccable/reference/shared-rules.md` and have the other 4 `@-include` it. Each
file shrinks to its unique contribution. No net file reduction but ~60% content reduction and
single source of truth.

Plan 65-02 should checkpoint on A-vs-B before execution.

## Notes for plan 65-02 (design consolidation)

- The 5 holistic skills currently live under `design-engineer` (14 owned skills). Consolidation
  drops that to 10-11 owned skills — still large, still cohesive.
- `minimalist-skill` is intentionally kept DESIGN-TARGETED per this plan's rubric, but its content
  style matches the holistic cluster. Plan 65-02 may decide to fold it into `impeccable` as
  `/impeccable craft --archetype minimalist-editorial` if Option A is taken.
- `critique` already references `npx impeccable *` in its `allowed-tools` — evidence that
  `impeccable` is already treated as the hub.

## Notes for plan 65-03 (NFL rules) and 65-04 (skill-optimizer audit)

- The 12 DATA-OWNED skills all have cohesive trigger phrases in their descriptions — they are not
  consolidation candidates. Plan 65-04 should audit them for eval coverage (`evals/evals.json`)
  per the maintenance checklist.
- `skill-creator` (FRAMEWORK) is owned by `skill-optimizer`. Plan 65-04 uses this skill to score
  every other skill's triggering accuracy.
- The 2 DOC-SPECIALIST skills are narrow and low-risk — no consolidation needed.
