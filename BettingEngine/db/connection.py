# db/connection.py
# Database connection management.
# Supports SQLite in V1; designed to extend to PostgreSQL.

import os
import sqlite3


def get_connection(settings: dict) -> sqlite3.Connection:
    """
    Return a SQLite database connection.

    Creates the database file and any missing parent directories automatically.
    row_factory is set to sqlite3.Row so columns can be accessed by name.

    Args:
        settings: parsed settings.yaml dict

    Returns:
        sqlite3.Connection with foreign keys enabled and row_factory set.
    """
    db_path = settings['database']['path']
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """
    Execute schema.sql against the connection to initialise all tables and indexes.

    Safe to run multiple times — all DDL uses CREATE TABLE IF NOT EXISTS.

    Args:
        conn: active SQLite connection
    """
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    with open(schema_path, 'r') as f:
        sql = f.read()
    conn.executescript(sql)
