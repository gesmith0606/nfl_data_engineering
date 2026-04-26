# Phase 71 — LLM-03 Benchmark

**Captured:** 2026-04-24
**Fixture commit:** 925d52e51a875cee65ba916ea21217654023d113
**Model:** claude-haiku-4-5
**Prompt-cache discipline:** `cache_control=ephemeral` on (a) static system prefix and (b) `ACTIVE PLAYERS` roster block (Plan 71-03 D-04)
**Batch size:** 15 docs/call (one batched call per week — matches the recorded fixture-per-week shape)

## Signal Counts on 30-doc Offseason Bronze (W17 + W18 of 2025)

The Bronze fixture is `tests/fixtures/bronze_sentiment/offseason_w17_w18.json`
— 15 W17 docs + 15 W18 docs covering NFL Draft buzz, coaching searches,
trade rumors, contract talk, and one in-season injury bridge to ensure
the rule extractor finds *something* (otherwise the ratio is undefined).

| Extractor       | Signals | Notes                                                                                          |
|-----------------|---------|------------------------------------------------------------------------------------------------|
| RuleExtractor   | 28      | Keyword patterns tuned for in-season content; misses draft/trade/coaching narrative.            |
| ClaudeExtractor | 156     | Batched (`BATCH_SIZE=15`), prompt-cached player list + system prefix.                           |

**Ratio:** 156 ÷ max(28, 1) = **5.57x**  (Gate: ≥ 5.0x — **PASS**)

## Test Output

```
$ python -m pytest tests/sentiment/test_extractor_benchmark.py -v -s
============================= test session starts ==============================
tests/sentiment/test_extractor_benchmark.py::test_claude_5x_rule_on_offseason
BENCHMARK: rule=28 claude=156 ratio=5.57x
PASSED
============================== 1 passed in 0.67s ===============================
```

## How to Reproduce

```bash
source venv/bin/activate
python -m pytest tests/sentiment/test_extractor_benchmark.py -v -s
```

The test runs **fully offline** — `FakeClaudeClient` replays the
recorded W17/W18 fixtures keyed by `prompt_sha`. Per LLM-05, no live
Anthropic API calls in CI. Re-recording the fixtures requires the
`ANTHROPIC_API_KEY` env var and the canonical roster contract
(`roster_provider=lambda: []`) so the SHA matches. See
`tests/fixtures/claude_responses/README.md` for the recording protocol.

## Determinism Contract

The benchmark MUST instantiate `ClaudeExtractor` with `roster_provider=lambda: []`
to match the SHA recorded in `tests/fixtures/claude_responses/offseason_batch_w{17,18}.json`.
Any non-empty roster drifts the prompt SHA and `FakeClaudeClient`
(strict mode) raises `AssertionError`. This is intentional — drift
detection is the test's secondary purpose.

## Cost Projection

See `71-SUMMARY.md` for the per-week cost projection at the daily-cron
cadence (80 docs/day × 7 days). Cost is enforced via
`tests/sentiment/test_cost_projection.py::test_weekly_cost_projection_under_5_dollars`.

## LLM-03 Status

| Metric              | Value | Required | Status |
|---------------------|-------|----------|--------|
| Claude/Rule ratio   | 5.57x | ≥ 5.0x   | PASS   |
| Claude total floor  | 156   | ≥ 10     | PASS   |
| Live API calls in CI | 0    | 0        | PASS (LLM-05 cross-check) |

LLM-03 ships green at the 2026-04-24 fixture commit. Future
prompt-template changes that reduce the lift trip the test in CI and
force a discussion before merge.
