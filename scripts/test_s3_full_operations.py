#!/usr/bin/env python3
"""
Comprehensive S3 Operations Test
Tests upload, download, list, and delete operations for the NFL data pipeline
"""

import boto3
from dotenv import load_dotenv
import os
import pandas as pd
import tempfile
from datetime import datetime

def test_s3_full_operations():
    """Test complete S3 operations needed for NFL pipeline"""
    
    # Load environment variables
    load_dotenv()
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION')
    
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    
    print("🧪 Comprehensive S3 Operations Test")
    print("=" * 50)
    
    # Test buckets
    buckets = [
        os.getenv('S3_BUCKET_BRONZE'),
        os.getenv('S3_BUCKET_SILVER'),
        os.getenv('S3_BUCKET_GOLD')
    ]
    
    for bucket in buckets:
        print(f"\n📦 Testing {bucket}:")
        
        # Test 1: Create test data (Parquet format like we'll use)
        test_data = pd.DataFrame({
            'game_id': ['2024_01_BUF_MIA', '2024_01_KC_CIN'],
            'season': [2024, 2024],
            'week': [1, 1],
            'home_team': ['MIA', 'CIN'],
            'away_team': ['BUF', 'KC'],
            'test_timestamp': [datetime.now(), datetime.now()]
        })
        
        # Test 2: Upload Parquet file
        try:
            with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp_file:
                test_data.to_parquet(tmp_file.name, index=False)
                
                test_key = f"test/season=2024/week=1/test_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
                
                s3_client.upload_file(tmp_file.name, bucket, test_key)
                print(f"   ✅ Upload successful: {test_key}")
                
                # Clean up temp file
                os.unlink(tmp_file.name)
                
        except Exception as e:
            print(f"   ❌ Upload failed: {str(e)}")
            continue
        
        # Test 3: List objects
        try:
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix="test/")
            object_count = response.get('KeyCount', 0)
            print(f"   ✅ List objects: {object_count} test objects found")
        except Exception as e:
            print(f"   ❌ List failed: {str(e)}")
            continue
        
        # Test 4: Download and verify
        try:
            with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp_file:
                s3_client.download_file(bucket, test_key, tmp_file.name)
                
                # Verify the data
                downloaded_data = pd.read_parquet(tmp_file.name)
                if len(downloaded_data) == 2 and 'game_id' in downloaded_data.columns:
                    print(f"   ✅ Download & verify successful: {len(downloaded_data)} rows")
                else:
                    print(f"   ⚠️  Download successful but data verification failed")
                
                # Clean up temp file
                os.unlink(tmp_file.name)
                
        except Exception as e:
            print(f"   ❌ Download failed: {str(e)}")
        
        # Test 5: Delete test file
        try:
            s3_client.delete_object(Bucket=bucket, Key=test_key)
            print(f"   ✅ Delete successful: Cleaned up test file")
        except Exception as e:
            print(f"   ❌ Delete failed: {str(e)}")
    
    print("\n" + "=" * 50)
    print("✅ S3 Operations Test Complete!")
    print("🚀 Ready for NFL Data Pipeline Implementation!")

if __name__ == "__main__":
    test_s3_full_operations()
