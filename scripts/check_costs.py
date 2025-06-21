#!/usr/bin/env python3
"""
Quick AWS Cost Check Script
Displays current AWS spending for daily monitoring.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.append(project_root)

from src.cost_tracker import get_cost_tracker

async def check_costs():
    """Check and display current AWS costs."""
    try:
        tracker = get_cost_tracker()
        
        print("💰 Fetching current AWS costs...")
        
        daily = await tracker.get_real_daily_spend()
        weekly = await tracker.get_real_weekly_spend()
        monthly = await tracker.get_real_monthly_spend()
        
        print(f"💰 Daily:   ${daily:.6f}")
        print(f"💰 Weekly:  ${weekly:.6f}")
        print(f"💰 Monthly: ${monthly:.6f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking costs: {e}")
        return False

def main():
    """Main function."""
    success = asyncio.run(check_costs())
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 