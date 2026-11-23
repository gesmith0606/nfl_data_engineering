---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Patterns

- `typing.Protocol` for duck-typed interfaces (e.g. `DraftAdapter` in `src/draft_adapter.py`).
- Dataclasses as DTOs.
- Context managers for resources; generators for lazy, memory-efficient iteration.
- Python 3.9 compatibility: the backend image runs 3.9, so use `Optional[X]` / `Union`, not `X | None`, in runtime-evaluated annotations.
- Idioms: see the `python-idioms` skill.
