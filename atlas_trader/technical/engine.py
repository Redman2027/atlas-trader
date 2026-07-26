"""
Technical Engine — combines EMA, RSI, MACD, ATR, and candlestick pattern
detection into a single explainable snapshot for a set of candles.

This is data-source agnostic, same as the Currency Strength Matrix: it
takes a list of candle dicts and returns a result dict. It doesn't
fetch candles itself — that's the Data Engine's job once built.
"""

from __future__ import annotations

from .indicators import ema_series, rsi_series, macd_series, atr_series
from .patterns import detect_pattern

DEFAULT_EMA_PERIOD = 20
DEFAULT_RSI_PERIOD = 14
DEFAULT_MACD_FAST = 12
DEFAULT_MACD_SLOW = 26
DEFAULT_MACD_SIGNAL = 9
DEFAULT_ATR_PERIOD = 14


def _latest(series: list):
    return series[-1] if series else None


def _ema_trend(closes: list[float], ema_values: list) -> str:
    """Simple trend read: is the latest close above or below the EMA?"""
    latest_close = closes[-1]
    latest_ema = _latest(ema_values)
    if latest_ema is None:
        return "unknown"
    if latest_close > latest_ema:
        return "up"
    elif latest_close < latest_ema:
        return "down"
    return "flat"


def _macd_cross(histogram: list) -> str:
    """Detect a fresh bullish/bearish cross on the most recent bar."""
    valid = [h for h in histogram if h is not None]
    if len(valid) < 2:
        return "none"
    prev_hist, curr_hist = valid[-2], valid[-1]
    if prev_hist <= 0 < curr_hist:
        return "bullish_cross"
    if prev_hist >= 0 > curr_hist:
        return "bearish_cross"
    return "none"


def analyze_candles(
    candles: list[dict],
    ema_period: int = DEFAULT_EMA_PERIOD,
    rsi_period: int = DEFAULT_RSI_PERIOD,
    macd_fast: int = DEFAULT_MACD_FAST,
    macd_slow: int = DEFAULT_MACD_SLOW,
    macd_signal: int = DEFAULT_MACD_SIGNAL,
    atr_period: int = DEFAULT_ATR_PERIOD,
) -> dict:
    """Run the full Technical Engine over a list of candles (oldest first).

    Returns a dict matching the shape used in the Journal's
    feature_snapshot, e.g.:
        {
            "ema": {"period": 20, "value": 1.0847, "trend": "up"},
            "rsi": {"period": 14, "value": 61.2},
            "macd": {"macd_line": .., "signal_line": .., "histogram": .., "cross": "bullish_cross"},
            "atr": {"period": 14, "value": 0.00072},
            "pattern": "bullish_engulfing",
        }
    """
    closes = [c["close"] for c in candles]

    ema_values = ema_series(closes, ema_period)
    rsi_values = rsi_series(closes, rsi_period)
    macd_result = macd_series(closes, macd_fast, macd_slow, macd_signal)
    atr_values = atr_series(candles, atr_period)

    return {
        "ema": {
            "period": ema_period,
            "value": _latest(ema_values),
            "trend": _ema_trend(closes, ema_values),
        },
        "rsi": {
            "period": rsi_period,
            "value": _latest(rsi_values),
        },
        "macd": {
            "macd_line": _latest(macd_result["macd_line"]),
            "signal_line": _latest(macd_result["signal_line"]),
            "histogram": _latest(macd_result["histogram"]),
            "cross": _macd_cross(macd_result["histogram"]),
        },
        "atr": {
            "period": atr_period,
            "value": _latest(atr_values),
        },
        "pattern": detect_pattern(candles),
    }
