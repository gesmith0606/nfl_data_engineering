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

    def test_save_rankings_extra_fields_merged_into_envelope(self):
        """Additive `extra` kwarg (used by the weekly-position capture to
        stamp week/scoring at the envelope level) doesn't disturb the
        existing `source`/`fetched_at`/`players` contract."""
        path, changed = rer.save_rankings(
            "fantasypros_weekly",
            [{"player_name": "A", "position": "WR", "rank": 1}],
            extra={"week": 1, "scoring": "half_ppr"},
        )
        self.assertTrue(changed)
        envelope = json.loads(path.read_text())
        self.assertEqual(envelope["week"], 1)
        self.assertEqual(envelope["scoring"], "half_ppr")
        self.assertEqual(envelope["source"], "fantasypros_weekly")
        self.assertIn("fetched_at", envelope)

    def test_save_rankings_no_extra_is_backward_compatible(self):
        """Existing call sites (no `extra` arg) get the original 3-key
        envelope shape, unchanged."""
        path, _ = rer.save_rankings("sleeper", [{"player_name": "A"}])
        envelope = json.loads(path.read_text())
        self.assertEqual(set(envelope.keys()), {"source", "fetched_at", "players"})


class TestExtractEcrDataJson(unittest.TestCase):
    """FantasyPros weekly-position pages embed `var ecrData = {...};` --
    verified live against fantasypros.com/nfl/rankings/half-point-ppr-wr.php
    et al. 2026-08-22 (see ECR_ANCHOR_FORWARD_GATE.md amendment)."""

    def test_extracts_simple_object(self):
        html = 'foo <script>var ecrData = {"a": 1, "b": "x"};</script> bar'
        data = rer._extract_ecr_data_json(html)
        self.assertEqual(data, {"a": 1, "b": "x"})

    def test_handles_nested_braces_and_string_with_brace_chars(self):
        html = (
            'var ecrData = {"players":[{"note":"contains }; a fake close","rank_ecr":1}]};'
            " trailing junk"
        )
        data = rer._extract_ecr_data_json(html)
        self.assertEqual(data["players"][0]["rank_ecr"], 1)
        self.assertEqual(data["players"][0]["note"], "contains }; a fake close")

    def test_missing_marker_returns_none(self):
        self.assertIsNone(rer._extract_ecr_data_json("<html>no ecr data here</html>"))

    def test_malformed_json_returns_none(self):
        html = "var ecrData = {not valid json};"
        self.assertIsNone(rer._extract_ecr_data_json(html))


class TestParseFpWeeklyPage(unittest.TestCase):
    def test_shapes_players_with_dispersion_and_id(self):
        data = {
            "week": "1",
            "ranking_type_name": "weekly",
            "players": [
                {
                    "player_name": "Ja'Marr Chase",
                    "player_team_id": "CIN",
                    "player_id": 19788,
                    "rank_ecr": 1,
                    "pos_rank": "WR1",
                    "rank_ave": "1.30",
                    "rank_std": "0.46",
                    "rank_min": "1",
                    "rank_max": "2",
                },
                {
                    "player_name": "Puka Nacua",
                    "player_team_id": "LAR",
                    "player_id": 23180,
                    "rank_ecr": 2,
                    "pos_rank": "WR2",
                    "rank_ave": "1.80",
                    "rank_std": "0.60",
                    "rank_min": "1",
                    "rank_max": "3",
                },
            ],
        }
        rows = rer._parse_fp_weekly_page(data, "WR", limit=300)
        self.assertEqual(len(rows), 2)
        chase = rows[0]
        self.assertEqual(chase["player_name"], "Ja'Marr Chase")
        self.assertEqual(chase["position"], "WR")
        self.assertEqual(chase["fantasypros_id"], 19788)
        self.assertEqual(chase["pos_rank"], 1)
        self.assertEqual(chase["ecr"], "1.30")
        self.assertEqual(chase["sd"], "0.46")
        self.assertEqual(chase["week"], 1)
        self.assertEqual(chase["ranking_type"], "weekly")
        self.assertEqual([r["rank"] for r in rows], [1, 2])

    def test_missing_pos_rank_falls_back_to_ecr_order(self):
        data = {
            "week": "1",
            "players": [
                {"player_name": "A", "rank_ecr": 2, "pos_rank": ""},
                {"player_name": "B", "rank_ecr": 1, "pos_rank": ""},
            ],
        }
        rows = rer._parse_fp_weekly_page(data, "RB", limit=300)
        by_name = {r["player_name"]: r["pos_rank"] for r in rows}
        self.assertEqual(by_name["B"], 1)
        self.assertEqual(by_name["A"], 2)

    def test_empty_players_returns_empty_list(self):
        self.assertEqual(rer._parse_fp_weekly_page({"players": []}, "QB", limit=300), [])


class TestFetchFantasyprosWeekly(unittest.TestCase):
    """Network calls mocked -- see the live findings recorded in
    ECR_ANCHOR_FORWARD_GATE.md for what FantasyPros actually serves."""

    def _resp(self, html, status=200):
        resp = mock.Mock()
        resp.status_code = status
        resp.text = html
        resp.raise_for_status = mock.Mock()
        if status >= 400:
            resp.raise_for_status.side_effect = __import__("requests").exceptions.HTTPError(
                response=resp
            )
        return resp

    def test_fetches_all_four_positions(self):
        html = (
            'var ecrData = {"week":"1","ranking_type_name":"weekly",'
            '"players":[{"player_name":"X","rank_ecr":1,"pos_rank":"QB1",'
            '"player_team_id":"AA","player_id":1}]};'
        )
        with mock.patch.object(rer.requests, "get", return_value=self._resp(html)) as m:
            rows = rer.fetch_fantasypros_weekly(season=2026, scoring="half_ppr", limit=300)
        self.assertEqual(m.call_count, 4)  # QB, RB, WR, TE
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["position"] for r in rows}, {"QB", "RB", "WR", "TE"})

    def test_one_position_failing_does_not_block_others(self):
        html = (
            'var ecrData = {"week":"1","ranking_type_name":"weekly",'
            '"players":[{"player_name":"X","rank_ecr":1,"pos_rank":"RB1",'
            '"player_team_id":"AA","player_id":1}]};'
        )

        def _side_effect(url, **kwargs):
            if "qb.php" in url:
                raise __import__("requests").exceptions.ConnectionError("boom")
            return self._resp(html)

        with mock.patch.object(rer.requests, "get", side_effect=_side_effect):
            rows = rer.fetch_fantasypros_weekly(season=2026, scoring="half_ppr", limit=300)
        self.assertTrue(all(r["position"] != "QB" for r in rows))
        self.assertGreater(len(rows), 0)

    def test_no_ecr_data_on_page_skips_that_position(self):
        with mock.patch.object(
            rer.requests, "get", return_value=self._resp("<html>no data</html>")
        ):
            rows = rer.fetch_fantasypros_weekly(season=2026, scoring="half_ppr", limit=300)
        self.assertEqual(rows, [])

    def test_all_positions_failing_returns_empty_list_not_raise(self):
        with mock.patch.object(
            rer.requests,
            "get",
            side_effect=__import__("requests").exceptions.Timeout("slow"),
        ):
            rows = rer.fetch_fantasypros_weekly(season=2026, scoring="half_ppr", limit=300)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
