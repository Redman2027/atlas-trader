"""
OandaDataProvider — real OANDA v20 REST API implementation.

Untested against a live token as of this writing (no credentials
available yet) — written directly against OANDA's documented v20 REST
API. The moment a token exists, this can be dropped in wherever
MockDataProvider is currently used with zero changes to any other
module — that's the entire point of the DataProvider interface.

Credentials are never hardcoded or committed. Load them from
config/oanda_credentials.json (gitignored — see
config/oanda_credentials.example.json for the expected format).
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

from .base import DataProvider

DEFAULT_CREDENTIALS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "oanda_credentials.json"
)

BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def load_credentials(path: Path | str = DEFAULT_CREDENTIALS_PATH) -> dict:
    """Load {"api_token": ..., "account_id": ..., "environment": "practice"}."""
    with open(path, "r") as f:
        return json.load(f)


class OandaDataProvider(DataProvider):
    def __init__(self, api_token: str, account_id: str, environment: str = "practice"):
        if environment not in BASE_URLS:
            raise ValueError(f"environment must be 'practice' or 'live', got: {environment!r}")
        self.api_token = api_token
        self.account_id = account_id
        self.environment = environment
        self.base_url = BASE_URLS[environment]
        self._headers = {"Authorization": f"Bearer {api_token}"}

    @classmethod
    def from_config(cls, path: Path | str = DEFAULT_CREDENTIALS_PATH) -> "OandaDataProvider":
        creds = load_credentials(path)
        return cls(
            api_token=creds["api_token"],
            account_id=creds["account_id"],
            environment=creds.get("environment", "practice"),
        )

    def get_candles(self, pair: str, granularity: str, count: int) -> list[dict]:
        """Fetch completed candles. Works whether the market is open or
        closed — returns the last completed candles either way."""
        url = f"{self.base_url}/v3/instruments/{pair}/candles"
        params = {"count": count, "granularity": granularity, "price": "M"}
        response = requests.get(url, headers=self._headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        candles = []
        for c in data["candles"]:
            if not c.get("complete", True):
                continue  # skip the still-forming current candle
            mid = c["mid"]
            candles.append(
                {
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "time": c["time"],
                }
            )
        return candles

    def get_current_price(self, pair: str) -> float:
        """Current mid price. Only meaningful while the market is open;
        while closed, prefer get_candles() for the last completed price."""
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing"
        params = {"instruments": pair}
        response = requests.get(url, headers=self._headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        price_info = data["prices"][0]
        bid = float(price_info["bids"][0]["price"])
        ask = float(price_info["asks"][0]["price"])
        return round((bid + ask) / 2, 5)

    def get_account_balance(self) -> float:
        url = f"{self.base_url}/v3/accounts/{self.account_id}/summary"
        response = requests.get(url, headers=self._headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return float(data["account"]["balance"])
