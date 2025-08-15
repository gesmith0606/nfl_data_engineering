# Model Context Protocol for NFL Data Engineering Pipeline

## Project Overview
This is a comprehensive NFL data engineering project designed to ingest, process, and analyze NFL game data using modern data engineering best practices. The pipeline implements a medallion architecture with **local Python development** and **dedicated S3 storage**.

**Primary Goal:** Create a robust, scalable, and modular data pipeline that supports multiple analytical use cases including game log analysis, player performance tracking, and betting analytics.

**Data Source:** Raw NFL data sourced from the `nfl-data-py` library, providing comprehensive game, player, and team statistics.

**Current Architecture (Local + S3):**
- **Development Environment:** Local Python 3.8+ with virtual environment
- **Storage Layer:** Dedicated AWS S3 buckets in us-east-2 region
- **Data Processing:** Local execution with boto3 S3 integration
- **Future Migration:** Databricks Standard/Premium upgrade path available

**Your Infrastructure Details:**
- **S3 Buckets:** `nfl-raw` (Bronze), `nfl-refined` (Silver), `nfl-trusted` (Gold)
- **AWS Region:** us-east-2 (Ohio)
- **Databricks Workspace:** `dbc-c9b1be11-c0c8.cloud.databricks.com` (Community Edition - learning only)
- **User Account:** `smithge0606@gmail.com`

**Model Context Protocol (MCP) Setup:**
- **Filesystem MCP:** Complete project file and directory management
- **Sequential Thinking MCP:** Structured problem-solving for complex pipeline issues
- **Puppeteer MCP:** Web browser automation for data collection and validation
- **Configuration:** All MCPs installed globally and configured in `.vscode/mcp.json`

## Architecture Overview
The project follows a **Medallion Architecture** with **local compute + cloud storage separation**:

**Storage Layer (Your AWS S3 Buckets in us-east-2):**
- **Bronze (`nfl-raw`):** Raw data ingestion (Parquet format)
- **Silver (`nfl-refined`):** Cleaned and standardized data (Parquet format)
- **Gold (`nfl-trusted`):** Business-ready aggregations (Parquet format)

**Compute Layer (Local Python Environment):**
- **Local Development:** Primary execution environment with full S3 access
- **Direct S3 Integration:** boto3 for seamless cloud storage operations
- **Future Scaling:** Ready for Databricks Standard upgrade when needed
- **Databricks Community:** Available for learning PySpark concepts (DBFS only)

## Data Pipeline Stages

### Bronze Layer (Raw Ingestion)
**Purpose:** Ingest unprocessed data directly from nfl-data-py to your `nfl-raw` S3 bucket

**Current Implementation:**
1. **Local Python Execution:** Run notebooks locally with command-line parameters
2. **NFL Data Fetching:** Use nfl-data-py library to get game/player data
3. **S3 Storage:** Direct upload to `s3://nfl-raw/` using boto3
4. **Partitioning:** Organize by `games/season=YYYY/week=WW/` structure
5. **Format:** Parquet files for efficient storage and querying

**Execution Pattern:**
```bash
python notebooks/bronze_ingestion.py --season 2024 --week 1
# Outputs to: s3://nfl-raw/games/season=2024/week=1/
```

### Silver Layer (Data Cleaning)
**Purpose:** Clean, standardize, and validate data from `nfl-raw` → `nfl-refined`

**Current Implementation:**
1. **S3 Data Reading:** Load Parquet files from Bronze layer using pandas/pyarrow
2. **Data Quality Pipeline:**
   - Remove duplicates and invalid records
   - Standardize data types and formats
   - Handle missing values with business logic
   - Validate against NFL business rules
3. **S3 Storage:** Save cleaned data to `s3://nfl-refined/`
4. **Quality Reports:** Generate data quality metrics and validation reports

**Execution Pattern:**
### **Data Validation & Enhancement with MCP Integration:**
```python
# Example: Cross-validate game scores using Puppeteer MCP
# 1. Get data from nfl-data-py
import nfl_data_py as nfl
games_data = nfl.import_schedules([2024])

# 2. Use Puppeteer MCP to scrape ESPN.com for same game
# (MCP browser automation capabilities)
# 3. Compare results for data quality assurance
```

### **Enhanced Data Sources via MCPs:**
- **Weather conditions** during games (via web scraping)
- **Betting line movements** over time (Puppeteer MCP automation)
- **Player injury status** updates from team websites
- **News sentiment** around teams/players from sports media sites
- **Real-time statistics** validation against multiple sources

### **Development Workflow with MCP Support:**
- **Sequential Thinking MCP:** Break down complex pipeline problems systematically
- **Filesystem MCP:** Manage medallion architecture file organization
- **Puppeteer MCP:** Automate data collection from multiple NFL data sources

### Gold Layer (Business Analytics)
**Purpose:** Create aggregated, analysis-ready datasets in `nfl-trusted` bucket

**Current Implementation:**
1. **Multi-week Aggregation:** Read all Silver data for a season
2. **Business Metrics Calculation:**
   - Team performance statistics per season
   - Player rankings and performance trends
   - Game outcome analysis and patterns
   - Betting-relevant aggregated statistics
3. **Analytics Optimization:** Structure data for BI tools and analysis
4. **S3 Storage:** Final curated datasets in `s3://nfl-trusted/`

**Execution Pattern:**
```bash
python notebooks/gold_aggregation.py --season 2024
# Input: s3://nfl-refined/games/season=2024/
# Output: s3://nfl-trusted/team_stats/season=2024/
```

## Migration Strategy: Future Databricks Upgrade

### Current State (Local + S3)
**Advantages:**
- ✅ Full control over your dedicated S3 buckets
- ✅ No monthly Databricks costs during development
- ✅ Direct boto3 integration with AWS services
- ✅ Local debugging and development workflow

### Future Databricks Standard/Premium Benefits
**When to Upgrade:**
- Data volume exceeds local processing capacity (>10GB per processing job)
- Need for distributed computing across multiple nodes
- Require production scheduling and monitoring features
- Team collaboration on shared notebooks and clusters

**Upgrade Preparation:**
- Current code structure already supports PySpark conversion
- S3 bucket architecture ready for Databricks mounting
- Configuration management prepared for secrets integration
- Notebooks designed with widget parameterization patterns

## Directory Structure
The project follows this modular structure optimized for local development and Databricks deployment:

```
nfl_data_engineering/
├── .vscode/
│   └── mcp.json                    # Model Context Protocol configuration
├── notebooks/                      # Databricks execution notebooks
│   ├── bronze_ingestion.py         # Raw data ingestion (Bronze layer)
│   ├── silver_transformation.py    # Data cleaning (Silver layer)
│   └── gold_aggregation.py         # Business aggregations (Gold layer)
├── src/                            # Shared Python modules
│   ├── __init__.py
│   ├── config.py                   # Configuration management
│   └── utils.py                    # Reusable utility functions
├── tests/                          # Test suite
│   ├── __init__.py
│   └── test_utils.py               # Unit tests for utilities
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore patterns
├── requirements.txt                # Python dependencies
├── setup.sh                       # Automated project setup
├── README.md                       # Project documentation
└── copilot-instructions.md         # AI assistant guidelines (this file)
```

**Key Design Principles:**
- **Local Development First:** All Python modules can be developed and tested locally
- **Databricks Optimized:** Notebooks designed specifically for Databricks execution
- **Modular Architecture:** Shared utilities and configuration promote code reuse
- **AI Integration:** MCP configuration enables AI-assisted development workflows

## Environment Configuration and Best Practices

### Local Development Environment
**Required Setup:**
```bash
# Python virtual environment (required)
python -m venv venv
source venv/bin/activate  # macOS/Linux

# Install dependencies for your specific setup
pip install -r requirements.txt

# Configure AWS credentials (required for S3 access)
aws configure
# Enter your AWS access key, secret key, and region: us-east-2
```

**MCP Server Installation (Required for AI-Assisted Development):**
```bash
# Install all MCP servers globally
npm install -g @modelcontextprotocol/server-filesystem
npm install -g @modelcontextprotocol/server-sequential-thinking  
npm install -g puppeteer-mcp-server

# Verify installation
npm list -g | grep -E "(modelcontextprotocol|puppeteer-mcp)"
```

**MCP Configuration:** 
Your `.vscode/mcp.json` file contains three configured servers:
- **Filesystem MCP:** Project file management and organization
- **Sequential Thinking MCP:** Structured problem-solving assistance
- **Puppeteer MCP:** Web browser automation for data collection

**Environment Variables (.env file):**
```bash
# Your pre-configured S3 buckets
S3_BUCKET_BRONZE=nfl-raw
S3_BUCKET_SILVER=nfl-refined
S3_BUCKET_GOLD=nfl-trusted
AWS_REGION=us-east-2

# Your Databricks workspace (future use)
DATABRICKS_WORKSPACE_URL=https://dbc-c9b1be11-c0c8.cloud.databricks.com

# Processing defaults
DEFAULT_SEASON=2024
DEFAULT_WEEK=1
```

### S3 Integration Patterns
**Standard S3 Operations:**
```python
import boto3
from src.config import S3_BUCKET_BRONZE, S3_REGION

# Initialize S3 client with your region
s3_client = boto3.client('s3', region_name=S3_REGION)

# Upload to your specific buckets
s3_client.upload_file(
    local_file, 
    S3_BUCKET_BRONZE, 
    f"games/season=2024/week=1/data.parquet"
)

# Download from your buckets
s3_client.download_file(
    S3_BUCKET_BRONZE,
    f"games/season=2024/week=1/data.parquet",
    local_file
)
```

### Databricks Community Edition Guidelines
**Current Limitations with Your Setup:**
- ❌ Cannot access your S3 buckets (`nfl-raw`, `nfl-refined`, `nfl-trusted`)
- ❌ Cannot install permanent cluster libraries
- ❌ No secrets management for AWS credentials
- ✅ Can upload notebooks for learning PySpark syntax
- ✅ Can work with sample data in DBFS for prototyping

**Learning Mode Usage:**
```python
# In Databricks Community notebooks - use for learning only
# Cannot connect to your actual S3 buckets
sample_data = spark.createDataFrame([
    (1, "Sample Game", "2024-09-01"),
    (2, "Another Game", "2024-09-08")
], ["game_id", "game_name", "date"])

# Practice PySpark transformations
sample_data.groupBy("date").count().show()
```

### Production Upgrade Path
**When to Consider Databricks Standard:**
- Processing time exceeds 30 minutes locally
- Data size per job exceeds 5-10GB
- Need distributed computing across multiple cores
- Require production scheduling and monitoring

**Upgrade Benefits:**
- Direct S3 mounting to your buckets
- Cluster libraries for nfl-data-py, boto3
- Secrets management for AWS credentials
- Auto-scaling clusters for large datasets
- Production job scheduling and monitoring

## Coding and Naming Conventions

### File and Variable Naming
**Python Files:** Use `snake_case` for all Python files
- ✅ `bronze_ingestion.py`, `silver_transformation.py`, `gold_aggregation.py`
- ❌ `bronzeIngestion.py`, `Bronze-Ingestion.py`

**Python Variables and Functions:** Consistent `snake_case` throughout
```python
# Good examples
season_data = get_nfl_games(season=2024, week=1)
cleaned_dataframe = apply_data_quality_checks(raw_dataframe)

# Avoid camelCase or mixed naming
seasonData = getNflGames(season=2024, week=1)  # ❌
```

**Constants:** Use `UPPER_SNAKE_CASE` for configuration constants
```python
# Configuration constants
DEFAULT_S3_BUCKET = "nfl-data-engineering"
BRONZE_LAYER_PATH = "bronze"
MAX_RETRIES = 3
```

### Delta Table and S3 Path Naming
**S3 Path Structure:** Follow consistent hierarchical naming:
```
s3://bucket-name/layer/data-type/season=YYYY/week=WW/
Examples:
- s3://nfl-data-bucket/bronze/games/season=2024/week=1/
- s3://nfl-data-bucket/silver/games/season=2024/week=1/
- s3://nfl-data-bucket/gold/team_stats/season=2024/
```

**Delta Table Naming:** Use pattern `layer_datatype_entity`
- ✅ `bronze_games`, `silver_games`, `gold_team_stats`
- ❌ `BronzeGames`, `silver-games`, `goldTeamStats`

### Databricks Notebook Organization
**Notebook Structure:** Follow consistent cell organization:
1. **Setup Cell:** Imports, widgets, and configuration
2. **Configuration Cell:** Parameter extraction and validation
3. **Data Processing Cells:** Core business logic with clear headers
4. **Output Cell:** Results validation and storage
5. **Cleanup Cell:** Resource cleanup and logging

**Cell Headers:** Use markdown cells with clear section headers:
```python
# COMMAND ----------
# MAGIC %md
# MAGIC ## Bronze Layer Data Ingestion
# MAGIC 
# MAGIC This section handles raw data ingestion from nfl-data-py library
# MAGIC - Input: nfl-data-py API calls
# MAGIC - Output: Parquet files in S3 Bronze layer
# MAGIC - Partitioning: By season and week
```

### Code Quality Standards
**Function Design:** Create modular, testable functions:
```python
def validate_game_data(df: DataFrame, season: int, week: int) -> DataFrame:
    """
    Validate NFL game data for completeness and accuracy.
    
    Args:
        df: PySpark DataFrame with game data
        season: NFL season year
        week: NFL week number
    
    Returns:
        Validated DataFrame
    
    Raises:
        ValueError: If validation fails
    """
    # Implementation with clear error handling
```

**Error Handling:** Implement comprehensive error handling:
```python
try:
    game_data = get_nfl_games(season, week)
    validated_data = validate_game_data(game_data, season, week)
except Exception as e:
    logger.error(f"Failed to process season {season}, week {week}: {str(e)}")
    raise
```

**Documentation:** Include docstrings for all functions and classes:
- Use Google-style docstrings for consistency
- Document parameters, return values, and exceptions
- Include usage examples for complex functions

## Development Workflow Best Practices

### Local Development
**Environment Setup:** Always use virtual environments:
```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

**Testing Strategy:** Implement comprehensive testing:
```python
# Unit tests for utility functions
def test_get_s3_path():
    expected = "s3://test-bucket/bronze/games/season=2024/week=1/"
    actual = get_s3_path("test-bucket", "bronze", "games", 2024, 1)
    assert actual == expected
```

**Code Validation:** Run validation before committing:
```bash
# Run tests
python -m pytest tests/ -v

# Check imports work correctly
python -c "from src.config import get_s3_path; print('✅ Imports working')"
```

### Databricks Deployment
**Pre-deployment Checklist:**
- [ ] All notebooks have required widget parameters
- [ ] Shared utilities are importable in Databricks environment
- [ ] No hardcoded credentials or paths
- [ ] Error handling covers expected failure scenarios
- [ ] Logging provides sufficient debugging information

**Performance Considerations:**
- Use broadcast joins for small lookup tables
- Partition data appropriately for query patterns
- Leverage Delta Lake optimizations (Z-ordering, auto-compaction)
- Monitor Spark UI for performance bottlenecks

## Important Implementation Notes

### Idempotency Requirements
**Critical Principle:** All pipeline executions must be idempotent
- Re-running with same parameters produces identical results
- No side effects from multiple executions
- Safe to retry failed runs without data corruption

**Implementation Strategies:**
```python
# Use Delta Lake merge operations for upserts
bronze_table.merge(new_data, "bronze.game_id = new_data.game_id") \
    .whenMatched().updateAll() \
    .whenNotMatched().insertAll() \
    .execute()
```

### Data Processing Standards
**PySpark Requirements:** All data processing must use PySpark DataFrames
- Never use pandas for large-scale processing
- Convert pandas DataFrames to PySpark early in pipeline
- Leverage Spark's distributed computing capabilities

**Memory Management:** Optimize for large datasets
```python
# Cache frequently accessed DataFrames
game_data.cache()

# Use appropriate file formats
df.write.mode("overwrite").parquet(s3_path)  # Bronze layer
df.write.mode("overwrite").format("delta").save(s3_path)  # Silver/Gold layers
```

### Monitoring and Logging
**Structured Logging:** Implement consistent logging patterns:
```python
import logging

logger = logging.getLogger(__name__)

def process_season_week(season: int, week: int):
    logger.info(f"Starting processing for season {season}, week {week}")
    try:
        # Processing logic
        logger.info(f"Successfully processed {record_count} records")
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        raise
```

**Data Quality Metrics:** Track important metrics at each layer:
- Record counts and data freshness
- Null value percentages and data completeness
- Schema evolution and breaking changes
- Processing execution times and resource usage