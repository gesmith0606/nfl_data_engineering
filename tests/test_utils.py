"""
Unit tests for utility functions
"""
import unittest
from unittest.mock import Mock, patch
import sys
import os

import pandas as pd

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import get_s3_path, DEFAULT_SEASON


class TestConfig(unittest.TestCase):
    """Test configuration functions"""
    
    def test_get_s3_path_basic(self):
        """Test basic S3 path generation for the bronze layer (bucket: nfl-raw)."""
        path = get_s3_path("bronze")
        self.assertTrue(path.startswith("s3://"))
        # Config uses separate buckets per layer; "nfl-raw" is the bronze bucket.
        self.assertIn("nfl-raw", path)

    def test_get_s3_path_with_dataset(self):
        """Test S3 path with dataset for the silver layer (bucket: nfl-refined)."""
        path = get_s3_path("silver", "games")
        # Config uses separate buckets per layer; "nfl-refined" is the silver bucket.
        self.assertIn("nfl-refined", path)
        self.assertIn("/games/", path)

    def test_get_s3_path_with_partitions(self):
        """Test S3 path with season and week partitions for the gold layer (bucket: nfl-trusted)."""
        path = get_s3_path("gold", "team_stats", 2024, 1)
        # Config uses separate buckets per layer; "nfl-trusted" is the gold bucket.
        self.assertIn("nfl-trusted", path)
        self.assertIn("/team_stats/", path)
        self.assertIn("season=2024", path)
        self.assertIn("week=1", path)


class TestUtils(unittest.TestCase):
    """Test utility functions"""
    
    @patch('boto3.client')
    def test_validate_s3_path_valid(self, mock_boto_client):
        """Test S3 path validation with valid path"""
        from utils import validate_s3_path
        
        # Mock successful S3 head_bucket call
        mock_s3 = Mock()
        mock_s3.head_bucket.return_value = {}
        mock_boto_client.return_value = mock_s3
        
        result = validate_s3_path("s3://valid-bucket/path/")
        self.assertTrue(result)
    
    def test_validate_s3_path_invalid_format(self):
        """Test S3 path validation with invalid format"""
        from utils import validate_s3_path
        
        result = validate_s3_path("not-s3-path")
        self.assertFalse(result)


class TestApplySleeperTeamOverrides(unittest.TestCase):
    """Coverage for the projection team-override helper."""

    @staticmethod
    def _make_sleeper_frame(rows):
        """Build a Sleeper rosters_live-shaped frame from compact tuples.

        Each row: (name_key, team, position, is_free_agent[, refreshed_at]).
        """
        cols = ["name_key", "team", "position", "is_free_agent"]
        data = []
        has_refreshed = any(len(r) >= 5 for r in rows)
        if has_refreshed:
            cols.append("refreshed_at")
        for r in rows:
            row = list(r)
            while len(row) < len(cols):
                row.append("2026-04-30T00:00:00Z" if has_refreshed else None)
            data.append(row)
        return pd.DataFrame(data, columns=cols)

    def test_overrides_team_on_match(self):
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame(
            [{"player_name": "Malik Willis", "team": "GB", "position": "QB"}]
        )
        sleeper = self._make_sleeper_frame(
            [("malik willis", "MIA", "QB", False)]
        )
        result = apply_sleeper_team_overrides(proj, sleeper)
        self.assertEqual(result.iloc[0]["team"], "MIA")

    def test_empty_sleeper_is_noop(self):
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame(
            [{"player_name": "Patrick Mahomes", "team": "KC", "position": "QB"}]
        )
        result = apply_sleeper_team_overrides(proj, pd.DataFrame())
        self.assertEqual(result.iloc[0]["team"], "KC")

    def test_missing_required_columns_is_noop(self):
        """Sleeper frame missing the contract columns must not attempt
        overrides — covers earlier ingestion shapes that lacked
        ``is_free_agent``."""
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame(
            [{"player_name": "Joe Burrow", "team": "CIN", "position": "QB"}]
        )
        broken = pd.DataFrame([{"team": "OOPS"}])  # no name_key / is_free_agent
        result = apply_sleeper_team_overrides(proj, broken)
        self.assertEqual(result.iloc[0]["team"], "CIN")

    def test_free_agent_rows_are_not_used_as_source(self):
        """An FA-tagged Sleeper row must NOT override the projection's
        existing team — the projection's team is more reliable than "FA"."""
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame(
            [{"player_name": "Some Backup", "team": "BUF", "position": "QB"}]
        )
        sleeper = self._make_sleeper_frame(
            [("some backup", "FA", "QB", True)]  # is_free_agent=True
        )
        result = apply_sleeper_team_overrides(proj, sleeper)
        self.assertEqual(result.iloc[0]["team"], "BUF")

    def test_same_name_different_position_not_collapsed(self):
        """Two distinct players sharing a lowercased name but at different
        positions must each get their own Sleeper team — not the
        most-recent ingest's team applied to both. This is the bug the
        prior code review flagged: name-only dedup silently overwrote."""
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame(
            [
                {"player_name": "Mike Williams", "team": "OLD_WR", "position": "WR"},
                {"player_name": "Mike Williams", "team": "OLD_DT", "position": "DT"},
            ]
        )
        sleeper = self._make_sleeper_frame(
            [
                ("mike williams", "NYJ", "WR", False, "2026-04-30T00:00:00Z"),
                ("mike williams", "DAL", "DT", False, "2026-04-30T00:00:00Z"),
            ]
        )
        result = apply_sleeper_team_overrides(proj, sleeper)
        teams = result.set_index("position")["team"]
        self.assertEqual(teams.loc["WR"], "NYJ")
        self.assertEqual(teams.loc["DT"], "DAL")

    def test_name_only_fallback_when_position_absent(self):
        """When the projection frame lacks a position column the helper
        falls back to name-only matching for back-compat."""
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame([{"player_name": "Aaron Rodgers", "team": "GB"}])
        sleeper = self._make_sleeper_frame(
            [("aaron rodgers", "PIT", "QB", False)]
        )
        result = apply_sleeper_team_overrides(proj, sleeper)
        self.assertEqual(result.iloc[0]["team"], "PIT")

    def test_unmatched_player_left_alone(self):
        from utils import apply_sleeper_team_overrides

        proj = pd.DataFrame(
            [{"player_name": "Nobody Special", "team": "CHI", "position": "WR"}]
        )
        sleeper = self._make_sleeper_frame(
            [("malik willis", "MIA", "QB", False)]
        )
        result = apply_sleeper_team_overrides(proj, sleeper)
        self.assertEqual(result.iloc[0]["team"], "CHI")


if __name__ == '__main__':
    unittest.main()
