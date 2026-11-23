---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Security

- Secrets come from the environment / `.env` (gitignored). Never hardcode or commit them. Nothing in this repo blocks a committed key automatically, so check the diff before every commit.
  Read required ones with `os.environ["NAME"]` so a missing key fails loudly.
- Static analysis: `bandit -r src/` (not in `requirements.txt`; install ad hoc).
- The `secrets-handling` skill covers credential hygiene.
