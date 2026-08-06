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
STRENGTH_LOOKBACK_CANDLES = 144

# Higher-timeframe trend context — reuses the same Technical Engine math
# on 4H and 1D candles, so a strong 5M bounce can't force a trade against
# an obvious daily/4H trend. 50 candles gives MACD's signal line (needs
# 26+9=35 minimum) comfortable room to warm up.
TREND_4H_GRANULARITY = "H4"
TREND_1D_GRANULARITY = "D"
TREND_1H_GRANULARITY = "H1"
TREND_CANDLE_COUNT = 50


def _pct_change(candles: list[dict]) -> float:
    """% change from the first to the last candle's close, in percentage points.

    Returns 0.0 (neutral — no signal) if there aren't at least 2
    candles to compare. This happens at the very edges of a backtest's
    historical data — e.g. if different pairs' cached history windows
    don't perfectly align (fetched at different times, so their
    "3 months back" start points differ slightly) — rather than
    crashing on an empty list.
    """
    if len(candles) < 2:
        return 0.0
    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]
    return (last_close - first_close) / first_close * 100.0


def run_analysis_cycle(
    provider: DataProvider,
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    entry_pair: str = "EUR_USD",
    balance_cap: float | None = None,
    min_log_threshold: float | None = None,
    trade_threshold: float | None = None,
    pair_pct_changes: dict[str, float] | None = None,
) -> dict:
    """Run one full pass: fetch data -> Technical -> Currency Strength ->
    Macro -> Voting -> (if should_trade) Risk.

    `pair_pct_changes`, if supplied, skips fetching the Currency Strength
    basket and reuses this pre-fetched data instead — this is what lets
    multiple tracked pairs share a single fetch of the (mostly
    overlapping) 8-major basket in one cycle, instead of each pair
    re-fetching nearly the same data. If omitted, fetches it directly
    (the original single-pair behavior, unchanged).

    Returns a dict with every module's output plus a `trade_plan`
    (None unless the setup cleared the trade threshold) — everything
    needed to log a Setup (and a Trade, if one was taken) to the Journal.
    """
    # 1. Technical Engine — 5M candles for the traded pair (entry trigger)
    entry_candles = provider.get_candles(entry_pair, ENTRY_GRANULARITY, ENTRY_CANDLE_COUNT)
    technical_result = analyze_candles(entry_candles)
    technical_bias_result = compute_technical_bias(technical_result)

    # 1b. Higher-timeframe trend context — 4H and 1D, using the same
    # Technical Engine math so results stay directly comparable to the
    # 5M entry-timeframe bias.
    candles_4h = provider.get_candles(entry_pair, TREND_4H_GRANULARITY, TREND_CANDLE_COUNT)
    trend_4h_technical = analyze_candles(candles_4h)
    trend_4h_result = compute_technical_bias(trend_4h_technical)

    candles_1d = provider.get_candles(entry_pair, TREND_1D_GRANULARITY, TREND_CANDLE_COUNT)
    trend_1d_technical = analyze_candles(candles_1d)
    trend_1d_result = compute_technical_bias(trend_1d_technical)

    candles_1h = provider.get_candles(entry_pair, TREND_1H_GRANULARITY, TREND_CANDLE_COUNT)
    trend_1h_technical = analyze_candles(candles_1h)
    trend_1h_result = compute_technical_bias(trend_1h_technical)

    # 2. Currency Strength Matrix — needs the full pair basket
    if pair_pct_changes is None:
        required_pairs = get_required_pairs([tracked_base, tracked_quote])
        pair_pct_changes = {
            pair: _pct_change(provider.get_candles(pair, ENTRY_GRANULARITY, STRENGTH_LOOKBACK_CANDLES))
            for pair in required_pairs
        }
    currency_strength_result = compute_currency_strength(
        pair_pct_changes, tracked_currencies=[tracked_base, tracked_quote]
    )

    # 3. Macro Engine — reads the rate config file, but needs the current
    # simulated/real date to look up rates as of that point in time
    trade_date = provider.get_current_time()
    macro_result = compute_macro_bias(tracked_base, tracked_quote, trade_date)

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
        trend_4h_result=trend_4h_result,
        trend_1d_result=trend_1d_result,
        trend_1h_result=trend_1h_result,
        **voting_kwargs,
    )

    result = {
        "pair": entry_pair,
        "timeframe": ENTRY_GRANULARITY,
        "technical": technical_result,
        "trend_4h": trend_4h_technical,
        "trend_1d": trend_1d_technical,
        "trend_1h": trend_1h_technical,
        "currency_strength": currency_strength_result,
        "macro": macro_result,
        "voting": voting_result,
        "trade_plan": None,
    }

    # 5. Risk Engine — only runs if the setup clears the trade threshold
    # AND the ATR is actually available (it's None during the first ~15
    # candles of any run/backtest, before there's enough data to compute
    # it — trying to size a position off no volatility reading isn't
    # safe, so skip trading rather than crash or guess).
    atr = technical_result["atr"]["value"]
    if voting_result["should_trade"] and atr is not None:
        entry_price = provider.get_current_price(entry_pair)
        account_balance = provider.get_account_balance()
        result["trade_plan"] = compute_trade_plan(
            direction=voting_result["direction"],
            entry_price=entry_price,
            atr=atr,
            account_balance=account_balance,
            balance_cap=balance_cap,
        )

    return result
