"""
Tests for the expanded Reddit ingestion
(scripts/ingest_sentiment_reddit.py) per Plan 61-01 Task 3.

Covers:
- Test 1: SENTIMENT_CONFIG["reddit_subreddits"] default list is exactly
  ["fantasyfootball", "nfl", "DynastyFF"].
- Test 2: main() with no --subreddit flag iterates over all three defaults.
- Test 3: main(["--subreddit", "DynastyFF", "--dry-run"]) runs successfully
  and fetches only DynastyFF.
- Test 4 (regression): existing reddit tests still pass -- covered by the
  separate tests/test_reddit_ingestion.py file (run under the same pytest
  invocation), but we also re-assert the _post_to_item envelope shape here
  to catch drift.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


SAMPLE_SUBREDDIT_RESPONSE: Dict[str, Any] = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Dynasty WR rankings Week 5",
                    "selftext": "Justin Jefferson still at #1 overall.",
                    "author": "dynastyuser",
                    "created_utc": 1700000200.0,
                    "permalink": "/r/DynastyFF/comments/xyz789/",
                    "url": "https://reddit.com/r/DynastyFF/comments/xyz789/",
                    "score": 420,
                    "num_comments": 77,
                    "id": "xyz789",
                }
            }
        ]
    }
}


class TestDefaultSubredditsIncludeDynastyFF(unittest.TestCase):
    """The config default list MUST include the DynastyFF subreddit."""

    def test_config_default_contains_three_subreddits(self) -> None:
        from src.config import SENTIMENT_CONFIG

        subs = SENTIMENT_CONFIG["reddit_subreddits"]
        self.assertEqual(subs, ["fantasyfootball", "nfl", "DynastyFF"])

    def test_module_default_matches_config(self) -> None:
        # The script-level _DEFAULT_SUBREDDITS constant must mirror the
        # config value when the module is first imported.
        from scripts.ingest_sentiment_reddit import _DEFAULT_SUBREDDITS

        self.assertIn("fantasyfootball", _DEFAULT_SUBREDDITS)
        self.assertIn("nfl", _DEFAULT_SUBREDDITS)
        self.assertIn("DynastyFF", _DEFAULT_SUBREDDITS)


class TestMainIteratesAllThreeSubreddits(unittest.TestCase):
    """When no --subreddit flag is passed, main() iterates all defaults."""

    def test_main_default_fetches_all_three(self) -> None:
        from scripts import ingest_sentiment_reddit as mod

        # Mock the HTTP fetch so we do not hit the network.
        with patch.object(
            mod, "_fetch_subreddit", return_value=SAMPLE_SUBREDDIT_RESPONSE
        ) as mock_fetch:
            exit_code = mod.main(["--dry-run"])

        self.assertEqual(exit_code, 0)

        # Extract the subreddit names passed to each call.
        call_subs = {call.args[0] for call in mock_fetch.call_args_list}
        self.assertIn("fantasyfootball", call_subs)
        self.assertIn("nfl", call_subs)
        self.assertIn("DynastyFF", call_subs)
        # Exactly three unique subreddits (no extras, no fewer).
        self.assertEqual(len(call_subs), 3)


class TestSingleSubredditOverride(unittest.TestCase):
    """--subreddit DynastyFF --dry-run fetches only DynastyFF."""

    def test_only_dynasty_ff_is_fetched(self) -> None:
        from scripts import ingest_sentiment_reddit as mod

        with patch.object(
            mod, "_fetch_subreddit", return_value=SAMPLE_SUBREDDIT_RESPONSE
        ) as mock_fetch:
            exit_code = mod.main(["--subreddit", "DynastyFF", "--dry-run"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_fetch.call_count, 1)
        # First positional arg of the only call is the subreddit name.
        self.assertEqual(mock_fetch.call_args.args[0], "DynastyFF")


class TestExistingBehaviourRegression(unittest.TestCase):
    """Regression: Reddit envelope shape must not drift."""

    def test_post_to_item_has_all_canonical_keys(self) -> None:
        from scripts.ingest_sentiment_reddit import _post_to_item

        post = SAMPLE_SUBREDDIT_RESPONSE["data"]["children"][0]["data"]
        resolver = MagicMock()
        resolver.resolve.return_value = None  # No player resolution

        item = _post_to_item(post, "DynastyFF", resolver)

        for key in (
            "external_id",
            "url",
            "permalink",
            "title",
            "body_text",
            "author",
            "published_at",
            "source",
            "score",
            "num_comments",
            "candidate_names",
            "resolved_player_ids",
            "team_hint",
        ):
            self.assertIn(key, item, f"Missing key: {key}")

        # Source string still uses the reddit_{subreddit} prefix.
        self.assertEqual(item["source"], "reddit_DynastyFF")


if __name__ == "__main__":
    unittest.main()
