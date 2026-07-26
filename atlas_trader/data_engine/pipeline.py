"""
Analysis pipeline — orchestrates every module through a DataProvider.

This is the "main loop" body: given any DataProvider (Mock or OANDA),
fetch the data every module needs, run them in sequence, and return
one fully explainable result ready for the Journal. Nothing in here
knows or cares whether the data came from OANDA or a mock — that's the
entire point of the DataProvider interface.
"""

from __future__ import annotations

from atlas_trader.currency_strength import compute_currency_strength, get_required_pairs
from atlas_trader.macro import compute_macro_bias
from atlas_trader.risk import compute_trade_plan
from atlas_trader.technical import analyze_candles, compute_technical_bias
from atlas_trader.voting import score_setup

from .base import DataProvider

ENTRY_GRANULARITY = "M5"
ENTRY_CANDLE_COUNT = 60
STRENGTH_LOOKBACK_CANDLES = 20


def _pct_change(candles: list[dict]) -> float:
    """% change from the first to the last candle's close, in percentage points."""
    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]
    return (last_close - first_close) / first_close * 100.0


def run_analysis_cycle(
    provider: DataProvider,
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    entry_pair: str = "EUR_USD",
    balance_cap: float = 2_000.0,
    min_log_threshold: float | None = None,
    trade_threshold: float | None = None,
) -> dict:
    """Run one full pass: fetch data -> Technical -> Currency Strength ->
    Macro -> Voting -> (if should_trade) Risk.

    Returns a dict with every module's output plus a `trade_plan`
    (None unless the setup cleared the trade threshold) — everything
    needed to log a Setup (and a Trade, if one was taken) to the Journal.
    """
    # 1. Technical Engine — 5M candles for the traded pair
    entry_candles = provider.get_candles(entry_pair, ENTRY_GRANULARITY, ENTRY_CANDLE_COUNT)
    technical_result = analyze_candles(entry_candles)
    technical_bias_result = compute_technical_bias(technical_result)

    # 2. Currency Strength Matrix — needs the full pair basket
    required_pairs = get_required_pairs([tracked_base, tracked_quote])
    pair_pct_changes = {
        pair: _pct_change(provider.get_candles(pair, ENTRY_GRANULARITY, STRENGTH_LOOKBACK_CANDLES))
        for pair in required_pairs
    }
    currency_strength_result = compute_currency_strength(pair_pct_changes)

    # 3. Macro Engine — no data provider needed, reads the rate config file
    macro_result = compute_macro_bias(tracked_base, tracked_quote)

    # 4. Voting/Confidence Engine
    voting_kwargs = {}
    if min_log_threshold is not None:
        voting_kwargs["min_log_threshold"] = min_log_threshold
    if trade_threshold is not None:
        voting_kwargs["trade_threshold"] = trade_threshold

    voting_result = score_setup(
        macro_result,
        currency_strength_result,
        technical_bias_result,
        tracked_base=tracked_base,
        tracked_quote=tracked_quote,
        **voting_kwargs,
    )

    result = {
        "pair": entry_pair,
        "timeframe": ENTRY_GRANULARITY,
        "technical": technical_result,
        "currency_strength": currency_strength_result,
        "macro": macro_result,
        "voting": voting_result,
        "trade_plan": None,
    }

    # 5. Risk Engine — only runs if the setup clears the trade threshold
    if voting_result["should_trade"]:
        entry_price = provider.get_current_price(entry_pair)
        account_balance = provider.get_account_balance()
        atr = technical_result["atr"]["value"]
        result["trade_plan"] = compute_trade_plan(
            direction=voting_result["direction"],
            entry_price=entry_price,
            atr=atr,
            account_balance=account_balance,
            balance_cap=balance_cap,
        )

    return result
