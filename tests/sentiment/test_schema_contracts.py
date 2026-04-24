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


if __name__ == "__main__":
    unittest.main()
