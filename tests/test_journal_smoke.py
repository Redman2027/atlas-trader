"""
Smoke test for the Journal Engine.

Run directly once you're set up on the PC:

    python tests/test_journal_smoke.py

Uses a throwaway in-memory-style temp file (not the real data/atlas_trader.db)
so running this never touches your live journal. Exercises the full
lifecycle: log a scored setup -> open a trade against it -> close the
trade -> read it back.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Allow running this file directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.journal import (
    Setup,
    Trade,
    get_connection,
    init_db,
    log_setup,
    open_trade,
    close_trade,
    get_setup_with_trade,
)


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_atlas_trader.db"
        init_db(db_path)
        conn = get_connection(db_path)

        # 1. Log a scored setup (as the Voting/Confidence Engine would)
        setup = Setup(
            pair="EUR_USD",
            timeframe="5M",
            direction="long",
            confidence_score=78.5,
            feature_snapshot={
                "macro_bias": "USD_hawkish_EUR_hawkish_neutral_net",
                "currency_strength": {"EUR": 62, "USD": 58},
                "technical": {
                    "ema_trend": "up",
                    "rsi": 61.2,
                    "macd": "bullish_cross",
                    "atr": 0.00072,
                    "pattern": "bullish_engulfing",
                },
            },
            traded=True,
        )
        setup_id = log_setup(conn, setup)
        assert setup_id is not None, "log_setup should return a row id"

        # 2. Open a trade against that setup
        trade = Trade(
            setup_id=setup_id,
            direction="long",
            entry_price=1.0850,
            stop_loss=1.0830,
            take_profit=1.0890,
            position_size=2000.0,
        )
        trade_id = open_trade(conn, trade)
        assert trade_id is not None, "open_trade should return a row id"

        # 3. Close the trade as a winner
        close_trade(
            conn,
            trade_id=trade_id,
            close_price=1.0890,
            pnl=80.0,
            pnl_pct=0.037,
            outcome_grade="A",
            loss_cause=None,
        )

        # 4. Read it back and check everything round-tripped correctly
        record = get_setup_with_trade(conn, setup_id)
        assert record["pair"] == "EUR_USD"
        assert record["feature_snapshot"]["technical"]["pattern"] == "bullish_engulfing"
        assert record["trade"] is not None
        assert record["trade"]["status"] == "closed"
        assert record["trade"]["outcome_grade"] == "A"
        assert record["trade"]["loss_cause"] is None

        conn.close()

    print("Journal Engine smoke test passed: setup -> trade -> close -> read, all good.")


if __name__ == "__main__":
    run()
