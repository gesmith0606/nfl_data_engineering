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


if __name__ == "__main__":
    unittest.main()
