#!/usr/bin/env python3
"""
Test script to send a real cost alert email showing actual AWS spending.
This will trigger an email with your real AWS costs displayed.
"""

import sys
import asyncio
from decimal import Decimal

sys.path.append('src')

from src.config import get_settings
from src.cost_tracker import get_cost_tracker, CostAlertLevel

async def test_real_cost_alert_email():
    """Send a test cost alert email with real AWS spending data."""
    
    print("🧪 TESTING REAL COST ALERT EMAIL")
    print("=" * 50)
    
    try:
        tracker = get_cost_tracker()
        settings = get_settings()
        
        print(f"📧 Sending test alert to: {settings.cost_alert_email}")
        print("📊 Gathering real AWS spending data...")
        
        # Get real spending for display
        real_daily = await tracker.get_real_daily_spend()
        real_weekly = await tracker.get_real_weekly_spend()
        real_monthly = await tracker.get_real_monthly_spend()
        
        print(f"💰 Current real spending:")
        print(f"   Daily:   ${real_daily:.6f}")
        print(f"   Weekly:  ${real_weekly:.6f}")
        print(f"   Monthly: ${real_monthly:.6f}")
        
        # Send a test warning alert with real data
        await tracker._send_budget_alert(
            level=CostAlertLevel.WARNING,
            message="📧 Real Cost Alert Email Test - This shows your actual AWS spending!",
            current_spend=real_daily,  # Use real daily spending
            limit=tracker.daily_limit,
            additional_cost=Decimal('0.001')  # Small test cost
        )
        
        print("✅ Real cost alert email sent successfully!")
        print(f"📬 Check your email at: {settings.cost_alert_email}")
        print("📊 The email will show your actual AWS spending amounts")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to send real cost alert: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_real_cost_alert_email()) 