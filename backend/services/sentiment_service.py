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
import re
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

GROUNDING RULES — these are strict:
1. Use ONLY the news data below. Do not add facts, figures, or context from
   your own knowledge of these companies, however confident you are in them.
2. Every number you state (revenue, growth rate, EPS, valuation, dates) must
   appear verbatim in the provided text. Copy it exactly — do not round,
   convert, restate, or infer it.
3. If the provided news is thin, say so and score accordingly. A short
   rationale citing two real figures is correct; a fuller one citing figures
   that are not in the text below is a failure.
4. Prefer quoting the article's own framing over paraphrasing it into a
   claim the article did not make.
5. Attach every figure to the exact subject the article attaches it to.
   If the text says "Azure revenue surpassed $100 billion", do not restate
   that as Azure Quantum, or as the company overall — a real number on the
   wrong subject is as wrong as an invented one.

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


# Figures a rationale might cite: money, percentages, scaled amounts.
_FIGURE_RE = re.compile(r"\$?\d[\d,]*\.?\d*\s*(?:%|billion|million|trillion)?", re.IGNORECASE)

# Values too generic to trace, and too common to be worth flagging: single and
# double digits, 100 (the score ceiling), and four-digit years.
_GENERIC_FIGURE_RE = re.compile(r"^(?:\d{1,2}|100|19\d\d|20\d\d)$")


def _figure_key(figure: str) -> str:
    """Reduce a cited figure to bare digits for corpus matching.

    '$19.6 billion', '19.6%', and '19.6' all reduce to '19.6', so a figure
    written one way in the article and another in the rationale still matches.
    """
    core = figure.strip().rstrip("%").replace("$", "").replace(",", "")
    core = re.sub(r"\s*(billion|million|trillion)\s*$", "", core, flags=re.IGNORECASE)
    return core.strip()


def _ungrounded_figures(reason: str, articles: list) -> list:
    """Return figures in `reason` that appear nowhere in the source articles.

    The model is told to use only the provided text, but instructions alone
    don't guarantee it — measured rates of untraceable figures stayed non-zero
    even with explicit grounding rules in the prompt. This checks rather than
    trusts: every number in the rationale must be present in the corpus the
    model was actually given.
    """
    corpus = " ".join(
        f"{a.get('title') or ''} {a.get('description') or ''} {a.get('full_text') or ''}"
        for a in articles
    )
    corpus = re.sub(r"\s+", " ", corpus.lower())
    # Normalise percent forms so "43 %" and "43 percent" both match "43%".
    corpus = re.sub(r"(\d)\s*(?:%|percent)", r"\1%", corpus)

    ungrounded = []
    for raw in _FIGURE_RE.findall(reason or ""):
        token = raw.strip()
        key = _figure_key(token)
        if not key:
            continue
        # A bare small integer ("three of five") is untraceable and not worth
        # flagging — but the same digits carrying a unit are a real claim, so
        # "41%" and "$41 billion" must still be checked.
        has_unit = "%" in token or "$" in token or re.search(
            r"(billion|million|trillion)", token, re.IGNORECASE
        )
        if not has_unit and _GENERIC_FIGURE_RE.match(key):
            continue
        # Match with the unit attached, not the bare digits. "43%" must not be
        # satisfied by "$43 billion", and "$100 billion" must not be satisfied
        # by a stray "100" — the scale word is part of the claim.
        scale = re.search(r"(billion|million|trillion)", token, re.IGNORECASE)
        if "%" in token:
            needle = rf"{re.escape(key)}\s*%"
        elif scale:
            needle = rf"{re.escape(key)}\s*{scale.group(1).lower()}"
        else:
            needle = re.escape(key)
        # Require a digit boundary, or "43%" matches "2.43%" — a different
        # number entirely, often an unrelated ticker's price change.
        if not re.search(r"(?<![\d.])" + needle, corpus):
            ungrounded.append(token)
    return sorted(set(ungrounded))


def _strip_ungrounded_sentences(reason: str, articles: list) -> tuple:
    """Drop sentences citing figures absent from the source articles.

    Returns (cleaned_reason, dropped_sentences). Sentence-level rather than
    all-or-nothing: a rationale is usually mostly grounded with one invented
    figure, so removing that sentence keeps the useful analysis and discards
    only the unsupported claim. What reaches the UI is then traceable by
    construction, not by trusting the model to have followed instructions.
    """
    if not reason:
        return reason, []

    ungrounded = _ungrounded_figures(reason, articles)
    if not ungrounded:
        return reason, []

    # Split on sentence boundaries only — a period followed by whitespace and
    # a capital letter (or end of string). A naive [.!?] split also breaks
    # decimals, turning "$4.74 EPS" into "$4." and "74 EPS".
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])", reason.strip())
    kept, dropped = [], []
    for sentence in sentences:
        if any(fig in sentence for fig in ungrounded):
            dropped.append(sentence.strip())
        else:
            kept.append(sentence.strip())

    cleaned = " ".join(s for s in kept if s).strip()
    # Never return an empty rationale — if every sentence was unsupported,
    # the score itself is suspect and the caller should see that plainly.
    if not cleaned:
        return "Recent coverage was too thin to support a specific rationale.", dropped
    return cleaned, dropped


def _sources_for_ticker(articles: list) -> list:
    """Build a ticker's source list deterministically from the fetched articles.

    Cites EVERY article included in the prompt, not just the ones scraped for
    full text. Only the first config.SCRAPE_ARTICLES_PER_TICKER articles get
    scraped, but all of them reach the model (the rest via title/description),
    so the model can — and does — reason from an article that was never
    scraped. Citing only the scraped subset produced results whose figures
    traced back to an uncited article, which defeats the point of citing at
    all.

    `full_text` marks which sources the model saw in full versus by summary.
    Never derived from the model's output: titles/URLs it wasn't given verbatim
    could be wrong, so this reads straight from the fetched articles instead.
    """
    sources = []
    for article in articles:
        url = article.get("article_url")
        if not url:
            continue
        sources.append({
            "title": article.get("title") or url,
            "url": url,
            "publisher": (article.get("publisher") or {}).get("name") or "",
            "full_text": bool(article.get("full_text")),
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
                articles = news_by_ticker.get(symbol) or []
                entry["sources"] = _sources_for_ticker(articles)
                # 3b. Verify the rationale against the source text and strip any
                #     sentence citing a figure the articles never contained.
                entry["reason"], dropped = _strip_ungrounded_sentences(
                    entry.get("reason") or "", articles
                )
                if dropped:
                    entry["grounding_note"] = (
                        f"{len(dropped)} statement(s) removed: cited figures not "
                        f"found in the source articles."
                    )
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
