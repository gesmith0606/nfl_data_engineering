"""Schema contract tests for Phase 71 LLM-primary extraction.

These tests LOCK the additive schema evolution introduced by Plan 71-01
before Plans 71-02..05 consume the contracts. Every assertion is
deliberately narrow — rename or removal of any existing field would
break these tests, which is the intended guardrail.

Covers:

* PlayerSignal new optional fields (summary, source_excerpt,
  team_abbr, extractor) with documented defaults.
* Module-level extractor-name + batch-size constants.
* PipelineResult new optional counter / flag / cost fields.
* Silver record shape additions (extractor + summary top-level keys).
* ClaudeClient Protocol importability and runtime structural check.
* Legacy ClaudeExtractor class remains instantiable (no regressions).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class PlayerSignalNewFieldsTests(unittest.TestCase):
    """Task 1: new optional fields on PlayerSignal keep defaults safe."""

    def test_player_signal_constructs_with_legacy_required_fields(self) -> None:
        """Existing call sites (RuleExtractor, ClaudeExtractor) still work."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="Travis Kelce",
            sentiment=0.0,
            confidence=0.5,
            category="general",
        )

        self.assertEqual(signal.player_name, "Travis Kelce")
        self.assertEqual(signal.sentiment, 0.0)
        self.assertEqual(signal.confidence, 0.5)
        self.assertEqual(signal.category, "general")

    def test_summary_defaults_to_empty_string(self) -> None:
        """summary is Claude-generated; defaults to "" for rule path."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x", sentiment=0.0, confidence=0.5, category="general"
        )
        self.assertEqual(signal.summary, "")

    def test_source_excerpt_defaults_to_empty_string(self) -> None:
        """source_excerpt defaults to "" when absent."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x", sentiment=0.0, confidence=0.5, category="general"
        )
        self.assertEqual(signal.source_excerpt, "")

    def test_team_abbr_defaults_to_none(self) -> None:
        """team_abbr populated only on non-player items / optional enrichment."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x", sentiment=0.0, confidence=0.5, category="general"
        )
        self.assertIsNone(signal.team_abbr)

    def test_extractor_defaults_to_rule(self) -> None:
        """extractor defaults to "rule" preserves back-compat on old runs."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x", sentiment=0.0, confidence=0.5, category="general"
        )
        self.assertEqual(signal.extractor, "rule")

    def test_player_signal_to_dict_includes_new_keys(self) -> None:
        """to_dict() returns all four new top-level keys alongside existing."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="Patrick Mahomes",
            sentiment=0.2,
            confidence=0.8,
            category="usage",
            summary="Mahomes practiced fully",
            source_excerpt="Mahomes was a full participant in practice...",
            team_abbr="KC",
            extractor="claude_primary",
        )

        d = signal.to_dict()

        # New top-level keys
        self.assertIn("summary", d)
        self.assertIn("source_excerpt", d)
        self.assertIn("team_abbr", d)
        self.assertIn("extractor", d)
        self.assertEqual(d["summary"], "Mahomes practiced fully")
        self.assertEqual(
            d["source_excerpt"], "Mahomes was a full participant in practice..."
        )
        self.assertEqual(d["team_abbr"], "KC")
        self.assertEqual(d["extractor"], "claude_primary")

        # Existing keys still present and events sub-dict intact
        self.assertIn("events", d)
        self.assertIsInstance(d["events"], dict)
        self.assertIn("is_ruled_out", d["events"])
        self.assertIn("is_weather_risk", d["events"])
        self.assertEqual(d["player_name"], "Patrick Mahomes")
        self.assertEqual(d["sentiment"], 0.2)
        self.assertEqual(d["confidence"], 0.8)
        self.assertEqual(d["category"], "usage")


class ExtractorConstantsTests(unittest.TestCase):
    """Task 1: module-level extractor name and batch size constants."""

    def test_extractor_name_constants_exist_with_expected_values(self) -> None:
        """All three extractor identity strings are single-source-of-truth."""
        from src.sentiment.processing.extractor import (
            _EXTRACTOR_NAME_CLAUDE_LEGACY,
            _EXTRACTOR_NAME_CLAUDE_PRIMARY,
            _EXTRACTOR_NAME_RULE,
        )

        self.assertEqual(_EXTRACTOR_NAME_RULE, "rule")
        self.assertEqual(_EXTRACTOR_NAME_CLAUDE_PRIMARY, "claude_primary")
        self.assertEqual(_EXTRACTOR_NAME_CLAUDE_LEGACY, "claude_legacy")

    def test_batch_size_default_is_eight(self) -> None:
        """Default batch size is 8 per Decision D-01 (range 5-10)."""
        from src.sentiment.processing.extractor import BATCH_SIZE

        self.assertEqual(BATCH_SIZE, 8)


class PipelineResultNewFieldsTests(unittest.TestCase):
    """Task 2: PipelineResult gains 6 optional counter/flag/cost fields."""

    def test_pipeline_result_new_counts(self) -> None:
        """All 6 new fields default to documented zero/empty/False values."""
        from src.sentiment.processing.pipeline import PipelineResult

        result = PipelineResult()

        # New counter fields default to 0 / False / 0.0
        self.assertEqual(result.claude_failed_count, 0)
        self.assertEqual(result.unresolved_player_count, 0)
        self.assertEqual(result.non_player_count, 0)
        self.assertEqual(result.non_player_items, [])
        self.assertIs(result.is_claude_primary, False)
        self.assertEqual(result.cost_usd_total, 0.0)

        # Existing 5 fields still default as before
        self.assertEqual(result.processed_count, 0)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(result.signal_count, 0)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.output_files, [])

    def test_non_player_items_default_factory_not_shared(self) -> None:
        """Each PipelineResult gets its own non_player_items list."""
        from src.sentiment.processing.pipeline import PipelineResult

        r1 = PipelineResult()
        r2 = PipelineResult()
        r1.non_player_items.append({"team_abbr": "KC"})
        self.assertEqual(len(r1.non_player_items), 1)
        self.assertEqual(len(r2.non_player_items), 0)


class SilverRecordExtractorFieldTests(unittest.TestCase):
    """Task 2: _build_silver_record emits new top-level extractor + summary."""

    def _build_pipeline(self):
        """Construct a pipeline with a stub resolver to avoid data lookups."""
        from src.sentiment.processing.pipeline import SentimentPipeline

        class _StubResolver:
            def resolve(self, name):  # type: ignore[no-untyped-def]
                return None

        # Stub resolver and force rule mode so no external deps load.
        return SentimentPipeline(resolver=_StubResolver(), extractor_mode="rule")

    def test_silver_record_extractor_field_defaults_to_rule(self) -> None:
        """Default PlayerSignal + stub doc -> record['extractor'] == 'rule'."""
        from src.sentiment.processing.extractor import PlayerSignal

        pipeline = self._build_pipeline()
        signal = PlayerSignal(
            player_name="X",
            sentiment=0.1,
            confidence=0.5,
            category="general",
        )
        record = pipeline._build_silver_record(
            doc={"external_id": "doc_1"},
            signal=signal,
            player_id="00-0001",
            season=2025,
            week=17,
            source="rss",
        )

        self.assertIn("extractor", record)
        self.assertIn("summary", record)
        self.assertEqual(record["extractor"], "rule")
        self.assertEqual(record["summary"], "")

        # Existing keys must remain intact
        self.assertEqual(record["player_id"], "00-0001")
        self.assertEqual(record["season"], 2025)
        self.assertEqual(record["week"], 17)
        self.assertIn("events", record)
        self.assertIn("raw_excerpt", record)

    def test_silver_record_extractor_field_reflects_claude_primary(self) -> None:
        """Claude-primary signal -> record reflects extractor + summary."""
        from src.sentiment.processing.extractor import PlayerSignal

        pipeline = self._build_pipeline()
        signal = PlayerSignal(
            player_name="Travis Kelce",
            sentiment=-0.3,
            confidence=0.85,
            category="injury",
            summary="Kelce limited at practice",
            source_excerpt="Travis Kelce was listed as a limited participant",
            team_abbr="KC",
            extractor="claude_primary",
        )
        record = pipeline._build_silver_record(
            doc={"external_id": "doc_2", "source": "rss_espn"},
            signal=signal,
            player_id="00-0030506",
            season=2025,
            week=18,
            source="rss",
        )

        self.assertEqual(record["extractor"], "claude_primary")
        self.assertEqual(record["summary"], "Kelce limited at practice")


class PlayerSignalDraftSeasonFlagsTests(unittest.TestCase):
    """Plan 72-01 Task 1: 7 new draft-season event flags on PlayerSignal.

    Each new flag must:

    1. Default to ``False`` when not passed to the constructor.
    2. Round-trip through ``to_dict()['events']`` (additive only — the
       existing 12 keys must still be present).
    3. Carry the canonical key name (lower-snake-case ``is_<event>``).

    The 7 new flags (locked by 72-CONTEXT D-01):

    * ``is_drafted`` — player was selected in the NFL Draft.
    * ``is_rumored_destination`` — speculation that a player will land
      with a specific team (different from confirmed ``is_traded``).
    * ``is_coaching_change`` — head coach / coordinator hire-or-fire.
    * ``is_trade_buzz`` — soft trade speculation
      (different from ``is_rumored_destination`` which names a team).
    * ``is_holdout`` — player skipping minicamp / OTAs / training camp
      over contract dispute.
    * ``is_cap_cut`` — release driven by salary-cap considerations
      (more specific than ``is_released``).
    * ``is_rookie_buzz`` — pre-draft prospect hype / draft-board surge.
    """

    NEW_FLAGS = (
        "is_drafted",
        "is_rumored_destination",
        "is_coaching_change",
        "is_trade_buzz",
        "is_holdout",
        "is_cap_cut",
        "is_rookie_buzz",
    )

    def test_seven_new_flags_default_false(self) -> None:
        """All 7 new event flags default to False when not passed."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x",
            sentiment=0.0,
            confidence=0.5,
            category="general",
        )
        for flag in self.NEW_FLAGS:
            self.assertFalse(
                getattr(signal, flag),
                f"{flag} should default to False",
            )

    def test_seven_new_flags_constructible_as_kwargs(self) -> None:
        """PlayerSignal accepts each new flag as a keyword argument."""
        from src.sentiment.processing.extractor import PlayerSignal

        for flag in self.NEW_FLAGS:
            kwargs = {flag: True}
            signal = PlayerSignal(
                player_name="x",
                sentiment=0.0,
                confidence=0.5,
                category="general",
                **kwargs,
            )
            self.assertTrue(
                getattr(signal, flag),
                f"{flag} should be True after PlayerSignal({flag}=True)",
            )

    def test_to_dict_events_contains_all_nineteen_flag_keys(self) -> None:
        """to_dict()['events'] contains 12 existing + 7 new = 19 keys."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x",
            sentiment=0.0,
            confidence=0.5,
            category="general",
            is_drafted=True,
            is_coaching_change=True,
        )
        d = signal.to_dict()
        events = d["events"]

        # All 12 existing flags must remain
        for key in (
            "is_ruled_out",
            "is_inactive",
            "is_questionable",
            "is_suspended",
            "is_returning",
            "is_traded",
            "is_released",
            "is_signed",
            "is_activated",
            "is_usage_boost",
            "is_usage_drop",
            "is_weather_risk",
        ):
            self.assertIn(key, events, f"existing flag {key} missing")

        # All 7 new flags must be present
        for key in self.NEW_FLAGS:
            self.assertIn(key, events, f"new flag {key} missing")

        # Cardinality is exactly 19
        self.assertEqual(
            len(events),
            19,
            f"events sub-dict should have exactly 19 keys, got {len(events)}",
        )

        # The two flags we set explicitly are True; the others False
        self.assertTrue(events["is_drafted"])
        self.assertTrue(events["is_coaching_change"])
        for flag in self.NEW_FLAGS:
            if flag in ("is_drafted", "is_coaching_change"):
                continue
            self.assertFalse(events[flag], f"{flag} should be False")

    def test_event_flag_keys_frozenset_cardinality_is_nineteen(self) -> None:
        """``_EVENT_FLAG_KEYS`` extends to 19 entries (12 + 7 new)."""
        from src.sentiment.processing.extractor import _EVENT_FLAG_KEYS

        self.assertEqual(
            len(_EVENT_FLAG_KEYS),
            19,
            f"_EVENT_FLAG_KEYS should have 19 entries, got {len(_EVENT_FLAG_KEYS)}",
        )
        for key in self.NEW_FLAGS:
            self.assertIn(
                key,
                _EVENT_FLAG_KEYS,
                f"_EVENT_FLAG_KEYS missing {key}",
            )

    def test_extraction_prompt_enumerates_new_flags(self) -> None:
        """``EXTRACTION_PROMPT`` enumerates each of the 7 new flags."""
        from src.sentiment.processing.extractor import EXTRACTION_PROMPT

        for key in self.NEW_FLAGS:
            self.assertIn(
                key,
                EXTRACTION_PROMPT,
                f"EXTRACTION_PROMPT missing flag name {key}",
            )

    def test_system_prefix_enumerates_new_flags(self) -> None:
        """``_SYSTEM_PREFIX`` enumerates each of the 7 new flags."""
        from src.sentiment.processing.extractor import _SYSTEM_PREFIX

        for key in self.NEW_FLAGS:
            self.assertIn(
                key,
                _SYSTEM_PREFIX,
                f"_SYSTEM_PREFIX missing flag name {key}",
            )


class PlayerSignalSubjectTypeTests(unittest.TestCase):
    """Plan 72-01 Task 1: ``subject_type`` field on PlayerSignal.

    ``subject_type`` is a 4-value string enum
    ({"player", "coach", "team", "reporter"}) defaulting to ``"player"``
    for back-compat with the rule path (which only emits player items).

    Phase 72 EVT-02 routes ``coach``/``team`` to a team rollup and
    ``reporter`` to the ``non_player_news`` Silver channel. Until that
    plan, the field is purely a schema additive.

    Threat T-72-01-01: tampering on ``subject_type`` is mitigated via
    ``__post_init__`` validation — invalid input falls back to
    ``"player"``.
    """

    def test_subject_type_defaults_to_player(self) -> None:
        """subject_type defaults to "player" when not passed."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x",
            sentiment=0.0,
            confidence=0.5,
            category="general",
        )
        self.assertEqual(signal.subject_type, "player")

    def test_subject_type_accepts_four_valid_values(self) -> None:
        """All four enum values round-trip through PlayerSignal."""
        from src.sentiment.processing.extractor import PlayerSignal

        for value in ("player", "coach", "team", "reporter"):
            signal = PlayerSignal(
                player_name="x",
                sentiment=0.0,
                confidence=0.5,
                category="general",
                subject_type=value,
            )
            self.assertEqual(
                signal.subject_type,
                value,
                f"subject_type={value!r} should round-trip",
            )

    def test_subject_type_normalises_invalid_to_player(self) -> None:
        """Invalid subject_type falls back to "player" via __post_init__."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x",
            sentiment=0.0,
            confidence=0.5,
            category="general",
            subject_type="bogus",
        )
        self.assertEqual(
            signal.subject_type,
            "player",
            "invalid subject_type should normalise to 'player'",
        )

    def test_subject_type_appears_in_to_dict_top_level(self) -> None:
        """to_dict() exposes subject_type at the top level (not nested)."""
        from src.sentiment.processing.extractor import PlayerSignal

        signal = PlayerSignal(
            player_name="x",
            sentiment=0.0,
            confidence=0.5,
            category="general",
            subject_type="coach",
        )
        d = signal.to_dict()
        self.assertIn("subject_type", d)
        self.assertEqual(d["subject_type"], "coach")
        # subject_type must NOT appear inside the events sub-dict
        self.assertNotIn("subject_type", d["events"])

    def test_extraction_prompt_documents_subject_type(self) -> None:
        """EXTRACTION_PROMPT mentions subject_type so Claude knows to emit it."""
        from src.sentiment.processing.extractor import EXTRACTION_PROMPT

        self.assertIn("subject_type", EXTRACTION_PROMPT)

    def test_system_prefix_documents_subject_type(self) -> None:
        """_SYSTEM_PREFIX mentions subject_type so Claude knows to emit it."""
        from src.sentiment.processing.extractor import _SYSTEM_PREFIX

        self.assertIn("subject_type", _SYSTEM_PREFIX)


class ClaudeClientProtocolTests(unittest.TestCase):
    """Task 3: ClaudeClient Protocol is importable + runtime-checkable."""

    def test_claude_client_protocol_importable(self) -> None:
        """Protocol must be importable from the extractor module."""
        from src.sentiment.processing.extractor import ClaudeClient

        self.assertIsNotNone(ClaudeClient)

    def test_claude_client_protocol_runtime_check(self) -> None:
        """Any object with a .messages attribute satisfies the Protocol.

        Matches the shape of the real anthropic.Anthropic SDK, which
        exposes chained ``.messages.create(...)``. Plan 71-02's
        ``FakeClaudeClient`` will satisfy this same Protocol so the
        batched extractor (Plan 71-03) can be tested without live API.
        """
        from src.sentiment.processing.extractor import ClaudeClient

        class _FakeMessages:
            def create(self, **kwargs):  # type: ignore[no-untyped-def]
                return None

        class _DuckTyped:
            messages = _FakeMessages()

        duck = _DuckTyped()
        self.assertIsInstance(duck, ClaudeClient)

    def test_claude_client_protocol_rejects_missing_messages(self) -> None:
        """Objects without a .messages attribute are NOT ClaudeClient."""
        from src.sentiment.processing.extractor import ClaudeClient

        class _NotAClient:
            other = "irrelevant"

        not_client = _NotAClient()
        self.assertNotIsInstance(not_client, ClaudeClient)

    def test_legacy_claude_extractor_still_instantiable(self) -> None:
        """The legacy ClaudeExtractor class remains usable (no regression)."""
        from src.sentiment.processing.extractor import ClaudeExtractor

        extractor = ClaudeExtractor()
        # is_available will be False without ANTHROPIC_API_KEY but the
        # property must remain on the class.
        self.assertTrue(hasattr(extractor, "is_available"))
        self.assertIsInstance(extractor.is_available, bool)


if __name__ == "__main__":
    unittest.main()
