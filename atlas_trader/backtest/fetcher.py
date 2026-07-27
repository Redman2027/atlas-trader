"""
Fetch and cache historical OANDA candles for backtesting.

Written against OANDA's documented v20 candles endpoint, same as
oanda_provider.py — untested against a live token in this environment
(no network access here), but follows the same pagination approach
OANDA's own docs describe: request up to 5000 candles at a time,
advance the `from` cursor past the last candle received, repeat until
reaching the desired end date.

Results are cached to disk (data/historical/) so re-running a backtest
doesn't re-download the same months of data every time.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from atlas_trader.data_engine.oanda_provider import BASE_URLS, load_credentials

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "historical"
MAX_CANDLES_PER_REQUEST = 5000


def _parse_oanda_time(time_str: str) -> datetime:
    """OANDA timestamps look like '2026-07-26T21:30:00.000000000Z'
    (nanosecond precision) — Python's datetime only handles up to
    microseconds, so truncate the fractional part before parsing."""
    if time_str.endswith("Z"):
        time_str = time_str[:-1] + "+00:00"
    if "." in time_str:
        head, rest = time_str.split(".", 1)
        frac_digits = "".join(ch for ch in rest if ch.isdigit())[:6]
        tz_part = rest[len(rest) - 6 :] if "+" in rest[-6:] else "+00:00"
        time_str = f"{head}.{frac_digits}{tz_part}"
    return datetime.fromisoformat(time_str)


def fetch_historical_candles(
    pair: str,
    granularity: str,
    start: datetime,
    end: datetime,
    api_token: str,
    environment: str = "practice",
) -> list[dict]:
    """Fetch all completed candles for `pair`/`granularity` between
    `start` and `end`, paginating in chunks of up to 5000."""
    base_url = BASE_URLS[environment]
    headers = {"Authorization": f"Bearer {api_token}"}
    url = f"{base_url}/v3/instruments/{pair}/candles"

    all_candles: list[dict] = []
    cursor = start

    while cursor < end:
        params = {
            "granularity": granularity,
            "price": "M",
            "from": cursor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": MAX_CANDLES_PER_REQUEST,
        }
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        candles = data.get("candles", [])
        if not candles:
            break

        for c in candles:
            if not c.get("complete", True):
                continue
            mid = c["mid"]
            all_candles.append(
                {
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "time": c["time"],
                }
            )

        last_time = _parse_oanda_time(candles[-1]["time"])
        if last_time <= cursor:
            break  # safety net against an infinite loop
        cursor = last_time + timedelta(seconds=1)
        if last_time >= end:
            break

    return [c for c in all_candles if _parse_oanda_time(c["time"]) <= end]


def fetch_and_cache(
    pairs: list[str],
    granularities: list[str],
    months: int = 3,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    credentials_path=None,
) -> dict[tuple[str, str], list[dict]]:
    """Fetch (or load from cache) historical candles for every
    pair/granularity combination a backtest needs."""
    creds = load_credentials(credentials_path) if credentials_path else load_credentials()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=months * 30)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    result: dict[tuple[str, str], list[dict]] = {}
    for pair in pairs:
        for granularity in granularities:
            cache_file = cache_dir / f"{pair}_{granularity}_{months}mo.json"
            if cache_file.exists():
                with open(cache_file, "r") as f:
                    candles = json.load(f)
                result[(pair, granularity)] = candles
                print(f"Loaded {pair} {granularity} from cache ({len(candles)} candles)")
                continue

            print(f"Fetching {pair} {granularity} from {start.date()} to {end.date()}...")
            candles = fetch_historical_candles(
                pair,
                granularity,
                start,
                end,
                api_token=creds["api_token"],
                environment=creds.get("environment", "practice"),
            )
            result[(pair, granularity)] = candles
            with open(cache_file, "w") as f:
                json.dump(candles, f)
            print(f"  Got {len(candles)} candles, cached to {cache_file}")

    return result
