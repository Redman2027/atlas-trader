"""
Candlestick pattern detection.

Simple, explainable rules — no proprietary/opaque pattern library.
Each function is a plain, readable geometric check on candle bodies
and wicks, so the exact reason a pattern was (or wasn't) flagged is
always inspectable.
"""

from __future__ import annotations


def _body(candle: dict) -> float:
    return abs(candle["close"] - candle["open"])


def _range(candle: dict) -> float:
    return candle["high"] - candle["low"]


def _is_bullish(candle: dict) -> bool:
    return candle["close"] > candle["open"]


def _is_bearish(candle: dict) -> bool:
    return candle["close"] < candle["open"]


def is_doji(candle: dict, body_ratio_threshold: float = 0.1) -> bool:
    """Body is a small fraction of the candle's total range — indecision."""
    candle_range = _range(candle)
    if candle_range == 0:
        return True
    return (_body(candle) / candle_range) <= body_ratio_threshold


def is_bullish_engulfing(prev: dict, current: dict) -> bool:
    """Current bullish candle's body fully engulfs the prior bearish candle's body."""
    return (
        _is_bearish(prev)
        and _is_bullish(current)
        and current["open"] <= prev["close"]
        and current["close"] >= prev["open"]
    )


def is_bearish_engulfing(prev: dict, current: dict) -> bool:
    """Current bearish candle's body fully engulfs the prior bullish candle's body."""
    return (
        _is_bullish(prev)
        and _is_bearish(current)
        and current["open"] >= prev["close"]
        and current["close"] <= prev["open"]
    )


def is_hammer(candle: dict, wick_ratio: float = 2.0) -> bool:
    """Small body near the top of the range, long lower wick — bullish reversal."""
    body = _body(candle)
    candle_range = _range(candle)
    if candle_range == 0 or body == 0:
        return False
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    return lower_wick >= body * wick_ratio and lower_wick > upper_wick


def is_shooting_star(candle: dict, wick_ratio: float = 2.0) -> bool:
    """Small body near the bottom of the range, long upper wick — bearish reversal."""
    body = _body(candle)
    candle_range = _range(candle)
    if candle_range == 0 or body == 0:
        return False
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    return upper_wick >= body * wick_ratio and upper_wick > lower_wick


def detect_pattern(candles: list[dict]) -> str:
    """Check the most recent candle(s) against all known patterns.

    Checks two-candle patterns first (engulfing needs the prior candle
    for context), then single-candle patterns on the latest candle.
    Returns "none" if nothing matches — that's a valid, meaningful
    result on its own, not an error state.
    """
    if not candles:
        return "none"

    current = candles[-1]

    if len(candles) >= 2:
        prev = candles[-2]
        if is_bullish_engulfing(prev, current):
            return "bullish_engulfing"
        if is_bearish_engulfing(prev, current):
            return "bearish_engulfing"

    if is_doji(current):
        return "doji"
    if is_hammer(current):
        return "hammer"
    if is_shooting_star(current):
        return "shooting_star"

    return "none"
