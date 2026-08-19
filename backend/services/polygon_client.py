"""Thin client for the Polygon.io reference-news endpoint."""
import time

import requests

import config

_NEWS_URL = "https://api.polygon.io/v2/reference/news"

# In-memory cache: (ticker, limit) -> (fetched_at_monotonic, results_list).
# Per-process only — cleared on restart, not shared across workers. See
# config.NEWS_CACHE_TTL_SECONDS for the expiry window.
_cache = {}


class PolygonError(RuntimeError):
    """Raised when Polygon returns an error or unexpected payload."""


def fetch_news_for_ticker(ticker: str, limit: int = None) -> tuple:
    """Return (articles, was_cached) for a single ticker.

    articles is a list of raw news-article dicts (empty if Polygon has no news
    for the ticker). was_cached is True when this call was served from the
    in-memory cache rather than a live Polygon request.
    Raises PolygonError on a network/HTTP failure.

    Cached per (ticker, limit) for config.NEWS_CACHE_TTL_SECONDS to avoid
    re-fetching news that was just fetched moments ago (e.g. re-running the
    same or an overlapping watchlist).
    """
    limit = limit or config.DEFAULT_NEWS_LIMIT

    cache_key = (ticker, limit)
    cached = _cache.get(cache_key)
    if cached is not None:
        fetched_at, results = cached
        if time.monotonic() - fetched_at < config.NEWS_CACHE_TTL_SECONDS:
            # Return a copy: callers (sentiment_service) mutate article dicts
            # in place to attach scraped full_text, and that must not leak
            # into what other requests see as "the cached Polygon result".
            return [dict(article) for article in results], True

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
    results = payload.get("results") or []
    _cache[cache_key] = (time.monotonic(), results)
    return [dict(article) for article in results], False
