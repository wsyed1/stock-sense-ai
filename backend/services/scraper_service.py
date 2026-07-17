"""Article full-text scraping.

Prefers newspaper3k when it is installed (best extraction quality). Falls back
to a lightweight requests + HTML-strip approach so the feature works even when
newspaper3k (and its heavy deps) are not available in the environment.

All functions fail soft: on any error they return None rather than raising, so
a single unreachable article never breaks the whole sentiment run.
"""
import re

import requests

# newspaper3k is optional. Import lazily-guarded so the module always loads.
try:
    from newspaper import Article  # type: ignore
    _HAS_NEWSPAPER = True
except Exception:  # noqa: BLE001 — any import failure means we fall back
    _HAS_NEWSPAPER = False

# Cap extracted text so a huge article does not blow up the model prompt.
_MAX_CHARS = 4000

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _scrape_with_newspaper(url: str) -> str:
    article = Article(url)
    article.download()
    article.parse()
    return article.text or ""


def _scrape_with_requests(url: str) -> str:
    """Very small HTML-to-text fallback (no BeautifulSoup dependency)."""
    resp = requests.get(url, headers={"User-Agent": _UA}, timeout=15)
    resp.raise_for_status()
    html = resp.text
    html = _TAG_RE.sub(" ", html)   # drop <script>/<style> bodies
    text = _HTML_RE.sub(" ", html)  # strip remaining tags
    return _WS_RE.sub(" ", text).strip()


def scrape_article(url: str):
    """Return the article's text (truncated), or None if it cannot be fetched.

    Never raises — callers can treat None as "no full text available".
    """
    if not url:
        return None

    try:
        text = (
            _scrape_with_newspaper(url) if _HAS_NEWSPAPER
            else _scrape_with_requests(url)
        )
    except Exception:  # noqa: BLE001 — fail soft, article is simply skipped
        return None

    text = (text or "").strip()
    if not text:
        return None
    return text[:_MAX_CHARS]


def backend_name() -> str:
    """Which extraction backend is active (for diagnostics)."""
    return "newspaper3k" if _HAS_NEWSPAPER else "requests-fallback"
