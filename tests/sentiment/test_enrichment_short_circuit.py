"""Tests for LLMEnrichment short-circuit on claude_primary envelopes (Plan 71-04).

CONTEXT.md: ``LLMEnrichment`` becomes a no-op when the active extractor is
``claude_primary``. Implementation: pipeline writes ``is_claude_primary: true``
into the Silver envelope; ``enrich_silver_records()`` early-returns on any
envelope carrying that flag. The module is preserved (still works in
``auto`` / ``rule`` modes — regression locked by
``test_llm_enrichment_optional.py``).

Tests in this module:

1. ``test_enrichment_skips_claude_primary_envelope`` — envelope with
   ``is_claude_primary=true`` is skipped; returns 0 and no sidecar written.
2. ``test_enrichment_processes_rule_envelope_unchanged`` — envelope without
   the flag is enriched as before (mocked LLMEnrichment client).
3. ``test_enrichment_mixed_envelopes`` — two envelopes in the same week,
   one with the flag one without; only the non-claude_primary one is enriched.
4. ``test_enrichment_legacy_envelope_missing_flag`` — envelope with no
   ``is_claude_primary`` key (pre-Phase-71 shape); enrichment runs normally.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from src.sentiment.enrichment import enrich_silver_records


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_record(
    signal_id: str = "sig-1",
    player_name: str = "Patrick Mahomes",
) -> Dict[str, Any]:
    """Construct a minimal Silver record dict for envelope fixtures."""
    return {
        "signal_id": signal_id,
        "doc_id": "doc-" + signal_id,
        "source": "rss",
        "season": 2025,
        "week": 17,
        "player_name": player_name,
        "player_id": "id-x",
        "sentiment_score": -0.2,
        "sentiment_confidence": 0.7,
        "category": "injury",
        "events": {"is_questionable": True},
        "published_at": "2025-12-29T00:00:00+00:00",
        "model_version": "ClaudeExtractor",
        "raw_excerpt": "Mahomes is questionable.",
    }


def _write_envelope(
    dir_path: Path,
    filename: str,
    envelope: Dict[str, Any],
) -> Path:
    """Write an envelope JSON to disk and return the path."""
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / filename
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def tmp_silver_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Dict[str, Path]:
    """Redirect the enrichment module's Silver dirs to a tmp tree.

    Returns a dict with ``signals_dir`` (season=2025/week=17) and
    ``enriched_dir`` (season=2025/week=17) for convenience.
    """
    silver_root = tmp_path / "data" / "silver" / "sentiment"
    signals_dir = silver_root / "signals" / "season=2025" / "week=17"
    enriched_dir = silver_root / "signals_enriched" / "season=2025" / "week=17"
    signals_dir.mkdir(parents=True, exist_ok=True)

    import src.sentiment.enrichment.llm_enrichment as mod

    monkeypatch.setattr(mod, "_SILVER_SIGNALS_DIR", silver_root / "signals")
    monkeypatch.setattr(
        mod, "_SILVER_ENRICHED_DIR", silver_root / "signals_enriched"
    )
    return {
        "signals_dir": signals_dir,
        "enriched_dir": enriched_dir,
        "silver_root": silver_root,
    }


# ---------------------------------------------------------------------------
# Test 1: claude_primary envelope skipped
# ---------------------------------------------------------------------------


def test_enrichment_skips_claude_primary_envelope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_silver_tree: Dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Envelope with is_claude_primary=true is skipped; 0 returned; no sidecar."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    envelope = {
        "batch_id": "abc123",
        "season": 2025,
        "week": 17,
        "is_claude_primary": True,
        "computed_at": "2026-04-24T12:00:00+00:00",
        "signal_count": 1,
        "records": [_make_record()],
    }
    _write_envelope(
        tmp_silver_tree["signals_dir"],
        "signals_abc123_20260424_120000.json",
        envelope,
    )

    # Patch LLMEnrichment._build_client so the class thinks it's available.
    import src.sentiment.enrichment.llm_enrichment as mod

    monkeypatch.setattr(
        mod.LLMEnrichment,
        "_build_client",
        lambda self: MagicMock(),
    )

    with caplog.at_level("INFO"):
        count = enrich_silver_records(season=2025, week=17)

    assert count == 0, "claude_primary envelope must contribute 0 to count"
    # No sidecar file written
    assert not tmp_silver_tree["enriched_dir"].exists() or not list(
        tmp_silver_tree["enriched_dir"].glob("*.json")
    )
    # An INFO log must mention the skip reason.
    assert any(
        "is_claude_primary" in rec.message.lower()
        or "claude_primary" in rec.message.lower()
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Test 2: rule envelope enriched unchanged
# ---------------------------------------------------------------------------


def test_enrichment_processes_rule_envelope_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_silver_tree: Dict[str, Path],
) -> None:
    """Envelope without is_claude_primary gets enriched as before."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    envelope = {
        "batch_id": "rule-1",
        "season": 2025,
        "week": 17,
        # No is_claude_primary key — pre-Plan-71 shape / rule output.
        "computed_at": "2026-04-24T12:00:00+00:00",
        "signal_count": 1,
        "records": [_make_record()],
    }
    _write_envelope(
        tmp_silver_tree["signals_dir"],
        "signals_rule1_20260424_120001.json",
        envelope,
    )

    import src.sentiment.enrichment.llm_enrichment as mod

    # Patch LLMEnrichment.enrich with a deterministic fake that tags the record.
    def fake_enrich(self: Any, record: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        out = dict(record)
        out["summary"] = "Fake enrichment summary."
        out["refined_category"] = "injury"
        return out

    monkeypatch.setattr(mod.LLMEnrichment, "enrich", fake_enrich)
    monkeypatch.setattr(
        mod.LLMEnrichment,
        "_build_client",
        lambda self: MagicMock(),
    )

    count = enrich_silver_records(season=2025, week=17)

    assert count == 1
    files = list(tmp_silver_tree["enriched_dir"].glob("enriched_*.json"))
    assert len(files) == 1
    out_env = json.loads(files[0].read_text())
    assert out_env["records"][0]["summary"] == "Fake enrichment summary."
    assert out_env["records"][0]["refined_category"] == "injury"


# ---------------------------------------------------------------------------
# Test 3: mixed envelopes — only rule envelope gets enriched
# ---------------------------------------------------------------------------


def test_enrichment_mixed_envelopes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_silver_tree: Dict[str, Path],
) -> None:
    """Two envelopes: one claude_primary + one rule. Only the rule one is enriched."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    claude_envelope = {
        "batch_id": "claude-1",
        "season": 2025,
        "week": 17,
        "is_claude_primary": True,
        "computed_at": "2026-04-24T12:00:00+00:00",
        "signal_count": 2,
        "records": [
            _make_record("cp-sig-1", "Patrick Mahomes"),
            _make_record("cp-sig-2", "Travis Kelce"),
        ],
    }
    rule_envelope = {
        "batch_id": "rule-1",
        "season": 2025,
        "week": 17,
        "computed_at": "2026-04-24T12:01:00+00:00",
        "signal_count": 1,
        "records": [_make_record("rule-sig-1", "Derrick Henry")],
    }
    _write_envelope(
        tmp_silver_tree["signals_dir"],
        "signals_claude1_20260424_120000.json",
        claude_envelope,
    )
    _write_envelope(
        tmp_silver_tree["signals_dir"],
        "signals_rule1_20260424_120100.json",
        rule_envelope,
    )

    import src.sentiment.enrichment.llm_enrichment as mod

    def fake_enrich(self: Any, record: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        out = dict(record)
        out["summary"] = "Mixed-run summary."
        out["refined_category"] = "general"
        return out

    monkeypatch.setattr(mod.LLMEnrichment, "enrich", fake_enrich)
    monkeypatch.setattr(
        mod.LLMEnrichment,
        "_build_client",
        lambda self: MagicMock(),
    )

    count = enrich_silver_records(season=2025, week=17)

    # Only the rule envelope's 1 record is enriched; claude_primary's 2 skipped.
    assert count == 1
    files = list(tmp_silver_tree["enriched_dir"].glob("enriched_*.json"))
    assert len(files) == 1
    out_env = json.loads(files[0].read_text())
    assert len(out_env["records"]) == 1
    assert out_env["records"][0]["signal_id"] == "rule-sig-1"
    assert out_env["records"][0]["summary"] == "Mixed-run summary."


# ---------------------------------------------------------------------------
# Test 4: legacy envelope missing flag => enriched normally
# ---------------------------------------------------------------------------


def test_enrichment_legacy_envelope_missing_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_silver_tree: Dict[str, Path],
) -> None:
    """Envelope predates Plan 71 (no is_claude_primary key); enrichment runs."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    # Completely lacks is_claude_primary — mirrors real pre-Phase-71 envelopes.
    envelope = {
        "batch_id": "legacy-1",
        "season": 2025,
        "week": 17,
        "computed_at": "2026-01-15T12:00:00+00:00",
        "signal_count": 1,
        "records": [_make_record("legacy-sig-1")],
    }
    _write_envelope(
        tmp_silver_tree["signals_dir"],
        "signals_legacy1_20260115_120000.json",
        envelope,
    )

    import src.sentiment.enrichment.llm_enrichment as mod

    def fake_enrich(self: Any, record: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
        out = dict(record)
        out["summary"] = "Legacy path summary."
        out["refined_category"] = "general"
        return out

    monkeypatch.setattr(mod.LLMEnrichment, "enrich", fake_enrich)
    monkeypatch.setattr(
        mod.LLMEnrichment,
        "_build_client",
        lambda self: MagicMock(),
    )

    count = enrich_silver_records(season=2025, week=17)
    assert count == 1
    files = list(tmp_silver_tree["enriched_dir"].glob("enriched_*.json"))
    assert len(files) == 1


# ---------------------------------------------------------------------------
# Test 5: all envelopes claude_primary => no sidecar, 0 returned
# ---------------------------------------------------------------------------


def test_enrichment_all_claude_primary_writes_no_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_silver_tree: Dict[str, Path],
) -> None:
    """When every envelope is claude_primary, no sidecar file is created."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    for i in range(3):
        envelope = {
            "batch_id": f"cp-{i}",
            "season": 2025,
            "week": 17,
            "is_claude_primary": True,
            "computed_at": f"2026-04-24T12:0{i}:00+00:00",
            "signal_count": 1,
            "records": [_make_record(f"cp-sig-{i}")],
        }
        _write_envelope(
            tmp_silver_tree["signals_dir"],
            f"signals_cp{i}_20260424_120{i}00.json",
            envelope,
        )

    import src.sentiment.enrichment.llm_enrichment as mod

    monkeypatch.setattr(
        mod.LLMEnrichment,
        "_build_client",
        lambda self: MagicMock(),
    )

    count = enrich_silver_records(season=2025, week=17)
    assert count == 0
    enriched_files: list = []
    if tmp_silver_tree["enriched_dir"].exists():
        enriched_files = list(
            tmp_silver_tree["enriched_dir"].glob("enriched_*.json")
        )
    assert enriched_files == []
