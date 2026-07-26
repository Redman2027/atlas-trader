#!/usr/bin/env python
"""
Entry point: run the AtlasTrader loop continuously.

Usage:
    python run_loop.py            # real OANDA data (needs config/oanda_credentials.json)
    python run_loop.py --mock     # synthetic data, for testing without credentials

This is the script that should run 24/5 on the dedicated PC — via
Task Scheduler (run at startup, restart on failure) or as a service
(e.g. using NSSM). See README.md for Windows deployment notes.
"""

from __future__ import annotations

import sys

from atlas_trader.data_engine import MockDataProvider, OandaDataProvider
from atlas_trader.loop import run_forever


def main() -> None:
    use_mock = "--mock" in sys.argv

    if use_mock:
        provider = MockDataProvider()
        print("Running with MockDataProvider (synthetic data, no real trades placed).")
    else:
        provider = OandaDataProvider.from_config()
        print(f"Running with OandaDataProvider (environment: {provider.environment}).")

    try:
        run_forever(provider)
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    main()
