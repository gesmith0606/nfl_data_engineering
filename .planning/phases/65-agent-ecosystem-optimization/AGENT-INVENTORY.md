# Agent Inventory — Phase 65

**Generated:** 2026-04-17
**Source of truth:** CLAUDE.md "Agent-Skill Architecture" table + `.claude/README.md` framework-ownership rule
**Total agents enumerated:** 42 (11 project-owned + 31 gsd-* framework-owned)

> Deviation note: the plan expected 41 agents (11 + 30). Actual directory count is 42 (11 + 31). The extra
> framework-owned agent is `gsd-intel-updater.md`, which must have been added by a recent
> `npx get-shit-done-cc@latest` update. All 31 `gsd-*` files share the framework-owned provenance and
> are triaged identically per the plan's FRAMEWORK-OWNED rule — no re-classification needed.

## Summary

- ACTIVE: 11
- FRAMEWORK-OWNED: 31
- DORMANT: 0
- REDUNDANT: 0
- TOTAL: 42

All 11 project-owned agents are present in CLAUDE.md's Agent-Skill Architecture table, so none are
tagged DORMANT. No two project-owned agents have identical owned-skill sets or overlapping
descriptions strong enough to warrant a REDUNDANT tag, so none are archived. (See the "Notes on
Near-Redundancy" section below for one borderline case — `code-reviewer` vs `git-code-reviewer` —
that is flagged for the Phase 65-04 quality audit but remains ACTIVE.)

## Triage Table

| Agent | Status | Default Model | Owned Skills | Recommendation |
|-------|--------|---------------|--------------|----------------|
| build-error-resolver | ACTIVE | sonnet | test | Keep as-is |
| code-reviewer | ACTIVE | opus | (built-in review logic) | Keep as-is — see near-redundancy note vs git-code-reviewer |
| data-engineer | ACTIVE | sonnet | ingest, validate-data, weekly-pipeline, backtest, model-training, prediction-pipeline, sentiment, graph, health-check, refresh | Keep as-is |
| data-modeler | ACTIVE | sonnet | (built-in data modeling) | Keep as-is |
| design-engineer | ACTIVE | opus | impeccable, taste-skill, polish, animate, layout, colorize, typeset, bolder, audit, critique, redesign-skill, soft-skill, emil-design-eng, minimalist-skill | Keep as-is — 14 owned skills; reduction pending plan 65-02 |
| devops-engineer | ACTIVE | sonnet | (built-in DevOps) | Keep as-is |
| docs-specialist | ACTIVE | sonnet | notebooklm, fireworks-tech-graph | Keep as-is |
| git-code-reviewer | ACTIVE | sonnet | (built-in, git-push triggered) | Keep as-is — see near-redundancy note vs code-reviewer |
| security-reviewer | ACTIVE | opus | (built-in security analysis) | Keep as-is |
| skill-optimizer | ACTIVE | opus | skill-creator | Keep as-is |
| web-scraper | ACTIVE | sonnet | (built-in scraping) | Keep as-is |
| gsd-advisor-researcher | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-ai-researcher | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-assumptions-analyzer | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-code-fixer | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-code-reviewer | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-codebase-mapper | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-debug-session-manager | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-debugger | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-doc-verifier | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-doc-writer | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-domain-researcher | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-eval-auditor | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-eval-planner | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-executor | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-framework-selector | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-integration-checker | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-intel-updater | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-nyquist-auditor | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-pattern-mapper | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-phase-researcher | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-plan-checker | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-planner | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-project-researcher | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-research-synthesizer | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-roadmapper | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-security-auditor | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-ui-auditor | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-ui-checker | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-ui-researcher | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-user-profiler | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |
| gsd-verifier | FRAMEWORK-OWNED | (task-level) | n/a | Framework-owned — no local action |

## Dormant Agent Details

None. Every project-owned agent (the 11 non-`gsd-*` files) is listed explicitly in CLAUDE.md's
Agent-Skill Architecture table, so none qualifies as DORMANT under the plan's criteria.

## Redundant Agent Details

None. No two project-owned agents ship identical owned-skill sets. The closest overlap
(`code-reviewer` vs `git-code-reviewer`) is intentional by design and documented below.

## Notes on Near-Redundancy (flagged for 65-04 quality audit, not archive)

**`code-reviewer` (opus) vs `git-code-reviewer` (sonnet)**

Both agents review code, but they differ on trigger and model tier:

| Dimension | code-reviewer | git-code-reviewer |
|-----------|---------------|-------------------|
| Trigger | Main-agent spawns after writing/modifying code | `.claude/hooks/post-push-review.js` triggers on `git push` |
| Default model | opus (deep reasoning, judgment) | sonnet (differential review, clear criteria) |
| Scope | Arbitrary code ranges, full-file review | Diff since last push, pattern-matched against rules |
| Output | Inline findings returned to orchestrator | Review log in background, no orchestrator interaction |

Both are listed as ACTIVE in CLAUDE.md. The division of labour is sensible — pre-commit human-in-loop
review (opus) vs background post-push audit (sonnet) — and neither is truly duplicative. Phase 65-04
(skill-optimizer audit) should still score both and confirm neither prompt has drifted into territory
owned by the other.

**`design-engineer` with 14 owned skills**

`design-engineer` owns all 14 design skills. That is a large surface area. Plan 65-02 is the
consolidation vehicle for pruning this to ~9 skills (5 holistic skills collapse into 1 umbrella).
The agent itself stays ACTIVE; only its owned-skill inventory will change.

## Cross-Reference to CLAUDE.md

The 11 ACTIVE agents above correspond 1:1 with the Agent-Skill Architecture table in CLAUDE.md.
If that table ever drifts (an agent is renamed, removed, or added), this inventory should be
regenerated as part of the `.claude/rules/maintenance.md` monthly checklist.
