#!/bin/bash
#
# LSST Alert Consumer Cron Job Script
# Add to crontab with: crontab -e
# Example: 0 2 * * * /home/ubuntu/lsst-extendedness/bin/run_lsst_consumer.sh
#
# This script runs the LSST alert consumer and handles logging

set -e  # Exit on error

# Determine script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Source environment if exists
if [ -f "$BASE_DIR/venv/bin/activate" ]; then
    source "$BASE_DIR/venv/bin/activate"
fi

# Change to base directory
cd "$BASE_DIR"

# Set up logging
LOG_DIR="$BASE_DIR/logs/cron"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/cron_$(date +%Y%m%d).log"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Start logging
log "======================================"
log "LSST Alert Consumer - Starting"
log "======================================"
log "Base directory: $BASE_DIR"
log "Python: $(which python3)"
log "User: $(whoami)"

# Check if consumer is already running
PIDFILE="$BASE_DIR/temp/consumer.pid"
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        log "ERROR: Consumer already running with PID $PID"
        log "If this is incorrect, remove $PIDFILE and try again"
        exit 1
    else
        log "Stale PID file found, removing..."
        rm -f "$PIDFILE"
    fi
fi

# Write current PID
echo $$ > "$PIDFILE"

# Update MPC ObsCodes file before running the consumer
log "--------------------------------------"
log "Updating MPC ObsCodes file..."
if bash "$BASE_DIR/scripts/update_obscodes.sh"; then
    log "ObsCodes update completed."
else
    log "WARNING: ObsCodes update failed (exit $?) — continuing with existing file"
fi
log "--------------------------------------"

# Run the consumer
log "Starting consumer..."
START_TIME=$(date +%s)

# Run with error handling
if python3 src/lsst_alert_consumer.py >> "$LOG_FILE" 2>&1; then
    EXIT_CODE=0
    log "Consumer completed successfully"
else
    EXIT_CODE=$?
    log "ERROR: Consumer failed with exit code $EXIT_CODE"
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log "Runtime: ${DURATION} seconds"
log "======================================"
log ""

# Remove PID file
rm -f "$PIDFILE"

# Exit with consumer's exit code
exit $EXIT_CODE
