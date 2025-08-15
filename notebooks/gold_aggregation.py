"""
Gold Layer: NFL Game Data Aggregation
Creates business-ready aggregated data from Silver layer
"""

# Databricks notebook source
import sys
import os

# Add src to path for local imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import get_s3_path
from utils import get_spark_session

# COMMAND ----------
# MAGIC %md
# MAGIC # NFL Game Data Aggregation - Gold Layer
# MAGIC 
# MAGIC Creates aggregated, business-ready data for analytics and reporting

# COMMAND ----------

# Create widgets
dbutils.widgets.text("season", "2024", "NFL Season")

# Get parameters
season = int(dbutils.widgets.get("season"))

print(f"Creating Gold layer aggregations for Season {season}")

# COMMAND ----------

# Initialize Spark
spark = get_spark_session("NFL-Gold-Aggregation")

# COMMAND ----------

def create_team_season_stats(season: int):
    """
    Create team statistics for the entire season
    """
    from pyspark.sql.functions import col, sum, avg, count, max, min, when
    
    # Read all Silver layer data for the season
    # This assumes we have data for multiple weeks
    try:
        # Try to read from multiple weeks - adjust logic based on available data
        silver_tables = []
        
        # Get list of available Silver tables for the season
        tables = spark.sql("SHOW TABLES").collect()
        season_tables = [table.tableName for table in tables 
                        if f"silver_nfl_games_s{season}" in table.tableName]
        
        if not season_tables:
            raise Exception(f"No Silver layer tables found for season {season}")
        
        print(f"Found {len(season_tables)} Silver tables for season {season}")
        
        # Union all available weeks
        combined_df = None
        for table_name in season_tables:
            week_df = spark.table(table_name)
            if combined_df is None:
                combined_df = week_df
            else:
                combined_df = combined_df.union(week_df)
        
        # Create team stats (both home and away games)
        home_stats = combined_df.select(
            col("home_team").alias("team"),
            col("home_score").alias("points_scored"),
            col("away_score").alias("points_allowed"),
            when(col("home_score") > col("away_score"), 1).otherwise(0).alias("wins"),
            when(col("home_score") < col("away_score"), 1).otherwise(0).alias("losses"),
            when(col("home_score") == col("away_score"), 1).otherwise(0).alias("ties"),
            col("week"),
            col("game_date")
        )
        
        away_stats = combined_df.select(
            col("away_team").alias("team"),
            col("away_score").alias("points_scored"),
            col("home_score").alias("points_allowed"),
            when(col("away_score") > col("home_score"), 1).otherwise(0).alias("wins"),
            when(col("away_score") < col("home_score"), 1).otherwise(0).alias("losses"),
            when(col("away_score") == col("home_score"), 1).otherwise(0).alias("ties"),
            col("week"),
            col("game_date")
        )
        
        # Combine home and away stats
        all_team_games = home_stats.union(away_stats)
        
        # Aggregate team season statistics
        team_season_stats = all_team_games.groupBy("team") \
            .agg(
                count("*").alias("games_played"),
                sum("wins").alias("total_wins"),
                sum("losses").alias("total_losses"),
                sum("ties").alias("total_ties"),
                avg("points_scored").alias("avg_points_scored"),
                avg("points_allowed").alias("avg_points_allowed"),
                sum("points_scored").alias("total_points_scored"),
                sum("points_allowed").alias("total_points_allowed"),
                max("week").alias("latest_week")
            )
        
        # Add calculated fields
        team_season_stats = team_season_stats.withColumn(
            "win_percentage",
            col("total_wins") / col("games_played")
        ).withColumn(
            "point_differential",
            col("total_points_scored") - col("total_points_allowed")
        )
        
        return team_season_stats
        
    except Exception as e:
        print(f"Error creating team season stats: {e}")
        raise

# COMMAND ----------

def create_weekly_league_stats(season: int):
    """
    Create weekly aggregate statistics for the entire league
    """
    from pyspark.sql.functions import col, avg, sum, count, max, min
    
    try:
        # Get all Silver tables for season
        tables = spark.sql("SHOW TABLES").collect()
        season_tables = [table.tableName for table in tables 
                        if f"silver_nfl_games_s{season}" in table.tableName]
        
        weekly_stats = []
        
        for table_name in season_tables:
            # Extract week from table name
            week_num = int(table_name.split('_w')[1])
            
            week_df = spark.table(table_name)
            
            # Calculate weekly league statistics
            week_stats = week_df.agg(
                count("*").alias("total_games"),
                avg("total_score").alias("avg_total_score"),
                max("total_score").alias("max_total_score"),
                min("total_score").alias("min_total_score"),
                sum("total_score").alias("total_points_scored")
            ).withColumn("season", lit(season)) \
             .withColumn("week", lit(week_num))
            
            weekly_stats.append(week_stats)
        
        # Combine all weekly stats
        if weekly_stats:
            from functools import reduce
            combined_weekly_stats = reduce(lambda df1, df2: df1.union(df2), weekly_stats)
            return combined_weekly_stats
        else:
            raise Exception("No weekly statistics created")
            
    except Exception as e:
        print(f"Error creating weekly league stats: {e}")
        raise

# COMMAND ----------

def load_to_gold(df, table_suffix: str, season: int):
    """
    Load aggregated data to Gold layer
    """
    try:
        s3_path = get_s3_path("gold", table_suffix, season)
        table_name = f"gold_nfl_{table_suffix}_s{season}"
        
        print(f"Writing Gold data to: {s3_path}")
        
        df.write \
            .format("delta") \
            .mode("overwrite") \
            .option("path", s3_path) \
            .saveAsTable(table_name)
        
        record_count = df.count()
        print(f"✅ Wrote {record_count} records to {table_name}")
        
        return s3_path, record_count
        
    except Exception as e:
        print(f"❌ Error loading to Gold layer: {e}")
        raise

# COMMAND ----------

# Main execution
try:
    # Create team season statistics
    print("📊 Creating team season statistics...")
    team_stats_df = create_team_season_stats(season)
    
    # Show sample data
    print("\nSample team statistics:")
    team_stats_df.orderBy(col("win_percentage").desc()).show(10)
    
    # Load team stats to Gold layer
    team_stats_path, team_stats_count = load_to_gold(team_stats_df, "team_stats", season)
    
    # Create weekly league statistics
    print("\n📊 Creating weekly league statistics...")
    weekly_stats_df = create_weekly_league_stats(season)
    
    # Show sample data
    print("\nWeekly league statistics:")
    weekly_stats_df.orderBy("week").show()
    
    # Load weekly stats to Gold layer
    weekly_stats_path, weekly_stats_count = load_to_gold(weekly_stats_df, "weekly_league_stats", season)
    
    print(f"\n✅ Gold layer creation completed!")
    print(f"📍 Team stats: {team_stats_count} records at {team_stats_path}")
    print(f"📍 Weekly stats: {weekly_stats_count} records at {weekly_stats_path}")
    
except Exception as e:
    print(f"❌ Gold layer creation failed: {e}")
    raise

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold Layer Verification

# COMMAND ----------

# Verify Gold layer tables
try:
    print("🔍 Verifying Gold layer tables...")
    
    # Verify team stats
    team_stats_table = f"gold_nfl_team_stats_s{season}"
    team_df = spark.table(team_stats_table)
    print(f"✅ Team stats table: {team_df.count()} records")
    
    # Show top teams by win percentage
    print("\nTop teams by win percentage:")
    team_df.select("team", "games_played", "total_wins", "total_losses", 
                   "win_percentage", "point_differential") \
           .orderBy(col("win_percentage").desc()) \
           .show(10)
    
    # Verify weekly stats
    weekly_stats_table = f"gold_nfl_weekly_league_stats_s{season}"
    weekly_df = spark.table(weekly_stats_table)
    print(f"✅ Weekly stats table: {weekly_df.count()} records")
    
    print("\nWeekly scoring trends:")
    weekly_df.select("week", "total_games", "avg_total_score", "total_points_scored") \
            .orderBy("week") \
            .show()
    
except Exception as e:
    print(f"❌ Gold layer verification failed: {e}")
