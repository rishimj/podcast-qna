#!/usr/bin/env python3
"""
Detailed Cost Explorer API verification test.
This test verifies that AWS Cost Explorer is returning real, accurate data.
"""

import sys
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import boto3

sys.path.append('src')

from src.config import get_settings
from src.cost_tracker import get_cost_tracker

class CostExplorerValidator:
    def __init__(self):
        self.settings = get_settings()
        self.cost_explorer = boto3.client(
            'ce',
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
            region_name=self.settings.aws_region
        )
        
    def print_header(self, title):
        print(f"\n{'='*60}")
        print(f"🔍 {title}")
        print(f"{'='*60}")
    
    def print_section(self, title):
        print(f"\n📊 {title}")
        print("-" * 40)
    
    async def test_1_basic_cost_explorer_api(self):
        """Test 1: Direct Cost Explorer API calls"""
        self.print_header("COST EXPLORER API VERIFICATION")
        
        try:
            # Test 1: Get last 7 days of costs
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
            
            print(f"📅 Testing period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
            
            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost', 'UnblendedCost', 'UsageQuantity']
            )
            
            print(f"✅ API call successful")
            print(f"📈 Results returned: {len(response['ResultsByTime'])} days")
            
            total_cost = Decimal('0')
            for i, result in enumerate(response['ResultsByTime']):
                date = result['TimePeriod']['Start']
                cost = Decimal(result['Total']['BlendedCost']['Amount'])
                total_cost += cost
                print(f"   Day {i+1} ({date}): ${cost:.6f}")
            
            print(f"💰 Total 7-day cost: ${total_cost:.6f}")
            
            return True, total_cost
            
        except Exception as e:
            print(f"❌ Cost Explorer API failed: {e}")
            return False, Decimal('0')
    
    async def test_2_service_breakdown(self):
        """Test 2: Get cost breakdown by AWS service"""
        self.print_section("SERVICE BREAKDOWN")
        
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=30)  # Last 30 days
            
            response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='MONTHLY',
                Metrics=['BlendedCost'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )
            
            print(f"📊 Monthly service breakdown:")
            
            services_with_cost = []
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = Decimal(group['Metrics']['BlendedCost']['Amount'])
                    if cost > 0:
                        services_with_cost.append((service, cost))
            
            # Sort by cost (highest first)
            services_with_cost.sort(key=lambda x: x[1], reverse=True)
            
            total_service_cost = sum(cost for _, cost in services_with_cost)
            
            if services_with_cost:
                print(f"💳 Found {len(services_with_cost)} services with costs:")
                for service, cost in services_with_cost:
                    percentage = (cost / total_service_cost * 100) if total_service_cost > 0 else 0
                    print(f"   • {service}: ${cost:.6f} ({percentage:.1f}%)")
                print(f"💰 Total monthly cost: ${total_service_cost:.6f}")
            else:
                print("📭 No services with costs found (unusual - might indicate an issue)")
            
            return len(services_with_cost), total_service_cost
            
        except Exception as e:
            print(f"❌ Service breakdown failed: {e}")
            return 0, Decimal('0')
    
    async def test_3_compare_time_periods(self):
        """Test 3: Compare different time periods"""
        self.print_section("TIME PERIOD COMPARISON")
        
        try:
            now = datetime.now(timezone.utc)
            
            # Today
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)
            
            # Yesterday
            yesterday_start = today_start - timedelta(days=1)
            yesterday_end = today_start
            
            # This month
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            periods = [
                ("Today", today_start, today_end),
                ("Yesterday", yesterday_start, yesterday_end),
                ("This Month", month_start, now)
            ]
            
            for period_name, start, end in periods:
                try:
                    response = self.cost_explorer.get_cost_and_usage(
                        TimePeriod={
                            'Start': start.strftime('%Y-%m-%d'),
                            'End': end.strftime('%Y-%m-%d')
                        },
                        Granularity='DAILY',
                        Metrics=['BlendedCost']
                    )
                    
                    total_cost = Decimal('0')
                    for result in response['ResultsByTime']:
                        cost = Decimal(result['Total']['BlendedCost']['Amount'])
                        total_cost += cost
                    
                    print(f"📅 {period_name}: ${total_cost:.6f}")
                    
                except Exception as e:
                    print(f"📅 {period_name}: Error - {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Time period comparison failed: {e}")
            return False
    
    async def test_4_validate_tracker_accuracy(self):
        """Test 4: Compare our tracker with direct API calls"""
        self.print_section("TRACKER ACCURACY VALIDATION")
        
        try:
            tracker = get_cost_tracker()
            
            # Get costs using our tracker
            tracker_daily = await tracker.get_real_daily_spend()
            tracker_weekly = await tracker.get_real_weekly_spend()
            tracker_monthly = await tracker.get_real_monthly_spend()
            tracker_services = await tracker.get_cost_by_service(days=7)
            
            print("🔧 OUR TRACKER RESULTS:")
            print(f"   Daily:   ${tracker_daily:.6f}")
            print(f"   Weekly:  ${tracker_weekly:.6f}")
            print(f"   Monthly: ${tracker_monthly:.6f}")
            print(f"   Services: {len(tracker_services)} services")
            
            # Get costs using direct API calls
            end_date = datetime.now(timezone.utc)
            
            # Direct daily call
            daily_response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': end_date.strftime('%Y-%m-%d'),
                    'End': (end_date + timedelta(days=1)).strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            
            direct_daily = sum(Decimal(r['Total']['BlendedCost']['Amount']) for r in daily_response['ResultsByTime'])
            
            # Direct weekly call
            weekly_start = end_date - timedelta(days=7)
            weekly_response = self.cost_explorer.get_cost_and_usage(
                TimePeriod={
                    'Start': weekly_start.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            
            direct_weekly = sum(Decimal(r['Total']['BlendedCost']['Amount']) for r in weekly_response['ResultsByTime'])
            
            print("\n🎯 DIRECT API RESULTS:")
            print(f"   Daily:   ${direct_daily:.6f}")
            print(f"   Weekly:  ${direct_weekly:.6f}")
            
            print("\n🔍 ACCURACY CHECK:")
            daily_match = abs(tracker_daily - direct_daily) < Decimal('0.000001')
            weekly_match = abs(tracker_weekly - direct_weekly) < Decimal('0.000001')
            
            print(f"   Daily match:  {'✅' if daily_match else '❌'} (diff: ${abs(tracker_daily - direct_daily):.6f})")
            print(f"   Weekly match: {'✅' if weekly_match else '❌'} (diff: ${abs(tracker_weekly - direct_weekly):.6f})")
            
            return daily_match and weekly_match
            
        except Exception as e:
            print(f"❌ Tracker accuracy validation failed: {e}")
            return False
    
    async def test_5_cost_data_freshness(self):
        """Test 5: Check how fresh the cost data is"""
        self.print_section("COST DATA FRESHNESS")
        
        try:
            print("⏰ Checking cost data freshness...")
            
            # Check last few days to see when we last had costs
            end_date = datetime.now(timezone.utc)
            
            for days_back in range(5):  # Check last 5 days
                check_date = end_date - timedelta(days=days_back)
                
                response = self.cost_explorer.get_cost_and_usage(
                    TimePeriod={
                        'Start': check_date.strftime('%Y-%m-%d'),
                        'End': (check_date + timedelta(days=1)).strftime('%Y-%m-%d')
                    },
                    Granularity='DAILY',
                    Metrics=['BlendedCost']
                )
                
                cost = sum(Decimal(r['Total']['BlendedCost']['Amount']) for r in response['ResultsByTime'])
                
                if cost > 0:
                    print(f"📅 {check_date.strftime('%Y-%m-%d')}: ${cost:.6f} ✅")
                else:
                    print(f"📅 {check_date.strftime('%Y-%m-%d')}: ${cost:.6f}")
            
            return True
            
        except Exception as e:
            print(f"❌ Cost data freshness check failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all Cost Explorer validation tests"""
        print("🧪 AWS COST EXPLORER DETAILED VALIDATION")
        print("This test verifies that Cost Explorer is returning real, accurate data")
        
        results = []
        
        # Test 1: Basic API
        success, total_cost = await self.test_1_basic_cost_explorer_api()
        results.append(("Basic API", success))
        
        # Test 2: Service breakdown
        service_count, service_total = await self.test_2_service_breakdown()
        results.append(("Service Breakdown", service_count > 0))
        
        # Test 3: Time periods
        time_success = await self.test_3_compare_time_periods()
        results.append(("Time Periods", time_success))
        
        # Test 4: Tracker accuracy
        accuracy_success = await self.test_4_validate_tracker_accuracy()
        results.append(("Tracker Accuracy", accuracy_success))
        
        # Test 5: Data freshness
        freshness_success = await self.test_5_cost_data_freshness()
        results.append(("Data Freshness", freshness_success))
        
        # Summary
        self.print_header("VALIDATION SUMMARY")
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\n📊 Overall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 Cost Explorer API is working correctly and returning real data!")
            print(f"💰 Confirmed real AWS spending: ${total_cost:.6f} (7 days)")
            print(f"🔧 Services with costs: {service_count}")
        else:
            print("⚠️  Some tests failed - Cost Explorer may not be working correctly")
        
        return passed == total

async def main():
    """Run the detailed Cost Explorer validation."""
    validator = CostExplorerValidator()
    await validator.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main()) 