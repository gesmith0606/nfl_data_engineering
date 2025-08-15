# AWS Console Automation Plan

## Option 1: Puppeteer MCP (Web Automation)
- Navigate to AWS IAM Console
- Log in to your AWS account
- Go to Users → gesmith0606
- Add inline policy with S3 permissions
- Apply the policy from aws-iam-policy.json

## Option 2: Manual Steps (Recommended)
1. Go to https://console.aws.amazon.com/iam/
2. Navigate to Users → gesmith0606
3. Click "Add permissions"
4. Choose "Attach policies directly"
5. Either:
   - Create inline policy using aws-iam-policy.json
   - Or attach "AmazonS3FullAccess" managed policy

## Option 3: AWS CLI (if you have admin access)
```bash
aws iam attach-user-policy --user-name gesmith0606 --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

Would you like me to try the Puppeteer automation approach?
