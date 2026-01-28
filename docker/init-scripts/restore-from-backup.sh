#!/bin/bash
# PostgreSQL initialization script to restore from backup
# This script runs automatically when the database is first created
# Place your backup chunks in ./data/db_backups/ before starting the container

set -e

BACKUP_DIR="/backups"
DB_NAME="${POSTGRES_DB}"
DB_USER="${POSTGRES_USER}"

echo "=========================================="
echo "PostgreSQL Initialization - Backup Restore"
echo "=========================================="

# Check if auto-restore is enabled
if [ "$AUTO_RESTORE_BACKUP" != "true" ]; then
    echo "ℹ Auto-restore disabled (AUTO_RESTORE_BACKUP != true)"
    echo "  Starting with empty database"
    echo ""
    echo "  To enable auto-restore:"
    echo "    Set AUTO_RESTORE_BACKUP=true in your .env file"
    exit 0
fi

# Check if backup files exist
if [ -d "$BACKUP_DIR" ] && [ "$(ls -A $BACKUP_DIR/db_dump.gz_* 2>/dev/null)" ]; then
    echo "✓ Backup files found in $BACKUP_DIR"
    echo "  Restoring database from backup..."

    # Concatenate all chunks, decompress, and restore
    cat "$BACKUP_DIR"/db_dump.gz_* | gunzip | psql -U "$DB_USER" -d "$DB_NAME"

    if [ $? -eq 0 ]; then
        echo "✓ Database restored successfully from backup!"
    else
        echo "✗ Error restoring database from backup"
        exit 1
    fi
else
    echo "ℹ No backup files found in $BACKUP_DIR"
    echo "  Starting with empty database"
    echo ""
    echo "  To restore from backup on next initialization:"
    echo "    1. Stop containers:     docker compose down -v"
    echo "    2. Place backups in:    ./data/db_backups/"
    echo "    3. Start containers:    docker compose up -d"
fi

echo "=========================================="
