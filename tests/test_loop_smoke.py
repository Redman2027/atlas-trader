"""
Smoke test for the AtlasTrader loop.

Run directly:

    python tests/test_loop_smoke.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.journal import init_db, get_connection, get_open_trades
from atlas_trader.ml import OnlineTradeModel
from atlas_trader.data_engine import MockDataProvider
from atlas_trader.loop import is_market_open, run_one_cycle


def _next_weekday(start: datetime, target_weekday: int) -> datetime:
    days_ahead = (target_weekday - start.weekday()) % 7
    return start + timedelta(days=days_ahead)


def test_is_market_open():
    base = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)  # arbitrary anchor

    saturday = _next_weekday(base, 5).replace(hour=12)
    assert is_market_open(saturday) is False

    wednesday = _next_weekday(base, 2).replace(hour=12)
    assert is_market_open(wednesday) is True

    friday_late = _next_weekday(base, 4).replace(hour=23)
    assert is_market_open(friday_late) is False

    sunday_early = _next_weekday(base, 6).replace(hour=10)
    assert is_market_open(sunday_early) is False

    sunday_late = _next_weekday(base, 6).replace(hour=23)
    assert is_market_open(sunday_late) is True

    print("Market hours checks passed.")


def test_full_cycle_open_skip_close_learn():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "loop_test.db"
        model_path = Path(tmp) / "model.json"
        init_db(db_path)
        conn = get_connection(db_path)
        model = OnlineTradeModel.load(model_path)
        provider = MockDataProvider(seed=1)

        # Deliberately low thresholds so this test doesn't depend on
        # finding a lucky seed — also proves the thresholds are
        # legitimately configurable per call, not hardcoded.
        low_thresholds = {"min_log_threshold": 5.0, "trade_threshold": 5.0}

        # Cycle 1: should open a new trade
        result = run_one_cycle(provider, conn, model, model_path=model_path, **low_thresholds)
        assert result["voting"]["should_trade"] is True
        assert len(get_open_trades(conn)) == 1

        # Cycle 2: same seed -> same signal again, but the open-position
        # guard should prevent a second trade from stacking on top
        run_one_cycle(provider, conn, model, model_path=model_path, **low_thresholds)
        assert len(get_open_trades(conn)) == 1, "Should not open a duplicate position"

        # Cycle 3: mock's get_trade_status reports 'closed' on the 2nd check.
        # The old trade closes, which frees the position guard — and since
        # the same seed still produces a should_trade signal, a brand new
        # trade correctly opens in this same cycle. That's the intended
        # behavior, not a bug.
        run_one_cycle(provider, conn, model, model_path=model_path, **low_thresholds)
        assert model.trades_seen == 1, "ML model should have learned from the closed trade"
        assert len(get_open_trades(conn)) == 1, "A new trade should have opened right after the old one closed"

        print("Full open -> skip-duplicate -> close -> learn cycle passed.")


if __name__ == "__main__":
    test_is_market_open()
    test_full_cycle_open_skip_close_learn()
    print("Loop smoke test passed.")
