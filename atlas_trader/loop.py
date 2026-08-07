"""
The AtlasTrader loop — the piece that turns 9 tested modules into an
actual running system.

`run_forever()` is what should run 24/5 on the dedicated PC. Each pass:

1. Checks any currently-open trade for a close (Journal + broker) —
   if closed, records the outcome and lets the ML/Adaptation Layer
   learn from it immediately.
2. Runs one full analysis cycle (Data -> Technical -> Currency
   Strength -> Macro -> Voting -> Risk).
3. Logs the setup if it clears the logging threshold.
4. Opens a trade if it clears the trading threshold AND there isn't
   already an open position (one position at a time, v1 — EURUSD only,
   so there's only ever one instrument to be in a position on anyway).

Market-hours check is intentionally simple (weekday/UTC-hour based) —
it does not account for holidays or broker-specific maintenance
windows. Good enough to avoid running against a dead weekend market;
not a substitute for checking OANDA's actual trading calendar around
holidays.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from atlas_trader.data_engine import DataProvider, PairConfig, run_analysis_cycle, run_multi_pair_cycle
from atlas_trader.journal import (
    Setup,
    Trade,
    get_connection,
    init_db,
    log_setup,
    open_trade,
    close_trade,
    get_open_trades,
    get_open_trades_for_pair,
    get_setup_with_trade,
)
from atlas_trader.ml import OnlineTradeModel, classify_loss_cause

DEFAULT_POLL_SECONDS = 300  # 5 minutes, matching the M5 entry timeframe


def is_market_open(now: datetime | None = None) -> bool:
    """Simplified forex session check: closed Saturday, closed Sunday
    before ~22:00 UTC, closed Friday after ~22:00 UTC. Doesn't account
    for holidays — check OANDA's calendar around those separately."""
    now = now or datetime.now(timezone.utc)
    weekday = now.weekday()  # Monday=0 ... Sunday=6

    if weekday == 5:  # Saturday
        return False
    if weekday == 6 and now.hour < 22:  # Sunday before 22:00 UTC
        return False
    if weekday == 4 and now.hour >= 22:  # Friday after 22:00 UTC
        return False
    return True


def check_open_trades(provider: DataProvider, conn, model: OnlineTradeModel, model_path=None) -> None:
    """Check every open trade against the broker; close and learn from any that finished."""
    for trade_row in get_open_trades(conn):
        status = provider.get_trade_status(trade_row["oanda_trade_id"])
        if status["status"] != "closed":
            continue

        pnl = status["pnl"] or 0.0
        won = pnl > 0

        setup_record = get_setup_with_trade(conn, trade_row["setup_id"])
        voting_snapshot = setup_record["feature_snapshot"]["voting"]

        loss_cause = None
        if not won:
            loss_cause = classify_loss_cause(
                {"components": voting_snapshot["components"]}, trade_row["direction"]
            )

        close_trade(
            conn,
            trade_id=trade_row["id"],
            close_price=status["close_price"] or 0.0,
            pnl=pnl,
            pnl_pct=pnl / max(abs(trade_row["position_size"]), 1),
            outcome_grade="A" if won else "F",
            loss_cause=loss_cause,
        )

        features = {
            "macro_bias": voting_snapshot["components"]["macro"]["bias"],
            "currency_strength_bias": voting_snapshot["components"]["currency_strength"]["bias"],
            "technical_bias": voting_snapshot["components"]["technical"]["bias"],
            "confidence_score": setup_record["confidence_score"],
        }
        model.update(features, won=won)
        model.save(model_path) if model_path else model.save()

        risk_amount = abs(trade_row["entry_price"] - trade_row["stop_loss"]) * trade_row["position_size"]
        r_multiple = pnl / risk_amount if risk_amount else 0.0
        print(
            f"  Trade {trade_row['id']} closed: {'WIN' if won else 'LOSS'} "
            f"pnl={pnl:.2f} risk_amount={risk_amount:.2f} r_multiple={r_multiple:.3f} loss_cause={loss_cause}"
        )
        component_biases = " ".join(
            f"{name}_bias={comp['bias']:.4f}" for name, comp in voting_snapshot["components"].items()
        )
        print(f"  Trade {trade_row['id']} components: outcome={'WIN' if won else 'LOSS'} {component_biases}")


def _log_setup_and_maybe_trade(provider: DataProvider, conn, result: dict, has_open_position: bool) -> int | None:
    """Shared logic: log the setup if it clears the log threshold, and
    open a trade if it clears the trade threshold and there's no
    existing open position for this specific pair. Used by both the
    single-pair and multi-pair cycle functions so the behavior stays
    identical either way."""
    voting = result["voting"]
    if not voting["should_log"]:
        return None

    will_trade = bool(voting["should_trade"] and result["trade_plan"] and not has_open_position)

    setup = Setup(
        pair=result["pair"],
        timeframe=result["timeframe"],
        direction=voting["direction"],
        confidence_score=voting["confidence_score"],
        feature_snapshot={
            "technical": result["technical"],
            "trend_4h": result["trend_4h"],
            "trend_1d": result["trend_1d"],
            "currency_strength": result["currency_strength"],
            "macro": result["macro"],
            "voting": voting,
        },
        traded=will_trade,
    )
    setup_id = log_setup(conn, setup)

    if will_trade:
        plan = result["trade_plan"]
        broker_trade_id = provider.place_order(
            pair=result["pair"],
            direction=plan["direction"],
            units=plan["position_size_units"],
            stop_loss=plan["stop_loss"],
            take_profit=plan["take_profit"],
        )
        trade = Trade(
            setup_id=setup_id,
            direction=plan["direction"],
            entry_price=plan["entry_price"],
            stop_loss=plan["stop_loss"],
            take_profit=plan["take_profit"],
            position_size=plan["position_size_units"],
            oanda_trade_id=broker_trade_id,
        )
        open_trade(conn, trade)
        print(f"  [{result['pair']}] Opened trade: {plan['direction']} {plan['position_size_units']} units")
    elif voting["should_trade"] and has_open_position:
        print(f"  [{result['pair']}] Signal cleared trade threshold but skipped — already in a position on this pair.")

    return setup_id


def run_one_cycle(
    provider: DataProvider,
    conn,
    model: OnlineTradeModel,
    model_path=None,
    balance_cap: float | None = None,
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    entry_pair: str = "EUR_USD",
    min_log_threshold: float | None = None,
    trade_threshold: float | None = None,
) -> dict:
    """One full pass for a SINGLE pair: check existing trades, then look
    for a new setup. For multiple pairs in one cycle, use
    run_one_cycle_multi() instead."""
    check_open_trades(provider, conn, model, model_path)

    result = run_analysis_cycle(
        provider,
        tracked_base,
        tracked_quote,
        entry_pair,
        balance_cap,
        min_log_threshold=min_log_threshold,
        trade_threshold=trade_threshold,
    )

    has_open_position = len(get_open_trades_for_pair(conn, entry_pair)) > 0
    _log_setup_and_maybe_trade(provider, conn, result, has_open_position)

    return result


def run_one_cycle_multi(
    provider: DataProvider,
    conn,
    model: OnlineTradeModel,
    pairs: list[PairConfig],
    model_path=None,
    balance_cap: float | None = None,
    min_log_threshold: float | None = None,
    trade_threshold: float | None = None,
) -> dict[str, dict]:
    """One full pass across MULTIPLE pairs: checks all open trades once
    (pair-agnostic), then runs every tracked pair's analysis — sharing
    one Currency Strength basket fetch across all of them — with each
    pair's position guard checked independently. Being long EUR_USD
    doesn't block a new position on GBP_USD; they're separate
    instruments.
    """
    check_open_trades(provider, conn, model, model_path)

    results = run_multi_pair_cycle(
        provider,
        pairs,
        balance_cap=balance_cap,
        min_log_threshold=min_log_threshold,
        trade_threshold=trade_threshold,
    )

    for pair_config in pairs:
        result = results[pair_config.entry_pair]
        has_open_position = len(get_open_trades_for_pair(conn, pair_config.entry_pair)) > 0
        _log_setup_and_maybe_trade(provider, conn, result, has_open_position)

    return results


def run_forever(
    provider: DataProvider,
    db_path=None,
    model_path=None,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    balance_cap: float | None = None,
    pairs: list[PairConfig] | None = None,
    tracked_base: str = "EUR",
    tracked_quote: str = "USD",
    entry_pair: str = "EUR_USD",
) -> None:
    """Run continuously until interrupted (Ctrl+C). This is what should
    run 24/5 on the dedicated PC.

    Pass `pairs` (a list of PairConfig) to track multiple pairs at
    once. If omitted, falls back to the original single-pair behavior
    using `tracked_base`/`tracked_quote`/`entry_pair` — fully backward
    compatible with existing single-pair setups.
    """
    init_db(db_path) if db_path else init_db()
    conn = get_connection(db_path) if db_path else get_connection()
    model = OnlineTradeModel.load(model_path) if model_path else OnlineTradeModel.load()

    print("AtlasTrader loop starting. Press Ctrl+C to stop.")
    while True:
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            if not is_market_open():
                print(f"[{timestamp}] Market closed — sleeping.")
            elif pairs:
                results = run_one_cycle_multi(
                    provider, conn, model, pairs, model_path=model_path, balance_cap=balance_cap
                )
                for pair_symbol, result in results.items():
                    voting = result["voting"]
                    print(
                        f"[{timestamp}] {pair_symbol}: confidence={voting['confidence_score']} "
                        f"direction={voting['direction']} should_trade={voting['should_trade']}"
                    )
            else:
                result = run_one_cycle(
                    provider,
                    conn,
                    model,
                    model_path=model_path,
                    balance_cap=balance_cap,
                    tracked_base=tracked_base,
                    tracked_quote=tracked_quote,
                    entry_pair=entry_pair,
                )
                voting = result["voting"]
                print(
                    f"[{timestamp}] confidence={voting['confidence_score']} "
                    f"direction={voting['direction']} should_trade={voting['should_trade']}"
                )
        except Exception as e:
            # Never let one bad cycle kill the whole loop — log it and keep going.
            print(f"[{timestamp}] Cycle error (continuing): {e}")

        time.sleep(poll_seconds)
