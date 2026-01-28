# Database Auto-Restore on Initialization

This feature allows PostgreSQL to automatically restore from a backup when the database is first created.

## How It Works

When you start a fresh PostgreSQL container (with an empty `postgres_data` directory), the initialization script `/docker/init-scripts/restore-from-backup.sh` runs automatically and checks for backup files in `./data/db_backups/`.

## Configuration

### 1. Enable Auto-Restore

Add to your `.env` file:

```bash
AUTO_RESTORE_BACKUP=true
```

### 2. Place Backup Files

Ensure your backup chunks are in `./data/db_backups/`:

```
./data/db_backups/
  ├── db_dump.gz_aa
  ├── db_dump.gz_ab
  ├── db_dump.gz_ac
  └── ...
```

### 3. Initialize Fresh Database

```bash
# Remove existing database data
docker compose down -v
sudo rm -rf postgres_data/

# Start with auto-restore enabled
docker compose up -d

# Check logs to see restore progress
docker compose logs -f postgres
```

## Use Cases

### Cloning Repository with Data

Perfect for distributing your application with pre-populated data:

```bash
# On machine A: Create backup
make db-backup
git add data/db_backups/
git commit -m "Add database backup"
git push

# On machine B: Clone and auto-restore
git clone <your-repo>
cd law_ai
echo "AUTO_RESTORE_BACKUP=true" >> .env
make start  # Automatically restores from backup!
```

### Disaster Recovery

Quick recovery to a known good state:

```bash
# Enable auto-restore
echo "AUTO_RESTORE_BACKUP=true" >> .env

# Reset to backup state
docker compose down -v
sudo rm -rf postgres_data/
docker compose up -d
```

### Development Environment Reset

Reset to baseline data for testing:

```bash
# One-time setup: create baseline backup
make db-backup

# Anytime: reset to baseline
AUTO_RESTORE_BACKUP=true make restart
```

## Important Notes

- **Only runs on first initialization**: The script only executes when creating a new database (empty `postgres_data/`)
- **Requires empty data directory**: You must delete `postgres_data/` to trigger restoration
- **Backup format**: Expects compressed chunks named `db_dump.gz_*` (created by `make db-backup`)
- **Read-only mount**: Backup directory is mounted as read-only (`:ro`) for safety

## Disabling Auto-Restore

Set in `.env`:

```bash
AUTO_RESTORE_BACKUP=false
```

Or remove the variable entirely (defaults to `false`).

## Troubleshooting

### "No backup files found"

**Problem**: Init script doesn't find backup files.

**Solution**: Ensure files are in `./data/db_backups/` with correct naming:
```bash
ls -la data/db_backups/
# Should show: db_dump.gz_aa, db_dump.gz_ab, etc.
```

### "Database already exists"

**Problem**: PostgreSQL init scripts don't run on existing databases.

**Solution**: Remove the data directory first:
```bash
docker compose down -v
sudo rm -rf postgres_data/
docker compose up -d
```

### Permission denied

**Problem**: Init script can't read backup files.

**Solution**: Check file permissions:
```bash
chmod 644 data/db_backups/db_dump.gz_*
```

## Manual Override

You can always restore manually without auto-restore:

```bash
# Traditional manual restore (works anytime)
make db-restore DIR=./data/db_backups
```

## See Also

- [Database Backup & Restore](./DATABASE_BACKUP.md) - Manual backup/restore commands
- [Makefile](../Makefile) - Available make commands
