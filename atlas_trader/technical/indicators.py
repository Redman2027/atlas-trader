"""
Core technical indicator math for the Technical Engine.

Pure Python / stdlib only — deliberately no pandas/numpy dependency,
consistent with the rest of the codebase so far. Takes plain lists/dicts
in, plain values out, so it's easy to test without a data pipeline
running yet.

Candles are expected as a list of dicts, OLDEST FIRST:
    [{"open": 1.0840, "high": 1.0855, "low": 1.0832, "close": 1.0849}, ...]
"""

from __future__ import annotations


def ema_series(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average. First (period-1) entries are None (not enough data)."""
    if len(values) < period:
        return [None] * len(values)

    multiplier = 2 / (period + 1)
    result: list[float | None] = [None] * (period - 1)

    # Seed with a simple moving average for the first EMA value.
    sma_seed = sum(values[:period]) / period
    result.append(sma_seed)

    ema = sma_seed
    for value in values[period:]:
        ema = (value - ema) * multiplier + ema
        result.append(ema)

    return result


def rsi_series(values: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI, aligned to `values` (first `period` entries are None)."""
    if len(values) < period + 1:
        return [None] * len(values)

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    result: list[float | None] = [None] * period

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result.append(_rsi_from_averages(avg_gain, avg_loss))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result.append(_rsi_from_averages(avg_gain, avg_loss))

    return result


def macd_series(
    values: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[float | None]]:
    """Returns MACD line, signal line, and histogram, all aligned to `values`."""
    ema_fast = ema_series(values, fast)
    ema_slow = ema_series(values, slow)

    macd_line: list[float | None] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]

    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), None)
    if first_valid is None:
        signal_line: list[float | None] = [None] * len(values)
    else:
        macd_values = [v for v in macd_line if v is not None]
        signal_tail = ema_series(macd_values, signal)
        signal_line = [None] * first_valid + signal_tail

    histogram: list[float | None] = [
        (m - s) if (m is not None and s is not None) else None
        for m, s in zip(macd_line, signal_line)
    ]

    return {"macd_line": macd_line, "signal_line": signal_line, "histogram": histogram}


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    """Wilder's Average True Range, aligned to `candles`."""
    if len(candles) < period + 1:
        return [None] * len(candles)

    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    result: list[float | None] = [None] * period

    atr = sum(true_ranges[:period]) / period
    result.append(atr)

    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period
        result.append(atr)

    return result
