"""LLM-03 benchmark: Claude primary ≥ 5× RuleExtractor on offseason content.

This test is the LLM-03 verifier. It loads the 30-doc offseason Bronze
fixture (W17 + W18), runs both extractors against it, and asserts the
Claude batched extractor produces at least 5× as many signals as the
RuleExtractor.

Rationale
---------
RuleExtractor's patterns are tuned for in-season content (injury reports,
status designations, weather, trade-deadline moves). On offseason news
(draft, coaching searches, contract rumors) it produces near-zero
signals — which is the core motivator for Phase 71's Claude-primary
extraction path.

Determinism contract
--------------------
The benchmark MUST instantiate ``ClaudeExtractor`` with
``roster_provider=lambda: []`` to match the ``_PENDING_WAVE_2_SHA`` →
real 64-hex SHA recording done in Plan 71-02 / 71-03 Task 2. If this
test is run with any non-empty roster, the computed prompt SHA drifts
from the fixture's recorded ``prompt_sha`` and ``FakeClaudeClient``
(strict mode) raises ``AssertionError``.

Output
------
Prints a line matching ``r"BENCHMARK: rule=\\d+ claude=\\d+ ratio=...x"``
for Plan 71-05 to grep out of pytest stdout and embed into the phase
SUMMARY.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.sentiment.processing.extractor import ClaudeExtractor
from src.sentiment.processing.rule_extractor import RuleExtractor
from tests.sentiment.fakes import FakeClaudeClient


def _load_bronze_docs():
    path = Path("tests/fixtures/bronze_sentiment/offseason_w17_w18.json")
    data = json.loads(path.read_text())
    return data["items"]


def test_claude_5x_rule_on_offseason(capsys):
    """LLM-03: claude_primary signals / rule signals ≥ 5.0 on offseason content."""
    docs = _load_bronze_docs()
    w17_docs = [d for d in docs if d.get("week") == 17]
    w18_docs = [d for d in docs if d.get("week") == 18]

    # --- Rule baseline -----------------------------------------------------
    rule = RuleExtractor()
    rule_signals = []
    for doc in docs:
        rule_signals.extend(rule.extract(doc))
    rule_total = len(rule_signals)

    # --- Claude primary (replay against recorded fixtures) -----------------
    # CRITICAL: roster_provider=lambda: [] — matches the recording contract
    # from Plan 71-02. Non-empty roster would drift the prompt SHA and
    # FakeClaudeClient (strict mode) would raise AssertionError.
    fake = FakeClaudeClient.from_fixture_dir(
        Path("tests/fixtures/claude_responses")
    )
    # batch_size=15 so each week's 15 docs land in a single batched call
    # matching the one recorded fixture per week.
    extractor = ClaudeExtractor(
        client=fake,
        roster_provider=lambda: [],
        batch_size=15,
    )

    by_doc_w17, non_player_w17 = extractor.extract_batch_primary(
        w17_docs, season=2025, week=17
    )
    by_doc_w18, non_player_w18 = extractor.extract_batch_primary(
        w18_docs, season=2025, week=18
    )

    player_signals_w17 = sum(len(sigs) for sigs in by_doc_w17.values())
    player_signals_w18 = sum(len(sigs) for sigs in by_doc_w18.values())
    claude_total = (
        player_signals_w17
        + player_signals_w18
        + len(non_player_w17)
        + len(non_player_w18)
    )

    ratio = claude_total / max(rule_total, 1)

    # Emit a greppable line for Plan 71-05 to harvest into SUMMARY.md.
    print(
        f"BENCHMARK: rule={rule_total} claude={claude_total} ratio={ratio:.2f}x"
    )

    # LLM-03 gate: ≥ 5× absolute ratio.
    assert ratio >= 5.0, (
        f"LLM-03 gate failed: claude/rule ratio={ratio:.2f}x "
        f"(claude={claude_total}, rule={rule_total}); expected ≥ 5.0x"
    )
    # Absolute floor: degenerate 0-rule AND 0-claude must still fail.
    assert claude_total >= 10, (
        f"Claude total ({claude_total}) below absolute floor of 10 signals"
    )
