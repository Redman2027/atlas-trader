"""
Smoke test for the Data Engine — runs the full pipeline end to end
using MockDataProvider (no network, no credentials needed).

Run directly:

    python tests/test_data_engine_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.data_engine import MockDataProvider, run_analysis_cycle


def test_pipeline_runs_end_to_end():
    provider = MockDataProvider(seed=1)
    result = run_analysis_cycle(provider)

    print("Pipeline result keys:", list(result.keys()))
    print("Voting result:", result["voting"])

    assert result["pair"] == "EUR_USD"
    assert "ema" in result["technical"]
    assert "EUR" in result["currency_strength"] and "USD" in result["currency_strength"]
    assert "bias" in result["macro"]
    assert result["voting"]["direction"] in ("long", "short", "none")
    assert 0 <= result["voting"]["confidence_score"] <= 100

    if result["voting"]["should_trade"]:
        assert result["trade_plan"] is not None
        assert result["trade_plan"]["direction"] == result["voting"]["direction"]
        assert result["trade_plan"]["position_size_units"] > 0
    else:
        assert result["trade_plan"] is None


def test_reproducible_with_same_seed():
    """Same seed should produce identical results — important for reliable testing."""
    result_a = run_analysis_cycle(MockDataProvider(seed=7))
    result_b = run_analysis_cycle(MockDataProvider(seed=7))
    assert result_a["voting"]["confidence_score"] == result_b["voting"]["confidence_score"]
    assert result_a["voting"]["direction"] == result_b["voting"]["direction"]


def test_different_seeds_can_differ():
    """Sanity check that the mock isn't secretly always returning the same thing."""
    result_a = run_analysis_cycle(MockDataProvider(seed=1))
    result_b = run_analysis_cycle(MockDataProvider(seed=999))
    # Not asserting they MUST differ (could coincidentally match), just printing
    # both so a human can eyeball that the mock actually varies with the seed.
    print("Seed 1 confidence:", result_a["voting"]["confidence_score"])
    print("Seed 999 confidence:", result_b["voting"]["confidence_score"])


def test_non_default_pair_scores_correct_currencies():
    """Regression test: run_analysis_cycle with a non-default pair (EUR/CAD)
    must score EUR/CAD in the Currency Strength Matrix, not silently fall
    back to the EUR/USD default. This was a real bug once."""
    provider = MockDataProvider(seed=1)
    result = run_analysis_cycle(
        provider, tracked_base="EUR", tracked_quote="CAD", entry_pair="EUR_CAD"
    )
    assert set(result["currency_strength"].keys()) == {"EUR", "CAD"}
    assert result["macro"]["base_currency"] == "EUR"
    assert result["macro"]["quote_currency"] == "CAD"


if __name__ == "__main__":
    test_pipeline_runs_end_to_end()
    test_reproducible_with_same_seed()
    test_different_seeds_can_differ()
    test_non_default_pair_scores_correct_currencies()
    print("Data Engine smoke test passed.")
