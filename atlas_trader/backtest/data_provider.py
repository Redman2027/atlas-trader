"""
HistoricalDataProvider — implements the DataProvider interface by
replaying pre-fetched historical candles instead of live data.

This is the entire payoff of building every module against the
abstract DataProvider interface: Technical, Currency Strength, Macro,
Voting, and Risk all need ZERO changes to work in a backtest. They
just consume candles and don't know or care whether time is real or
simulated.

How simulated time works: `advance_to(timestamp)` moves the provider's
internal clock forward. `get_candles()` then only returns candles at
or before that timestamp — exactly what a live system would have known
"as of" that moment, with no lookahead into the future.

Trade resolution: `place_order()` opens a simulated position.
`get_trade_status()` scans the ACTUAL subsequent historical candles
(up to the current simulated time) to see whether price crossed the
stop-loss or take-profit, and reports the trade closed the moment it
would genuinely have happened.

Known simplification: if a single candle's range crosses both the
stop-loss and take-profit (a big/gappy candle), this conservatively
assumes the stop-loss was hit first. Real intra-candle order isn't
knowable from OHLC data alone — this is the safer assumption for a
system whose whole point is discipline, not the more optimistic one.
"""

from __future__ import annotations

from datetime import date
import bisect

from atlas_trader.backtest.fetcher import _parse_oanda_time
from atlas_trader.data_engine.base import DataProvider

# Toggle for the breakeven-stop feature (moves SL to entry+buffer once
# price reaches 1R favorable). Added this session -- default True, but
# can be flipped False to isolate its effect from other changes when
# comparing backtest runs (e.g. topdown-bias architecture validation).
BREAKEVEN_ENABLED = False


class HistoricalDataProvider(DataProvider):
    def __init__(
        self,
        candle_history: dict[tuple[str, str], list[dict]],
        start_balance: float = 100_000.0,
    ):
        """`candle_history` maps (pair, granularity) -> candles, sorted
        oldest-first, each a dict with open/high/low/close/time (time as
        an ISO 8601 string, e.g. '2026-07-26T21:30:00Z')."""
        self._history = candle_history
        self._history_times: dict[tuple[str, str], list[str]] = {}
        self._current_time: str | None = None
        self._balance = start_balance
        self._open_positions: dict[str, dict] = {}
        self._next_trade_id = 1
        self.closed_trades_log: list[dict] = []

    def advance_to(self, timestamp: str) -> None:
        self._current_time = timestamp

    def get_current_time(self) -> date:
        """Return the current simulated date, derived from the backtest's
        simulated clock (set via advance_to()). Raises if called before
        the clock has been advanced at least once."""
        if self._current_time is None:
            raise ValueError(
                "get_current_time() called before advance_to() — "
                "no simulated time set yet."
            )
        return _parse_oanda_time(self._current_time).date()

    def get_entry_timestamps(self, pair: str, granularity: str = "M5") -> list[str]:
        """Every timestamp available for `pair`/`granularity` — what the
        backtest runner steps through, one at a time."""
        return [c["time"] for c in self._history.get((pair, granularity), [])]

    def _candles_up_to_now(self, pair: str, granularity: str) -> list[dict]:
        all_candles = self._history.get((pair, granularity), [])
        if self._current_time is None:
            return []
        key = (pair, granularity)
        times = self._history_times.get(key)
        if times is None:
            times = [c["time"] for c in all_candles]
            self._history_times[key] = times
        idx = bisect.bisect_right(times, self._current_time)
        return all_candles[:idx]

    def get_candles(self, pair: str, granularity: str, count: int) -> list[dict]:
        return self._candles_up_to_now(pair, granularity)[-count:]

    def get_current_price(self, pair: str) -> float:
        candles = self._candles_up_to_now(pair, "M5")
        if not candles:
            raise ValueError(f"No historical M5 data for {pair} at or before {self._current_time}")
        return candles[-1]["close"]

    def get_account_balance(self) -> float:
        return self._balance

    def place_order(
        self, pair: str, direction: str, units: int, stop_loss: float, take_profit: float
    ) -> str:
        trade_id = f"bt-{self._next_trade_id}"
        self._next_trade_id += 1
        entry_price = self.get_current_price(pair)
        self._open_positions[trade_id] = {
            "pair": pair,
            "direction": direction,
            "units": units,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": self._current_time,
            "entry_price": entry_price,
            "original_sl_distance": abs(entry_price - stop_loss),
            "breakeven_moved": False,
        }
        return trade_id

    def _pnl(self, position: dict, close_price: float) -> float:
        if position["direction"] == "long":
            distance = close_price - position["entry_price"]
        else:
            distance = position["entry_price"] - close_price
        return round(distance * position["units"], 2)

    def get_trade_status(self, broker_trade_id: str) -> dict:
        position = self._open_positions.get(broker_trade_id)
        if position is None:
            raise ValueError(f"Unknown trade id: {broker_trade_id}")

        candles = [
            c
            for c in self._history.get((position["pair"], "M5"), [])
            if position["entry_time"] < c["time"] <= self._current_time
        ]

        for candle in candles:
            if BREAKEVEN_ENABLED and not position["breakeven_moved"]:
                buffer = position["original_sl_distance"] * 0.1
                if position["direction"] == "long":
                    breakeven_trigger = position["entry_price"] + position["original_sl_distance"]
                    if candle["high"] >= breakeven_trigger:
                        position["stop_loss"] = position["entry_price"] + buffer
                        position["breakeven_moved"] = True
                else:
                    breakeven_trigger = position["entry_price"] - position["original_sl_distance"]
                    if candle["low"] <= breakeven_trigger:
                        position["stop_loss"] = position["entry_price"] - buffer
                        position["breakeven_moved"] = True
            if position["direction"] == "long":
                hit_sl = candle["low"] <= position["stop_loss"]
                hit_tp = candle["high"] >= position["take_profit"]
            else:
                hit_sl = candle["high"] >= position["stop_loss"]
                hit_tp = candle["low"] <= position["take_profit"]

            if hit_sl or hit_tp:
                # Conservative: if both were touched in the same candle,
                # assume the stop-loss hit first (see module docstring).
                close_price = position["stop_loss"] if hit_sl else position["take_profit"]
                pnl = self._pnl(position, close_price)
                self._balance += pnl
                self.closed_trades_log.append(
                    {**position, "close_price": close_price, "pnl": pnl, "close_time": candle["time"]}
                )
                del self._open_positions[broker_trade_id]
                return {"status": "closed", "close_price": close_price, "pnl": pnl}

        return {"status": "open", "close_price": None, "pnl": None}
