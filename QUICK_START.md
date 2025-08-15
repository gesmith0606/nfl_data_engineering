# NFL Data Engineering - Quick Start Guide

## 🚀 Getting Started (5 minutes)

### Step 1: Clone and Setup
```bash
git clone https://github.com/gesmith0606/nfl_data_engineering.git
cd nfl_data_engineering
source venv/bin/activate  # Virtual environment is included
```

### Step 2: Configure AWS
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your AWS credentials:
# AWS_ACCESS_KEY_ID=your_key_here
# AWS_SECRET_ACCESS_KEY=your_secret_here
# S3_BUCKET_BRONZE=your-bronze-bucket
# S3_BUCKET_SILVER=your-silver-bucket  
# S3_BUCKET_GOLD=your-gold-bucket
```

### Step 3: Validate Setup
```bash
python scripts/validate_project.py
```

### Step 4: Ingest NFL Data
```bash
# Ingest game schedules for 2023 Week 1
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type schedules

# Ingest play-by-play data
python scripts/bronze_ingestion_simple.py --season 2023 --week 1 --data-type pbp
```

### Step 5: View Results
```bash
python scripts/list_bronze_contents.py
```

## 📊 What You'll Get

After running the ingestion scripts, you'll have:
- **Game Data**: 16 NFL games with scores, teams, dates
- **Play Data**: 2,800+ individual plays with yards, downs, players  
- **Storage**: Parquet files in S3 with proper partitioning
- **Quality**: Data validation and quality reports

## 🔧 Common Commands

```bash
# Test different seasons/weeks
python scripts/bronze_ingestion_simple.py --season 2024 --week 5 --data-type schedules

# Test AWS connectivity
python scripts/test_aws_connectivity.py

# Full project validation
python scripts/validate_project.py
```

## 🆘 Troubleshooting

**AWS Permission Issues?**
- Check your .env file has correct credentials
- Ensure IAM user has S3 permissions
- See: `docs/AWS_IAM_SETUP_INSTRUCTIONS.md`

**Import Errors?**
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

**Data Issues?**
- NFL data is seasonal - some weeks may not have data yet
- Try 2023 data which is complete
- Check validation output for data quality insights

## 🎯 Next Steps

1. **Explore the data** in your S3 buckets
2. **Try different seasons/weeks** (2020-2024)
3. **Check out the notebooks/** folder for Silver/Gold layer development
4. **Read the full README.md** for comprehensive documentation

---

**Ready to analyze some NFL data! 🏈**
