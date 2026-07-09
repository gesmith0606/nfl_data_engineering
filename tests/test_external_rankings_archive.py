"""
Tests for dated external-rankings snapshots (anchor-weight backtest history).
"""
import gzip
import json
import os
import sys
import unittest
from unittest import mock

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

import refresh_external_rankings as rer


class TestSaveRankingsChangedFlag(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self.tmp = tempfile.TemporaryDirectory()
        self.external = Path(self.tmp.name) / "external"
        self.archive = self.external / "archive"
        self._patches = [
            mock.patch.object(rer, "EXTERNAL_DIR", self.external),
            mock.patch.object(rer, "ARCHIVE_DIR", self.archive),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    def test_first_write_reports_changed(self):
        _, changed = rer.save_rankings(
            "sleeper", [{"player_name": "A", "position": "QB", "rank": 1}]
        )
        self.assertTrue(changed)

    def test_identical_content_reports_unchanged(self):
        data = [{"player_name": "A", "position": "QB", "rank": 1}]
        rer.save_rankings("sleeper", data)
        _, changed = rer.save_rankings("sleeper", data)
        self.assertFalse(changed)

    def test_archive_writes_gzipped_snapshot(self):
        data = [{"player_name": "A", "position": "QB", "rank": 1}]
        rer.save_rankings("sleeper", data)
        written = rer.archive_rankings_snapshot(["sleeper"])
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].name.endswith("_rankings.json.gz"))
        with gzip.open(written[0], "rt", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["players"], data)
        # date-partitioned directory
        self.assertRegex(written[0].parent.name, r"^\d{4}-\d{2}-\d{2}$")

    def test_archive_skips_empty_source_list_and_missing_files(self):
        self.assertEqual(rer.archive_rankings_snapshot([]), [])
        self.assertEqual(rer.archive_rankings_snapshot(["nonexistent"]), [])


if __name__ == "__main__":
    unittest.main()
