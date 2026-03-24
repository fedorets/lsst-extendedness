#!/bin/bash
#
# update_obscodes.sh — Keep the local MPC observatory codes file current.
#
# Downloads ObsCodes.html from the Minor Planet Center and replaces the local
# copy at data/ObsCodes.dat only when the content has changed (SHA-256 check).
# No update is written if the file is identical to what was previously stored.
#
# Called automatically by:
#   - bin/run_lsst_consumer.sh  (daily cron job)
#   - systemd/lsst-update-obscodes.service  (systemd timer, daily at 01:00)
#
# Can also be run manually:
#   bash scripts/update_obscodes.sh
#
# Exit codes:
#   0  Success (updated or already current)
#   1  Download failed
#   2  Unexpected error

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

OBSCODE_URL="https://www.minorplanetcenter.net/iau/lists/ObsCodes.html"
OBSCODE_LOCAL="$BASE_DIR/data/ObsCodes.dat"
OBSCODE_TEMP="$BASE_DIR/temp/ObsCodes.dat.tmp"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR="$BASE_DIR/logs/obscodes"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/obscodes_$(date +%Y%m%d).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "======================================"
log "MPC ObsCodes Update - Starting"
log "======================================"
log "Source:  $OBSCODE_URL"
log "Local:   $OBSCODE_LOCAL"

# ---------------------------------------------------------------------------
# Ensure directories exist
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "$OBSCODE_LOCAL")"
mkdir -p "$(dirname "$OBSCODE_TEMP")"

# ---------------------------------------------------------------------------
# Download to temporary file
# ---------------------------------------------------------------------------
log "Downloading..."

if ! curl --silent --show-error --fail \
          --max-time 60 \
          --user-agent "lsst-extendedness/obscodes-updater" \
          --output "$OBSCODE_TEMP" \
          "$OBSCODE_URL"; then
    log "ERROR: Download failed from $OBSCODE_URL"
    rm -f "$OBSCODE_TEMP"
    exit 1
fi

# Verify the downloaded file is non-empty and looks like ObsCodes data
if [ ! -s "$OBSCODE_TEMP" ]; then
    log "ERROR: Downloaded file is empty"
    rm -f "$OBSCODE_TEMP"
    exit 1
fi

if ! grep -q "Code" "$OBSCODE_TEMP" 2>/dev/null; then
    log "ERROR: Downloaded file does not look like an ObsCodes file (missing 'Code' header)"
    rm -f "$OBSCODE_TEMP"
    exit 1
fi

NEW_SIZE=$(wc -c < "$OBSCODE_TEMP")
log "Downloaded ${NEW_SIZE} bytes"

# ---------------------------------------------------------------------------
# Compare with existing file
# ---------------------------------------------------------------------------
if [ -f "$OBSCODE_LOCAL" ]; then
    OLD_HASH=$(sha256sum "$OBSCODE_LOCAL" | cut -d' ' -f1)
    NEW_HASH=$(sha256sum "$OBSCODE_TEMP"  | cut -d' ' -f1)

    if [ "$OLD_HASH" = "$NEW_HASH" ]; then
        log "No changes detected (SHA-256 identical: ${OLD_HASH:0:16}...)"
        log "Local file is already current."
        rm -f "$OBSCODE_TEMP"
    else
        OLD_SIZE=$(wc -c < "$OBSCODE_LOCAL")
        log "Change detected:"
        log "  Old SHA-256: ${OLD_HASH:0:16}...  (${OLD_SIZE} bytes)"
        log "  New SHA-256: ${NEW_HASH:0:16}...  (${NEW_SIZE} bytes)"

        # Keep a dated backup of the previous version
        BACKUP="$OBSCODE_LOCAL.$(date +%Y%m%d)"
        cp "$OBSCODE_LOCAL" "$BACKUP"
        log "Backup saved: $BACKUP"

        mv "$OBSCODE_TEMP" "$OBSCODE_LOCAL"
        log "ObsCodes updated successfully."
    fi
else
    log "No existing file found — saving initial copy."
    mv "$OBSCODE_TEMP" "$OBSCODE_LOCAL"
    log "ObsCodes saved to $OBSCODE_LOCAL"
fi

# ---------------------------------------------------------------------------
# Clean up dated backups older than 90 days
# ---------------------------------------------------------------------------
find "$(dirname "$OBSCODE_LOCAL")" \
     -name "ObsCodes.dat.*" \
     -type f \
     -mtime +90 \
     -delete 2>/dev/null || true

log "======================================"
log "MPC ObsCodes Update - Done"
log "======================================"
exit 0
