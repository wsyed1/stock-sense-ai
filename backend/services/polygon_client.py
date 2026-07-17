"""Thin client for the Polygon.io reference-news endpoint."""
import requests

import config

_NEWS_URL = "https://api.polygon.io/v2/reference/news"


class PolygonError(RuntimeError):
    """Raised when Polygon returns an error or unexpected payload."""


def fetch_news_for_ticker(ticker: str, limit: int = None) -> list:
    """Return a list of raw news-article dicts for a single ticker.

    Returns an empty list if Polygon has no news for the ticker.
    Raises PolygonError on a network/HTTP failure.
    """
    limit = limit or config.DEFAULT_NEWS_LIMIT

    try:
        response = requests.get(
            _NEWS_URL,
            params={
                "ticker": ticker,
                "limit": limit,
                "apiKey": config.get_polygon_api_key(),
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PolygonError(f"Polygon request failed for '{ticker}': {exc}") from exc

    payload = response.json()
    # Polygon returns {"results": [...]} — may be missing/empty for unknown tickers.
    return payload.get("results") or []
