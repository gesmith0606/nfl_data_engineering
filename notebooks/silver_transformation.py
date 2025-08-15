"""
Silver Layer: NFL Game Data Transformation
Cleans and standardizes Bronze layer data into Silver layer
"""

# Databricks notebook source
import sys
import os
from datetime import datetime

# Add src to path for local imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import get_s3_path, DATA_QUALITY_THRESHOLDS
from utils import get_spark_session, validate_game_data_quality, write_validation_report

# COMMAND ----------
# MAGIC %md
# MAGIC # NFL Game Data Transformation - Silver Layer
# MAGIC 
# MAGIC This notebook reads Bronze layer data, applies cleaning and standardization, then writes to Silver layer

# COMMAND ----------

# Create Databricks widgets
dbutils.widgets.text("season", "2024", "NFL Season")
dbutils.widgets.text("week", "1", "NFL Week")

# Get parameters
season = int(dbutils.widgets.get("season"))
week = int(dbutils.widgets.get("week"))

print(f"Processing Silver transformation for Season {season}, Week {week}")

# COMMAND ----------

# Initialize Spark
spark = get_spark_session("NFL-Silver-Transformation")

# COMMAND ----------

def clean_game_data(bronze_df):
    """
    Clean and standardize game data from Bronze layer
    """
    from pyspark.sql.functions import col, when, regexp_replace, upper, trim, to_date
    from pyspark.sql.types import IntegerType, DoubleType
    
    # Start with bronze data
    silver_df = bronze_df
    
    # Standardize team names (uppercase, trim whitespace)
    silver_df = silver_df.withColumn("home_team", upper(trim(col("home_team")))) \
                         .withColumn("away_team", upper(trim(col("away_team"))))
    
    # Ensure game_date is proper date format
    if "gameday" in silver_df.columns:
        silver_df = silver_df.withColumn("game_date", to_date(col("gameday"), "yyyy-MM-dd"))
    
    # Clean and cast numeric columns
    numeric_columns = ["home_score", "away_score", "week"]
    for column in numeric_columns:
        if column in silver_df.columns:
            silver_df = silver_df.withColumn(
                column, 
                col(column).cast(IntegerType())
            )
    
    # Remove any games with missing critical data
    critical_columns = ["game_id", "home_team", "away_team"]
    for column in critical_columns:
        if column in silver_df.columns:
            silver_df = silver_df.filter(col(column).isNotNull())
    
    # Add derived columns
    silver_df = silver_df.withColumn("total_score", 
                                   when(col("home_score").isNotNull() & col("away_score").isNotNull(),
                                        col("home_score") + col("away_score"))
                                   .otherwise(None))
    
    # Add game outcome
    if "home_score" in silver_df.columns and "away_score" in silver_df.columns:
        silver_df = silver_df.withColumn("winning_team",
                                       when(col("home_score") > col("away_score"), col("home_team"))
                                       .when(col("away_score") > col("home_score"), col("away_team"))
                                       .otherwise("TIE"))
    
    return silver_df

# COMMAND ----------

def load_to_silver(silver_df, season: int, week: int):
    """
    Load cleaned data to Silver layer
    """
    try:
        # Generate Silver layer path
        s3_path = get_s3_path("silver", "games", season, week)
        
        print(f"Writing Silver data to: {s3_path}")
        
        # Write as Delta table for Silver layer (enables ACID transactions)
        table_name = f"silver_nfl_games_s{season}_w{week}"
        
        silver_df.write \
            .format("delta") \
            .mode("overwrite") \
            .option("path", s3_path) \
            .saveAsTable(table_name)
        
        record_count = silver_df.count()
        print(f"✅ Successfully wrote {record_count} records to Silver layer")
        
        return s3_path, record_count
        
    except Exception as e:
        print(f"❌ Error loading to Silver layer: {e}")
        raise

# COMMAND ----------

# Main execution
try:
    # Read Bronze layer data
    bronze_table_name = f"bronze_nfl_games_s{season}_w{week}"
    print(f"Reading from Bronze table: {bronze_table_name}")
    
    bronze_df = spark.table(bronze_table_name)
    bronze_count = bronze_df.count()
    print(f"Found {bronze_count} records in Bronze layer")
    
    # Apply data quality validation
    print("\n📊 Running data quality checks...")
    validation_results = validate_game_data_quality(bronze_df)
    print("Data quality results:", validation_results)
    
    # Transform data
    print("\n🔄 Applying transformations...")
    silver_df = clean_game_data(bronze_df)
    
    # Load to Silver layer
    silver_path, silver_count = load_to_silver(silver_df, season, week)
    
    print(f"\n✅ Silver transformation completed!")
    print(f"📍 Input: {bronze_count} records from Bronze")
    print(f"📍 Output: {silver_count} records to Silver at {silver_path}")
    
    # Write validation report
    validation_report_path = get_s3_path("silver", f"validation_reports/games_s{season}_w{week}.json")
    write_validation_report(validation_results, validation_report_path)
    
except Exception as e:
    print(f"❌ Silver transformation failed: {e}")
    raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver Layer Verification

# COMMAND ----------

# Verify Silver layer data
try:
    silver_table_name = f"silver_nfl_games_s{season}_w{week}"
    silver_verify_df = spark.table(silver_table_name)
    
    print(f"✅ Verification: {silver_verify_df.count()} records in Silver layer")
    
    # Show schema
    print("\nSilver layer schema:")
    silver_verify_df.printSchema()
    
    # Show sample data
    print("\nSample Silver records:")
    silver_verify_df.select("game_id", "home_team", "away_team", "home_score", "away_score", 
                           "winning_team", "total_score", "game_date").show(5)
    
except Exception as e:
    print(f"❌ Silver verification failed: {e}")
