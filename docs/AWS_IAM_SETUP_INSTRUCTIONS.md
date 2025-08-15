# Manual AWS IAM Permissions Setup

## 🎯 Goal
Add S3 permissions to IAM user `gesmith0606` so our NFL data pipeline can access the S3 buckets.

## 📋 Step-by-Step Instructions

### Step 1: Open AWS IAM Console
1. Go to: https://console.aws.amazon.com/iam/
2. Sign in to your AWS account (Account ID: 512821312570)

### Step 2: Navigate to Your User
1. In the left sidebar, click **"Users"**
2. Find and click on **"gesmith0606"** in the user list

### Step 3: Add Permissions (Option A - Simple)
1. Click the **"Add permissions"** button
2. Select **"Attach policies directly"**
3. In the search box, type: **"AmazonS3FullAccess"**
4. Check the box next to **"AmazonS3FullAccess"**
5. Click **"Add permissions"**

### Step 3: Add Permissions (Option B - Custom Policy)
If you prefer more granular control:

1. Click the **"Add permissions"** button
2. Select **"Create inline policy"**
3. Click the **"JSON"** tab
4. Copy and paste the contents from `aws-iam-policy.json` in this project
5. Click **"Review policy"**
6. Name it: **"NFL-Data-S3-Access"**
7. Click **"Create policy"**

## ✅ Verification
After adding permissions, run this command to test:

```bash
python test_aws_connectivity.py
```

You should see:
- ✅ AWS Authentication Successful!
- ✅ nfl-raw: Accessible
- ✅ nfl-refined: Accessible  
- ✅ nfl-trusted: Accessible

## 🚀 Next Steps
Once S3 access is working, we can proceed to:
- Task 2.1: NFL Data Integration
- Start building the data pipeline!

---

**Estimated Time:** 2-3 minutes
**Difficulty:** Easy - just a few clicks in the AWS Console
