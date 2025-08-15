# NFL Data Engineering Pipeline

## Project Overview
This project implements an end-to-end data engineering pipeline for N## Key Design Principles:**
- **Local Development First:** Python files can be developed and tested locally
- **Databricks Deployment:** Notebooks designed for Databricks execution  
- **Modular Design:** Shared utilities and configuration in `src/` directory
- **Testability:** Comprehensive test coverage for core functions
- **AI Integration:** Complete MCP configuration for AI-assisted development
- **Web Automation:** Puppeteer MCP for data validation and additional source collectionl Football League (NFL) data, specifically focusing on game data analysis. The pipeline is designed to ingest raw data, process it, and transform it into a structured format suitable for analysis and downstream applications, such as machine learning models or business intelligence dashboards. The entire pipeline is built using AWS S3 for storage and Databricks as the compute platform, adhering to the principles of a modern data lakehouse architecture.

This project serves as a foundation for three potential use cases:
1. **NFL Game Log Data Pipeline** - Basic game data ingestion and transformation
2. **Player Performance Analysis and Prediction** - Advanced analytics and ML modeling  
3. **NFL Betting and Odds Analysis** - Sports betting analytics integration

The README.md is designed to provide comprehensive context for developers and AI coding assistants like GitHub Copilot, explaining the project's purpose, architecture, and file structure to facilitate efficient development and maintenance.

## Project Goal
The primary objective of this pipeline is to extract NFL game data from the `nfl-data-py` library and progressively refine it through a medallion architecture pattern. This ensures data quality, reliability, and reusability for various analytical use cases.

**Core Pipeline Objectives:**
1. **Bronze Layer**: Ingest raw NFL game data for specified seasons and weeks
2. **Silver Layer**: Cleanse, standardize, and validate the data with quality checks  
3. **Gold Layer**: Create aggregated, business-ready datasets for analytics and reporting

**Key Features:**
- Parameterized notebooks for flexible execution
- Comprehensive data quality validation
- AWS S3 integration with partitioned storage
- Delta Lake format for ACID transactions
- Model Context Protocol (MCP) integration for AI-assisted development

## Architecture Overview

### Storage Layer (AWS S3 - us-east-2)
**Your Dedicated S3 Buckets:**
- **Bronze Layer:** `nfl-raw` - Raw data ingestion from nfl-data-py
- **Silver Layer:** `nfl-refined` - Cleaned and standardized data  
- **Gold Layer:** `nfl-trusted` - Business-ready aggregations and analytics

**Data Format Strategy:**
- Bronze: Parquet files for efficient columnar storage
- Silver/Gold: Delta Lake format for ACID transactions (when using full Databricks)
- Local Development: Parquet files with CSV exports for analysis

### Compute Layer Architecture
**Current Setup (Local Development + S3):**
- **Local Python Environment:** Primary development and execution environment
- **AWS S3 Integration:** Direct boto3 connectivity to your buckets
- **Databricks Community Edition:** Learning and prototyping (DBFS only)
- **Future Migration Path:** Upgrade to Databricks Standard/Premium for production scale

**Databricks Workspace (Ready for Upgrade):**
- **URL:** `dbc-c9b1be11-c0c8.cloud.databricks.com`
- **User:** `smithge0606@gmail.com`
- **Current Limitation:** Community Edition - no direct S3 access
- **Upgrade Benefits:** Full S3 mounting, secrets management, cluster libraries

**Bronze Layer (Raw)**  
- Contains unprocessed data directly from `nfl-data-py`
- Preserves original data structure and values
- Adds audit columns (created_at, updated_at, data_source)
- Storage format: Parquet for fast ingestion

**Silver Layer (Cleaned)**  
- Data quality validation and cleansing applied
- Standardized team names, date formats, and data types
- Null value handling and duplicate removal
- Derived fields added (total_score, winning_team)
- Storage format: Delta Lake for ACID transactions

**Gold Layer (Curated)**  
- Business-ready aggregated datasets
- Team season statistics (wins, losses, scoring averages)
- Weekly league-wide metrics and trends  
- Optimized for analytics tools and reporting
- Storage format: Delta Lake with Z-ordering for performance

## Data Source
The pipeline uses the **nfl-data-py** Python library as its primary data source. This library provides programmatic access to comprehensive NFL datasets originally sourced from nflfastR.

**Available Data Types:**
- **Game Schedules**: Basic game information (teams, dates, scores)
- **Play-by-Play Data**: Detailed information for every play in every game
- **Player Statistics**: Individual player performance metrics
- **Team Statistics**: Aggregated team-level metrics
- **Roster Information**: Player roster data by team and season

**Current Focus**: This pipeline initially focuses on **game-level data** including:
- Game schedules and basic information
- Final scores and game outcomes
- Team matchups and game dates
- Season and week organization

**Future Expansion Opportunities:**
- Player performance metrics and statistics
- Play-by-play analysis for advanced metrics (EPA, WPA)
- Injury reports and roster changes
- Weather data and game conditions
- Betting odds and market data integration

## Project Structure
The project follows a modular structure optimized for local development and Databricks deployment:

```
nfl_data_engineering/
├── .vscode/
│   └── mcp.json                    # Model Context Protocol configuration
├── notebooks/                      # Databricks notebooks (medallion architecture)
│   ├── bronze_ingestion.py         # Raw data ingestion from nfl-data-py
│   ├── silver_transformation.py    # Data cleaning and standardization
│   └── gold_aggregation.py         # Business metrics and aggregations
├── src/                            # Shared Python modules
│   ├── __init__.py
│   ├── config.py                   # Configuration management (S3 paths, settings)
│   └── utils.py                    # Utility functions (Spark, validation, S3)
├── tests/                          # Unit and integration tests  
│   ├── __init__.py
│   └── test_utils.py               # Tests for utility functions
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore patterns
├── requirements.txt                # Python dependencies
├── setup.sh                       # Project setup script
├── README.md                       # This documentation
└── copilot-instructions.md         # AI assistant context and guidelines
```

**Key Design Principles:**
- **Local Development**: Python files can be developed and tested locally
- **Databricks Deployment**: Notebooks designed for Databricks execution  
- **Modular Design**: Shared utilities and configuration in `src/` directory
- **Testability**: Comprehensive test coverage for core functions
- **AI Integration**: MCP configuration for AI-assisted development

## How to Run the Project

### Prerequisites
**Required Services:**
- AWS Account with S3 access (✅ **Your buckets configured:** `nfl-raw`, `nfl-refined`, `nfl-trusted`)
- Python 3.8+ for local development and pipeline execution
- Optional: Databricks workspace for advanced features (✅ **Your workspace:** `dbc-c9b1be11-c0c8.cloud.databricks.com`)

**Required Credentials:**
- AWS credentials configured locally (via `aws configure` or environment variables)
- S3 read/write permissions for your three buckets in `us-east-2` region

**Current Development Mode:**
- **Primary Execution:** Local Python environment with direct S3 integration
- **Databricks Community:** Available for learning and notebook prototyping (no S3 access)
- **Upgrade Path:** Databricks Standard/Premium when ready for production scale

### Environment Setup

**1. Local Environment Setup:**
```bash
# Clone and navigate to project
git clone <repository-url>
cd nfl_data_engineering

# Run setup script
./setup.sh

# Configure environment variables
cp .env.example .env
# Edit .env with your AWS S3 bucket and Databricks details
```

**2. AWS Configuration:**
```bash
# Configure AWS credentials for your buckets
aws configure
# When prompted, use us-east-2 as your default region

# Verify access to your specific buckets
aws s3 ls s3://nfl-raw
aws s3 ls s3://nfl-refined  
aws s3 ls s3://nfl-trusted
```

**3. Environment Variables Setup:**
```bash
# Copy and configure environment file
cp .env.example .env

# Edit .env with your credentials - buckets are pre-configured:
# S3_BUCKET_BRONZE=nfl-raw
# S3_BUCKET_SILVER=nfl-refined
# S3_BUCKET_GOLD=nfl-trusted
# AWS_REGION=us-east-2
# DATABRICKS_WORKSPACE_URL=https://dbc-c9b1be11-c0c8.cloud.databricks.com
```

**4. Optional: Databricks Community Edition Setup:**
- Access your workspace: `dbc-c9b1be11-c0c8.cloud.databricks.com`
- Upload notebooks from `notebooks/` directory for learning
- Note: Community Edition cannot access your S3 buckets directly

**5. AI Development Environment (MCP Setup):**
```bash
# Install Node.js MCPs for AI-assisted development
npm install -g @modelcontextprotocol/server-filesystem
npm install -g @modelcontextprotocol/server-sequential-thinking
npm install -g puppeteer-mcp-server

# Verify MCP installation
npm list -g | grep -E "(modelcontextprotocol|puppeteer-mcp)"
```

**MCP Capabilities:**
- **File Management:** Complete project organization and navigation
- **Problem Solving:** Sequential thinking for complex pipeline challenges  
- **Web Automation:** NFL data validation and additional source collection

### Execution Steps

**Current Mode: Local Python + S3 Integration**

The pipeline runs locally with direct S3 integration. Future Databricks upgrade will enable cluster-based processing.

**Step 1: Bronze Layer Ingestion**
```bash
# Run locally with Python
cd /Users/georgesmith/repos/nfl_data_engineering
source venv/bin/activate
python notebooks/bronze_ingestion.py --season 2024 --week 1

# Output: Raw game data stored in s3://nfl-raw/games/season=2024/week=1/
```

**Step 2: Silver Layer Transformation**  
```bash
# Run data cleaning and validation
python notebooks/silver_transformation.py --season 2024 --week 1

# Input: s3://nfl-raw/games/season=2024/week=1/
# Output: Cleaned data in s3://nfl-refined/games/season=2024/week=1/
```

**Step 3: Gold Layer Aggregation**
```bash
# Run business aggregations
python notebooks/gold_aggregation.py --season 2024

# Input: All s3://nfl-refined/games/season=2024/ data
# Output: Team stats in s3://nfl-trusted/team_stats/season=2024/
```

**Alternative: Databricks Community Edition (Learning Mode)**
- Upload notebooks to `dbc-c9b1be11-c0c8.cloud.databricks.com`
- Modify to use sample data or DBFS storage
- Great for learning PySpark and Databricks concepts

### Local Testing
```bash
# Activate virtual environment
source venv/bin/activate

# Run unit tests
python -m pytest tests/ -v

# Test configuration
python -c "from src.config import get_s3_path; print(get_s3_path('bronze', 'games', 2024, 1))"
```

## Development Guidelines

### Local Development Workflow
**Environment Management:**
- Use virtual environment for dependency isolation
- Keep `requirements.txt` updated with exact versions
- Test imports locally before deploying to Databricks

**Code Organization:**
- `src/config.py`: Centralized configuration management
- `src/utils.py`: Reusable data processing functions
- `notebooks/`: Databricks notebooks for pipeline execution
- `tests/`: Unit tests for utility functions

**Best Practices:**
- Parameterize notebooks for flexible execution
- Use Delta Lake format for data persistence
- Implement data quality checks in Silver layer
- Follow naming conventions: `snake_case` for files, `UPPER_CASE` for constants

### Testing Strategy
**Unit Testing:**
```bash
# Run all tests
python -m pytest tests/ -v

# Test specific module
python -m pytest tests/test_utils.py -v

# Test with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

**Integration Testing:**
- Test S3 connectivity with sample data
- Validate Databricks cluster access
- Verify end-to-end pipeline with small dataset

### Data Quality Monitoring
**Bronze Layer Validation:**
- Check for successful data ingestion
- Validate expected columns and data types
- Monitor for missing weeks/games

**Silver Layer Validation:**
- Verify data cleaning transformations
- Check for null values in critical fields
- Validate referential integrity

**Gold Layer Validation:**
- Ensure aggregation accuracy
- Check for business rule compliance
- Validate against known metrics

### Performance Optimization
**Databricks Tuning:**
- Use appropriate cluster size for data volume
- Optimize Spark configurations for workload
- Leverage auto-scaling for variable loads

**Data Partitioning:**
- Partition by season and week for query performance
- Use Z-order optimization for frequently queried columns
- Monitor partition sizes to avoid small file problems

## Future Improvements

### Pipeline Automation
**Orchestration Options:**
- **Databricks Jobs**: Native scheduling with parameter support
- **Apache Airflow**: Complex dependency management and monitoring
- **AWS Step Functions**: Cloud-native orchestration with AWS services

**Scheduling Strategy:**
- Weekly execution during NFL season (Tuesday post-game)
- Backfill capabilities for historical data processing
- Parameterized execution for flexible date ranges

### Data Quality & Monitoring
**Advanced Quality Checks:**
- Great Expectations integration for comprehensive data validation
- Automated anomaly detection for statistical outliers
- Data lineage tracking with Delta Lake history

**Observability:**
- CloudWatch metrics for pipeline health monitoring
- Databricks dashboard for data quality KPIs
- Alerting for failed jobs or data quality issues

### Enhanced Data Sources
**Additional Integrations with MCP Support:**
- **Player injury reports** and status updates (via Puppeteer MCP web scraping)
- **Weather data** with detailed game conditions (automated collection)
- **Real-time betting odds** and market movements (web automation)
- **Social media sentiment** analysis from Twitter/Reddit (future enhancement)
- **Advanced tracking data** (Next Gen Stats) via web scraping validation

**MCP-Enabled Data Validation:**
- Cross-reference nfl-data-py results with ESPN.com, NFL.com
- Automated data quality checks against multiple sources
- Real-time monitoring for data discrepancies
- Sequential problem-solving for data pipeline issues

**External APIs:**
- ESPN API for additional game metadata
- Pro Football Reference for historical statistics
- Fantasy sports platforms for player valuations

### Analytics Capabilities
**Advanced Analytics:**
- Machine learning models for game outcome prediction
- Player performance forecasting
- Team strength ratings and ELO calculations
- Win probability models by game situation

**Visualization & BI:**
- Tableau/Power BI dashboards for business users
- Jupyter notebooks for data science exploration
- Real-time streaming analytics for live games