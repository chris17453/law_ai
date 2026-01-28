# Database Backup and Restore

LawBot includes built-in database backup and restore functionality that creates GitHub-friendly chunked backups.

## Features

- **Chunked backups**: Automatically splits large databases into chunks under 100MB (configurable)
- **Compression**: Uses gzip compression to minimize storage space
- **Easy restore**: Simple one-command restore from backup chunks
- **GitHub-ready**: Designed for storing backups in git repositories

## Prerequisites

Make sure you have PostgreSQL client tools installed:

```bash
# Ubuntu/Debian
sudo apt-get install postgresql-client

# macOS
brew install postgresql

# Red Hat/Fedora
sudo dnf install postgresql
```

## Usage

### Backup Database

Create a backup of your database:

```bash
lawbot db backup
```

This creates a compressed, chunked backup in `./backups` directory by default.

**Options:**

- `--dir, -d`: Specify backup directory (default: `./backups`)
- `--chunk-size, -c`: Maximum chunk size in MB (default: 95)
- `--no-compress`: Disable compression (not recommended)

**Examples:**

```bash
# Backup to custom directory
lawbot db backup --dir ./data/backups

# Use larger chunks (for services that support >100MB)
lawbot db backup --chunk-size 200

# Uncompressed backup
lawbot db backup --no-compress
```

### Restore Database

Restore your database from a backup:

```bash
lawbot db restore ./backups
```

**Warning**: This will replace all data in your current database. You'll be prompted to confirm before proceeding.

**Options:**

- `--no-compress`: Indicate backup is not compressed

**Examples:**

```bash
# Restore from custom directory
lawbot db restore ./data/backups

# Restore uncompressed backup
lawbot db restore ./backups --no-compress
```

## How It Works

### Backup Process

1. Connects to PostgreSQL using credentials from `.env`
2. Runs `pg_dump` to export the entire database
3. Compresses the dump with `gzip` (optional)
4. Splits the compressed dump into chunks using `split`
5. Creates files named `db_dump.gz_aa`, `db_dump.gz_ab`, etc.

### Restore Process

1. Finds all backup chunks in the specified directory
2. Concatenates chunks using `cat`
3. Decompresses with `gunzip` (if compressed)
4. Pipes the SQL into `psql` to restore the database

## Git Integration

The chunked backups are designed to work well with git:

```bash
# Create backup
lawbot db backup --dir ./data/db_backups

# Add to git
git add data/db_backups/
git commit -m "Add database backup"
git push
```

To restore on another machine:

```bash
# Clone the repo
git clone <your-repo>
cd law_ai

# Restore database
lawbot db restore ./data/db_backups
```

## Automation

You can automate backups using cron:

```bash
# Edit crontab
crontab -e

# Add a daily backup at 2 AM
0 2 * * * cd /path/to/law_ai && /path/to/venv/bin/lawbot db backup --dir ./data/backups
```

## Troubleshooting

### "Command not found: pg_dump"

Install PostgreSQL client tools (see Prerequisites above).

### "Connection refused"

Make sure your PostgreSQL container is running:

```bash
docker-compose up -d
```

### "Permission denied"

Check that your `.env` file has the correct database credentials:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=law_ai
POSTGRES_USER=law_ai_user
POSTGRES_PASSWORD=law_ai_password
```

### Backup too large even with compression

Try increasing the chunk size or consider backing up only specific tables:

```bash
# Manual table-specific backup
pg_dump -h localhost -U law_ai_user -d law_ai -t large_table > large_table.sql
```

## Technical Details

**Backup command pipeline:**

```bash
pg_dump [options] | gzip | split -b 95M - db_dump.gz_
```

**Restore command pipeline:**

```bash
cat db_dump.gz_* | gunzip | psql [options]
```

**Chunk naming:**

- Compressed: `db_dump.gz_aa`, `db_dump.gz_ab`, `db_dump.gz_ac`, ...
- Uncompressed: `db_dump_aa`, `db_dump_ab`, `db_dump_ac`, ...

The suffix uses alphabetic ordering (aa, ab, ..., zz, aaa, aab, ...).
