# Agent Orchestration

## Agents that exist in this repo (`.claude/agents/`)

| Agent | Use for |
|-------|---------|
| git-code-reviewer | Review after writing code, before commits (quality, security, pandas/parquet, NFL logic) |
| docs-specialist | README/API docs/changelog upkeep |
| data-engineer, data-modeler | Pipeline/layer design, schemas, data quality |
| devops-engineer | CI/CD, Docker, deployment |
| draft-agent | Fantasy draft prep and live co-piloting |
| web-scraper | Scraping rankings/news/stats sources |
| design-engineer | Frontend UI polish |
| skill-optimizer | Auditing skills/agents |
| gsd-* | GSD workflow (planner, executor, verifier, debugger, ...), driven by `/gsd:*` skills |

Planning uses the built-in Plan agent (or `gsd-planner` inside GSD). Other agents live in per-machine
`~/.claude/agents/` and may not exist; check before relying on one.

## Usage

- Complex feature or refactor: plan first (Plan agent).
- Code just written or modified: run **git-code-reviewer**.
- Run independent work in parallel (one message, several agents), not sequentially.
- For hard problems use split-role reviewers (factual, senior engineer, security, consistency, redundancy).
