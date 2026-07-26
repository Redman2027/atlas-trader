# AtlasTrader

A macro-first trading system that explains every decision it makes.

Full design background: `docs/AtlasTrader_Blueprint_v1_1.md`

## Status: v1 in progress

Built module by module. Current progress:

- [x] **Journal Engine** — SQLite-backed logging of every scored setup
      (traded or not) and every executed trade's outcome
- [x] **Macro Engine (stub)** — manually-maintained interest rate
      differential config (`config/macro_rates.json`)
- [x] **Currency Strength Matrix** — independent 0-100 strength score
      per tracked currency, computed from signed % change across a
      13-pair major currency basket (`atlas_trader/currency_strength/`)
- [x] **Technical Engine** — EMA, RSI, MACD, ATR, and candlestick
      pattern detection, all pure stdlib (`atlas_trader/technical/`)
- [x] **Voting/Confidence Engine** — weighted combination of Macro,
      Currency Strength, and Technical biases into one 0-100 confidence
      score + direction (`atlas_trader/voting/`)
- [x] **Risk Engine** — ATR-based dynamic position sizing against a
      capped effective balance, with a leverage safety clamp
      (`atlas_trader/risk/`)
- [x] **ML/Adaptation Layer** — online learning (SGD logistic
      regression, updates after every closed trade) + auto loss-cause
      classification (`atlas_trader/ml/`)
- [x] **Analytics Engine** — read-only reporting over the Journal: win
      rate, confidence-vs-outcome, loss-cause breakdown, P/L summary
      (`atlas_trader/analytics/`)
- [x] **Data Engine** — `DataProvider` interface with a working
      `MockDataProvider` (synthetic, no network) and an `OandaDataProvider`
      (written against OANDA's v20 REST API, untested until a token
      exists). `run_analysis_cycle()` orchestrates every module end to
      end (`atlas_trader/data_engine/`)

**All 9 modules exist, are wired together, and have been proven against
real live OANDA data** (not just synthetic). The Journal Engine is now
also automatically called by the loop below — nothing needs manual
wiring anymore.

## The Loop — `run_loop.py`

This is what actually runs 24/5 on the dedicated PC. Each cycle:
checks any open trade for a close (and lets the ML layer learn from
it immediately), then runs one full analysis pass and opens a trade
if warranted (skipping if already in a position).

```bash
python run_loop.py --mock     # synthetic data, no credentials needed
python run_loop.py            # real OANDA data (needs config/oanda_credentials.json)
```

**Windows deployment (once ready to run continuously):**
- **Task Scheduler** — simplest option. Create a task that runs
  `python run_loop.py` at startup, set it to restart on failure.
- **NSSM** (nssm.cc) — installs it as a real Windows service; more
  robust, survives reboots more gracefully, runs invisibly.
- Either way, disable sleep/screen-off in Windows power settings so
  the PC never pauses itself.

`atlas_trader/loop.py` also exposes `is_market_open()` (simplified
weekday/UTC-hour check — doesn't account for holidays) and
`run_one_cycle()` / `check_open_trades()` if you want to run things
manually or step through a single cycle for debugging.

Sentiment Engine and a live news/calendar feed are deferred to v2.

## Project layout

```
atlas_trader/
├── atlas_trader/
│   ├── __init__.py
│   ├── journal/
│   │   ├── __init__.py
│   │   ├── db.py            # SQLite connection + schema
│   │   ├── models.py        # Setup / Trade dataclasses
│   │   └── repository.py    # log_setup, open_trade, close_trade, etc.
│   ├── macro/
│   │   ├── __init__.py
│   │   └── engine.py        # compute_macro_bias() from the rate config
│   ├── currency_strength/
│   │   ├── __init__.py
│   │   ├── pairs.py         # FX pair conventions, currency universe
│   │   └── calculator.py    # compute_currency_strength(), scoring math
│   ├── technical/
│   │   ├── __init__.py
│   │   ├── indicators.py    # EMA, RSI, MACD, ATR (pure stdlib)
│   │   ├── patterns.py      # candlestick pattern detection
│   │   └── engine.py        # analyze_candles(), compute_technical_bias()
│   ├── voting/
│   │   ├── __init__.py
│   │   └── engine.py        # combine_biases(), score_setup()
│   ├── risk/
│   │   ├── __init__.py
│   │   └── engine.py        # compute_position_size(), compute_trade_plan()
│   ├── ml/
│   │   ├── __init__.py
│   │   └── engine.py        # OnlineTradeModel, classify_loss_cause()
│   ├── analytics/
│   │   ├── __init__.py
│   │   └── engine.py        # generate_report(), win rate, confidence-vs-outcome, etc.
│   ├── data_engine/
│   │   ├── __init__.py
│   │   ├── base.py          # DataProvider abstract interface
│   │   ├── mock_provider.py # MockDataProvider — synthetic data, no network
│   │   ├── oanda_provider.py # OandaDataProvider — real v20 REST API, verified working live
│   │   └── pipeline.py      # run_analysis_cycle() — orchestrates every module
│   └── loop.py               # is_market_open(), run_one_cycle(), run_forever()
├── run_loop.py               # entry point — run this on the PC (--mock for testing)
├── config/
│   ├── macro_rates.json     # manually-updated Fed/ECB rate + stance table
│   └── oanda_credentials.example.json  # copy to oanda_credentials.json + fill in (gitignored)
├── data/                    # atlas_trader.db lives here (gitignored)
├── docs/
│   └── AtlasTrader_Blueprint_v1_1.md
├── tests/
│   ├── test_journal_smoke.py
│   ├── test_currency_strength_smoke.py
│   ├── test_technical_engine_smoke.py
│   ├── test_voting_engine_smoke.py
│   ├── test_risk_engine_smoke.py
│   ├── test_ml_engine_smoke.py
│   ├── test_analytics_engine_smoke.py
│   ├── test_data_engine_smoke.py
│   └── test_loop_smoke.py
├── requirements.txt
└── .gitignore
```

## Setup (on the dedicated PC)

```bash
git clone <your-repo-url>
cd atlas_trader
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Initialize the journal database:

```bash
python -m atlas_trader.journal.db
```

Run the smoke test to confirm everything works:

```bash
python tests/test_journal_smoke.py
```

## Journal Engine schema

**`setups`** — every trade opportunity scored above the minimum
confidence threshold, whether or not it was traded. `feature_snapshot`
stores the full module output (macro bias, currency strength, technical
readings, candlestick pattern) as JSON, so any decision can be
reconstructed and explained later.

**`trades`** — the actual execution record for a `Setup` that was
traded. Stays `open` until closed, at which point P/L, outcome grade,
and (for losses) an auto-classified `loss_cause` get filled in by the
ML/Adaptation Layer.

## Macro Engine (v1 stub)

`config/macro_rates.json` holds the current Fed and ECB rate + stance
(hawkish/neutral/dovish) — update it manually after each rate decision.
Central bank meetings are infrequent (~8x/year) so this doesn't need a
live feed to stay accurate; it just needs you to update it after each
meeting. It's wired to plug into the Voting/Confidence Engine as a
directional bias input.

## Currency Strength Matrix

Computes an independent 0-100 strength score per tracked currency
(currently EUR and USD), centered at 50 (neutral). For each tracked
currency, it averages the signed % price change across all 7 pairs
that currency forms against the other major currencies (EUR, GBP,
AUD, NZD, USD, CAD, CHF, JPY) — 13 unique pairs total for EUR+USD.

This module is data-source agnostic: it takes a plain
`{pair_symbol: pct_change}` dict and returns scores. It doesn't fetch
prices itself — that's the Data Engine's job once built. Both `raw`
(the actual average % move) and `score` (the scaled 0-100 value) are
returned together, so the Journal's feature_snapshot always shows the
real number behind the score, not just the final figure.

```python
from atlas_trader.currency_strength import get_required_pairs, compute_currency_strength

pairs_needed = get_required_pairs()  # 13 pairs for EUR + USD
# pair_changes = {...}  # fill in from the Data Engine
result = compute_currency_strength(pair_changes)
# {"EUR": {"raw": 0.25, "score": 62.5}, "USD": {"raw": -0.04, "score": 47.93}}
```

## Technical Engine

Pure stdlib (no pandas/numpy/ta dependency yet) — takes a list of
candle dicts (oldest first: `{"open", "high", "low", "close"}`) and
returns EMA, RSI, MACD, ATR, and the detected candlestick pattern in
one call:

```python
from atlas_trader.technical import analyze_candles

# candles = [...]  # fill in from the Data Engine
result = analyze_candles(candles)
# {
#   "ema": {"period": 20, "value": 1.0927, "trend": "up"},
#   "rsi": {"period": 14, "value": 68.0},
#   "macd": {"macd_line": .., "signal_line": .., "histogram": .., "cross": "none"},
#   "atr": {"period": 14, "value": 0.0011},
#   "pattern": "none",
# }
```

Candlestick pattern detection (`patterns.py`) currently covers bullish/
bearish engulfing, doji, hammer, and shooting star — each is a plain,
readable geometric check on candle bodies/wicks, not a black-box
classifier, so a flagged pattern can always be traced back to the
exact numbers that triggered it.

## Macro Engine

`atlas_trader/macro/engine.py` reads `config/macro_rates.json` and
converts the stance (hawkish/neutral/dovish) difference + rate
differential between two currencies into a -100..100 bias:

```python
from atlas_trader.macro import compute_macro_bias

result = compute_macro_bias("EUR", "USD")
# {"base_stance": "hawkish", "quote_stance": "hawkish", "stance_diff": 0,
#  "rate_diff": -1.5, "bias": -15.0}
```

## Voting/Confidence Engine

Combines Macro, Currency Strength, and Technical biases — all on the
same -100..100 scale — into one weighted composite score. The
magnitude becomes the confidence score (0-100); the sign becomes the
direction. Default weights: macro 25%, currency strength 25%,
technical 50% (technical weighted highest since it's the actual entry
trigger on the 5M chart; easy to retune in `DEFAULT_WEIGHTS`).

```python
from atlas_trader.voting import score_setup

result = score_setup(macro_result, currency_strength_result, technical_bias_result)
# {
#   "direction": "long",
#   "confidence_score": 66.23,
#   "composite_bias": 66.23,
#   "should_log": True,
#   "should_trade": True,
#   "components": {...}   # full breakdown -> feeds straight into feature_snapshot
# }
```

Two thresholds control behavior: `MIN_LOG_THRESHOLD` (40 by default —
setups at or above this get journaled, traded or not) and
`TRADE_THRESHOLD` (65 by default — setups at or above this get
executed). When modules agree, their biases reinforce each other into
a high score; when they disagree, they cancel out into a low one —
that's the actual "voting."

## Risk Engine

ATR-based dynamic position sizing against the capped effective balance
(`min(real_balance, balance_cap)`). Defaults: 1% risk per trade,
stop-loss = 1.5x ATR, take-profit = 1.5x the stop distance (1.5:1
reward:risk), and a 20:1 max-leverage safety clamp so an unusually
tight ATR reading can never demand an oversized position. All defaults
live at the top of `atlas_trader/risk/engine.py` and are easy to retune.

```python
from atlas_trader.risk import compute_trade_plan

plan = compute_trade_plan(
    direction="long",       # from the Voting Engine's output
    entry_price=1.0850,
    atr=0.0007,              # from the Technical Engine
    account_balance=100_000, # real account balance
    balance_cap=2_000,       # effective balance is capped here
)
# {
#   "direction": "long", "entry_price": 1.085,
#   "stop_loss": 1.08395, "take_profit": 1.08658,
#   "position_size_units": 19047,
#   "sizing_detail": {...}   # full breakdown for the Journal's feature_snapshot
# }
```

Assumes the account currency matches the traded pair's quote currency
(true for a USD account trading EUR_USD) — see the docstring in
`risk/engine.py` if that ever changes.

## Analytics Engine

Read-only reporting over the Journal — one function call gets you a
full snapshot:

```python
from atlas_trader.journal import get_connection
from atlas_trader.analytics import generate_report

conn = get_connection()
report = generate_report(conn)
# {
#   "total_setups_logged": ..., "total_trades_opened": ..., "open_trades": ...,
#   "win_rate": {"total_closed": .., "wins": .., "losses": .., "win_rate": 0.6},
#   "confidence_vs_outcome": {"avg_confidence_wins": 75.0, "avg_confidence_losses": 43.5, ...},
#   "loss_cause_breakdown": {"technical_misread": 1, "macro_misread": 1},
#   "pnl_summary": {"total_pnl": .., "avg_pnl": .., "best_trade": .., "worst_trade": ..},
# }
```

`confidence_vs_outcome` is the most important number here — if the
Voting Engine's confidence score is actually meaningful, winning
trades should consistently average a higher confidence score than
losing trades. If that ever inverts once real trades are flowing,
that's the signal something upstream needs attention.

## Data Engine

`DataProvider` is the abstract interface every price source implements:
`get_candles()`, `get_current_price()`, `get_account_balance()`. No
other module ever talks to OANDA (or anything else) directly — this is
what makes swapping mock data for real data a zero-rework change.

**`MockDataProvider`** — synthetic, deterministic (same seed = same
data every time), no network. This is what proves the whole pipeline
end to end right now:

```python
from atlas_trader.data_engine import MockDataProvider, run_analysis_cycle

provider = MockDataProvider(seed=1)
result = run_analysis_cycle(provider)
# result["voting"] -> direction, confidence_score, should_trade, components (full breakdown)
# result["trade_plan"] -> None, or a full Risk Engine plan if should_trade is True
```

**`OandaDataProvider`** — real OANDA v20 REST API implementation.
Written against OANDA's documented API structure but **untested until
a real token exists** (no credentials were available while building
this). To connect it once you have a token:

1. `pip install requests` (if not already installed)
2. Copy `config/oanda_credentials.example.json` to
   `config/oanda_credentials.json` and fill in your real `api_token`
   and `account_id` (this file is gitignored — it will never be
   committed)
3. Swap the provider in your code:
   ```python
   from atlas_trader.data_engine import OandaDataProvider, run_analysis_cycle
   provider = OandaDataProvider.from_config()
   result = run_analysis_cycle(provider)
   ```

`get_candles()` works whether the market is open or closed — OANDA
always returns the last completed candles either way, which is exactly
what's needed for testing outside market hours.

## Uploading to GitHub

```bash
cd atlas_trader
git init
git add .
git commit -m "Journal Engine + Macro Engine stub"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```
