#!/bin/bash
# Example script demonstrating database backup functionality

set -e

echo "==================================="
echo "LawBot Database Backup Example"
echo "==================================="
echo

# Set the backup directory
BACKUP_DIR="./data/db_backups"

echo "1. Creating backup of law_ai database..."
echo "   Directory: $BACKUP_DIR"
echo "   Chunk size: 95MB"
echo "   Compression: enabled"
echo

# Create backup
lawbot db backup --dir "$BACKUP_DIR" --chunk-size 95

echo
echo "2. Backup created! Files:"
ls -lh "$BACKUP_DIR"

echo
echo "3. To restore this backup later, run:"
echo "   lawbot db restore $BACKUP_DIR"

echo
echo "4. To add to git:"
echo "   git add $BACKUP_DIR"
echo "   git commit -m 'Add database backup'"
echo "   git push"

echo
echo "==================================="
echo "Backup complete!"
echo "==================================="
