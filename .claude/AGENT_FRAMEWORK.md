# Agent Integration Framework

## Available Agents

### Core Development
- **system-architect**: Design architecture, data schemas, API contracts
- **code-implementation-specialist**: Implement features following project patterns
- **code-reviewer** (MANDATORY): Review all production code before commits
- **test-engineer**: Create test suites, improve coverage

### Data Engineering Specialists
- **data-engineer**: Databricks, AWS S3, modern data stack guidance (uses MCPs for research)
- **data-modeler**: Design data models, create data dictionaries
- **git-code-reviewer**: Automated review on git commit with /simplify integration

### Project Management & Docs
- **project-orchestrator**: Coordinate multi-step projects
- **docs-specialist**: Create and maintain documentation
- **devops-engineer**: CI/CD, AWS infrastructure

## Standard Workflow

```
1. project-orchestrator  →  Break down requirements
2. system-architect      →  Design component structure
3. code-implementation-specialist  →  Write code
4. /simplify             →  Review changed files for quality
5. test-engineer         →  Add test coverage
6. code-reviewer         →  Final review before commit
7. docs-specialist       →  Update docs
```

## Quality Gates
- Every `git push` triggers automated code review via Claude Code hook (`.claude/hooks/post-push-review.js`)
- Review runs as `git-code-reviewer` subagent in background
- Hardcoded credentials / injection vulnerabilities: BLOCKING
- NFL patterns (team validation, S3 paths): WARNING
- Minimum 80% test coverage for new features

## Automated Code Review Flow
```
git push
    ↓
Claude Code PostToolUse hook detects push
    ↓
git-code-reviewer subagent spawned in background
    ↓
Reviews diff of pushed commits
    ↓
Reports findings in conversation
```

## Model Selection
- **Opus/Sonnet**: Architecture design, complex multi-file implementations, agent delegation
- **Haiku**: Reading a file, quick syntax questions, simple one-line fixes, grep/search tasks
