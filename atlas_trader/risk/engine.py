"""
Risk Engine — ATR-based dynamic position sizing, optionally against a
capped effective balance.

Core rule: if `balance_cap` is set, and the real account balance is
larger than it, size as if the account were only the cap amount. e.g.
real balance $100,000, cap $2,000 -> sized as a $2,000 account
regardless of what's actually in the account. If `balance_cap` is
None, position sizing scales with the REAL account balance directly —
money management rules (risk % per trade, the leverage safety clamp)
still fully apply either way, this only changes what "100%" means.

Stop-loss distance is a multiple of ATR (volatility-based, not a fixed
pip count), and position size is derived from how much of the
effective balance you're willing to risk on that stop distance.

Assumption made explicit: this assumes the account currency matches
the quote currency of the traded pair (true for a USD account trading
EUR_USD, since USD is the quote currency) — so P&L per unit is simply
price_change_in_quote_currency, with no currency-conversion step
needed. If you ever trade a pair where that's not true, this module
will need an added conversion-rate parameter.
"""

from __future__ import annotations

DEFAULT_RISK_PCT = 0.01          # 1% of effective balance risked per trade
DEFAULT_ATR_MULTIPLIER = 1.5     # stop-loss distance = ATR * this
DEFAULT_REWARD_RISK_RATIO = 1.5  # take-profit distance = stop-loss distance * this
DEFAULT_MAX_LEVERAGE = 20.0      # safety cap: position value can't exceed effective_balance * this


def compute_effective_balance(account_balance: float, balance_cap: float | None) -> float:
    """The smaller of the real balance and the configured cap — or the
    real balance directly if `balance_cap` is None (uncapped)."""
    if balance_cap is None:
        return account_balance
    return min(account_balance, balance_cap)


def compute_position_size(
    account_balance: float,
    balance_cap: float | None,
    atr: float,
    entry_price: float,
    risk_pct: float = DEFAULT_RISK_PCT,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    max_leverage: float = DEFAULT_MAX_LEVERAGE,
) -> dict:
    """Compute position size in units, with an explainable breakdown.

    Returns a dict with every intermediate number used, so a later
    review can always see exactly why a given size was chosen.
    """
    if atr <= 0:
        raise ValueError("ATR must be positive to compute a stop-loss distance")

    effective_balance = compute_effective_balance(account_balance, balance_cap)
    risk_amount = effective_balance * risk_pct
    stop_loss_distance = atr * atr_multiplier

    raw_position_size = risk_amount / stop_loss_distance

    max_position_value = effective_balance * max_leverage
    max_position_size = max_position_value / entry_price

    leverage_capped = raw_position_size > max_position_size
    position_size_units = min(raw_position_size, max_position_size)

    return {
        "account_balance": account_balance,
        "balance_cap": balance_cap,
        "effective_balance": effective_balance,
        "risk_pct": risk_pct,
        "risk_amount": round(risk_amount, 2),
        "atr": atr,
        "atr_multiplier": atr_multiplier,
        "stop_loss_distance": round(stop_loss_distance, 5),
        "raw_position_size": round(raw_position_size, 2),
        "max_leverage": max_leverage,
        "leverage_capped": leverage_capped,
        "position_size_units": int(position_size_units),
    }


def compute_trade_plan(
    direction: str,
    entry_price: float,
    atr: float,
    account_balance: float,
    balance_cap: float | None,
    risk_pct: float = DEFAULT_RISK_PCT,
    atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
    reward_risk_ratio: float = DEFAULT_REWARD_RISK_RATIO,
    max_leverage: float = DEFAULT_MAX_LEVERAGE,
) -> dict:
    """Full trade plan: stop-loss, take-profit, and position size, all in one place.

    `direction` must be "long" or "short" — matches the Voting/Confidence
    Engine's output directly, so its result can be passed straight through.
    """
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got: {direction!r}")

    sizing = compute_position_size(
        account_balance=account_balance,
        balance_cap=balance_cap,
        atr=atr,
        entry_price=entry_price,
        risk_pct=risk_pct,
        atr_multiplier=atr_multiplier,
        max_leverage=max_leverage,
    )

    stop_loss_distance = sizing["stop_loss_distance"]
    take_profit_distance = stop_loss_distance * reward_risk_ratio

    if direction == "long":
        stop_loss = entry_price - stop_loss_distance
        take_profit = entry_price + take_profit_distance
    else:
        stop_loss = entry_price + stop_loss_distance
        take_profit = entry_price - take_profit_distance

    return {
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": round(stop_loss, 5),
        "take_profit": round(take_profit, 5),
        "reward_risk_ratio": reward_risk_ratio,
        "position_size_units": sizing["position_size_units"],
        "sizing_detail": sizing,
    }
