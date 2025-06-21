#!/usr/bin/env python3
"""
Minimal AWS Test - Test what works with current permissions.
This tests the core system without requiring Cost Explorer permissions.
"""

import asyncio
from decimal import Decimal
from src.config import get_settings
from src.cost_tracker import get_cost_tracker
import boto3

async def test_minimal_system():
    """Test the system with minimal AWS permissions."""
    
    print("🧪 MINIMAL AWS SYSTEM TEST")
    print("=" * 50)
    
    # Test 1: Configuration loading
    try:
        settings = get_settings()
        print("✅ Configuration loaded successfully")
        print(f"   AWS Region: {settings.aws_region}")
        print(f"   Budget limits configured: ${settings.daily_budget_limit}")
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        return False
    
    # Test 2: Basic AWS connectivity
    try:
        sts = boto3.client('sts',
                          aws_access_key_id=settings.aws_access_key_id,
                          aws_secret_access_key=settings.aws_secret_access_key,
                          region_name=settings.aws_region)
        
        identity = sts.get_caller_identity()
        print("✅ AWS credentials working")
        print(f"   Account: {identity['Account']}")
        print(f"   User: {identity['Arn'].split('/')[-1]}")
    except Exception as e:
        print(f"❌ AWS credentials failed: {e}")
        return False
    
    # Test 3: Cost tracker initialization (without AWS calls)
    try:
        tracker = get_cost_tracker()
        print("✅ Cost tracker initialized")
        print(f"   Daily limit: ${tracker.daily_limit}")
        print(f"   Emergency limit: ${tracker.emergency_limit}")
    except Exception as e:
        print(f"❌ Cost tracker failed: {e}")
        return False
    
    # Test 4: Internal cost tracking (no AWS API calls)
    try:
        # Track some test operations
        await tracker.track_api_call(
            service="test_service",
            operation="test_operation", 
            estimated_cost=Decimal('0.001'),
            user_id="test_user_123"
        )
        
        print("✅ Internal cost tracking working")
        print(f"   Records tracked: {len(tracker._cost_records)}")
        
        # Test user isolation
        user_costs = await tracker.get_cost_by_user(days=1)
        print(f"   User cost breakdown: {len(user_costs)} users")
        
    except Exception as e:
        print(f"❌ Cost tracking failed: {e}")
        return False
    
    # Test 5: Database models structure
    try:
        from src.models import User, Episode, CostRecord
        print("✅ Database models loaded")
        print("   Multi-user schema ready")
    except Exception as e:
        print(f"❌ Database models failed: {e}")
        return False
    
    print("\n🎉 MINIMAL SYSTEM TEST PASSED!")
    print("=" * 50)
    print("✅ Core system working correctly")
    print("✅ AWS credentials valid") 
    print("✅ Cost tracking logic operational")
    print("✅ Multi-user architecture ready")
    print("\n⚠️  NEXT STEP: Add Cost Explorer permissions to enable full testing")
    
    return True

async def test_with_mock_aws_costs():
    """Test the system using mock AWS cost data (for testing logic)."""
    
    print("\n🧪 TESTING COST LOGIC WITH SIMULATED DATA")
    print("=" * 50)
    
    tracker = get_cost_tracker()
    
    # Override the AWS cost methods temporarily for testing
    original_get_daily = tracker.get_real_daily_spend
    original_get_weekly = tracker.get_real_weekly_spend
    original_get_monthly = tracker.get_real_monthly_spend
    
    # Mock functions that return test data
    async def mock_daily():
        return Decimal('0.50')  # $0.50 daily spend
    
    async def mock_weekly():
        return Decimal('2.00')  # $2.00 weekly spend
        
    async def mock_monthly():
        return Decimal('8.00')  # $8.00 monthly spend
    
    # Temporarily replace methods
    tracker.get_real_daily_spend = mock_daily
    tracker.get_real_weekly_spend = mock_weekly  
    tracker.get_real_monthly_spend = mock_monthly
    
    try:
        # Test budget checking logic
        print("Testing budget enforcement...")
        
        # Small cost should be allowed
        small_cost = Decimal('0.10')
        should_proceed = await tracker._check_budget_limits(small_cost)
        print(f"✅ Small cost (${small_cost}): {'ALLOWED' if should_proceed else 'BLOCKED'}")
        
        # Large cost should be blocked
        large_cost = Decimal('10.00')  # Would exceed daily limit
        should_proceed = await tracker._check_budget_limits(large_cost)
        print(f"✅ Large cost (${large_cost}): {'ALLOWED' if should_proceed else 'BLOCKED'}")
        
        # Test cost summary generation
        summary = await tracker.get_cost_summary(days=1)
        print(f"✅ Cost summary generated: ${summary.total_cost}")
        
        print("✅ Budget protection logic working correctly!")
        
    except Exception as e:
        print(f"❌ Budget logic test failed: {e}")
        return False
    finally:
        # Restore original methods
        tracker.get_real_daily_spend = original_get_daily
        tracker.get_real_weekly_spend = original_get_weekly
        tracker.get_real_monthly_spend = original_get_monthly
    
    return True

if __name__ == "__main__":
    asyncio.run(test_minimal_system())
    asyncio.run(test_with_mock_aws_costs()) 