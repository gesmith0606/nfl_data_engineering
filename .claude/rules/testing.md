---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Testing

- Framework: **pytest** (`python -m pytest tests/ -v`; config in `pytest.ini`, collects `tests/` only).
- Coverage: `pytest --cov=src --cov-report=term-missing`
- Categorize with registered marks: `unit`, `integration`, `network` (see `pytest.ini`).
- New code follows TDD (see [development-workflow.md](./development-workflow.md)); the `test-driven-development` skill covers the loop.
