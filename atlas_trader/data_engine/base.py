"""
Data Engine — abstract interface every price data source must implement.

Downstream modules (Technical, Currency Strength, Risk) never talk to
OANDA or any other broker directly — they only ever see plain candle
dicts and floats. Swapping MockDataProvider for OandaDataProvider (once
a token is available) requires zero changes anywhere else in the
codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DataProvider(ABC):
    @abstractmethod
    def get_candles(self, pair: str, granularity: str, count: int) -> list[dict]:
        """Return the `count` most recent candles for `pair` at `granularity`
        (e.g. 'M5', 'H4', 'D'), oldest first, as a list of
        {"open", "high", "low", "close"} dicts."""
        raise NotImplementedError

    @abstractmethod
    def get_current_price(self, pair: str) -> float:
        """Return the current mid price for `pair`."""
        raise NotImplementedError

    @abstractmethod
    def get_account_balance(self) -> float:
        """Return the current real account balance (before any risk cap)."""
        raise NotImplementedError

    @abstractmethod
    def place_order(
        self, pair: str, direction: str, units: int, stop_loss: float, take_profit: float
    ) -> str:
        """Place a market order with attached stop-loss/take-profit.

        Returns a broker trade ID (a string) that can later be passed to
        get_trade_status() to check whether it's still open or has closed.
        """
        raise NotImplementedError

    @abstractmethod
    def get_trade_status(self, broker_trade_id: str) -> dict:
        """Check a previously-placed trade.

        Returns {"status": "open"} while still running, or
        {"status": "closed", "close_price": float, "pnl": float} once
        the stop-loss or take-profit has been hit.
        """
        raise NotImplementedError
