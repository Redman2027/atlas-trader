"""
MockDataProvider — deterministic synthetic data, no network required.

Used for building and testing the full pipeline before real OANDA
credentials exist, or any time you want a fast, reproducible run
without hitting a live API. Same seed always produces the same
candles, so test results are stable.
"""

from __future__ import annotations

import random

from .base import DataProvider

# Roughly realistic per-candle step size by granularity, in price terms.
GRANULARITY_STEP = {
    "M5": 0.0002,
    "H4": 0.0015,
    "D": 0.0040,
}


class MockDataProvider(DataProvider):
    def __init__(
        self,
        seed: int = 42,
        start_price: float = 1.0850,
        account_balance: float = 100_000.0,
        drift: float = 0.15,
    ):
        self._seed = seed
        self._start_price = start_price
        self._account_balance = account_balance
        self._drift = drift  # slight directional bias so trends aren't purely random

    def get_candles(self, pair: str, granularity: str, count: int) -> list[dict]:
        # Seed per (pair, granularity) so different pairs/timeframes get
        # different-but-reproducible series, instead of identical data.
        rng = random.Random(f"{self._seed}-{pair}-{granularity}")
        step = GRANULARITY_STEP.get(granularity, 0.0003)
        price = self._start_price
        candles = []
        for _ in range(count):
            move = rng.uniform(-step, step) + step * self._drift
            open_ = price
            close = price + move
            high = max(open_, close) + step * 0.2
            low = min(open_, close) - step * 0.2
            candles.append(
                {
                    "open": round(open_, 5),
                    "high": round(high, 5),
                    "low": round(low, 5),
                    "close": round(close, 5),
                }
            )
            price = close
        return candles

    def get_current_price(self, pair: str) -> float:
        return self.get_candles(pair, "M5", 1)[0]["close"]

    def get_account_balance(self) -> float:
        return self._account_balance
