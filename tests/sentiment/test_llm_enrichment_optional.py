"""Tests for the optional LLM enrichment module (Plan 61-06).

These tests lock in D-04 (LLM is optional) and D-06 (fail-open) contracts:
    - Enrichment returns the record unchanged when ANTHROPIC_API_KEY is absent.
    - Enrichment catches any SDK exception and returns the record unchanged.
    - enrich_silver_records() never raises when no Silver files exist.
    - Sidecar output goes to signals_enriched/, not the original signals/.

The tests are deliberately hermetic: they monkeypatch os.environ and the
Anthropic client so no real API calls fire and no real files are read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.sentiment.enrichment import LLMEnrichment, enrich_silver_records


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_silver_record() -> Dict[str, Any]:
    """Minimal rule-extracted Silver record fed into enrichment."""
    return {
        "signal_id": "abc-123",
        "doc_id": "doc-1",
        "source": "reddit",
        "season": 2025,
        "week": 1,
        "player_name": "Patrick Mahomes",
        "player_id": "00-0033873",
        "sentiment_score": -0.3,
        "sentiment_confidence": 0.7,
        "category": "injury",
        "events": {
            "is_ruled_out": False,
            "is_questionable": True,
            "is_returning": False,
        },
        "published_at": "2026-04-13T00:00:00+00:00",
        "model_version": "RuleExtractor",
        "raw_excerpt": "Mahomes is questionable for Sunday with an ankle sprain.",
    }


@pytest.fixture
def silver_week_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the enrichment module at a temp Silver tree.

    Returns the season=2025/week=01 directory so tests can drop JSON files
    into it directly.
    """
    silver_root = tmp_path / "data" / "silver" / "sentiment"
    signals_dir = silver_root / "signals" / "season=2025" / "week=01"
    signals_dir.mkdir(parents=True, exist_ok=True)

    # Redirect module-level constants to the tmp tree
    import src.sentiment.enrichment.llm_enrichment as mod

    monkeypatch.setattr(mod, "_SILVER_SIGNALS_DIR", silver_root / "signals")
    monkeypatch.setattr(mod, "_SILVER_ENRICHED_DIR", silver_root / "signals_enriched")
    return signals_dir


# ---------------------------------------------------------------------------
# Test 1: is_available is False without API key
# ---------------------------------------------------------------------------


def test_is_available_false_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMEnrichment().is_available is False when the env var is missing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    enrichment = LLMEnrichment()
    assert enrichment.is_available is False


# ---------------------------------------------------------------------------
# Test 2: enrich() returns record unchanged when unavailable
# ---------------------------------------------------------------------------


def test_enrich_passthrough_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    sample_silver_record: Dict[str, Any],
) -> None:
    """With no key present, enrich() returns the record unchanged."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    enrichment = LLMEnrichment()

    out = enrichment.enrich(sample_silver_record)

    assert "summary" not in out, "summary must NOT be added when unavailable"
    assert "refined_category" not in out, (
        "refined_category must NOT be added when unavailable"
    )
    # Event flags untouched
    assert out["events"] == sample_silver_record["events"]
    # Same identity semantics — either the same dict or an equal copy
    assert out["signal_id"] == sample_silver_record["signal_id"]


# ---------------------------------------------------------------------------
# Test 3: enrich() catches any SDK exception and fails open (D-06)
# ---------------------------------------------------------------------------


def test_enrich_fails_open_on_sdk_exception(
    monkeypatch: pytest.MonkeyPatch,
    sample_silver_record: Dict[str, Any],
) -> None:
    """enrich() catches any exception from the Anthropic SDK."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    enrichment = LLMEnrichment()
    # Force a client even if the SDK import failed in CI — we only care that
    # when .messages.create() raises, enrich() returns the record unchanged.
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("simulated API error")
    enrichment._client = mock_client  # type: ignore[attr-defined]

    out = enrichment.enrich(sample_silver_record)

    # Never raises, never adds enrichment fields
    assert "summary" not in out
    assert "refined_category" not in out
    # Event flags untouched
    assert out["events"] == sample_silver_record["events"]


# ---------------------------------------------------------------------------
# Test 4: enrich() success path populates summary and refined_category
# ---------------------------------------------------------------------------


def test_enrich_success_populates_summary_and_category(
    monkeypatch: pytest.MonkeyPatch,
    sample_silver_record: Dict[str, Any],
) -> None:
    """When the mocked client returns valid JSON, enrich() adds fields."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    enrichment = LLMEnrichment()

    # Build a fake Anthropic response: response.content[0].text
    fake_json = json.dumps(
        {
            "summary": "Mahomes is questionable for Sunday with an ankle issue.",
            "category": "injury",
        }
    )
    fake_content = MagicMock()
    fake_content.text = fake_json
    fake_response = MagicMock()
    fake_response.content = [fake_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = fake_response
    enrichment._client = mock_client  # type: ignore[attr-defined]

    out = enrichment.enrich(sample_silver_record)

    assert "summary" in out
    assert isinstance(out["summary"], str)
    assert 0 < len(out["summary"]) <= 200, "summary must be clamped to 200 chars"
    assert "refined_category" in out
    # Must be in the valid category allow-list
    valid_categories = {
        "injury",
        "usage",
        "trade",
        "weather",
        "motivation",
        "legal",
        "general",
    }
    assert out["refined_category"] in valid_categories
    # Original event flags never overwritten
    assert out["events"] == sample_silver_record["events"]


# ---------------------------------------------------------------------------
# Test 5: enrich_silver_records() with no files returns 0 and does not crash
# ---------------------------------------------------------------------------


def test_enrich_silver_records_no_files_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """enrich_silver_records() with an empty week returns 0 and does not raise."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Redirect to an empty tmp tree so we cannot pick up real Silver files
    import src.sentiment.enrichment.llm_enrichment as mod

    monkeypatch.setattr(mod, "_SILVER_SIGNALS_DIR", tmp_path / "signals_missing")
    monkeypatch.setattr(
        mod, "_SILVER_ENRICHED_DIR", tmp_path / "signals_enriched_missing"
    )

    count = enrich_silver_records(season=2026, week=1)
    assert count == 0


# ---------------------------------------------------------------------------
# Test 6: sidecar output goes to signals_enriched/, not signals/
# ---------------------------------------------------------------------------


def test_enrich_silver_records_writes_to_sidecar_path(
    monkeypatch: pytest.MonkeyPatch,
    silver_week_dir: Path,
    sample_silver_record: Dict[str, Any],
) -> None:
    """Enriched output is written to signals_enriched/, never to signals/."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-does-not-matter")

    # Drop a Silver envelope into the temp signals directory
    envelope = {
        "batch_id": "test-batch",
        "season": 2025,
        "week": 1,
        "computed_at": "2026-04-18T00:00:00+00:00",
        "signal_count": 1,
        "records": [sample_silver_record],
    }
    src_file = silver_week_dir / "signals_testbatch_20260418_000000.json"
    src_file.write_text(json.dumps(envelope), encoding="utf-8")

    # Capture the original contents so we can verify non-destructive behavior
    original_contents = src_file.read_text(encoding="utf-8")

    # Patch LLMEnrichment.enrich to a deterministic passthrough that adds fields.
    # This keeps the test hermetic (no real anthropic client construction).
    import src.sentiment.enrichment.llm_enrichment as mod

    def fake_enrich(
        self: Any, record: Dict[str, Any]  # noqa: ARG001
    ) -> Dict[str, Any]:
        enriched = dict(record)
        enriched["summary"] = "fake summary under 200 chars"
        enriched["refined_category"] = "injury"
        return enriched

    with patch.object(mod.LLMEnrichment, "enrich", fake_enrich):
        count = enrich_silver_records(season=2025, week=1)

    assert count == 1, "one record should have been enriched"

    # Sidecar file lives under signals_enriched/season=2025/week=01/
    enriched_dir = mod._SILVER_ENRICHED_DIR / "season=2025" / "week=01"
    assert enriched_dir.exists(), f"enriched dir should exist at {enriched_dir}"

    enriched_files: List[Path] = list(enriched_dir.glob("enriched_*.json"))
    assert len(enriched_files) >= 1, "at least one enriched sidecar should exist"

    # Payload shape: envelope with enriched records
    payload = json.loads(enriched_files[0].read_text(encoding="utf-8"))
    assert "records" in payload
    assert len(payload["records"]) == 1
    assert payload["records"][0].get("summary") == "fake summary under 200 chars"
    assert payload["records"][0].get("refined_category") == "injury"

    # Original file is UNTOUCHED (non-destructive contract)
    assert src_file.read_text(encoding="utf-8") == original_contents
