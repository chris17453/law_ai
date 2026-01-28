"""Database backup and restore utilities."""

import os
import subprocess
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn


def get_db_credentials():
    """Get database credentials from environment."""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'database': os.getenv('POSTGRES_DB', 'law_ai'),
        'user': os.getenv('POSTGRES_USER', 'law_ai_user'),
        'password': os.getenv('POSTGRES_PASSWORD', 'law_ai_password'),
    }


def backup_database(backup_dir: Path, chunk_size_mb: int = 95, compress: bool = True, console: Optional[Console] = None):
    """
    Backup the PostgreSQL database to chunked files.

    Args:
        backup_dir: Directory to store backup chunks
        chunk_size_mb: Maximum size per chunk in MB (default 95 for GitHub)
        compress: Whether to compress the dump (default True)
        console: Rich console for output
    """
    if console is None:
        console = Console()

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    creds = get_db_credentials()

    # Set PGPASSWORD environment variable for pg_dump
    env = os.environ.copy()
    env['PGPASSWORD'] = creds['password']

    console.print(f"[cyan]Backing up database:[/] {creds['database']}")
    console.print(f"[cyan]Backup location:[/] {backup_dir}")
    console.print(f"[cyan]Chunk size:[/] {chunk_size_mb}MB")
    console.print(f"[cyan]Compression:[/] {'Yes' if compress else 'No'}\n")

    # Build pg_dump command
    pg_dump_cmd = [
        'pg_dump',
        '-h', creds['host'],
        '-p', creds['port'],
        '-U', creds['user'],
        '-d', creds['database'],
        '--no-owner',  # Don't output commands to set ownership
        '--no-acl',    # Don't output commands to set ACLs
    ]

    # Determine output file prefix
    prefix = 'db_dump'
    if compress:
        prefix += '.gz'

    chunk_size_bytes = chunk_size_mb * 1024 * 1024

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Dumping database...", total=None)

            # Create the pipeline: pg_dump | (gzip) | split
            if compress:
                # pg_dump | gzip | split
                dump_process = subprocess.Popen(
                    pg_dump_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )

                gzip_process = subprocess.Popen(
                    ['gzip'],
                    stdin=dump_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                dump_process.stdout.close()  # Allow dump_process to receive SIGPIPE

                split_process = subprocess.Popen(
                    ['split', '-b', str(chunk_size_bytes), '-', str(backup_dir / prefix) + '_'],
                    stdin=gzip_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                gzip_process.stdout.close()

                # Wait for all processes
                split_stdout, split_stderr = split_process.communicate()
                gzip_returncode = gzip_process.wait()
                dump_returncode = dump_process.wait()

                if dump_returncode != 0:
                    _, dump_stderr = dump_process.communicate()
                    raise subprocess.CalledProcessError(dump_returncode, pg_dump_cmd, stderr=dump_stderr)
                if gzip_returncode != 0:
                    raise subprocess.CalledProcessError(gzip_returncode, ['gzip'])
                if split_process.returncode != 0:
                    raise subprocess.CalledProcessError(split_process.returncode, ['split'], stderr=split_stderr)
            else:
                # pg_dump | split
                dump_process = subprocess.Popen(
                    pg_dump_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )

                split_process = subprocess.Popen(
                    ['split', '-b', str(chunk_size_bytes), '-', str(backup_dir / prefix) + '_'],
                    stdin=dump_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                dump_process.stdout.close()

                split_stdout, split_stderr = split_process.communicate()
                dump_returncode = dump_process.wait()

                if dump_returncode != 0:
                    _, dump_stderr = dump_process.communicate()
                    raise subprocess.CalledProcessError(dump_returncode, pg_dump_cmd, stderr=dump_stderr)
                if split_process.returncode != 0:
                    raise subprocess.CalledProcessError(split_process.returncode, ['split'], stderr=split_stderr)

            progress.update(task, description="[green]Backup complete!")

        # List created files
        backup_files = sorted(backup_dir.glob(f'{prefix}_*'))
        console.print(f"\n[green]✓[/] Created {len(backup_files)} backup chunks:")
        total_size = 0
        for f in backup_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            total_size += f.stat().st_size
            console.print(f"  [dim]{f.name}[/] ({size_mb:.2f} MB)")

        console.print(f"\n[green]Total backup size:[/] {total_size / (1024 * 1024):.2f} MB")
        console.print(f"[green]Location:[/] {backup_dir.absolute()}")

        # Create restore instructions
        restore_cmd = f"lawbot db restore {backup_dir}"
        console.print(f"\n[yellow]To restore:[/] {restore_cmd}")

    except subprocess.CalledProcessError as e:
        console.print(f"\n[red]✗ Backup failed:[/] {e}")
        if e.stderr:
            console.print(f"[red]{e.stderr.decode()}[/]")
        raise click.Abort()
    except FileNotFoundError as e:
        console.print(f"\n[red]✗ Command not found:[/] {e.filename}")
        console.print("[yellow]Make sure PostgreSQL client tools are installed[/]")
        raise click.Abort()


def restore_database(backup_dir: Path, compressed: bool = True, console: Optional[Console] = None):
    """
    Restore the PostgreSQL database from chunked files.

    Args:
        backup_dir: Directory containing backup chunks
        compressed: Whether the backup is compressed (default True)
        console: Rich console for output
    """
    if console is None:
        console = Console()

    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        console.print(f"[red]✗ Backup directory not found:[/] {backup_dir}")
        raise click.Abort()

    # Find backup chunks
    prefix = 'db_dump.gz_' if compressed else 'db_dump_'
    backup_files = sorted(backup_dir.glob(f'{prefix}*'))

    if not backup_files:
        console.print(f"[red]✗ No backup files found in:[/] {backup_dir}")
        console.print(f"[yellow]Looking for files matching:[/] {prefix}*")
        raise click.Abort()

    creds = get_db_credentials()

    console.print(f"[cyan]Restoring database:[/] {creds['database']}")
    console.print(f"[cyan]From:[/] {backup_dir}")
    console.print(f"[cyan]Found {len(backup_files)} chunks[/]\n")

    # Confirm restoration
    console.print("[yellow]⚠ Warning: This will replace all data in the database![/]")
    if not click.confirm("Continue with restore?"):
        console.print("[dim]Restore cancelled[/]")
        return

    # Set PGPASSWORD environment variable
    env = os.environ.copy()
    env['PGPASSWORD'] = creds['password']

    # Build psql command
    psql_cmd = [
        'psql',
        '-h', creds['host'],
        '-p', creds['port'],
        '-U', creds['user'],
        '-d', creds['database'],
    ]

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Restoring database...", total=None)

            # Create the pipeline: cat chunks | (gunzip) | psql
            if compressed:
                # cat chunks | gunzip | psql
                cat_process = subprocess.Popen(
                    ['cat'] + [str(f) for f in backup_files],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                gunzip_process = subprocess.Popen(
                    ['gunzip'],
                    stdin=cat_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                cat_process.stdout.close()

                psql_process = subprocess.Popen(
                    psql_cmd,
                    stdin=gunzip_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )
                gunzip_process.stdout.close()

                # Wait for all processes
                psql_stdout, psql_stderr = psql_process.communicate()
                gunzip_returncode = gunzip_process.wait()
                cat_returncode = cat_process.wait()

                if cat_returncode != 0:
                    raise subprocess.CalledProcessError(cat_returncode, ['cat'])
                if gunzip_returncode != 0:
                    raise subprocess.CalledProcessError(gunzip_returncode, ['gunzip'])
                if psql_process.returncode != 0:
                    raise subprocess.CalledProcessError(psql_process.returncode, psql_cmd, stderr=psql_stderr)
            else:
                # cat chunks | psql
                cat_process = subprocess.Popen(
                    ['cat'] + [str(f) for f in backup_files],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                psql_process = subprocess.Popen(
                    psql_cmd,
                    stdin=cat_process.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env
                )
                cat_process.stdout.close()

                psql_stdout, psql_stderr = psql_process.communicate()
                cat_returncode = cat_process.wait()

                if cat_returncode != 0:
                    raise subprocess.CalledProcessError(cat_returncode, ['cat'])
                if psql_process.returncode != 0:
                    raise subprocess.CalledProcessError(psql_process.returncode, psql_cmd, stderr=psql_stderr)

            progress.update(task, description="[green]Restore complete!")

        console.print(f"\n[green]✓ Database restored successfully[/]")

    except subprocess.CalledProcessError as e:
        console.print(f"\n[red]✗ Restore failed:[/] {e}")
        if e.stderr:
            console.print(f"[red]{e.stderr.decode()}[/]")
        raise click.Abort()
    except FileNotFoundError as e:
        console.print(f"\n[red]✗ Command not found:[/] {e.filename}")
        console.print("[yellow]Make sure PostgreSQL client tools are installed[/]")
        raise click.Abort()
