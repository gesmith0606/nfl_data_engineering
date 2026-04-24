"""LLM-04 cost gate (Plan 71-05 Task 3).

Promotes the LLM-04 budget contract from documentary (mention in
SUMMARY.md) to CI-enforced via a pytest assertion.

Methodology
-----------
* Read the W18 (warm-cache) fixture's recorded ``input_tokens``,
  ``output_tokens``, ``cache_read_input_tokens``, and
  ``cache_creation_input_tokens``. The W18 case represents steady-state
  weekly operation after the prompt cache has been primed (W17 was the
  cold-cache write); using the W17 fixture would over-project cost.
* Call ``compute_cost_usd`` with those four token classes. The function
  reads ``HAIKU_4_5_RATES`` internally, so any future Anthropic price
  change automatically flows through this test (no hard-coded dollars).
* Multiply by ``80 docs/day ÷ BATCH_SIZE`` batches/day × 7 days. The
  ``BATCH_SIZE`` constant is *imported* from
  ``src.sentiment.processing.extractor`` — never hard-coded — so a
  future BATCH_SIZE tune at the source ripples through this test.
* Assert ``weekly_cost < 5.0``. Failure mode is actionable: assertion
  message includes ``per_call_cost``, ``batches_per_day``, and the
  computed ``weekly_cost``.

A future regression (larger prompts, BATCH_SIZE shrink, rate hike, or
fixture re-record at higher token counts) fails this test in CI and
forces an explicit code-review discussion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.sentiment.processing.cost_log import HAIKU_4_5_RATES, compute_cost_usd
from src.sentiment.processing.extractor import BATCH_SIZE

# Per-context CONTEXT.md LLM-04: 80 docs/day daily cron average. Treated
# as a module-level constant rather than test-local literal so the source
# of truth shows up in a grep for cost projections.
DOCS_PER_DAY = 80
DAYS_PER_WEEK = 7

# Fixture path is documented in tests/fixtures/claude_responses/README.md
# (Plan 71-02). offseason_batch_w18.json is the warm-cache case (cache_read
# > 0, cache_creation == 0). offseason_batch_w17.json is the cold-cache
# baseline (kept for reference but not the gate basis).
_WARM_CACHE_FIXTURE = Path(
    "tests/fixtures/claude_responses/offseason_batch_w18.json"
)
_COLD_CACHE_FIXTURE = Path(
    "tests/fixtures/claude_responses/offseason_batch_w17.json"
)


@pytest.fixture(scope="module")
def warm_cache_tokens() -> dict:
    """Read the W18 (warm-cache) fixture's token counts."""
    payload = json.loads(_WARM_CACHE_FIXTURE.read_text())
    return {
        "input_tokens": int(payload["input_tokens"]),
        "output_tokens": int(payload["output_tokens"]),
        "cache_read_input_tokens": int(payload["cache_read_input_tokens"]),
        "cache_creation_input_tokens": int(
            payload["cache_creation_input_tokens"]
        ),
    }


# ---------------------------------------------------------------------------
# Cost gate
# ---------------------------------------------------------------------------


def test_weekly_cost_projection_under_5_dollars(warm_cache_tokens: dict) -> None:
    """LLM-04 gate: projected weekly cost < $5.00 at 80 docs/day warm cache.

    Computation:
        per_call_cost  = compute_cost_usd(**warm_cache_tokens)
        batches/day    = DOCS_PER_DAY / BATCH_SIZE
        weekly_cost    = per_call_cost × batches/day × 7

    A failure here means EITHER (a) prompt got bigger, (b) BATCH_SIZE
    shrank, (c) Anthropic raised Haiku 4.5 rates, or (d) the fixture
    was re-recorded at higher token counts. Any of those warrants an
    explicit discussion before merge.
    """
    per_call_cost = compute_cost_usd(
        input_tokens=warm_cache_tokens["input_tokens"],
        output_tokens=warm_cache_tokens["output_tokens"],
        cache_read_input_tokens=warm_cache_tokens["cache_read_input_tokens"],
        cache_creation_input_tokens=warm_cache_tokens[
            "cache_creation_input_tokens"
        ],
    )
    batches_per_day = DOCS_PER_DAY / BATCH_SIZE
    weekly_cost = per_call_cost * batches_per_day * DAYS_PER_WEEK

    assert weekly_cost < 5.0, (
        f"LLM-04 gate FAIL: projected weekly cost ${weekly_cost:.4f} "
        f">= $5.00. per_call=${per_call_cost:.6f} "
        f"batches/day={batches_per_day} (DOCS_PER_DAY={DOCS_PER_DAY} ÷ "
        f"BATCH_SIZE={BATCH_SIZE}) × {DAYS_PER_WEEK} days. "
        f"tokens={warm_cache_tokens}"
    )


def test_cost_projection_uses_warm_cache_fixture(warm_cache_tokens: dict) -> None:
    """Document WHY we use W18 — it's the steady-state warm-cache case.

    Cold-cache (week one of a season) costs more per call because the
    cache must be created before it can be read. Using W17 here would
    over-project the steady-state weekly burn rate. We assert the
    fixture's shape so a future re-record can't silently flip the
    cache discipline (cache_creation > 0 and cache_read == 0 would
    indicate a cold-cache re-record).
    """
    assert warm_cache_tokens["cache_read_input_tokens"] > 0, (
        "W18 fixture must have cache_read > 0 (warm-cache case). "
        f"got: {warm_cache_tokens}"
    )
    assert warm_cache_tokens["cache_creation_input_tokens"] == 0, (
        "W18 fixture must have cache_creation == 0 (cache already primed "
        f"by W17). got: {warm_cache_tokens}"
    )


def test_cold_cache_week_one_is_documented(capsys: pytest.CaptureFixture[str]) -> None:
    """Document the cold-cache (W17) cost as the worst-case projection.

    No assertion — purely informational so the print output lands in
    pytest -s logs. The cold-cache case happens once per season (or
    once per prompt-template change); steady-state cost is the W18
    figure asserted above.
    """
    payload = json.loads(_COLD_CACHE_FIXTURE.read_text())
    cold_cost = compute_cost_usd(
        input_tokens=int(payload["input_tokens"]),
        output_tokens=int(payload["output_tokens"]),
        cache_read_input_tokens=int(payload["cache_read_input_tokens"]),
        cache_creation_input_tokens=int(
            payload["cache_creation_input_tokens"]
        ),
    )
    batches_per_day = DOCS_PER_DAY / BATCH_SIZE
    cold_weekly = cold_cost * batches_per_day * DAYS_PER_WEEK
    print(
        f"COST_PROJECTION_COLD_CACHE: per_call=${cold_cost:.6f} "
        f"weekly=${cold_weekly:.4f} (cold-cache ceiling, once per season)"
    )


def test_haiku_rates_table_imported_not_hardcoded() -> None:
    """Assert HAIKU_4_5_RATES is the source of truth (no hard-coded $).

    A future Haiku price change updates ``HAIKU_4_5_RATES`` in
    ``cost_log.py``; this test imports it so the projection automatically
    reflects the new rates without manual edits here.
    """
    # Sanity: rate dict has the four expected token classes.
    assert set(HAIKU_4_5_RATES.keys()) == {
        "input",
        "output",
        "cache_read",
        "cache_creation",
    }
    # All rates must be positive floats per 1M tokens.
    for key, rate in HAIKU_4_5_RATES.items():
        assert rate > 0.0, f"HAIKU_4_5_RATES[{key!r}] must be > 0; got {rate}"
