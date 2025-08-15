"""
Utility functions for the NFL Data Engineering Pipeline
"""
import logging
import pandas as pd
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import *
from pyspark.sql.types import *
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_spark_session(app_name: str = "NFL-Data-Pipeline") -> SparkSession:
    """
    Create and configure Spark session for NFL data processing
    
    Args:
        app_name: Name of the Spark application
        
    Returns:
        Configured SparkSession
    """
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .getOrCreate()

def pandas_to_spark(spark: SparkSession, df: pd.DataFrame, schema: Optional[StructType] = None) -> DataFrame:
    """
    Convert pandas DataFrame to Spark DataFrame with optional schema
    
    Args:
        spark: SparkSession
        df: pandas DataFrame
        schema: Optional Spark schema
        
    Returns:
        Spark DataFrame
    """
    if schema:
        return spark.createDataFrame(df, schema)
    return spark.createDataFrame(df)

def validate_s3_path(s3_path: str) -> bool:
    """
    Validate if S3 path exists and is accessible
    
    Args:
        s3_path: S3 path to validate
        
    Returns:
        True if path is valid and accessible
    """
    try:
        # Parse S3 path
        if not s3_path.startswith('s3://'):
            return False
            
        path_parts = s3_path.replace('s3://', '').split('/', 1)
        bucket = path_parts[0]
        key = path_parts[1] if len(path_parts) > 1 else ''
        
        # Check if bucket exists
        s3_client = boto3.client('s3')
        s3_client.head_bucket(Bucket=bucket)
        
        return True
        
    except ClientError as e:
        logger.error(f"S3 path validation failed for {s3_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating S3 path {s3_path}: {e}")
        return False

def add_audit_columns(df: DataFrame) -> DataFrame:
    """
    Add standard audit columns to DataFrame
    
    Args:
        df: Input Spark DataFrame
        
    Returns:
        DataFrame with audit columns added
    """
    return df.withColumn("created_at", current_timestamp()) \
             .withColumn("updated_at", current_timestamp()) \
             .withColumn("data_source", lit("nfl-data-py"))

def validate_game_data_quality(df: DataFrame) -> Dict[str, Any]:
    """
    Validate data quality for NFL game data
    
    Args:
        df: Spark DataFrame containing game data
        
    Returns:
        Dictionary with validation results
    """
    total_rows = df.count()
    
    validation_results = {
        "total_rows": total_rows,
        "validations": {}
    }
    
    # Check for null values in critical columns
    critical_columns = ["game_id", "home_team", "away_team", "game_date"]
    
    for col in critical_columns:
        if col in df.columns:
            null_count = df.filter(df[col].isNull()).count()
            null_percentage = (null_count / total_rows) * 100 if total_rows > 0 else 0
            
            validation_results["validations"][f"{col}_null_check"] = {
                "null_count": null_count,
                "null_percentage": null_percentage,
                "passed": null_percentage <= 10  # Max 10% nulls allowed
            }
    
    # Check for duplicate games
    if "game_id" in df.columns:
        distinct_games = df.select("game_id").distinct().count()
        duplicate_games = total_rows - distinct_games
        
        validation_results["validations"]["duplicate_check"] = {
            "duplicate_count": duplicate_games,
            "passed": duplicate_games == 0
        }
    
    return validation_results

def write_validation_report(validation_results: Dict[str, Any], output_path: str) -> None:
    """
    Write data quality validation report to S3
    
    Args:
        validation_results: Results from validation
        output_path: S3 path to write report
    """
    try:
        import json
        
        # Convert to JSON and upload to S3
        report_json = json.dumps(validation_results, indent=2, default=str)
        
        # Parse S3 path
        path_parts = output_path.replace('s3://', '').split('/', 1)
        bucket = path_parts[0]
        key = path_parts[1] if len(path_parts) > 1 else 'validation_report.json'
        
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=report_json,
            ContentType='application/json'
        )
        
        logger.info(f"Validation report written to {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to write validation report: {e}")
        raise
