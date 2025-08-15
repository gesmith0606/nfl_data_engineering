"""
Unit tests for utility functions
"""
import unittest
from unittest.mock import Mock, patch
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import get_s3_path, DEFAULT_SEASON


class TestConfig(unittest.TestCase):
    """Test configuration functions"""
    
    def test_get_s3_path_basic(self):
        """Test basic S3 path generation"""
        path = get_s3_path("bronze")
        self.assertTrue(path.startswith("s3://"))
        self.assertIn("/bronze/", path)
    
    def test_get_s3_path_with_dataset(self):
        """Test S3 path with dataset"""
        path = get_s3_path("silver", "games")
        self.assertIn("/silver/", path)
        self.assertIn("/games/", path)
    
    def test_get_s3_path_with_partitions(self):
        """Test S3 path with season and week partitions"""
        path = get_s3_path("gold", "team_stats", 2024, 1)
        self.assertIn("/gold/", path)
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


if __name__ == '__main__':
    unittest.main()
