#!/bin/bash
# Setup macOS launchd for Daily Cost Reports
# More reliable than cron on macOS

echo "🍎 Setting up macOS launchd for Daily Cost Reports"
echo "=================================================="

PROJECT_DIR="/Users/rishimanimaran/Documents/Work/podcast-q&a"
PLIST_NAME="com.podcast-qa.daily-cost-report"
PLIST_FILE="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

# Create the launchd plist file
echo "📝 Creating launchd configuration..."

cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$PROJECT_DIR/run_daily_report.sh</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>10</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd_out.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd_err.log</string>
    
    <key>RunAtLoad</key>
    <false/>
    
    <key>KeepAlive</key>
    <false/>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/Users/rishimanimaran/miniforge3/bin</string>
        <key>HOME</key>
        <string>/Users/rishimanimaran</string>
    </dict>
</dict>
</plist>
EOF

echo "✅ Created launchd plist file: $PLIST_FILE"

# Load the launchd job
echo "🔄 Loading launchd job..."
launchctl unload "$PLIST_FILE" 2>/dev/null || true  # Remove if exists
launchctl load "$PLIST_FILE"

if [ $? -eq 0 ]; then
    echo "✅ launchd job loaded successfully!"
else
    echo "❌ Failed to load launchd job"
    exit 1
fi

# Test the job
echo "🧪 Testing launchd job..."
launchctl start "$PLIST_NAME"

# Wait a moment for it to complete
sleep 3

# Check if it ran
if [ -f "$PROJECT_DIR/logs/launchd_out.log" ]; then
    echo "✅ Test run completed! Check logs:"
    echo "📄 Output log: $PROJECT_DIR/logs/launchd_out.log"
    echo "📄 Error log: $PROJECT_DIR/logs/launchd_err.log"
    
    echo ""
    echo "📊 Latest output:"
    tail -10 "$PROJECT_DIR/logs/launchd_out.log" 2>/dev/null || echo "No output log yet"
    
    if [ -f "$PROJECT_DIR/logs/launchd_err.log" ]; then
        echo ""
        echo "⚠️ Errors (if any):"
        tail -5 "$PROJECT_DIR/logs/launchd_err.log" 2>/dev/null || echo "No errors"
    fi
else
    echo "⚠️ Test run may not have completed yet"
fi

# Show job status
echo ""
echo "📋 launchd job status:"
launchctl list | grep "$PLIST_NAME" || echo "Job not found in list"

# Remove old cron job
echo ""
echo "🔄 Removing old cron job..."
crontab -l 2>/dev/null | grep -v "podcast-q&a" | crontab -
echo "✅ Old cron job removed"

echo ""
echo "🎉 macOS launchd setup complete!"
echo ""
echo "📅 Your daily cost reports will now run at 10:00 AM using launchd"
echo "📊 This is more reliable than cron on macOS"
echo ""
echo "🛠️ Management commands:"
echo "  Start job now:    launchctl start $PLIST_NAME"
echo "  Stop job:         launchctl stop $PLIST_NAME"
echo "  Unload job:       launchctl unload $PLIST_FILE"
echo "  Reload job:       launchctl unload $PLIST_FILE && launchctl load $PLIST_FILE"
echo ""
echo "📝 Log files:"
echo "  Output: $PROJECT_DIR/logs/launchd_out.log"
echo "  Errors: $PROJECT_DIR/logs/launchd_err.log" 