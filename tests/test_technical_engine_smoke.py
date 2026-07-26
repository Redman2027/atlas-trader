"""
Smoke test for the Technical Engine.

Run directly:

    python tests/test_technical_engine_smoke.py

Part 1 runs the full indicator stack over a synthetic uptrending
candle series and sanity-checks the outputs. Part 2 hand-builds
specific candles to verify each pattern detector fires correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.technical import analyze_candles, detect_pattern


def make_candle(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def build_synthetic_uptrend(n: int = 60, start: float = 1.0800, step: float = 0.0004):
    """A gently uptrending series with occasional pullbacks, enough bars for MACD/RSI/ATR to warm up."""
    candles = []
    price = start
    for i in range(n):
        if i % 7 == 0 and i > 20:
            move = -0.0012  # occasional pullback so RSI isn't pinned at 100
        else:
            noise = 0.0002 if i % 3 == 0 else -0.0001
            move = step + noise
        open_ = price
        close = price + move
        high = max(open_, close) + 0.0003
        low = min(open_, close) - 0.0003
        candles.append(make_candle(open_, high, low, close))
        price = close
    return candles


def test_indicator_stack():
    candles = build_synthetic_uptrend()
    result = analyze_candles(candles)

    print("Technical Engine result on synthetic uptrend:", result)

    assert result["ema"]["value"] is not None
    assert result["ema"]["trend"] in ("up", "down", "flat")
    assert 0 <= result["rsi"]["value"] <= 100
    assert result["atr"]["value"] > 0
    assert result["macd"]["cross"] in ("bullish_cross", "bearish_cross", "none")
    assert isinstance(result["pattern"], str)

    # It's a sustained uptrend -> EMA trend should read "up"
    assert result["ema"]["trend"] == "up", "Expected an 'up' EMA trend on a rising synthetic series"


def test_patterns():
    # Bullish engulfing: prior bearish candle, current bullish candle that engulfs it
    prev = make_candle(open_=1.0860, high=1.0865, low=1.0840, close=1.0845)
    current = make_candle(open_=1.0843, high=1.0875, low=1.0842, close=1.0870)
    assert detect_pattern([prev, current]) == "bullish_engulfing"

    # Doji: open and close almost identical relative to the day's range
    doji = make_candle(open_=1.0850, high=1.0870, low=1.0830, close=1.0851)
    assert detect_pattern([doji]) == "doji"

    # Hammer: small body near the top, long lower wick
    hammer = make_candle(open_=1.0840, high=1.0855, low=1.0800, close=1.0850)
    assert detect_pattern([hammer]) == "hammer"

    # No pattern: an ordinary mid-range candle with no notable wick or engulfing
    plain = make_candle(open_=1.0850, high=1.0860, low=1.0845, close=1.0856)
    assert detect_pattern([plain]) == "none"

    print("All candlestick pattern checks passed.")


if __name__ == "__main__":
    test_indicator_stack()
    test_patterns()
    print("Technical Engine smoke test passed.")
