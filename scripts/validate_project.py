#!/usr/bin/env python3
"""
NFL Data Engineering Project Validation
Comprehensive validation of the entire project setup and functionality
"""

import sys
import os
from datetime import datetime

def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_success(message):
    """Print success message"""
    print(f"✅ {message}")

def print_error(message):
    """Print error message"""
    print(f"❌ {message}")

def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")

def validate_project_structure():
    """Validate project directory structure"""
    print_header("PROJECT STRUCTURE VALIDATION")
    
    required_dirs = [
        'src',
        'notebooks', 
        'tests',
        'scripts',
        'docs',
        'venv'
    ]
    
    required_files = [
        'README.md',
        'requirements.txt',
        '.env',
        '.env.example',
        'development_tasks.md',
        'src/__init__.py',
        'src/config.py',
        'src/utils.py',
        'src/nfl_data_integration.py',
        'scripts/bronze_ingestion_simple.py',
        'scripts/list_bronze_contents.py'
    ]
    
    # Check directories
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print_success(f"Directory exists: {dir_name}/")
        else:
            print_error(f"Missing directory: {dir_name}/")
    
    # Check files
    for file_name in required_files:
        if os.path.exists(file_name):
            print_success(f"File exists: {file_name}")
        else:
            print_error(f"Missing file: {file_name}")

def validate_python_environment():
    """Validate Python environment and dependencies"""
    print_header("PYTHON ENVIRONMENT VALIDATION")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major == 3 and python_version.minor >= 9:
        print_success(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    else:
        print_error(f"Python version {python_version.major}.{python_version.minor} - need 3.9+")
    
    # Check key imports
    key_imports = [
        ('pandas', 'Data processing'),
        ('boto3', 'AWS SDK'),
        ('nfl_data_py', 'NFL data API'),
        ('dotenv', 'Environment variables'),
        ('pytest', 'Testing framework')
    ]
    
    for module_name, description in key_imports:
        try:
            __import__(module_name)
            print_success(f"{module_name} - {description}")
        except ImportError:
            print_error(f"Missing: {module_name} - {description}")

def validate_environment_config():
    """Validate environment configuration"""
    print_header("ENVIRONMENT CONFIGURATION VALIDATION")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        required_vars = [
            'AWS_REGION',
            'AWS_ACCOUNT_ID', 
            'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY',
            'S3_BUCKET_BRONZE',
            'S3_BUCKET_SILVER',
            'S3_BUCKET_GOLD'
        ]
        
        for var in required_vars:
            value = os.getenv(var)
            if value and value != f"your_{var.lower()}_here":
                print_success(f"{var}: {'*' * min(len(value), 20)}")
            else:
                print_error(f"Missing or default: {var}")
                
    except Exception as e:
        print_error(f"Environment validation failed: {str(e)}")

def validate_aws_connectivity():
    """Validate AWS S3 connectivity"""
    print_header("AWS S3 CONNECTIVITY VALIDATION")
    
    try:
        import boto3
        from dotenv import load_dotenv
        load_dotenv()
        
        # Test STS connection
        sts_client = boto3.client('sts')
        identity = sts_client.get_caller_identity()
        print_success(f"AWS Authentication successful")
        print_info(f"Account: {identity['Account']}")
        print_info(f"User: {identity['Arn'].split('/')[-1]}")
        
        # Test S3 buckets
        s3_client = boto3.client('s3')
        buckets = [
            os.getenv('S3_BUCKET_BRONZE'),
            os.getenv('S3_BUCKET_SILVER'),
            os.getenv('S3_BUCKET_GOLD')
        ]
        
        for bucket in buckets:
            try:
                s3_client.head_bucket(Bucket=bucket)
                print_success(f"S3 bucket accessible: {bucket}")
            except Exception as e:
                print_error(f"S3 bucket issue: {bucket} - {str(e)}")
        
    except Exception as e:
        print_error(f"AWS connectivity validation failed: {str(e)}")

def validate_nfl_data_integration():
    """Validate NFL data integration"""
    print_header("NFL DATA INTEGRATION VALIDATION")
    
    try:
        sys.path.append('src')
        from nfl_data_integration import NFLDataFetcher
        
        fetcher = NFLDataFetcher()
        
        # Test schedule fetch (small sample)
        schedules = fetcher.fetch_game_schedules([2023], week=1)
        print_success(f"NFL schedules fetched: {len(schedules)} games")
        
        # Validate data
        validation = fetcher.validate_data(schedules, 'schedules')
        if validation['is_valid']:
            print_success(f"Data validation passed")
        else:
            print_error(f"Data validation failed: {validation['issues']}")
            
    except Exception as e:
        print_error(f"NFL data integration validation failed: {str(e)}")

def validate_bronze_layer():
    """Validate Bronze layer functionality"""
    print_header("BRONZE LAYER VALIDATION")
    
    try:
        # Check if data exists in Bronze layer
        from dotenv import load_dotenv
        import boto3
        
        load_dotenv()
        
        s3_client = boto3.client('s3')
        bronze_bucket = os.getenv('S3_BUCKET_BRONZE')
        
        response = s3_client.list_objects_v2(Bucket=bronze_bucket)
        
        if 'Contents' in response:
            file_count = len(response['Contents'])
            total_size = sum(obj['Size'] for obj in response['Contents'])
            print_success(f"Bronze layer has {file_count} files ({total_size/1024/1024:.2f} MB)")
            
            # Show data types
            data_types = set(obj['Key'].split('/')[0] for obj in response['Contents'])
            print_info(f"Data types: {', '.join(data_types)}")
        else:
            print_info("Bronze layer is empty (ready for data)")
            
    except Exception as e:
        print_error(f"Bronze layer validation failed: {str(e)}")

def generate_validation_report():
    """Generate comprehensive validation report"""
    print_header("NFL DATA ENGINEERING PROJECT VALIDATION")
    print_info(f"Validation Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run all validations
    validate_project_structure()
    validate_python_environment()
    validate_environment_config()
    validate_aws_connectivity()
    validate_nfl_data_integration()
    validate_bronze_layer()
    
    print_header("VALIDATION COMPLETE")
    print_success("Project validation finished!")
    print_info("Check output above for any issues that need attention")

if __name__ == "__main__":
    generate_validation_report()
