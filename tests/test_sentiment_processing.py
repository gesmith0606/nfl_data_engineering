"""
Tests for the Phase S2 sentiment processing pipeline.

Covers:
- Extraction prompt parsing with mocked Claude API responses
- Sentiment → multiplier conversion logic
- Staleness decay weight computation
- Event flag OR aggregation
- Weekly aggregation with multiple signals per player
- Pipeline dry-run and processed-ID tracking
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.sentiment.processing.extractor import (
    ClaudeExtractor,
    PlayerSignal,
    EXTRACTION_PROMPT,
)
from src.sentiment.aggregation.weekly import (
    WeeklyAggregator,
    sentiment_to_multiplier,
    compute_staleness_weight,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    external_id: str = "doc-001",
    title: str = "Patrick Mahomes is questionable",
    body: str = "Patrick Mahomes has a knee injury and is listed as questionable.",
    source: str = "rss_espn",
    published_at: str = "2026-04-07T09:00:00+00:00",
) -> Dict[str, Any]:
    """Create a minimal Bronze document dict for testing."""
    return {
        "external_id": external_id,
        "title": title,
        "body_text": body,
        "source": source,
        "published_at": published_at,
    }


def _make_signal(
    player_name: str = "Patrick Mahomes",
    sentiment: float = -0.5,
    confidence: float = 0.9,
    category: str = "injury",
    is_ruled_out: bool = False,
    is_questionable: bool = True,
    published_at: str = "2026-04-07T09:00:00+00:00",
    player_id: str = "00-0033873",
) -> Dict[str, Any]:
    """Create a Silver signal record dict for aggregation tests."""
    return {
        "signal_id": "sig-001",
        "doc_id": "doc-001",
        "source": "rss_espn",
        "season": 2026,
        "week": 1,
        "player_name": player_name,
        "player_id": player_id,
        "sentiment_score": sentiment,
        "sentiment_confidence": confidence,
        "category": category,
        "events": {
            "is_ruled_out": is_ruled_out,
            "is_inactive": False,
            "is_questionable": is_questionable,
            "is_suspended": False,
            "is_returning": False,
        },
        "published_at": published_at,
        "extracted_at": "2026-04-07T10:00:00+00:00",
        "model_version": "claude-haiku-4-5",
        "raw_excerpt": "Patrick Mahomes has a knee injury.",
    }


def _mock_anthropic_response(json_array: List[Dict]) -> MagicMock:
    """Create a mock Anthropic API response containing a JSON array."""
    content_block = MagicMock()
    content_block.text = json.dumps(json_array)
    response = MagicMock()
    response.content = [content_block]
    return response


# ===========================================================================
# 1. Extraction prompt parsing tests
# ===========================================================================


class TestClaudeExtractorParsing(unittest.TestCase):
    """Tests for ClaudeExtractor._parse_response and .extract with mocked API."""

    def _make_extractor_with_mock_client(
        self, response_payload: List[Dict]
    ) -> ClaudeExtractor:
        """Return a ClaudeExtractor whose API client is mocked."""
        extractor = ClaudeExtractor.__new__(ClaudeExtractor)
        extractor.model = "claude-haiku-4-5"
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response(
            response_payload
        )
        extractor._client = mock_client
        return extractor

    def test_extract_single_player(self):
        """extract() returns one PlayerSignal for a single-player article."""
        payload = [
            {
                "player_name": "Patrick Mahomes",
                "sentiment": -0.6,
                "confidence": 0.9,
                "category": "injury",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": True,
                    "is_suspended": False,
                    "is_returning": False,
                },
            }
        ]
        extractor = self._make_extractor_with_mock_client(payload)
        signals = extractor.extract(_make_doc())

        self.assertEqual(len(signals), 1)
        s = signals[0]
        self.assertEqual(s.player_name, "Patrick Mahomes")
        self.assertAlmostEqual(s.sentiment, -0.6)
        self.assertAlmostEqual(s.confidence, 0.9)
        self.assertEqual(s.category, "injury")
        self.assertTrue(s.is_questionable)
        self.assertFalse(s.is_ruled_out)

    def test_extract_multiple_players(self):
        """extract() returns multiple PlayerSignals from one document."""
        payload = [
            {
                "player_name": "Travis Kelce",
                "sentiment": 0.3,
                "confidence": 0.8,
                "category": "usage",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
            },
            {
                "player_name": "Isiah Pacheco",
                "sentiment": 0.5,
                "confidence": 0.7,
                "category": "usage",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": True,
                },
            },
        ]
        extractor = self._make_extractor_with_mock_client(payload)
        doc = _make_doc(title="KC backfield update", body="Kelce and Pacheco are healthy.")
        signals = extractor.extract(doc)

        self.assertEqual(len(signals), 2)
        names = {s.player_name for s in signals}
        self.assertIn("Travis Kelce", names)
        self.assertIn("Isiah Pacheco", names)

        pacheco = next(s for s in signals if s.player_name == "Isiah Pacheco")
        self.assertTrue(pacheco.is_returning)

    def test_extract_empty_array_returns_empty(self):
        """extract() returns [] when Claude returns an empty JSON array."""
        extractor = self._make_extractor_with_mock_client([])
        signals = extractor.extract(_make_doc())
        self.assertEqual(signals, [])

    def test_extract_handles_markdown_code_fence(self):
        """_parse_response handles Claude responses wrapped in ```json ... ```."""
        payload = [
            {
                "player_name": "Josh Allen",
                "sentiment": 0.8,
                "confidence": 0.95,
                "category": "general",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
            }
        ]
        extractor = ClaudeExtractor.__new__(ClaudeExtractor)
        extractor.model = "claude-haiku-4-5"
        extractor._client = MagicMock()

        # Wrap JSON in a markdown code fence
        fenced_response = "```json\n" + json.dumps(payload) + "\n```"
        signals = extractor._parse_response(fenced_response, "test excerpt")

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].player_name, "Josh Allen")

    def test_extract_clamps_sentiment_out_of_range(self):
        """Sentiment values outside [-1, 1] are clamped."""
        payload = [
            {
                "player_name": "Tyreek Hill",
                "sentiment": 5.0,  # out of range
                "confidence": 0.8,
                "category": "general",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
            }
        ]
        extractor = self._make_extractor_with_mock_client(payload)
        signals = extractor.extract(_make_doc())

        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].sentiment, 1.0)

    def test_extract_clamps_confidence_out_of_range(self):
        """Confidence values outside [0, 1] are clamped."""
        payload = [
            {
                "player_name": "Davante Adams",
                "sentiment": 0.2,
                "confidence": -0.5,  # out of range
                "category": "general",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
            }
        ]
        extractor = self._make_extractor_with_mock_client(payload)
        signals = extractor.extract(_make_doc())

        self.assertEqual(len(signals), 1)
        self.assertAlmostEqual(signals[0].confidence, 0.0)

    def test_extract_invalid_category_falls_back_to_general(self):
        """Unknown category strings default to 'general'."""
        payload = [
            {
                "player_name": "Lamar Jackson",
                "sentiment": 0.1,
                "confidence": 0.7,
                "category": "unicorn",  # invalid
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
            }
        ]
        extractor = self._make_extractor_with_mock_client(payload)
        signals = extractor.extract(_make_doc())

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].category, "general")

    def test_extract_skips_item_with_no_player_name(self):
        """Items missing player_name are silently skipped."""
        payload = [
            {
                "player_name": "",  # empty → skipped
                "sentiment": 0.3,
                "confidence": 0.5,
                "category": "general",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": False,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
            }
        ]
        extractor = self._make_extractor_with_mock_client(payload)
        signals = extractor.extract(_make_doc())
        self.assertEqual(signals, [])

    def test_extract_not_available_when_no_api_key(self):
        """ClaudeExtractor.is_available is False when ANTHROPIC_API_KEY is unset."""
        with patch.dict(os.environ, {}, clear=True):
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]
            extractor = ClaudeExtractor()
            self.assertFalse(extractor.is_available)

    def test_extract_returns_empty_when_not_available(self):
        """extract() returns [] gracefully when extractor is not available."""
        extractor = ClaudeExtractor.__new__(ClaudeExtractor)
        extractor.model = "claude-haiku-4-5"
        extractor._client = None
        signals = extractor.extract(_make_doc())
        self.assertEqual(signals, [])

    def test_api_error_returns_empty(self):
        """extract() returns [] when the API call raises an exception."""
        extractor = ClaudeExtractor.__new__(ClaudeExtractor)
        extractor.model = "claude-haiku-4-5"
        extractor._client = MagicMock()
        extractor._client.messages.create.side_effect = RuntimeError("API timeout")

        signals = extractor.extract(_make_doc())
        self.assertEqual(signals, [])

    def test_player_signal_to_dict(self):
        """PlayerSignal.to_dict() serialises all fields correctly."""
        signal = PlayerSignal(
            player_name="CeeDee Lamb",
            sentiment=0.7,
            confidence=0.85,
            category="usage",
            is_ruled_out=False,
            is_questionable=False,
            raw_excerpt="CeeDee Lamb is expected to lead the offense.",
        )
        d = signal.to_dict()
        self.assertEqual(d["player_name"], "CeeDee Lamb")
        self.assertAlmostEqual(d["sentiment"], 0.7)
        self.assertIn("events", d)
        self.assertFalse(d["events"]["is_ruled_out"])


# ===========================================================================
# 2. Sentiment → multiplier conversion tests
# ===========================================================================


class TestSentimentToMultiplier(unittest.TestCase):
    """Tests for the sentiment_to_multiplier() helper function."""

    def test_neutral_sentiment_gives_neutral_multiplier(self):
        """sentiment=0.0 → multiplier=1.0 (neutral)."""
        self.assertAlmostEqual(sentiment_to_multiplier(0.0), 1.0)

    def test_max_positive_sentiment(self):
        """sentiment=+1.0 → multiplier=1.15."""
        self.assertAlmostEqual(sentiment_to_multiplier(1.0), 1.15)

    def test_max_negative_sentiment(self):
        """sentiment=-1.0 → multiplier=0.70."""
        self.assertAlmostEqual(sentiment_to_multiplier(-1.0), 0.70)

    def test_midpoint_positive(self):
        """sentiment=+0.5 → linear interpolation between 1.0 and 1.15."""
        expected = 1.0 + 0.5 * (1.15 - 1.0)
        self.assertAlmostEqual(sentiment_to_multiplier(0.5), expected, places=4)

    def test_midpoint_negative(self):
        """sentiment=-0.5 → linear interpolation between 0.70 and 1.0."""
        expected = 1.0 + (-0.5) * (1.0 - 0.70)
        self.assertAlmostEqual(sentiment_to_multiplier(-0.5), expected, places=4)

    def test_clamps_above_max(self):
        """Values > 1.0 are clamped to multiplier=1.15."""
        self.assertAlmostEqual(sentiment_to_multiplier(2.0), 1.15)

    def test_clamps_below_min(self):
        """Values < -1.0 are clamped to multiplier=0.70."""
        self.assertAlmostEqual(sentiment_to_multiplier(-5.0), 0.70)

    def test_small_positive_sentiment(self):
        """Small positive sentiment yields multiplier slightly above 1.0."""
        mult = sentiment_to_multiplier(0.1)
        self.assertGreater(mult, 1.0)
        self.assertLess(mult, 1.15)

    def test_small_negative_sentiment(self):
        """Small negative sentiment yields multiplier slightly below 1.0."""
        mult = sentiment_to_multiplier(-0.1)
        self.assertLess(mult, 1.0)
        self.assertGreater(mult, 0.70)


# ===========================================================================
# 3. Staleness decay tests
# ===========================================================================


class TestStalenessDecay(unittest.TestCase):
    """Tests for compute_staleness_weight()."""

    def _now(self) -> datetime:
        return datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)

    def test_fresh_signal_has_high_weight(self):
        """A signal published 1 hour ago has weight close to 1.0."""
        pub = (self._now() - timedelta(hours=1)).isoformat()
        w = compute_staleness_weight(pub, self._now())
        self.assertGreater(w, 0.9)

    def test_stale_signal_has_zero_weight(self):
        """A signal older than staleness_hours has weight=0.0."""
        pub = (self._now() - timedelta(hours=100)).isoformat()
        w = compute_staleness_weight(pub, self._now(), staleness_hours=72)
        self.assertEqual(w, 0.0)

    def test_signal_exactly_at_boundary_is_excluded(self):
        """Signal exactly at staleness_hours boundary has weight=0.0."""
        pub = (self._now() - timedelta(hours=72)).isoformat()
        w = compute_staleness_weight(pub, self._now(), staleness_hours=72)
        self.assertEqual(w, 0.0)

    def test_none_published_at_returns_1(self):
        """None published_at is treated as current time (weight=1.0)."""
        w = compute_staleness_weight(None, self._now())
        self.assertAlmostEqual(w, 1.0)

    def test_weight_decreases_with_age(self):
        """Older signals have lower weight than newer signals."""
        pub_new = (self._now() - timedelta(hours=10)).isoformat()
        pub_old = (self._now() - timedelta(hours=40)).isoformat()
        w_new = compute_staleness_weight(pub_new, self._now())
        w_old = compute_staleness_weight(pub_old, self._now())
        self.assertGreater(w_new, w_old)

    def test_weight_in_0_to_1_range(self):
        """Weight is always in [0.0, 1.0]."""
        for hours_ago in [0, 1, 10, 24, 48, 72, 100]:
            pub = (self._now() - timedelta(hours=hours_ago)).isoformat()
            w = compute_staleness_weight(pub, self._now())
            self.assertGreaterEqual(w, 0.0)
            self.assertLessEqual(w, 1.0)

    def test_invalid_timestamp_returns_1(self):
        """Unparseable timestamps default to weight=1.0 (safe fallback)."""
        w = compute_staleness_weight("not-a-date", self._now())
        self.assertAlmostEqual(w, 1.0)

    def test_z_suffix_timestamp_parsed(self):
        """ISO timestamps ending in 'Z' are correctly parsed."""
        pub = (self._now() - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        w = compute_staleness_weight(pub, self._now())
        self.assertGreater(w, 0.0)
        self.assertLessEqual(w, 1.0)


# ===========================================================================
# 4. Event flag OR logic tests
# ===========================================================================


class TestEventFlagOrLogic(unittest.TestCase):
    """Tests for event flag OR aggregation in WeeklyAggregator."""

    def _make_aggregator(self) -> WeeklyAggregator:
        return WeeklyAggregator()

    def _agg_records(
        self, records: List[Dict], ref_time: datetime
    ) -> Dict:
        agg = self._make_aggregator()
        player_agg = agg._aggregate_player_signals(records, ref_time)
        return player_agg

    def _now(self) -> datetime:
        return datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)

    def test_is_ruled_out_any_true_propagates(self):
        """If any signal has is_ruled_out=True, the aggregate has it True."""
        records = [
            _make_signal(is_ruled_out=False, player_id="P1"),
            _make_signal(is_ruled_out=True, player_id="P1"),
        ]
        result = self._agg_records(records, self._now())
        self.assertTrue(result["P1"]["is_ruled_out"])

    def test_is_ruled_out_all_false_stays_false(self):
        """If no signals have is_ruled_out=True, the aggregate is False."""
        records = [
            _make_signal(is_ruled_out=False, is_questionable=False, player_id="P1"),
            _make_signal(is_ruled_out=False, is_questionable=False, player_id="P1"),
        ]
        result = self._agg_records(records, self._now())
        self.assertFalse(result["P1"]["is_ruled_out"])

    def test_is_questionable_or_aggregation(self):
        """is_questionable is OR'd across all signals."""
        records = [
            _make_signal(is_ruled_out=False, is_questionable=False, player_id="P2"),
            _make_signal(is_ruled_out=False, is_questionable=True, player_id="P2"),
        ]
        result = self._agg_records(records, self._now())
        self.assertTrue(result["P2"]["is_questionable"])

    def test_ruled_out_overrides_multiplier_to_zero(self):
        """is_ruled_out=True forces sentiment_multiplier=0.0."""
        records = [
            _make_signal(
                is_ruled_out=True,
                sentiment=0.5,  # positive sentiment but ruled out
                player_id="P3",
            )
        ]
        result = self._agg_records(records, self._now())
        self.assertAlmostEqual(result["P3"]["sentiment_multiplier"], 0.0)

    def test_inactive_overrides_multiplier_to_zero(self):
        """is_inactive=True forces sentiment_multiplier=0.0."""
        records = [
            {
                "signal_id": "s1",
                "player_id": "P4",
                "player_name": "Test Player",
                "sentiment_score": 0.8,
                "sentiment_confidence": 0.9,
                "published_at": "2026-04-07T10:00:00+00:00",
                "events": {
                    "is_ruled_out": False,
                    "is_inactive": True,
                    "is_questionable": False,
                    "is_suspended": False,
                    "is_returning": False,
                },
                "source": "rss_espn",
            }
        ]
        result = self._agg_records(records, self._now())
        self.assertAlmostEqual(result["P4"]["sentiment_multiplier"], 0.0)

    def test_no_event_flags_gives_positive_multiplier(self):
        """No event flags + positive sentiment → multiplier > 1.0."""
        records = [
            _make_signal(
                is_ruled_out=False,
                is_questionable=False,
                sentiment=0.5,
                player_id="P5",
            )
        ]
        result = self._agg_records(records, self._now())
        self.assertGreater(result["P5"]["sentiment_multiplier"], 1.0)


# ===========================================================================
# 5. Full weekly aggregation tests
# ===========================================================================


class TestWeeklyAggregation(unittest.TestCase):
    """Integration tests for WeeklyAggregator.aggregate() using temp directories."""

    def _now(self) -> datetime:
        return datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)

    def _write_silver_file(
        self, tmp_dir: Path, records: List[Dict], season: int = 2026, week: int = 1
    ) -> None:
        """Write a Silver signal file to a temp directory."""
        sig_dir = tmp_dir / "silver" / "sentiment" / "signals" / f"season={season}" / f"week={week:02d}"
        sig_dir.mkdir(parents=True, exist_ok=True)
        envelope = {
            "batch_id": "test",
            "season": season,
            "week": week,
            "signal_count": len(records),
            "records": records,
        }
        (sig_dir / "signals_test.json").write_text(json.dumps(envelope), encoding="utf-8")

    def test_aggregate_single_player(self):
        """Aggregation returns one row per player."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            records = [_make_signal(sentiment=0.4, player_id="00-0033873")]
            self._write_silver_file(tmp_path, records)

            agg = WeeklyAggregator()
            # Patch the module-level path constants to use our temp dir
            import src.sentiment.aggregation.weekly as weekly_mod
            orig_signals_dir = weekly_mod._SILVER_SIGNALS_DIR
            orig_gold_dir = weekly_mod._GOLD_SENTIMENT_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            weekly_mod._GOLD_SENTIMENT_DIR = tmp_path / "gold" / "sentiment"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig_signals_dir
                weekly_mod._GOLD_SENTIMENT_DIR = orig_gold_dir

        self.assertFalse(df.empty)
        self.assertIn("sentiment_multiplier", df.columns)
        self.assertIn("player_id", df.columns)
        self.assertEqual(len(df), 1)

    def test_aggregate_multiple_signals_per_player_weighted(self):
        """Multiple signals per player are merged via weighted average."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Two signals for same player with different sentiments
            records = [
                _make_signal(
                    sentiment=0.8,
                    confidence=1.0,
                    player_id="P-MULTI",
                    published_at="2026-04-07T11:00:00+00:00",
                ),
                _make_signal(
                    sentiment=0.0,
                    confidence=1.0,
                    player_id="P-MULTI",
                    published_at="2026-04-07T10:00:00+00:00",
                ),
            ]
            self._write_silver_file(tmp_path, records)

            agg = WeeklyAggregator()
            import src.sentiment.aggregation.weekly as weekly_mod
            orig = weekly_mod._SILVER_SIGNALS_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig

        self.assertEqual(len(df), 1)
        # Weighted avg: both have same weight at ≈ 1 hr ago; avg ≈ 0.4
        avg = df.iloc[0]["sentiment_score_avg"]
        self.assertGreater(avg, 0.0)
        self.assertLess(avg, 0.8)

    def test_aggregate_multiple_players(self):
        """Each player gets its own row in the output."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            records = [
                _make_signal(player_id="P-A", player_name="Player A", sentiment=0.2),
                _make_signal(player_id="P-B", player_name="Player B", sentiment=-0.3),
            ]
            self._write_silver_file(tmp_path, records)

            agg = WeeklyAggregator()
            import src.sentiment.aggregation.weekly as weekly_mod
            orig = weekly_mod._SILVER_SIGNALS_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig

        self.assertEqual(len(df), 2)
        player_ids = set(df["player_id"].tolist())
        self.assertIn("P-A", player_ids)
        self.assertIn("P-B", player_ids)

    def test_aggregate_empty_silver_returns_empty_df(self):
        """aggregate() returns an empty DataFrame when no Silver files exist."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            agg = WeeklyAggregator()
            import src.sentiment.aggregation.weekly as weekly_mod
            orig = weekly_mod._SILVER_SIGNALS_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig

        self.assertTrue(df.empty)

    def test_aggregate_ruled_out_player_has_zero_multiplier(self):
        """Players with is_ruled_out=True get a 0.0 multiplier."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            records = [
                _make_signal(
                    player_id="P-OUT",
                    sentiment=0.5,
                    is_ruled_out=True,
                )
            ]
            self._write_silver_file(tmp_path, records)

            agg = WeeklyAggregator()
            import src.sentiment.aggregation.weekly as weekly_mod
            orig = weekly_mod._SILVER_SIGNALS_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig

        row = df[df["player_id"] == "P-OUT"].iloc[0]
        self.assertAlmostEqual(row["sentiment_multiplier"], 0.0)

    def test_aggregate_multiplier_range_clamped(self):
        """All sentiment multipliers are within [0.70, 1.15]."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            records = [
                _make_signal(player_id="P1", sentiment=1.0),
                _make_signal(player_id="P2", sentiment=-1.0),
                _make_signal(player_id="P3", sentiment=0.0),
            ]
            self._write_silver_file(tmp_path, records)

            agg = WeeklyAggregator()
            import src.sentiment.aggregation.weekly as weekly_mod
            orig = weekly_mod._SILVER_SIGNALS_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig

        for _, row in df.iterrows():
            mult = row["sentiment_multiplier"]
            self.assertGreaterEqual(mult, 0.0)  # 0.0 for ruled out
            self.assertLessEqual(mult, 1.15)

    def test_stale_signals_excluded_from_aggregation(self):
        """Signals older than staleness_hours do not contribute to multiplier."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Very old signal
            stale_pub = "2020-01-01T00:00:00+00:00"
            records = [
                _make_signal(
                    player_id="P-STALE",
                    sentiment=0.9,
                    published_at=stale_pub,
                )
            ]
            self._write_silver_file(tmp_path, records)

            agg = WeeklyAggregator()
            import src.sentiment.aggregation.weekly as weekly_mod
            orig = weekly_mod._SILVER_SIGNALS_DIR
            weekly_mod._SILVER_SIGNALS_DIR = tmp_path / "silver" / "sentiment" / "signals"
            try:
                df = agg.aggregate(
                    season=2026, week=1, dry_run=True, reference_time=self._now()
                )
            finally:
                weekly_mod._SILVER_SIGNALS_DIR = orig

        if not df.empty and "P-STALE" in df["player_id"].values:
            row = df[df["player_id"] == "P-STALE"].iloc[0]
            # Stale signal has 0 weight → score_avg falls to 0 → multiplier = 1.0
            self.assertAlmostEqual(row["sentiment_multiplier"], 1.0)


# ===========================================================================
# 6. Pipeline dry-run and processed-ID tracking
# ===========================================================================


class TestPipelineProcessedIdTracking(unittest.TestCase):
    """Tests for SentimentPipeline processed-ID deduplication."""

    def _write_bronze_file(
        self, tmp_dir: Path, items: List[Dict], source: str = "rss", season: int = 2026
    ) -> None:
        """Write a Bronze JSON file to a temp directory."""
        bronze_dir = tmp_dir / "data" / "bronze" / "sentiment" / source / f"season={season}"
        bronze_dir.mkdir(parents=True, exist_ok=True)
        envelope = {
            "fetch_run_id": "test-run",
            "source": source,
            "season": season,
            "items": items,
        }
        (bronze_dir / "bronze_test.json").write_text(
            json.dumps(envelope), encoding="utf-8"
        )

    def test_dry_run_does_not_write_silver_files(self):
        """dry_run=True prevents Silver files from being written."""
        import src.sentiment.processing.pipeline as pipeline_mod

        mock_extractor = MagicMock()
        mock_extractor.is_available = True
        mock_signal = PlayerSignal(
            player_name="Patrick Mahomes",
            sentiment=-0.5,
            confidence=0.9,
            category="injury",
            is_questionable=True,
        )
        mock_extractor.extract.return_value = [mock_signal]

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "00-0033873"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Write a bronze file
            items = [_make_doc()]
            self._write_bronze_file(tmp_path, items)

            # Patch pipeline module constants to use temp dir
            orig_silver = pipeline_mod._SILVER_SIGNALS_DIR
            orig_processed = pipeline_mod._PROCESSED_IDS_FILE

            pipeline_mod._SILVER_SIGNALS_DIR = (
                tmp_path / "data" / "silver" / "sentiment" / "signals"
            )
            pipeline_mod._PROCESSED_IDS_FILE = (
                tmp_path / "data" / "silver" / "sentiment" / "processed_ids.json"
            )

            try:
                from src.sentiment.processing.pipeline import SentimentPipeline

                # Also patch the SENTIMENT_LOCAL_DIRS used by _find_bronze_files
                with patch(
                    "src.sentiment.processing.pipeline.SENTIMENT_LOCAL_DIRS",
                    {"rss": str(tmp_path / "data" / "bronze" / "sentiment" / "rss")},
                ):
                    pipeline = SentimentPipeline(
                        extractor=mock_extractor, resolver=mock_resolver
                    )
                    result = pipeline.run(season=2026, week=None, dry_run=True)
            finally:
                pipeline_mod._SILVER_SIGNALS_DIR = orig_silver
                pipeline_mod._PROCESSED_IDS_FILE = orig_processed

        # dry_run → no output files written
        self.assertEqual(result.output_files, [])

    def test_processed_ids_prevent_reprocessing(self):
        """Documents already in processed_ids are skipped on subsequent runs."""
        import src.sentiment.processing.pipeline as pipeline_mod

        mock_extractor = MagicMock()
        mock_extractor.is_available = True
        mock_signal = PlayerSignal(
            player_name="Josh Allen",
            sentiment=0.5,
            confidence=0.8,
            category="general",
        )
        mock_extractor.extract.return_value = [mock_signal]

        mock_resolver = MagicMock()
        mock_resolver.resolve.return_value = "00-0036442"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            items = [_make_doc(external_id="already-seen-doc")]
            self._write_bronze_file(tmp_path, items)

            # Pre-seed the processed_ids file
            processed_dir = tmp_path / "data" / "silver" / "sentiment"
            processed_dir.mkdir(parents=True, exist_ok=True)
            processed_file = processed_dir / "processed_ids.json"
            processed_file.write_text(
                json.dumps(["already-seen-doc"]), encoding="utf-8"
            )

            orig_silver = pipeline_mod._SILVER_SIGNALS_DIR
            orig_processed = pipeline_mod._PROCESSED_IDS_FILE

            pipeline_mod._SILVER_SIGNALS_DIR = (
                tmp_path / "data" / "silver" / "sentiment" / "signals"
            )
            pipeline_mod._PROCESSED_IDS_FILE = processed_file

            try:
                from src.sentiment.processing.pipeline import SentimentPipeline

                with patch(
                    "src.sentiment.processing.pipeline.SENTIMENT_LOCAL_DIRS",
                    {"rss": str(tmp_path / "data" / "bronze" / "sentiment" / "rss")},
                ):
                    pipeline = SentimentPipeline(
                        extractor=mock_extractor, resolver=mock_resolver
                    )
                    result = pipeline.run(season=2026, week=None, dry_run=True)
            finally:
                pipeline_mod._SILVER_SIGNALS_DIR = orig_silver
                pipeline_mod._PROCESSED_IDS_FILE = orig_processed

        # Already processed — should be skipped
        self.assertEqual(result.processed_count, 0)
        self.assertEqual(result.skipped_count, 1)


if __name__ == "__main__":
    unittest.main()
