"""
Smoke test for multi-pair support — proves two pairs can be tracked
independently in one cycle: shared basket fetch, per-pair position
guards (a position on EUR_USD doesn't block GBP_USD), and correct
Journal logging for both.

Run directly:

    python tests/test_multi_pair_smoke.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.data_engine import MockDataProvider, PairConfig, run_multi_pair_cycle
from atlas_trader.journal import get_connection, get_open_trades_for_pair, init_db
from atlas_trader.loop import run_one_cycle_multi
from atlas_trader.ml import OnlineTradeModel

PAIRS = [
    PairConfig("EUR_USD", "EUR", "USD"),
    PairConfig("GBP_USD", "GBP", "USD"),
]


def test_shared_basket_fetch_covers_both_pairs():
    provider = MockDataProvider(seed=1)
    results = run_multi_pair_cycle(provider, PAIRS, min_log_threshold=5.0, trade_threshold=5.0)

    assert set(results.keys()) == {"EUR_USD", "GBP_USD"}
    assert set(results["EUR_USD"]["currency_strength"].keys()) == {"EUR", "USD"}
    assert set(results["GBP_USD"]["currency_strength"].keys()) == {"GBP", "USD"}
    print("Shared basket fetch produced correct per-pair currency strength scores.")


def _find_seed_with_trades_on_both_pairs(max_seed: int = 100) -> int:
    """Find a seed where BOTH pairs independently clear the trade
    threshold, so we can test that they don't block each other."""
    for seed in range(1, max_seed):
        provider = MockDataProvider(seed=seed)
        results = run_multi_pair_cycle(provider, PAIRS, min_log_threshold=5.0, trade_threshold=5.0)
        if results["EUR_USD"]["voting"]["should_trade"] and results["GBP_USD"]["voting"]["should_trade"]:
            return seed
    raise AssertionError("No seed produced should_trade=True on both pairs simultaneously")


def test_independent_position_guards():
    seed = _find_seed_with_trades_on_both_pairs()
    print(f"Using seed {seed} (both pairs independently clear the trade threshold).")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "multi_pair_test.db"
        model_path = Path(tmp) / "model.json"
        init_db(db_path)
        conn = get_connection(db_path)
        model = OnlineTradeModel.load(model_path)
        provider = MockDataProvider(seed=seed)

        low_thresholds = {"min_log_threshold": 5.0, "trade_threshold": 5.0}

        # Cycle 1: both pairs should open independent trades
        run_one_cycle_multi(provider, conn, model, PAIRS, model_path=model_path, **low_thresholds)

        assert len(get_open_trades_for_pair(conn, "EUR_USD")) == 1, "EUR_USD should have an open trade"
        assert len(get_open_trades_for_pair(conn, "GBP_USD")) == 1, "GBP_USD should have an independent open trade"

        # Cycle 2: same seed -> same signals again, but each pair's own
        # guard should block a duplicate on THAT pair only
        run_one_cycle_multi(provider, conn, model, PAIRS, model_path=model_path, **low_thresholds)
        assert len(get_open_trades_for_pair(conn, "EUR_USD")) == 1, "Should not stack a duplicate EUR_USD position"
        assert len(get_open_trades_for_pair(conn, "GBP_USD")) == 1, "Should not stack a duplicate GBP_USD position"

        print("Both pairs held independent positions correctly, with per-pair duplicate guards working.")


if __name__ == "__main__":
    test_shared_basket_fetch_covers_both_pairs()
    test_independent_position_guards()
    print("Multi-pair smoke test passed.")
