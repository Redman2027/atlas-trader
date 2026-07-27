#!/usr/bin/env python
"""
Run a backtest against real historical OANDA data.

Usage:
    python backtest.py

First run will download and cache several months of 5-minute, 4-hour,
and daily candles for EUR_USD and every pair the Currency Strength
Matrix needs — this can take a while (OANDA paginates in chunks of up
to 5000 candles per request). Subsequent runs reuse the cache
(data/historical/) instantly unless you delete those files.

Uses a SEPARATE database and ML model file from live trading
(data/backtest_atlas_trader.db, data/backtest_ml_model.json) so this
never touches your real Journal or the model your live trading learns
from.
"""

from __future__ import annotations

from atlas_trader.analytics import generate_report
from atlas_trader.backtest import HistoricalDataProvider, fetch_and_cache, run_backtest
from atlas_trader.currency_strength import get_required_pairs
from atlas_trader.journal import get_connection

ENTRY_PAIR = "EUR_USD"
TRACKED_BASE = "EUR"
TRACKED_QUOTE = "USD"
MONTHS = 3

DB_PATH = "data/backtest_atlas_trader.db"
MODEL_PATH = "data/backtest_ml_model.json"


def main() -> None:
    required_pairs = sorted(set(get_required_pairs([TRACKED_BASE, TRACKED_QUOTE])) | {ENTRY_PAIR})

    print(f"Fetching {MONTHS} months of history for {len(required_pairs)} pairs...")
    print("(First run downloads from OANDA; later runs reuse the local cache.)\n")

    history = fetch_and_cache(
        pairs=required_pairs,
        granularities=["M5", "H4", "D"],
        months=MONTHS,
    )

    provider = HistoricalDataProvider(history)

    print(f"\nStarting {MONTHS}-month backtest on {ENTRY_PAIR}...\n")
    result = run_backtest(
        provider,
        entry_pair=ENTRY_PAIR,
        tracked_base=TRACKED_BASE,
        tracked_quote=TRACKED_QUOTE,
        db_path=DB_PATH,
        model_path=MODEL_PATH,
    )

    print(f"\nBacktest complete. {result['steps']} steps processed, {result['errors']} errors.")
    print(f"Final simulated balance: {result['final_balance']:.2f} (started at 100,000)\n")

    conn = get_connection(DB_PATH)
    report = generate_report(conn)

    print("--- Backtest Report ---")
    print(f"Setups logged:        {report['total_setups_logged']}")
    print(f"Trades opened:        {report['total_trades_opened']}")
    win_rate = report["win_rate"]
    print(f"Trades closed:        {win_rate['total_closed']}  (wins: {win_rate['wins']}, losses: {win_rate['losses']})")
    print(f"Win rate:             {win_rate['win_rate']}")
    conf = report["confidence_vs_outcome"]
    print(f"Avg confidence wins:  {conf['avg_confidence_wins']}")
    print(f"Avg confidence losses:{conf['avg_confidence_losses']}")
    print(f"Loss cause breakdown: {report['loss_cause_breakdown']}")
    pnl = report["pnl_summary"]
    print(f"Total P/L:            {pnl['total_pnl']}")
    print(f"Best trade:           {pnl['best_trade']}")
    print(f"Worst trade:          {pnl['worst_trade']}")
    print()


if __name__ == "__main__":
    main()
