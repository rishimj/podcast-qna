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
"/Users/rishimanimaran/Documents/Work/podcast-q&a/run_daily_report.sh" >> logs/cron_debug.log 2>&1
echo "$(date): Daily cost report completed with exit code: $?" >> logs/cron_debug.log
