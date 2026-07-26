"""
Currency pair conventions for the Currency Strength Matrix.

FX pairs are always quoted in a fixed base/quote order (e.g. EUR_USD,
never USD_EUR). This module encodes that ordering using the standard
market precedence hierarchy, so pairs are generated programmatically
instead of hardcoded one by one — this scales cleanly if you ever want
to track more currencies than just EUR/USD.
"""

from __future__ import annotations

# Standard FX market precedence: if a currency appears earlier in this
# list, it is quoted as the BASE currency against anything later in
# the list. e.g. EUR appears before USD -> EUR_USD (never USD_EUR).
CURRENCY_PRECEDENCE = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]

# The full major-currency universe the Currency Strength Matrix understands.
MAJOR_CURRENCIES = list(CURRENCY_PRECEDENCE)

# Currencies actually scored/reported on for this EA (EURUSD only, for now).
TRACKED_CURRENCIES = ["EUR", "USD"]


def make_pair(currency_a: str, currency_b: str) -> str:
    """Return the correctly-ordered OANDA-style pair symbol, e.g. 'EUR_USD'."""
    if currency_a == currency_b:
        raise ValueError("Cannot make a pair from a currency and itself")
    idx_a = CURRENCY_PRECEDENCE.index(currency_a)
    idx_b = CURRENCY_PRECEDENCE.index(currency_b)
    base, quote = (currency_a, currency_b) if idx_a < idx_b else (currency_b, currency_a)
    return f"{base}_{quote}"


def get_pairs_for_currency(
    currency: str, universe: list[str] = MAJOR_CURRENCIES
) -> list[str]:
    """All correctly-ordered pairs between `currency` and every other currency in `universe`."""
    return [make_pair(currency, other) for other in universe if other != currency]


def get_required_pairs(
    tracked_currencies: list[str] = TRACKED_CURRENCIES,
    universe: list[str] = MAJOR_CURRENCIES,
) -> list[str]:
    """The minimal, deduplicated set of pairs needed to score every tracked currency.

    For TRACKED_CURRENCIES = ["EUR", "USD"] against the 8 majors, this
    resolves to 13 pairs (7 each, minus 1 shared: EUR_USD).
    """
    pairs: set[str] = set()
    for currency in tracked_currencies:
        pairs.update(get_pairs_for_currency(currency, universe))
    return sorted(pairs)
