#!/usr/bin/env python3
"""
Test S3 Permissions - Check what we can access
"""

import boto3
from dotenv import load_dotenv
import os

def test_s3_permissions():
    """Test what S3 operations we can perform"""
    
    # Load environment variables
    load_dotenv()
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION')
    
    try:
        # Create S3 client with explicit credentials
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        print("🔍 Testing S3 Permissions:")
        
        # Test 1: List all buckets
        try:
            response = s3_client.list_buckets()
            print(f"✅ Can list buckets: {len(response['Buckets'])} buckets found")
            for bucket in response['Buckets']:
                print(f"   - {bucket['Name']}")
        except Exception as e:
            print(f"❌ Cannot list buckets: {str(e)}")
        
        # Test 2: Try to create a test bucket (this should fail, but shows permissions)
        test_bucket = "nfl-test-permissions-12345"
        try:
            s3_client.create_bucket(
                Bucket=test_bucket,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
            print(f"✅ Can create buckets (cleaning up...)")
            s3_client.delete_bucket(Bucket=test_bucket)
        except Exception as e:
            print(f"❌ Cannot create buckets: {str(e)}")
        
        # Test 3: Check specific bucket access with different operations
        buckets_to_test = ['nfl-raw', 'nfl-refined', 'nfl-trusted']
        
        for bucket in buckets_to_test:
            print(f"\n📦 Testing {bucket}:")
            
            # Try to list objects
            try:
                response = s3_client.list_objects_v2(Bucket=bucket, MaxKeys=1)
                print(f"   ✅ Can list objects")
            except Exception as e:
                print(f"   ❌ Cannot list objects: {str(e)}")
            
            # Try to get bucket location
            try:
                response = s3_client.get_bucket_location(Bucket=bucket)
                print(f"   ✅ Can get bucket location: {response.get('LocationConstraint', 'us-east-1')}")
            except Exception as e:
                print(f"   ❌ Cannot get bucket location: {str(e)}")
        
    except Exception as e:
        print(f"❌ S3 Client Creation Failed: {str(e)}")
        return False

if __name__ == "__main__":
    test_s3_permissions()
