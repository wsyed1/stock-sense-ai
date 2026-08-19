"""Watchlist sentiment analysis.

Given a list of watchlist tickers, fetch recent news for each, ask the model to
score sentiment, and return exactly one result per requested ticker (results for
tickers merely *mentioned* in the news but not on the watchlist are dropped).

This module deliberately demonstrates TWO ways to get consistent, schema-valid
JSON out of an OpenAI model, so they can be compared side by side:

  * "structured"  — response_format with a strict json_schema (the modern,
                    recommended approach). See _score_structured_outputs().
  * "function"    — classic function / tool calling: the schema is declared as a
                    function's parameters, the model "calls" it, and we read the
                    arguments. See _score_function_calling().

Both share the exact same JSON schema (_SENTIMENT_SCHEMA) and prompt, so the only
difference is the API mechanism used to enforce structure.
"""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

import config
from services import polygon_client, scraper_service

# In-memory cache for scraped article text: article_url -> (fetched_at, text).
# Kept here rather than in scraper_service so that module stays a pure
# "fetch this URL" function with no caching concerns of its own. Per-process
# only — see config.SCRAPE_CACHE_TTL_SECONDS for the expiry window.
_scrape_cache = {}


def _scrape_article_cached(url: str) -> tuple:
    """scraper_service.scrape_article(), memoized by URL for a TTL.

    Returns (text, was_cached). Two tickers whose news cites the same
    article, or the same article scraped again shortly after, skip the
    network fetch entirely on a hit.
    """
    cached = _scrape_cache.get(url)
    if cached is not None:
        fetched_at, text = cached
        if time.monotonic() - fetched_at < config.SCRAPE_CACHE_TTL_SECONDS:
            return text, True

    text = scraper_service.scrape_article(url)
    _scrape_cache[url] = (time.monotonic(), text)
    return text, False

# JSON schema for the structured response. Every property is required and
# additionalProperties is false, as mandated by OpenAI structured outputs.
#
# Note there is no "recommendation" or "sources" field here: the model only
# judges sentiment and explains why, in more depth than a one-liner. The
# recommendation label is derived deterministically from sentiment_score in
# _recommendation_for_score() below, and the sources list is built directly
# from news_by_ticker's real Polygon article data in analyse_watchlist() — the
# model is never trusted to invent or recall URLs/titles it was only shown as
# part of a large prompt.
_SENTIMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Symbol used to represent the stock"},
                    "stock_name": {"type": "string", "description": "Full name of the stock"},
                    "sentiment_score": {"type": "integer", "description": "Score between 1-100 of the sentiment"},
                    "reason": {
                        "type": "string",
                        "description": (
                            "A detailed, multi-sentence explanation (3-5 sentences) of the "
                            "sentiment_score, grounded in specifics from the provided news: "
                            "name the concrete events, numbers, or developments driving the "
                            "score, not just a one-line summary."
                        ),
                    },
                },
                "required": ["ticker", "stock_name", "sentiment_score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentiments"],
    "additionalProperties": False,
}

# Ordered high-to-low: first matching (min_score) threshold wins. Symmetric
# around 50 (Neutral) — see getBarColor/getBadgeClass in frontend/js/app.js,
# which must stay in sync with these same seven bands.
_RECOMMENDATION_THRESHOLDS = [
    (90, "Strongly Bullish"),
    (75, "Bullish"),
    (60, "Slightly Bullish"),
    (41, "Neutral"),
    (26, "Slightly Bearish"),
    (11, "Bearish"),
    (0,  "Strongly Bearish"),
]


def _recommendation_for_score(sentiment_score) -> str:
    """Deterministically map a 1-100 sentiment score to a recommendation label.

    Keeping this out of the model's hands guarantees the badge shown to users
    always agrees with the score bar next to it.
    """
    try:
        score = int(sentiment_score)
    except (TypeError, ValueError):
        return "No Data"
    for min_score, label in _RECOMMENDATION_THRESHOLDS:
        if score >= min_score:
            return label
    return "Strongly Bearish"


def _scrape_all_articles(news_by_ticker: dict) -> bool:
    """Attach scraped full article text to articles, across ALL tickers at once.

    Only the first config.SCRAPE_ARTICLES_PER_TICKER articles per ticker are
    scraped (it is slow). Mutates the article dicts in news_by_ticker in place.
    Returns True if every scrape job was served from cache (or there were no
    jobs at all), False if at least one required a live fetch.

    Scraping is dispatched through a ThreadPoolExecutor rather than asyncio:
    scraper_service.scrape_article() calls newspaper3k/requests, both of which
    are blocking (synchronous) I/O under the hood with no async-native API, so
    there is no coroutine to await — threads are what actually let many of
    these blocking downloads run concurrently. Every article across every
    ticker is flattened into one job list first so the thread pool is shared
    watchlist-wide, instead of paying the sequential cost once per ticker.
    """
    if not config.ENABLE_SCRAPING:
        return True

    jobs = [
        article
        for articles in news_by_ticker.values()
        for article in articles[: config.SCRAPE_ARTICLES_PER_TICKER]
    ]
    if not jobs:
        return True

    all_cached = True
    with ThreadPoolExecutor(max_workers=config.SCRAPE_MAX_WORKERS) as executor:
        future_to_article = {
            executor.submit(_scrape_article_cached, article.get("article_url")): article
            for article in jobs
        }
        # A single slow/failed article must never block or crash the others —
        # scrape_article() already fails soft (returns None), and iterating via
        # as_completed() means one hung future can't hold up results that are
        # already done.
        for future in as_completed(future_to_article):
            full_text, was_cached = future.result()
            if not was_cached:
                all_cached = False
            if full_text:
                future_to_article[future]["full_text"] = full_text
    return all_cached


def _build_prompt(tickers: list, news_by_ticker: dict) -> str:
    """Build a prompt that pins the analysis to the requested tickers only."""
    ticker_list = ", ".join(tickers)
    return f"""
You are given recent news articles for a stock watchlist.

Analyse the sentiment for EACH of these watchlist tickers only: {ticker_list}.
Return exactly one entry per watchlist ticker listed above — do not add entries
for other companies that merely appear in the news.

For each ticker provide:
- sentiment_score: an integer from 1 (very negative) to 100 (very positive)
- reason: a detailed, multi-sentence explanation (3-5 sentences). Name the
  concrete events, figures, or developments from the news that drove the
  score — not a generic one-line summary.

Where an article includes a "full_text" field, prefer it over the shorter
"description" when forming your judgement.

News data by ticker (JSON):
{json.dumps(news_by_ticker)}
""".strip()


# --- Two mechanisms for structured model output ---------------------------

def _score_structured_outputs(client, tickers_with_news, news_by_ticker) -> list:
    """Get JSON via response_format + strict json_schema (modern approach).

    The model is constrained to emit JSON matching _SENTIMENT_SCHEMA, returned as
    a JSON string in message.content.
    """
    completion = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=config.OPENAI_TEMPERATURE,
        seed=config.OPENAI_SEED,
        messages=[
            {"role": "system", "content": "You are a helpful stock-news sentiment analyst."},
            {"role": "user", "content": _build_prompt(tickers_with_news, news_by_ticker)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "stock_sentiments",
                "strict": True,
                "schema": _SENTIMENT_SCHEMA,
            },
        },
    )
    parsed = json.loads(completion.choices[0].message.content)
    return parsed.get("sentiments", [])


def _score_function_calling(client, tickers_with_news, news_by_ticker) -> list:
    """Get JSON via classic function / tool calling.

    Here the same schema is declared as a function's `parameters`. We force the
    model to call that function with tool_choice, then read the structured JSON
    out of message.tool_calls[0].function.arguments instead of content.
    """
    tools = [{
        "type": "function",
        "function": {
            "name": "record_stock_sentiments",
            "description": "Record the sentiment analysis for each watchlist ticker.",
            "parameters": _SENTIMENT_SCHEMA,
            "strict": True,
        },
    }]
    completion = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=config.OPENAI_TEMPERATURE,
        seed=config.OPENAI_SEED,
        messages=[
            {"role": "system", "content": "You are a helpful stock-news sentiment analyst."},
            {"role": "user", "content": _build_prompt(tickers_with_news, news_by_ticker)},
        ],
        tools=tools,
        # Force the model to call our function rather than reply with free text.
        tool_choice={"type": "function", "function": {"name": "record_stock_sentiments"}},
    )
    tool_calls = completion.choices[0].message.tool_calls or []
    if not tool_calls:
        return []
    arguments = json.loads(tool_calls[0].function.arguments)
    return arguments.get("sentiments", [])


def _sources_for_ticker(articles: list) -> list:
    """Build a ticker's source list deterministically from Polygon's own data.

    Only the first config.SCRAPE_ARTICLES_PER_TICKER articles are included —
    the same ones _scrape_all_articles() actually fetched full text for, so
    "sources" lines up with what the model was shown in most detail. Never
    derived from the model's output: titles/URLs it wasn't given verbatim
    could be wrong, so this reads straight from the Polygon articles instead.
    """
    sources = []
    for article in articles[: config.SCRAPE_ARTICLES_PER_TICKER]:
        url = article.get("article_url")
        if not url:
            continue
        sources.append({
            "title": article.get("title") or url,
            "url": url,
            "publisher": (article.get("publisher") or {}).get("name") or "",
        })
    return sources


# Dispatch table: method name -> scoring function.
_SCORERS = {
    "structured": _score_structured_outputs,
    "function": _score_function_calling,
}
DEFAULT_METHOD = "structured"


def analyse_watchlist(tickers: list, method: str = DEFAULT_METHOD) -> dict:
    """Return {"sentiments": [...]} with one entry per requested ticker.

    Tickers with no news are still returned, marked as having no coverage, so
    the caller always gets a predictable one-row-per-watchlist-ticker result.

    `method` selects how structured JSON is obtained from the model:
    "structured" (json_schema) or "function" (function/tool calling).
    """
    scorer = _SCORERS.get(method, _SCORERS[DEFAULT_METHOD])
    # Normalise: uppercase, de-duplicate, preserve order.
    seen = set()
    watchlist = []
    for raw in tickers:
        symbol = raw.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            watchlist.append(symbol)

    # 1. Fetch news per ticker. Kept sequential — it's a fast, cheap call per
    #    ticker, so parallelizing it isn't worth the added complexity.
    news_by_ticker = {}
    tickers_with_news = []
    all_cached = True
    for symbol in watchlist:
        articles, was_cached = polygon_client.fetch_news_for_ticker(symbol)
        if not was_cached:
            all_cached = False
        if articles:
            news_by_ticker[symbol] = articles
            tickers_with_news.append(symbol)

    # 1b. Scrape full article text for all tickers' articles concurrently, in
    #     one shared thread pool, instead of one ticker (and one article) at a
    #     time. This is the slow part of step 1, so it's where concurrency pays
    #     off the most.
    if not _scrape_all_articles(news_by_ticker):
        all_cached = False

    # 2. Score the tickers that actually have news, in one model pass, using the
    #    selected mechanism (structured outputs or function calling).
    scored_by_ticker = {}
    if tickers_with_news:
        client = OpenAI(api_key=config.get_openai_api_key())
        sentiments = scorer(client, tickers_with_news, news_by_ticker)
        for entry in sentiments:
            symbol = (entry.get("ticker") or "").strip().upper()
            # 3. Filter: keep only tickers that are on the requested watchlist.
            if symbol in seen:
                entry["recommendation"] = _recommendation_for_score(entry.get("sentiment_score"))
                entry["sources"] = _sources_for_ticker(news_by_ticker.get(symbol) or [])
                scored_by_ticker[symbol] = entry

    # 4. Return one row per requested ticker, in the original order.
    results = []
    for symbol in watchlist:
        if symbol in scored_by_ticker:
            results.append(scored_by_ticker[symbol])
        else:
            results.append({
                "ticker": symbol,
                "stock_name": symbol,
                "sentiment_score": 0,
                "recommendation": "No Data",
                "reason": "No recent news was found for this ticker.",
                "sources": [],
            })

    # Echo which mechanism produced these results (handy for demos / blog).
    resolved_method = method if method in _SCORERS else DEFAULT_METHOD
    # "cached" is True only if every underlying Polygon/scrape call this
    # request needed was served from cache — a single live fetch marks the
    # whole watchlist as fresh, since some of the data really was just fetched.
    return {"method": resolved_method, "sentiments": results, "cached": all_cached}
