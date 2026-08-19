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

# --- Determinism knobs (temperature + seed) ------------------------------
#
# IMPORTANT: these control reproducibility for IDENTICAL input only. They do NOT
# freeze a stock's sentiment over time. There are two very different kinds of
# "change" to keep straight:
#
#   1. The news itself changing  -> a stock can read Bullish now and Bearish an
#      hour later once new articles appear. That is REAL change: the input is
#      different, so the score SHOULD differ. These settings do not touch it.
#   2. The model wobbling on the SAME news -> without determinism the model might
#      say 88 one run and 81 the next for byte-identical input. That is FAKE
#      variation (just sampling randomness), and it is what we remove here.
#
# So this does not hurt accuracy: it strips out random noise on identical input
# while leaving genuine news-driven movement fully intact. Think of it as using
# the same scale every time — the reading is repeatable, but your weight still
# changes day to day. Note OpenAI treats this as *best-effort* reproducibility,
# not an ironclad guarantee, so small drift is still possible.

# Sampling temperature for the model. 0 makes outputs (near-)deterministic, so
# the same news input yields the same sentiment scores between runs — the
# simplest lever for making the system measurable/consistent. Override in .env.
OPENAI_TEMPERATURE = float(os.getenv("openai_temperature", "0"))

# Fixed sampling seed. temperature=0 reduces run-to-run drift but does not fully
# guarantee it; passing a stable seed makes the model's output far more
# reproducible. The value (42) is arbitrary — any fixed number works; what
# matters is that it stays constant. Set openai_seed= (empty) in .env to disable.
_raw_seed = os.getenv("openai_seed", "42")
OPENAI_SEED = int(_raw_seed) if _raw_seed.strip() else None

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

# Max concurrent worker threads used to scrape articles in parallel (see
# sentiment_service._scrape_all_articles). Scraping is I/O-bound (blocking HTTP
# requests), so threads well beyond the CPU core count are still a net win.
SCRAPE_MAX_WORKERS = int(os.getenv("scrape_max_workers", "8"))

# --- In-memory caching (per process, cleared on restart) ------------------
#
# Both caches avoid redundant network calls when the same ticker or article
# URL is requested again shortly after — e.g. repeated demo runs, or two
# tickers whose news happens to cite the same article. Neither is meant to
# survive a restart or be shared across processes; that would need a real
# cache (Redis, etc.), which isn't warranted at this scale.

# How long a ticker's fetched Polygon news list stays cached before a fresh
# request is made again.
NEWS_CACHE_TTL_SECONDS = int(os.getenv("news_cache_ttl_seconds", "300"))

# How long a scraped article's full text stays cached before it is re-scraped.
SCRAPE_CACHE_TTL_SECONDS = int(os.getenv("scrape_cache_ttl_seconds", "300"))

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
