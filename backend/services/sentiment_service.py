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

from openai import OpenAI

import config
from services import polygon_client, scraper_service

# JSON schema for the structured response. Every property is required and
# additionalProperties is false, as mandated by OpenAI structured outputs.
#
# Note there is no "recommendation" field here: the model only judges sentiment
# and explains why. The recommendation label is derived deterministically from
# sentiment_score in _recommendation_for_score() below, so the label and the
# score can never disagree with each other.
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
                    "reason": {"type": "string", "description": "Reason for the sentiment_score"},
                    "source": {"type": "string", "description": "Source or web URL for the reason and sentiment_score"},
                },
                "required": ["ticker", "stock_name", "sentiment_score", "reason", "source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentiments"],
    "additionalProperties": False,
}

# Ordered high-to-low: first matching (min_score) threshold wins.
_RECOMMENDATION_THRESHOLDS = [
    (86, "Strongly Bullish"),
    (66, "Bullish"),
    (26, "Neutral"),
    (0,  "Bearish"),
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
    return "Bearish"


def _enrich_with_full_text(articles: list) -> list:
    """Attach scraped full article text to each article, when enabled.

    Only the first config.SCRAPE_ARTICLES_PER_TICKER articles are scraped (it is
    slow), and scraping failures are silently ignored — the model still gets the
    Polygon title/description for those. Returns the same list, mutated in place.
    """
    if not config.ENABLE_SCRAPING:
        return articles

    for article in articles[: config.SCRAPE_ARTICLES_PER_TICKER]:
        full_text = scraper_service.scrape_article(article.get("article_url"))
        if full_text:
            article["full_text"] = full_text
    return articles


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
- reason: a short justification grounded in the provided news
- source: the article/publisher the reasoning is based on

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

    # 1. Fetch news per ticker.
    news_by_ticker = {}
    tickers_with_news = []
    for symbol in watchlist:
        articles = polygon_client.fetch_news_for_ticker(symbol)
        if articles:
            news_by_ticker[symbol] = _enrich_with_full_text(articles)
            tickers_with_news.append(symbol)

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
                "source": "",
            })

    # Echo which mechanism produced these results (handy for demos / blog).
    resolved_method = method if method in _SCORERS else DEFAULT_METHOD
    return {"method": resolved_method, "sentiments": results}
