"""Thin client for Polygon.io price data.

Sibling to polygon_client (news). Uses the previous-close aggregate endpoint,
which the Polygon free tier supports (end-of-day / delayed data — NOT real
time). Each call returns the last completed trading day's OHLC for one ticker.
"""
import requests

import config

_PREV_CLOSE_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/prev"


class PriceError(RuntimeError):
    """Raised when Polygon returns an error or unexpected price payload."""


def fetch_latest_price(ticker: str) -> dict:
    """Return the previous close + day change for a single ticker.

    Shape:
        {
            "ticker": "AAPL",
            "price": 325.89,          # previous close
            "open": 327.87,
            "change": -1.98,          # close - open
            "change_pct": -0.60,      # percent, rounded to 2dp
            "as_of": 1784750400000,   # Polygon timestamp (ms) of the bar
        }

    Returns {"ticker": ..., "price": None, ...} if Polygon has no data for the
    ticker (e.g. an unknown symbol). Raises PriceError on network/HTTP failure.
    """
    symbol = ticker.strip().upper()
    try:
        response = requests.get(
            _PREV_CLOSE_URL.format(ticker=symbol),
            params={"apiKey": config.get_polygon_api_key(), "adjusted": "true"},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PriceError(f"Polygon price request failed for '{symbol}': {exc}") from exc

    payload = response.json()
    results = payload.get("results") or []
    if not results:
        return {
            "ticker": symbol,
            "price": None,
            "open": None,
            "change": None,
            "change_pct": None,
            "as_of": None,
        }

    bar = results[0]
    close = bar.get("c")
    open_ = bar.get("o")

    change = None
    change_pct = None
    if isinstance(close, (int, float)) and isinstance(open_, (int, float)) and open_:
        change = round(close - open_, 2)
        change_pct = round((close - open_) / open_ * 100, 2)

    return {
        "ticker": symbol,
        "price": round(close, 2) if isinstance(close, (int, float)) else None,
        "open": round(open_, 2) if isinstance(open_, (int, float)) else None,
        "change": change,
        "change_pct": change_pct,
        "as_of": bar.get("t"),
    }


def fetch_prices(tickers: list) -> list:
    """Fetch latest price for each ticker, preserving order and de-duplicating."""
    seen = set()
    out = []
    for raw in tickers:
        symbol = raw.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(fetch_latest_price(symbol))
    return out
