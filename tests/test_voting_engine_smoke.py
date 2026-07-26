"""
Smoke test for the Voting/Confidence Engine — runs the full pipeline:
Macro Engine + Currency Strength Matrix + Technical Engine -> Voting
Engine, and checks that agreement produces high confidence while
disagreement cancels out into low confidence.

Run directly:

    python tests/test_voting_engine_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.macro import compute_macro_bias
from atlas_trader.currency_strength import compute_currency_strength
from atlas_trader.technical import compute_technical_bias
from atlas_trader.voting import score_setup


def test_all_modules_agree_bullish():
    """EUR hawkish/USD dovish, EUR strong, technicals bullish -> should be a strong 'long'."""
    macro_result = compute_macro_bias(
        "EUR",
        "USD",
        config={
            "EUR": {"current_rate": 3.50, "stance": "hawkish"},
            "USD": {"current_rate": 1.00, "stance": "dovish"},
        },
    )

    currency_strength_result = compute_currency_strength(
        {
            "EUR_USD": 0.60,
            "EUR_GBP": 0.30,
            "EUR_AUD": 0.40,
            "EUR_NZD": 0.45,
            "EUR_CAD": 0.35,
            "EUR_CHF": 0.20,
            "EUR_JPY": 0.55,
            "GBP_USD": 0.05,
            "AUD_USD": -0.15,
            "NZD_USD": -0.10,
            "USD_CAD": -0.10,
            "USD_CHF": -0.05,
            "USD_JPY": 0.05,
        }
    )

    technical_bias_result = compute_technical_bias(
        {
            "ema": {"trend": "up"},
            "macd": {"cross": "bullish_cross"},
            "rsi": {"value": 70.0},
            "pattern": "bullish_engulfing",
        }
    )

    result = score_setup(macro_result, currency_strength_result, technical_bias_result)
    print("All-agree bullish scenario:", result["direction"], result["confidence_score"])

    assert result["direction"] == "long"
    assert result["confidence_score"] > 60, "Strong agreement should produce high confidence"
    assert result["should_log"] is True
    assert result["should_trade"] is True


def test_modules_disagree():
    """Macro bullish EUR, but technicals bearish -> should cancel toward low confidence."""
    macro_result = compute_macro_bias(
        "EUR",
        "USD",
        config={
            "EUR": {"current_rate": 3.00, "stance": "hawkish"},
            "USD": {"current_rate": 2.00, "stance": "dovish"},
        },
    )

    # Currency strength roughly flat/neutral
    currency_strength_result = compute_currency_strength(
        {
            "EUR_USD": 0.0,
            "EUR_GBP": 0.0,
            "EUR_AUD": 0.0,
            "EUR_NZD": 0.0,
            "EUR_CAD": 0.0,
            "EUR_CHF": 0.0,
            "EUR_JPY": 0.0,
            "GBP_USD": 0.0,
            "AUD_USD": 0.0,
            "NZD_USD": 0.0,
            "USD_CAD": 0.0,
            "USD_CHF": 0.0,
            "USD_JPY": 0.0,
        }
    )

    technical_bias_result = compute_technical_bias(
        {
            "ema": {"trend": "down"},
            "macd": {"cross": "bearish_cross"},
            "rsi": {"value": 30.0},
            "pattern": "bearish_engulfing",
        }
    )

    result = score_setup(macro_result, currency_strength_result, technical_bias_result)
    print("Disagreement scenario:", result["direction"], result["confidence_score"])

    # Macro pulls long, technical pulls short -> should net out to a low-confidence read
    assert result["confidence_score"] < 40, "Disagreement between modules should suppress confidence"
    assert result["should_trade"] is False


if __name__ == "__main__":
    test_all_modules_agree_bullish()
    test_modules_disagree()
    print("Voting/Confidence Engine smoke test passed.")
