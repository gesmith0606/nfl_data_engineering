#!/usr/bin/env python3
"""
List Bronze Layer Contents
Show what data has been ingested into the Bronze layer
"""

import boto3
from dotenv import load_dotenv
import os
from datetime import datetime

def list_bronze_contents():
    """List contents of the Bronze layer S3 bucket"""
    
    # Load environment variables
    load_dotenv()
    
    # Get AWS credentials
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION')
    bronze_bucket = os.getenv('S3_BUCKET_BRONZE')
    
    # Create S3 client
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    
    print(f"📦 Bronze Layer Contents (s3://{bronze_bucket})")
    print("=" * 70)
    
    try:
        # List all objects in the bronze bucket
        response = s3_client.list_objects_v2(Bucket=bronze_bucket)
        
        if 'Contents' not in response:
            print("🔍 No files found in Bronze layer")
            return
        
        # Group by data type
        files_by_type = {}
        total_size = 0
        
        for obj in response['Contents']:
            key = obj['Key']
            size = obj['Size']
            modified = obj['LastModified']
            
            # Extract data type from path
            data_type = key.split('/')[0]
            if data_type not in files_by_type:
                files_by_type[data_type] = []
            
            files_by_type[data_type].append({
                'key': key,
                'size': size,
                'modified': modified,
                'size_mb': round(size / (1024 * 1024), 2)
            })
            
            total_size += size
        
        # Display by data type
        for data_type, files in files_by_type.items():
            print(f"\n📁 {data_type.upper()} Data:")
            for file in sorted(files, key=lambda x: x['modified'], reverse=True):
                print(f"   📄 {file['key']}")
                print(f"      Size: {file['size_mb']} MB | Modified: {file['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\n📊 Summary:")
        print(f"   Total Files: {len(response['Contents'])}")
        print(f"   Total Size: {round(total_size / (1024 * 1024), 2)} MB")
        print(f"   Data Types: {', '.join(files_by_type.keys())}")
        
    except Exception as e:
        print(f"❌ Error listing Bronze contents: {str(e)}")

if __name__ == "__main__":
    list_bronze_contents()
