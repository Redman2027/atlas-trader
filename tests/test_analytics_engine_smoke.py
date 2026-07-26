"""
Smoke test for the Analytics Engine.

Run directly:

    python tests/test_analytics_engine_smoke.py

Builds a small journal with known, hand-picked outcomes in a temp
database, then checks generate_report() computes the exact numbers we
expect from that data.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.journal import Setup, Trade, get_connection, init_db, log_setup, open_trade, close_trade
from atlas_trader.analytics import generate_report


def _add_closed_trade(conn, confidence_score, pnl, outcome_grade, loss_cause=None):
    setup = Setup(
        pair="EUR_USD",
        timeframe="5M",
        direction="long",
        confidence_score=confidence_score,
        feature_snapshot={"note": "synthetic test data"},
        traded=True,
    )
    setup_id = log_setup(conn, setup)

    trade = Trade(
        setup_id=setup_id,
        direction="long",
        entry_price=1.0850,
        stop_loss=1.0830,
        take_profit=1.0890,
        position_size=1000.0,
    )
    trade_id = open_trade(conn, trade)

    close_trade(
        conn,
        trade_id=trade_id,
        close_price=1.0850 + (0.001 if pnl > 0 else -0.001),
        pnl=pnl,
        pnl_pct=pnl / 1000,
        outcome_grade=outcome_grade,
        loss_cause=loss_cause,
    )


def run():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_analytics.db"
        init_db(db_path)
        conn = get_connection(db_path)

        # 3 wins (high confidence), 2 losses (lower confidence, different causes)
        _add_closed_trade(conn, confidence_score=80, pnl=50.0, outcome_grade="A")
        _add_closed_trade(conn, confidence_score=75, pnl=40.0, outcome_grade="A")
        _add_closed_trade(conn, confidence_score=70, pnl=30.0, outcome_grade="B")
        _add_closed_trade(conn, confidence_score=45, pnl=-20.0, outcome_grade="F", loss_cause="technical_misread")
        _add_closed_trade(conn, confidence_score=42, pnl=-25.0, outcome_grade="F", loss_cause="macro_misread")

        report = generate_report(conn)
        print("Analytics report:", report)

        assert report["total_setups_logged"] == 5
        assert report["total_trades_opened"] == 5
        assert report["open_trades"] == 0

        assert report["win_rate"]["total_closed"] == 5
        assert report["win_rate"]["wins"] == 3
        assert report["win_rate"]["losses"] == 2
        assert report["win_rate"]["win_rate"] == 0.6

        # Wins should show a clearly higher average confidence than losses
        conf = report["confidence_vs_outcome"]
        assert conf["avg_confidence_wins"] > conf["avg_confidence_losses"]

        breakdown = report["loss_cause_breakdown"]
        assert breakdown == {"technical_misread": 1, "macro_misread": 1}

        pnl_summary = report["pnl_summary"]
        assert pnl_summary["total_pnl"] == 75.0  # 50+40+30-20-25
        assert pnl_summary["best_trade"] == 50.0
        assert pnl_summary["worst_trade"] == -25.0

        conn.close()

    print("Analytics Engine smoke test passed.")


if __name__ == "__main__":
    run()
