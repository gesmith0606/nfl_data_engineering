# Development Workflow

Pipeline for a feature: research, plan, TDD, review, commit. Commit/PR format is in [git-workflow.md](./git-workflow.md).

0. **Research & reuse first** (before any new implementation)
   - `gh search repos` / `gh search code` for existing implementations; check PyPI/npm before writing utilities.
   - Prefer adopting or wrapping a proven approach over net-new code when it meets the requirement.
   - Use the web-search/fetch MCP tools listed in `CLAUDE.md` (Configuration) for broader prior art.

1. **Plan first**: use the Plan agent (or `gsd-planner` in GSD flows); identify dependencies and risks, break into phases.

2. **TDD**: write the test first (RED), implement to pass (GREEN), refactor; aim for 80%+ coverage on new code.

3. **Review**: run **git-code-reviewer** right after writing code; fix CRITICAL/HIGH, and MEDIUM where possible.

4. **Commit & push**: detailed conventional commits, see git-workflow.md.
