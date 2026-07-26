"""
Macro Engine (v1 stub) — turns the manually-maintained interest rate
config into a directional bias score.

This deliberately does NOT fetch live data. Central bank decisions are
infrequent (~8x/year), so a manually-updated config
(config/macro_rates.json) stays accurate without the complexity of a
live feed — see the main README for how to update it after each
Fed/ECB decision.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "macro_rates.json"
)

STANCE_SCORES = {"hawkish": 1, "neutral": 0, "dovish": -1}

# How much weight the stance (hawkish/neutral/dovish) difference carries
# vs. the raw rate differential in percentage points. Both land on the
# same -100..100 bias scale used by every other module.
STANCE_WEIGHT = 20.0
RATE_WEIGHT = 10.0


def load_macro_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> dict:
    with open(config_path, "r") as f:
        return json.load(f)


def compute_macro_bias(
    base_currency: str,
    quote_currency: str,
    config: dict | None = None,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> dict:
    """Directional bias for base/quote (e.g. EUR, USD -> EURUSD).

    Positive bias favors the base currency (e.g. bullish EURUSD).
    Negative bias favors the quote currency (e.g. bearish EURUSD).
    """
    if config is None:
        config = load_macro_config(config_path)

    base_info = config[base_currency]
    quote_info = config[quote_currency]

    stance_diff = STANCE_SCORES[base_info["stance"]] - STANCE_SCORES[quote_info["stance"]]
    rate_diff = base_info["current_rate"] - quote_info["current_rate"]

    raw_bias = (stance_diff * STANCE_WEIGHT) + (rate_diff * RATE_WEIGHT)
    bias = max(-100.0, min(100.0, raw_bias))

    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "base_stance": base_info["stance"],
        "quote_stance": quote_info["stance"],
        "stance_diff": stance_diff,
        "rate_diff": round(rate_diff, 3),
        "bias": round(bias, 2),
    }
