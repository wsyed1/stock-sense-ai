"""Central configuration for the StockSense API.

Secrets (API keys) are read exclusively from environment variables / the .env
file — they are never hardcoded here. The .env file is git-ignored.
"""
import os
from dotenv import load_dotenv

# Load variables from APIs/.env into the environment (no-op if already set).
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


def _require(name: str) -> str:
    """Return an env var, raising a clear error if it is missing."""
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Missing required environment variable '{name}'. "
            f"Add it to APIs/.env (see .env for the expected keys)."
        )
    return value


def get_polygon_api_key() -> str:
    return _require("polygon_api_key")


def get_openai_api_key() -> str:
    return _require("openai_api_key")


# --- Application settings -------------------------------------------------

# Model used for sentiment analysis.
OPENAI_MODEL = os.getenv("openai_model", "gpt-4o-mini")

# How many news articles to pull per ticker from Polygon.
DEFAULT_NEWS_LIMIT = int(os.getenv("news_limit", "5"))

# Port the Flask app listens on.
PORT = int(os.getenv("port", "8888"))

# Whether to scrape full article text (via services.scraper_service) and feed it
# to the model, instead of relying on Polygon's short description alone. Slower
# but higher quality. Set enable_scraping=false in .env to turn off.
ENABLE_SCRAPING = os.getenv("enable_scraping", "true").lower() not in ("0", "false", "no")

# How many articles per ticker to scrape when scraping is enabled (scraping is
# the slow part, so keep this small).
SCRAPE_ARTICLES_PER_TICKER = int(os.getenv("scrape_articles_per_ticker", "2"))

# A demo watchlist used by the frontend for a one-click demo. The API itself
# does NOT default to this — callers must pass tickers explicitly. It lives
# here so the list is defined in exactly one place.
DEMO_WATCHLIST = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "GOOGL",  # Alphabet (FAANG)
    "AMZN",   # Amazon (FAANG)
    "META",   # Meta (FAANG)
    "NFLX",   # Netflix (FAANG)
    "NVDA",   # NVIDIA
    "TSLA",   # Tesla
]
