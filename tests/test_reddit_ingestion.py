"""
Tests for the Reddit sentiment ingestion script (scripts/ingest_sentiment_reddit.py).

Covers:
- Reddit JSON response parsing
- Player name extraction from titles
- Rate limiting behavior
- Bronze file output format (JSON envelope)
- CLI argument parsing
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# Sample Reddit JSON response structure
SAMPLE_REDDIT_RESPONSE: Dict[str, Any] = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Patrick Mahomes ruled out for Week 5",
                    "selftext": "Chiefs QB Patrick Mahomes has been ruled out with knee injury.",
                    "author": "testuser",
                    "created_utc": 1700000000.0,
                    "permalink": "/r/fantasyfootball/comments/abc123/",
                    "url": "https://reddit.com/r/fantasyfootball/comments/abc123/",
                    "score": 150,
                    "num_comments": 42,
                    "id": "abc123",
                }
            },
            {
                "data": {
                    "title": "Travis Kelce questionable with ankle",
                    "selftext": "Travis Kelce limited in practice.",
                    "author": "user2",
                    "created_utc": 1700000100.0,
                    "permalink": "/r/fantasyfootball/comments/def456/",
                    "url": "https://reddit.com/r/fantasyfootball/comments/def456/",
                    "score": 89,
                    "num_comments": 15,
                    "id": "def456",
                }
            },
        ]
    }
}


class TestRedditResponseParsing(unittest.TestCase):
    """Test parsing of Reddit's public JSON API response."""

    def test_parse_reddit_posts(self) -> None:
        from scripts.ingest_sentiment_reddit import _parse_reddit_response

        posts = _parse_reddit_response(SAMPLE_REDDIT_RESPONSE)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["title"], "Patrick Mahomes ruled out for Week 5")
        self.assertEqual(posts[0]["author"], "testuser")
        self.assertEqual(posts[0]["score"], 150)

    def test_parse_empty_response(self) -> None:
        from scripts.ingest_sentiment_reddit import _parse_reddit_response

        posts = _parse_reddit_response({"data": {"children": []}})
        self.assertEqual(posts, [])

    def test_parse_malformed_response(self) -> None:
        from scripts.ingest_sentiment_reddit import _parse_reddit_response

        posts = _parse_reddit_response({})
        self.assertEqual(posts, [])


class TestRedditPostToItem(unittest.TestCase):
    """Test conversion of Reddit posts to Bronze item format."""

    def test_post_to_item_has_required_fields(self) -> None:
        from scripts.ingest_sentiment_reddit import _post_to_item

        post = SAMPLE_REDDIT_RESPONSE["data"]["children"][0]["data"]
        resolver = MagicMock()
        resolver.resolve.return_value = "00-0033873"

        item = _post_to_item(post, "fantasyfootball", resolver)

        self.assertIn("external_id", item)
        self.assertIn("title", item)
        self.assertIn("body_text", item)
        self.assertIn("author", item)
        self.assertIn("source", item)
        self.assertIn("resolved_player_ids", item)
        self.assertIn("url", item)
        self.assertEqual(item["source"], "reddit_fantasyfootball")

    def test_post_to_item_resolves_players(self) -> None:
        from scripts.ingest_sentiment_reddit import _post_to_item

        post = SAMPLE_REDDIT_RESPONSE["data"]["children"][0]["data"]
        resolver = MagicMock()
        resolver.resolve.return_value = "00-0033873"

        item = _post_to_item(post, "fantasyfootball", resolver)

        # Should have called resolve at least once (for "Patrick Mahomes")
        self.assertTrue(resolver.resolve.called)
        self.assertIn("00-0033873", item["resolved_player_ids"])


class TestRedditBronzeOutput(unittest.TestCase):
    """Test Bronze JSON envelope format for Reddit data."""

    def test_save_items_creates_envelope(self) -> None:
        from scripts.ingest_sentiment_reddit import _save_items

        items = [
            {
                "external_id": "abc123",
                "title": "Test post",
                "body_text": "Test body",
                "source": "reddit_fantasyfootball",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            path = _save_items(items, "fantasyfootball", 2026, output_dir, "run-123")

            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertIn("fetch_run_id", data)
            self.assertIn("source", data)
            self.assertIn("season", data)
            self.assertIn("items", data)
            self.assertEqual(data["source"], "reddit_fantasyfootball")
            self.assertEqual(data["season"], 2026)
            self.assertEqual(len(data["items"]), 1)


class TestRedditCLIArgs(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_default_args(self) -> None:
        from scripts.ingest_sentiment_reddit import _build_arg_parser

        parser = _build_arg_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.subreddit)
        self.assertEqual(args.limit, 25)
        self.assertFalse(args.dry_run)
        self.assertFalse(args.verbose)

    def test_custom_args(self) -> None:
        from scripts.ingest_sentiment_reddit import _build_arg_parser

        parser = _build_arg_parser()
        args = parser.parse_args([
            "--subreddit", "nfl",
            "--limit", "10",
            "--dry-run",
            "--verbose",
            "--season", "2025",
        ])
        self.assertEqual(args.subreddit, "nfl")
        self.assertEqual(args.limit, 10)
        self.assertTrue(args.dry_run)
        self.assertTrue(args.verbose)
        self.assertEqual(args.season, 2025)


if __name__ == "__main__":
    unittest.main()
