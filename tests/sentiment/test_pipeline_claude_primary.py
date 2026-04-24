"""Tests for the claude_primary mode wiring in ``SentimentPipeline`` (Plan 71-04).

Covers:

Task 1 — extractor mode routing + EXTRACTOR_MODE env + roster_provider factory:
* `SentimentPipeline(extractor_mode="claude_primary", claude_client=fake)` instantiates
  even when ANTHROPIC_API_KEY is unset.
* `SentimentPipeline(extractor_mode="claude_primary")` without a DI'd client and
  without ANTHROPIC_API_KEY falls back to RuleExtractor and logs a WARNING.
* `EXTRACTOR_MODE` env var triggers claude_primary when constructor arg is the default.
* Explicit constructor arg wins over env.
* `_roster_provider_factory(season)` returns a callable; calling it returns names
  if rosters parquet exists, else returns [] (no exception).
* `_build_extractor("claude_primary")` instantiates ClaudeExtractor with DI'd
  client / cost_log / roster_provider / batch_size correctly.
* When claude_primary is active, `self._rule_fallback` is also constructed.
* Back-compat: ``SentimentPipeline(extractor_mode="auto")`` still returns a
  RuleExtractor and ``result.is_claude_primary`` is False.

Task 2 — batched run loop + per-doc soft fallback + new sinks:
* Claude-primary mode writes Silver envelope with `"is_claude_primary": true`.
* `result.signal_count > 0`, `result.non_player_count >= 1` after a successful run.
* Failure-injected batch falls back to RuleExtractor per-doc; `claude_failed_count`
  reflects the batch size and fallback signals carry `extractor="rule"`.
* Non-player envelope written under `data/silver/sentiment/non_player_pending/`.
* `result.cost_usd_total > 0` after a successful run with cost_log.

Test conventions follow the existing sentiment-suite pattern:
* `monkeypatch.setattr(pipeline_pkg, "_PROJECT_ROOT", tmp_path)` for hermetic tree.
* `FakeClaudeClient` injected via `claude_client=` constructor seam (LLM-05).
* No live API calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from src.sentiment.processing.cost_log import CostLog
from src.sentiment.processing.extractor import (
    BATCH_SIZE,
    ClaudeExtractor,
    _build_batched_prompt_for_sha,
)
from src.sentiment.processing.rule_extractor import RuleExtractor
from tests.sentiment.fakes import FakeClaudeClient, prompt_sha


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_resolver() -> Any:
    """A resolver that returns a deterministic player_id for all names.

    The pipeline only needs ``.resolve(name)`` to return either a string id
    or None. We return a deterministic id for most names and None for one
    sentinel name to exercise the unresolved-names sink.
    """

    class _FakeResolver:
        def resolve(self, name: str) -> Optional[str]:
            if not name:
                return None
            # Sentinel: a Claude-extracted name that intentionally fails to resolve.
            if name.lower().startswith("unknown") or "carnell tate" in name.lower():
                return None
            return f"id-{name.lower().replace(' ', '-')[:30]}"

    return _FakeResolver()


@pytest.fixture
def hermetic_tmp_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect pipeline _PROJECT_ROOT to tmp_path for hermetic Silver writes.

    Returns the tmp_path so tests can build Bronze inputs under it.
    """
    import src.sentiment.processing.pipeline as pipeline_pkg

    monkeypatch.setattr(pipeline_pkg, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        pipeline_pkg,
        "_SILVER_SIGNALS_DIR",
        tmp_path / "data" / "silver" / "sentiment" / "signals",
    )
    monkeypatch.setattr(
        pipeline_pkg,
        "_PROCESSED_IDS_FILE",
        tmp_path / "data" / "silver" / "sentiment" / "processed_ids.json",
    )
    # Will be created by Task 2 — set up now so both tasks share the same tree.
    monkeypatch.setattr(
        pipeline_pkg,
        "_UNRESOLVED_DIR",
        tmp_path / "data" / "silver" / "sentiment" / "unresolved_names",
        raising=False,
    )
    monkeypatch.setattr(
        pipeline_pkg,
        "_NON_PLAYER_DIR",
        tmp_path / "data" / "silver" / "sentiment" / "non_player_pending",
        raising=False,
    )
    return tmp_path


def _write_bronze_doc_file(
    tmp_root: Path,
    season: int,
    week: int,
    items: List[Dict[str, Any]],
    source: str = "rss",
    filename: str = "sample.json",
) -> Path:
    """Write a Bronze JSON file at the conventional path under tmp_root.

    Mirrors the SENTIMENT_LOCAL_DIRS layout — uses 'rss' as the source
    directory so the existing _infer_source mapping works without monkeypatching.
    """
    bronze_dir = (
        tmp_root
        / "data"
        / "bronze"
        / "sentiment"
        / source
        / f"season={season}"
        / f"week={week:02d}"
    )
    bronze_dir.mkdir(parents=True, exist_ok=True)
    path = bronze_dir / filename
    path.write_text(json.dumps({"items": items}, indent=2))
    return path


def _seed_roster_parquet(tmp_root: Path, season: int, names: List[str]) -> Path:
    """Write a minimal Bronze rosters parquet so _roster_provider_factory finds it."""
    import pandas as pd

    rosters_dir = (
        tmp_root / "data" / "bronze" / "players" / "rosters" / f"season={season}"
    )
    rosters_dir.mkdir(parents=True, exist_ok=True)
    path = rosters_dir / "rosters_test.parquet"
    pd.DataFrame({"player_name": names, "team": ["KC"] * len(names)}).to_parquet(
        path, index=False
    )
    return path


# ---------------------------------------------------------------------------
# Task 1 tests — mode routing, env precedence, roster factory
# ---------------------------------------------------------------------------


def test_constructor_accepts_claude_primary_with_di_client_and_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DI'd client lets claude_primary mode work without ANTHROPIC_API_KEY."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EXTRACTOR_MODE", raising=False)
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(
        extractor_mode="claude_primary", claude_client=FakeClaudeClient()
    )
    assert pipeline._is_claude_primary is True
    assert isinstance(pipeline._extractor, ClaudeExtractor)
    # Soft-fallback rule extractor must be constructed when claude_primary active.
    assert isinstance(pipeline._rule_fallback, RuleExtractor)


def test_claude_primary_without_di_or_env_falls_back_to_rule_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Fail-open: claude_primary requested but no client => RuleExtractor + WARNING."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EXTRACTOR_MODE", raising=False)
    from src.sentiment.processing.pipeline import SentimentPipeline

    with caplog.at_level(logging.WARNING):
        pipeline = SentimentPipeline(extractor_mode="claude_primary")

    assert isinstance(pipeline._extractor, RuleExtractor)
    assert pipeline._is_claude_primary is False
    # WARNING text must mention the fallback path so ops can see why.
    assert any(
        "claude_primary" in rec.message.lower() and "fallback" in rec.message.lower()
        for rec in caplog.records
    )


def test_extractor_mode_env_var_overrides_default_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EXTRACTOR_MODE env wins when constructor arg is the default ``auto``."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("EXTRACTOR_MODE", "claude_primary")
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(claude_client=FakeClaudeClient())
    assert pipeline._is_claude_primary is True
    assert isinstance(pipeline._extractor, ClaudeExtractor)


def test_explicit_arg_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When extractor_mode != 'auto' is passed explicitly, env is ignored."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("EXTRACTOR_MODE", "claude_primary")
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(extractor_mode="rule")
    assert pipeline._is_claude_primary is False
    assert isinstance(pipeline._extractor, RuleExtractor)


def test_legacy_auto_mode_still_returns_rule_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Back-compat: default ``extractor_mode='auto'`` keeps RuleExtractor."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EXTRACTOR_MODE", raising=False)
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline()
    assert isinstance(pipeline._extractor, RuleExtractor)
    assert pipeline._is_claude_primary is False


def test_roster_provider_factory_returns_names_when_parquet_present(
    hermetic_tmp_tree: Path,
) -> None:
    """Factory returns a callable; callable returns names from the latest parquet."""
    _seed_roster_parquet(
        hermetic_tmp_tree, season=2026, names=["Patrick Mahomes", "Travis Kelce"]
    )
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(extractor_mode="rule")  # mode irrelevant here
    provider = pipeline._roster_provider_factory(2026)
    names = provider()
    assert "Patrick Mahomes" in names
    assert "Travis Kelce" in names


def test_roster_provider_factory_returns_empty_when_dir_missing(
    hermetic_tmp_tree: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing rosters dir => provider returns [] without raising."""
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(extractor_mode="rule")
    provider = pipeline._roster_provider_factory(1999)  # year with no parquet
    names = provider()
    assert names == []


def test_build_extractor_claude_primary_wires_di_client_and_cost_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The claude_primary branch passes through cost_log + client + batch_size."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake = FakeClaudeClient()
    cost_log = CostLog(base_dir=tmp_path)
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(
        extractor_mode="claude_primary",
        claude_client=fake,
        cost_log=cost_log,
    )
    extractor = pipeline._extractor
    assert isinstance(extractor, ClaudeExtractor)
    assert extractor._client is fake
    assert extractor.cost_log is cost_log
    assert extractor.batch_size == BATCH_SIZE


# ---------------------------------------------------------------------------
# Task 2 tests — batched run loop, soft fallback, sinks, envelope flag
# ---------------------------------------------------------------------------


def _register_fixture_sha_for_batch(
    fake: FakeClaudeClient,
    extractor: ClaudeExtractor,
    docs: List[Dict[str, Any]],
    response: List[Dict[str, Any]],
    *,
    register_failure: Optional[Exception] = None,
) -> str:
    """Register a response (or failure) for the SHA of a single batch."""
    system, messages = _build_batched_prompt_for_sha(
        static_prefix=extractor._system_prefix_for_test(),
        roster_block=extractor._get_roster_block(),
        batch_docs=docs,
    )
    sha = prompt_sha(system, messages, extractor.model)
    if register_failure is not None:
        fake.register_failure(sha, register_failure)
    else:
        fake.register_response(sha, response)
    return sha


def test_claude_primary_run_writes_envelope_with_is_claude_primary_flag(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
    tmp_path: Path,
) -> None:
    """End-to-end: claude_primary mode writes Silver envelope with the new flag.

    The envelope JSON's top-level dict must include ``"is_claude_primary": true``.
    `result.is_claude_primary` must be True. Cost total > 0 because the fake
    reports non-zero token counts on registered responses.
    """
    # Bronze: two docs in season=2025/week=17
    items = [
        {
            "external_id": "doc-1",
            "source": "rss",
            "title": "Mahomes update",
            "body_text": "Patrick Mahomes ankle sprain news.",
            "season": 2025,
            "week": 17,
        },
        {
            "external_id": "doc-2",
            "source": "rss",
            "title": "Coach hire",
            "body_text": "Bears hire new offensive coordinator.",
            "season": 2025,
            "week": 17,
        },
    ]
    _write_bronze_doc_file(hermetic_tmp_tree, 2025, 17, items)

    fake = FakeClaudeClient(strict=True)
    cost_log = CostLog(base_dir=tmp_path / "ops" / "llm_costs")
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(
        extractor_mode="claude_primary",
        claude_client=fake,
        resolver=fake_resolver,
        cost_log=cost_log,
    )
    # Override extractor batch_size + roster_provider to lambda:[] for SHA determinism.
    pipeline._extractor.roster_provider = lambda: []
    pipeline._extractor.batch_size = 8

    response = [
        {
            "doc_id": "doc-1",
            "player_name": "Patrick Mahomes",
            "sentiment": -0.3,
            "confidence": 0.8,
            "category": "injury",
            "events": {"is_questionable": True},
            "summary": "Mahomes ankle sprain — questionable.",
            "team_abbr": "KC",
            "source_excerpt": "Patrick Mahomes ankle sprain.",
        },
        {
            "doc_id": "doc-2",
            "player_name": None,
            "sentiment": 0.1,
            "confidence": 0.6,
            "category": "general",
            "events": {},
            "summary": "Bears hire OC.",
            "team_abbr": "CHI",
            "source_excerpt": "Bears hire new offensive coordinator.",
        },
    ]
    _register_fixture_sha_for_batch(
        fake, pipeline._extractor, items, response
    )

    result = pipeline.run(season=2025, week=17, dry_run=False)

    assert result.is_claude_primary is True
    assert result.signal_count >= 1
    assert result.non_player_count == 1
    assert result.processed_count == 2
    assert result.cost_usd_total > 0.0

    # Silver envelope: must carry the is_claude_primary flag.
    silver_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "signals"
        / "season=2025"
        / "week=17"
    )
    files = list(silver_dir.glob("signals_*.json"))
    assert len(files) == 1
    envelope = json.loads(files[0].read_text())
    assert envelope.get("is_claude_primary") is True
    assert envelope["signal_count"] >= 1
    # Each signal record carries the extractor provenance.
    for rec in envelope["records"]:
        assert rec["extractor"] == "claude_primary"


def test_claude_primary_writes_non_player_envelope(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
    tmp_path: Path,
) -> None:
    """Non-player items are persisted to data/silver/sentiment/non_player_pending/."""
    items = [
        {
            "external_id": "doc-100",
            "source": "rss",
            "title": "Coaching change",
            "body_text": "The team hired a new OC.",
            "season": 2025,
            "week": 17,
        },
    ]
    _write_bronze_doc_file(hermetic_tmp_tree, 2025, 17, items)

    fake = FakeClaudeClient(strict=True)
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(
        extractor_mode="claude_primary",
        claude_client=fake,
        resolver=fake_resolver,
    )
    pipeline._extractor.roster_provider = lambda: []
    pipeline._extractor.batch_size = 8

    response = [
        {
            "doc_id": "doc-100",
            "player_name": None,
            "sentiment": 0.0,
            "confidence": 0.5,
            "category": "general",
            "events": {},
            "summary": "OC hired.",
            "team_abbr": "DAL",
            "source_excerpt": "New OC hired.",
        },
    ]
    _register_fixture_sha_for_batch(fake, pipeline._extractor, items, response)

    result = pipeline.run(season=2025, week=17, dry_run=False)

    assert result.non_player_count == 1
    non_player_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "non_player_pending"
        / "season=2025"
        / "week=17"
    )
    files = list(non_player_dir.glob("non_player_*.json"))
    assert len(files) == 1
    envelope = json.loads(files[0].read_text())
    assert envelope["record_count"] == 1
    assert envelope["records"][0]["team_abbr"] == "DAL"
    assert envelope["records"][0]["doc_id"] == "doc-100"


def test_claude_primary_writes_unresolved_names_envelope(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
    tmp_path: Path,
) -> None:
    """When resolver.resolve returns None, name lands in the unresolved sink."""
    items = [
        {
            "external_id": "doc-200",
            "source": "rss",
            "title": "Prospect rising",
            "body_text": "Carnell Tate rising up the boards.",
            "season": 2025,
            "week": 17,
        },
    ]
    _write_bronze_doc_file(hermetic_tmp_tree, 2025, 17, items)

    fake = FakeClaudeClient(strict=True)
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(
        extractor_mode="claude_primary",
        claude_client=fake,
        resolver=fake_resolver,
    )
    pipeline._extractor.roster_provider = lambda: []
    pipeline._extractor.batch_size = 8

    response = [
        {
            "doc_id": "doc-200",
            "player_name": "Carnell Tate",  # fake_resolver returns None for this
            "sentiment": 0.4,
            "confidence": 0.7,
            "category": "general",
            "events": {},
            "summary": "Prospect news.",
            "team_abbr": None,
            "source_excerpt": "Carnell Tate rising.",
        },
    ]
    _register_fixture_sha_for_batch(fake, pipeline._extractor, items, response)

    result = pipeline.run(season=2025, week=17, dry_run=False)

    assert result.unresolved_player_count == 1
    unresolved_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "unresolved_names"
        / "season=2025"
        / "week=17"
    )
    files = list(unresolved_dir.glob("unresolved_*.json"))
    assert len(files) == 1
    envelope = json.loads(files[0].read_text())
    assert envelope["record_count"] == 1
    assert envelope["records"][0]["player_name"] == "Carnell Tate"


def test_batch_failure_falls_back_to_rule_per_doc(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
    tmp_path: Path,
) -> None:
    """API failure on a batch => RuleExtractor handles each doc individually.

    Asserts:
    * `result.claude_failed_count` == batch size
    * Silver records for those docs carry `extractor="rule"` (the fallback path)
    """
    items = [
        {
            "external_id": "doc-A",
            "source": "rss",
            "title": "Mahomes ruled out",
            "body_text": (
                "Patrick Mahomes ruled out for Sunday's game with an ankle sprain. "
                "He will not play this week."
            ),
            "season": 2025,
            "week": 18,
        },
    ]
    _write_bronze_doc_file(hermetic_tmp_tree, 2025, 18, items)

    fake = FakeClaudeClient(strict=True)
    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(
        extractor_mode="claude_primary",
        claude_client=fake,
        resolver=fake_resolver,
    )
    pipeline._extractor.roster_provider = lambda: []
    pipeline._extractor.batch_size = 8

    # Inject API failure for this batch's SHA.
    _register_fixture_sha_for_batch(
        fake,
        pipeline._extractor,
        items,
        response=[],
        register_failure=RuntimeError("simulated API outage"),
    )

    result = pipeline.run(season=2025, week=18, dry_run=False)

    assert result.claude_failed_count == 1
    assert result.processed_count == 1  # doc still gets processed via fallback

    # Silver envelope should still exist; records (if any) must be from rule path.
    silver_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "signals"
        / "season=2025"
        / "week=18"
    )
    files = list(silver_dir.glob("signals_*.json"))
    if files:
        envelope = json.loads(files[0].read_text())
        for rec in envelope["records"]:
            assert rec["extractor"] == "rule"


def test_legacy_auto_mode_run_does_not_set_is_claude_primary(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
) -> None:
    """Regression: `extractor_mode='auto'` => result.is_claude_primary is False.

    Envelope must NOT contain `is_claude_primary=true` (key may be absent or false).
    """
    items = [
        {
            "external_id": "doc-legacy-1",
            "source": "rss",
            "title": "Mahomes ruled out",
            "body_text": "Patrick Mahomes ruled out for Sunday with ankle injury.",
            "season": 2025,
            "week": 17,
        },
    ]
    _write_bronze_doc_file(hermetic_tmp_tree, 2025, 17, items)

    from src.sentiment.processing.pipeline import SentimentPipeline

    pipeline = SentimentPipeline(extractor_mode="auto", resolver=fake_resolver)
    result = pipeline.run(season=2025, week=17, dry_run=False)

    assert result.is_claude_primary is False
    silver_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "signals"
        / "season=2025"
        / "week=17"
    )
    files = list(silver_dir.glob("signals_*.json"))
    if files:
        envelope = json.loads(files[0].read_text())
        # is_claude_primary either absent or False — never True for auto/rule.
        assert envelope.get("is_claude_primary", False) is False
