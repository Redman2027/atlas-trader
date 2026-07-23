"""
Data models for the AtlasTrader Journal Engine.

Two core record types:

- Setup: any trade opportunity scored by the Voting/Confidence Engine,
  whether or not it was ultimately traded. This is what makes the
  system explainable — every decision (and every non-decision) leaves
  a trace.
- Trade: the actual execution record for a Setup that was traded,
  including its eventual outcome once closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Setup:
    """A scored trade opportunity, traded or not.

    `feature_snapshot` holds the raw output of every module that fed
    into the confidence score (macro bias, currency strength, technical
    readings, candlestick pattern, ATR, etc.) as a plain dict, so the
    decision can always be explained after the fact.
    """

    pair: str
    timeframe: str
    direction: str  # "long", "short", or "none"
    confidence_score: float
    feature_snapshot: dict[str, Any]
    traded: bool = False
    id: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)
    notes: Optional[str] = None


@dataclass
class Trade:
    """An actual executed trade tied back to a Setup."""

    setup_id: int
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    id: Optional[int] = None
    oanda_trade_id: Optional[str] = None
    opened_at: str = field(default_factory=utc_now_iso)
    status: str = "open"  # "open" or "closed"
    closed_at: Optional[str] = None
    close_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    outcome_grade: Optional[str] = None
    loss_cause: Optional[str] = None
