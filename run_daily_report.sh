#!/bin/bash
# Daily AWS Cost Report - Cron Job Wrapper
# Ensures proper environment setup for automated execution

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the project directory
cd "$SCRIPT_DIR"

# Set up logging
LOG_FILE="$SCRIPT_DIR/logs/daily_cost_report.log"
mkdir -p "$SCRIPT_DIR/logs"

# Add timestamp to log
echo "=================================" >> "$LOG_FILE"
echo "Daily Cost Report - $(date)" >> "$LOG_FILE"
echo "=================================" >> "$LOG_FILE"

# Activate conda environment (if using conda)
# Uncomment and modify the next line if you need to activate a specific conda environment
# source /Users/rishimanimaran/miniforge3/bin/activate base

# Set up Python path
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Run the daily cost report
echo "Running daily cost report from: $SCRIPT_DIR" >> "$LOG_FILE"
python3 "$SCRIPT_DIR/daily_cost_report.py" >> "$LOG_FILE" 2>&1

# Log the exit status
EXIT_CODE=$?
echo "Daily cost report completed with exit code: $EXIT_CODE" >> "$LOG_FILE"
echo "=================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

exit $EXIT_CODE 