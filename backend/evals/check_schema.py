"""Shape / schema eval for StockSense sentiment responses.

This is the regression-catcher: it asserts the *structure* of a response is
correct, independent of whether the sentiment judgement is any good. Run it after
changing a prompt, the schema, or the model to catch a broken output shape fast.

It validates that, for a given list of requested tickers, the result:
  * has exactly one row per requested ticker (order-independent),
  * has no rows for tickers that were NOT requested,
  * every sentiment_score is an int in 1..100 (or 0 for a "No Data" row),
  * every recommendation is one of the allowed labels.

By default it validates a captured SAMPLE (no API calls, no cost). Pass --live
with tickers to validate a real response instead.

Run from the backend/ directory:

    cd backend && ../venv/bin/python -m evals.check_schema
    ../venv/bin/python -m evals.check_schema --live AAPL,NVDA
"""
import sys

import config
from services import sentiment_service

# Allowed recommendation labels: the score-derived ones plus the No-Data sentinel.
_ALLOWED_LABELS = {
    "Strongly Bullish", "Bullish", "Neutral", "Bearish", "No Data",
}

# A captured, well-formed sample so the shape eval can run offline for free.
SAMPLE_REQUEST = ["AAPL", "NVDA", "ZZZZ"]
SAMPLE_RESULT = {
    "method": "structured",
    "sentiments": [
        {"ticker": "AAPL", "stock_name": "Apple Inc.", "sentiment_score": 82,
         "recommendation": "Bullish", "reason": "Strong product cycle.", "source": "Reuters"},
        {"ticker": "NVDA", "stock_name": "NVIDIA Corp.", "sentiment_score": 90,
         "recommendation": "Strongly Bullish", "reason": "AI demand.", "source": "Bloomberg"},
        {"ticker": "ZZZZ", "stock_name": "ZZZZ", "sentiment_score": 0,
         "recommendation": "No Data", "reason": "No recent news was found for this ticker.", "source": ""},
    ],
}

_REQUIRED_FIELDS = ["ticker", "stock_name", "sentiment_score", "recommendation", "reason", "source"]


def validate_shape(requested_tickers: list, result: dict) -> list:
    """Return a list of problem strings. Empty list means the shape is valid."""
    problems = []

    sentiments = result.get("sentiments")
    if not isinstance(sentiments, list):
        return ["'sentiments' is missing or not a list"]

    requested = [t.strip().upper() for t in requested_tickers if t.strip()]
    returned = [(row.get("ticker") or "").strip().upper() for row in sentiments]

    # One row per requested ticker, and nothing extra.
    missing = set(requested) - set(returned)
    extra = set(returned) - set(requested)
    if missing:
        problems.append(f"missing rows for requested tickers: {sorted(missing)}")
    if extra:
        problems.append(f"unexpected rows for non-requested tickers: {sorted(extra)}")
    if len(sentiments) != len(requested):
        problems.append(
            f"expected {len(requested)} rows, got {len(sentiments)}"
        )

    # Per-row field checks.
    for row in sentiments:
        ticker = row.get("ticker", "<?>")

        for field in _REQUIRED_FIELDS:
            if field not in row:
                problems.append(f"{ticker}: missing field '{field}'")

        score = row.get("sentiment_score")
        if not isinstance(score, int) or isinstance(score, bool):
            problems.append(f"{ticker}: sentiment_score is not an int ({score!r})")
        elif not (score == 0 or 1 <= score <= 100):
            problems.append(f"{ticker}: sentiment_score {score} outside 1..100 (0=No Data)")

        label = row.get("recommendation")
        if label not in _ALLOWED_LABELS:
            problems.append(f"{ticker}: recommendation '{label}' not in {sorted(_ALLOWED_LABELS)}")

    return problems


def _report(requested, result) -> bool:
    problems = validate_shape(requested, result)
    if problems:
        print(f"SHAPE INVALID ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return False
    print(f"SHAPE VALID: {len(result['sentiments'])} rows, one per requested ticker.")
    return True


if __name__ == "__main__":
    if "--live" in sys.argv:
        idx = sys.argv.index("--live")
        tickers = sys.argv[idx + 1].split(",") if len(sys.argv) > idx + 1 else config.DEMO_WATCHLIST
        print(f"Validating LIVE response for {tickers}\n")
        result = sentiment_service.analyse_watchlist(tickers)
    else:
        print("Validating captured SAMPLE (no API calls)\n")
        tickers = SAMPLE_REQUEST
        result = SAMPLE_RESULT

    ok = _report(tickers, result)
    sys.exit(0 if ok else 1)
