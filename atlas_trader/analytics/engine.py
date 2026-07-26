"""
Analytics Engine — reporting over the Journal.

Read-only: takes a journal DB connection (from
atlas_trader.journal.get_connection) and produces summary statistics.
Nothing here writes to the database — the Journal Engine owns writes.
"""

from __future__ import annotations

import json
import sqlite3


def _closed_trades_with_setups(conn: sqlite3.Connection) -> list[dict]:
    """Every closed trade, joined with its setup's confidence score and feature snapshot."""
    rows = conn.execute(
        """
        SELECT trades.*, setups.confidence_score, setups.pair, setups.timeframe,
               setups.feature_snapshot
        FROM trades
        JOIN setups ON trades.setup_id = setups.id
        WHERE trades.status = 'closed'
        """
    ).fetchall()
    results = []
    for row in rows:
        record = dict(row)
        record["feature_snapshot"] = json.loads(record["feature_snapshot"])
        results.append(record)
    return results


def compute_win_rate(closed_trades: list[dict]) -> dict:
    if not closed_trades:
        return {"total_closed": 0, "wins": 0, "losses": 0, "win_rate": None}
    wins = sum(1 for t in closed_trades if t["pnl"] is not None and t["pnl"] > 0)
    losses = sum(1 for t in closed_trades if t["pnl"] is not None and t["pnl"] <= 0)
    total = len(closed_trades)
    return {
        "total_closed": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total, 4) if total else None,
    }


def compute_confidence_vs_outcome(closed_trades: list[dict]) -> dict:
    """Average confidence score for winning vs. losing trades.

    If the Voting Engine's confidence score means anything, winning
    trades should show a higher average confidence than losing trades.
    This is the single most important sanity check for whether the
    whole system is actually working, not just running.
    """
    wins = [t["confidence_score"] for t in closed_trades if t["pnl"] is not None and t["pnl"] > 0]
    losses = [t["confidence_score"] for t in closed_trades if t["pnl"] is not None and t["pnl"] <= 0]
    return {
        "avg_confidence_wins": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_confidence_losses": round(sum(losses) / len(losses), 2) if losses else None,
        "sample_size_wins": len(wins),
        "sample_size_losses": len(losses),
    }


def compute_loss_cause_breakdown(closed_trades: list[dict]) -> dict:
    """How often each loss_cause (from the ML/Adaptation Layer) shows up among losses."""
    losses = [t for t in closed_trades if t["pnl"] is not None and t["pnl"] <= 0]
    breakdown: dict[str, int] = {}
    for t in losses:
        cause = t.get("loss_cause") or "unclassified"
        breakdown[cause] = breakdown.get(cause, 0) + 1
    return breakdown


def compute_pnl_summary(closed_trades: list[dict]) -> dict:
    pnls = [t["pnl"] for t in closed_trades if t["pnl"] is not None]
    if not pnls:
        return {"total_pnl": 0.0, "avg_pnl": None, "best_trade": None, "worst_trade": None}
    return {
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
    }


def generate_report(conn: sqlite3.Connection) -> dict:
    """Full analytics snapshot — everything at a glance.

    Safe to call at any time, including with an empty journal (every
    sub-function degrades gracefully to None/0 rather than erroring).
    """
    closed_trades = _closed_trades_with_setups(conn)

    total_setups = conn.execute("SELECT COUNT(*) FROM setups").fetchone()[0]
    total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    open_trades = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status = 'open'"
    ).fetchone()[0]

    return {
        "total_setups_logged": total_setups,
        "total_trades_opened": total_trades,
        "open_trades": open_trades,
        "win_rate": compute_win_rate(closed_trades),
        "confidence_vs_outcome": compute_confidence_vs_outcome(closed_trades),
        "loss_cause_breakdown": compute_loss_cause_breakdown(closed_trades),
        "pnl_summary": compute_pnl_summary(closed_trades),
    }
