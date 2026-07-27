#!/usr/bin/env python
"""
One-off verification: places a single small real order on your OANDA
account to confirm place_order()/get_trade_status() actually work.
Bypasses the Voting Engine entirely — this is just testing the broker
connection, not a real trading signal.

Usage:
    python test_place_order.py
"""

from __future__ import annotations

from atlas_trader.data_engine import OandaDataProvider

PAIR = "EUR_USD"
DIRECTION = "short"   # matches the user's macro read for this test
UNITS = 100           # small size, just to prove the pipe works
STOP_DISTANCE = 0.0030
TAKE_PROFIT_DISTANCE = 0.0030


def main() -> None:
    provider = OandaDataProvider.from_config()
    entry_price = provider.get_current_price(PAIR)

    if DIRECTION == "short":
        stop_loss = round(entry_price + STOP_DISTANCE, 5)
        take_profit = round(entry_price - TAKE_PROFIT_DISTANCE, 5)
    else:
        stop_loss = round(entry_price - STOP_DISTANCE, 5)
        take_profit = round(entry_price + TAKE_PROFIT_DISTANCE, 5)

    print(f"Current price: {entry_price}")
    print(f"Placing {DIRECTION} {UNITS} units | SL={stop_loss} TP={take_profit}")

    trade_id = provider.place_order(
        pair=PAIR,
        direction=DIRECTION,
        units=UNITS,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    print(f"\nOrder placed. Broker trade ID: {trade_id}")

    status = provider.get_trade_status(trade_id)
    print(f"Current status: {status}")


if __name__ == "__main__":
    main()
