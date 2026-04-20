# db/migrate.py
# =============================================================================
# Database migration runner
# =============================================================================
#
# Applies pending SQL migration files from db/migrations/ in filename order.
# Tracks which migrations have been applied in a schema_migrations table
# so each migration is run exactly once per database.
#
# HOW TO RUN
# ----------
# From the project root:
#
#   python -m db.migrate --settings config/settings.yaml
#
# SAFE TO RE-RUN
# --------------
# Re-running against a database that is already up to date prints
# "No pending migrations." and exits cleanly.
#
# MIGRATION FILE CONVENTIONS
# --------------------------
# Files must:
#   - live in db/migrations/
#   - end in .sql
#   - be named with a numeric prefix for ordering (e.g. 001_..., 002_...)
#   - be idempotent where possible (ALTER TABLE ... ADD COLUMN is not inherently
#     idempotent, but the runner swallows "duplicate column name" errors safely)
#
# RELATIONSHIP TO schema.sql
# --------------------------
# schema.sql is the canonical definition for NEW databases (via init_schema).
# Migrations are for EXISTING databases that pre-date a schema.sql change.
#
# When you add columns to schema.sql, also add a migration file so existing
# databases can be updated without recreating them.
#
# =============================================================================

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'migrations')


# =============================================================================
# Internal helpers
# =============================================================================

def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    """Create the schema_migrations tracking table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_name  TEXT     PRIMARY KEY,
            applied_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _applied_migrations(conn: sqlite3.Connection) -> set:
    """Return the set of migration filenames that have already been applied."""
    rows = conn.execute(
        "SELECT migration_name FROM schema_migrations"
    ).fetchall()
    return {row['migration_name'] for row in rows}


def _mark_applied(conn: sqlite3.Connection, migration_name: str) -> None:
    """Record that a migration has been successfully applied."""
    conn.execute(
        "INSERT INTO schema_migrations (migration_name) VALUES (?)",
        (migration_name,)
    )
    conn.commit()


def _execute_migration(conn: sqlite3.Connection, sql: str) -> None:
    """
    Execute each statement in a migration file individually.

    Statements are split on ';' and executed one at a time.
    "Duplicate column name" errors are swallowed with a debug log — this
    makes re-running a migration against an already-migrated database safe.
    All other errors propagate and abort the migration.
    """
    statements = [s.strip() for s in sql.split(';') if s.strip()]
    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as exc:
            if 'duplicate column name' in str(exc).lower():
                logger.debug("Column already exists (skipping): %s", exc)
            else:
                raise
    conn.commit()


# =============================================================================
# Public API
# =============================================================================

def run_migrations(conn: sqlite3.Connection) -> list:
    """
    Apply all pending migrations from db/migrations/ in filename order.

    Safe to call on any database at any time:
      - New database: schema.sql already includes all columns; ALTER TABLE
        statements fail silently with "duplicate column name" and are skipped.
      - Existing pre-migration database: columns are added successfully.
      - Already-migrated database: no migrations are pending; returns [].

    Args:
        conn: active database connection (row_factory should be set to sqlite3.Row)

    Returns:
        list of migration filenames that were applied in this call.
        Empty list if nothing was pending.
    """
    _ensure_migrations_table(conn)
    applied = _applied_migrations(conn)

    if not os.path.isdir(_MIGRATIONS_DIR):
        logger.info("No migrations directory found at %s — nothing to apply.", _MIGRATIONS_DIR)
        return []

    migration_files = sorted(
        f for f in os.listdir(_MIGRATIONS_DIR)
        if f.endswith('.sql')
    )

    newly_applied = []
    for filename in migration_files:
        if filename in applied:
            logger.debug("Already applied: %s", filename)
            continue

        filepath = os.path.join(_MIGRATIONS_DIR, filename)
        with open(filepath, 'r') as fh:
            sql = fh.read()

        logger.info("Applying migration: %s", filename)
        try:
            _execute_migration(conn, sql)
            _mark_applied(conn, filename)
            newly_applied.append(filename)
            logger.info("Migration applied: %s", filename)
        except Exception as exc:
            logger.error("Migration FAILED: %s — %s", filename, exc)
            raise

    if not newly_applied:
        logger.info("All migrations are up to date.")

    return newly_applied


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == '__main__':
    import argparse
    import yaml
    from db.connection import get_connection, init_schema

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    parser = argparse.ArgumentParser(
        description='NRL Pricing Engine — Database Migration Runner'
    )
    parser.add_argument(
        '--settings',
        default='config/settings.yaml',
        help='Path to settings.yaml (default: config/settings.yaml)',
    )
    args = parser.parse_args()

    with open(args.settings, 'r') as fh:
        settings = yaml.safe_load(fh)

    conn = get_connection(settings)
    init_schema(conn)

    applied = run_migrations(conn)

    if applied:
        print(f"Applied {len(applied)} migration(s):")
        for name in applied:
            print(f"  {name}")
    else:
        print("No pending migrations — database is up to date.")

    conn.close()
