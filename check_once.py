#!/usr/bin/env python
"""
One-time check: run a single analysis pass against real OANDA data and
print the result. Does NOT loop, does NOT place trades on its own —
just tells you what the system currently sees.

Usage:
    python check_once.py
"""

from __future__ import annotations

from atlas_trader.data_engine import OandaDataProvider, run_analysis_cycle


def main() -> None:
    provider = OandaDataProvider.from_config()
    result = run_analysis_cycle(provider)
    voting = result["voting"]

    print("\n--- AtlasTrader — one-time check ---")
    print(f"Pair:            {result['pair']} ({result['timeframe']})")
    print(f"Direction:       {voting['direction']}")
    print(f"Confidence:      {voting['confidence_score']} / 100")
    print(f"Would log:       {voting['should_log']}")
    print(f"Would trade:     {voting['should_trade']}")

    if result["trade_plan"]:
        plan = result["trade_plan"]
        print("\n--- Trade plan (not executed by this script) ---")
        print(f"  Entry:          {plan['entry_price']}")
        print(f"  Stop-loss:      {plan['stop_loss']}")
        print(f"  Take-profit:    {plan['take_profit']}")
        print(f"  Position size:  {plan['position_size_units']} units")

    print()


if __name__ == "__main__":
    main()
