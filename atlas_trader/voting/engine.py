"""
Voting/Confidence Engine — combines Macro, Currency Strength, Technical
(5M entry timeframe), and higher-timeframe Trend Context (4H + 1D)
biases into a single directional confidence score.

Every upstream module reports a bias on the same -100 (max bearish) to
+100 (max bullish) scale:
    - Macro Engine: rate differential + stance -> bias
    - Currency Strength Matrix: base currency score - quote currency
      score -> bias
    - Technical Engine: EMA/MACD/RSI/pattern -> bias (5M, the entry
      timeframe)
    - Trend Context (4H, 1D): the same Technical Engine math, run on
      higher timeframes -> bias, giving real "is this against the
      broader trend?" context that a 5M-only read can't see

This engine takes a weighted average of all supplied biases. The
magnitude of the result becomes the confidence score (0-100); its sign
becomes the direction. Modules that agree reinforce each other into a
high confidence score; modules that disagree cancel each other out
into a low one — that's the actual "voting."

If both `trend_4h_result` and `trend_1d_result` are supplied, they can
also VETO a trade outright — even if confidence otherwise clears the
trade threshold — when both higher timeframes strongly disagree with
the short-term composite direction. This exists specifically so a
strong 5M bounce can't force a trade against an obvious daily
downtrend.

Two thresholds, both configurable:
    - MIN_LOG_THRESHOLD: setups scoring at or above this get logged to
      the Journal (traded or not) — the "worth paying attention to" bar.
    - TRADE_THRESHOLD: setups scoring at or above this get traded —
      the higher "worth risking money on" bar.
"""

from __future__ import annotations

# 3-component weights — used only when no 4H/1D trend data is supplied.
# Kept for backward compatibility with earlier callers/tests.
DEFAULT_WEIGHTS = {
    "macro": 0.25,
    "currency_strength": 0.25,
    "technical": 0.50,
}

# 5-component weights — used whenever 4H/1D trend context is supplied,
# which is what the real pipeline always does now. Technical (5M) stays
# the single largest weight since it's the actual entry trigger, but
# the two higher timeframes combined (30%) now provide real trend
# context that was missing before.
DEFAULT_WEIGHTS_WITH_TREND = {
    "macro": 0.20,
    "currency_strength": 0.15,
    "technical": 0.35,
    "trend_4h": 0.15,
    "trend_1d": 0.15,
}

MIN_LOG_THRESHOLD = 40.0
TRADE_THRESHOLD = 65.0

# If both higher-timeframe trends agree with each other AND oppose the
# short-term composite direction by at least this much, veto the trade
# even if confidence otherwise clears TRADE_THRESHOLD.
TREND_VETO_THRESHOLD = 40.0


def combine_biases(
    macro_bias: float,
    currency_strength_bias: float,
    technical_bias: float,
    weights: dict = DEFAULT_WEIGHTS,
) -> float:
    """Weighted sum of the three original module biases (backward-compatible,
    3-component version). Stays on the -100..100 scale as long as `weights`
    sum to 1.0.
    """
    composite = (
        macro_bias * weights["macro"]
        + currency_strength_bias * weights["currency_strength"]
        + technical_bias * weights["technical"]
    )
    return max(-100.0, min(100.0, composite))


def _combine_weighted(biases: dict, weights: dict) -> float:
    """Generic weighted sum over any number of named components."""
    composite = sum(biases[name] * weights[name] for name in weights if name in biases)
    return max(-100.0, min(100.0, composite))


def score_setup(
    macro_result: dict,
    currency_strength_result: dict,
    technical_bias_result: dict,
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    trend_4h_result: dict | None = None,
    trend_1d_result: dict | None = None,
    weights: dict | None = None,
    min_log_threshold: float = MIN_LOG_THRESHOLD,
    trade_threshold: float = TRADE_THRESHOLD,
    trend_veto_threshold: float = TREND_VETO_THRESHOLD,
) -> dict:
    """Combine all module outputs into one explainable confidence score.

    `macro_result` is the dict from `compute_macro_bias()`.
    `currency_strength_result` is the dict from `compute_currency_strength()`.
    `technical_bias_result` is the dict from `compute_technical_bias()`
    run on the entry (5M) timeframe.

    `trend_4h_result`/`trend_1d_result` (optional) are
    `compute_technical_bias()` run on 4H/1D candles instead. If both are
    supplied, they're folded in as two extra weighted components AND can
    veto the trade — see module docstring. If either is omitted, this
    falls back to the original 3-component scheme with no veto, so
    existing callers keep working unchanged.

    Returns a dict with `direction`, `confidence_score`, `should_log`,
    `should_trade`, `trend_veto`, and a `components` breakdown that maps
    directly onto the Journal's `feature_snapshot` — every number that
    produced the final score is preserved, nothing is thrown away.
    """
    macro_bias = macro_result["bias"]
    currency_strength_bias = (
        currency_strength_result[tracked_base]["score"]
        - currency_strength_result[tracked_quote]["score"]
    )
    technical_bias = technical_bias_result["bias"]

    use_trend = trend_4h_result is not None and trend_1d_result is not None

    if use_trend:
        active_weights = weights or DEFAULT_WEIGHTS_WITH_TREND
        biases = {
            "macro": macro_bias,
            "currency_strength": currency_strength_bias,
            "technical": technical_bias,
            "trend_4h": trend_4h_result["bias"],
            "trend_1d": trend_1d_result["bias"],
        }
        composite_bias = _combine_weighted(biases, active_weights)
    else:
        active_weights = weights or DEFAULT_WEIGHTS
        composite_bias = combine_biases(
            macro_bias, currency_strength_bias, technical_bias, active_weights
        )

    confidence_score = round(abs(composite_bias), 2)

    if composite_bias > 0:
        direction = "long"
    elif composite_bias < 0:
        direction = "short"
    else:
        direction = "none"

    trend_veto = False
    if use_trend and direction != "none":
        composite_sign = 1 if direction == "long" else -1
        trend_4h_bias = trend_4h_result["bias"]
        trend_1d_bias = trend_1d_result["bias"]
        trend_veto = (
            trend_4h_bias * composite_sign < 0
            and trend_1d_bias * composite_sign < 0
            and abs(trend_4h_bias) >= trend_veto_threshold
            and abs(trend_1d_bias) >= trend_veto_threshold
        )

    components = {
        "macro": {
            "bias": macro_bias,
            "weight": active_weights.get("macro", 0),
            "detail": macro_result,
        },
        "currency_strength": {
            "bias": round(currency_strength_bias, 2),
            "weight": active_weights.get("currency_strength", 0),
            "detail": currency_strength_result,
        },
        "technical": {
            "bias": technical_bias,
            "weight": active_weights.get("technical", 0),
            "detail": technical_bias_result,
        },
    }
    if use_trend:
        components["trend_4h"] = {
            "bias": trend_4h_result["bias"],
            "weight": active_weights.get("trend_4h", 0),
            "detail": trend_4h_result,
        }
        components["trend_1d"] = {
            "bias": trend_1d_result["bias"],
            "weight": active_weights.get("trend_1d", 0),
            "detail": trend_1d_result,
        }

    return {
        "direction": direction,
        "confidence_score": confidence_score,
        "composite_bias": round(composite_bias, 2),
        "should_log": confidence_score >= min_log_threshold,
        "should_trade": (confidence_score >= trade_threshold) and not trend_veto,
        "trend_veto": trend_veto,
        "components": components,
    }
