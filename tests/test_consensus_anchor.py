"""
Unit tests for the consensus anchor (preseason market blending).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from consensus_anchor import (
    DEFAULT_CONSENSUS_WEIGHTS,
    apply_consensus_anchor,
    load_consensus_ranks,
    normalize_player_name,
)


def _write_cache(directory: Path, source: str, players: list) -> None:
    payload = {
        "source": source,
        "fetched_at": "2026-07-07T00:00:00+00:00",
        "players": players,
    }
    (directory / f"{source}_rankings.json").write_text(json.dumps(payload))


class TestNormalizePlayerName(unittest.TestCase):
    def test_strips_suffixes_and_punctuation(self):
        self.assertEqual(
            normalize_player_name("Patrick Mahomes II"),
            normalize_player_name("Patrick Mahomes"),
        )
        self.assertEqual(
            normalize_player_name("Amon-Ra St. Brown"),
            normalize_player_name("Amon Ra St Brown"),
        )
        self.assertEqual(
            normalize_player_name("Marvin Harrison Jr."),
            normalize_player_name("Marvin Harrison"),
        )

    def test_does_not_strip_suffix_letters_inside_words(self):
        # "v" is a suffix token but must not be stripped from names
        self.assertEqual(normalize_player_name("Vita Vea"), "vita vea")


class TestLoadConsensusRanks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_positional_rank_is_order_within_position(self):
        _write_cache(
            self.dir,
            "sleeper",
            [
                {"player_name": "WR One", "position": "WR"},
                {"player_name": "QB One", "position": "QB"},
                {"player_name": "WR Two", "position": "WR"},
                {"player_name": "QB Two", "position": "QB"},
            ],
        )
        ranks = load_consensus_ranks(self.dir, sources=["sleeper"])
        by_name = ranks.set_index("name_key")
        self.assertEqual(by_name.loc["qb one", "consensus_pos_rank"], 1.0)
        self.assertEqual(by_name.loc["qb two", "consensus_pos_rank"], 2.0)
        self.assertEqual(by_name.loc["wr two", "consensus_pos_rank"], 2.0)

    def test_median_across_sources(self):
        for source, order in [
            ("sleeper", ["A", "B", "C"]),
            ("fantasypros", ["B", "A", "C"]),
            ("espn", ["B", "C", "A"]),
        ]:
            _write_cache(
                self.dir,
                source,
                [{"player_name": n, "position": "QB"} for n in order],
            )
        ranks = load_consensus_ranks(
            self.dir, sources=["sleeper", "fantasypros", "espn"]
        )
        by_name = ranks.set_index("name_key")
        # A ranks 1, 2, 3 -> median 2; B ranks 2, 1, 1 -> median 1
        self.assertEqual(by_name.loc["a", "consensus_pos_rank"], 2.0)
        self.assertEqual(by_name.loc["b", "consensus_pos_rank"], 1.0)
        self.assertEqual(by_name.loc["a", "consensus_sources"], 3)

    def test_missing_files_return_empty(self):
        self.assertTrue(load_consensus_ranks(self.dir).empty)

    def test_position_label_with_digits_normalized(self):
        _write_cache(
            self.dir, "sleeper", [{"player_name": "QB One", "position": "QB1"}]
        )
        ranks = load_consensus_ranks(self.dir, sources=["sleeper"])
        self.assertEqual(ranks.iloc[0]["position"], "QB")


class TestApplyConsensusAnchor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # Model points curve: QB ranks 1..4 = 400, 350, 300, 250
        self.proj = pd.DataFrame(
            {
                "player_name": ["Vet Passer", "Young Star", "Mid Guy", "Backup"],
                "position": ["QB", "QB", "QB", "QB"],
                "projected_season_points": [400.0, 350.0, 300.0, 250.0],
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _write_two_sources(self, order):
        for source in ["sleeper", "fantasypros"]:
            _write_cache(
                self.dir,
                source,
                [{"player_name": n, "position": "QB"} for n in order],
            )

    def test_blend_pulls_toward_consensus(self):
        # Consensus says Young Star is QB1 and Vet Passer is QB4
        self._write_two_sources(["Young Star", "Mid Guy", "Backup", "Vet Passer"])
        out = apply_consensus_anchor(
            self.proj, self.dir, weights={"QB": 0.5}
        ).set_index("player_name")
        # Young Star: 0.5*350 + 0.5*implied(rank1=400) = 375
        self.assertAlmostEqual(
            out.loc["Young Star", "projected_season_points"], 375.0
        )
        # Vet Passer: 0.5*400 + 0.5*implied(rank4=250) = 325
        self.assertAlmostEqual(
            out.loc["Vet Passer", "projected_season_points"], 325.0
        )
        # Provenance preserved
        self.assertAlmostEqual(out.loc["Vet Passer", "pre_anchor_points"], 400.0)
        self.assertEqual(out.loc["Vet Passer", "consensus_pos_rank"], 4.0)

    def test_weight_one_is_pure_consensus(self):
        self._write_two_sources(["Backup", "Mid Guy", "Young Star", "Vet Passer"])
        out = apply_consensus_anchor(
            self.proj, self.dir, weights={"QB": 1.0}
        ).set_index("player_name")
        self.assertAlmostEqual(out.loc["Backup", "projected_season_points"], 400.0)
        self.assertAlmostEqual(
            out.loc["Vet Passer", "projected_season_points"], 250.0
        )

    def test_player_missing_from_consensus_untouched(self):
        self._write_two_sources(["Young Star", "Mid Guy", "Backup"])
        out = apply_consensus_anchor(
            self.proj, self.dir, weights={"QB": 0.7}
        ).set_index("player_name")
        self.assertAlmostEqual(
            out.loc["Vet Passer", "projected_season_points"], 400.0
        )
        self.assertTrue(pd.isna(out.loc["Vet Passer", "pre_anchor_points"]))

    def test_single_source_player_not_anchored(self):
        # Player appears in only one source -> below MIN_SOURCES, untouched
        _write_cache(
            self.dir,
            "sleeper",
            [{"player_name": "Young Star", "position": "QB"}],
        )
        _write_cache(self.dir, "fantasypros", [])
        out = apply_consensus_anchor(
            self.proj, self.dir, weights={"QB": 1.0}
        ).set_index("player_name")
        self.assertAlmostEqual(
            out.loc["Young Star", "projected_season_points"], 350.0
        )

    def test_zero_weight_position_untouched(self):
        self._write_two_sources(["Backup", "Mid Guy", "Young Star", "Vet Passer"])
        out = apply_consensus_anchor(
            self.proj, self.dir, weights={"QB": 0.0}
        )
        pd.testing.assert_series_equal(
            out["projected_season_points"],
            self.proj["projected_season_points"],
            check_names=False,
        )

    def test_no_cache_files_is_noop(self):
        out = apply_consensus_anchor(self.proj, self.dir, weights={"QB": 0.7})
        pd.testing.assert_series_equal(
            out["projected_season_points"],
            self.proj["projected_season_points"],
            check_names=False,
        )

    def test_consensus_rank_beyond_curve_clamps_to_worst(self):
        # Consensus lists an extra QB ranked ahead, pushing Backup to rank 5
        self._write_two_sources(
            ["Young Star", "Mid Guy", "Vet Passer", "Extra Guy", "Backup"]
        )
        out = apply_consensus_anchor(
            self.proj, self.dir, weights={"QB": 1.0}
        ).set_index("player_name")
        # implied(rank 5) clamps to the curve's last value (250)
        self.assertAlmostEqual(out.loc["Backup", "projected_season_points"], 250.0)

    def test_default_weights_anchor_qb_only(self):
        self.assertGreater(DEFAULT_CONSENSUS_WEIGHTS["QB"], 0.0)
        for pos in ("RB", "WR", "TE"):
            self.assertEqual(DEFAULT_CONSENSUS_WEIGHTS[pos], 0.0)


if __name__ == "__main__":
    unittest.main()
