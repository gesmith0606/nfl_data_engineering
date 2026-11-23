# Python Security

- Secrets come from the environment / `.env` (gitignored; the pre-commit hook blocks key patterns). Never hardcode or commit them.
  Read required ones with `os.environ["NAME"]` so a missing key fails loudly.
- Static analysis: `bandit -r src/` (not in `requirements.txt`; install ad hoc).
- The `secrets-handling` skill covers credential hygiene.
