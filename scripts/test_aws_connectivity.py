#!/usr/bin/env python3
"""
Test AWS S3 Connectivity
Tests connection to S3 buckets using credentials from .env file
"""

import os
import boto3
from dotenv import load_dotenv

def test_aws_connectivity():
    """Test AWS S3 connectivity"""
    
    # Load environment variables
    load_dotenv()
    
    # Set AWS credentials as environment variables
    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv('AWS_ACCESS_KEY_ID')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv('AWS_SECRET_ACCESS_KEY')
    os.environ['AWS_DEFAULT_REGION'] = os.getenv('AWS_REGION')
    
    try:
        # Test STS (Security Token Service) - basic AWS connectivity
        sts_client = boto3.client('sts')
        identity = sts_client.get_caller_identity()
        print(f"✅ AWS Authentication Successful!")
        print(f"Account ID: {identity['Account']}")
        print(f"User ARN: {identity['Arn']}")
        
        # Test S3 connectivity
        s3_client = boto3.client('s3')
        
        # Test each bucket
        buckets = [
            os.getenv('S3_BUCKET_BRONZE'),
            os.getenv('S3_BUCKET_SILVER'),
            os.getenv('S3_BUCKET_GOLD')
        ]
        
        print(f"\n🪣 Testing S3 Bucket Access:")
        for bucket in buckets:
            try:
                response = s3_client.head_bucket(Bucket=bucket)
                print(f"✅ {bucket}: Accessible")
            except Exception as e:
                print(f"❌ {bucket}: {str(e)}")
        
        return True
        
    except Exception as e:
        print(f"❌ AWS Connection Failed: {str(e)}")
        return False

if __name__ == "__main__":
    test_aws_connectivity()
