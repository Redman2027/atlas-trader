#!/usr/bin/env python
"""
Check any currency pair against real OANDA data — not just EURUSD.
Read-only, same as check_once.py: never places a trade.

Usage:
    python check_pair.py EUR CAD
    python check_pair.py EUR USD
    python check_pair.py GBP JPY

Note: the Macro Engine needs both currencies present in
config/macro_rates.json. If you get a KeyError, that currency's rate
data hasn't been added yet — add it the same way EUR/USD/CAD were.
"""

from __future__ import annotations

import sys

from atlas_trader.currency_strength import make_pair
from atlas_trader.data_engine import OandaDataProvider, run_analysis_cycle


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python check_pair.py <BASE> <QUOTE>   e.g. python check_pair.py EUR CAD")
        sys.exit(1)

    base, quote = sys.argv[1].upper(), sys.argv[2].upper()
    pair = make_pair(base, quote)

    provider = OandaDataProvider.from_config()
    result = run_analysis_cycle(provider, tracked_base=base, tracked_quote=quote, entry_pair=pair)
    voting = result["voting"]

    print(f"\n--- AtlasTrader — {pair} check ---")
    print(f"Direction:       {voting['direction']}")
    print(f"Confidence:      {voting['confidence_score']} / 100")
    print(f"Would log:       {voting['should_log']}")
    print(f"Would trade:     {voting['should_trade']}")

    print("\nComponent breakdown:")
    for name, comp in voting["components"].items():
        print(f"  {name:<18} bias={comp['bias']:>7}   weight={comp['weight']}")

    print()


if __name__ == "__main__":
    main()
