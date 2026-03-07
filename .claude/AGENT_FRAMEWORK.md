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
- Every `git commit` triggers automated code review (`.claude/workflows/automated-code-review.py`)
- Functions >50 lines: auto-simplified via /simplify (WARNING)
- Hardcoded credentials / injection vulnerabilities: BLOCKING
- NFL patterns (team validation, S3 paths): WARNING
- Minimum 80% test coverage for new features
- All public interfaces need updated docstrings

## Automated Code Review Flow
```
git commit
    ↓
🔒 Credential scan (blocks AKIA*, github_pat_*, private keys)
    ↓
🔍 Static analysis of changed Python files
    ↓
✅ /simplify applied to complex functions
    ↓
❌ Block on critical issues | ⚠️ Warn + 5s delay | ✅ Pass
    ↓
📊 Quality metrics saved to .claude/review_history/
```

## Hook Installation
```bash
.claude/git-hooks/install-hooks.sh
```

## Model Selection
- **Opus/Sonnet**: Architecture design, complex multi-file implementations, agent delegation
- **Haiku**: Reading a file, quick syntax questions, simple one-line fixes, grep/search tasks
