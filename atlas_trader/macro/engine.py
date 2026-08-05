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
import calendar
from datetime import date

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


def get_rate_as_of(currency: str, as_of_date, config: dict) -> float:
    """Return the currency's policy rate effective as of as_of_date.

    Finds the most recent entry in the currency's rate_history whose
    effective_date is <= as_of_date. as_of_date may be a date object
    or an ISO 'YYYY-MM-DD' string.
    """
    if isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(as_of_date)

    history = config[currency]["rate_history"]
    applicable = [
        entry for entry in history
        if date.fromisoformat(entry["effective_date"]) <= as_of_date
    ]
    if not applicable:
        raise ValueError(
            f"No rate history for {currency} on or before {as_of_date} "
            f"\u2014 earliest entry is {history[0]['effective_date']}"
        )
    latest = max(applicable, key=lambda e: e["effective_date"])
    return latest["rate"]


def _subtract_months(d: date, months: int) -> date:
    month_index = d.month - 1 - months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# Rate-change magnitude below this (in percentage points) over the
# lookback window is treated as "neutral" rather than a directional
# hawkish/dovish move.
STANCE_NEUTRAL_THRESHOLD = 0.125

def derive_stance(currency: str, as_of_date, config: dict, lookback_months: int = 6) -> str:
    """Derive hawkish/neutral/dovish from the rate trajectory itself,
    rather than a hand-labeled snapshot (see macro-history handoff
    doc, Section 2.1, for the reasoning). Compares the rate as of
    as_of_date to the rate lookback_months prior.
    """
    if isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(as_of_date)

    current_rate = get_rate_as_of(currency, as_of_date, config)
    prior_date = _subtract_months(as_of_date, lookback_months)
    prior_rate = get_rate_as_of(currency, prior_date, config)

    delta = current_rate - prior_rate
    if delta > STANCE_NEUTRAL_THRESHOLD:
        return "hawkish"
    elif delta < -STANCE_NEUTRAL_THRESHOLD:
        return "dovish"
    return "neutral"


def compute_macro_bias(
    base_currency: str,
    quote_currency: str,
    trade_date,
    config: dict | None = None,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    lookback_months: int = 6,
) -> dict:
    """Directional bias for base/quote (e.g. EUR, USD -> EURUSD).

    Positive bias favors the base currency (e.g. bullish EURUSD).
    Negative bias favors the quote currency (e.g. bearish EURUSD).
    """
    if config is None:
        config = load_macro_config(config_path)

    base_rate = get_rate_as_of(base_currency, trade_date, config)
    quote_rate = get_rate_as_of(quote_currency, trade_date, config)
    base_stance = derive_stance(base_currency, trade_date, config, lookback_months)
    quote_stance = derive_stance(quote_currency, trade_date, config, lookback_months)

    stance_diff = STANCE_SCORES[base_stance] - STANCE_SCORES[quote_stance]
    rate_diff = base_rate - quote_rate

    raw_bias = (stance_diff * STANCE_WEIGHT) + (rate_diff * RATE_WEIGHT)
    bias = max(-100.0, min(100.0, raw_bias))

    return {
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "trade_date": str(trade_date),
        "base_rate": round(base_rate, 3),
        "quote_rate": round(quote_rate, 3),
        "base_stance": base_stance,
        "quote_stance": quote_stance,
        "stance_diff": stance_diff,
        "rate_diff": round(rate_diff, 3),
        "bias": round(bias, 2),
    }
