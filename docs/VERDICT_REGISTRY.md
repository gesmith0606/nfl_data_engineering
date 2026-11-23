# Verdict registry

`.planning/verdicts.json` makes the rule "a verdict nobody wires into code is not a
decision" executable. Each `.planning/*` ruling (SHIP / SHIP_OPT_IN / HOLD / KILL / DEAD)
gets one entry plus machine-checkable assertions about the repo. Checker:
`src/verdict_registry.py`; tests: `tests/test_verdict_registry.py`; table:
`python scripts/check_verdicts.py` (exit 1 on any failure).

**Rule: a KILL or HOLD ships with its registry entry in the same change as the ruling doc.**
A new lever with no entry and no `unregistered_ok` reason fails CI. Levers are: argparse
booleans (`store_true`, `store_false`, `BooleanOptionalAction`, as string or attribute) in
`generate_projections.py`, `generate_predictions.py`, `set_lineups.py`,
`sunday_projection_refresh.py`; and module-level constants named
`USE|ENABLE|ALLOW|APPLY|DISABLE|SKIP_*` bound to a bool or 0/1, in `src/`, `scripts/`,
`web/api/`.

**Shipped VALUES are levers too.** A bool pin does not stop `SHRINK_FACTOR = 1.0`, or a cron
passing `--consensus-anchor-src`. The `value_levers` list names the numeric/dict levers that
MUST be pinned by a `module_constant` / `argparse_default` assertion (the test asserts the
list); add to it when a new tuned number ships.

## Adding an entry
1. Write the ruling in `.planning/<NAME>.md`.
2. Append to `verdicts`: `id`, `subject`, `ruling`, `date`, `doc`, `note`, `enforcement`.
   `doc` must be the doc that actually rules it; if none does, cite the closest factual
   source and say in `note` what it does and does not say.
3. Purely operational flags go in `unregistered_ok` with an honest `reason`.
4. `python scripts/check_verdicts.py`. A real violation: fix the code, never the entry.
   If you must land first, mark that test in `KNOWN_VIOLATIONS` (xfail strict).

## Assertion kinds
- `argparse_default` `{script, flag, expected}`: static `ast` read; the default may be a name
  (resolved through the script's own constants or its `from X import`). Fails if the script
  calls `set_defaults(...)`, `setattr(.., dest, ..)` or assigns `<obj>.<dest> = ...`. For
  scripts the cron runs, the entry must also hold a workflow assertion for the same flag.
- `module_constant` `{module, name, expected}`: `expected` is a bool/number/string/list/dict
  compared by value (floats within 1e-9, bools strictly, dict keys exactly). Read with `ast`
  (names resolved statically; the module is never imported). Fails if the name is bound
  more than once at module level (incl. inside top-level `if`/`try`), via `globals()`,
  `global X` in a function, or an import, and reports every site.
- `module_constant_contains` `{module, name, item}`: item (by value) is in a literal sequence.
- `workflow_must_not_pass` `{workflow, script, flag}`: conservative token scan. The flag
  token anywhere in the executable text of any `.github/workflows/*.yml|*.yaml` (every `run:`
  body after comment stripping, plus every other YAML scalar: `env:`, `with:`, matrix, input
  defaults) or any tracked `*.sh` is a violation. The ONE exemption: the flag is on a simple
  command (split on `; & && | ||`, `\` continuations joined) that invokes the script and carries
  a real `--shadow-tag <value>`. Expect false positives; they are loud on purpose.
- `workflow_must_pass`: some non-shadow simple command genuinely invokes the script
  (`python[3] <path>/script.py`, `./script.py`, `-m scripts.script`) with the flag. `echo`
  lines, comments and variable indirection do not count.
- `workflow_no_flag_passthrough` `{workflow, scripts, allow_expressions, allow_vars}`: any
  `${{ inputs|vars|matrix|steps|needs|env.* }}` expression, or shell variable, on a command
  line naming one of `scripts` is a violation unless allowlisted with a reason (it is an
  unreviewable flag passthrough).
- `data_column_blank` `{glob, column, enforced_since}`: every file whose FILENAME timestamp
  (UTC, never mtime) is `>=` `enforced_since` has the column all blank. `enforced_since` is a
  date (midnight UTC) or a full ISO timestamp (`Z`/offset). No such file = SKIP with the reason.
- `source_must_not_contain` / `source_must_contain` `{file, pattern[, unless]}`: regex over
  tracked-or-not files. `file` is one glob or a list (case-sensitive; `**` supported); a list
  matching nothing fails. With `unless`, matching is per line and a line that also matches
  `unless` is allowed (dated or negated wording).

## Other checks
- Every literal path and glob in the registry must resolve against `git ls-files` with exact
  case (so `README.md` vs the tracked `README.MD` fails on macOS too).
- `shape_errors`: each ruling needs enforcement or a gap; HOLD/SHIP_OPT_IN must never require
  the cron to pass a flag; cron-script defaults need a paired workflow assertion.
- No file in `src/`, `scripts/` (not `scripts/experiment*`) or `web/api/` may assign
  `<other>.USE_*` / `ENABLE_*` or `setattr(.., 'USE_*', ..)`; allowlist legitimate cases in
  `attribute_write_allowlist` (file, target, reason).

## Scope notes
- `claim-*` bans cover frontend source (`.ts/.tsx/.md/.json`) and `README.MD`. `docs/` is out
  of scope: dated architecture docs legitimately quote old numbers.
- CI: add `.github/workflows/**` and `.planning/verdicts.json` to the `backend-tests`
  paths-filter in `ci.yml`, otherwise a workflow-only edit that passes a HOLD flag never
  runs these tests.
