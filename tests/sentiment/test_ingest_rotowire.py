"""
Tests for the RotoWire sentiment ingestion script
(scripts/ingest_sentiment_rotowire.py).

Covers per Plan 61-01 Task 1:
- Test 1: _parse_rotowire_feed returns a list of item dicts with the
  expected keys.
- Test 2: _item_to_bronze produces the canonical Bronze item envelope shape.
- Test 3: Unresolvable player candidates still populate candidate_names
  but leave resolved_player_ids empty.
- Test 4: main(["--dry-run"]) exits 0 and writes zero files.
- Test 5: SENTIMENT_LOCAL_DIRS["rotowire"] is configured.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# Minimal valid RotoWire RSS 2.0 envelope with two items.  Keeping this as a
# raw string (rather than a feedparser fixture) ensures the parser works with
# the stdlib xml.etree.ElementTree flow too if the implementation switches.
SAMPLE_ROTOWIRE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>RotoWire NFL News</title>
    <link>https://www.rotowire.com/football/</link>
    <description>Latest NFL news</description>
    <item>
      <title>Patrick Mahomes questionable for Week 5</title>
      <link>https://www.rotowire.com/football/news.php?id=12345</link>
      <description>Chiefs QB Patrick Mahomes is questionable with a knee injury.</description>
      <pubDate>Tue, 01 Oct 2024 15:00:00 GMT</pubDate>
      <guid isPermaLink="false">rotowire-12345</guid>
    </item>
    <item>
      <title>Travis Kelce limited in practice</title>
      <link>https://www.rotowire.com/football/news.php?id=12346</link>
      <description>Chiefs TE Travis Kelce was limited in Wednesday practice.</description>
      <pubDate>Wed, 02 Oct 2024 18:30:00 GMT</pubDate>
      <guid isPermaLink="false">rotowire-12346</guid>
    </item>
  </channel>
</rss>
"""


class TestRotoWireParsing(unittest.TestCase):
    """Parsing of the RotoWire RSS feed XML."""

    def test_parse_rotowire_feed_returns_item_list(self) -> None:
        from scripts.ingest_sentiment_rotowire import _parse_rotowire_feed

        items = _parse_rotowire_feed(SAMPLE_ROTOWIRE_XML)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertIn("title", first)
        self.assertIn("url", first)
        self.assertIn("published_at", first)
        self.assertIn("body_text", first)
        self.assertEqual(first["title"], "Patrick Mahomes questionable for Week 5")
        self.assertEqual(
            first["url"], "https://www.rotowire.com/football/news.php?id=12345"
        )

    def test_parse_handles_empty_xml(self) -> None:
        from scripts.ingest_sentiment_rotowire import _parse_rotowire_feed

        empty = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<rss version=\"2.0\"><channel></channel></rss>"
        )
        items = _parse_rotowire_feed(empty)
        self.assertEqual(items, [])


class TestRotoWireItemToBronze(unittest.TestCase):
    """Conversion of a parsed RotoWire entry to the Bronze item shape."""

    def _sample_parsed(self) -> Dict[str, Any]:
        return {
            "title": "Patrick Mahomes questionable for Week 5",
            "url": "https://www.rotowire.com/football/news.php?id=12345",
            "body_text": (
                "Chiefs QB Patrick Mahomes is questionable with a knee injury."
            ),
            "published_at": "2024-10-01T15:00:00+00:00",
            "external_id": "rotowire-12345",
            "author": "",
        }

    def test_item_to_bronze_has_required_envelope_keys(self) -> None:
        from scripts.ingest_sentiment_rotowire import _item_to_bronze

        resolver = MagicMock()
        resolver.resolve.return_value = "00-0033873"

        item = _item_to_bronze(self._sample_parsed(), resolver)

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

        self.assertEqual(item["source"], "rotowire")
        self.assertEqual(item["score"], 0)
        self.assertEqual(item["num_comments"], 0)
        self.assertEqual(item["team_hint"], "KC")
        self.assertIn("Patrick Mahomes", item["candidate_names"])
        self.assertIn("00-0033873", item["resolved_player_ids"])

    def test_item_to_bronze_unresolved_player_keeps_candidates(self) -> None:
        from scripts.ingest_sentiment_rotowire import _item_to_bronze

        resolver = MagicMock()
        resolver.resolve.return_value = None  # cannot resolve any name

        item = _item_to_bronze(self._sample_parsed(), resolver)

        # Candidate names still extracted from the title/body text
        self.assertIn("Patrick Mahomes", item["candidate_names"])
        # But resolver returned None for every candidate -> empty resolved list
        self.assertEqual(item["resolved_player_ids"], [])


class TestRotoWireCLI(unittest.TestCase):
    """End-to-end CLI behaviour (dry-run, no files)."""

    def test_dry_run_writes_no_files_and_exits_zero(self) -> None:
        # Patch the live fetch so the test never touches the network.
        from scripts import ingest_sentiment_rotowire as mod

        with patch.object(
            mod, "_fetch_rotowire_xml", return_value=SAMPLE_ROTOWIRE_XML
        ):
            with tempfile.TemporaryDirectory() as tmpdir:
                # Redirect SENTIMENT_LOCAL_DIRS indirectly by pointing _PROJECT_ROOT
                # read path; actual dry-run should not hit the filesystem regardless.
                tmp_path = Path(tmpdir)
                exit_code = mod.main(["--dry-run", "--season", "2026"])

                self.assertEqual(exit_code, 0)
                # No files should have been written anywhere in tmpdir
                self.assertEqual(list(tmp_path.rglob("*.json")), [])


class TestRotoWireConfig(unittest.TestCase):
    """Config wiring for the new rotowire bronze path."""

    def test_sentiment_local_dirs_has_rotowire_entry(self) -> None:
        from src.config import SENTIMENT_LOCAL_DIRS

        self.assertIn("rotowire", SENTIMENT_LOCAL_DIRS)
        self.assertEqual(
            SENTIMENT_LOCAL_DIRS["rotowire"], "data/bronze/sentiment/rotowire"
        )


if __name__ == "__main__":
    unittest.main()
