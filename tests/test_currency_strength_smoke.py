"""
Smoke test for the Currency Strength Matrix.

Run directly:

    python tests/test_currency_strength_smoke.py

Uses synthetic pct_change data (not real prices) just to prove the
math is internally consistent: if EUR is genuinely stronger than USD
across the board, EUR's score should land above 50 and USD's below it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.currency_strength import (
    get_required_pairs,
    compute_currency_strength,
)


def run() -> None:
    required_pairs = get_required_pairs()
    print(f"Pairs required for EUR + USD strength: {required_pairs}")
    assert len(required_pairs) == 13, "Expected 13 unique pairs for EUR+USD vs 8 majors"

    # Synthetic scenario: EUR broadly strong, USD broadly weak.
    # Positive pct_change means the FIRST currency in the pair name
    # strengthened (e.g. EUR_USD +0.40 means EUR gained vs USD).
    synthetic_changes = {
        "EUR_USD": 0.40,
        "EUR_GBP": 0.15,
        "EUR_AUD": 0.25,
        "EUR_NZD": 0.30,
        "EUR_CAD": 0.20,
        "EUR_CHF": 0.10,
        "EUR_JPY": 0.35,
        "GBP_USD": 0.05,
        "AUD_USD": -0.10,
        "NZD_USD": -0.05,
        "USD_CAD": -0.05,   # negative = USD weakened vs CAD
        "USD_CHF": -0.02,
        "USD_JPY": 0.08,
    }

    result = compute_currency_strength(synthetic_changes)
    print("Currency strength result:", result)

    assert result["EUR"]["score"] > 50, "EUR should score above neutral in this scenario"
    assert result["USD"]["score"] < 50, "USD should score below neutral in this scenario"
    assert result["EUR"]["score"] > result["USD"]["score"], "EUR should outscore USD"

    print("Currency Strength Matrix smoke test passed.")


if __name__ == "__main__":
    run()
