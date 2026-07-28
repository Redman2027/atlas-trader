"""
Repository functions for reading and writing AtlasTrader journal records.

This module intentionally contains no trading logic — it only knows how
to persist and retrieve Setups and Trades. The Voting/Confidence Engine
decides *whether* something gets logged; this module just logs it.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

from .models import Trade, Setup, utc_now_iso


def log_setup(conn: sqlite3.Connection, setup: Setup) -> int:
    """Insert a scored setup and return its new row id.

    Called by the Voting/Confidence Engine for every opportunity that
    clears the minimum confidence threshold — whether or not it is
    ultimately traded.
    """
    cursor = conn.execute(
        """
        INSERT INTO setups
            (created_at, pair, timeframe, direction, confidence_score,
             traded, feature_snapshot, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            setup.created_at,
            setup.pair,
            setup.timeframe,
            setup.direction,
            setup.confidence_score,
            int(setup.traded),
            json.dumps(setup.feature_snapshot),
            setup.notes,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def mark_setup_traded(conn: sqlite3.Connection, setup_id: int) -> None:
    """Flip a setup's `traded` flag once a Trade is opened against it."""
    conn.execute("UPDATE setups SET traded = 1 WHERE id = ?", (setup_id,))
    conn.commit()


def open_trade(conn: sqlite3.Connection, trade: Trade) -> int:
    """Insert a newly-opened trade tied to a setup, and mark that setup traded."""
    cursor = conn.execute(
        """
        INSERT INTO trades
            (setup_id, oanda_trade_id, direction, entry_price, stop_loss,
             take_profit, position_size, opened_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            trade.setup_id,
            trade.oanda_trade_id,
            trade.direction,
            trade.entry_price,
            trade.stop_loss,
            trade.take_profit,
            trade.position_size,
            trade.opened_at,
        ),
    )
    conn.commit()
    mark_setup_traded(conn, trade.setup_id)
    return cursor.lastrowid


def close_trade(
    conn: sqlite3.Connection,
    trade_id: int,
    close_price: float,
    pnl: float,
    pnl_pct: float,
    outcome_grade: str,
    loss_cause: Optional[str] = None,
) -> None:
    """Record the outcome of a closed trade.

    `loss_cause` is left None for winning trades; the ML/Adaptation
    layer populates it on losses by comparing the linked setup's
    feature snapshot against what actually happened.
    """
    conn.execute(
        """
        UPDATE trades
        SET status = 'closed',
            closed_at = ?,
            close_price = ?,
            pnl = ?,
            pnl_pct = ?,
            outcome_grade = ?,
            loss_cause = ?
        WHERE id = ?
        """,
        (utc_now_iso(), close_price, pnl, pnl_pct, outcome_grade, loss_cause, trade_id),
    )
    conn.commit()


def get_open_trades(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all trades currently open, across every pair."""
    return conn.execute("SELECT * FROM trades WHERE status = 'open'").fetchall()


def get_open_trades_for_pair(conn: sqlite3.Connection, pair: str) -> list[sqlite3.Row]:
    """Return open trades for one specific pair only.

    `trades` doesn't store the pair directly (only `setups` does), so
    this joins through to filter — needed for the multi-pair position
    guard: being long EUR_USD shouldn't block opening a position on
    GBP_USD, since they're independent instruments.
    """
    return conn.execute(
        """
        SELECT trades.*
        FROM trades
        JOIN setups ON trades.setup_id = setups.id
        WHERE trades.status = 'open' AND setups.pair = ?
        """,
        (pair,),
    ).fetchall()


def get_setup_with_trade(conn: sqlite3.Connection, setup_id: int) -> dict[str, Any]:
    """Fetch a setup and its linked trade (if any) as a combined dict."""
    setup_row = conn.execute(
        "SELECT * FROM setups WHERE id = ?", (setup_id,)
    ).fetchone()
    if setup_row is None:
        raise ValueError(f"No setup found with id={setup_id}")

    trade_row = conn.execute(
        "SELECT * FROM trades WHERE setup_id = ?", (setup_id,)
    ).fetchone()

    result = dict(setup_row)
    result["feature_snapshot"] = json.loads(result["feature_snapshot"])
    result["trade"] = dict(trade_row) if trade_row else None
    return result
