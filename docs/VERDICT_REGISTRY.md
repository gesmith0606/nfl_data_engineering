# Verdict registry

`.planning/verdicts.json` makes the rule "a verdict nobody wires into code is not a
decision" executable. Each `.planning/*` ruling (SHIP / SHIP_OPT_IN / HOLD / KILL / DEAD)
gets one entry plus machine-checkable assertions about the repo. Checker:
`src/verdict_registry.py`; tests: `tests/test_verdict_registry.py`; table:
`python scripts/check_verdicts.py` (exit 1 on any failure).

**Rule: a KILL or HOLD ships with its registry entry in the same change as the ruling doc.**
New lever (argparse boolean in `generate_projections.py`/`generate_predictions.py`, or a
module-level `USE_*`/`ENABLE_*` bool in `src/`) with no entry and no `unregistered_ok`
reason fails CI.

## Adding an entry
1. Write the ruling in `.planning/<NAME>.md`.
2. Append to `verdicts` in `.planning/verdicts.json`: `id`, `subject`, `ruling`, `date`,
   `doc`, `note`, `enforcement` (list). If nothing in code can gate it yet, give
   `enforcement_gap` (one line) instead, and open an issue.
3. Purely operational flags go in `unregistered_ok` with a `reason`.
4. `python scripts/check_verdicts.py`. A real violation: fix the code, never the entry.
   If you must land first, mark that test in `KNOWN_VIOLATIONS` (xfail strict).

## Assertion kinds
- `argparse_default` `{script, flag, expected}`: static `ast` read of the parser (also
  follows a `build_parser()` imported from another module). For `--no-X` flags, "default
  ON" means the flag's default is `False`; for HOLD/opt-in flags it is also `False`.
- `module_constant` `{module, name, expected}`: literal module-level value, e.g.
  `ranking_score.USE_RANKING_SCORE` False. Dotted modules are repo paths
  (`web.api.routers.predictions`).
- `module_constant_contains` `{module, name, item}`: item is in a literal tuple/list.
- `workflow_must_not_pass` / `workflow_must_pass` `{workflow, script, flag}`: parses
  `.github/workflows/*.yml` `run:` blocks (line continuations, `VAR="--flag"` indirection).
  `workflow: "*"` scans every workflow. Commands carrying `--shadow-tag` are exempt (they
  never publish). `must_pass` means some non-exempt command passes it.
- `data_column_blank` `{glob, column, enforced_since}`: every file whose FILENAME
  timestamp (never mtime) is after `enforced_since` has the column all blank. No such file
  = SKIP with the reason shown.
- `source_must_not_contain` / `source_must_contain` `{file, pattern}`: regex over a tracked
  file or `**` glob; a glob matching nothing fails (no vacuous pass).

## Gaps
Ownership of CI: add `.github/workflows/**` and `.planning/verdicts.json` to the
`backend-tests` paths-filter in `ci.yml`, otherwise a workflow-only edit that passes a HOLD
flag never runs these tests.
