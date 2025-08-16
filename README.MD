# NFL Data Engineering Pipeline 🏈

A comprehensive data engineering solution for NFL analytics using AWS S3, nfl-data-py, and the Medallion Architecture pattern.

**📊 Current Status: Bronze Layer Complete, Ready for Silver Layer Development**

## 🎯 Project Overview

This project implements a complete NFL data pipeline that:
- **Ingests** raw NFL data from nfl-data-py API ✅ **COMPLETE**
- **Transforms** data through Bronze → Silver → Gold layers ⏳ **IN PROGRESS**  
- **Stores** data in AWS S3 with proper partitioning ✅ **COMPLETE**
- **Enables** advanced NFL analytics and insights 🔄 **PLANNED**

## 🏆 Current Achievements

### ✅ **Bronze Layer Operational** 
- **16 NFL games** + **2,816 plays** successfully ingested (2023 Week 1)
- **0.21 MB** of structured data stored in S3 with proper partitioning
- **Command-line interface** for data ingestion
- **Full validation suite** ensuring data quality

### 🛠️ **Infrastructure Ready**
- **AWS S3 Integration**: 3 buckets configured (raw, refined, trusted)
- **Python Environment**: Complete with nfl-data-py, boto3, pandas
- **Testing Suite**: AWS connectivity, NFL API, data validation tests
- **Documentation**: Comprehensive setup guides and API documentation

## 🎯 **Next Session Goals**

### 🥈 **Silver Layer Development** (Recommended)
Transform Bronze data into clean, validated datasets:
- Data quality pipeline implementation
- NFL business rule validations  
- Standardization and enrichment
- S3 Silver layer storage (`s3://nfl-refined/`)

### 📈 **Alternative: Bronze Layer Expansion**
Add more data variety for richer Silver layer development:
- Additional weeks and seasons
- Player statistics integration
- Team performance data
- Historical trend analysis

## 🏗️ Architecture

```
📊 Data Sources          🥉 Bronze Layer         🥈 Silver Layer         🥇 Gold Layer
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   nfl-data-py   │ ──→  │   Raw NFL Data  │ ──→  │  Cleaned Data   │ ──→  │  Aggregated     │
│   • Games       │      │   • Parquet     │      │   • Validated   │      │  Analytics      │
│   • Play-by-play│      │   • Partitioned │      │   • Enriched    │      │   • KPIs        │
│   • Team Stats  │      │   • Timestamped │      │   • Standardized│      │   • Reports     │
└─────────────────┘      └─────────────────┘      └─────────────────┘      └─────────────────┘
                                 │                          │                         │
                            s3://nfl-raw             s3://nfl-refined         s3://nfl-trusted
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- AWS Account with S3 buckets
- AWS CLI configured

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/gesmith0606/nfl_data_engineering.git
cd nfl_data_engineering

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. AWS Configuration
```bash
# Configure AWS credentials
aws configure

# Or set environment variables in .env file
cp .env.example .env
# Edit .env with your AWS credentials
```

### 3. Test Setup
```bash
# Test AWS connectivity
python test_aws_connectivity.py

# Test NFL data integration
python test_nfl_data.py
```

### 4. Run Data Ingestion
```bash
# Ingest game schedules
python bronze_ingestion_simple.py --season 2023 --week 1 --data-type schedules

# Ingest play-by-play data
python bronze_ingestion_simple.py --season 2023 --week 1 --data-type pbp

# View ingested data
python list_bronze_contents.py
```

## 📁 Project Structure

```
nfl_data_engineering/
├── 📄 README.md                          # This file
├── 📄 requirements.txt                   # Python dependencies
├── 📄 .env                              # Environment variables
├── 📄 development_tasks.md              # Development roadmap
├── 
├── 📂 src/                              # Core source code
│   ├── 📄 config.py                     # Configuration settings
│   ├── 📄 utils.py                      # Utility functions  
│   └── 📄 nfl_data_integration.py       # NFL data fetching & validation
├── 
├── 📂 notebooks/                        # Data processing notebooks
│   ├── 📄 bronze_ingestion.py           # Raw data ingestion
│   ├── 📄 silver_transformation.py      # Data cleaning & validation
│   └── 📄 gold_aggregation.py           # Analytics & aggregation
├── 
├── 📂 tests/                           # Unit tests
│   └── 📄 test_utils.py                # Utility function tests
├── 
├── 📂 scripts/                         # Standalone scripts
│   ├── 📄 bronze_ingestion_simple.py   # CLI data ingestion
│   ├── 📄 list_bronze_contents.py      # S3 content viewer
│   └── 📄 test_*.py                    # Various test scripts
└── 
└── 📂 docs/                           # Documentation
    ├── 📄 AWS_IAM_SETUP_INSTRUCTIONS.md  # AWS configuration guide
    ├── 📄 BRONZE_LAYER_DATA_INVENTORY.md # Current data catalog
    ├── 📄 IMPLEMENTATION_SUMMARY.md      # Technical implementation details
    └── 📄 project_details.md             # Project specifications
```

## 🥉 Bronze Layer (Raw Data)

**Purpose:** Ingest raw NFL data with minimal processing  
**Storage:** `s3://nfl-raw/`  
**Format:** Parquet files with partitioning  
**Current Status:** ✅ **Active with 2023 Week 1 Data**

### 📊 Current Data Inventory:
| Data Type | Records | Size | Season | Week | Status |
|-----------|---------|------|--------|------|--------|
| **Games** | 16 games | 0.03 MB | 2023 | 1 | ✅ Complete |
| **Plays** | 2,816 plays | 0.18 MB | 2023 | 1 | ✅ Complete |
| **Total** | - | **0.21 MB** | - | - | ✅ Ready for Silver |

*📋 [View detailed data inventory](docs/BRONZE_LAYER_DATA_INVENTORY.md)*

### Supported Data Types:
- **Game Schedules**: Season schedules with scores, dates, teams (50 columns)
- **Play-by-Play**: Detailed play data with yards, downs, players (32 columns)  
- **Team Stats**: Team information and statistics (available but not yet ingested)

### Partitioning Structure:
```
s3://nfl-raw/
├── games/season=2023/week=1/schedules_20240815_123456.parquet
├── plays/season=2023/week=1/pbp_20240815_123456.parquet
└── teams/season=2023/teams_20240815_123456.parquet
```

## 🥈 Silver Layer (Cleaned Data)

**Purpose:** Clean, validate, and enrich Bronze data
**Storage:** `s3://nfl-refined/`
**Status:** 🚧 In Development

### Planned Transformations:
- Data type validation and correction
- Missing value handling
- Player name standardization
- Team abbreviation consistency
- Date/time standardization

## 🥇 Gold Layer (Analytics Ready)

**Purpose:** Business-ready aggregated data
**Storage:** `s3://nfl-trusted/`  
**Status:** 📋 Planned

### Planned Aggregations:
- Team performance metrics
- Player statistics by season/week
- Game outcome predictions
- Historical trend analysis

## 🛠️ Key Components

### 1. NFL Data Integration (`src/nfl_data_integration.py`)
- Fetches data from nfl-data-py API
- Handles rate limits and errors
- Validates data quality
- Supports multiple data types

### 2. Bronze Layer Ingestion (`bronze_ingestion_simple.py`)
- Command-line interface for data ingestion
- Configurable season, week, and data type
- Automatic S3 upload with proper partitioning
- Built-in data validation

### 3. AWS S3 Integration
- Full CRUD operations tested
- Parquet format support
- Proper IAM permissions configured
- Cross-region connectivity (us-east-2)

## 📊 Current Status

### ✅ Completed (August 15, 2025)
- [x] **Task 1.1**: Local Environment Configuration
- [x] **Task 1.2**: AWS S3 Connectivity Testing  
- [x] **Task 2.1**: NFL Data Integration

### 📊 Bronze Layer Data Status:
| Metric | Value | Details |
|--------|-------|---------|
| **Total Files** | 2 | Games + Plays data |
| **Total Size** | 0.21 MB | Parquet compressed |
| **Game Records** | 16 games | 2023 Season Week 1 |
| **Play Records** | 2,816 plays | Detailed play-by-play |
| **Data Quality** | ✅ Validated | All required fields present |
| **Partitioning** | ✅ Active | `season=YYYY/week=WW` structure |

*📋 [Complete data inventory and schema details](docs/BRONZE_LAYER_DATA_INVENTORY.md)*

### 🚧 In Progress
- **Task 2.2**: S3 Upload Implementation Enhancement
- **Task 2.3**: Bronze Layer CLI Enhancement

### 📋 Planned
- Silver Layer Data Transformation
- Gold Layer Analytics Aggregation
- Databricks Integration
- Automated Pipeline Orchestration

## 🔧 Configuration

### Environment Variables (.env)
```bash
# AWS Configuration
AWS_REGION=us-east-2
AWS_ACCOUNT_ID=512821312570
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# S3 Buckets
S3_BUCKET_BRONZE=nfl-raw
S3_BUCKET_SILVER=nfl-refined  
S3_BUCKET_GOLD=nfl-trusted

# NFL Data Settings
DEFAULT_SEASON=2024
DEFAULT_WEEK=1
LOG_LEVEL=INFO
```

## 🧪 Testing

```bash
# Test AWS connectivity
python test_aws_connectivity.py

# Test NFL data fetching
python test_nfl_data.py

# Test S3 full operations
python test_s3_full_operations.py

# Run unit tests
python -m pytest tests/
```

## 📈 Usage Examples

### Basic Data Ingestion
```bash
# Ingest current week games
python bronze_ingestion_simple.py --season 2024 --week 1 --data-type schedules

# Ingest historical play-by-play
python bronze_ingestion_simple.py --season 2023 --week 1 --data-type pbp
```

### Check Ingested Data
```bash
# View Bronze layer contents
python list_bronze_contents.py

# Test data quality
python src/nfl_data_integration.py
```

## 🚀 Future Enhancements

- **Real-time Data Ingestion**: Live game data streaming
- **Advanced Analytics**: Player performance models
- **Visualization Dashboard**: Interactive NFL analytics
- **API Layer**: REST API for data access
- **Data Lineage**: Track data flow and transformations
- **Cost Optimization**: S3 lifecycle policies and compression

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **nfl-data-py**: For providing excellent NFL data API
- **AWS**: For cloud infrastructure
- **Apache Parquet**: For efficient data storage
- **NFL**: For the amazing game that makes this data possible! 🏈

---

**Built with ❤️ for NFL Analytics**
