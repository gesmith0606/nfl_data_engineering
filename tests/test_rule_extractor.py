"""
Tests for the rule-based text extractor (src/sentiment/processing/rule_extractor.py).

Covers:
- Injury pattern detection (ruled_out, questionable, doubtful, limited, full, dnp, ir, returning)
- Roster move patterns (traded, released, signed, starter, benched)
- Sentiment patterns (positive, negative)
- Sentiment scoring and confidence capping
- Multi-pattern documents
- No-match documents returning empty list
- PlayerSignal format consistency with Claude extractor
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.sentiment.processing.extractor import PlayerSignal


class TestRuleExtractorAvailability(unittest.TestCase):
    """RuleExtractor.is_available should always return True."""

    def test_is_available_always_true(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        ext = RuleExtractor()
        self.assertTrue(ext.is_available)


class TestInjuryPatterns(unittest.TestCase):
    """Injury pattern detection tests."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_ruled_out(self) -> None:
        doc = {
            "title": "Patrick Mahomes ruled out for Sunday",
            "body_text": "Chiefs QB Patrick Mahomes has been ruled out.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        signal = signals[0]
        self.assertLess(signal.sentiment, -0.5)
        self.assertTrue(signal.is_ruled_out)
        self.assertEqual(signal.category, "injury")

    def test_questionable(self) -> None:
        doc = {
            "title": "Travis Kelce questionable with knee",
            "body_text": "Travis Kelce is listed as questionable.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        signal = signals[0]
        self.assertLess(signal.sentiment, 0)
        self.assertTrue(signal.is_questionable)
        self.assertEqual(signal.category, "injury")

    def test_doubtful(self) -> None:
        doc = {
            "title": "Davante Adams doubtful",
            "body_text": "Davante Adams is doubtful for the game.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, -0.3)

    def test_full_participant(self) -> None:
        doc = {
            "title": "Josh Allen full participant",
            "body_text": "Josh Allen was a full participant in practice.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertGreater(signals[0].sentiment, 0)

    def test_dnp(self) -> None:
        doc = {
            "title": "Tyreek Hill did not practice",
            "body_text": "Tyreek Hill DNP on Wednesday.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, 0)

    def test_limited_practice(self) -> None:
        doc = {
            "title": "Saquon Barkley limited in practice",
            "body_text": "Saquon Barkley was a limited participant.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, 0)

    def test_ir_placement(self) -> None:
        doc = {
            "title": "Joe Burrow placed on IR",
            "body_text": "Bengals placed Joe Burrow on injured reserve.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, -0.5)

    def test_returning_from_ir(self) -> None:
        doc = {
            "title": "Christian McCaffrey activated from IR",
            "body_text": "Christian McCaffrey return to practice.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertGreater(signals[0].sentiment, 0)
        self.assertTrue(signals[0].is_returning)


class TestRosterPatterns(unittest.TestCase):
    """Roster move pattern detection tests."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_traded(self) -> None:
        doc = {
            "title": "Amari Cooper traded to Bills",
            "body_text": "Deal sends Amari Cooper to Buffalo.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertEqual(signals[0].category, "trade")

    def test_released(self) -> None:
        doc = {
            "title": "Ezekiel Elliott released by Cowboys",
            "body_text": "Cowboys released Ezekiel Elliott.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, 0)
        self.assertEqual(signals[0].category, "trade")

    def test_signed(self) -> None:
        doc = {
            "title": "Dalvin Cook signed with Jets",
            "body_text": "Dalvin Cook agrees to terms with the Jets.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertGreater(signals[0].sentiment, 0)
        self.assertEqual(signals[0].category, "trade")

    def test_named_starter(self) -> None:
        doc = {
            "title": "Bryce Young named starter",
            "body_text": "Bryce Young will start for the Panthers.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertGreater(signals[0].sentiment, 0)
        self.assertEqual(signals[0].category, "usage")

    def test_benched(self) -> None:
        doc = {
            "title": "Russell Wilson benched",
            "body_text": "Russell Wilson is losing starting job.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, 0)
        self.assertEqual(signals[0].category, "usage")


class TestSentimentPatterns(unittest.TestCase):
    """General positive/negative sentiment detection tests."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_positive_breakout(self) -> None:
        doc = {
            "title": "Amon-Ra St. Brown breakout game",
            "body_text": "Dominant performance by Amon-Ra St. Brown.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertGreater(signals[0].sentiment, 0)

    def test_negative_struggling(self) -> None:
        doc = {
            "title": "Derrick Henry struggling",
            "body_text": "Derrick Henry has been disappointing.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        self.assertLess(signals[0].sentiment, 0)


class TestConfidenceCapping(unittest.TestCase):
    """Rule-based confidence should be capped at 0.7."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_confidence_capped(self) -> None:
        doc = {
            "title": "Patrick Mahomes ruled out",
            "body_text": "Patrick Mahomes has been ruled out.",
        }
        signals = self.extractor.extract(doc)
        for signal in signals:
            self.assertLessEqual(signal.confidence, 0.7)

    def test_confidence_positive(self) -> None:
        doc = {
            "title": "Josh Allen full practice",
            "body_text": "Josh Allen was a full participant.",
        }
        signals = self.extractor.extract(doc)
        for signal in signals:
            self.assertGreater(signal.confidence, 0)
            self.assertLessEqual(signal.confidence, 0.7)


class TestNoMatch(unittest.TestCase):
    """Documents with no recognizable patterns return empty list."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_empty_text(self) -> None:
        doc = {"title": "", "body_text": ""}
        signals = self.extractor.extract(doc)
        self.assertEqual(signals, [])

    def test_no_patterns(self) -> None:
        doc = {
            "title": "NFL schedule released",
            "body_text": "The NFL has released the 2026 schedule.",
        }
        signals = self.extractor.extract(doc)
        self.assertEqual(signals, [])


class TestMultiPattern(unittest.TestCase):
    """Documents with multiple patterns/players produce multiple signals."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_multi_player_text(self) -> None:
        doc = {
            "title": "Injury report: multiple players",
            "body_text": (
                "Patrick Mahomes is questionable. "
                "Travis Kelce has been ruled out. "
                "Isiah Pacheco is a full participant."
            ),
        }
        signals = self.extractor.extract(doc)
        # Should have signals for multiple players
        self.assertGreaterEqual(len(signals), 2)

        # Check different player names are represented
        names = {s.player_name for s in signals}
        self.assertGreaterEqual(len(names), 2)


class TestPlayerSignalFormat(unittest.TestCase):
    """Verify signals match the PlayerSignal dataclass from extractor.py."""

    def setUp(self) -> None:
        from src.sentiment.processing.rule_extractor import RuleExtractor

        self.extractor = RuleExtractor()

    def test_signal_is_player_signal_instance(self) -> None:
        doc = {
            "title": "Patrick Mahomes ruled out",
            "body_text": "Patrick Mahomes is ruled out for Sunday.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        for signal in signals:
            self.assertIsInstance(signal, PlayerSignal)

    def test_signal_has_all_fields(self) -> None:
        doc = {
            "title": "Josh Allen questionable",
            "body_text": "Josh Allen is questionable with an ankle.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(len(signals) > 0)
        signal = signals[0]
        # Check all expected fields exist
        self.assertIsInstance(signal.player_name, str)
        self.assertIsInstance(signal.sentiment, float)
        self.assertIsInstance(signal.confidence, float)
        self.assertIsInstance(signal.category, str)
        self.assertIsInstance(signal.is_ruled_out, bool)
        self.assertIsInstance(signal.is_inactive, bool)
        self.assertIsInstance(signal.is_questionable, bool)
        self.assertIsInstance(signal.is_suspended, bool)
        self.assertIsInstance(signal.is_returning, bool)

    def test_to_dict_works(self) -> None:
        doc = {
            "title": "Patrick Mahomes ruled out",
            "body_text": "Mahomes ruled out.",
        }
        signals = self.extractor.extract(doc)
        if signals:
            d = signals[0].to_dict()
            self.assertIn("player_name", d)
            self.assertIn("sentiment", d)
            self.assertIn("events", d)


if __name__ == "__main__":
    unittest.main()
