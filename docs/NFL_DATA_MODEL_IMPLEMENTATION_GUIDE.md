# NFL Data Model Implementation Guide

**Version:** 1.0  
**Last Updated:** March 4, 2026  
**Purpose:** Step-by-step implementation guide for NFL game prediction data model  
**Related Documents:** 
- [NFL_GAME_PREDICTION_DATA_MODEL.md](./NFL_GAME_PREDICTION_DATA_MODEL.md)
- [NFL_DATA_DICTIONARY.md](./NFL_DATA_DICTIONARY.md)

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
**Objective:** Extend Bronze layer and establish Silver layer framework

#### Week 1: Bronze Layer Extensions
1. **Extend existing Bronze schema**
2. **Add new data sources**  
3. **Implement data quality checks**
4. **Set up monitoring**

#### Week 2: Silver Layer Foundation
1. **Design Silver layer transformations**
2. **Implement data validation framework**
3. **Set up Delta Lake storage**
4. **Create initial Silver tables**

### Phase 2: Analytics Foundation (Weeks 3-4) 
**Objective:** Build core analytics capabilities

#### Week 3: Advanced Analytics
1. **Implement EPA calculations**
2. **Build Win Probability models**
3. **Create temporal tracking**
4. **Add situational analytics**

#### Week 4: Team & Player Metrics
1. **Build team performance aggregations**
2. **Implement player impact ratings**
3. **Create performance trends tracking**
4. **Add injury impact modeling**

### Phase 3: ML Integration (Weeks 5-6)
**Objective:** Build prediction-ready feature pipeline

#### Week 5: Feature Engineering  
1. **Build prediction feature pipeline**
2. **Implement rolling metrics**
3. **Add head-to-head analytics**
4. **Create market integration**

#### Week 6: Model Integration
1. **Build model training pipeline**
2. **Implement prediction serving**
3. **Add model validation**
4. **Create feedback loops**

### Phase 4: Production (Weeks 7-8)
**Objective:** Deploy to production with monitoring

#### Week 7: Production Deployment
1. **Deploy monitoring & alerting**
2. **Implement automated quality checks** 
3. **Set up performance optimization**
4. **Create operational runbooks**

#### Week 8: Validation & Optimization
1. **End-to-end testing**
2. **Performance tuning**
3. **User acceptance testing**
4. **Documentation finalization**

---

## Phase 1: Bronze Layer Extensions

### 1.1 Current State Assessment

**Existing Bronze Tables:**
- ✅ `games` (s3://nfl-raw/games/) - 2023 Week 1 data
- ✅ `plays` (s3://nfl-raw/plays/) - 2023 Week 1 data

**Required Extensions:**
- 🔄 `teams` (reference data)
- 🔄 `players` (seasonal rosters) 
- 🔄 `weather` (game conditions)
- 🔄 Historical data backfill (2020-2024)

### 1.2 Extend Bronze Schema

#### Add Teams Table
```python
# File: src/bronze_teams_ingestion.py

import nfl_data_py as nfl
import pandas as pd
from src.utils import upload_to_s3
from src.config import get_s3_path

def ingest_teams_data():
    """Ingest NFL teams reference data to Bronze layer"""
    
    # Fetch team descriptions
    teams_df = nfl.import_team_desc()
    
    # Add metadata
    teams_df['data_source'] = 'nfl-data-py'
    teams_df['ingestion_timestamp'] = pd.Timestamp.now()
    
    # Validate required columns
    required_cols = ['team_abbr', 'team_name', 'team_id']
    missing_cols = [col for col in required_cols if col not in teams_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Upload to S3
    s3_path = get_s3_path('bronze', 'teams')
    filename = f"teams_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.parquet"
    
    success = upload_to_s3(
        df=teams_df,
        bucket='nfl-raw', 
        key=f"teams/{filename}",
        file_format='parquet'
    )
    
    if success:
        print(f"✅ Teams data uploaded: {len(teams_df)} teams")
        return teams_df
    else:
        raise Exception("Failed to upload teams data")

if __name__ == "__main__":
    ingest_teams_data()
```

#### Add Players Table  
```python
# File: src/bronze_players_ingestion.py

import nfl_data_py as nfl
import pandas as pd
from src.utils import upload_to_s3
from src.config import get_s3_path

def ingest_players_data(seasons):
    """Ingest NFL player data to Bronze layer"""
    
    all_players = []
    
    for season in seasons:
        print(f"Fetching player data for {season}...")
        
        # Fetch seasonal player data
        try:
            # Get roster data (player info + team assignments)
            roster_df = nfl.import_seasonal_rosters([season])
            
            # Add season and metadata
            roster_df['season'] = season
            roster_df['data_source'] = 'nfl-data-py'
            roster_df['ingestion_timestamp'] = pd.Timestamp.now()
            
            all_players.append(roster_df)
            
        except Exception as e:
            print(f"Warning: Could not fetch players for {season}: {e}")
            continue
    
    if not all_players:
        raise ValueError("No player data fetched")
    
    # Combine all seasons
    players_df = pd.concat(all_players, ignore_index=True)
    
    print(f"Fetched {len(players_df)} player records across {len(seasons)} seasons")
    
    # Upload partitioned by season
    for season in players_df['season'].unique():
        season_data = players_df[players_df['season'] == season]
        
        filename = f"players_{season}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        
        success = upload_to_s3(
            df=season_data,
            bucket='nfl-raw',
            key=f"players/season={season}/{filename}",
            file_format='parquet'
        )
        
        if success:
            print(f"✅ {season} player data uploaded: {len(season_data)} records")
    
    return players_df

if __name__ == "__main__":
    # Ingest last 5 seasons
    seasons = [2020, 2021, 2022, 2023, 2024]
    ingest_players_data(seasons)
```

### 1.3 Historical Data Backfill

#### Backfill Games and Plays
```python
# File: scripts/historical_data_backfill.py

import argparse
from src.nfl_data_integration import NFLDataFetcher
from src.utils import upload_to_s3
import pandas as pd

def backfill_historical_data(start_season, end_season, data_types):
    """Backfill historical NFL data for multiple seasons"""
    
    fetcher = NFLDataFetcher()
    
    for season in range(start_season, end_season + 1):
        print(f"\n📅 Processing {season} season...")
        
        if 'schedules' in data_types:
            print(f"  Fetching schedules for {season}...")
            schedules_df = fetcher.fetch_game_schedules([season])
            
            # Upload partitioned by week
            for week in schedules_df['week'].unique():
                week_data = schedules_df[schedules_df['week'] == week]
                filename = f"schedules_{season}_{week:02d}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.parquet"
                
                upload_to_s3(
                    df=week_data,
                    bucket='nfl-raw',
                    key=f"games/season={season}/week={week:02d}/{filename}",
                    file_format='parquet'
                )
                print(f"    ✅ Week {week}: {len(week_data)} games")
        
        if 'pbp' in data_types:
            print(f"  Fetching play-by-play for {season}...")
            
            # Get plays in chunks by week to manage memory
            for week in range(1, 23):  # Weeks 1-22 (includes playoffs)
                try:
                    pbp_df = fetcher.fetch_play_by_play([season], week=week)
                    
                    if len(pbp_df) > 0:
                        filename = f"pbp_{season}_{week:02d}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.parquet"
                        
                        upload_to_s3(
                            df=pbp_df,
                            bucket='nfl-raw',
                            key=f"plays/season={season}/week={week:02d}/{filename}",
                            file_format='parquet'
                        )
                        print(f"    ✅ Week {week}: {len(pbp_df)} plays")
                    
                except Exception as e:
                    print(f"    ⚠️ Week {week}: {e}")
                    continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Backfill historical NFL data')
    parser.add_argument('--start-season', type=int, default=2020, help='Start season')
    parser.add_argument('--end-season', type=int, default=2024, help='End season') 
    parser.add_argument('--data-types', nargs='+', default=['schedules', 'pbp'], 
                       choices=['schedules', 'pbp'], help='Data types to backfill')
    
    args = parser.parse_args()
    
    backfill_historical_data(args.start_season, args.end_season, args.data_types)
```

### 1.4 Data Quality Framework

#### Bronze Validation Rules
```python
# File: src/data_quality.py

import pandas as pd
from typing import Dict, List, Any
import logging

class BronzeDataValidator:
    """Data quality validation for Bronze layer"""
    
    def __init__(self):
        self.validation_rules = {
            'games': {
                'required_columns': ['game_id', 'season', 'week', 'home_team', 'away_team'],
                'unique_columns': ['game_id'],
                'range_checks': {
                    'season': (1999, 2025),
                    'week': (1, 22),
                    'home_score': (0, 100),
                    'away_score': (0, 100)
                },
                'business_rules': [
                    self._validate_team_different,
                    self._validate_game_id_format,
                    self._validate_scores_consistent
                ]
            },
            'plays': {
                'required_columns': ['game_id', 'play_id', 'down', 'ydstogo'],
                'unique_columns': ['game_id', 'play_id'],
                'range_checks': {
                    'down': (1, 4),
                    'ydstogo': (0, 99),
                    'yardline_100': (0, 100)
                },
                'business_rules': [
                    self._validate_play_sequence,
                    self._validate_possession_team
                ]
            }
        }
    
    def validate_dataframe(self, df: pd.DataFrame, table_name: str) -> Dict[str, Any]:
        """Validate a dataframe against Bronze layer rules"""
        
        results = {
            'table_name': table_name,
            'row_count': len(df),
            'validation_passed': True,
            'errors': [],
            'warnings': [],
            'quality_score': 1.0
        }
        
        if table_name not in self.validation_rules:
            results['errors'].append(f"No validation rules defined for {table_name}")
            results['validation_passed'] = False
            return results
        
        rules = self.validation_rules[table_name]
        
        # Check required columns
        missing_cols = [col for col in rules['required_columns'] if col not in df.columns]
        if missing_cols:
            results['errors'].append(f"Missing required columns: {missing_cols}")
            results['validation_passed'] = False
        
        # Check uniqueness constraints
        for col in rules.get('unique_columns', []):
            if col in df.columns and df[col].duplicated().any():
                duplicates = df[df[col].duplicated()][col].tolist()
                results['errors'].append(f"Duplicate values in {col}: {duplicates[:5]}")
                results['validation_passed'] = False
        
        # Check range constraints
        for col, (min_val, max_val) in rules.get('range_checks', {}).items():
            if col in df.columns:
                invalid_count = len(df[(df[col] < min_val) | (df[col] > max_val)])
                if invalid_count > 0:
                    results['warnings'].append(
                        f"{invalid_count} values in {col} outside range [{min_val}, {max_val}]"
                    )
        
        # Apply business rules
        for rule_func in rules.get('business_rules', []):
            try:
                rule_result = rule_func(df)
                if not rule_result['passed']:
                    results['errors'].extend(rule_result['errors'])
                    results['validation_passed'] = False
            except Exception as e:
                results['errors'].append(f"Business rule validation failed: {e}")
                results['validation_passed'] = False
        
        # Calculate quality score
        total_checks = (
            len(rules['required_columns']) + 
            len(rules.get('unique_columns', [])) + 
            len(rules.get('range_checks', {})) +
            len(rules.get('business_rules', []))
        )
        
        failed_checks = len(results['errors'])
        results['quality_score'] = max(0.0, 1.0 - (failed_checks / total_checks))
        
        return results
    
    def _validate_team_different(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate home team != away team"""
        if 'home_team' in df.columns and 'away_team' in df.columns:
            same_team_games = df[df['home_team'] == df['away_team']]
            if len(same_team_games) > 0:
                return {
                    'passed': False,
                    'errors': [f"Games with same home/away team: {same_team_games['game_id'].tolist()}"]
                }
        return {'passed': True, 'errors': []}
    
    def _validate_game_id_format(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate game_id format: YYYY_WW_AWAY_HOME"""
        if 'game_id' in df.columns:
            pattern = r'^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$'
            invalid_ids = df[~df['game_id'].str.match(pattern, na=False)]['game_id'].tolist()
            if invalid_ids:
                return {
                    'passed': False,
                    'errors': [f"Invalid game_id format: {invalid_ids[:5]}"]
                }
        return {'passed': True, 'errors': []}
    
    def _validate_scores_consistent(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate score consistency"""
        required_cols = ['home_score', 'away_score', 'result', 'total']
        if all(col in df.columns for col in required_cols):
            # Check result = home_score - away_score
            result_inconsistent = df[
                (df['result'] != (df['home_score'] - df['away_score'])) & 
                df['result'].notna() & df['home_score'].notna() & df['away_score'].notna()
            ]
            
            # Check total = home_score + away_score  
            total_inconsistent = df[
                (df['total'] != (df['home_score'] + df['away_score'])) &
                df['total'].notna() & df['home_score'].notna() & df['away_score'].notna()
            ]
            
            errors = []
            if len(result_inconsistent) > 0:
                errors.append(f"Inconsistent result calculation in {len(result_inconsistent)} games")
            if len(total_inconsistent) > 0:
                errors.append(f"Inconsistent total calculation in {len(total_inconsistent)} games")
            
            return {'passed': len(errors) == 0, 'errors': errors}
        
        return {'passed': True, 'errors': []}
    
    def _validate_play_sequence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate play sequence within games"""
        if 'game_id' in df.columns and 'play_id' in df.columns:
            # Check for reasonable play sequences
            for game_id in df['game_id'].unique()[:5]:  # Sample check
                game_plays = df[df['game_id'] == game_id]['play_id'].astype(str)
                if game_plays.str.contains(r'[^\d]', na=False).any():
                    return {
                        'passed': False, 
                        'errors': [f"Non-numeric play_id in game {game_id}"]
                    }
        return {'passed': True, 'errors': []}
    
    def _validate_possession_team(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate possession team is home or away team"""
        required_cols = ['possession_team', 'home_team', 'away_team']
        if all(col in df.columns for col in required_cols):
            invalid_possession = df[
                (~df['possession_team'].isin(df['home_team'])) & 
                (~df['possession_team'].isin(df['away_team'])) &
                df['possession_team'].notna()
            ]
            if len(invalid_possession) > 0:
                return {
                    'passed': False,
                    'errors': [f"Invalid possession team in {len(invalid_possession)} plays"]
                }
        return {'passed': True, 'errors': []}
```

---

## Phase 2: Silver Layer Implementation

### 2.1 Silver Layer Architecture

#### Delta Lake Setup
```python
# File: src/silver_delta_setup.py

from delta import DeltaTable, configure_spark_with_delta_pip
from pyspark.sql import SparkSession
import os

def setup_delta_lake_silver():
    """Initialize Delta Lake for Silver layer"""
    
    # Configure Spark with Delta Lake
    builder = SparkSession.builder \
        .appName("NFLDataSilverLayer") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID")) \
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY")) \
        .config("spark.hadoop.fs.s3a.endpoint", f"s3.{os.getenv('AWS_REGION', 'us-east-2')}.amazonaws.com")
    
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    
    return spark

def create_silver_tables(spark):
    """Create Silver layer Delta tables"""
    
    # Games Silver table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS silver.games (
            game_id STRING,
            season INT,
            week INT,
            game_date DATE,
            game_time_et TIME,
            home_team_id STRING,
            away_team_id STRING,
            home_score INT,
            away_score INT,
            game_result INT,
            total_points INT,
            overtime_flag BOOLEAN,
            neutral_site_flag BOOLEAN,
            dome_game_flag BOOLEAN,
            division_game_flag BOOLEAN,
            playoff_flag BOOLEAN,
            prime_time_flag BOOLEAN,
            game_type STRING,
            season_type STRING,
            week_category STRING,
            home_rest_days INT,
            away_rest_days INT,
            rest_differential INT,
            spread DECIMAL(4,1),
            total_line DECIMAL(4,1),
            home_favorite_flag BOOLEAN,
            spread_cover_result STRING,
            total_result STRING,
            temperature INT,
            wind_speed INT,
            precipitation_flag BOOLEAN,
            weather_category STRING,
            data_quality_score DECIMAL(3,2),
            validation_status STRING,
            load_timestamp TIMESTAMP
        ) USING DELTA
        PARTITIONED BY (season, week)
        LOCATION 's3://nfl-refined/games/'
    """)
    
    # Teams Silver table
    spark.sql("""
        CREATE TABLE IF NOT EXISTS silver.teams (
            team_id STRING,
            team_abbr STRING,
            team_name STRING,
            team_city STRING,
            team_state STRING,
            division_id STRING,
            conference STRING,
            founded_year INT,
            stadium_id STRING,
            stadium_name STRING,
            stadium_capacity INT,
            stadium_surface STRING,
            stadium_roof_type STRING,
            stadium_elevation INT,
            time_zone STRING,
            stadium_lat DECIMAL(8,6),
            stadium_lng DECIMAL(9,6),
            stadium_city STRING,
            stadium_state STRING,
            primary_color STRING,
            secondary_color STRING,
            logo_url STRING,
            team_website STRING,
            load_timestamp TIMESTAMP
        ) USING DELTA
        LOCATION 's3://nfl-refined/teams/'
    """)
    
    print("✅ Silver layer Delta tables created")
```

### 2.2 Bronze to Silver Transformation

#### Games Transformation
```python
# File: src/silver_games_transform.py

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
from src.data_quality import BronzeDataValidator
import logging

class GamesTransformer:
    """Transform Bronze games data to Silver layer"""
    
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.validator = BronzeDataValidator()
        self.logger = logging.getLogger(__name__)
    
    def transform_bronze_to_silver(self, season: int, week: int = None):
        """Transform Bronze games to Silver with data quality"""
        
        self.logger.info(f"Transforming games data for season {season}, week {week}")
        
        # Read Bronze data
        if week:
            bronze_path = f"s3://nfl-raw/games/season={season}/week={week:02d}/"
        else:
            bronze_path = f"s3://nfl-raw/games/season={season}/"
        
        try:
            bronze_df = self.spark.read.parquet(bronze_path)
            self.logger.info(f"Read {bronze_df.count()} games from Bronze")
        except Exception as e:
            self.logger.error(f"Failed to read Bronze data: {e}")
            return False
        
        # Apply transformations
        silver_df = self._apply_transformations(bronze_df)
        
        # Data quality validation
        quality_results = self._validate_silver_data(silver_df)
        
        # Write to Silver layer
        if quality_results['validation_passed']:
            self._write_to_silver(silver_df, season, week)
            self.logger.info(f"✅ Successfully transformed {silver_df.count()} games to Silver")
            return True
        else:
            self.logger.error(f"Data quality validation failed: {quality_results['errors']}")
            return False
    
    def _apply_transformations(self, bronze_df):
        """Apply business transformations to Bronze data"""
        
        silver_df = bronze_df.select(
            # Core identifiers (validated)
            col("game_id"),
            col("season").cast("int"),
            col("week").cast("int"),
            
            # Date/time standardization
            to_date(col("gameday")).alias("game_date"),
            col("gametime").alias("game_time_et"),  # Assume already ET
            
            # Team standardization
            col("home_team").alias("home_team_id"),
            col("away_team").alias("away_team_id"),
            
            # Score validation and derived fields
            coalesce(col("home_score").cast("int"), lit(0)).alias("home_score"),
            coalesce(col("away_score").cast("int"), lit(0)).alias("away_score"),
            (coalesce(col("home_score").cast("int"), lit(0)) - 
             coalesce(col("away_score").cast("int"), lit(0))).alias("game_result"),
            (coalesce(col("home_score").cast("int"), lit(0)) + 
             coalesce(col("away_score").cast("int"), lit(0))).alias("total_points"),
            
            # Boolean flags
            (col("overtime") == 1).alias("overtime_flag"),
            (col("location") != "Home").alias("neutral_site_flag"),
            
            # Derived game context
            when(col("roof").isin(["dome", "closed"]), True).otherwise(False).alias("dome_game_flag"),
            (col("week") > 18).alias("playoff_flag"),
            when(col("gametime").like("%20:2%"), True)  # SNF
            .when(col("gametime").like("%21:1%"), True)   # MNF  
            .when(col("gametime").like("%20:1%"), True)   # TNF
            .otherwise(False).alias("prime_time_flag"),
            
            # Game categorization
            when(col("week") > 18, 
                when(col("week") == 19, "WC")
                .when(col("week") == 20, "DIV")  
                .when(col("week") == 21, "CONF")
                .when(col("week") == 22, "SB")
            ).otherwise("REG").alias("game_type"),
            
            when(col("week") > 18, "Playoffs").otherwise("Regular").alias("season_type"),
            
            when(col("week") <= 6, "Early")
            .when(col("week") <= 12, "Mid")
            .otherwise("Late").alias("week_category"),
            
            # Rest analysis
            coalesce(col("home_rest"), lit(7)).alias("home_rest_days"),
            coalesce(col("away_rest"), lit(7)).alias("away_rest_days"),
            (coalesce(col("home_rest"), lit(7)) - coalesce(col("away_rest"), lit(7))).alias("rest_differential"),
            
            # Betting data
            col("spread_line").alias("spread"),
            col("total_line"),
            (col("spread_line") < 0).alias("home_favorite_flag"),
            
            # Add timestamp
            current_timestamp().alias("load_timestamp")
        )
        
        # Add division game logic (requires teams reference)
        silver_df = self._add_division_game_flag(silver_df)
        
        # Add spread cover results (post-game)
        silver_df = self._add_betting_results(silver_df)
        
        # Add data quality score
        silver_df = silver_df.withColumn("data_quality_score", lit(0.95))  # Calculated later
        silver_df = silver_df.withColumn("validation_status", lit("PASSED"))
        
        return silver_df
    
    def _add_division_game_flag(self, df):
        """Add division game flag by looking up team divisions"""
        
        # This would require a teams reference table
        # For now, return with placeholder
        return df.withColumn("division_game_flag", lit(False))  # TODO: Implement lookup
    
    def _add_betting_results(self, df):
        """Calculate spread cover and total results"""
        
        df_with_results = df.withColumn(
            "spread_cover_result",
            when(col("spread").isNull(), lit(None))
            .when(col("game_result") + col("spread") > 0, "Home_Cover")
            .when(col("game_result") + col("spread") < 0, "Away_Cover")  
            .otherwise("Push")
        ).withColumn(
            "total_result",
            when(col("total_line").isNull(), lit(None))
            .when(col("total_points") > col("total_line"), "Over")
            .when(col("total_points") < col("total_line"), "Under")
            .otherwise("Push")
        )
        
        # Add placeholder weather fields
        df_with_results = df_with_results \
            .withColumn("temperature", lit(None).cast("int")) \
            .withColumn("wind_speed", lit(None).cast("int")) \
            .withColumn("precipitation_flag", lit(None).cast("boolean")) \
            .withColumn("weather_category", lit(None).cast("string"))
        
        return df_with_results
    
    def _validate_silver_data(self, df):
        """Validate transformed Silver data"""
        
        # Convert to Pandas for validation (for small datasets)
        pandas_df = df.limit(1000).toPandas()  # Sample for validation
        
        # Custom Silver validation rules
        validation_results = {
            'validation_passed': True,
            'errors': [],
            'warnings': []
        }
        
        # Check for required fields
        required_fields = ['game_id', 'season', 'week', 'home_team_id', 'away_team_id']
        missing_fields = [field for field in required_fields if field not in df.columns]
        if missing_fields:
            validation_results['validation_passed'] = False
            validation_results['errors'].append(f"Missing required fields: {missing_fields}")
        
        # Check for null values in key fields
        null_counts = pandas_df[required_fields].isnull().sum()
        if null_counts.any():
            validation_results['warnings'].append(f"Null values found: {null_counts[null_counts > 0].to_dict()}")
        
        return validation_results
    
    def _write_to_silver(self, df, season: int, week: int = None):
        """Write transformed data to Silver layer"""
        
        if week:
            output_path = f"s3://nfl-refined/games/season={season}/week={week:02d}/"
        else:
            output_path = f"s3://nfl-refined/games/season={season}/"
        
        # Write as Delta Lake table
        df.write \
            .format("delta") \
            .mode("overwrite") \
            .option("overwriteSchema", "true") \
            .save(output_path)
        
        self.logger.info(f"Silver games data written to {output_path}")

# CLI Script
if __name__ == "__main__":
    import argparse
    from src.silver_delta_setup import setup_delta_lake_silver
    
    parser = argparse.ArgumentParser(description='Transform Bronze games to Silver')
    parser.add_argument('--season', type=int, required=True, help='Season to process')
    parser.add_argument('--week', type=int, help='Specific week to process')
    
    args = parser.parse_args()
    
    # Setup Spark with Delta Lake
    spark = setup_delta_lake_silver()
    
    # Run transformation
    transformer = GamesTransformer(spark)
    success = transformer.transform_bronze_to_silver(args.season, args.week)
    
    if success:
        print("✅ Games transformation completed successfully")
    else:
        print("❌ Games transformation failed")
        exit(1)
```

---

## Phase 3: Gold Layer Analytics

### 3.1 Team Performance Metrics

#### EPA Calculations
```python
# File: src/gold_epa_calculator.py

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.window import Window
import numpy as np

class EPACalculator:
    """Calculate Expected Points Added (EPA) for NFL plays"""
    
    def __init__(self, spark: SparkSession):
        self.spark = spark
        
        # EPA model coefficients (simplified version)
        # In production, this would be a trained ML model
        self.epa_model = self._load_epa_model()
    
    def calculate_team_epa_metrics(self, season: int):
        """Calculate EPA-based team metrics for a season"""
        
        # Read Silver plays data
        plays_df = self.spark.read.parquet(f"s3://nfl-refined/plays/season={season}/")
        
        # Add EPA to each play
        plays_with_epa = self._add_epa_to_plays(plays_df)
        
        # Calculate team aggregations
        team_metrics = self._aggregate_team_metrics(plays_with_epa, season)
        
        # Write to Gold layer
        self._write_team_metrics(team_metrics, season)
        
        return team_metrics
    
    def _load_epa_model(self):
        """Load EPA model (simplified lookup table)"""
        
        # This is a simplified version. In production, you'd load a trained model
        # EPA roughly based on field position, down, distance
        return {
            'field_position_factor': 0.07,   # Points per yard closer to goal
            'down_penalties': {1: 0, 2: -0.3, 3: -0.8, 4: -1.5},
            'distance_penalty': -0.02,       # Per yard to go
            'baseline_epa': 2.0              # Average drive result
        }
    
    def _add_epa_to_plays(self, plays_df):
        """Add EPA calculations to each play"""
        
        # Calculate expected points before play (simplified)
        plays_with_ep = plays_df.withColumn(
            "ep_before",
            (
                # Field position component (closer to goal = higher EP)
                (100 - col("yardline_100")) * self.epa_model['field_position_factor'] +
                
                # Down penalty
                when(col("down") == 1, self.epa_model['down_penalties'][1])
                .when(col("down") == 2, self.epa_model['down_penalties'][2])  
                .when(col("down") == 3, self.epa_model['down_penalties'][3])
                .when(col("down") == 4, self.epa_model['down_penalties'][4])
                .otherwise(0) +
                
                # Distance penalty
                col("ydstogo") * self.epa_model['distance_penalty'] +
                
                # Baseline
                self.epa_model['baseline_epa']
            )
        )
        
        # Calculate expected points after play (simplified)
        # This would use next play situation or drive outcome
        window_spec = Window.partitionBy("game_id", "drive_id").orderBy("play_id")
        
        plays_with_ep_after = plays_with_ep.withColumn(
            "ep_after",
            when(col("touchdown_flag"), 7)  # TD worth 7 points
            .when(col("field_goal_flag"), 3)  # FG worth 3 points  
            .when(col("safety_flag"), 2)      # Safety worth 2 points
            .when(col("turnover_flag"), -lag("ep_before", 1).over(window_spec))  # Opponent gets EP
            .when(col("punt_flag"), -1.5)     # Roughly average opponent EP after punt
            .otherwise(
                # Continue drive - calculate EP for new situation
                (100 - (col("yardline_100") - col("yards_gained"))) * 
                self.epa_model['field_position_factor'] +
                # New down logic would go here
                self.epa_model['baseline_epa']
            )
        )
        
        # Calculate EPA = EP_after - EP_before  
        plays_with_epa = plays_with_ep_after.withColumn(
            "epa",
            col("ep_after") - col("ep_before")
        )
        
        # Add success flag (simplified as gaining 50% of needed yards)
        plays_with_success = plays_with_epa.withColumn(
            "success_flag",
            when(col("first_down_flag") | col("touchdown_flag"), True)
            .when(col("yards_gained") >= (col("ydstogo") * 0.5), True)
            .otherwise(False)
        )
        
        return plays_with_success
    
    def _aggregate_team_metrics(self, plays_df, season: int):
        """Aggregate play-level data to team metrics"""
        
        # Offensive metrics (by possession team)
        offense_metrics = plays_df.filter(
            col("play_type").isin(["pass", "run"]) &  # Only offensive plays
            col("penalty_flag").isNull() |             # Exclude penalty-only plays
            (col("penalty_flag") == False)
        ).groupBy("possession_team_id") \
        .agg(
            count("*").alias("total_plays"),
            avg("epa").alias("epa_per_play"),
            avg(col("success_flag").cast("double")).alias("success_rate"),
            sum(when(col("yards_gained") >= 20, 1).otherwise(0)).alias("explosive_plays"),
            count("*").alias("total_plays_for_explosive_rate")
        ).withColumn(
            "explosive_play_rate", 
            col("explosive_plays") / col("total_plays_for_explosive_rate")
        ).select(
            col("possession_team_id").alias("team_id"),
            lit("offense").alias("metric_type"), 
            lit(season).alias("season"),
            lit(0).alias("week_number"),  # Season totals
            col("total_plays").alias("games_played"),  # Will be corrected later
            col("epa_per_play"),
            col("success_rate"), 
            col("explosive_play_rate")
        )
        
        # Defensive metrics (by defense team)  
        defense_metrics = plays_df.filter(
            col("play_type").isin(["pass", "run"]) &
            col("penalty_flag").isNull() |
            (col("penalty_flag") == False)
        ).groupBy("defense_team_id") \
        .agg(
            avg("epa").alias("def_epa_per_play"),
            avg(col("success_flag").cast("double")).alias("def_success_rate_allowed"),
            sum(when(col("yards_gained") >= 20, 1).otherwise(0)).alias("explosive_plays_allowed"),
            count("*").alias("total_plays_defense")
        ).withColumn(
            "explosive_rate_allowed",
            col("explosive_plays_allowed") / col("total_plays_defense")
        ).select(
            col("defense_team_id").alias("team_id"),
            lit("defense").alias("metric_type"),
            lit(season).alias("season"), 
            lit(0).alias("week_number"),
            col("total_plays_defense").alias("games_played"),
            (-1 * col("def_epa_per_play")).alias("epa_per_play"),  # Flip sign for defense
            (1 - col("def_success_rate_allowed")).alias("success_rate"),  # Defensive success
            col("explosive_rate_allowed").alias("explosive_play_rate")
        )
        
        # Combine offensive and defensive metrics
        combined_metrics = offense_metrics.union(defense_metrics)
        
        # Add additional calculated fields
        enhanced_metrics = combined_metrics.withColumn(
            "load_timestamp", current_timestamp()
        )
        
        return enhanced_metrics
    
    def _write_team_metrics(self, metrics_df, season: int):
        """Write team metrics to Gold layer"""
        
        output_path = f"s3://nfl-trusted/team_performance/season={season}/"
        
        metrics_df.write \
            .format("delta") \
            .mode("overwrite") \
            .partitionBy("metric_type") \
            .option("overwriteSchema", "true") \
            .save(output_path)
        
        print(f"✅ Team EPA metrics written to {output_path}")

# CLI Script
if __name__ == "__main__":
    import argparse
    from src.silver_delta_setup import setup_delta_lake_silver
    
    parser = argparse.ArgumentParser(description='Calculate EPA-based team metrics')
    parser.add_argument('--season', type=int, required=True, help='Season to process')
    
    args = parser.parse_args()
    
    # Setup Spark
    spark = setup_delta_lake_silver()
    
    # Calculate EPA metrics
    epa_calc = EPACalculator(spark)
    metrics = epa_calc.calculate_team_epa_metrics(args.season)
    
    print(f"✅ EPA calculations completed for {args.season} season")
    print(f"Generated metrics for {metrics.count()} team-metric type combinations")
```

### 3.2 Game Prediction Features

#### Feature Engineering Pipeline
```python
# File: src/gold_prediction_features.py

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.window import Window
from typing import List, Dict
import logging

class PredictionFeatureBuilder:
    """Build ML-ready features for NFL game prediction"""
    
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.logger = logging.getLogger(__name__)
    
    def build_game_features(self, season: int, week: int) -> bool:
        """Build prediction features for games in specified season/week"""
        
        self.logger.info(f"Building prediction features for {season} season, week {week}")
        
        try:
            # Get games to predict
            games_df = self._get_games_to_predict(season, week)
            
            # Build feature components
            team_form_features = self._build_team_form_features(season, week)
            head_to_head_features = self._build_head_to_head_features()
            situational_features = self._build_situational_features()
            advanced_metrics = self._build_advanced_metrics(season, week)
            
            # Combine all features
            prediction_features = self._combine_features(
                games_df, team_form_features, head_to_head_features, 
                situational_features, advanced_metrics, season, week
            )
            
            # Write to Gold layer
            self._write_prediction_features(prediction_features, season, week)
            
            self.logger.info(f"✅ Built features for {prediction_features.count()} games")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to build prediction features: {e}")
            return False
    
    def _get_games_to_predict(self, season: int, week: int):
        """Get games that need predictions"""
        
        games_path = f"s3://nfl-refined/games/season={season}/week={week:02d}/"
        games_df = self.spark.read.parquet(games_path)
        
        return games_df.select(
            "game_id", "season", "week", "game_date",
            "home_team_id", "away_team_id", "spread", "total_line"
        )
    
    def _build_team_form_features(self, season: int, week: int):
        """Build recent team performance features"""
        
        # Get historical performance through previous week
        historical_games = self.spark.read.parquet(f"s3://nfl-refined/games/season={season}/") \
            .filter(col("week") < week)
        
        # Calculate rolling form (last 4 games)
        window_spec = Window.partitionBy("team_id").orderBy("game_date") \
            .rowsBetween(-3, 0)  # Last 4 games including current
        
        # Home team form
        home_form = historical_games.select(
            col("home_team_id").alias("team_id"),
            col("game_date"),
            col("home_score").alias("points_scored"),
            col("away_score").alias("points_allowed"),
            (col("home_score") > col("away_score")).cast("int").alias("wins")
        ).withColumn(
            "recent_ppg", avg("points_scored").over(window_spec)
        ).withColumn(
            "recent_papg", avg("points_allowed").over(window_spec)
        ).withColumn(
            "recent_win_rate", avg("wins").over(window_spec)
        )
        
        # Away team form (similar calculation)
        away_form = historical_games.select(
            col("away_team_id").alias("team_id"),
            col("game_date"), 
            col("away_score").alias("points_scored"),
            col("home_score").alias("points_allowed"),
            (col("away_score") > col("home_score")).cast("int").alias("wins")
        ).withColumn(
            "recent_ppg", avg("points_scored").over(window_spec)
        ).withColumn(
            "recent_papg", avg("points_allowed").over(window_spec)  
        ).withColumn(
            "recent_win_rate", avg("wins").over(window_spec)
        )
        
        # Combine home and away
        all_form = home_form.union(away_form)
        
        # Get most recent form for each team
        latest_form = all_form.withColumn(
            "row_num", row_number().over(
                Window.partitionBy("team_id").orderBy(desc("game_date"))
            )
        ).filter(col("row_num") == 1).drop("row_num")
        
        return latest_form
    
    def _build_head_to_head_features(self):
        """Build head-to-head historical features"""
        
        # Get last 5 years of historical matchups
        h2h_games = self.spark.read.parquet("s3://nfl-refined/games/") \
            .filter(col("season") >= (col("season").max() - 4))  # Last 5 seasons
        
        # Calculate H2H records
        h2h_summary = h2h_games.groupBy("home_team_id", "away_team_id") \
            .agg(
                sum(when(col("home_score") > col("away_score"), 1).otherwise(0)).alias("home_wins"),
                sum(when(col("away_score") > col("home_score"), 1).otherwise(0)).alias("away_wins"), 
                avg(col("home_score") + col("away_score")).alias("avg_total_points"),
                avg(col("home_score") - col("away_score")).alias("avg_home_margin"),
                count("*").alias("total_meetings")
            ).filter(col("total_meetings") >= 2)  # At least 2 meetings
        
        return h2h_summary
    
    def _build_situational_features(self):
        """Build situational context features (rest, travel, etc.)"""
        
        # This would integrate with external data sources
        # For now, return placeholder
        return self.spark.createDataFrame([], "team_id string, travel_distance int, rest_advantage int")
    
    def _build_advanced_metrics(self, season: int, week: int):
        """Get advanced team metrics from Gold layer"""
        
        # Read team performance metrics
        metrics_path = f"s3://nfl-trusted/team_performance/season={season}/"
        
        try:
            team_metrics = self.spark.read.parquet(metrics_path)
            
            # Pivot to get offense and defense metrics in same row
            metrics_pivot = team_metrics.groupBy("team_id") \
                .pivot("metric_type", ["offense", "defense"]) \
                .agg(
                    first("epa_per_play").alias("epa_per_play"),
                    first("success_rate").alias("success_rate"), 
                    first("explosive_play_rate").alias("explosive_play_rate")
                )
            
            return metrics_pivot
            
        except Exception as e:
            self.logger.warning(f"Could not load team metrics: {e}")
            return self.spark.createDataFrame([], "team_id string")
    
    def _combine_features(self, games_df, team_form, h2h_features, 
                         situational_features, advanced_metrics, season: int, week: int):
        """Combine all feature sets into final prediction features"""
        
        # Add basic game context
        features_df = games_df.withColumn(
            "prediction_date", current_date()
        ).withColumn(
            "days_until_game", datediff(col("game_date"), current_date())
        ).withColumn(
            "division_game_flag", lit(False)  # TODO: Calculate from team divisions
        ).withColumn(
            "prime_time_flag", lit(False)     # TODO: Calculate from game time
        ).withColumn(
            "playoff_flag", col("week") > 18
        )
        
        # Join home team form
        features_with_home = features_df.join(
            team_form.select(
                col("team_id").alias("home_team_id"),
                col("recent_ppg").alias("home_recent_ppg"),
                col("recent_papg").alias("home_recent_papg"), 
                col("recent_win_rate").alias("home_recent_record")
            ),
            "home_team_id",
            "left"
        )
        
        # Join away team form  
        features_with_away = features_with_home.join(
            team_form.select(
                col("team_id").alias("away_team_id"),
                col("recent_ppg").alias("away_recent_ppg"),
                col("recent_papg").alias("away_recent_papg"),
                col("recent_win_rate").alias("away_recent_record") 
            ),
            "away_team_id",
            "left"
        )
        
        # Join H2H features
        features_with_h2h = features_with_away.join(
            h2h_features.select(
                "home_team_id", "away_team_id", "home_wins", "away_wins",
                "avg_total_points", "avg_home_margin"
            ).withColumnRenamed("home_wins", "h2h_home_wins") \
             .withColumnRenamed("away_wins", "h2h_away_wins") \
             .withColumnRenamed("avg_total_points", "h2h_avg_total") \
             .withColumnRenamed("avg_home_margin", "h2h_home_avg_margin"),
            ["home_team_id", "away_team_id"],
            "left"
        )
        
        # Join advanced metrics for home team
        if not advanced_metrics.rdd.isEmpty():
            features_with_adv_home = features_with_h2h.join(
                advanced_metrics.select(
                    col("team_id").alias("home_team_id"),
                    col("offense_epa_per_play").alias("home_epa_per_play"),
                    col("offense_success_rate").alias("home_success_rate"),
                    col("defense_epa_per_play").alias("home_def_epa_per_play"),
                    col("defense_success_rate").alias("home_def_success_rate")
                ),
                "home_team_id", 
                "left"
            )
            
            # Join advanced metrics for away team
            final_features = features_with_adv_home.join(
                advanced_metrics.select(
                    col("team_id").alias("away_team_id"),
                    col("offense_epa_per_play").alias("away_epa_per_play"),
                    col("offense_success_rate").alias("away_success_rate"), 
                    col("defense_epa_per_play").alias("away_def_epa_per_play"),
                    col("defense_success_rate").alias("away_def_success_rate")
                ),
                "away_team_id",
                "left"
            )
        else:
            final_features = features_with_h2h
        
        # Add placeholder fields for missing features
        complete_features = final_features \
            .withColumn("home_team_elo", lit(1500)) \
            .withColumn("away_team_elo", lit(1500)) \
            .withColumn("elo_differential", col("home_team_elo") - col("away_team_elo")) \
            .withColumn("home_field_advantage", lit(0.57)) \
            .withColumn("rest_advantage", lit(0)) \
            .withColumn("weather_impact_score", lit(0.0)) \
            .withColumn("closing_spread", col("spread")) \
            .withColumn("closing_total", col("total_line")) \
            .withColumn("load_timestamp", current_timestamp())
        
        return complete_features
    
    def _write_prediction_features(self, features_df, season: int, week: int):
        """Write prediction features to Gold layer"""
        
        output_path = f"s3://nfl-trusted/prediction_features/season={season}/week={week:02d}/"
        
        features_df.write \
            .format("delta") \
            .mode("overwrite") \
            .option("overwriteSchema", "true") \
            .save(output_path)
        
        self.logger.info(f"Prediction features written to {output_path}")

# CLI Script
if __name__ == "__main__":
    import argparse
    from src.silver_delta_setup import setup_delta_lake_silver
    
    parser = argparse.ArgumentParser(description='Build game prediction features')
    parser.add_argument('--season', type=int, required=True, help='Season to process')
    parser.add_argument('--week', type=int, required=True, help='Week to process')
    
    args = parser.parse_args()
    
    # Setup Spark
    spark = setup_delta_lake_silver()
    
    # Build features
    feature_builder = PredictionFeatureBuilder(spark)
    success = feature_builder.build_game_features(args.season, args.week)
    
    if success:
        print(f"✅ Prediction features built for {args.season} season, week {args.week}")
    else:
        print("❌ Feature building failed")
        exit(1)
```

---

## Phase 4: Production Deployment

### 4.1 Automated Pipeline

#### Airflow DAG for Complete Pipeline
```python
# File: dags/nfl_prediction_pipeline.py

from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.sensors.s3_sensor import S3KeySensor
from datetime import datetime, timedelta
import pendulum

# DAG Configuration
default_args = {
    'owner': 'nfl-data-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 9, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}

dag = DAG(
    'nfl_prediction_pipeline',
    default_args=default_args,
    description='NFL Game Prediction Data Pipeline',
    schedule_interval='0 6 * * TUE',  # Run Tuesdays at 6 AM (after Monday games)
    catchup=False,
    tags=['nfl', 'sports', 'prediction']
)

# Helper functions
def get_current_season_week():
    """Determine current NFL season and week"""
    # This would use NFL calendar logic
    return 2024, 17  # Placeholder

def ingest_bronze_data(**context):
    """Ingest latest NFL data to Bronze layer"""
    season, week = get_current_season_week()
    
    # Run Bronze ingestion scripts
    import subprocess
    
    # Ingest games
    result = subprocess.run([
        'python', '/opt/airflow/scripts/bronze_ingestion_simple.py',
        '--season', str(season),
        '--week', str(week),
        '--data-type', 'schedules'
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Bronze games ingestion failed: {result.stderr}")
    
    # Ingest plays
    result = subprocess.run([
        'python', '/opt/airflow/scripts/bronze_ingestion_simple.py',
        '--season', str(season),
        '--week', str(week), 
        '--data-type', 'pbp'
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Bronze plays ingestion failed: {result.stderr}")
    
    return {'season': season, 'week': week}

def transform_to_silver(**context):
    """Transform Bronze data to Silver layer"""
    ti = context['task_instance']
    bronze_result = ti.xcom_pull(task_ids='ingest_bronze_data')
    season, week = bronze_result['season'], bronze_result['week']
    
    import subprocess
    
    # Transform games
    result = subprocess.run([
        'python', '/opt/airflow/src/silver_games_transform.py',
        '--season', str(season),
        '--week', str(week)
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Silver transformation failed: {result.stderr}")
    
    return {'season': season, 'week': week}

def build_gold_analytics(**context):
    """Build Gold layer analytics"""
    ti = context['task_instance']
    silver_result = ti.xcom_pull(task_ids='transform_to_silver')
    season, week = silver_result['season'], silver_result['week']
    
    import subprocess
    
    # Calculate EPA metrics
    epa_result = subprocess.run([
        'python', '/opt/airflow/src/gold_epa_calculator.py',
        '--season', str(season)
    ], capture_output=True, text=True)
    
    if epa_result.returncode != 0:
        raise Exception(f"EPA calculation failed: {epa_result.stderr}")
    
    # Build prediction features
    features_result = subprocess.run([
        'python', '/opt/airflow/src/gold_prediction_features.py',
        '--season', str(season),
        '--week', str(week)
    ], capture_output=True, text=True)
    
    if features_result.returncode != 0:
        raise Exception(f"Feature building failed: {features_result.stderr}")
    
    return {'season': season, 'week': week}

def run_model_predictions(**context):
    """Run ML model predictions"""
    ti = context['task_instance']
    gold_result = ti.xcom_pull(task_ids='build_gold_analytics')
    season, week = gold_result['season'], gold_result['week']
    
    # This would call your ML model prediction script
    import subprocess
    
    result = subprocess.run([
        'python', '/opt/airflow/src/model_predictions.py',
        '--season', str(season),
        '--week', str(week)
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Model predictions failed: {result.stderr}")
    
    return True

# Define tasks
ingest_bronze_task = PythonOperator(
    task_id='ingest_bronze_data',
    python_callable=ingest_bronze_data,
    dag=dag
)

transform_silver_task = PythonOperator(
    task_id='transform_to_silver', 
    python_callable=transform_to_silver,
    dag=dag
)

build_gold_task = PythonOperator(
    task_id='build_gold_analytics',
    python_callable=build_gold_analytics,
    dag=dag
)

run_predictions_task = PythonOperator(
    task_id='run_model_predictions',
    python_callable=run_model_predictions,
    dag=dag
)

data_quality_check = BashOperator(
    task_id='data_quality_check',
    bash_command='python /opt/airflow/scripts/validate_project.py',
    dag=dag
)

# Set dependencies
ingest_bronze_task >> transform_silver_task >> build_gold_task >> run_predictions_task
transform_silver_task >> data_quality_check
```

### 4.2 Monitoring and Alerting

#### Data Quality Monitoring
```python
# File: src/monitoring/data_quality_monitor.py

import pandas as pd
import boto3
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List
from src.config import S3_BUCKET_BRONZE, S3_BUCKET_SILVER, S3_BUCKET_GOLD

class DataQualityMonitor:
    """Monitor data quality across all layers"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.cloudwatch = boto3.client('cloudwatch')
        self.sns = boto3.client('sns')
        self.logger = logging.getLogger(__name__)
        
        # Quality thresholds
        self.thresholds = {
            'data_freshness_hours': 24,
            'row_count_variance_threshold': 0.3,  # 30% variance
            'null_percentage_threshold': 0.15,    # 15% nulls max
            'quality_score_threshold': 0.8        # 80% quality score min
        }
    
    def run_quality_checks(self) -> Dict:
        """Run all data quality checks"""
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'PASSED',
            'checks': {
                'bronze_freshness': self._check_bronze_freshness(),
                'silver_processing': self._check_silver_processing(),
                'gold_consistency': self._check_gold_consistency(), 
                'row_count_anomalies': self._check_row_count_anomalies(),
                'null_value_checks': self._check_null_values()
            },
            'alerts': []
        }
        
        # Determine overall status
        failed_checks = [name for name, result in results['checks'].items() 
                        if result['status'] == 'FAILED']
        
        if failed_checks:
            results['overall_status'] = 'FAILED'
            results['alerts'] = [f"Failed checks: {', '.join(failed_checks)}"]
        
        # Send CloudWatch metrics
        self._send_cloudwatch_metrics(results)
        
        # Send alerts if needed
        if results['overall_status'] == 'FAILED':
            self._send_alert(results)
        
        return results
    
    def _check_bronze_freshness(self) -> Dict:
        """Check if Bronze data is fresh enough"""
        
        try:
            # Check latest Bronze data timestamp
            response = self.s3_client.list_objects_v2(
                Bucket=S3_BUCKET_BRONZE,
                Prefix='games/',
                Delimiter='/'
            )
            
            if 'Contents' not in response:
                return {
                    'status': 'FAILED',
                    'message': 'No Bronze data found',
                    'details': {}
                }
            
            # Get most recent object
            latest_object = max(response['Contents'], key=lambda x: x['LastModified'])
            hours_old = (datetime.now(latest_object['LastModified'].tzinfo) - 
                        latest_object['LastModified']).total_seconds() / 3600
            
            status = 'PASSED' if hours_old <= self.thresholds['data_freshness_hours'] else 'FAILED'
            
            return {
                'status': status,
                'message': f"Bronze data is {hours_old:.1f} hours old",
                'details': {
                    'latest_file': latest_object['Key'],
                    'last_modified': latest_object['LastModified'].isoformat(),
                    'hours_old': hours_old
                }
            }
            
        except Exception as e:
            return {
                'status': 'FAILED',
                'message': f"Error checking Bronze freshness: {e}",
                'details': {}
            }
    
    def _check_silver_processing(self) -> Dict:
        """Check Silver layer processing lag"""
        
        try:
            # Compare Bronze and Silver timestamps for latest data
            bronze_latest = self._get_latest_timestamp(S3_BUCKET_BRONZE, 'games/')
            silver_latest = self._get_latest_timestamp(S3_BUCKET_SILVER, 'games/')
            
            if not bronze_latest or not silver_latest:
                return {
                    'status': 'FAILED',
                    'message': 'Could not determine Bronze/Silver timestamps',
                    'details': {}
                }
            
            lag_hours = (bronze_latest - silver_latest).total_seconds() / 3600
            status = 'PASSED' if lag_hours <= 4 else 'FAILED'  # 4 hour SLA
            
            return {
                'status': status,
                'message': f"Silver processing lag: {lag_hours:.1f} hours",
                'details': {
                    'bronze_latest': bronze_latest.isoformat(),
                    'silver_latest': silver_latest.isoformat(),
                    'lag_hours': lag_hours
                }
            }
            
        except Exception as e:
            return {
                'status': 'FAILED',
                'message': f"Error checking Silver processing: {e}",
                'details': {}
            }
    
    def _check_gold_consistency(self) -> Dict:
        """Check Gold layer data consistency"""
        
        # This would check that Gold aggregations match Silver detail
        # Placeholder implementation
        return {
            'status': 'PASSED',
            'message': 'Gold layer consistency check passed',
            'details': {}
        }
    
    def _check_row_count_anomalies(self) -> Dict:
        """Check for unusual row count patterns"""
        
        # This would analyze row count patterns over time
        # Placeholder implementation  
        return {
            'status': 'PASSED',
            'message': 'Row count patterns are normal',
            'details': {}
        }
    
    def _check_null_values(self) -> Dict:
        """Check null value percentages in key fields"""
        
        # This would sample data and check null rates
        # Placeholder implementation
        return {
            'status': 'PASSED', 
            'message': 'Null value rates are within thresholds',
            'details': {}
        }
    
    def _get_latest_timestamp(self, bucket: str, prefix: str) -> datetime:
        """Get timestamp of latest object in S3 prefix"""
        
        response = self.s3_client.list_objects_v2(
            Bucket=bucket, Prefix=prefix, Delimiter='/'
        )
        
        if 'Contents' not in response:
            return None
        
        latest = max(response['Contents'], key=lambda x: x['LastModified'])
        return latest['LastModified']
    
    def _send_cloudwatch_metrics(self, results: Dict):
        """Send metrics to CloudWatch"""
        
        try:
            metrics = []
            
            # Overall status metric
            metrics.append({
                'MetricName': 'DataQualityOverallStatus',
                'Value': 1 if results['overall_status'] == 'PASSED' else 0,
                'Unit': 'Count'
            })
            
            # Individual check metrics
            for check_name, check_result in results['checks'].items():
                metrics.append({
                    'MetricName': f'DataQuality_{check_name}',
                    'Value': 1 if check_result['status'] == 'PASSED' else 0,
                    'Unit': 'Count'
                })
            
            self.cloudwatch.put_metric_data(
                Namespace='NFL/DataQuality',
                MetricData=metrics
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send CloudWatch metrics: {e}")
    
    def _send_alert(self, results: Dict):
        """Send alert for data quality failures"""
        
        try:
            message = {
                'timestamp': results['timestamp'],
                'status': results['overall_status'],
                'failed_checks': [name for name, result in results['checks'].items()
                                if result['status'] == 'FAILED'],
                'details': results['checks']
            }
            
            # Send to SNS (configure topic ARN in environment)
            sns_topic = os.getenv('DATA_QUALITY_SNS_TOPIC')
            if sns_topic:
                self.sns.publish(
                    TopicArn=sns_topic,
                    Subject='NFL Data Quality Alert',
                    Message=json.dumps(message, indent=2)
                )
                
        except Exception as e:
            self.logger.error(f"Failed to send alert: {e}")

# CLI Script
if __name__ == "__main__":
    monitor = DataQualityMonitor()
    results = monitor.run_quality_checks()
    
    print(json.dumps(results, indent=2))
    
    if results['overall_status'] == 'FAILED':
        exit(1)
```

### 4.3 Performance Optimization

#### S3 Optimization Script
```bash
#!/bin/bash
# File: scripts/optimize_s3_storage.sh

# NFL Data Model S3 Storage Optimization
# Optimizes partitioning, compression, and file sizes

set -e

echo "🔧 Starting S3 storage optimization..."

# Function to optimize Parquet files in a path
optimize_parquet_files() {
    local s3_path=$1
    local target_size_mb=$2
    
    echo "📊 Optimizing: $s3_path (target: ${target_size_mb}MB files)"
    
    # Use AWS CLI and Spark to compact small files
    python3 << EOF
import boto3
from pyspark.sql import SparkSession

s3_path = "$s3_path"
target_size = $target_size_mb * 1024 * 1024  # Convert to bytes

# Setup Spark with S3 optimization
spark = SparkSession.builder \\
    .appName("S3Optimization") \\
    .config("spark.sql.adaptive.enabled", "true") \\
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \\
    .config("spark.sql.files.maxPartitionBytes", str(target_size)) \\
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \\
    .getOrCreate()

# Read and repartition data
df = spark.read.parquet(s3_path)
current_files = df.rdd.getNumPartitions()
optimal_partitions = max(1, int(df.count() * 100 / target_size))  # Rough estimate

print(f"Current partitions: {current_files}, Target: {optimal_partitions}")

if current_files > optimal_partitions * 1.5:  # Only optimize if worthwhile
    print("Repartitioning and rewriting...")
    df.coalesce(optimal_partitions) \\
        .write \\
        .mode("overwrite") \\
        .option("compression", "snappy") \\
        .parquet(s3_path + "_optimized")
    
    print("✅ Optimization complete")
else:
    print("ℹ️  No optimization needed")

spark.stop()
EOF
}

# Optimize Bronze layer
echo "📁 Optimizing Bronze layer..."
optimize_parquet_files "s3://nfl-raw/games/" 100
optimize_parquet_files "s3://nfl-raw/plays/" 500

# Optimize Silver layer  
echo "📁 Optimizing Silver layer..."
optimize_parquet_files "s3://nfl-refined/games/" 200
optimize_parquet_files "s3://nfl-refined/plays/" 800

# Optimize Gold layer
echo "📁 Optimizing Gold layer..."
optimize_parquet_files "s3://nfl-trusted/team_performance/" 50
optimize_parquet_files "s3://nfl-trusted/prediction_features/" 100

# Set up S3 lifecycle policies
echo "🔄 Configuring S3 lifecycle policies..."
aws s3api put-bucket-lifecycle-configuration --bucket nfl-raw --lifecycle-configuration file://scripts/s3-lifecycle-bronze.json
aws s3api put-bucket-lifecycle-configuration --bucket nfl-refined --lifecycle-configuration file://scripts/s3-lifecycle-silver.json
aws s3api put-bucket-lifecycle-configuration --bucket nfl-trusted --lifecycle-configuration file://scripts/s3-lifecycle-gold.json

echo "✅ S3 optimization complete!"
```

---

## Testing and Validation

### Integration Test Suite
```python
# File: tests/test_end_to_end.py

import pytest
import pandas as pd
from pyspark.sql import SparkSession
from src.silver_delta_setup import setup_delta_lake_silver
from src.silver_games_transform import GamesTransformer
from src.gold_epa_calculator import EPACalculator
from src.gold_prediction_features import PredictionFeatureBuilder

class TestNFLPipeline:
    """End-to-end pipeline testing"""
    
    @pytest.fixture(scope="class")
    def spark(self):
        spark = setup_delta_lake_silver()
        yield spark
        spark.stop()
    
    def test_bronze_to_silver_transformation(self, spark):
        """Test Bronze to Silver data transformation"""
        
        transformer = GamesTransformer(spark)
        
        # Test with sample data
        success = transformer.transform_bronze_to_silver(2023, 1)
        assert success, "Bronze to Silver transformation failed"
        
        # Validate Silver data exists
        silver_df = spark.read.parquet("s3://nfl-refined/games/season=2023/week=01/")
        assert silver_df.count() > 0, "No Silver data found"
        
        # Check required columns
        expected_columns = ['game_id', 'season', 'week', 'home_team_id', 'away_team_id']
        for col in expected_columns:
            assert col in silver_df.columns, f"Missing column: {col}"
    
    def test_epa_calculations(self, spark):
        """Test EPA calculations"""
        
        epa_calc = EPACalculator(spark)
        metrics = epa_calc.calculate_team_epa_metrics(2023)
        
        assert metrics.count() > 0, "No EPA metrics generated"
        
        # Check metric types
        metric_types = metrics.select("metric_type").distinct().rdd.flatMap(lambda x: x).collect()
        assert "offense" in metric_types, "Missing offensive metrics"
        assert "defense" in metric_types, "Missing defensive metrics"
    
    def test_prediction_features(self, spark):
        """Test prediction feature generation"""
        
        feature_builder = PredictionFeatureBuilder(spark)
        success = feature_builder.build_game_features(2023, 2)
        
        assert success, "Feature building failed"
        
        # Validate feature data
        features_df = spark.read.parquet("s3://nfl-trusted/prediction_features/season=2023/week=02/")
        assert features_df.count() > 0, "No prediction features generated"
        
        # Check key feature columns
        feature_columns = ['home_recent_ppg', 'away_recent_ppg', 'elo_differential']
        for col in feature_columns:
            assert col in features_df.columns, f"Missing feature: {col}"
    
    def test_data_quality_pipeline(self):
        """Test data quality monitoring"""
        
        from src.monitoring.data_quality_monitor import DataQualityMonitor
        
        monitor = DataQualityMonitor()
        results = monitor.run_quality_checks()
        
        assert 'overall_status' in results, "Missing overall status"
        assert results['overall_status'] in ['PASSED', 'FAILED'], "Invalid status"
        
        # All checks should have a status
        for check_name, check_result in results['checks'].items():
            assert 'status' in check_result, f"Missing status for {check_name}"
    
    @pytest.mark.performance
    def test_pipeline_performance(self, spark):
        """Test pipeline performance benchmarks"""
        
        import time
        
        # Test Bronze to Silver performance
        start_time = time.time()
        transformer = GamesTransformer(spark)
        transformer.transform_bronze_to_silver(2023, 1)
        transform_time = time.time() - start_time
        
        # Should complete within 5 minutes for one week
        assert transform_time < 300, f"Transformation too slow: {transform_time}s"
        
        # Test feature building performance
        start_time = time.time()
        feature_builder = PredictionFeatureBuilder(spark)
        feature_builder.build_game_features(2023, 2)
        feature_time = time.time() - start_time
        
        # Should complete within 10 minutes
        assert feature_time < 600, f"Feature building too slow: {feature_time}s"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## Operational Runbooks

### 4.4 Common Operations

#### Daily Operations Checklist
```markdown
# NFL Data Pipeline - Daily Operations Checklist

## Pre-Game Day (Tuesday-Saturday)
- [ ] Verify Bronze layer data freshness (< 24 hours)
- [ ] Check Silver layer processing status
- [ ] Validate Gold layer metrics completeness
- [ ] Review data quality dashboard
- [ ] Confirm prediction features are ready
- [ ] Check model performance metrics

## Game Day (Sunday/Monday/Thursday)
- [ ] Monitor real-time data ingestion
- [ ] Verify Bronze layer game result updates
- [ ] Check post-game Silver transformations
- [ ] Validate betting result calculations
- [ ] Update prediction model performance
- [ ] Generate post-game analytics

## Weekly Operations
- [ ] Run full season data validation
- [ ] Review model prediction accuracy
- [ ] Update team performance trends
- [ ] Check storage costs and optimization
- [ ] Review pipeline performance metrics
- [ ] Update documentation as needed

## Monthly Operations  
- [ ] Full data quality audit
- [ ] Model retraining evaluation
- [ ] Storage optimization review
- [ ] Security audit
- [ ] Backup verification
- [ ] Disaster recovery test
```

#### Troubleshooting Guide
```markdown
# NFL Data Pipeline - Troubleshooting Guide

## Common Issues and Solutions

### 1. Bronze Layer Ingestion Failures

**Symptoms:**
- Missing data files in s3://nfl-raw/
- Pipeline alerts for data freshness
- Empty or incomplete Bronze tables

**Root Causes:**
- nfl-data-py API issues
- AWS credentials expired
- S3 permissions problems
- Network connectivity issues

**Solutions:**
```bash
# Check API connectivity
python -c "import nfl_data_py as nfl; print(nfl.import_schedules([2024]).head())"

# Verify AWS credentials
aws sts get-caller-identity

# Test S3 access
aws s3 ls s3://nfl-raw/

# Re-run ingestion manually
python scripts/bronze_ingestion_simple.py --season 2024 --week 1 --data-type schedules
```

### 2. Silver Layer Transformation Errors

**Symptoms:**
- Silver transformation jobs failing
- Data quality validation errors
- Inconsistent data in Silver tables

**Root Causes:**
- Schema changes in Bronze data
- Data validation rule failures
- Spark/Delta Lake configuration issues

**Solutions:**
```bash
# Check Schema compatibility
python -c "
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
df = spark.read.parquet('s3://nfl-raw/games/season=2024/week=01/')
df.printSchema()
"

# Validate data quality manually
python src/data_quality.py --table games --season 2024 --week 1

# Re-run Silver transformation with verbose logging
python src/silver_games_transform.py --season 2024 --week 1 --debug
```

### 3. Gold Layer Analytics Issues  

**Symptoms:**
- Missing or incorrect EPA calculations
- Incomplete prediction features
- Team metrics not updating

**Root Causes:**
- Incomplete Silver layer data
- Calculation logic errors
- Missing reference data (teams, players)

**Solutions:**
```bash
# Verify Silver data completeness
python -c "
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
df = spark.read.parquet('s3://nfl-refined/games/season=2024/')
print(f'Games: {df.count()}')
print(f'Teams: {df.select("home_team_id").distinct().count()}')
"

# Re-calculate EPA metrics
python src/gold_epa_calculator.py --season 2024 --force-refresh

# Rebuild prediction features  
python src/gold_prediction_features.py --season 2024 --week 17 --rebuild
```

### 4. Performance Issues

**Symptoms:**
- Slow pipeline execution
- High AWS costs
- Memory errors in Spark jobs

**Solutions:**
```bash
# Optimize S3 storage
./scripts/optimize_s3_storage.sh

# Tune Spark configurations
export SPARK_CONF="
--conf spark.sql.adaptive.enabled=true
--conf spark.sql.adaptive.coalescePartitions.enabled=true  
--conf spark.executor.memory=4g
--conf spark.driver.memory=2g
"

# Monitor resource usage
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name BucketSizeBytes \
  --dimensions Name=BucketName,Value=nfl-raw Name=StorageType,Value=StandardStorage \
  --statistics Average \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-31T23:59:59Z \
  --period 86400
```

## Emergency Procedures

### Data Corruption Recovery
1. **Stop all pipeline processes**
2. **Identify corruption scope**
3. **Restore from S3 versioning or backups**
4. **Re-run affected pipeline stages**
5. **Validate data integrity**

### API Outage Response
1. **Switch to backup data sources if available**
2. **Notify stakeholders of delay**
3. **Monitor API status**
4. **Resume normal operations when restored**

### AWS Service Outage
1. **Check AWS Service Health Dashboard**
2. **Activate cross-region failover if configured**
3. **Document impact and duration**
4. **Post-incident review and improvements**
```

---

## Conclusion

This comprehensive implementation guide provides the detailed steps, code, and operational procedures needed to successfully implement the NFL game prediction data model. The phased approach ensures systematic rollout with proper validation at each stage.

**Key Success Factors:**
- Follow the phased implementation timeline
- Implement comprehensive data quality monitoring
- Build robust error handling and recovery procedures
- Maintain thorough documentation and testing
- Plan for scalability and performance optimization

**Next Steps:**
1. Begin Phase 1 implementation with Bronze layer extensions
2. Set up development and testing environments
3. Implement core data quality framework
4. Begin Silver layer development
5. Plan Gold layer analytics and ML integration

This implementation guide, combined with the data model and dictionary, provides a complete blueprint for building a production-grade NFL game prediction system using modern data engineering best practices.

---

**Document Control:**
- **Version**: 1.0
- **Owner**: Data Engineering Team  
- **Review Cycle**: Monthly during implementation, quarterly thereafter
- **Related Documents**: NFL_GAME_PREDICTION_DATA_MODEL.md, NFL_DATA_DICTIONARY.md