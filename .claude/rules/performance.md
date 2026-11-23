# Performance Optimization

## Model Selection

- Smaller/cheaper model: lookups, searches, mechanical edits, frequently invoked worker agents.
- Mid-tier model: main development and orchestration.
- Strongest model: architecture, design, review, research, hard debugging.

## Context Window Management

Avoid the last ~20% of the context window for large refactors, multi-file features, and debugging
complex interactions. Single-file edits, utilities, docs, and simple fixes are low-sensitivity.

For complex tasks: use extended thinking and Plan mode, run multiple critique rounds, and use
split-role sub-agents for diverse perspectives.

## Build Troubleshooting

If a build fails: read the error, fix incrementally, and re-verify after each fix.
