#!/usr/bin/env python3
"""
Daily AWS Cost Report - Automated Email Summary
Sends daily email with real AWS spending breakdown.
Perfect for cron job automation.
"""

import sys
import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config import get_settings
from src.cost_aware_tracker import get_cost_aware_tracker
from src.email_alerts import send_cost_alert_email

async def generate_daily_cost_report():
    """Generate and send daily cost report email."""
    
    print(f"📊 Generating daily cost report at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    try:
        tracker = get_cost_aware_tracker()
        settings = get_settings()
        
        # Get real AWS spending data
        print("💰 Fetching real AWS spending data...")
        real_daily = await tracker.get_real_daily_spend()
        real_weekly = await tracker.get_real_weekly_spend()
        real_monthly = await tracker.get_real_monthly_spend()
        
        # Get service breakdown
        service_costs = await tracker.get_cost_by_service(days=1)
        weekly_service_costs = await tracker.get_cost_by_service(days=7)
        
        # Get API cost summary
        api_summary = tracker.get_api_cost_summary()
        
        # Calculate percentages of budget used
        daily_percentage = (real_daily / settings.daily_budget_limit * 100) if settings.daily_budget_limit > 0 else 0
        weekly_percentage = (real_weekly / settings.weekly_budget_limit * 100) if settings.weekly_budget_limit > 0 else 0
        monthly_percentage = (real_monthly / settings.monthly_budget_limit * 100) if settings.monthly_budget_limit > 0 else 0
        
        # Create email subject
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        subject = f"📊 Daily AWS Cost Report - {date_str} (${real_daily:.4f} today)"
        
        # Build detailed email body
        body = f"""📊 AWS COST REPORT - {date_str}

🎯 PODCAST Q&A SYSTEM SPENDING SUMMARY

💰 CURRENT SPENDING:
   Today:      ${real_daily:.6f}
   This Week:  ${real_weekly:.6f}
   This Month: ${real_monthly:.6f}

📈 BUDGET UTILIZATION:
   Daily:   {daily_percentage:.1f}% of ${settings.daily_budget_limit:.2f} limit
   Weekly:  {weekly_percentage:.1f}% of ${settings.weekly_budget_limit:.2f} limit  
   Monthly: {monthly_percentage:.1f}% of ${settings.monthly_budget_limit:.2f} limit

"""

        # Add service breakdown for today
        if service_costs:
            body += "🔧 TODAY'S SPENDING BY SERVICE:\n"
            sorted_services = sorted(service_costs.items(), key=lambda x: x[1], reverse=True)
            for service, cost in sorted_services:
                if cost > 0:
                    body += f"   • {service}: ${cost:.6f}\n"
        else:
            body += "🔧 TODAY'S SPENDING BY SERVICE:\n   • No costs incurred today\n"
        
        body += "\n"
        
        # Add weekly service breakdown
        if weekly_service_costs:
            body += "📊 THIS WEEK'S SPENDING BY SERVICE:\n"
            sorted_weekly = sorted(weekly_service_costs.items(), key=lambda x: x[1], reverse=True)
            total_weekly_cost = sum(cost for _, cost in sorted_weekly)
            for service, cost in sorted_weekly:
                if cost > 0:
                    percentage = (cost / total_weekly_cost * 100) if total_weekly_cost > 0 else 0
                    body += f"   • {service}: ${cost:.6f} ({percentage:.1f}%)\n"
        
        # Add status indicators
        body += "\n🚦 STATUS INDICATORS:\n"
        
        if daily_percentage > 80:
            body += "   🔴 Daily budget: HIGH usage (>80%)\n"
        elif daily_percentage > 50:
            body += "   🟡 Daily budget: MODERATE usage (>50%)\n"
        else:
            body += "   🟢 Daily budget: LOW usage (<50%)\n"
            
        if monthly_percentage > 80:
            body += "   🔴 Monthly budget: HIGH usage (>80%)\n"
        elif monthly_percentage > 50:
            body += "   🟡 Monthly budget: MODERATE usage (>50%)\n"
        else:
            body += "   🟢 Monthly budget: LOW usage (<50%)\n"
        
        # Add recommendations
        body += f"""
🔍 API USAGE TRACKING:
   • Cost Explorer API calls today: {api_summary['todays_api_calls']}
   • Estimated API costs: {api_summary['estimated_api_cost']}
   • Remaining calls: {api_summary['remaining_calls']}/{api_summary['daily_limit']}
   • Cache entries: {api_summary['cache_entries']}

💡 RECOMMENDATIONS:
   • Monitor AWS console for unexpected spikes
   • Consider cost optimization for high-usage services
   • Review budget limits if consistently near thresholds
   • API calls are cached for 6 hours to minimize costs

🕒 Report Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
📧 Automated Daily Report - Podcast Q&A System
🛡️  Cost Protection: ACTIVE (Emergency limit: ${settings.emergency_stop_budget:.2f})
🔒 API Protection: ACTIVE (Max 10 calls/day = $0.10)
"""
        
        # Send the email
        print(f"📧 Sending daily report to: {settings.cost_alert_email}")
        email_sent = await send_cost_alert_email(subject, body)
        
        if email_sent:
            print("✅ Daily cost report sent successfully!")
            print(f"💰 Summary: Daily ${real_daily:.6f}, Weekly ${real_weekly:.6f}, Monthly ${real_monthly:.6f}")
            return True
        else:
            print("❌ Failed to send daily cost report")
            return False
            
    except Exception as e:
        print(f"❌ Error generating daily cost report: {e}")
        
        # Send error notification email
        try:
            error_subject = f"🚨 Error: Daily Cost Report Failed - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
            error_body = f"""❌ DAILY COST REPORT ERROR

The automated daily cost report failed to generate.

Error Details:
{str(e)}

Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

Please check the system and retry manually if needed.

Automated Error Report - Podcast Q&A System
"""
            await send_cost_alert_email(error_subject, error_body)
            print("📧 Error notification email sent")
        except:
            print("❌ Failed to send error notification email")
            
        return False

def main():
    """Main function for cron job execution."""
    try:
        result = asyncio.run(generate_daily_cost_report())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"❌ Critical error in daily cost report: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 