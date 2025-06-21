# Multi-User Podcast Q&A System 🎧

A cost-optimized, multi-user web application that allows users to connect their Spotify accounts, download and transcribe full podcast episodes, and query their personal podcast content using AI.

## 🚨 STEP-BY-STEP DEVELOPMENT WITH REAL DATA ONLY 🚨

**MANDATORY RULE:** Each step must be completed and tested with REAL data before proceeding to the next step. NO MOCK DATA AT ANY POINT.

---

## 📋 STEP 1: Project Foundation & Cost Monitoring _(CURRENT STEP)_

### What Step 1 Accomplishes:

- ✅ Real AWS Cost Explorer API integration
- ✅ Multi-user cost tracking and attribution
- ✅ Budget protection and emergency stops
- ✅ Real email alerts via AWS SES
- ✅ Database models for user isolation
- ✅ Comprehensive test suite with actual AWS calls

### 🔧 Prerequisites

1. **AWS Account** with billing enabled
2. **AWS IAM User** with these permissions:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ce:GetCostAndUsage",
           "ce:GetDimensionValues",
           "ce:GetReservationCoverage",
           "ce:GetReservationPurchaseRecommendation",
           "ce:GetReservationUtilization"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": ["ses:SendEmail", "ses:SendRawEmail", "ses:GetSendQuota"],
         "Resource": "*"
       }
     ]
   }
   ```

3. **Python 3.9+** installed
4. **PostgreSQL** (for later steps)

### 🚀 Step 1 Setup Instructions

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Configure Environment

```bash
# Copy the example configuration
cp config.env.example config.env

# Edit config.env with your AWS credentials
nano config.env
```

**Required configuration in `config.env`:**

```bash
# AWS Configuration - REQUIRED FOR REAL COST TRACKING
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key_here
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# Cost Monitoring Configuration
DAILY_BUDGET_LIMIT=5.00
WEEKLY_BUDGET_LIMIT=25.00
MONTHLY_BUDGET_LIMIT=100.00
COST_ALERT_EMAIL=your-email@example.com

# ... (other settings)
```

#### 3. Run Step 1 Validation

```bash
python setup_step1.py
```

This script will:

- ✅ Validate your AWS credentials
- ✅ Test Cost Explorer API access
- ✅ Verify SES email configuration
- ✅ Run real cost tracking tests
- ✅ Validate database models
- ✅ Check budget limit logic

**Expected validation cost: < $0.10**

#### 4. Run Comprehensive Tests

```bash
# Run all Step 1 tests with real AWS integration
python -m pytest tests/test_real_cost_tracking.py -v

# Run specific critical tests
python -m pytest tests/test_real_cost_tracking.py::TestRealAWSCostTracking::test_real_aws_credentials_work -v
```

### 🎯 Step 1 Success Criteria

**ALL of these must pass before proceeding to Step 2:**

- [ ] **Real AWS Connection**: Cost Explorer API accessible
- [ ] **Real Cost Retrieval**: Can fetch actual daily/weekly/monthly spend
- [ ] **Budget Protection**: Operations blocked when limits exceeded
- [ ] **User Isolation**: Cost attribution works per user
- [ ] **Email Alerts**: SES can send real budget alerts
- [ ] **Database Models**: Multi-user schema validated
- [ ] **Test Suite**: All real AWS integration tests pass

### 💰 Cost Tracking Dashboard

Once Step 1 is complete, you can monitor costs in real-time:

```python
# Get current spending
from src.cost_tracker import get_cost_tracker

tracker = get_cost_tracker()
daily_spend = await tracker.get_real_daily_spend()
summary = await tracker.get_cost_summary(days=7)

print(f"Daily spend: ${daily_spend:.6f}")
print(f"Weekly total: ${summary.total_cost:.6f}")
```

### 🚨 Emergency Budget Protection

The system automatically:

- Blocks operations that would exceed budget limits
- Sends real email alerts via AWS SES
- Tracks variance between estimated and actual costs
- Provides per-user cost attribution

### 📊 Real AWS Integration Verified

Step 1 ensures:

- ✅ AWS Cost Explorer returns actual billing data
- ✅ SES sends real email notifications
- ✅ Budget limits enforced against real spending
- ✅ Multi-user cost isolation works correctly
- ✅ No mock data anywhere in the system

---

## 🔄 Next Steps (After Step 1 Completion)

### Step 2: Spotify Integration _(Coming Next)_

- OAuth 2.0 flow with your real Spotify account
- Fetch actual recent podcast episodes
- Store real listening history with user isolation
- Test with your actual Spotify data

### Step 3: Audio Discovery _(Future)_

- Find real RSS feeds for actual episodes
- Verify downloadable audio URLs
- Test with real podcast audio files

### Step 4: Transcription Pipeline _(Future)_

- Process real audio with Whisper on EC2
- Track actual transcription costs
- Store real transcripts in S3

### And so on...

---

## 🛑 CRITICAL RULES

1. **NO PROGRESSION WITHOUT VALIDATION**: Do not proceed to Step 2 until ALL Step 1 tests pass
2. **REAL DATA ONLY**: Never use mock data, dummy APIs, or simulated responses
3. **COST MONITORING**: Every AWS call tracked and monitored in real-time
4. **USER ISOLATION**: All data completely separated by user_id
5. **BUDGET PROTECTION**: Operations automatically blocked when limits exceeded

---

## 📞 Step 1 Support

### Common Issues:

**AWS Credentials Error:**

```
❌ AWS credentials not found or invalid
```

**Solution:** Verify `config.env` has correct AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

**Permission Denied:**

```
❌ AWS credentials lack required permissions for Cost Explorer
```

**Solution:** Add Cost Explorer permissions to your AWS IAM user

**SES Not Configured:**

```
❌ SES region not verified for sending emails
```

**Solution:** Verify your email address in AWS SES console

### Testing Individual Components:

```python
# Test cost tracking
from src.cost_tracker import get_cost_tracker
tracker = get_cost_tracker()
daily_spend = await tracker.get_real_daily_spend()

# Test budget protection
should_proceed = await tracker.track_api_call("test", "op", Decimal('0.001'))

# Test user isolation
user_costs = await tracker.get_cost_by_user(days=7)
```

---

## 🎯 Success Metrics for Step 1

- **Functional**: All AWS APIs accessible and working
- **Cost**: Validation completed for < $0.10 total
- **Performance**: API calls complete within 5 seconds
- **Quality**: Real cost data matches AWS Console within 1 cent
- **Isolation**: User cost attribution 100% accurate

**Once Step 1 passes all tests, you're ready for Step 2! 🚀**
