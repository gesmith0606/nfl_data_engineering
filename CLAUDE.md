# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment (required for all operations)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt

# Setup project (first time only)
./setup.sh
```

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test types
python tests/test_utils.py
python scripts/test_aws_connectivity.py
python scripts/test_nfl_data.py
python scripts/validate_project.py

# Test individual components
python src/nfl_data_integration.py
```

### Data Pipeline Operations
```bash
# Bronze layer ingestion
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type schedules
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type pbp

# Data exploration
python scripts/list_bronze_contents.py
python scripts/explore_bronze_data.py
```

### Code Quality
```bash
# Code formatting (available via dependencies)
python -m black src/ tests/ scripts/
python -m isort src/ tests/ scripts/

# Linting
python -m flake8 src/ tests/ scripts/
```

## Architecture Overview

This is an NFL data engineering pipeline implementing the **Medallion Architecture** pattern with local development and AWS S3 cloud storage.

### Key Architectural Patterns
- **Medallion Architecture**: Bronze (raw) → Silver (cleaned) → Gold (analytics-ready) data layers
- **Local Development**: Primary development environment with Python virtual environment
- **Cloud Storage**: AWS S3 buckets for data persistence across layers
- **Modular Design**: Shared utilities in `src/` with pipeline-specific scripts

### Data Flow
```
NFL API (nfl-data-py) → Bronze Layer (s3://nfl-raw/) → Silver Layer (s3://nfl-refined/) → Gold Layer (s3://nfl-trusted/)
```

### S3 Storage Structure
```
{bucket}/
├── games/season=YYYY/week=WW/schedules_YYYYMMDD_HHMMSS.parquet
├── plays/season=YYYY/week=WW/pbp_YYYYMMDD_HHMMSS.parquet
└── teams/season=YYYY/teams_YYYYMMDD_HHMMSS.parquet
```

## Key Components

### Core Modules (`src/`)
- **`config.py`**: Configuration management, S3 paths, and data quality thresholds
- **`nfl_data_integration.py`**: NFL data fetching with `NFLDataFetcher` class and validation
- **`utils.py`**: Shared utility functions across the pipeline

### Pipeline Scripts (`scripts/`)
- **`bronze_ingestion_simple.py`**: CLI tool for Bronze layer data ingestion with S3 upload
- **`list_bronze_contents.py`**: S3 Bronze layer content exploration
- **`explore_bronze_data.py`**: Interactive Bronze data analysis
- **`validate_project.py`**: Complete project validation including AWS and NFL API connectivity

### Development Notebooks (`notebooks/`)
- **`bronze_ingestion.py`**: Interactive Bronze layer development (legacy)
- **`silver_transformation.py`**: Silver layer development (in progress)
- **`gold_aggregation.py`**: Gold layer development (planned)

## Configuration

### AWS Configuration
- **Region**: us-east-2 (Ohio)
- **Buckets**: 
  - Bronze: `nfl-raw`
  - Silver: `nfl-refined`  
  - Gold: `nfl-trusted`
- **Credentials**: Configured via AWS CLI (`aws configure`) or `.env` file

### Environment Variables (`.env`)
```bash
# AWS Configuration
AWS_REGION=us-east-2
S3_BUCKET_BRONZE=nfl-raw
S3_BUCKET_SILVER=nfl-refined
S3_BUCKET_GOLD=nfl-trusted

# NFL Data Settings
DEFAULT_SEASON=2024
DEFAULT_WEEK=1
```

## NFL Data Context

### Current Bronze Layer Data (Complete)
- **16 NFL games** from 2023 Week 1 (complete metadata)
- **2,816 plays** with full play-by-play details
- **Team reference data** for all participating teams
- **Total: 0.21 MB** in S3 with proper partitioning

### Data Types Available
1. **Game Schedules** (`schedules`): Game metadata, scores, dates, teams
2. **Play-by-Play** (`pbp`): Detailed play data with downs, yards, players
3. **Team Stats** (`teams`): Team information and statistics

### NFL Business Rules for Validation
- Games per week: Typically 16 games per regular season week
- Season structure: Weeks 1-18 regular season, then playoffs
- Team validation: 32 NFL teams with consistent abbreviations
- Play validation: Down (1-4), distance (1-99), yard line (0-100)
- Score logic: Points scored must align with play outcomes

## Development Patterns

### Error Handling
Always include robust error handling for:
- NFL API calls (network timeouts, rate limits)
- S3 operations (credentials, bucket access, upload failures)
- Data validation (missing columns, invalid values)

### Data Processing
- **Primary Format**: Pandas DataFrames for all data manipulation
- **Storage Format**: Parquet files for efficient storage and querying
- **Partitioning**: Always partition by `season=YYYY/week=WW` for performance
- **Validation**: Validate data at each layer boundary using `NFLDataFetcher.validate_data()`

### Code Style
- Use descriptive function names with NFL context (e.g., `fetch_game_data`, `validate_play_data`)
- Include type hints for function parameters and return values
- Document functions with docstrings including purpose, parameters, and return values
- Follow existing patterns in `src/nfl_data_integration.py` for consistency

## Current Development Status

### Completed ✅
- Bronze Layer: Fully operational with NFL data ingestion
- AWS S3 Integration: Complete with proper partitioning and error handling
- Data Validation: Comprehensive validation framework implemented
- CLI Interface: Command-line tools for data ingestion and exploration

### In Progress 🚧
- Silver Layer: Data cleaning and transformation logic (next priority)
- Data Quality Pipeline: Advanced validation and business rule checking

### Planned ⏳
- Gold Layer: Business analytics and aggregated metrics
- Advanced NFL Analytics: EPA, win probability, efficiency metrics

## Agent Integration Framework

This project uses specialized Claude Code agents to accelerate development and maintain high code quality across the NFL data pipeline.

### Available Agents

#### Core Development Agents
- **🏗️ system-architect**: Design system architecture, define component structure, create technical specifications
- **💻 code-implementation-specialist**: Implement new features, write functions, create classes following project patterns
- **🔍 code-reviewer**: Comprehensive code review for quality, security, and best practices (use after all implementations)
- **🧪 test-engineer**: Create comprehensive test suites, improve test coverage, design validation frameworks

#### Project Management & Documentation
- **📋 project-orchestrator**: Manage complex, multi-step projects requiring coordination between multiple tasks
- **📚 docs-specialist**: Create and maintain all project documentation, README files, API docs
- **⚙️ devops-engineer**: CI/CD pipelines, containerization, deployment automation, infrastructure configuration

### Development Workflow with Agents

#### Phase 1: Architecture & Planning
```bash
# For new features or major changes
1. project-orchestrator: Break down complex requirements into manageable tasks
2. system-architect: Design component structure, data flow, and technical specifications
```

#### Phase 2: Implementation
```bash
# Core development cycle
3. code-implementation-specialist: Write the actual code implementation
4. test-engineer: Create comprehensive test coverage for new functionality
5. code-reviewer: Review all code for quality, security, and best practices
```

#### Phase 3: Documentation & Deployment
```bash
# Finalization and deployment
6. docs-specialist: Update documentation to reflect changes
7. devops-engineer: Handle deployment, CI/CD, and infrastructure needs
```

### Agent Usage Guidelines

#### When to Use Each Agent

**system-architect**: 
- Designing Silver/Gold layer architecture
- Planning database schemas and API contracts
- System integration planning
- Technology stack decisions

**code-implementation-specialist**:
- Silver layer transformation logic
- Gold layer analytics and aggregations
- NFL-specific business rule implementations
- Data validation functions

**code-reviewer** (MANDATORY):
- Review ALL production code before commits
- Security and performance analysis
- Code quality standards enforcement
- Architecture compliance validation

**test-engineer**:
- Data pipeline validation tests
- NFL business rule testing
- Integration tests for S3 operations
- Performance and load testing

**project-orchestrator**:
- Multi-layer pipeline development
- Complex feature implementations (e.g., advanced NFL analytics)
- Coordinating agent workflows
- Managing dependencies between components

**docs-specialist**:
- Updating CLAUDE.md with new patterns
- API documentation for new functions
- User guides for new CLI tools
- Architecture documentation updates

**devops-engineer**:
- GitHub Actions workflow setup
- Docker containerization
- AWS infrastructure automation
- Deployment pipeline configuration

### Handoff Procedures

#### Code Implementation → Review → Testing Flow
1. **code-implementation-specialist** completes feature implementation
2. **code-reviewer** performs comprehensive code review 
3. **test-engineer** creates/updates test coverage
4. **docs-specialist** updates relevant documentation

#### Multi-Agent Coordination Patterns
- Use **project-orchestrator** for features requiring 3+ agents
- Always end development cycles with **code-reviewer** validation
- **docs-specialist** should be involved in any user-facing changes
- **devops-engineer** handles all AWS/infrastructure modifications

### Quality Gates
- **Code Review**: All implementations must pass code-reviewer validation
- **Testing**: Minimum 80% test coverage for new features  
- **Documentation**: All public interfaces must have updated documentation
- **NFL Validation**: All data transformations must pass NFL business rule checks

## Important Notes

- **Virtual Environment**: Always activate `venv` before running any Python commands
- **AWS Credentials**: Ensure AWS credentials are configured before S3 operations
- **Data Dependencies**: Bronze layer data must exist before Silver layer development
- **NFL Seasons**: Valid seasons range from 1999-2025 based on nfl-data-py coverage
- **Testing**: Run validation scripts after any significant changes to ensure data integrity
- **Agent Workflow**: Follow the agent integration framework for all development tasks