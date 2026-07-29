"""
Multi-pair orchestration — runs run_analysis_cycle() for several
tracked pairs in a single cycle, fetching the Currency Strength
basket only ONCE and sharing it across all of them.

Why this matters: EUR_USD and GBP_USD both need USD's pairs; adding
more tracked pairs from the same currency family (EUR/GBP/USD/JPY)
means heavy overlap in what the Currency Strength Matrix needs to
fetch. Fetching the union once here, instead of each pair re-fetching
almost the same data independently, keeps the added API cost of extra
pairs small.
"""

from __future__ import annotations

from atlas_trader.currency_strength import get_required_pairs

from .base import DataProvider
from .pipeline import ENTRY_GRANULARITY, STRENGTH_LOOKBACK_CANDLES, _pct_change, run_analysis_cycle


class PairConfig:
    """One tracked pair's identity: its OANDA symbol plus its two currencies."""

    def __init__(self, entry_pair: str, tracked_base: str, tracked_quote: str):
        self.entry_pair = entry_pair
        self.tracked_base = tracked_base
        self.tracked_quote = tracked_quote

    def __repr__(self) -> str:
        return f"PairConfig({self.entry_pair}, {self.tracked_base}/{self.tracked_quote})"


def run_multi_pair_cycle(
    provider: DataProvider,
    pairs: list[PairConfig],
    balance_cap: float | None = None,
    min_log_threshold: float | None = None,
    trade_threshold: float | None = None,
) -> dict[str, dict]:
    """Run one full cycle for every pair in `pairs`, sharing a single
    fetch of the Currency Strength basket across all of them.

    Returns {entry_pair_symbol: run_analysis_cycle_result}.
    """
    all_currencies = sorted({c for p in pairs for c in (p.tracked_base, p.tracked_quote)})
    shared_required_pairs = get_required_pairs(all_currencies)
    shared_pair_pct_changes = {
        pair: _pct_change(provider.get_candles(pair, ENTRY_GRANULARITY, STRENGTH_LOOKBACK_CANDLES))
        for pair in shared_required_pairs
    }

    results: dict[str, dict] = {}
    for pair_config in pairs:
        results[pair_config.entry_pair] = run_analysis_cycle(
            provider,
            tracked_base=pair_config.tracked_base,
            tracked_quote=pair_config.tracked_quote,
            entry_pair=pair_config.entry_pair,
            balance_cap=balance_cap,
            min_log_threshold=min_log_threshold,
            trade_threshold=trade_threshold,
            pair_pct_changes=shared_pair_pct_changes,
        )
    return results
