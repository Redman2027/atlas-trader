"""1H entry-trigger logic (Handoff 18).

Separate from compute_technical_bias() on purpose: this is structural/
sequential pattern logic (pullback -> resumption), not an indicator blend.
It takes RAW 1H candles (open/high/low/close/time dicts) directly, the
same candles_1h already fetched in pipeline.py before being passed into
analyze_candles().

Role in the architecture: trend_4h/trend_1d/macro/currency_strength decide
DIRECTION via the composite score in voting/engine.py. This function is the
sole gate on TIMING/ENTRY -- it does not vote in the composite. A trade
only fires if the composite clears TRADE_THRESHOLD AND this trigger fires
for that direction.

Rule (finalized Handoff 18):
  - Pullback: up to MAX_PULLBACK_CANDLES (default 3) consecutive 1H candles
    moving against the bias direction, immediately preceding the latest
    candle.
  - Swing point: highest high (long) / lowest low (short) over the
    SWING_LOOKBACK (default 5) candles immediately preceding the start of
    the pullback.
  - Trigger fires when the latest 1H candle closes beyond that swing point
    in the bias direction (resumption, not a raw crossover).
  - Expiration: if the pullback runs longer than MAX_PULLBACK_CANDLES
    without a resumption close, the setup is expired -- no trigger, no
    window extension.
"""

from __future__ import annotations

MAX_PULLBACK_CANDLES = 3
SWING_LOOKBACK = 5


def _is_against_direction(candle: dict, direction: str) -> bool:
    """A candle counts as 'against' the bias direction if it closed opposite
    its open -- a plain bearish candle during a long bias, or a plain
    bullish candle during a short bias."""
    if direction == "long":
        return candle["close"] < candle["open"]
    return candle["close"] > candle["open"]


def check_entry_trigger(
    candles_1h: list[dict],
    direction: str,
    max_pullback_candles: int = MAX_PULLBACK_CANDLES,
    swing_lookback: int = SWING_LOOKBACK,
) -> dict:
    """Check whether the 1H pullback-then-resumption trigger has fired.

    candles_1h: raw OHLC candle dicts, oldest first, most recent last.
    direction: "long" or "short" -- the composite bias direction from
        voting/engine.py. Pass "none" (or anything else) to short-circuit.

    Returns a dict always containing "triggered" (bool) and "reason"
    (str), plus diagnostic fields when a pullback was found at all.
    """
    if direction not in ("long", "short"):
        return {"triggered": False, "reason": "no_direction"}

    min_required = max_pullback_candles + swing_lookback + 1
    if len(candles_1h) < min_required:
        return {"triggered": False, "reason": "insufficient_candles"}

    latest = candles_1h[-1]

    # Count consecutive against-direction candles immediately preceding the
    # latest candle. Cap the scan one past the allowed window so we can
    # distinguish "no pullback" / "valid pullback" / "expired pullback".
    pullback_count = 0
    idx = len(candles_1h) - 2
    while idx >= 0 and pullback_count <= max_pullback_candles:
        if not _is_against_direction(candles_1h[idx], direction):
            break
        pullback_count += 1
        idx -= 1

    if pullback_count == 0:
        return {"triggered": False, "reason": "no_pullback"}

    if pullback_count > max_pullback_candles:
        return {
            "triggered": False,
            "reason": "pullback_expired",
            "pullback_candles": pullback_count,
        }

    # Swing window is the N candles immediately BEFORE the pullback started.
    pullback_start_idx = len(candles_1h) - 1 - pullback_count
    swing_start_idx = pullback_start_idx - swing_lookback
    if swing_start_idx < 0:
        return {"triggered": False, "reason": "insufficient_swing_history"}

    swing_window = candles_1h[swing_start_idx:pullback_start_idx]

    if direction == "long":
        swing_level = max(c["high"] for c in swing_window)
        fired = latest["close"] > swing_level
    else:
        swing_level = min(c["low"] for c in swing_window)
        fired = latest["close"] < swing_level

    return {
        "triggered": fired,
        "reason": "resumption_confirmed" if fired else "no_resumption_close",
        "pullback_candles": pullback_count,
        "swing_level": round(swing_level, 5),
        "entry_price": latest["close"],
    }
