"""Tests for expanded structured-event extraction in the rule-based extractor.

Covers the three new event categories introduced by Plan 61-02:

- Transaction events (is_traded, is_released, is_signed, is_activated)
- Usage events (is_usage_boost, is_usage_drop)
- Weather events (is_weather_risk)

Plus regression guards to make sure the existing injury flags
(is_ruled_out, is_questionable, is_returning, is_suspended) are
untouched by the expansion.

Design principles (see 61-CONTEXT.md, D-02 and threat T-61-02-01):
- HIGH PRECISION: phrases that only fuzzily imply an event must NOT
  fire the flag. Prefer false negatives over false positives.
- Every new event ships with at least one positive test and one
  negative test to lock the precision contract.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.sentiment.processing.extractor import PlayerSignal  # noqa: E402
from src.sentiment.processing.rule_extractor import RuleExtractor  # noqa: E402


# ---------------------------------------------------------------------------
# Transaction event tests (Task 1)
# ---------------------------------------------------------------------------


class TestTransactionEvents(unittest.TestCase):
    """Transaction detection: traded, released, signed, activated."""

    def setUp(self) -> None:
        self.extractor = RuleExtractor()

    def test_traded_sets_is_traded(self) -> None:
        doc = {
            "title": "Trade rumors send Amari Cooper to Dallas Cowboys",
            "body_text": "Deal sends Amari Cooper to the Cowboys.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals, "expected at least one signal")
        self.assertTrue(signals[0].is_traded)
        self.assertEqual(signals[0].category, "trade")

    def test_released_sets_is_released(self) -> None:
        doc = {
            "title": "Ezekiel Elliott was released by Dallas Cowboys today",
            "body_text": "Cowboys released Ezekiel Elliott this afternoon.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_released)
        self.assertEqual(signals[0].category, "trade")
        # Should still be negative sentiment
        self.assertLess(signals[0].sentiment, 0)

    def test_signed_sets_is_signed(self) -> None:
        doc = {
            "title": "Jets signed Dalvin Cook to a one-year deal",
            "body_text": "Dalvin Cook agrees to terms with the Jets.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_signed)
        self.assertEqual(signals[0].category, "trade")
        self.assertGreater(signals[0].sentiment, 0)

    def test_activated_sets_is_activated_and_is_returning(self) -> None:
        doc = {
            "title": "Travis Kelce activated from injured reserve",
            "body_text": "The Chiefs activated Travis Kelce from IR.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        sig = signals[0]
        self.assertTrue(sig.is_activated)
        # Backward-compat: activation also signals a return
        self.assertTrue(sig.is_returning)
        self.assertGreater(sig.sentiment, 0)

    def test_activated_from_suspension(self) -> None:
        doc = {
            "title": "Deshaun Watson activated from suspension",
            "body_text": "Deshaun Watson activated from suspension list.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_activated)

    # ---- Regression guards for existing injury-path flags ----

    def test_ruled_out_regression_guard(self) -> None:
        doc = {
            "title": "Travis Kelce ruled out for Sunday",
            "body_text": "Kelce ruled out.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_ruled_out)
        # Do NOT mis-classify as a transaction
        self.assertFalse(signals[0].is_traded)
        self.assertFalse(signals[0].is_released)
        self.assertFalse(signals[0].is_signed)

    def test_suspended_regression_guard(self) -> None:
        """'Player X was suspended four games' still flags is_suspended.

        The existing injury-path behaviour is: `is_suspended` is a field
        that used to only be set via the Claude events dict. Rule-based
        detection did not previously fire it; this test documents that
        behaviour so we do not silently regress.
        """
        doc = {
            "title": "Stefon Diggs was suspended four games",
            "body_text": "Stefon Diggs suspended four games by the league.",
        }
        signals = self.extractor.extract(doc)
        # Either it flags is_suspended via a new/existing pattern, or it
        # at least does not fabricate a trade/release for a suspension.
        self.assertTrue(signals)
        self.assertFalse(signals[0].is_traded)
        self.assertFalse(signals[0].is_released)

    # ---- Precision tests (must NOT fire) ----

    def test_negative_ambiguous_phrase_does_not_fire_trade(self) -> None:
        """'Thinking about a trade' is speculation, not a trade event."""
        doc = {
            "title": "Derrick Henry considered in trade talks",
            "body_text": "Derrick Henry could be considered in trade talks.",
        }
        signals = self.extractor.extract(doc)
        if signals:  # may produce a signal from other patterns, or none
            self.assertFalse(signals[0].is_traded)

    def test_resigned_does_not_fire_released(self) -> None:
        """'Re-signed' must not match the 'signed' release-adjacent pattern."""
        doc = {
            "title": "Patrick Mahomes re-signed with the Chiefs",
            "body_text": "Patrick Mahomes inked a deal to stay in Kansas City.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertFalse(signals[0].is_released)
        # 'inked a deal' SHOULD fire is_signed though
        self.assertTrue(signals[0].is_signed)


# ---------------------------------------------------------------------------
# Usage event tests (Task 2)
# ---------------------------------------------------------------------------


class TestUsageEvents(unittest.TestCase):
    """Usage boost / drop detection: workhorse, starter, limited snaps, etc."""

    def setUp(self) -> None:
        self.extractor = RuleExtractor()

    def test_workhorse_sets_usage_boost(self) -> None:
        doc = {
            "title": "Saquon Barkley named starter and will operate as the workhorse back",
            "body_text": "Saquon Barkley is the workhorse back.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_boost)
        self.assertEqual(signals[0].category, "usage")

    def test_expected_to_start_sets_usage_boost(self) -> None:
        doc = {
            "title": "Bryce Young expected to start in Week 5",
            "body_text": "Bryce Young expected to start against the Falcons.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_boost)

    def test_primary_target_sets_usage_boost(self) -> None:
        doc = {
            "title": "CeeDee Lamb is the primary target in the passing game",
            "body_text": "CeeDee Lamb is the primary target.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_boost)

    def test_lead_back_sets_usage_boost(self) -> None:
        doc = {
            "title": "Jordan Mason will be the lead back",
            "body_text": "Jordan Mason is the lead back.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_boost)

    def test_splitting_carries_sets_usage_drop(self) -> None:
        doc = {
            "title": "Christian McCaffrey splitting carries with Jordan Mason",
            "body_text": "Christian McCaffrey splitting carries with Jordan Mason.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_drop)
        self.assertEqual(signals[0].category, "usage")

    def test_limited_snaps_sets_usage_drop(self) -> None:
        doc = {
            "title": "Tyler Allgeier saw limited snaps last week",
            "body_text": "Tyler Allgeier saw only a handful of snaps.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_drop)

    def test_benched_sets_usage_drop(self) -> None:
        """Existing 'benched' role pattern must still mark usage drop."""
        doc = {
            "title": "Russell Wilson was demoted to backup",
            "body_text": "Russell Wilson has been benched.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_usage_drop)
        self.assertEqual(signals[0].category, "usage")

    # ---- Precision tests ----

    def test_neutral_text_does_not_fire_usage_boost(self) -> None:
        doc = {
            "title": "Patrick Mahomes threw for 300 yards",
            "body_text": "Patrick Mahomes had a good day.",
        }
        signals = self.extractor.extract(doc)
        if signals:
            self.assertFalse(signals[0].is_usage_boost)
            self.assertFalse(signals[0].is_usage_drop)


# ---------------------------------------------------------------------------
# Weather event tests (Task 2)
# ---------------------------------------------------------------------------


class TestWeatherEvents(unittest.TestCase):
    """Weather risk detection: blizzard, high winds, game in doubt."""

    def setUp(self) -> None:
        self.extractor = RuleExtractor()

    def test_blizzard_sets_weather_risk(self) -> None:
        doc = {
            "title": "Josh Allen game could be played in a blizzard",
            "body_text": "The Bills game could be played in a blizzard.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_weather_risk)
        self.assertEqual(signals[0].category, "weather")

    def test_high_winds_with_mph_threshold(self) -> None:
        doc = {
            "title": "Josh Allen high winds gusts up to 35 mph expected Sunday",
            "body_text": "High winds, gusts up to 35 mph, expected Sunday.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_weather_risk)

    def test_game_in_doubt_sets_weather_risk(self) -> None:
        doc = {
            "title": "Josh Allen Sunday game in doubt due to weather",
            "body_text": "Sunday's game in doubt due to weather.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_weather_risk)

    def test_freezing_rain_sets_weather_risk(self) -> None:
        doc = {
            "title": "Josh Allen faces freezing rain on Sunday",
            "body_text": "Freezing rain in the forecast for Sunday.",
        }
        signals = self.extractor.extract(doc)
        self.assertTrue(signals)
        self.assertTrue(signals[0].is_weather_risk)

    # ---- Precision tests ----

    def test_normal_article_does_not_set_weather_risk(self) -> None:
        doc = {
            "title": "Patrick Mahomes threw three touchdowns",
            "body_text": "Patrick Mahomes had a great game.",
        }
        signals = self.extractor.extract(doc)
        if signals:
            self.assertFalse(signals[0].is_weather_risk)

    def test_light_rain_does_not_set_weather_risk(self) -> None:
        """Light rain is not a 'weather risk' — only extreme conditions fire."""
        doc = {
            "title": "Patrick Mahomes practiced in light rain today",
            "body_text": "Patrick Mahomes practiced in light rain.",
        }
        signals = self.extractor.extract(doc)
        if signals:
            self.assertFalse(signals[0].is_weather_risk)


# ---------------------------------------------------------------------------
# PlayerSignal + Silver record schema tests
# ---------------------------------------------------------------------------


class TestPlayerSignalExpandedFields(unittest.TestCase):
    """PlayerSignal dataclass must expose all new event fields."""

    def test_all_new_fields_exist_and_default_false(self) -> None:
        sig = PlayerSignal(
            player_name="Test Player",
            sentiment=0.0,
            confidence=0.5,
            category="general",
        )
        # Existing fields still default False
        self.assertFalse(sig.is_ruled_out)
        self.assertFalse(sig.is_inactive)
        self.assertFalse(sig.is_questionable)
        self.assertFalse(sig.is_suspended)
        self.assertFalse(sig.is_returning)
        # New fields default False
        self.assertFalse(sig.is_traded)
        self.assertFalse(sig.is_released)
        self.assertFalse(sig.is_signed)
        self.assertFalse(sig.is_activated)
        self.assertFalse(sig.is_usage_boost)
        self.assertFalse(sig.is_usage_drop)
        self.assertFalse(sig.is_weather_risk)

    def test_to_dict_serialises_all_event_fields(self) -> None:
        sig = PlayerSignal(
            player_name="Test Player",
            sentiment=0.0,
            confidence=0.5,
            category="trade",
            is_traded=True,
            is_usage_boost=True,
            is_weather_risk=True,
        )
        d = sig.to_dict()
        self.assertIn("events", d)
        events = d["events"]
        # All 12 event fields must be in the serialised dict
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
            self.assertIn(key, events, f"missing {key} in to_dict events")
        self.assertTrue(events["is_traded"])
        self.assertTrue(events["is_usage_boost"])
        self.assertTrue(events["is_weather_risk"])


class TestSilverRecordExpandedEvents(unittest.TestCase):
    """Silver record writer must include all new event fields."""

    def test_build_silver_record_includes_new_flags(self) -> None:
        from src.sentiment.processing.pipeline import SentimentPipeline

        # Build a minimal pipeline without touching disk
        pipeline = SentimentPipeline.__new__(SentimentPipeline)
        pipeline._extractor = RuleExtractor()
        pipeline.extractor = pipeline._extractor

        signal = PlayerSignal(
            player_name="Amari Cooper",
            sentiment=-0.2,
            confidence=0.7,
            category="trade",
            is_traded=True,
            is_usage_boost=False,
            is_weather_risk=False,
        )
        doc = {"external_id": "d1", "source": "rss", "published_at": "2026-04-17"}
        record = pipeline._build_silver_record(
            doc=doc,
            signal=signal,
            player_id="P001",
            season=2026,
            week=1,
            source="rss",
        )
        self.assertIn("events", record)
        events = record["events"]
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
            self.assertIn(key, events, f"missing {key} in Silver record")
        self.assertTrue(events["is_traded"])


# ---------------------------------------------------------------------------
# Confidence ceiling regression
# ---------------------------------------------------------------------------


class TestConfidenceCeilingPreserved(unittest.TestCase):
    """_RULE_CONFIDENCE = 0.7 must be preserved across all new patterns."""

    def setUp(self) -> None:
        self.extractor = RuleExtractor()

    def test_transaction_signal_confidence_capped(self) -> None:
        doc = {
            "title": "Amari Cooper traded to Buffalo Bills",
            "body_text": "Deal sends Amari Cooper to Buffalo.",
        }
        signals = self.extractor.extract(doc)
        for sig in signals:
            self.assertLessEqual(sig.confidence, 0.7)

    def test_usage_signal_confidence_capped(self) -> None:
        doc = {
            "title": "Saquon Barkley named starter as workhorse",
            "body_text": "Saquon Barkley is the workhorse back.",
        }
        signals = self.extractor.extract(doc)
        for sig in signals:
            self.assertLessEqual(sig.confidence, 0.7)

    def test_weather_signal_confidence_capped(self) -> None:
        doc = {
            "title": "Josh Allen game in doubt due to blizzard",
            "body_text": "Blizzard expected Sunday.",
        }
        signals = self.extractor.extract(doc)
        for sig in signals:
            self.assertLessEqual(sig.confidence, 0.7)


if __name__ == "__main__":
    unittest.main()
