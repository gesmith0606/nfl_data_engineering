---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Coding Style

- Follow **PEP 8**; type annotations on all function signatures.
- Prefer immutable structures (`@dataclass(frozen=True)`, `NamedTuple`) where mutation isn't needed.
- Formatting/linting: **black** and **flake8** (both in `requirements.txt`); **isort** for import order.
- Idioms: see the `python-idioms` skill.
