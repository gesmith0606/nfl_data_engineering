"""
Configuration settings for the NFL Data Engineering Pipeline
"""
import os
from typing import Dict, Any

# AWS S3 Configuration - Updated with your specific buckets
S3_BUCKET_BRONZE = os.getenv("S3_BUCKET_BRONZE", "nfl-raw")
S3_BUCKET_SILVER = os.getenv("S3_BUCKET_SILVER", "nfl-refined")
S3_BUCKET_GOLD = os.getenv("S3_BUCKET_GOLD", "nfl-trusted")
S3_REGION = os.getenv("AWS_REGION", "us-east-2")

# S3 Paths following medallion architecture with separate buckets
S3_PATHS = {
    "bronze": f"s3://{S3_BUCKET_BRONZE}/",
    "silver": f"s3://{S3_BUCKET_SILVER}/",
    "gold": f"s3://{S3_BUCKET_GOLD}/"
}

# NFL Data Configuration
DEFAULT_SEASON = 2024
DEFAULT_WEEK = 1

# Databricks Configuration - Updated with your workspace
DATABRICKS_CLUSTER_ID = os.getenv("DATABRICKS_CLUSTER_ID")
DATABRICKS_WORKSPACE_URL = os.getenv("DATABRICKS_WORKSPACE_URL", "https://dbc-c9b1be11-c0c8.cloud.databricks.com")

# Data Quality Thresholds
DATA_QUALITY_THRESHOLDS = {
    "min_games_per_week": 16,  # NFL has 16-17 games per week typically
    "max_null_percentage": 0.1,  # Max 10% null values allowed
    "min_teams_per_game": 2  # Each game must have exactly 2 teams
}

def get_s3_path(layer: str, dataset: str = "", season: int = None, week: int = None) -> str:
    """
    Generate S3 path for a specific layer and dataset
    
    Args:
        layer: bronze, silver, or gold
        dataset: name of the dataset (e.g., 'games', 'players')
        season: NFL season year
        week: NFL week number
    
    Returns:
        Complete S3 path
    """
    base_path = S3_PATHS[layer]
    
    if dataset:
        base_path += f"{dataset}/"
    
    if season:
        base_path += f"season={season}/"
    
    if week:
        base_path += f"week={week}/"
    
    return base_path
