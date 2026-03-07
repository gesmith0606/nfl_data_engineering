# Technology Stack

**Analysis Date:** 2026-03-07

## Languages

**Primary:**
- Python 3.9.7 - All source code, scripts, and pipeline logic

**Secondary:**
- JavaScript (inline) - GitHub Actions workflow scripts (`actions/github-script@v7` in `.github/workflows/weekly-pipeline.yml`)

## Runtime

**Environment:**
- CPython 3.9.7 (local venv from Anaconda base)
- GitHub Actions uses Python 3.11 (set in `.github/workflows/weekly-pipeline.yml` `PYTHON_VERSION`)

**Package Manager:**
- pip (standard)
- Lockfile: `requirements.txt` (pinned versions, 91 packages)

**Virtual Environment:**
- venv at `./venv/` - activate with `source venv/bin/activate` before all operations

## Frameworks

**Core:**
- pandas 1.5.3 - Primary DataFrame processing throughout all src/ and scripts/
- numpy 1.26.4 - Numerical operations in projections, analytics, scoring
- pyarrow 21.0.0 - Parquet file read/write (storage format for all layers)
- boto3 1.40.11 - AWS S3 client for all data storage operations

**Testing:**
- pytest 8.4.1 - Test runner (`python -m pytest tests/ -v`)
- pytest-cov 6.2.1 - Coverage reporting
- moto 5.1.10 - AWS service mocking for S3 tests
- responses 0.25.8 - HTTP request mocking

**Build/Dev:**
- black 25.1.0 - Code formatting (`python -m black src/ tests/ scripts/`)
- flake8 7.3.0 - Linting (`python -m flake8 src/ tests/ scripts/`)
- isort 6.0.1 - Import sorting
- coverage 7.10.3 - Code coverage measurement

## Key Dependencies

**Critical:**
- nfl_data_py 0.3.3 - NFL statistical data source (schedules, PBP, weekly stats, snap counts, injuries, rosters, seasonal stats). Wraps the nflverse GitHub data. All Bronze layer ingestion flows through this.
- boto3 1.40.11 - AWS S3 read/write for all three medallion layers. Used in `src/utils.py`, all scripts.
- pandas 1.5.3 - Every module uses DataFrames for data processing. This is the core abstraction.
- pyarrow 21.0.0 - Parquet serialization format for all pipeline data storage.

**Infrastructure:**
- python-dotenv 1.1.1 - Loads `.env` file for AWS credentials and config (`scripts/bronze_ingestion_simple.py`, `scripts/check_pipeline_health.py`)
- requests 2.32.4 - HTTP client for Sleeper API calls (`scripts/refresh_adp.py`)
- scipy 1.13.1 - Statistical calculations (used in analytics)
- fastparquet 2024.11.0 - Alternative Parquet engine (available but pyarrow is primary)

**Optional / Dormant:**
- pyspark 4.0.0 - Spark session helpers in `src/utils.py` (guarded import, not actively used in pipeline)
- great_expectations 1.5.8 - Data quality framework (installed but not integrated into active pipeline)
- selenium 4.32.0 - Browser automation (installed, not actively used)
- beautifulsoup4 4.13.4 - HTML parsing (installed, not actively used)
- structlog 25.4.0 - Structured logging (installed, standard `logging` module used instead)
- pydantic 2.11.7 - Data validation (installed, not actively used in src/)

## Configuration

**Environment:**
- `.env` file at project root (never committed - in `.gitignore`)
- `.env.example` documents all expected variables
- Key env vars: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_BRONZE`, `S3_BUCKET_SILVER`, `S3_BUCKET_GOLD`
- Optional: `DATABRICKS_WORKSPACE_URL`, `DATABRICKS_CLUSTER_ID`, `DATABRICKS_TOKEN`
- Pipeline control: `PIPELINE_WEEK_OVERRIDE` (format `YYYY:WW`), `HEALTH_CHECK_MAX_AGE_DAYS`
- All config centralized in `src/config.py` with `os.getenv()` fallbacks

**Build:**
- No build step required - pure Python scripts
- `requirements.txt` - all dependencies pinned to exact versions
- Pre-commit hooks: credential scanning (blocks `AKIA*`, `github_pat_*`, private keys)

## Platform Requirements

**Development:**
- macOS or Linux (tested on Darwin 25.3.0)
- Python 3.9+ (3.9 compatibility maintained with `Optional[]` type hints, guarded PySpark import)
- AWS credentials configured (currently expired - local-first mode active)
- ~15 MB disk for local data (`data/bronze/`, `data/silver/`, `data/gold/`)

**Production (GitHub Actions):**
- ubuntu-latest runner
- Python 3.11
- AWS credentials via GitHub Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- S3 buckets: `nfl-raw`, `nfl-refined`, `nfl-trusted` in us-east-2

---

*Stack analysis: 2026-03-07*
