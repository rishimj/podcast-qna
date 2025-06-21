#!/bin/bash
# Setup Daily AWS Cost Reports - Cron Job Configuration
# This script helps you set up automated daily cost reports

PROJECT_DIR="/Users/rishimanimaran/Documents/Work/podcast-q&a"

echo "🔧 Setting up Daily AWS Cost Reports"
echo "=================================="

# Check if the script exists
if [ ! -f "$PROJECT_DIR/run_daily_report.sh" ]; then
    echo "❌ Error: run_daily_report.sh not found in $PROJECT_DIR"
    exit 1
fi

echo "✅ Found daily report script"

# Make sure the script is executable
chmod +x "$PROJECT_DIR/run_daily_report.sh"
chmod +x "$PROJECT_DIR/daily_cost_report.py"

echo "✅ Set script permissions"

# Show current crontab
echo ""
echo "📋 Current crontab entries:"
crontab -l 2>/dev/null || echo "(No current crontab entries)"

echo ""
echo "🕒 Cron Job Options:"
echo "1. Daily at 8:00 AM: 0 8 * * * $PROJECT_DIR/run_daily_report.sh"
echo "2. Daily at 9:00 AM: 0 9 * * * $PROJECT_DIR/run_daily_report.sh"
echo "3. Daily at 10:00 AM: 0 10 * * * $PROJECT_DIR/run_daily_report.sh"
echo "4. Custom time (you'll enter manually)"

echo ""
read -p "Choose option (1-4): " choice

case $choice in
    1)
        CRON_TIME="0 8 * * *"
        TIME_DESC="8:00 AM daily"
        ;;
    2)
        CRON_TIME="0 9 * * *"
        TIME_DESC="9:00 AM daily"
        ;;
    3)
        CRON_TIME="0 10 * * *"
        TIME_DESC="10:00 AM daily"
        ;;
    4)
        echo "Enter cron time format (e.g., '0 8 * * *' for 8:00 AM daily):"
        read -p "Cron time: " CRON_TIME
        TIME_DESC="custom time"
        ;;
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

# Create the cron job entry
CRON_ENTRY="$CRON_TIME $PROJECT_DIR/run_daily_report.sh"

echo ""
echo "📝 Cron job to add:"
echo "$CRON_ENTRY"
echo ""
echo "This will send daily AWS cost reports to: $(grep COST_ALERT_EMAIL $PROJECT_DIR/config.env | cut -d'=' -f2)"
echo ""

read -p "Add this cron job? (y/n): " confirm

if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    
    if [ $? -eq 0 ]; then
        echo "✅ Cron job added successfully!"
        echo "📊 Daily AWS cost reports will be sent $TIME_DESC"
        echo ""
        echo "📋 Current crontab:"
        crontab -l
        echo ""
        echo "📝 To remove this cron job later, run: crontab -e"
        echo "📧 Check your email tomorrow for the first report!"
        
        # Test the setup
        echo ""
        read -p "Would you like to test the setup now? (y/n): " test_now
        if [ "$test_now" = "y" ] || [ "$test_now" = "Y" ]; then
            echo "🧪 Testing daily report setup..."
            "$PROJECT_DIR/run_daily_report.sh"
            echo "✅ Test completed! Check the log file: $PROJECT_DIR/logs/daily_cost_report.log"
        fi
    else
        echo "❌ Failed to add cron job"
        exit 1
    fi
else
    echo "❌ Cron job setup cancelled"
fi

echo ""
echo "🎯 Setup Complete!"
echo "Your daily AWS cost reports are now automated 🚀" 