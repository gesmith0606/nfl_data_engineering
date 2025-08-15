#!/usr/bin/env python3
"""
Debug AWS Credentials
"""

import os
from dotenv import load_dotenv

def debug_credentials():
    """Debug AWS credentials from .env"""
    
    # Load environment variables
    load_dotenv()
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION')
    
    print("🔍 Credential Debug Info:")
    print(f"Access Key: {access_key}")
    print(f"Access Key Length: {len(access_key) if access_key else 'None'}")
    print(f"Secret Key Length: {len(secret_key) if secret_key else 'None'}")
    print(f"Region: {region}")
    
    # Check for common issues
    if secret_key:
        print(f"Secret Key starts with: {secret_key[:5]}...")
        print(f"Secret Key ends with: ...{secret_key[-5:]}")
        print(f"Contains spaces: {' ' in secret_key}")
        tab_char = '\t'
        newline_char = '\n'
        print(f"Contains tabs: {tab_char in secret_key}")
        print(f"Contains newlines: {newline_char in secret_key}")
    
if __name__ == "__main__":
    debug_credentials()
