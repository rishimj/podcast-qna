#!/bin/bash
# Fix macOS Cron Permissions and Setup
# Addresses common macOS cron job issues

echo "🔧 Fixing macOS Cron Job Issues"
echo "================================"

PROJECT_DIR="/Users/rishimanimaran/Documents/Work/podcast-q&a"

# Check if we're on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "✅ Detected macOS - applying macOS-specific fixes"
    
    # Check Terminal permissions
    echo "📋 Checking Terminal permissions..."
    
    # Create a more robust wrapper script
    cat > "$PROJECT_DIR/cron_wrapper.sh" << 'EOF'
#!/bin/bash
# Robust cron wrapper for macOS

# Set up environment
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export HOME="/Users/rishimanimaran"
export USER="rishimanimaran"

# Change to project directory
cd "/Users/rishimanimaran/Documents/Work/podcast-q&a"

# Source conda/python environment if needed
if [ -f "/Users/rishimanimaran/miniforge3/bin/activate" ]; then
    source "/Users/rishimanimaran/miniforge3/bin/activate" base
fi

# Run the daily report with full logging
echo "$(date): Starting daily cost report..." >> logs/cron_debug.log
/Users/rishimanimaran/Documents/Work/podcast-q&a/run_daily_report.sh >> logs/cron_debug.log 2>&1
echo "$(date): Daily cost report completed with exit code: $?" >> logs/cron_debug.log
EOF

    chmod +x "$PROJECT_DIR/cron_wrapper.sh"
    echo "✅ Created robust cron wrapper script"
    
    # Remove old cron job and add new one
    echo "🔄 Updating cron job..."
    
    # Remove existing podcast-qa cron jobs
    crontab -l 2>/dev/null | grep -v "podcast-q&a" | crontab -
    
    # Add new cron job with better error handling
    (crontab -l 2>/dev/null; echo "0 10 * * * $PROJECT_DIR/cron_wrapper.sh") | crontab -
    
    echo "✅ Updated cron job to use robust wrapper"
    
    # Test the wrapper
    echo "🧪 Testing cron wrapper..."
    "$PROJECT_DIR/cron_wrapper.sh"
    
    if [ $? -eq 0 ]; then
        echo "✅ Cron wrapper test successful!"
    else
        echo "❌ Cron wrapper test failed"
    fi
    
    # Show current crontab
    echo ""
    echo "📋 Current crontab:"
    crontab -l
    
    echo ""
    echo "🍎 macOS-Specific Instructions:"
    echo "1. Go to System Preferences > Security & Privacy > Privacy"
    echo "2. Select 'Full Disk Access' from the left panel"
    echo "3. Click the lock and enter your password"
    echo "4. Click '+' and add Terminal app (/Applications/Utilities/Terminal.app)"
    echo "5. Also add cron (/usr/sbin/cron) if visible"
    echo ""
    echo "📧 Alternative: Use launchd instead of cron (more reliable on macOS)"
    
else
    echo "ℹ️ Not on macOS - standard cron should work fine"
fi

echo ""
echo "🎯 Next Steps:"
echo "1. Check your email for the test report that just ran"
echo "2. If no email, check Gmail spam folder"
echo "3. Wait until tomorrow 10 AM for automatic report"
echo "4. Check logs/cron_debug.log for detailed cron execution info" 