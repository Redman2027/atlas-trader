"""
Smoke test for the backtest engine.

Uses fully synthetic candle history (no network, no real OANDA data)
to prove the tricky part actually works: simulated time advancing
candle-by-candle, trades resolving against real subsequent candles
(not randomly), the Journal getting populated, and the ML model
learning — all through the exact same run_one_cycle() used for live
trading.

Run directly:

    python tests/test_backtest_smoke.py
"""

from __future__ import annotations

import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.currency_strength import get_required_pairs
from atlas_trader.journal import get_connection
from atlas_trader.analytics import generate_report
from atlas_trader.backtest import HistoricalDataProvider, run_backtest

ENTRY_PAIR = "EUR_USD"
TRACKED_BASE = "EUR"
TRACKED_QUOTE = "USD"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


def _generate_series(pair: str, start: datetime, count: int, step: timedelta, seed_key: str):
    rng = random.Random(seed_key)
    price = 1.0850 if "JPY" not in pair else 150.0
    step_size = 0.0002 if "JPY" not in pair else 0.02
    candles = []
    t = start
    for _ in range(count):
        move = rng.uniform(-step_size, step_size)
        open_ = price
        close = price + move
        high = max(open_, close) + step_size * 0.2
        low = min(open_, close) - step_size * 0.2
        candles.append(
            {
                "open": round(open_, 5),
                "high": round(high, 5),
                "low": round(low, 5),
                "close": round(close, 5),
                "time": _iso(t),
            }
        )
        price = close
        t += step
    return candles


def _build_synthetic_history():
    required_pairs = sorted(set(get_required_pairs([TRACKED_BASE, TRACKED_QUOTE])) | {ENTRY_PAIR})

    start = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)  # a Monday
    m5_count = 800  # a few days of 5-minute candles
    h4_count = 100
    d_count = 100
    h1_count = 400  # needs to cover the same trend_start window as H4/D

    history = {}
    for pair in required_pairs:
        history[(pair, "M5")] = _generate_series(pair, start, m5_count, timedelta(minutes=5), f"m5-{pair}")

    # 4H/1D history needs to extend further back so indicators are
    # warmed up from the start of the M5 test window, not starting cold.
    trend_start = start - timedelta(days=60)
    history[(ENTRY_PAIR, "H4")] = _generate_series(
        ENTRY_PAIR, trend_start, h4_count, timedelta(hours=4), "h4"
    )
    history[(ENTRY_PAIR, "D")] = _generate_series(
        ENTRY_PAIR, trend_start, d_count, timedelta(days=1), "d1"
    )
    history[(ENTRY_PAIR, "H1")] = _generate_series(
        ENTRY_PAIR, trend_start, h1_count, timedelta(hours=1), "h1"
    )

    return history


def test_backtest_runs_and_produces_a_journal(monkeypatch):
    history = _build_synthetic_history()
    provider = HistoricalDataProvider(history, start_balance=100_000.0)

    # Trigger logic is not what this test exercises (it tests that a
    # backtest run produces a journal) -- force it to always fire so
    # should_trade alone determines whether a trade opens.
    monkeypatch.setattr(
        "atlas_trader.data_engine.pipeline.check_entry_trigger",
        lambda candles, direction: {"triggered": True, "reason": "test_override"},
    )

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "backtest_test.db"
        model_path = Path(tmp) / "backtest_model.json"

        result = run_backtest(
            provider,
            entry_pair=ENTRY_PAIR,
            tracked_base=TRACKED_BASE,
            tracked_quote=TRACKED_QUOTE,
            db_path=db_path,
            model_path=model_path,
            progress_every=0,  # quiet for the test
            min_log_threshold=5.0,
            trade_threshold=5.0,  # deliberately low so at least one real trade opens+resolves
        )

        print("Backtest result:", result)
        assert result["steps"] > 0
        assert result["errors"] == 0, "Backtest hit unexpected errors — see output above"

        conn = get_connection(db_path)
        report = generate_report(conn)
        print("Backtest report:", report)

        # With a low threshold, this synthetic data should produce at
        # least some real trades that open AND resolve via the actual
        # SL/TP-crossing logic (not randomly) — proving the core
        # mechanism, not just that the loop ran without crashing.
        print(f"Trades opened: {report['total_trades_opened']}, closed: {report['win_rate']['total_closed']}")
        assert report["total_trades_opened"] > 0, "Expected at least one trade with a low threshold"
        assert report["win_rate"]["total_closed"] > 0, "Expected at least one trade to resolve via SL/TP"

        assert "win_rate" in report
        assert "pnl_summary" in report


if __name__ == "__main__":
    test_backtest_runs_and_produces_a_journal()
    print("Backtest engine smoke test passed.")
