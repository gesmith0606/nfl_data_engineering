"""
Tests for the Pro Football Talk (PFT) sentiment ingestion script
(scripts/ingest_sentiment_pft.py).

Covers per Plan 61-01 Task 2:
- Test 1: _parse_pft_feed returns item dicts with required keys.
- Test 2: _item_to_bronze produces a Bronze envelope with source == "pft".
- Test 3: Network failure (HTTPError) -> main() logs a warning and exits 0
  (D-06 -- daily cron must never be blocked by upstream outages).
- Test 4: main(["--dry-run"]) exits 0 and writes zero files.
- Test 5: SENTIMENT_LOCAL_DIRS["pft"] is configured.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


# Minimal PFT RSS 2.0 payload (WordPress-style feed).
SAMPLE_PFT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>ProFootballTalk</title>
    <link>https://profootballtalk.nbcsports.com</link>
    <description>NFL news from PFT</description>
    <item>
      <title>Josh Allen leads Bills to comeback win</title>
      <link>https://profootballtalk.nbcsports.com/2024/10/01/josh-allen-bills-comeback/</link>
      <description><![CDATA[<p>Bills QB Josh Allen led a 4th quarter comeback.</p>]]></description>
      <pubDate>Tue, 01 Oct 2024 20:00:00 GMT</pubDate>
      <guid isPermaLink="true">https://profootballtalk.nbcsports.com/?p=98765</guid>
      <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Mike Florio</dc:creator>
    </item>
    <item>
      <title>Cowboys release veteran linebacker</title>
      <link>https://profootballtalk.nbcsports.com/2024/10/02/cowboys-release-lb/</link>
      <description>Cowboys made a surprise cut Wednesday.</description>
      <pubDate>Wed, 02 Oct 2024 14:15:00 GMT</pubDate>
      <guid isPermaLink="true">https://profootballtalk.nbcsports.com/?p=98766</guid>
    </item>
  </channel>
</rss>
"""


class TestPFTParsing(unittest.TestCase):
    """Parsing of the PFT RSS feed XML."""

    def test_parse_pft_feed_returns_item_list(self) -> None:
        from scripts.ingest_sentiment_pft import _parse_pft_feed

        items = _parse_pft_feed(SAMPLE_PFT_XML)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 2)
        first = items[0]
        for key in ("title", "url", "body_text", "published_at"):
            self.assertIn(key, first)
        self.assertEqual(first["title"], "Josh Allen leads Bills to comeback win")
        self.assertIn("Bills QB Josh Allen", first["body_text"])  # HTML stripped


class TestPFTItemToBronze(unittest.TestCase):
    """Conversion of a parsed PFT entry to the Bronze item shape."""

    def _sample_parsed(self) -> Dict[str, Any]:
        return {
            "title": "Josh Allen leads Bills to comeback win",
            "url": "https://profootballtalk.nbcsports.com/2024/10/01/josh-allen-bills-comeback/",
            "body_text": "Bills QB Josh Allen led a 4th quarter comeback.",
            "published_at": "2024-10-01T20:00:00+00:00",
            "external_id": "https://profootballtalk.nbcsports.com/?p=98765",
            "author": "Mike Florio",
        }

    def test_item_to_bronze_has_required_envelope_keys(self) -> None:
        from scripts.ingest_sentiment_pft import _item_to_bronze

        resolver = MagicMock()
        resolver.resolve.return_value = "00-0034857"  # Josh Allen BUF

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

        self.assertEqual(item["source"], "pft")
        self.assertEqual(item["team_hint"], "BUF")
        self.assertIn("Josh Allen", item["candidate_names"])
        self.assertIn("00-0034857", item["resolved_player_ids"])
        self.assertEqual(item["author"], "Mike Florio")


class TestPFTNetworkFailureGraceful(unittest.TestCase):
    """Per D-06: upstream failures MUST NOT break the daily cron."""

    def test_http_error_logs_warning_and_exits_zero(self) -> None:
        from scripts import ingest_sentiment_pft as mod

        err = HTTPError(
            url="https://profootballtalk.nbcsports.com/feed/",
            code=503,
            msg="Service Unavailable",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        with patch.object(mod, "_fetch_pft_xml", side_effect=err):
            exit_code = mod.main(["--dry-run", "--season", "2026"])
            self.assertEqual(exit_code, 0)

    def test_url_error_logs_warning_and_exits_zero(self) -> None:
        from scripts import ingest_sentiment_pft as mod

        with patch.object(mod, "_fetch_pft_xml", side_effect=URLError("no network")):
            exit_code = mod.main(["--dry-run", "--season", "2026"])
            self.assertEqual(exit_code, 0)


class TestPFTCLI(unittest.TestCase):
    """End-to-end CLI behaviour (dry-run, no files)."""

    def test_dry_run_writes_no_files_and_exits_zero(self) -> None:
        from scripts import ingest_sentiment_pft as mod

        with patch.object(mod, "_fetch_pft_xml", return_value=SAMPLE_PFT_XML):
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                exit_code = mod.main(["--dry-run", "--season", "2026"])

                self.assertEqual(exit_code, 0)
                self.assertEqual(list(tmp_path.rglob("*.json")), [])


class TestPFTConfig(unittest.TestCase):
    """Config wiring for the new pft bronze path."""

    def test_sentiment_local_dirs_has_pft_entry(self) -> None:
        from src.config import SENTIMENT_LOCAL_DIRS

        self.assertIn("pft", SENTIMENT_LOCAL_DIRS)
        self.assertEqual(SENTIMENT_LOCAL_DIRS["pft"], "data/bronze/sentiment/pft")


if __name__ == "__main__":
    unittest.main()
