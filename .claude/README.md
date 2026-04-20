# .claude/ Directory Guide

## What's Here

This directory configures Claude Code for the NFL Data Engineering project. It contains agent definitions, skill instructions, rules, hooks, and GSD framework files.

## Project-Owned (you maintain these)

| Directory | Contents | Update How |
|-----------|----------|------------|
| `rules/agents.md` | Agent-skill map, 5-route task routing, model routing | Edit directly |
| `rules/performance.md` | Model selection, context window, thinking budget | Edit directly |
| `rules/development-workflow.md` | Feature pipeline (research → TDD → review → commit → wiki) | Edit directly |
| `rules/git-workflow.md` | Commit message format, PR workflow | Edit directly |
| `rules/nfl-data-conventions.md` | S3 key pattern, download_latest_parquet, Medallion layers, local-first reads | Edit directly |
| `rules/nfl-scoring-formats.md` | PPR/Half-PPR/Standard formulas, SCORING_CONFIGS, roster formats, VORP | Edit directly |
| `rules/nfl-validation-patterns.md` | validate_data(), DuckDB-on-Parquet, business rules (seasons/weeks/teams) | Edit directly |
| `skills/ingest/` | Bronze ingestion skill + evals | Edit directly |
| `skills/validate-data/` | Data validation skill + evals | Edit directly |
| `skills/weekly-pipeline/` | Full pipeline skill + evals | Edit directly |
| `skills/backtest/` | Backtesting skill + evals | Edit directly |
| `skills/model-training/` | ML training skill + evals | Edit directly |
| `skills/prediction-pipeline/` | Game predictions skill + evals | Edit directly |
| `skills/sentiment/` | Sentiment pipeline skill + evals | Edit directly |
| `skills/graph/` | Graph features skill + evals | Edit directly |
| `skills/health-check/` | Pipeline health check skill + evals | Edit directly |
| `skills/refresh/` | ADP/roster refresh skill + evals | Edit directly |
| `skills/test/` | Test suite skill + evals | Edit directly |
| `skills/draft-prep/` | Draft preparation skill + evals | Edit directly |
| `agents/data-engineer.md` | Data pipeline agent definition | Edit directly |
| `agents/design-engineer.md` | Design agent definition | Edit directly |
| `agents/code-reviewer.md` | Code review agent | Edit directly |
| `agents/security-reviewer.md` | Security analysis agent | Edit directly |
| `agents/build-error-resolver.md` | Build/test failure agent | Edit directly |
| `agents/skill-optimizer.md` | Skill maintenance agent | Edit directly |
| `hooks/post-push-review.js` | Auto code review on git push | Edit directly |

## External Dependencies (updated via tools)

| Directory | Source | Update How |
|-----------|--------|------------|
| `rules/coding-style.md` | ECC (Everything Claude Code) | `git pull` in `~/repos/everything-claude-code/` |
| `rules/hooks.md` | ECC | Same |
| `rules/patterns.md` | ECC | Same |
| `rules/security.md` | ECC | Same |
| `rules/testing.md` | ECC | Same |
| `get-shit-done/` | GSD framework | `npx get-shit-done-cc@latest` |
| `hooks/gsd-*.js` | GSD framework | Same |
| `hooks/gsd-*.sh` | GSD framework | Same |
| `agents/gsd-*.md` | GSD framework | Same |
| `commands/gsd/` | GSD framework | Same |
| `skills/impeccable/` | ECC design skills | `git pull` in `~/repos/everything-claude-code/` |
| `skills/taste-skill/` | ECC design skills | Same (evals are project-owned) |
| `skills/soft-skill/` | ECC design skills | Same |
| `skills/emil-design-eng/` | ECC design skills | Same |
| 10 other design skills | ECC design skills | Same |

## Daily Workflow Quick Reference

**Data pipeline**: `/ingest` → `/validate-data` → `/weekly-pipeline`
**Model workflow**: `/model-training` → `/backtest` → `/prediction-pipeline`
**Sentiment**: `/sentiment` → `/weekly-pipeline`
**Graph**: `/ingest` (pbp) → `/graph` → `/model-training`
**Draft prep**: `/refresh` → `/draft-prep`
**Health**: `/health-check` (standalone)
**Before committing**: `/test`
**Before implementing**: `/wiki-query` (check knowledge vault)
**After meaningful work**: `/wiki-update` (sync to knowledge vault)

## Skill Audit

Run `skill-optimizer` agent monthly against `evals/evals.json` files. Tracked in `/memories/repo/skill-audit-log.md`.
