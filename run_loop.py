#!/usr/bin/env python
"""
Entry point: run the AtlasTrader loop continuously.

Usage:
    python run_loop.py            # real OANDA data, tracks EUR_USD + GBP_USD
    python run_loop.py --mock     # synthetic data, for testing without credentials
    python run_loop.py --single   # original single-pair mode (EUR_USD only)

This is the script that should run 24/5 on the dedicated PC — via
Task Scheduler (run at startup, restart on failure) or as a service
(e.g. using NSSM). See README.md for Windows deployment notes.
"""

from __future__ import annotations

import sys

from atlas_trader.data_engine import MockDataProvider, OandaDataProvider, PairConfig
from atlas_trader.loop import run_forever

TRACKED_PAIRS = [
    PairConfig("EUR_USD", "EUR", "USD"),
    PairConfig("GBP_USD", "GBP", "USD"),
    PairConfig("USD_JPY", "USD", "JPY"),
    PairConfig("EUR_JPY", "EUR", "JPY"),
    PairConfig("GBP_JPY", "GBP", "JPY"),
]


def main() -> None:
    use_mock = "--mock" in sys.argv
    single_pair = "--single" in sys.argv

    if use_mock:
        provider = MockDataProvider()
        print("Running with MockDataProvider (synthetic data, no real trades placed).")
    else:
        provider = OandaDataProvider.from_config()
        print(f"Running with OandaDataProvider (environment: {provider.environment}).")

    try:
        if single_pair:
            print("Tracking EUR_USD only (single-pair mode).")
            run_forever(provider)
        else:
            pair_names = [p.entry_pair for p in TRACKED_PAIRS]
            print(f"Tracking {len(TRACKED_PAIRS)} pairs: {pair_names}")
            run_forever(provider, pairs=TRACKED_PAIRS)
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
