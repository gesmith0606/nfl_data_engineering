"""
Bronze Layer: NFL Game Data Ingestion
Ingests raw NFL game data from nfl-data-py into AWS S3 Bronze layer
"""

# Databricks notebook source
import pandas as pd
import nfl_data_py as nfl
from datetime import datetime
import sys
import os

# Add src to path for local imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import get_s3_path, DEFAULT_SEASON, DEFAULT_WEEK
from utils import get_spark_session, pandas_to_spark, validate_s3_path, add_audit_columns

# COMMAND ----------
# MAGIC %md
# MAGIC # NFL Game Data Ingestion - Bronze Layer
# MAGIC 
# MAGIC This notebook ingests raw NFL game data from the nfl-data-py library and stores it in the Bronze layer (AWS S3) without any transformations.

# COMMAND ----------

# Create Databricks widgets for parameterization
dbutils.widgets.text("season", str(DEFAULT_SEASON), "NFL Season")
dbutils.widgets.text("week", str(DEFAULT_WEEK), "NFL Week")
dbutils.widgets.dropdown("data_type", "games", ["games", "schedules"], "Data Type")

# Get widget values
season = int(dbutils.widgets.get("season"))
week = int(dbutils.widgets.get("week"))
data_type = dbutils.widgets.get("data_type")

print(f"Processing NFL {data_type} data for Season {season}, Week {week}")

# COMMAND ----------

# Initialize Spark session
spark = get_spark_session("NFL-Bronze-Ingestion")
print(f"Spark session initialized: {spark.version}")

# COMMAND ----------

def extract_game_data(season: int, week: int) -> pd.DataFrame:
    """
    Extract NFL game data from nfl-data-py
    
    Args:
        season: NFL season year
        week: NFL week number
        
    Returns:
        pandas DataFrame with raw game data
    """
    try:
        print(f"Extracting game data for season {season}, week {week}")
        
        # Get schedule data which contains game information
        schedule_df = nfl.import_schedules([season])
        
        # Filter for specific week
        week_games = schedule_df[schedule_df['week'] == week].copy()
        
        print(f"Found {len(week_games)} games for week {week}")
        
        return week_games
        
    except Exception as e:
        print(f"Error extracting game data: {e}")
        raise

# COMMAND ----------

def load_to_bronze(df: pd.DataFrame, season: int, week: int) -> str:
    """
    Load raw data to Bronze layer in S3
    
    Args:
        df: pandas DataFrame with raw data
        season: NFL season
        week: NFL week
        
    Returns:
        S3 path where data was written
    """
    try:
        # Convert to Spark DataFrame
        spark_df = pandas_to_spark(spark, df)
        
        # Add audit columns
        spark_df_with_audit = add_audit_columns(spark_df)
        
        # Generate S3 path
        s3_path = get_s3_path("bronze", "games", season, week)
        
        print(f"Writing data to: {s3_path}")
        
        # Write to S3 as Parquet (raw format for bronze layer)
        spark_df_with_audit.write \
            .mode("overwrite") \
            .option("path", s3_path) \
            .saveAsTable(f"bronze_nfl_games_s{season}_w{week}")
            
        print(f"Successfully wrote {spark_df_with_audit.count()} records to Bronze layer")
        
        return s3_path
        
    except Exception as e:
        print(f"Error loading to Bronze layer: {e}")
        raise

# COMMAND ----------

# Main execution
try:
    # Extract raw data
    raw_games_df = extract_game_data(season, week)
    
    # Display sample of raw data
    print("\nSample of raw data:")
    print(raw_games_df.head())
    print(f"\nDataFrame shape: {raw_games_df.shape}")
    print(f"Columns: {list(raw_games_df.columns)}")
    
    # Load to Bronze layer
    output_path = load_to_bronze(raw_games_df, season, week)
    
    print(f"\n✅ Bronze ingestion completed successfully!")
    print(f"📍 Data location: {output_path}")
    
except Exception as e:
    print(f"❌ Bronze ingestion failed: {e}")
    raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data Quality Checks
# MAGIC Basic checks on the ingested data

# COMMAND ----------

# Read back the data for validation
try:
    table_name = f"bronze_nfl_games_s{season}_w{week}"
    bronze_df = spark.table(table_name)
    
    print(f"✅ Verification: Successfully read {bronze_df.count()} records from {table_name}")
    
    # Show schema
    print("\nSchema:")
    bronze_df.printSchema()
    
    # Show sample data
    print("\nSample records:")
    bronze_df.show(5, truncate=False)
    
except Exception as e:
    print(f"❌ Verification failed: {e}")
