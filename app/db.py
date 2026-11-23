import sqlite3
from datetime import datetime, timezone

DB_PATH = "privacylab.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','analyst','viewer'))
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        username TEXT,
        action TEXT NOT NULL,
        outcome TEXT NOT NULL,
        detail TEXT
    );
    CREATE TABLE IF NOT EXISTS datasets (
        id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        filename TEXT NOT NULL,
        row_count INTEGER NOT NULL,
        columns TEXT NOT NULL,
        bounds TEXT NOT NULL,
        epsilon_budget REAL NOT NULL DEFAULT 5.0,
        epsilon_spent REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS queries (
        id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL,
        username TEXT NOT NULL,
        query_hash TEXT NOT NULL,
        spec TEXT NOT NULL,
        epsilon REAL NOT NULL,
        mechanism TEXT NOT NULL,
        result TEXT NOT NULL,
        evidence TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(dataset_id, query_hash)
    );
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_by TEXT,
        updated_at TEXT
    );
    """)
    conn.commit()
    conn.close()


def log_event(username, action, outcome, detail=""):
    """Append-only audit log. Never pass passwords or raw data here."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (timestamp, username, action, outcome, detail) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), username, action, outcome, detail),
    )
    conn.commit()
    conn.close()