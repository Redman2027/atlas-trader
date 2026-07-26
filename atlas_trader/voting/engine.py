"""
Voting/Confidence Engine — combines Macro, Currency Strength, and
Technical biases into a single directional confidence score.

Every upstream module reports a bias on the same -100 (max bearish) to
+100 (max bullish) scale:
    - Macro Engine: rate differential + stance -> bias
    - Currency Strength Matrix: base currency score - quote currency
      score -> bias
    - Technical Engine: EMA/MACD/RSI/pattern -> bias

This engine takes a weighted average of those three. The magnitude of
the result becomes the confidence score (0-100); its sign becomes the
direction. Modules that agree reinforce each other into a high
confidence score; modules that disagree cancel each other out into a
low one — that's the actual "voting."

Two thresholds, both configurable:
    - MIN_LOG_THRESHOLD: setups scoring at or above this get logged to
      the Journal (traded or not) — the "worth paying attention to" bar.
    - TRADE_THRESHOLD: setups scoring at or above this get traded —
      the higher "worth risking money on" bar.
"""

from __future__ import annotations

DEFAULT_WEIGHTS = {
    "macro": 0.25,
    "currency_strength": 0.25,
    "technical": 0.50,
}

MIN_LOG_THRESHOLD = 40.0
TRADE_THRESHOLD = 65.0


def combine_biases(
    macro_bias: float,
    currency_strength_bias: float,
    technical_bias: float,
    weights: dict = DEFAULT_WEIGHTS,
) -> float:
    """Weighted sum of the three module biases.

    Stays on the -100..100 scale as long as `weights` sum to 1.0.
    """
    composite = (
        macro_bias * weights["macro"]
        + currency_strength_bias * weights["currency_strength"]
        + technical_bias * weights["technical"]
    )
    return max(-100.0, min(100.0, composite))


def score_setup(
    macro_result: dict,
    currency_strength_result: dict,
    technical_bias_result: dict,
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    weights: dict = DEFAULT_WEIGHTS,
    min_log_threshold: float = MIN_LOG_THRESHOLD,
    trade_threshold: float = TRADE_THRESHOLD,
) -> dict:
    """Combine all module outputs into one explainable confidence score.

    `macro_result` is the dict from `compute_macro_bias()`.
    `currency_strength_result` is the dict from `compute_currency_strength()`.
    `technical_bias_result` is the dict from `compute_technical_bias()`.

    Returns a dict with `direction`, `confidence_score`, `should_log`,
    `should_trade`, and a `components` breakdown that maps directly
    onto the Journal's `feature_snapshot` — every number that produced
    the final score is preserved, nothing is thrown away.
    """
    macro_bias = macro_result["bias"]
    currency_strength_bias = (
        currency_strength_result[tracked_base]["score"]
        - currency_strength_result[tracked_quote]["score"]
    )
    technical_bias = technical_bias_result["bias"]

    composite_bias = combine_biases(
        macro_bias, currency_strength_bias, technical_bias, weights
    )

    confidence_score = round(abs(composite_bias), 2)

    if composite_bias > 0:
        direction = "long"
    elif composite_bias < 0:
        direction = "short"
    else:
        direction = "none"

    return {
        "direction": direction,
        "confidence_score": confidence_score,
        "composite_bias": round(composite_bias, 2),
        "should_log": confidence_score >= min_log_threshold,
        "should_trade": confidence_score >= trade_threshold,
        "components": {
            "macro": {
                "bias": macro_bias,
                "weight": weights["macro"],
                "detail": macro_result,
            },
            "currency_strength": {
                "bias": round(currency_strength_bias, 2),
                "weight": weights["currency_strength"],
                "detail": currency_strength_result,
            },
            "technical": {
                "bias": technical_bias,
                "weight": weights["technical"],
                "detail": technical_bias_result,
            },
        },
    }
