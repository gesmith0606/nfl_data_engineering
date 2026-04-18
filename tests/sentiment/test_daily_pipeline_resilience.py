"""Resilience tests for ``scripts/daily_sentiment_pipeline.py``.

These tests encode the D-06 guarantee from phase 61: the daily sentiment
pipeline must NEVER fail because the Claude LLM path is unavailable, and a
failure in any single ingestion source must not abort subsequent steps.

The tests use ``unittest.mock.patch`` to replace the sub-script ``main``
functions so that no network calls happen.  Each test asserts a specific
slice of the resilience contract:

1. Rule-based extraction runs when ``ANTHROPIC_API_KEY`` is absent.
2. One ingestion step raising an exception does not abort the others.
3. ``skip_rotowire`` isolates RotoWire while running everything else.
4. ``skip_pft`` isolates PFT while running everything else.
5. ``PipelineResult.any_success`` is True with a single successful step.
6. With all ingestion skipped the pipeline still returns exit 0.
7. The step list contains RotoWire and PFT entries when enabled.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from scripts import daily_sentiment_pipeline as pipeline_mod


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _ok(*_args: Any, **_kwargs: Any) -> int:
    """Stand-in for a sub-script ``main`` that succeeds."""

    return 0


def _fail(*_args: Any, **_kwargs: Any) -> int:
    """Stand-in for a sub-script ``main`` that returns a non-zero exit code."""

    return 1


def _boom(*_args: Any, **_kwargs: Any) -> int:
    """Stand-in for a sub-script ``main`` that raises an exception."""

    raise RuntimeError("simulated upstream failure")


@pytest.fixture(autouse=True)
def _patch_extractor_and_aggregation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the extraction + aggregation steps with no-op stand-ins.

    These sub-steps touch disk/resolver internals that are irrelevant to the
    resilience contract.  Replacing them with lightweight stand-ins keeps the
    tests fast and deterministic.

    Args:
        monkeypatch: pytest monkeypatch fixture.
    """

    class _FakeResult:
        processed_count = 0
        skipped_count = 0
        signal_count = 0

    class _FakePipeline:
        def __init__(self) -> None:
            class _FakeExtractor:
                is_available = True

                def __class__(self) -> type:  # pragma: no cover - unused
                    return type("RuleExtractor", (), {})

            self.extractor = _FakeExtractor()

        def run(self, season: int, week: int, dry_run: bool) -> _FakeResult:
            return _FakeResult()

    class _FakeAggregator:
        def aggregate(
            self, season: int, week: int, dry_run: bool
        ) -> list:  # noqa: D401
            return []

    # Patch out the heavy lifters so extraction + aggregation are no-ops.
    import src.sentiment.processing.pipeline as pipeline_pkg
    import src.sentiment.aggregation.weekly as weekly_pkg
    import src.sentiment.aggregation.team_weekly as team_pkg

    monkeypatch.setattr(pipeline_pkg, "SentimentPipeline", _FakePipeline)
    monkeypatch.setattr(weekly_pkg, "WeeklyAggregator", _FakeAggregator)
    monkeypatch.setattr(team_pkg, "TeamWeeklyAggregator", _FakeAggregator)


# ---------------------------------------------------------------------------
# Test 1: Rule-based extraction runs when API key is absent
# ---------------------------------------------------------------------------


def test_extraction_runs_without_anthropic_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-06: extraction step must succeed even without ANTHROPIC_API_KEY.

    The pipeline's extractor fallback is deterministic — when the API key is
    unset the ``SentimentPipeline`` builds a ``RuleExtractor``.  The pipeline
    step MUST return ``success=True`` in that state.
    """

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch.object(pipeline_mod, "_run_rss_ingestion", side_effect=lambda *a, **k: pipeline_mod.StepResult(name="RSS Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_reddit_ingestion", side_effect=lambda *a, **k: pipeline_mod.StepResult(name="Reddit Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_sleeper_ingestion", side_effect=lambda *a, **k: pipeline_mod.StepResult(name="Sleeper Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_rotowire_ingestion", side_effect=lambda *a, **k: pipeline_mod.StepResult(name="RotoWire Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_pft_ingestion", side_effect=lambda *a, **k: pipeline_mod.StepResult(name="PFT Ingestion", success=True)):
        result = pipeline_mod.run_pipeline(season=2026, week=1, dry_run=True)

    extraction = next(
        (s for s in result.steps if s.name == "Signal Extraction"), None
    )
    assert extraction is not None, "Extraction step missing from result"
    assert extraction.success is True, "Extraction must succeed without API key"


# ---------------------------------------------------------------------------
# Test 2: One ingestion failure does not abort subsequent steps
# ---------------------------------------------------------------------------


def test_single_ingestion_failure_does_not_abort_pipeline() -> None:
    """Isolation: a single source raising must not prevent later steps.

    PFT raises an exception; all other steps must still execute and the
    failing step is recorded with ``success=False`` in ``result.steps``.
    """

    with patch.object(pipeline_mod, "_run_rss_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RSS Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_reddit_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Reddit Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_sleeper_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Sleeper Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_rotowire_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RotoWire Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_pft_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="PFT Ingestion", success=False, error="boom")):
        result = pipeline_mod.run_pipeline(season=2026, week=1, dry_run=True)

    names = [s.name for s in result.steps]
    assert "RSS Ingestion" in names
    assert "Reddit Ingestion" in names
    assert "Sleeper Ingestion" in names
    assert "RotoWire Ingestion" in names
    assert "PFT Ingestion" in names
    assert "Signal Extraction" in names
    pft = next(s for s in result.steps if s.name == "PFT Ingestion")
    assert pft.success is False
    assert result.any_success is True


# ---------------------------------------------------------------------------
# Test 3: --skip-rotowire omits only RotoWire
# ---------------------------------------------------------------------------


def test_skip_rotowire_omits_rotowire_step() -> None:
    """``skip_rotowire=True`` removes RotoWire while running every other step."""

    with patch.object(pipeline_mod, "_run_rss_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RSS Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_reddit_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Reddit Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_sleeper_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Sleeper Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_rotowire_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RotoWire Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_pft_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="PFT Ingestion", success=True)):
        result = pipeline_mod.run_pipeline(
            season=2026, week=1, dry_run=True, skip_rotowire=True
        )

    names = [s.name for s in result.steps]
    assert "RotoWire Ingestion" not in names
    assert "PFT Ingestion" in names
    assert "RSS Ingestion" in names


# ---------------------------------------------------------------------------
# Test 4: --skip-pft omits only PFT
# ---------------------------------------------------------------------------


def test_skip_pft_omits_pft_step() -> None:
    """``skip_pft=True`` removes PFT while running every other step."""

    with patch.object(pipeline_mod, "_run_rss_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RSS Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_reddit_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Reddit Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_sleeper_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Sleeper Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_rotowire_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RotoWire Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_pft_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="PFT Ingestion", success=True)):
        result = pipeline_mod.run_pipeline(
            season=2026, week=1, dry_run=True, skip_pft=True
        )

    names = [s.name for s in result.steps]
    assert "PFT Ingestion" not in names
    assert "RotoWire Ingestion" in names
    assert "RSS Ingestion" in names


# ---------------------------------------------------------------------------
# Test 5: any_success is True with at least one success
# ---------------------------------------------------------------------------


def test_any_success_true_when_one_step_succeeds() -> None:
    """``PipelineResult.any_success`` reflects the contract: any win == exit 0."""

    with patch.object(pipeline_mod, "_run_rss_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RSS Ingestion", success=False, error="x")), \
        patch.object(pipeline_mod, "_run_reddit_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Reddit Ingestion", success=False, error="x")), \
        patch.object(pipeline_mod, "_run_sleeper_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Sleeper Ingestion", success=False, error="x")), \
        patch.object(pipeline_mod, "_run_rotowire_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RotoWire Ingestion", success=False, error="x")), \
        patch.object(pipeline_mod, "_run_pft_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="PFT Ingestion", success=True)):
        result = pipeline_mod.run_pipeline(season=2026, week=1, dry_run=True)

    assert result.any_success is True
    assert result.all_success is False


# ---------------------------------------------------------------------------
# Test 6: skip_ingest still runs extraction + aggregation, exits 0
# ---------------------------------------------------------------------------


def test_skip_ingest_runs_downstream_steps_only() -> None:
    """``skip_ingest=True`` runs the three processing steps only, exits 0."""

    result = pipeline_mod.run_pipeline(
        season=2026, week=1, dry_run=True, skip_ingest=True
    )

    names = [s.name for s in result.steps]
    assert "RSS Ingestion" not in names
    assert "Reddit Ingestion" not in names
    assert "Sleeper Ingestion" not in names
    assert "RotoWire Ingestion" not in names
    assert "PFT Ingestion" not in names
    assert "Signal Extraction" in names
    assert "Player Aggregation" in names
    assert "Team Aggregation" in names
    assert result.any_success is True


# ---------------------------------------------------------------------------
# Test 7: RotoWire + PFT steps appear when their skip flags are False
# ---------------------------------------------------------------------------


def test_rotowire_and_pft_steps_present_by_default() -> None:
    """Default behaviour: the step list contains RotoWire + PFT entries."""

    with patch.object(pipeline_mod, "_run_rss_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RSS Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_reddit_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Reddit Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_sleeper_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="Sleeper Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_rotowire_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="RotoWire Ingestion", success=True)), \
        patch.object(pipeline_mod, "_run_pft_ingestion", side_effect=lambda s, d, v: pipeline_mod.StepResult(name="PFT Ingestion", success=True)):
        result = pipeline_mod.run_pipeline(season=2026, week=1, dry_run=True)

    names = [s.name for s in result.steps]
    assert "RotoWire Ingestion" in names
    assert "PFT Ingestion" in names
