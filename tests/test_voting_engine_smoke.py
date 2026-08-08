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
            "EUR": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.5}, {'effective_date': '2025-01-01', 'rate': 3.5}]},
            "USD": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.0}, {'effective_date': '2025-01-01', 'rate': 1.0}]},
        },
        trade_date="2025-01-01"
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
            "EUR": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.0}, {'effective_date': '2025-01-01', 'rate': 3.0}]},
            "USD": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 3.0}, {'effective_date': '2025-01-01', 'rate': 2.0}]},
        },
        trade_date="2025-01-01"
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


def test_strong_daily_downtrend_flips_direction_against_5m_bounce():
    """A strong 5M bounce says 'long', but both the 4H and 1D charts are
    clearly in a downtrend. Trend now carries real weight (40% combined)
    directly in the composite, so a downtrend this strong on both higher
    timeframes outweighs the 5M signal and flips direction to 'short'
    outright -- no separate veto needed (see AtlasTrader_Handoff12.md)."""
    macro_result = compute_macro_bias(
        "EUR",
        "USD",
        config={
            "EUR": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.0}, {'effective_date': '2025-01-01', 'rate': 2.0}]},
            "USD": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.0}, {'effective_date': '2025-01-01', 'rate': 2.0}]},
        },
        trade_date="2025-01-01"
    )

    # Neutral currency strength so it doesn't influence the outcome
    currency_strength_result = compute_currency_strength(
        {pair: 0.0 for pair in [
            "EUR_USD", "EUR_GBP", "EUR_AUD", "EUR_NZD", "EUR_CAD", "EUR_CHF", "EUR_JPY",
            "GBP_USD", "AUD_USD", "NZD_USD", "USD_CAD", "USD_CHF", "USD_JPY",
        ]}
    )

    # Strong bullish 5M bounce
    technical_bias_result = compute_technical_bias(
        {
            "ema": {"trend": "up"},
            "macd": {"cross": "bullish_cross"},
            "rsi": {"value": 75.0},
            "pattern": "bullish_engulfing",
        }
    )

    # Both higher timeframes clearly bearish
    trend_4h_result = compute_technical_bias(
        {
            "ema": {"trend": "down"},
            "macd": {"cross": "bearish_cross"},
            "rsi": {"value": 25.0},
            "pattern": "bearish_engulfing",
        }
    )
    trend_1d_result = compute_technical_bias(
        {
            "ema": {"trend": "down"},
            "macd": {"cross": "bearish_cross"},
            "rsi": {"value": 20.0},
            "pattern": "bearish_engulfing",
        }
    )

    result = score_setup(
        macro_result,
        currency_strength_result,
        technical_bias_result,
        trend_4h_result=trend_4h_result,
        trend_1d_result=trend_1d_result,
    )
    print("Trend veto scenario:", result["direction"], result["confidence_score"], "veto:", result["trend_veto"])

    assert result["direction"] == "short"  # strong 4H/1D downtrend outweighs the 5M bounce
    assert result["trend_veto"] is False  # veto removed -- trend acts through composite weight now
    assert result["should_trade"] is True  # trend now carries 60% combined weight; a fully-aligned 4H/1D downtrend clears threshold outright, overriding the 5M bounce (no veto needed)


def test_no_veto_when_trend_data_absent():
    """Backward compatibility: omitting trend_4h/trend_1d entirely must
    behave exactly like before this feature existed — no veto possible."""
    macro_result = compute_macro_bias(
        "EUR", "USD",
        config={
            "EUR": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.5}, {'effective_date': '2025-01-01', 'rate': 3.5}]},
            "USD": {"rate_history": [{'effective_date': '2023-01-01', 'rate': 2.0}, {'effective_date': '2025-01-01', 'rate': 1.0}]},
        },
        trade_date="2025-01-01"
    )
    currency_strength_result = compute_currency_strength({pair: 0.5 for pair in [
        "EUR_USD", "EUR_GBP", "EUR_AUD", "EUR_NZD", "EUR_CAD", "EUR_CHF", "EUR_JPY",
        "GBP_USD", "AUD_USD", "NZD_USD", "USD_CAD", "USD_CHF", "USD_JPY",
    ]})
    technical_bias_result = compute_technical_bias(
        {"ema": {"trend": "up"}, "macd": {"cross": "bullish_cross"}, "rsi": {"value": 70.0}, "pattern": "bullish_engulfing"}
    )

    result = score_setup(macro_result, currency_strength_result, technical_bias_result)
    assert result["trend_veto"] is False
    assert "trend_4h" not in result["components"]


if __name__ == "__main__":
    test_all_modules_agree_bullish()
    test_modules_disagree()
    test_trend_veto_blocks_trade_against_daily_downtrend()
    test_no_veto_when_trend_data_absent()
    print("Voting/Confidence Engine smoke test passed.")
