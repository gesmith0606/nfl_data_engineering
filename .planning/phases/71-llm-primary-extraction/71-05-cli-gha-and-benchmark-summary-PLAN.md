---
phase: 71-llm-primary-extraction
plan: 05
type: execute
wave: 5
depends_on:
  - 71-03
  - 71-04
files_modified:
  - scripts/process_sentiment.py
  - .github/workflows/daily-sentiment.yml
  - tests/sentiment/test_process_sentiment_cli.py
  - tests/sentiment/test_daily_sentiment_workflow.py
  - tests/sentiment/test_cost_projection.py
  - .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md
autonomous: true
requirements:
  - LLM-02
  - LLM-03
  - LLM-04
  - LLM-05
must_haves:
  truths:
    - "`python scripts/process_sentiment.py --extractor-mode claude_primary --season 2025 --week 17` routes through the claude_primary pipeline path"
    - "`--mode claude_primary` is accepted as a short alias (matches existing CLI conventions)"
    - "When both `--extractor-mode` CLI arg and `EXTRACTOR_MODE` env are set, CLI wins and an INFO log documents the precedence"
    - "`.github/workflows/daily-sentiment.yml` sets `EXTRACTOR_MODE=claude_primary` when `ENABLE_LLM_ENRICHMENT=true` (else omits it, preserving auto/rule fallback)"
    - "The workflow never hard-fails because of claude_primary errors — the pipeline's own per-doc fallback handles this, and the workflow keeps its existing error-handling posture"
    - "`.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` records the claude/rule signal ratio from Plan 71-03's benchmark test (>= 5.0x required)"
    - "A Phase SUMMARY doc at `71-SUMMARY.md` captures: commit hash of fixtures, cost-per-week projection, ratio, and full list of new files (per LLM-03/LLM-04 evidence requirements)"
    - "LLM-04 cost gate is CI-enforced: `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` asserts projected weekly cost < $5.00 using `HAIKU_4_5_RATES` × warm-cache fixture token counts × 80 docs/day × 7 days"
  artifacts:
    - path: "scripts/process_sentiment.py"
      provides: "Extended CLI with --extractor-mode / --mode arg; passed through to SentimentPipeline"
      contains: "--extractor-mode"
    - path: ".github/workflows/daily-sentiment.yml"
      provides: "EXTRACTOR_MODE env var set conditionally on ENABLE_LLM_ENRICHMENT"
      contains: "EXTRACTOR_MODE"
    - path: "tests/sentiment/test_process_sentiment_cli.py"
      provides: "CLI arg-parsing tests; precedence tests; subprocess integration test"
    - path: "tests/sentiment/test_daily_sentiment_workflow.py"
      provides: "YAML-structure tests for the workflow edit"
    - path: "tests/sentiment/test_cost_projection.py"
      provides: "CI-enforced LLM-04 gate: weekly cost projection < $5.00 using HAIKU_4_5_RATES and fixture token counts"
      exports: ["test_weekly_cost_projection_under_5_dollars"]
    - path: ".planning/phases/71-llm-primary-extraction/71-BENCHMARK.md"
      provides: "LLM-03 benchmark evidence: rule vs claude signal counts + ratio + fixture commit hash"
  key_links:
    - from: "scripts/process_sentiment.py::main"
      to: "SentimentPipeline.__init__(extractor_mode=...)"
      via: "passes args.extractor_mode into constructor kwarg"
      pattern: "extractor_mode=args\\.extractor_mode"
    - from: ".github/workflows/daily-sentiment.yml"
      to: "EXTRACTOR_MODE env var consumed by SentimentPipeline"
      via: "workflow `env:` block on the pipeline step"
      pattern: "EXTRACTOR_MODE:"
    - from: "71-BENCHMARK.md"
      to: "tests/sentiment/test_extractor_benchmark.py output"
      via: "ratio captured from pytest -s output"
      pattern: "ratio=[0-9]+\\.[0-9]+x"
    - from: "tests/sentiment/test_cost_projection.py"
      to: "src/sentiment/processing/cost_log.py (HAIKU_4_5_RATES, compute_cost_usd) + tests/fixtures/claude_responses/offseason_batch_w18.json (warm-cache token counts)"
      via: "imports rate table; loads fixture for warm-cache tokens; computes weekly projection; asserts < $5"
      pattern: "test_weekly_cost_projection_under_5_dollars"
---

<objective>
Expose the new `claude_primary` mode to operators: (1) extend `scripts/process_sentiment.py` with `--extractor-mode`/`--mode` CLI args; (2) update `.github/workflows/daily-sentiment.yml` to set `EXTRACTOR_MODE=claude_primary` when `ENABLE_LLM_ENRICHMENT=true`; (3) promote the LLM-04 cost gate from documentary to CI-enforced via a dedicated test that computes the projected weekly cost from fixture token counts + `HAIKU_4_5_RATES` and asserts < $5; (4) run the Plan 71-03 benchmark test and commit the ratio evidence to `71-BENCHMARK.md`; (5) produce a `71-SUMMARY.md` with cost projection + fixture commit hashes for LLM-04 audit trail.

Purpose: LLM-02 requires the routing to be operator-accessible. LLM-03 requires the 5x ratio to be documented. LLM-04 requires the cost-per-week projection to be CI-enforced, not just documented.
Output: Extended CLI script, updated GHA workflow, CI cost-gate test, benchmark doc, phase SUMMARY.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/71-llm-primary-extraction/71-CONTEXT.md
@.planning/phases/71-llm-primary-extraction/71-03-batched-claude-extractor-PLAN.md
@.planning/phases/71-llm-primary-extraction/71-04-pipeline-wiring-PLAN.md
@scripts/process_sentiment.py
@.github/workflows/daily-sentiment.yml
@tests/sentiment/test_extractor_benchmark.py

<interfaces>
<!-- CLI surface -->

```
python scripts/process_sentiment.py \
  --season 2025 --week 17 \
  [--extractor-mode {auto,rule,claude,claude_primary}]    # new
  [--mode {auto,rule,claude,claude_primary}]              # short alias for --extractor-mode
  [--dry-run] [--skip-extraction] [--skip-team] [--verbose]
```

Precedence (documented in --help): CLI arg > EXTRACTOR_MODE env > default "auto".

GHA workflow diff — add to the "Run daily sentiment pipeline" step's `env:` block:

```yaml
env:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  ENABLE_LLM_ENRICHMENT: ${{ vars.ENABLE_LLM_ENRICHMENT || 'false' }}
  # NEW — Plan 71-05:
  EXTRACTOR_MODE: ${{ (vars.ENABLE_LLM_ENRICHMENT == 'true') && 'claude_primary' || '' }}
```

71-BENCHMARK.md template:

```markdown
# Phase 71 — LLM-03 Benchmark

**Captured:** YYYY-MM-DD
**Fixture commit:** <git rev-parse HEAD of tests/fixtures/bronze_sentiment/offseason_w17_w18.json>
**Model:** claude-haiku-4-5

## Signal Counts on 30-doc Offseason Bronze (W17+W18 2025)

| Extractor | Signals | Notes |
|-----------|---------|-------|
| RuleExtractor | N | Keyword patterns; misses draft/trade/coaching content |
| ClaudeExtractor | M | Batched (BATCH_SIZE=8), prompt-cached player list |

**Ratio:** M / max(N, 1) = X.XXx  (Gate: >= 5.0x)

## Test Output

(paste of pytest -s output including the `BENCHMARK: rule=... claude=... ratio=...x` line)

## Cost Projection

(see 71-SUMMARY.md for weekly/monthly projection)
```

71-SUMMARY.md sections (per phase SUMMARY template):
- Phase goal recap
- Files changed (complete list from `git diff --name-only`)
- Plan-by-plan outcome with evidence links
- Cost projection: input/output tokens per call × 80 docs/day × 7 days × Haiku 4.5 rates = projected $/week
- Risks/deferred: non-player routing deferred to Phase 72, Sonnet/Opus deferred unless 5x gate misses by >20%

Cost projection test shape (LLM-04 CI gate — Warning 5):

```python
# tests/sentiment/test_cost_projection.py
import json
from pathlib import Path
from src.sentiment.processing.cost_log import HAIKU_4_5_RATES, compute_cost_usd

def test_weekly_cost_projection_under_5_dollars():
    """LLM-04 gate: projected weekly cost < $5.00 at 80 docs/day warm-cache steady state.

    Uses the W18 (warm-cache) fixture's token counts as the per-call baseline,
    multiplied by (80 docs/day ÷ BATCH_SIZE) batches/day × 7 days.
    """
    fixture = json.loads(Path("tests/fixtures/claude_responses/offseason_batch_w18.json").read_text())
    per_call_cost = compute_cost_usd(
        input_tokens=fixture["input_tokens"],
        output_tokens=fixture["output_tokens"],
        cache_read_input_tokens=fixture["cache_read_input_tokens"],
        cache_creation_input_tokens=fixture["cache_creation_input_tokens"],
    )
    DOCS_PER_DAY = 80
    BATCH_SIZE = 8                        # matches src.sentiment.processing.extractor.BATCH_SIZE
    batches_per_day = DOCS_PER_DAY / BATCH_SIZE
    weekly_cost = per_call_cost * batches_per_day * 7
    assert weekly_cost < 5.0, (
        f"LLM-04 gate FAIL: projected weekly cost ${weekly_cost:.4f} >= $5.00. "
        f"per_call=${per_call_cost:.6f} batches/day={batches_per_day} × 7 days"
    )
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend process_sentiment.py CLI with --extractor-mode / --mode</name>
  <files>scripts/process_sentiment.py, tests/sentiment/test_process_sentiment_cli.py</files>
  <read_first>
    - scripts/process_sentiment.py (full file)
    - src/sentiment/processing/pipeline.py (new constructor signature after Plan 71-04)
    - src/sentiment/processing/extractor.py (mode constants — _EXTRACTOR_NAME_* for validation)
  </read_first>
  <behavior>
    - `python scripts/process_sentiment.py --help` output includes `--extractor-mode` and `--mode` with choices `auto|rule|claude|claude_primary`
    - `python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode claude_primary` invokes `SentimentPipeline(extractor_mode="claude_primary")` (verified by a subprocess test that patches the pipeline to a spy)
    - `--mode` is accepted as an exact alias for `--extractor-mode`; using both simultaneously is an error (argparse raises)
    - Default when neither is set: does NOT pass `extractor_mode` to constructor, letting it default to `"auto"` so the `EXTRACTOR_MODE` env var precedence in the pipeline kicks in
    - When both `--extractor-mode` arg and `EXTRACTOR_MODE` env are set, the CLI arg is the one passed to `SentimentPipeline` — env is effectively ignored (pipeline's own precedence code handles CLI > env)
    - Invalid mode value: `--extractor-mode nonsense` fails fast with argparse error (exit code 2, does NOT reach the pipeline)
  </behavior>
  <action>
    1. Open `scripts/process_sentiment.py`.
    2. Inside `_build_parser()`:
       ```python
       VALID_MODES = ["auto", "rule", "claude", "claude_primary"]

       mode_group = parser.add_mutually_exclusive_group()
       mode_group.add_argument(
           "--extractor-mode",
           choices=VALID_MODES,
           default=None,
           help=(
               "Override extractor mode. claude_primary uses batched Claude "
               "with rule fallback; rule forces deterministic; auto (default) "
               "honors EXTRACTOR_MODE env var. CLI arg wins over env."
           ),
       )
       mode_group.add_argument(
           "--mode",
           dest="extractor_mode",
           choices=VALID_MODES,
           default=None,
           help="Short alias for --extractor-mode.",
       )
       ```
       The mutually exclusive group enforces "use only one of --extractor-mode / --mode."
    3. In `main()`, when constructing `SentimentPipeline`, only pass `extractor_mode` when the arg is not None:
       ```python
       pipeline_kwargs = {}
       if args.extractor_mode is not None:
           pipeline_kwargs["extractor_mode"] = args.extractor_mode
           logger.info("CLI arg --extractor-mode=%s (wins over EXTRACTOR_MODE env)", args.extractor_mode)
       pipeline = SentimentPipeline(**pipeline_kwargs)
       ```
       This preserves the "env wins when arg is the default 'auto'" path Plan 71-04 built.
    4. Keep the existing "ANTHROPIC_API_KEY not set" warning under `if not skip_extraction:` but generalise to include the new modes — only warn about missing key when the chosen mode is `claude_primary` or `claude` (not for `rule`/`auto`).
    5. Create `tests/sentiment/test_process_sentiment_cli.py`:
       - Test `_build_parser()` directly: `--extractor-mode claude_primary` parses; `--mode claude_primary` parses; both together fail.
       - Test parser `--extractor-mode nonsense` raises `SystemExit(2)`.
       - Test that when `args.extractor_mode is None`, `main()` constructs the pipeline without passing the kwarg (use `monkeypatch` to swap `SentimentPipeline` with a spy that records kwargs).
       - Test that `--mode claude_primary` produces the same behaviour as `--extractor-mode claude_primary`.
       - Test that `--help` output mentions `claude_primary` (via `capsys`).
    6. Do NOT run the full pipeline in the subprocess test — patch `SentimentPipeline` and `WeeklyAggregator` / `TeamWeeklyAggregator` to spies that record `__init__` kwargs and return empty DataFrames / no-op `run()`.
    Why: CONTEXT.md D-01 "`--extractor-mode claude_primary` on `scripts/process_sentiment.py`" + specifics "`--extractor-mode` is also accepted as `--mode` short alias on the CLI." Mutual-exclusive group is the cleanest enforcement.
  </action>
  <acceptance_criteria>
    - `grep -n "\\-\\-extractor-mode" scripts/process_sentiment.py` returns at least 1 hit
    - `grep -n "\\-\\-mode" scripts/process_sentiment.py` returns at least 1 hit (alias)
    - `grep -n "add_mutually_exclusive_group" scripts/process_sentiment.py` returns 1 hit
    - `grep -n "claude_primary" scripts/process_sentiment.py` returns at least 2 hits
    - `python scripts/process_sentiment.py --help 2>&1 | grep -qE "\\-\\-extractor-mode.*claude_primary"` exits 0
    - `python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode nonsense 2>&1; test $? -eq 2` exits 0
    - `python scripts/process_sentiment.py --season 2025 --week 17 --extractor-mode claude_primary --mode rule 2>&1; test $? -eq 2` exits 0 (mutex error)
    - `python -m pytest tests/sentiment/test_process_sentiment_cli.py -v` all 5+ tests pass
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_process_sentiment_cli.py -v && python scripts/process_sentiment.py --help | grep -qE "claude_primary"</automated>
  </verify>
  <done>CLI accepts `--extractor-mode` and `--mode` as aliases; mutex enforced; invalid values rejected by argparse; pipeline kwargs-passing respects default-None to let env take over.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire EXTRACTOR_MODE into daily-sentiment GHA workflow</name>
  <files>.github/workflows/daily-sentiment.yml, tests/sentiment/test_daily_sentiment_workflow.py</files>
  <read_first>
    - .github/workflows/daily-sentiment.yml (full file already read)
    - scripts/daily_sentiment_pipeline.py (the actual script called by the workflow — confirm it eventually constructs SentimentPipeline or calls process_sentiment.py internally)
  </read_first>
  <behavior>
    - The "Run daily sentiment pipeline" step's `env:` block contains an `EXTRACTOR_MODE` key whose value is conditionally `claude_primary` when `vars.ENABLE_LLM_ENRICHMENT == 'true'` and empty otherwise
    - The "Log pipeline health summary" step emits an annotation documenting the effective EXTRACTOR_MODE
    - No `||` or `&&` outside of YAML expression syntax — use `${{ }}` expressions correctly
    - YAML is still valid and parseable by `PyYAML` / `yaml.safe_load`
    - Existing workflow structure preserved (permissions, concurrency, roster-refresh step, commit step, notify-failure job)
  </behavior>
  <action>
    1. Open `.github/workflows/daily-sentiment.yml`.
    2. In the "Run daily sentiment pipeline" step (around line 94-102), add a new env entry BELOW the existing two env vars:
       ```yaml
       env:
         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
         ENABLE_LLM_ENRICHMENT: ${{ vars.ENABLE_LLM_ENRICHMENT || 'false' }}
         # Phase 71 LLM-02: route to claude_primary extraction when enrichment flag is on.
         # Pipeline gracefully falls back to RuleExtractor per-doc if Claude errors occur.
         EXTRACTOR_MODE: ${{ (vars.ENABLE_LLM_ENRICHMENT == 'true') && 'claude_primary' || '' }}
       ```
    3. In the "Log pipeline health summary" step (around line 108-116), add a line AFTER the existing `LLM enrichment:` notice:
       ```yaml
       EXTRACTOR_MODE: ${{ (vars.ENABLE_LLM_ENRICHMENT == 'true') && 'claude_primary' || '' }}
       ```
       (Extend the env block for this step to include EXTRACTOR_MODE.)
       And in the run: block, add:
       ```bash
       echo "::notice::Extractor mode: ${EXTRACTOR_MODE:-auto (rule-primary)}"
       ```
    4. Do NOT modify: permissions, concurrency group, roster-refresh step, commit step, artifact upload step, notify-failure job. Preserve the existing comment about D-06 fail-open on missing ANTHROPIC_API_KEY (it's still accurate — pipeline per-doc fallback handles that).
    5. Create `tests/sentiment/test_daily_sentiment_workflow.py`:
       ```python
       import yaml
       from pathlib import Path

       WORKFLOW = Path(".github/workflows/daily-sentiment.yml")

       def test_workflow_parses_as_yaml():
           with open(WORKFLOW) as f:
               data = yaml.safe_load(f)
           assert "jobs" in data
           assert "sentiment" in data["jobs"]

       def test_run_step_sets_extractor_mode_env():
           with open(WORKFLOW) as f:
               data = yaml.safe_load(f)
           steps = data["jobs"]["sentiment"]["steps"]
           run_step = next(s for s in steps if s.get("name") == "Run daily sentiment pipeline")
           env = run_step.get("env", {})
           assert "EXTRACTOR_MODE" in env, env
           # Value is a GHA expression; string contains 'claude_primary'
           assert "claude_primary" in str(env["EXTRACTOR_MODE"])
           assert "ENABLE_LLM_ENRICHMENT" in str(env["EXTRACTOR_MODE"])

       def test_health_step_logs_extractor_mode():
           with open(WORKFLOW) as f:
               content = f.read()
           assert "Extractor mode:" in content

       def test_existing_permissions_preserved():
           with open(WORKFLOW) as f:
               data = yaml.safe_load(f)
           assert data["permissions"]["contents"] == "write"
           assert data["permissions"]["issues"] == "write"

       def test_no_anthropic_api_key_in_plain_text():
           """Secret reference only, never a literal value."""
           with open(WORKFLOW) as f:
               content = f.read()
           assert "secrets.ANTHROPIC_API_KEY" in content
           # No leaked literal key patterns (paranoia check)
           import re
           assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", content)
       ```
    6. Run the test file.
    Why: CONTEXT.md D-01 "`daily-sentiment.yml` GHA workflow gets `EXTRACTOR_MODE=claude_primary` env when `ENABLE_LLM_ENRICHMENT=true`." The conditional expression keeps the auto/rule fallback path intact when enrichment is off.
  </action>
  <acceptance_criteria>
    - `grep -n "EXTRACTOR_MODE" .github/workflows/daily-sentiment.yml` returns at least 2 hits
    - `grep -n "claude_primary" .github/workflows/daily-sentiment.yml` returns at least 1 hit
    - `python -c "import yaml; d=yaml.safe_load(open('.github/workflows/daily-sentiment.yml')); s=next(x for x in d['jobs']['sentiment']['steps'] if x.get('name')=='Run daily sentiment pipeline'); assert 'EXTRACTOR_MODE' in s['env'] and 'claude_primary' in str(s['env']['EXTRACTOR_MODE'])"` exits 0
    - `python -m pytest tests/sentiment/test_daily_sentiment_workflow.py -v` all 5 tests pass
    - Permissions preserved: yaml parse shows `contents: write` and `issues: write`
    - No literal API key patterns in workflow file
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_daily_sentiment_workflow.py -v</automated>
  </verify>
  <done>Workflow sets EXTRACTOR_MODE conditionally; health-summary step logs the effective mode; existing behavior preserved; 5 workflow tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: CI-enforce the LLM-04 cost gate (weekly projection < $5)</name>
  <files>tests/sentiment/test_cost_projection.py</files>
  <read_first>
    - src/sentiment/processing/cost_log.py (HAIKU_4_5_RATES + compute_cost_usd from Plan 71-03)
    - src/sentiment/processing/extractor.py (BATCH_SIZE constant from Plan 71-01)
    - tests/fixtures/claude_responses/offseason_batch_w18.json (warm-cache token counts; cache_read_input_tokens > 0)
    - .planning/phases/71-llm-primary-extraction/71-CONTEXT.md (LLM-04 <$5/week @ 80 docs/day gate)
  </read_first>
  <behavior>
    - `test_weekly_cost_projection_under_5_dollars` loads the W18 fixture (warm-cache case), computes per-call cost via `compute_cost_usd` using the fixture's token counts, multiplies by `(80 docs/day ÷ BATCH_SIZE)` batches/day × 7 days, and asserts `weekly_cost < 5.0`
    - The assertion message on failure includes the computed `weekly_cost`, the `per_call_cost`, and the input token breakdown so the failure mode is actionable
    - The test fails CI (exit code != 0) if LLM-04 regresses — this promotes the gate from documentary (SUMMARY.md text) to enforced (pytest)
    - Test uses the WARM-cache fixture (W18) because that represents steady-state weekly operation after cache is primed; using the cold-cache fixture (W17) would be pessimistic and non-representative of actual production cost
  </behavior>
  <action>
    1. Create `tests/sentiment/test_cost_projection.py` per the template in the `<interfaces>` block above. Key details:
       - Import `HAIKU_4_5_RATES` and `compute_cost_usd` from `src.sentiment.processing.cost_log`.
       - Import `BATCH_SIZE` from `src.sentiment.processing.extractor` (do NOT hard-code 8 — import the constant so it tracks the source of truth).
       - Load the W18 fixture from `tests/fixtures/claude_responses/offseason_batch_w18.json`.
       - Compute `per_call_cost = compute_cost_usd(input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens)` using the four token fields from the fixture.
       - Compute `batches_per_day = 80 / BATCH_SIZE` (float division — documents that 80 docs/day at BATCH_SIZE=8 = 10 batches/day).
       - Compute `weekly_cost = per_call_cost * batches_per_day * 7`.
       - Assert `weekly_cost < 5.0` with a message that includes the numeric computation.
    2. Add a second test `test_cost_projection_uses_warm_cache_fixture` that asserts the W18 fixture has `cache_read_input_tokens > 0` and `cache_creation_input_tokens == 0` (documents WHY we use W18 — it's the steady-state case).
    3. Optionally add `test_cold_cache_week_one_is_documented` that computes the W17 (cold-cache) cost and just prints it (no assertion — this is the documented worst case).
    4. Run the test file directly:
       ```bash
       python -m pytest tests/sentiment/test_cost_projection.py -v
       ```
       Confirm it passes at the fixture token counts recorded in Plan 71-02 (input ~1200-1800, output ~400-800, cache_read ~1100 for W18 → per-call ~$0.005 → weekly ~$0.35 — well under $5).
    Why: Warning 5 (reviewer) — LLM-04 was documented in SUMMARY.md but not CI-enforced. A projection drift (larger prompts, higher token counts, rate changes) would go unnoticed until production. This test makes the gate self-policing: any increase that pushes projected weekly cost above $5 fails CI and forces an explicit code-review discussion.
  </action>
  <acceptance_criteria>
    - `test -f tests/sentiment/test_cost_projection.py` exits 0
    - `grep -n "test_weekly_cost_projection_under_5_dollars" tests/sentiment/test_cost_projection.py` returns 1 hit
    - `grep -n "HAIKU_4_5_RATES\|compute_cost_usd" tests/sentiment/test_cost_projection.py` returns at least 1 hit
    - `grep -n "from src.sentiment.processing.extractor import BATCH_SIZE" tests/sentiment/test_cost_projection.py` returns 1 hit (no hard-coded 8)
    - `grep -n "offseason_batch_w18.json" tests/sentiment/test_cost_projection.py` returns 1 hit (warm-cache fixture)
    - `grep -n "80" tests/sentiment/test_cost_projection.py` returns at least 1 hit (80 docs/day constant per LLM-04)
    - `grep -nE "\\*\\s*7\\b|\\bdays?\\b" tests/sentiment/test_cost_projection.py` returns at least 1 hit (weekly multiplier)
    - `python -m pytest tests/sentiment/test_cost_projection.py -v` all tests pass
    - `python -m pytest tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars -v` passes in isolation
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/test_cost_projection.py -v</automated>
  </verify>
  <done>LLM-04 cost gate is CI-enforced; weekly projection under $5 asserted with fixture token counts + `HAIKU_4_5_RATES` + BATCH_SIZE imported (not hard-coded); any future regression (larger prompts, rate hikes) fails the test and blocks the commit.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Capture benchmark + cost projection; write 71-BENCHMARK.md and phase SUMMARY</name>
  <files>.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md, .planning/phases/71-llm-primary-extraction/71-SUMMARY.md</files>
  <read_first>
    - tests/sentiment/test_extractor_benchmark.py (from Plan 71-03)
    - tests/sentiment/test_cost_projection.py (just built in Task 3)
    - tests/fixtures/bronze_sentiment/offseason_w17_w18.json
    - src/sentiment/processing/cost_log.py (from Plan 71-03; HAIKU_4_5_RATES)
    - .planning/phases/71-llm-primary-extraction/71-CONTEXT.md (LLM-04 cost gate <$5/week at 80 docs/day)
    - .claude/get-shit-done/templates/summary.md (phase SUMMARY template)
  </read_first>
  <behavior>
    - `71-BENCHMARK.md` captures RuleExtractor signal count, ClaudeExtractor signal count, and ratio — pasted verbatim from `pytest tests/sentiment/test_extractor_benchmark.py -v -s` output
    - The ratio in `71-BENCHMARK.md` is >= 5.0x (LLM-03 gate)
    - The fixture commit hash is the git rev of `tests/fixtures/bronze_sentiment/offseason_w17_w18.json`
    - `71-SUMMARY.md` includes a "Cost Projection" section with:
      - Calculation: `input_tokens_per_call × 10 batches/day × 7 days × input_rate + output_tokens_per_call × ... + cache_read × ...`
      - Projected weekly cost: target < $5, document actual projection
      - Assumption basis: 80 docs/day ÷ 8 batch size = 10 batches/day; W17 fixture input_tokens ~1400, output_tokens ~500, cache_read ~1100 from week 2 onward
      - Link to the CI-enforced gate: `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars`
    - `71-SUMMARY.md` lists ALL files changed in the phase (produced via `git diff --name-only main...HEAD` conceptually, or by listing by hand from plan manifests)
  </behavior>
  <action>
    1. Run the benchmark test with `-s` to capture the BENCHMARK output line:
       ```bash
       python -m pytest tests/sentiment/test_extractor_benchmark.py -v -s 2>&1 | tee /tmp/71-benchmark.out
       ```
       Extract the `rule=N claude=M ratio=X.XXx` line.
    2. Compute the fixture commit hash:
       ```bash
       git log -n 1 --pretty=%H -- tests/fixtures/bronze_sentiment/offseason_w17_w18.json
       ```
    3. Write `.planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` per the template in `<interfaces>`. Include:
       - Capture date (today).
       - Fixture commit hash.
       - Model: `claude-haiku-4-5`.
       - Signal counts table with RuleExtractor and ClaudeExtractor rows.
       - Ratio and LLM-03 gate status (PASS >= 5.0x / FAIL < 5.0x).
       - Pasted pytest output section (trimmed to the relevant BENCHMARK line + the test name line).
    4. Write `.planning/phases/71-llm-primary-extraction/71-SUMMARY.md` with sections:
       - **Phase Goal Recap**: one paragraph from ROADMAP.
       - **Shipped Plans**: a bullet for each of 71-01..71-05 with evidence link to each plan's SUMMARY.
       - **LLM-03 Evidence**: link to 71-BENCHMARK.md; explicit ratio value + PASS/FAIL.
       - **LLM-04 Cost Projection**:
         - W1 (cold cache): `(1400/1e6 × 1.00 + 500/1e6 × 5.00 + 0 + 1100/1e6 × 1.25) × 10 batches/day × 7 days = $X.XX/week`
         - W2+ (warm cache): `(300/1e6 × 1.00 + 500/1e6 × 5.00 + 1100/1e6 × 0.10 + 0) × 10 batches/day × 7 days = $Y.YY/week`
         - State whether projected weekly is < $5 gate.
         - **CI enforcement:** link to `tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars` (the gate is now an assertion, not a narrative).
       - **LLM-05 Evidence**: pytest summary line `N passed` for the entire sentiment suite; confirm FakeClaudeClient-driven determinism.
       - **Files Changed**: Exhaustive list of files created/modified across all 5 plans (organised by plan).
       - **Operational Notes**: how to toggle the mode via GHA vars.ENABLE_LLM_ENRICHMENT, how to re-record fixtures if the prompt changes, what happens on Claude outages.
       - **Deferred to Phase 72**: non-player attribution routing (EVT-02), new event flags (EVT-01).
       - **Risks & Watchouts**: GHA cache-miss weeks may spike cost; Haiku→Sonnet escalation path if LLM-03 ever fails.
    5. Commit the two planning docs (part of standard commit flow in execute-phase; do not force a commit here — leave for the commit step downstream).
    Why: LLM-03 requires the benchmark delta committed to a summary doc. LLM-04 requires the cost trace via log OR console screenshot — the computed projection plus the per-call CostLog Parquet files AND the CI-enforced gate (Task 3) together satisfy this. The SUMMARY.md closes out the phase per the standard GSD flow.
  </action>
  <acceptance_criteria>
    - `test -f .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` exits 0
    - `test -f .planning/phases/71-llm-primary-extraction/71-SUMMARY.md` exits 0
    - `grep -E "ratio=[0-9]+\.[0-9]+x" .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` returns a hit
    - `grep -E "PASS|>= 5\.0x" .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` returns a hit (ratio passes LLM-03 gate)
    - `grep -qE "Cost Projection|cost projection" .planning/phases/71-llm-primary-extraction/71-SUMMARY.md` exits 0
    - `grep -qE "71-BENCHMARK\.md" .planning/phases/71-llm-primary-extraction/71-SUMMARY.md` exits 0
    - `grep -qE "ENABLE_LLM_ENRICHMENT|EXTRACTOR_MODE" .planning/phases/71-llm-primary-extraction/71-SUMMARY.md` exits 0
    - `grep -qE "test_weekly_cost_projection_under_5_dollars|test_cost_projection" .planning/phases/71-llm-primary-extraction/71-SUMMARY.md` exits 0 (references the CI gate)
    - Benchmark file contains the fixture commit hash (40-char hex): `grep -E "^\\*\\*Fixture commit:\\*\\* [a-f0-9]{40}" .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md` returns a hit (OR document placeholder with explanation if fixture not yet committed)
    - LLM-05 confirmation: `python -m pytest tests/sentiment/ -v 2>&1 | tail -3 | grep -qE "passed"` exits 0
  </acceptance_criteria>
  <verify>
    <automated>python -m pytest tests/sentiment/ -v && test -f .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md && test -f .planning/phases/71-llm-primary-extraction/71-SUMMARY.md && grep -qE "ratio=[0-9]+\.[0-9]+x" .planning/phases/71-llm-primary-extraction/71-BENCHMARK.md && grep -qE "Cost Projection" .planning/phases/71-llm-primary-extraction/71-SUMMARY.md</automated>
  </verify>
  <done>Benchmark doc committed with ratio >=5x; SUMMARY.md captures cost projection under $5/week gate with CI-enforcement link; files-changed list exhaustive; operational notes + deferred items + risks documented.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CLI args → pipeline | User-supplied `--extractor-mode` string; argparse validates choices |
| GHA env → pipeline | EXTRACTOR_MODE sourced from repo `vars` — not a secret, safe to log |
| benchmark capture → planning docs | pytest output pasted verbatim; no credentials crossed |
| fixture tokens → cost gate | Fixture token counts used as CI cost projection basis; drift caught by test |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-71-05-01 | Tampering | Invalid --extractor-mode value | mitigate | argparse `choices=` enforcement; exit 2 on bad value |
| T-71-05-02 | Information disclosure | Workflow file leaking API key | mitigate | Test asserts only `secrets.ANTHROPIC_API_KEY` reference, no literal sk-ant- patterns |
| T-71-05-03 | Denial of Service | Cost overrun in production | mitigate | CostLog WARNING at >$5/week (Plan 71-03) + CI-enforced gate in `test_cost_projection.py` blocks commits that would raise projected cost above $5 |
| T-71-05-04 | Repudiation | LLM-03 gate not documented | mitigate | 71-BENCHMARK.md captures ratio + fixture commit hash + pytest output; permanent audit trail |
| T-71-05-05 | Repudiation | LLM-04 gate not enforced | mitigate | `test_weekly_cost_projection_under_5_dollars` promotes the gate from narrative to CI-enforced assertion |
</threat_model>

<verification>
- `python -m pytest tests/sentiment/ -v` — entire sentiment suite green
- `python scripts/process_sentiment.py --help` shows `claude_primary` and `--mode` alias
- `python -c "import yaml; d=yaml.safe_load(open('.github/workflows/daily-sentiment.yml'))"` parses cleanly
- `71-BENCHMARK.md` has ratio >= 5.0x
- `71-SUMMARY.md` has Cost Projection, Files Changed, Deferred Items sections and references the CI-enforced cost gate
- `tests/sentiment/test_cost_projection.py` passes (CI-enforces LLM-04)
</verification>

<success_criteria>
- CLI exposes `--extractor-mode` / `--mode` with mutual exclusion + valid-choice enforcement
- GHA workflow sets EXTRACTOR_MODE conditionally; health log documents effective mode
- LLM-04 cost gate is CI-enforced: `test_weekly_cost_projection_under_5_dollars` asserts < $5
- Benchmark evidence committed to `71-BENCHMARK.md`; ratio >= 5.0x
- Phase SUMMARY committed to `71-SUMMARY.md` with cost projection under $5/week gate + CI-enforcement link
- All prior-wave tests still pass (regression locked)
</success_criteria>

<output>
After completion, `.planning/phases/71-llm-primary-extraction/71-05-SUMMARY.md` contains a link to the phase-level `71-SUMMARY.md`.
</output>
