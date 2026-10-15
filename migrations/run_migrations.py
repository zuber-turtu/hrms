#!/usr/bin/env python3
"""
Enterprise Database Migration Runner for HRMS
Supports MySQL (Production), PostgreSQL, and SQLite (Local Development).
Tracks applied migrations in the `schema_migrations` table for idempotency.
"""

import sys
import os
import argparse
import importlib.util
from datetime import datetime, timezone

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text, inspect
from app.config import settings
from app.database import engine


def init_migrations_table(connection):
    """Ensure the schema_migrations tracking table exists."""
    dialect = connection.dialect.name
    if dialect == "mysql":
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    elif dialect == "postgresql":
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    else:  # SQLite and fallbacks
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    connection.execute(text(sql))


def get_applied_migrations(connection) -> set:
    """Returns a set of version identifiers already applied."""
    try:
        result = connection.execute(text("SELECT version FROM schema_migrations ORDER BY version ASC"))
        return {row[0] for row in result.fetchall()}
    except Exception:
        return set()


def load_migration_modules():
    """Discovers and imports all migration scripts in migrations/versions/ ordered by filename."""
    versions_dir = os.path.join(os.path.dirname(__file__), "versions")
    if not os.path.exists(versions_dir):
        os.makedirs(versions_dir, exist_ok=True)
        return []

    files = [f for f in os.listdir(versions_dir) if f.endswith(".py") and not f.startswith("__")]
    files.sort()

    migrations = []
    for filename in files:
        version = filename.split("_")[0]
        filepath = os.path.join(versions_dir, filename)
        module_name = f"migration_{filename[:-3]}"

        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            migrations.append({
                "version": version,
                "name": filename[:-3],
                "filename": filename,
                "module": mod,
            })
    return migrations


def show_status():
    """Prints the status of all discovered migrations."""
    migrations = load_migration_modules()
    with engine.connect() as conn:
        init_migrations_table(conn)
        applied = get_applied_migrations(conn)

    print("\n========================================================")
    print("  HRMS DATABASE MIGRATION STATUS")
    print(f" Database Dialect : {engine.dialect.name.upper()}")
    print(f" Target Database  : {getattr(settings, 'DB_NAME', 'Configured Engine')}")
    print("========================================================")
    if not migrations:
        print(" No migration versions found in migrations/versions/.")
        return

    for m in migrations:
        status_icon = "[APPLIED]" if m["version"] in applied else "[PENDING]"
        print(f" {status_icon:<10} {m['name']} ({m['filename']})")
    print("========================================================\n")


def run_migrations(dry_run=False):
    """Executes all pending migrations in sequential order."""
    migrations = load_migration_modules()
    if not migrations:
        print("[Migrations] No migration versions found.")
        return 0

    with engine.connect() as conn:
        init_migrations_table(conn)
        conn.commit()
        applied = get_applied_migrations(conn)

    pending = [m for m in migrations if m["version"] not in applied]

    if not pending:
        print(f"[Migrations] Database is fully up to date ({len(applied)} migrations applied).")
        return 0

    print(f"\n[Migrations] Found {len(pending)} pending migration(s) for dialect '{engine.dialect.name}':")
    for m in pending:
        print(f"  -> {m['name']}")

    if dry_run:
        print("\n[Dry Run] No migrations were executed.")
        return 0

    for m in pending:
        print(f"\n[Migrations] Running {m['name']} ...")
        start_time = datetime.now()
        with engine.begin() as conn:
            # Execute upgrade
            if hasattr(m["module"], "upgrade"):
                m["module"].upgrade(conn)
            else:
                raise AttributeError(f"Migration {m['filename']} has no upgrade(conn) function.")

            # Record migration
            conn.execute(
                text("INSERT INTO schema_migrations (version, name, applied_at) VALUES (:version, :name, :applied_at)"),
                {"version": m["version"], "name": m["name"], "applied_at": datetime.now(timezone.utc)}
            )
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[Migrations] [+] Successfully applied {m['name']} in {elapsed:.3f}s")

    print("\n[Migrations] All migrations completed successfully!\n")
    return 0


def main():
    parser = argparse.ArgumentParser(description="HRMS Database Migration Runner")
    parser.add_argument("--status", action="store_true", help="Show migration status and history")
    parser.add_argument("--dry-run", action="store_true", help="Preview pending migrations without applying")
    args = parser.parse_args()

    if args.status:
        show_status()
        sys.exit(0)

    try:
        exit_code = run_migrations(dry_run=args.dry_run)
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n[Migrations Error] ❌ Migration failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
