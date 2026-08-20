"""Grounding check: is every figure in the model's rationale actually in the source text?

The model is asked to score sentiment from provided news. Nothing stops it
from also drawing on its pretrained knowledge of these companies, which
produces rationales that read well and cite figures that were never in the
articles — indistinguishable from grounded output unless you check.

This extracts every number from each rationale and looks for it in the text
the model was given (titles, descriptions, and scraped full text). A number
that is not there was not retrieved.

    cd backend && ../venv/bin/python -m evals.check_grounding AAPL MSFT
"""
import re
import sys

import config
from services import polygon_client, sentiment_service

# Money, percentages, and bare decimals — the figures a rationale actually cites.
_NUMBER_RE = re.compile(r"\$?\d[\d,]*\.?\d*\s*(?:%|billion|million|trillion)?", re.IGNORECASE)

# Ignore values too generic to trace: small integers, years, the 1-100 score itself.
_SKIP = re.compile(r"^\$?(?:[0-9]|[1-9][0-9]|100|19\d\d|20\d\d)$")


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace so '$19.6 billion' matches '19.6  Billion'."""
    return re.sub(r"\s+", " ", text.lower())


def _figures(text: str) -> list:
    out = []
    for raw in _NUMBER_RE.findall(text or ""):
        token = raw.strip()
        core = token.rstrip("%").replace("$", "").replace(",", "").strip()
        if not core or _SKIP.match(core):
            continue
        out.append(token)
    return sorted(set(out), key=len, reverse=True)


def check(ticker: str) -> tuple:
    articles, _ = polygon_client.fetch_news_for_ticker(ticker)
    if not articles:
        print(f"{ticker}: no news")
        return 0, 0

    news = {ticker: articles}
    sentiment_service._scrape_all_articles(news)

    corpus = _normalize(" ".join(
        f"{a.get('title') or ''} {a.get('description') or ''} {a.get('full_text') or ''}"
        for a in articles
    ))

    result = sentiment_service.analyse_watchlist([ticker])
    entry = result["sentiments"][0]
    reason = entry.get("reason") or ""

    figures = _figures(reason)
    missing = []
    for fig in figures:
        # Match on the bare digits: the corpus may write it with different
        # currency/percent decoration than the rationale does.
        core = fig.rstrip("%").replace("$", "").replace(",", "").strip()
        core = re.sub(r"\s*(billion|million|trillion)$", "", core, flags=re.IGNORECASE).strip()
        if core and core not in corpus:
            missing.append(fig)

    scraped = sum(1 for a in articles if a.get("full_text"))
    print(f"\n{ticker}  score {entry['sentiment_score']}  ({scraped}/{len(articles)} articles scraped)")
    print(f"  rationale: {reason[:150]}...")
    print(f"  figures cited: {len(figures)}")
    if missing:
        print(f"  NOT IN SOURCE ({len(missing)}): {', '.join(missing)}")
    else:
        print("  all figures traced to source text")
    return len(figures), len(missing)


if __name__ == "__main__":
    tickers = [t.upper() for t in sys.argv[1:]] or ["AAPL", "MSFT", "NVDA"]
    print(f"scraper backend: {__import__('services.scraper_service', fromlist=['x']).backend_name()}")
    print(f"model: {config.OPENAI_MODEL}  temp: {config.OPENAI_TEMPERATURE}")

    total = ungrounded = 0
    for t in tickers:
        f, m = check(t)
        total += f
        ungrounded += m

    print(f"\n{'-' * 52}")
    if total:
        print(f"{ungrounded}/{total} cited figures absent from source "
              f"({100 * ungrounded / total:.0f}% ungrounded)")
    sys.exit(1 if ungrounded else 0)
