"""
Backtest runner — replays historical data through the exact same
pipeline and loop logic used for live trading (Technical, Currency
Strength, Macro, Voting, Risk, Journal, ML). No module changes needed
anywhere else — that's the entire point of building against the
DataProvider abstraction from the start.
"""

from __future__ import annotations

from atlas_trader.journal import get_connection, init_db
from atlas_trader.loop import is_market_open, run_one_cycle
from atlas_trader.ml import OnlineTradeModel

from .data_provider import HistoricalDataProvider
from .fetcher import _parse_oanda_time


def run_backtest(
    provider: HistoricalDataProvider,
    entry_pair: str = "EUR_USD",
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    balance_cap: float = 2_000.0,
    db_path=None,
    model_path=None,
    progress_every: int = 500,
    min_log_threshold: float | None = None,
    trade_threshold: float | None = None,
) -> dict:
    """Step through every M5 timestamp available for `entry_pair`,
    running one full cycle at each step — logging setups, opening/
    closing trades, and letting the ML model learn, exactly like the
    live loop does."""
    init_db(db_path) if db_path else init_db()
    conn = get_connection(db_path) if db_path else get_connection()
    model = OnlineTradeModel.load(model_path) if model_path else OnlineTradeModel.load()

    timestamps = provider.get_entry_timestamps(entry_pair)
    total_steps = len(timestamps)
    errors = 0

    for i, ts in enumerate(timestamps):
        provider.advance_to(ts)

        if not is_market_open(_parse_oanda_time(ts)):
            continue

        try:
            run_one_cycle(
                provider,
                conn,
                model,
                model_path=model_path,
                balance_cap=balance_cap,
                tracked_base=tracked_base,
                tracked_quote=tracked_quote,
                entry_pair=entry_pair,
                min_log_threshold=min_log_threshold,
                trade_threshold=trade_threshold,
            )
        except Exception as e:
            errors += 1
            if errors <= 10:  # don't flood the console if something's systematically wrong
                print(f"  Step {i}/{total_steps} error (continuing): {e}")

        if progress_every and i % progress_every == 0:
            print(f"  Progress: {i}/{total_steps} ({100 * i / max(total_steps, 1):.1f}%)")

    return {
        "final_balance": provider.get_account_balance(),
        "steps": total_steps,
        "errors": errors,
    }
