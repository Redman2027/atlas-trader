#!/usr/bin/env python
"""
Diagnose why a backtest produced zero trades — looks at the actual
logged setups to see how close confidence got to the trade threshold,
and whether the trend veto ever fired.

Usage:
    python diagnose_backtest.py
"""

from __future__ import annotations

import json

from atlas_trader.journal import get_connection

DB_PATH = "data/backtest_atlas_trader.db"


def main() -> None:
    conn = get_connection(DB_PATH)
    rows = conn.execute(
        "SELECT confidence_score, feature_snapshot FROM setups ORDER BY confidence_score DESC LIMIT 10"
    ).fetchall()

    if not rows:
        print("No setups were logged at all — even the 40-point logging threshold was never cleared.")
        return

    print(f"Top {len(rows)} highest-confidence setups logged during the backtest:\n")
    for row in rows:
        snapshot = json.loads(row["feature_snapshot"])
        voting = snapshot["voting"]
        components = voting["components"]
        print(f"Confidence: {row['confidence_score']}  Direction: {voting['direction']}  Trend veto: {voting.get('trend_veto')}")
        for name, comp in components.items():
            print(f"    {name:<18} bias={comp['bias']:>7}  weight={comp['weight']}")
        print()

    all_scores = conn.execute("SELECT confidence_score FROM setups").fetchall()
    scores = [r["confidence_score"] for r in all_scores]
    print(f"Total setups logged: {len(scores)}")
    print(f"Max confidence seen: {max(scores)}")
    print(f"Min confidence seen (of those logged, i.e. >=40): {min(scores)}")
    print(f"Average confidence:  {sum(scores)/len(scores):.2f}")


if __name__ == "__main__":
    main()
