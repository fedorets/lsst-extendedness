#!/bin/bash
#
# LSST Alert Pipeline - Data Cleanup Script
# Removes old data files based on retention policies
#
# Can be run manually or via cron:
# 0 3 * * * /home/ubuntu/lsst-extendedness/bin/cleanup_old_data.sh

set -e

# Determine script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
CSV_RETENTION_DAYS=${CSV_RETENTION_DAYS:-90}      # Keep CSV files for 90 days
CUTOUT_RETENTION_DAYS=${CUTOUT_RETENTION_DAYS:-30}  # Keep cutouts for 30 days
LOG_RETENTION_DAYS=${LOG_RETENTION_DAYS:-60}      # Keep logs for 60 days
ARCHIVE_BEFORE_DELETE=${ARCHIVE_BEFORE_DELETE:-true}  # Archive before deletion
DRY_RUN=${DRY_RUN:-false}                         # Set to true for testing

# Directories
DATA_DIR="$BASE_DIR/data"
LOG_DIR="$BASE_DIR/logs"
ARCHIVE_DIR="$DATA_DIR/archive"
TEMP_DIR="$BASE_DIR/temp"

# Logging
LOG_FILE="$LOG_DIR/cleanup/cleanup_$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "======================================"
log "LSST Data Cleanup - Starting"
log "======================================"
log "CSV retention: $CSV_RETENTION_DAYS days"
log "Cutout retention: $CUTOUT_RETENTION_DAYS days"
log "Log retention: $LOG_RETENTION_DAYS days"
log "Archive before delete: $ARCHIVE_BEFORE_DELETE"
log "Dry run: $DRY_RUN"
log ""

# Function to archive directory before deletion
archive_and_delete() {
    local source_dir="$1"
    local retention_days="$2"
    local archive_name="$3"

    if [ ! -d "$source_dir" ]; then
        log "Directory not found: $source_dir (skipping)"
        return
    fi

    # Find directories older than retention period
    old_dirs=$(find "$source_dir" -mindepth 1 -maxdepth 3 -type d -mtime +$retention_days 2>/dev/null || true)

    if [ -z "$old_dirs" ]; then
        log "No old directories found in $source_dir"
        return
    fi

    log "Found old directories in $source_dir:"
    echo "$old_dirs" | while read dir; do
        log "  - $dir"
    done

    if [ "$ARCHIVE_BEFORE_DELETE" = "true" ]; then
        # Create archive directory
        mkdir -p "$ARCHIVE_DIR/$(date +%Y)"

        # Archive each old directory
        echo "$old_dirs" | while read dir; do
            if [ -d "$dir" ]; then
                dir_name=$(basename "$dir")
                parent_name=$(basename "$(dirname "$dir")")
                archive_file="$ARCHIVE_DIR/$(date +%Y)/${archive_name}_${parent_name}_${dir_name}_$(date +%Y%m%d).tar.gz"

                log "Archiving: $dir -> $archive_file"

                if [ "$DRY_RUN" = "false" ]; then
                    tar -czf "$archive_file" -C "$(dirname "$dir")" "$(basename "$dir")" 2>&1 | tee -a "$LOG_FILE"
                    if [ ${PIPESTATUS[0]} -eq 0 ]; then
                        log "Archive created successfully: $archive_file"
                        log "Deleting: $dir"
                        rm -rf "$dir"
                        log "Deleted: $dir"
                    else
                        log "ERROR: Failed to create archive for $dir - NOT DELETING"
                    fi
                else
                    log "[DRY RUN] Would archive and delete: $dir"
                fi
            fi
        done
    else
        # Delete without archiving
        echo "$old_dirs" | while read dir; do
            if [ -d "$dir" ]; then
                log "Deleting (no archive): $dir"
                if [ "$DRY_RUN" = "false" ]; then
                    rm -rf "$dir"
                    log "Deleted: $dir"
                else
                    log "[DRY RUN] Would delete: $dir"
                fi
            fi
        done
    fi
}

# Function to clean old files
clean_old_files() {
    local dir="$1"
    local pattern="$2"
    local retention_days="$3"

    if [ ! -d "$dir" ]; then
        log "Directory not found: $dir (skipping)"
        return
    fi

    log "Cleaning old files in $dir (pattern: $pattern, age: >$retention_days days)"

    count=$(find "$dir" -name "$pattern" -type f -mtime +$retention_days 2>/dev/null | wc -l || echo 0)

    if [ "$count" -eq 0 ]; then
        log "No old files found matching pattern $pattern"
        return
    fi

    log "Found $count old files"

    if [ "$DRY_RUN" = "false" ]; then
        find "$dir" -name "$pattern" -type f -mtime +$retention_days -delete 2>&1 | tee -a "$LOG_FILE"
        log "Deleted $count files"
    else
        log "[DRY RUN] Would delete $count files"
        find "$dir" -name "$pattern" -type f -mtime +$retention_days 2>/dev/null | head -10 | tee -a "$LOG_FILE"
    fi
}

# Clean CSV files
log ""
log "--- Cleaning CSV files ---"
archive_and_delete "$DATA_DIR/processed/csv" "$CSV_RETENTION_DAYS" "csv"

# Clean cutout files
log ""
log "--- Cleaning cutout files ---"
archive_and_delete "$DATA_DIR/cutouts" "$CUTOUT_RETENTION_DAYS" "cutouts"

# Clean log files
log ""
log "--- Cleaning log files ---"
clean_old_files "$LOG_DIR/consumer" "*.log" "$LOG_RETENTION_DAYS"
clean_old_files "$LOG_DIR/cron" "*.log" "$LOG_RETENTION_DAYS"
clean_old_files "$LOG_DIR/error" "*.log" "$LOG_RETENTION_DAYS"

# Clean temp files older than 7 days
log ""
log "--- Cleaning temporary files ---"
clean_old_files "$TEMP_DIR/failed" "*.json" 7
clean_old_files "$TEMP_DIR/processing" "*" 7
clean_old_files "$TEMP_DIR/partial_csvs" "*.csv" 7

# Clean empty directories
log ""
log "--- Removing empty directories ---"
if [ "$DRY_RUN" = "false" ]; then
    find "$DATA_DIR" -type d -empty -delete 2>/dev/null || true
    log "Empty directories removed"
else
    empty_count=$(find "$DATA_DIR" -type d -empty 2>/dev/null | wc -l || echo 0)
    log "[DRY RUN] Would remove $empty_count empty directories"
fi

# Summary
log ""
log "======================================"
log "Cleanup completed"
log "======================================"

# Disk usage report
log ""
log "Current disk usage:"
du -sh "$DATA_DIR/processed/csv" 2>/dev/null | tee -a "$LOG_FILE" || true
du -sh "$DATA_DIR/cutouts" 2>/dev/null | tee -a "$LOG_FILE" || true
du -sh "$DATA_DIR/archive" 2>/dev/null | tee -a "$LOG_FILE" || true
du -sh "$LOG_DIR" 2>/dev/null | tee -a "$LOG_FILE" || true

exit 0
