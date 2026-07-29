#!/usr/bin/env python
"""
Buckets every closed trade by signal strength (technical bias magnitude,
and confidence score) into terciles, and shows the win rate in each
bucket. This is the direct test of "does a stronger signal actually
predict a better outcome, or the opposite?"

Usage:
    python diagnose_signal_buckets.py
"""

from __future__ import annotations

import json

from atlas_trader.journal import get_connection

DB_PATH = "data/backtest_atlas_trader.db"


def bucket_and_report(label: str, values_with_outcomes: list[tuple[float, bool]]) -> None:
    """values_with_outcomes: list of (metric_value, won) tuples."""
    sorted_by_value = sorted(values_with_outcomes, key=lambda x: x[0])
    n = len(sorted_by_value)
    third = n // 3

    buckets = {
        "Low (bottom third)": sorted_by_value[:third],
        "Medium (middle third)": sorted_by_value[third: 2 * third if 2 * third < n else n],
        "High (top third)": sorted_by_value[2 * third:],
    }

    print(f"\n--- {label} ---")
    for bucket_name, items in buckets.items():
        if not items:
            continue
        wins = sum(1 for _, won in items if won)
        total = len(items)
        avg_value = sum(v for v, _ in items) / total
        win_rate = wins / total if total else None
        print(f"  {bucket_name:<22} n={total:<4} avg_value={avg_value:>7.2f}  win_rate={win_rate:.3f}")


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

    confidence_data = []
    technical_abs_data = []
    trend_4h_abs_data = []
    trend_1d_abs_data = []
    currency_strength_abs_data = []

    for row in rows:
        won = (row["pnl"] or 0.0) > 0
        snapshot = json.loads(row["feature_snapshot"])
        components = snapshot["voting"]["components"]

        confidence_data.append((row["confidence_score"], won))
        technical_abs_data.append((abs(components["technical"]["bias"]), won))
        trend_4h_abs_data.append((abs(components.get("trend_4h", {}).get("bias", 0)), won))
        trend_1d_abs_data.append((abs(components.get("trend_1d", {}).get("bias", 0)), won))
        currency_strength_abs_data.append((abs(components["currency_strength"]["bias"]), won))

    print(f"Total closed trades: {len(rows)}")
    bucket_and_report("Confidence score", confidence_data)
    bucket_and_report("Technical bias (magnitude)", technical_abs_data)
    bucket_and_report("Trend 4H bias (magnitude)", trend_4h_abs_data)
    bucket_and_report("Trend 1D bias (magnitude)", trend_1d_abs_data)
    bucket_and_report("Currency Strength bias (magnitude)", currency_strength_abs_data)

    print(
        "\nIf win_rate decreases from 'Low' to 'High' consistently across "
        "these, that confirms strong signals are predicting WORSE outcomes "
        "here, not better ones."
    )


if __name__ == "__main__":
    main()
