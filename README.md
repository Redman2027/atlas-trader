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
- [ ] Risk Engine (ATR-based sizing, capped effective balance)
- [ ] ML/Adaptation Layer (online learning, auto loss-cause classification)
- [ ] Analytics Engine
- [ ] Data Engine (OANDA v20 API integration)

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
│   └── voting/
│       ├── __init__.py
│       └── engine.py        # combine_biases(), score_setup()
├── config/
│   └── macro_rates.json     # manually-updated Fed/ECB rate + stance table
├── data/                    # atlas_trader.db lives here (gitignored)
├── docs/
│   └── AtlasTrader_Blueprint_v1_1.md
├── tests/
│   └── test_journal_smoke.py
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
