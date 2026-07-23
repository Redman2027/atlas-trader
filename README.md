# AtlasTrader

A macro-first trading system that explains every decision it makes.

Full design background: `docs/AtlasTrader_Blueprint_v1_1.md`

## Status: v1 in progress

Built module by module. Current progress:

- [x] **Journal Engine** — SQLite-backed logging of every scored setup
      (traded or not) and every executed trade's outcome
- [x] **Macro Engine (stub)** — manually-maintained interest rate
      differential config (`config/macro_rates.json`)
- [ ] Currency Strength Matrix
- [ ] Technical Engine (EMA, RSI, MACD, ATR, candlestick patterns)
- [ ] Voting/Confidence Engine
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
│   └── journal/
│       ├── __init__.py
│       ├── db.py            # SQLite connection + schema
│       ├── models.py        # Setup / Trade dataclasses
│       └── repository.py    # log_setup, open_trade, close_trade, etc.
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
