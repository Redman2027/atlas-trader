"""
Smoke test for the Risk Engine.

Run directly:

    python tests/test_risk_engine_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.risk import compute_position_size, compute_trade_plan


def test_normal_case_uses_the_cap():
    """Real balance well above the cap -> effective balance should be the cap."""
    result = compute_position_size(
        account_balance=100_000,
        balance_cap=2_000,
        atr=0.0007,
        entry_price=1.0850,
    )
    print("Normal case:", result)

    assert result["effective_balance"] == 2_000
    assert result["risk_amount"] == 20.0  # 1% of 2000
    assert result["leverage_capped"] is False
    assert result["position_size_units"] > 0


def test_balance_below_cap_uses_real_balance():
    """Real balance smaller than the cap -> effective balance should be the real balance."""
    result = compute_position_size(
        account_balance=1_000,
        balance_cap=2_000,
        atr=0.0007,
        entry_price=1.0850,
    )
    print("Below-cap case:", result)

    assert result["effective_balance"] == 1_000
    assert result["risk_amount"] == 10.0  # 1% of 1000


def test_leverage_clip_kicks_in_on_tiny_atr():
    """A very tight ATR would otherwise demand an oversized position -> leverage cap should clip it."""
    result = compute_position_size(
        account_balance=100_000,
        balance_cap=2_000,
        atr=0.00005,  # unusually tight, to force a large raw position size
        entry_price=1.0850,
    )
    print("Leverage-clip case:", result)

    assert result["leverage_capped"] is True
    max_position_value = result["effective_balance"] * result["max_leverage"]
    implied_value = result["position_size_units"] * 1.0850
    assert implied_value <= max_position_value + 1  # small rounding tolerance


def test_full_trade_plan_long_and_short():
    common_args = dict(
        entry_price=1.0850,
        atr=0.0007,
        account_balance=100_000,
        balance_cap=2_000,
    )

    long_plan = compute_trade_plan(direction="long", **common_args)
    print("Long trade plan:", long_plan)
    assert long_plan["stop_loss"] < long_plan["entry_price"]
    assert long_plan["take_profit"] > long_plan["entry_price"]

    short_plan = compute_trade_plan(direction="short", **common_args)
    print("Short trade plan:", short_plan)
    assert short_plan["stop_loss"] > short_plan["entry_price"]
    assert short_plan["take_profit"] < short_plan["entry_price"]

    # Reward should be 1.5x the risk distance by default
    long_risk = long_plan["entry_price"] - long_plan["stop_loss"]
    long_reward = long_plan["take_profit"] - long_plan["entry_price"]
    assert abs(long_reward - (long_risk * 1.5)) < 1e-4


if __name__ == "__main__":
    test_normal_case_uses_the_cap()
    test_balance_below_cap_uses_real_balance()
    test_leverage_clip_kicks_in_on_tiny_atr()
    test_full_trade_plan_long_and_short()
    print("Risk Engine smoke test passed.")
