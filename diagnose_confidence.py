#!/usr/bin/env python
"""
Diagnose why confidence_score isn't predicting outcomes — breaks down
every individual component (not just the combined score) to see which
ones, if any, actually differ between wins and losses.

Usage:
    python diagnose_confidence.py
"""

from __future__ import annotations

import json

from atlas_trader.journal import get_connection

DB_PATH = "data/backtest_atlas_trader.db"


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def main() -> None:
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        """
        SELECT trades.pnl, trades.direction, setups.confidence_score, setups.feature_snapshot
        FROM trades
        JOIN setups ON trades.setup_id = setups.id
        WHERE trades.status = 'closed'
        """
    ).fetchall()

    if not rows:
        print("No closed trades found.")
        return

    wins = {"confidence": [], "macro": [], "currency_strength": [], "technical": [],
            "trend_4h": [], "trend_1d": [], "rsi_aligned": []}
    losses = {"confidence": [], "macro": [], "currency_strength": [], "technical": [],
              "trend_4h": [], "trend_1d": [], "rsi_aligned": []}

    for row in rows:
        pnl = row["pnl"] or 0.0
        direction = row["direction"]
        snapshot = json.loads(row["feature_snapshot"])
        voting = snapshot["voting"]
        components = voting["components"]
        rsi_value = snapshot["technical"]["rsi"]["value"]

        # "rsi_aligned": for a long, how far ABOVE 50 was RSI (continuation
        # bet); for a short, how far BELOW 50. Positive = RSI agreed with
        # the trade direction the way the current formula assumes.
        rsi_aligned = None
        if rsi_value is not None:
            rsi_aligned = (rsi_value - 50) if direction == "long" else (50 - rsi_value)

        bucket = wins if pnl > 0 else losses
        bucket["confidence"].append(row["confidence_score"])
        bucket["macro"].append(components["macro"]["bias"])
        bucket["currency_strength"].append(components["currency_strength"]["bias"])
        bucket["technical"].append(components["technical"]["bias"])
        bucket["trend_4h"].append(components.get("trend_4h", {}).get("bias"))
        bucket["trend_1d"].append(components.get("trend_1d", {}).get("bias"))
        bucket["rsi_aligned"].append(rsi_aligned)

    print(f"Wins: {len(wins['confidence'])}   Losses: {len(losses['confidence'])}\n")
    print(f"{'Metric':<20} {'Avg (Wins)':>12} {'Avg (Losses)':>14} {'Difference':>12}")
    for key in ["confidence", "macro", "currency_strength", "technical", "trend_4h", "trend_1d", "rsi_aligned"]:
        w = _avg(wins[key])
        l = _avg(losses[key])
        diff = round(w - l, 2) if (w is not None and l is not None) else None
        print(f"{key:<20} {str(w):>12} {str(l):>14} {str(diff):>12}")

    print(
        "\nNote: for macro/currency_strength/technical/trend components, these are "
        "SIGNED biases (not direction-adjusted) — a real difference here means one "
        "direction of that signal is more reliable than the other, which is itself "
        "useful to know. 'rsi_aligned' IS direction-adjusted: positive means RSI was "
        "on the same side as the trade (continuation), negative means RSI was against "
        "it (the trade went the opposite way RSI would suggest under classic "
        "overbought/oversold logic)."
    )


if __name__ == "__main__":
    main()
