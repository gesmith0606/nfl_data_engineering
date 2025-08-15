#!/usr/bin/env python3
"""
Test AWS S3 Connectivity with Direct Credentials
"""

import boto3
from dotenv import load_dotenv
import os

def test_aws_direct():
    """Test AWS S3 connectivity with direct credential passing"""
    
    # Load environment variables
    load_dotenv()
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION')
    
    try:
        # Create STS client with explicit credentials
        sts_client = boto3.client(
            'sts',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        identity = sts_client.get_caller_identity()
        print(f"✅ AWS Authentication Successful!")
        print(f"Account ID: {identity['Account']}")
        print(f"User ARN: {identity['Arn']}")
        
        return True
        
    except Exception as e:
        print(f"❌ AWS Connection Failed: {str(e)}")
        print(f"Access Key: {access_key}")
        print(f"Region: {region}")
        return False

if __name__ == "__main__":
    test_aws_direct()
