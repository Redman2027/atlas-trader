"""
Currency Strength Matrix calculator.

Computes an independent strength score (0-100, centered at 50) for
each tracked currency by averaging its signed percentage price change
against every other major currency it's paired against.

This module is deliberately data-source agnostic: it takes a dict of
{pair_symbol: pct_change} and doesn't know or care whether that came
from OANDA, a CSV, or a test fixture. The Data Engine (not yet built)
is responsible for computing pct_change per pair over whatever lookback
window is chosen, and handing it to this module.
"""

from __future__ import annotations

from .pairs import MAJOR_CURRENCIES, TRACKED_CURRENCIES, get_pairs_for_currency

# How many percentage points of average signed move correspond to a
# full swing from neutral (50) to the edge of the scale (0 or 100).
# e.g. SCALE_SENSITIVITY = 0.2 means an average +0.2% move across a
# currency's pairs maps to a raw score of 100.
#
# CALIBRATION NOTE (from a real 3-month backtest): the original value
# of 1.0 assumed a 1% average move was a realistic "strong" reading.
# In practice, over the ~100-minute lookback window Currency Strength
# actually uses, real EURUSD differentials are typically 0.05-0.3% —
# meaning the old value left this component producing bias scores of
# roughly -2 to +2 almost all the time, regardless of how strong the
# real move was. That made 15% of the Voting Engine's weight
# functionally dead. 0.2 was chosen so a genuinely strong short-term
# differential (~0.2%) can actually reach the component's full range,
# while a quiet/flat market still correctly scores near zero.
SCALE_SENSITIVITY = 0.2


def _signed_change_for_currency(currency: str, pair: str, pct_change: float) -> float:
    """Flip the sign of pct_change if `currency` is the quote side of `pair`.

    pct_change is the % change of the pair as quoted (base/quote). If
    `currency` is the base, a positive pct_change means it strengthened.
    If `currency` is the quote, a positive pct_change of the pair means
    the OTHER currency strengthened, so the sign is flipped.
    """
    base, quote = pair.split("_")
    if currency == base:
        return pct_change
    elif currency == quote:
        return -pct_change
    raise ValueError(f"Currency '{currency}' is not part of pair '{pair}'")


def compute_raw_strength(
    currency: str,
    pair_pct_changes: dict[str, float],
    universe: list[str] = MAJOR_CURRENCIES,
) -> float:
    """Average signed % change for `currency` across all its pairs in `universe`."""
    relevant_pairs = get_pairs_for_currency(currency, universe)
    missing = [p for p in relevant_pairs if p not in pair_pct_changes]
    if missing:
        raise ValueError(
            f"Missing price data for pairs required to score {currency}: {missing}"
        )
    signed_changes = [
        _signed_change_for_currency(currency, pair, pair_pct_changes[pair])
        for pair in relevant_pairs
    ]
    return sum(signed_changes) / len(signed_changes)


def scale_to_score(raw_strength: float, sensitivity: float = SCALE_SENSITIVITY) -> float:
    """Map a raw average % change to a 0-100 score, centered at 50 (neutral)."""
    score = 50.0 + (raw_strength / sensitivity) * 50.0
    return max(0.0, min(100.0, score))


def compute_currency_strength(
    pair_pct_changes: dict[str, float],
    tracked_currencies: list[str] = TRACKED_CURRENCIES,
    universe: list[str] = MAJOR_CURRENCIES,
    sensitivity: float = SCALE_SENSITIVITY,
) -> dict[str, dict[str, float]]:
    """Compute strength scores for each tracked currency.

    Returns a dict like:
        {
            "EUR": {"raw": 0.34, "score": 67.0},
            "USD": {"raw": -0.12, "score": 44.0},
        }

    `raw` is kept alongside `score` so the Journal Engine's
    feature_snapshot stays fully explainable — you can always see the
    actual average % move that produced the final score, not just the
    final number.
    """
    results: dict[str, dict[str, float]] = {}
    for currency in tracked_currencies:
        raw = compute_raw_strength(currency, pair_pct_changes, universe)
        results[currency] = {
            "raw": round(raw, 5),
            "score": round(scale_to_score(raw, sensitivity), 2),
        }
    return results
