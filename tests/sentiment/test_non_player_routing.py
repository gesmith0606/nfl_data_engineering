"""Tests for non-player attribution routing (Plan 72-03 Task 1).

Covers EVT-02 hybrid attribution per CONTEXT D-02:

* ``ClaudeExtractor._parse_batch_response`` captures ``subject_type`` per
  non-player item dict (default ``"player"`` when absent; defensive
  coercion for unknown values).
* ``SentimentPipeline._route_non_player_items`` splits non-player items
  into 3 buckets:
    - ``rollup_items``: subject_type in {coach, team} AND team_abbr set
      (these contribute to the team rollup ``coach_news_count`` /
      ``team_news_count`` columns added in Task 2).
    - ``news_items``: subject_type in {coach, team, reporter} AND
      team_abbr set (written to the new ``non_player_news`` Silver
      sink).
    - ``leftover_items``: subject_type == "player" or team_abbr missing
      (kept in ``non_player_pending`` for human review).
* End-to-end: pipeline writes a non_player_news envelope under
  ``data/silver/sentiment/non_player_news/season=YYYY/week=WW/`` with the
  correct records, plus the existing non_player_pending envelope for
  leftovers, and the new counters on PipelineResult.
* Multi-batch accumulation contract (Test 7) — proves that the
  ``_run_claude_primary_loop`` body uses ``+=`` (not ``=``) on the new
  ``result.non_player_routed_count`` and ``result.non_player_news_count``
  counters. A regression to ``=`` would drop earlier batches' counts.

Test conventions match ``test_pipeline_claude_primary.py``:
* monkeypatch ``_PROJECT_ROOT`` and the four Silver dir constants
  (signals, processed-ids, unresolved, non_player_pending,
  non_player_news).
* Inject ``FakeClaudeClient`` via the ``claude_client=`` constructor seam.
* No live API calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from src.sentiment.processing.extractor import (
    ClaudeExtractor,
    _build_batched_prompt_for_sha,
    _coerce_subject_type,
)
from tests.sentiment.fakes import FakeClaudeClient, prompt_sha


# ---------------------------------------------------------------------------
# Fixtures (mirror test_pipeline_claude_primary.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_resolver() -> Any:
    """Resolver that returns deterministic player_id for any name."""

    class _FakeResolver:
        def resolve(self, name: str) -> Optional[str]:
            if not name:
                return None
            return f"id-{name.lower().replace(' ', '-')[:30]}"

    return _FakeResolver()


@pytest.fixture
def hermetic_tmp_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect pipeline _PROJECT_ROOT + all Silver sinks to tmp_path."""
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
    # Plan 72-03 Task 1 — new Silver sink for hybrid routing.
    monkeypatch.setattr(
        pipeline_pkg,
        "_NON_PLAYER_NEWS_DIR",
        tmp_path / "data" / "silver" / "sentiment" / "non_player_news",
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
    """Write a Bronze JSON file under tmp_root."""
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


def _register_fixture_sha_for_batch(
    fake: FakeClaudeClient,
    extractor: ClaudeExtractor,
    docs: List[Dict[str, Any]],
    response: List[Dict[str, Any]],
) -> str:
    """Register a response for the SHA of a single batch."""
    system, messages = _build_batched_prompt_for_sha(
        static_prefix=extractor._system_prefix_for_test(),
        roster_block=extractor._get_roster_block(),
        batch_docs=docs,
    )
    sha = prompt_sha(system, messages, extractor.model)
    fake.register_response(sha, response)
    return sha


# ---------------------------------------------------------------------------
# Tests 1-4 — extractor capture of subject_type
# ---------------------------------------------------------------------------


class TestSubjectTypeCapture:
    """``_parse_batch_response`` captures ``subject_type`` per non-player item.

    Plan 72-03 Task 1 — extracts the field with default 'player' for
    back-compat, and coerces unknown values to 'player' via the shared
    ``_coerce_subject_type`` helper.
    """

    def _make_extractor(self) -> ClaudeExtractor:
        ext = ClaudeExtractor(claude_client=FakeClaudeClient())
        ext.roster_provider = lambda: []
        return ext

    def test_subject_type_coach_captured_verbatim(self) -> None:
        """Item with subject_type='coach' is captured as 'coach'."""
        ext = self._make_extractor()
        docs = [
            {"external_id": "doc-1", "title": "x", "body_text": "Coach hire"}
        ]
        raw = json.dumps(
            [
                {
                    "doc_id": "doc-1",
                    "player_name": None,
                    "team_abbr": "KC",
                    "summary": "Andy Reid signs extension.",
                    "sentiment": 0.5,
                    "confidence": 0.9,
                    "category": "general",
                    "source_excerpt": "Reid extension.",
                    "subject_type": "coach",
                }
            ]
        )
        _, non_player_items = ext._parse_batch_response(raw, docs)
        assert len(non_player_items) == 1
        assert non_player_items[0]["subject_type"] == "coach"

    def test_subject_type_reporter_captured_verbatim(self) -> None:
        """Item with subject_type='reporter' is captured as 'reporter'."""
        ext = self._make_extractor()
        docs = [
            {"external_id": "doc-1", "title": "x", "body_text": "Schefter says"}
        ]
        raw = json.dumps(
            [
                {
                    "doc_id": "doc-1",
                    "player_name": None,
                    "team_abbr": "PHI",
                    "summary": "Schefter reports trade interest.",
                    "sentiment": 0.0,
                    "confidence": 0.7,
                    "category": "trade",
                    "source_excerpt": "Schefter reports.",
                    "subject_type": "reporter",
                }
            ]
        )
        _, non_player_items = ext._parse_batch_response(raw, docs)
        assert len(non_player_items) == 1
        assert non_player_items[0]["subject_type"] == "reporter"

    def test_subject_type_absent_defaults_to_player(self) -> None:
        """Item without subject_type → captured as 'player' (back-compat)."""
        ext = self._make_extractor()
        docs = [
            {"external_id": "doc-1", "title": "x", "body_text": "Update"}
        ]
        raw = json.dumps(
            [
                {
                    "doc_id": "doc-1",
                    "player_name": None,
                    "team_abbr": "DAL",
                    "summary": "Generic team news.",
                    "sentiment": 0.0,
                    "confidence": 0.5,
                    "category": "general",
                    "source_excerpt": "Team update.",
                    # No subject_type key — back-compat default.
                }
            ]
        )
        _, non_player_items = ext._parse_batch_response(raw, docs)
        assert len(non_player_items) == 1
        assert non_player_items[0]["subject_type"] == "player"

    def test_subject_type_garbage_coerced_to_player(self) -> None:
        """Unknown subject_type → coerced to 'player' (T-72-03-01)."""
        ext = self._make_extractor()
        docs = [
            {"external_id": "doc-1", "title": "x", "body_text": "x"}
        ]
        raw = json.dumps(
            [
                {
                    "doc_id": "doc-1",
                    "player_name": None,
                    "team_abbr": "BUF",
                    "summary": "Mystery item.",
                    "sentiment": 0.0,
                    "confidence": 0.5,
                    "category": "general",
                    "source_excerpt": "Mystery.",
                    "subject_type": "garbage",
                }
            ]
        )
        _, non_player_items = ext._parse_batch_response(raw, docs)
        assert len(non_player_items) == 1
        assert non_player_items[0]["subject_type"] == "player"

    def test_coerce_subject_type_helper_validates_enum(self) -> None:
        """Module-level coercion helper round-trips valid + normalises invalid."""
        # Valid values pass through.
        assert _coerce_subject_type("player") == "player"
        assert _coerce_subject_type("coach") == "coach"
        assert _coerce_subject_type("team") == "team"
        assert _coerce_subject_type("reporter") == "reporter"
        # Invalid / missing fall back to "player".
        assert _coerce_subject_type(None) == "player"
        assert _coerce_subject_type("") == "player"
        assert _coerce_subject_type("agent") == "player"
        assert _coerce_subject_type("OWNER") == "player"  # case-sensitive
        assert _coerce_subject_type(42) == "player"


# ---------------------------------------------------------------------------
# Test 5 — _route_non_player_items helper splits into 3-tuple
# ---------------------------------------------------------------------------


class TestRouteNonPlayerItems:
    """``_route_non_player_items`` splits items per CONTEXT D-02."""

    def _make_pipeline(self) -> Any:
        from src.sentiment.processing.pipeline import SentimentPipeline

        return SentimentPipeline(
            extractor_mode="claude_primary",
            claude_client=FakeClaudeClient(),
        )

    def test_route_splits_into_rollup_news_leftover(self) -> None:
        """Coach/team → rollup AND news; reporter → news only; player → leftover."""
        pipeline = self._make_pipeline()
        items = [
            {"subject_type": "coach", "team_abbr": "KC", "summary": "c1"},
            {"subject_type": "reporter", "team_abbr": "PHI", "summary": "r1"},
            {"subject_type": "team", "team_abbr": "BUF", "summary": "t1"},
            {"subject_type": "player", "team_abbr": None, "summary": "p1"},
        ]
        rollup_items, news_items, leftover_items = (
            pipeline._route_non_player_items(items)
        )
        assert len(rollup_items) == 2  # coach + team
        assert len(news_items) == 3  # coach + team + reporter
        assert len(leftover_items) == 1  # player with null team_abbr

        # Verify each bucket has the expected subject_type set.
        rollup_types = sorted(it["subject_type"] for it in rollup_items)
        assert rollup_types == ["coach", "team"]

        news_types = sorted(it["subject_type"] for it in news_items)
        assert news_types == ["coach", "reporter", "team"]

        assert leftover_items[0]["subject_type"] == "player"

    def test_route_drops_team_abbr_missing_for_attributable_types(self) -> None:
        """Coach/team/reporter without team_abbr → leftover (can't route)."""
        pipeline = self._make_pipeline()
        items = [
            {"subject_type": "coach", "team_abbr": None, "summary": "c"},
            {"subject_type": "reporter", "team_abbr": "", "summary": "r"},
        ]
        rollup_items, news_items, leftover_items = (
            pipeline._route_non_player_items(items)
        )
        assert rollup_items == []
        assert news_items == []
        assert len(leftover_items) == 2

    def test_route_handles_default_subject_type_missing_key(self) -> None:
        """Missing subject_type key → treated as 'player' default."""
        pipeline = self._make_pipeline()
        items = [
            {"team_abbr": "KC", "summary": "no-subject-type-key"},
        ]
        rollup_items, news_items, leftover_items = (
            pipeline._route_non_player_items(items)
        )
        assert rollup_items == []
        assert news_items == []
        assert len(leftover_items) == 1


# ---------------------------------------------------------------------------
# Test 6 — end-to-end pipeline run writes both envelopes + counters
# ---------------------------------------------------------------------------


def test_pipeline_routes_to_news_and_pending_envelopes(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
) -> None:
    """End-to-end: SentimentPipeline.run() splits non-player items per CONTEXT D-02.

    Bronze input has 1 doc that yields 3 non-player items (2 coach KC+PHI,
    1 reporter DAL). The pipeline:

    * Writes 3 records to non_player_news (coach KC, coach PHI, reporter DAL)
    * Writes 0 records to non_player_pending (no leftover items)
    * Sets ``result.non_player_routed_count == 2`` (coach + team only)
    * Sets ``result.non_player_news_count == 3`` (all attributable)
    * ``result.non_player_count == 3`` (existing total field unchanged)
    """
    items = [
        {
            "external_id": "doc-1",
            "source": "rss",
            "title": "Coach + reporter news",
            "body_text": "Multi-subject batch.",
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
            "doc_id": "doc-1",
            "player_name": None,
            "team_abbr": "KC",
            "sentiment": 0.2,
            "confidence": 0.7,
            "category": "general",
            "summary": "Reid extension.",
            "source_excerpt": "Reid signed.",
            "subject_type": "coach",
        },
        {
            "doc_id": "doc-1",
            "player_name": None,
            "team_abbr": "PHI",
            "sentiment": 0.3,
            "confidence": 0.7,
            "category": "general",
            "summary": "Sirianni extension.",
            "source_excerpt": "Sirianni signed.",
            "subject_type": "coach",
        },
        {
            "doc_id": "doc-1",
            "player_name": None,
            "team_abbr": "DAL",
            "sentiment": 0.1,
            "confidence": 0.6,
            "category": "general",
            "summary": "Schefter floats Cowboys trade.",
            "source_excerpt": "Schefter says.",
            "subject_type": "reporter",
        },
    ]
    _register_fixture_sha_for_batch(fake, pipeline._extractor, items, response)

    result = pipeline.run(season=2025, week=17, dry_run=False)

    # Counter contract: routed = team-rollup (coach+team), news = all attributable.
    assert result.non_player_count == 3
    assert result.non_player_routed_count == 2
    assert result.non_player_news_count == 3

    # non_player_news envelope (3 records: 2 coach + 1 reporter).
    news_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "non_player_news"
        / "season=2025"
        / "week=17"
    )
    news_files = list(news_dir.glob("non_player_news_*.json"))
    assert len(news_files) == 1
    news_envelope = json.loads(news_files[0].read_text())
    assert news_envelope["record_count"] == 3
    routed_subjects = sorted(r["subject_type"] for r in news_envelope["records"])
    assert routed_subjects == ["coach", "coach", "reporter"]

    # non_player_pending envelope: 0 leftover items, so no file written.
    pending_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "non_player_pending"
        / "season=2025"
        / "week=17"
    )
    pending_files = list(pending_dir.glob("non_player_*.json")) if pending_dir.exists() else []
    assert pending_files == []


def test_pipeline_writes_leftovers_to_pending_envelope(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
) -> None:
    """Player-typed items with null team_abbr land in non_player_pending."""
    items = [
        {
            "external_id": "doc-1",
            "source": "rss",
            "title": "Mystery name",
            "body_text": "An unknown subject is mentioned.",
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
            "doc_id": "doc-1",
            "player_name": None,
            "team_abbr": None,  # null team => leftover
            "sentiment": 0.0,
            "confidence": 0.5,
            "category": "general",
            "summary": "Mystery item.",
            "source_excerpt": "?",
            # subject_type omitted => defaults to player => leftover.
        },
    ]
    _register_fixture_sha_for_batch(fake, pipeline._extractor, items, response)

    result = pipeline.run(season=2025, week=17, dry_run=False)

    assert result.non_player_count == 1
    assert result.non_player_routed_count == 0
    assert result.non_player_news_count == 0

    pending_dir = (
        hermetic_tmp_tree
        / "data"
        / "silver"
        / "sentiment"
        / "non_player_pending"
        / "season=2025"
        / "week=17"
    )
    pending_files = list(pending_dir.glob("non_player_*.json"))
    assert len(pending_files) == 1
    pending_envelope = json.loads(pending_files[0].read_text())
    assert pending_envelope["record_count"] == 1


# ---------------------------------------------------------------------------
# Test 7 — multi-batch accumulation contract (the += vs = lock)
# ---------------------------------------------------------------------------


def test_routing_counters_accumulate_across_batches(
    hermetic_tmp_tree: Path,
    fake_resolver: Any,
) -> None:
    """Multi-batch contract: counters accumulate via += (not =).

    With batch_size=1 and 2 distinct Bronze docs, ``_run_claude_primary_loop``
    iterates twice. Each iteration's response yields routed and news items.
    The final ``PipelineResult`` MUST hold the SUM of per-batch counts —
    NOT just the last batch's count.

    This test would fail loudly with `expected 5, got 2` (or similar) if
    the implementation regressed from ``+=`` to ``=`` on either counter.
    """
    items = [
        {
            "external_id": "batch-A-doc",
            "source": "rss",
            "title": "Batch A",
            "body_text": "Batch A body.",
            "season": 2025,
            "week": 17,
        },
        {
            "external_id": "batch-B-doc",
            "source": "rss",
            "title": "Batch B",
            "body_text": "Batch B body.",
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
    pipeline._extractor.batch_size = 1  # Force one batch per doc.

    # Batch 1 (one of the 2 docs): 3 rollup-eligible (coach/team) + 0 reporter
    # so news_items has 3 (coach + team + team), rollup has 3.
    batch_1_response = [
        {
            "doc_id": "batch-A-doc",
            "player_name": None,
            "team_abbr": "KC",
            "sentiment": 0.0,
            "confidence": 0.7,
            "category": "general",
            "summary": "B1 coach.",
            "source_excerpt": "B1 coach.",
            "subject_type": "coach",
        },
        {
            "doc_id": "batch-A-doc",
            "player_name": None,
            "team_abbr": "PHI",
            "sentiment": 0.0,
            "confidence": 0.7,
            "category": "general",
            "summary": "B1 team-1.",
            "source_excerpt": "B1 team-1.",
            "subject_type": "team",
        },
        {
            "doc_id": "batch-A-doc",
            "player_name": None,
            "team_abbr": "BUF",
            "sentiment": 0.0,
            "confidence": 0.7,
            "category": "general",
            "summary": "B1 team-2.",
            "source_excerpt": "B1 team-2.",
            "subject_type": "team",
        },
    ]

    # Batch 2: 1 rollup-eligible (team) + 1 reporter (news only) =>
    # rollup_items=1, news_items=2.
    batch_2_response = [
        {
            "doc_id": "batch-B-doc",
            "player_name": None,
            "team_abbr": "DAL",
            "sentiment": 0.0,
            "confidence": 0.7,
            "category": "general",
            "summary": "B2 team-1.",
            "source_excerpt": "B2 team-1.",
            "subject_type": "team",
        },
        {
            "doc_id": "batch-B-doc",
            "player_name": None,
            "team_abbr": "MIN",
            "sentiment": 0.0,
            "confidence": 0.7,
            "category": "general",
            "summary": "B2 reporter.",
            "source_excerpt": "B2 reporter.",
            "subject_type": "reporter",
        },
    ]

    # Order within `unprocessed` is preserved by file-iteration order. The
    # registration order is irrelevant — the SHA depends on the prompt
    # content for each batch.
    _register_fixture_sha_for_batch(
        fake, pipeline._extractor, [items[0]], batch_1_response
    )
    _register_fixture_sha_for_batch(
        fake, pipeline._extractor, [items[1]], batch_2_response
    )

    result = pipeline.run(season=2025, week=17, dry_run=False)

    # Total non-player items across both batches = 3 + 2 = 5.
    assert result.non_player_count == 5

    # Routed (rollup destinations: coach + team only) = 3 (B1: coach + 2 team)
    # + 1 (B2: team) = 4.
    assert result.non_player_routed_count == 4, (
        "Expected 4 (3 from batch-1 + 1 from batch-2). "
        "If you see 1, the implementation regressed from '+=' to '=' "
        "and only the last batch's count was kept."
    )

    # News (coach + team + reporter, all attributable) = 3 (B1) + 2 (B2) = 5.
    assert result.non_player_news_count == 5, (
        "Expected 5 (3 from batch-1 + 2 from batch-2). "
        "If you see 2, the implementation regressed from '+=' to '=' "
        "and only the last batch's count was kept."
    )
