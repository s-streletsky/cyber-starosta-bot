#!/bin/bash
set -euo pipefail

# Daily root-owned backup of the two JSON data files.
# Data files are 640 (root-readable); the data dir is 750. No service stop is needed.
# Individual absent files are skipped: a fresh install may not have them yet.

DATA_DIR=/var/lib/cyber-starosta-bot
BACKUP_ROOT=/var/backups/cyber-starosta-bot
STAMP=$(date +%F)
DEST="$BACKUP_ROOT/$STAMP"

echo "Backup started: $STAMP"

install -d -m 0700 -o root -g root "$DEST"

copied=0
for name in absences.jsonl members.json; do
    source_file="$DATA_DIR/$name"
    if [ -f "$source_file" ]; then
        install -m 600 -o root -g root "$source_file" "$DEST/$name"
        echo "Copied $name"
        copied=$((copied + 1))
    else
        echo "Skipped $name (not found)"
    fi
done

if [ "$copied" -eq 0 ]; then
    echo "ERROR: no files were copied from $DATA_DIR" >&2
    exit 1
fi

echo "Pruning backups older than 30 days..."
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +

echo "Backup finished: $DEST"
