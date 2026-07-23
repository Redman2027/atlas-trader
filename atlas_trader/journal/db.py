"""
SQLite connection and schema management for the AtlasTrader Journal Engine.

Run this module directly to initialize the database file:

    python -m atlas_trader.journal.db

Every other module (Voting/Confidence Engine, Risk Engine, ML/Adaptation
Layer, Analytics Engine) reads from or writes to this same database, so
this file defines the single source of truth for the schema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Default location: <repo_root>/data/atlas_trader.db
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "atlas_trader.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS setups (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT NOT NULL,
    pair              TEXT NOT NULL,
    timeframe         TEXT NOT NULL,
    direction         TEXT NOT NULL,
    confidence_score  REAL NOT NULL,
    traded            INTEGER NOT NULL DEFAULT 0,
    feature_snapshot  TEXT NOT NULL,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id          INTEGER NOT NULL REFERENCES setups(id),
    oanda_trade_id    TEXT,
    direction         TEXT NOT NULL,
    entry_price       REAL NOT NULL,
    stop_loss         REAL NOT NULL,
    take_profit       REAL NOT NULL,
    position_size     REAL NOT NULL,
    opened_at         TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'open',
    closed_at         TEXT,
    close_price       REAL,
    pnl               REAL,
    pnl_pct           REAL,
    outcome_grade     TEXT,
    loss_cause        TEXT
);

CREATE INDEX IF NOT EXISTS idx_setups_pair_created
    ON setups (pair, created_at);

CREATE INDEX IF NOT EXISTS idx_trades_status
    ON trades (status);
"""


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults, creating parent dirs."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create the journal tables if they don't already exist."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"AtlasTrader journal database initialized at: {DEFAULT_DB_PATH}")
